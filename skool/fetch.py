"""Skool transport: plain curl_cffi with browser-impersonated TLS. No
browser, no cookies, no token. Egress: the pod's own IP (config.skool_proxy(),
knob SKOOL_EXIT = "direct") — every surface below answered 200 from the
patchright pod on 2026-11-03 (table in config.py's skool block); a retryable
failure drops the thread's session so a retry on a proxied tier rides a
fresh exit.

Two upstream hosts, both open to a bare GET:

  * PAGE DATA  GET www.skool.com/_next/data/<buildId>/<route>.json?<query>
    The Next.js data route of every page: the discovery directory
    (/discovery, 30 cards per page, 1000-result cap), a community's feed
    (/<slug>), about, plans, members, leaderboards, classroom, course,
    calendar, in-community search (/<slug>/-/search), a post page
    (/<slug>/<post-slug>) and a profile (/@handle). The HTML /discovery
    page is behind an AWS WAF JS challenge (202 + x-amzn-waf-action:
    challenge on every exit and TLS profile), the JSON route is not.
    The buildId changes on every Skool deploy; a stale one answers 404
    with the site's 404 HTML, which itself carries the current buildId
    (__NEXT_DATA__), so a 404 HTML refreshes it and retries once. A real
    unknown slug answers 404 {"notFound":true}. Private communities send
    their feed / members / classroom / calendar as a 307 redirect to
    /<slug>/about (`__N_REDIRECT` in the JSON); a discovery query with no
    match redirects to itself with lang=all.

  * API        GET api2.skool.com/posts/<id>/comments?group-id=..&limit=25
    (cursor: the response's `last` -> next call's created-gt), /groups/<id>
    /reviews?limit=&offset=, /users/<id>, /calendar-events/<id>. Unknown
    ids answer 404 "<kind> not found: <id>".

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  SkoolUpstreamError  transport failure / 5xx / stale buildId   — retryable
  SkoolBlocked        403 / 429 / WAF challenge page            — retryable
  SkoolBadRequest     upstream 400 (invalid sort, tag, ...)     — never retried
  SkoolNotFound       unknown community / post / user / course  — never retried
"""
import json
import os
import re
import sys
import threading
import time

# Allow direct execution (python skool/fetch.py): flat imports resolve like
# under the server. Idempotent when imported normally.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import egress
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from skool.refs import API, SITE

IMPERSONATE = "chrome"
PAGE_TIMEOUT = 30     # feed / member pages are 300-600 KB
API_TIMEOUT = 20

DATA_HEADERS = {
    "accept": "*/*",
    "accept-language": egress.site_accept_language("skool"),
    "x-nextjs-data": "1",
    "referer": SITE + "/",
}
API_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": egress.site_accept_language("skool"),
    "origin": SITE,
    "referer": SITE + "/",
}

_BUILD_ID_RE = re.compile(r'"buildId":"([^"]+)"')
BOOTSTRAP_BUILD = "bootstrap"   # any unknown buildId -> the 404 page with the real one


class SkoolUpstreamError(UpstreamError):
    """Transport failure, 5xx or a stale buildId — retryable."""


class SkoolBlocked(SkoolUpstreamError, Blocked):
    """403 / 429 or the AWS WAF challenge page — retryable."""


class SkoolBadRequest(BadRequest):
    """Upstream 400 — never retried."""


class SkoolNotFound(NotFound):
    """Community / post / user / course does not exist — never retried."""

    def __init__(self, message, reason=None, **details):
        super().__init__(message)
        self.reason = reason
        self.details = details


class _StaleBuild(SkoolUpstreamError):
    """The data route 404ed with the 404 page: buildId refreshed, retry."""


# One session per cheroot worker thread: a curl handle must not be shared
# across threads; these GETs are stateless so thread-lifetime sessions with
# keep-alive are enough.
_local = threading.local()

# The Next.js buildId, shared by every thread (one refresh serves all).
_build = {"id": None}
_build_lock = threading.Lock()


def _session():
    sess = getattr(_local, "session", None)
    if sess is None:
        from curl_cffi import requests as curl_requests
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        proxy = config.skool_proxy()
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
            sess.headers["accept-language"] = egress.accept_language(proxy)
        _local.session = sess
    return sess


def _drop_session():
    """Close the thread's session so a poisoned keep-alive connection dies
    and the retry rides a fresh exit."""
    sess = getattr(_local, "session", None)
    _local.session = None
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _retrying(fn):
    """Run fn() under the shared retry policy (SkoolUpstreamError only;
    NotFound / BadRequest surface immediately)."""
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return fn()
        except _StaleBuild as e:
            last = e           # not a transport fault: keep the session, retry at once
        except SkoolUpstreamError as e:
            last = e
            _drop_session()
            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


def _is_challenge(resp):
    return (resp.headers.get("x-amzn-waf-action") == "challenge"
            or "awswaf" in (resp.text or "")[:3000].lower())


def _classify(resp, label):
    """Map the shared statuses to the taxonomy (404 is handled per surface)."""
    if resp.status_code == 202 or _is_challenge(resp):
        raise SkoolBlocked(f"AWS WAF challenge for {label}")
    if resp.status_code == 400:
        raise SkoolBadRequest(resp.text[:200])
    if resp.status_code in (401, 403, 429):
        raise SkoolBlocked(f"HTTP {resp.status_code} for {label}")
    if resp.status_code != 200:
        raise SkoolUpstreamError(f"HTTP {resp.status_code} for {label}")


# ---- buildId --------------------------------------------------------------------

def parse_build_id(html):
    match = _BUILD_ID_RE.search(html or "")
    return match.group(1) if match else None


def _set_build_id(value):
    with _build_lock:
        changed = bool(value) and value != _build["id"]
        if changed:
            _build["id"] = value
    return changed


def _build_id():
    """The current buildId; bootstrapped from the site's own 404 page (a
    data route with an unknown buildId answers it, 2.5 KB)."""
    with _build_lock:
        current = _build["id"]
    if current:
        return current
    try:
        resp = _session().get(f"{SITE}/_next/data/{BOOTSTRAP_BUILD}/discovery.json",
                              headers=DATA_HEADERS, timeout=API_TIMEOUT)
    except Exception as e:
        raise SkoolUpstreamError(f"buildId bootstrap failed: {type(e).__name__}: {e}")
    if resp.status_code == 404:
        build = parse_build_id(resp.text)
        if build:
            _set_build_id(build)
            return build
        raise SkoolUpstreamError("buildId bootstrap: no __NEXT_DATA__ on the 404 page")
    _classify(resp, "buildId bootstrap")
    raise SkoolUpstreamError(f"buildId bootstrap: unexpected HTTP {resp.status_code}")


# ---- page data ------------------------------------------------------------------

def fetch_page_props(route, query, label):
    """GET the Next.js data route for `route` ("/discovery", "/<slug>/about",
    "/@handle", ...) -> its pageProps dict. A `__N_REDIRECT` pageProps is
    returned as is (the caller decides what the redirect means)."""
    def once():
        build = _build_id()
        url = f"{SITE}/_next/data/{build}{route}.json"
        try:
            resp = _session().get(url, params={k: v for k, v in (query or {}).items() if v is not None},
                                  headers=DATA_HEADERS, timeout=PAGE_TIMEOUT)
        except Exception as e:
            raise SkoolUpstreamError(f"request failed: {type(e).__name__}: {e}")
        if resp.status_code == 404:
            text = resp.text or ""
            if text.lstrip().startswith("{"):
                raise SkoolNotFound(f"{label} not found")
            # compare with the buildId THIS request used, not the shared one:
            # another thread may already have refreshed it, and this 404 is
            # still the stale-build page, not a missing entity
            fresh = parse_build_id(text)
            if fresh and fresh != build:
                _set_build_id(fresh)
                raise _StaleBuild(f"buildId {build} is stale")
            raise SkoolNotFound(f"{label} not found")
        # a page whose backend call failed is served with the error inside
        # pageProps.settings.error (HTTP 200 or 400 alike)
        _raise_page_error(resp, label)
        _classify(resp, label)
        try:
            payload = resp.json()
        except Exception:
            if _is_challenge(resp):
                raise SkoolBlocked(f"AWS WAF challenge for {label}")
            raise SkoolUpstreamError(f"non-JSON page data for {label}: {resp.text[:120]}")
        props = payload.get("pageProps") if isinstance(payload, dict) else None
        if not isinstance(props, dict):
            raise SkoolUpstreamError(f"unexpected page data shape for {label}")
        return props
    return _retrying(once)


def _raise_page_error(resp, label):
    """pageProps.settings.error {status, data} -> the taxonomy: 404 (an
    unknown community on a tab page) -> NotFound, 400 (invalid sort /
    tag / date) -> BadRequest with Skool's own message, 5xx -> upstream."""
    if resp.status_code not in (200, 400, 500):
        return
    text = resp.text or ""
    if not text.lstrip().startswith("{") or '"error"' not in text:
        return
    try:
        props = (resp.json() or {}).get("pageProps") or {}
    except Exception:
        return
    settings = props.get("settings") if isinstance(props, dict) else None
    error = settings.get("error") if isinstance(settings, dict) else None
    if not isinstance(error, dict):
        return
    status = error.get("status")
    message = str(error.get("data") or "").strip()
    # the calendar of an unknown community answers 400 "group param required"
    if status == 404 or "not found" in message.lower() or message == "group param required":
        raise SkoolNotFound(f"{label} not found")
    if status == 400 or resp.status_code == 400:
        raise SkoolBadRequest(message[:200] or "bad request")
    raise SkoolUpstreamError(f"upstream {status} for {label}: {message[:120]}")


def redirect_target(props):
    """The `__N_REDIRECT` path of a redirecting pageProps, else None."""
    target = props.get("__N_REDIRECT") if isinstance(props, dict) else None
    return target if isinstance(target, str) and target else None


# ---- api2 -----------------------------------------------------------------------

def fetch_api(path, query, label):
    """GET api2.skool.com<path> -> parsed JSON."""
    def once():
        try:
            resp = _session().get(API + path, params={k: v for k, v in (query or {}).items() if v is not None},
                                  headers=API_HEADERS, timeout=API_TIMEOUT)
        except Exception as e:
            raise SkoolUpstreamError(f"request failed: {type(e).__name__}: {e}")
        if resp.status_code == 404:
            raise SkoolNotFound(f"{label} not found")
        _classify(resp, label)
        try:
            return resp.json()
        except Exception:
            raise SkoolUpstreamError(f"non-JSON API response for {label}: {resp.text[:120]}")
    return _retrying(once)


# ---- the surfaces -----------------------------------------------------------------

def fetch_discovery(query=None, category=None, price=None, group_type=None, language=None,
                    sort=None, page=1):
    """One directory page (30 cards). A query with no match redirects to
    lang=all; that redirect is followed once so the caller sees the empty
    (or language-widened) page Skool itself shows."""
    params = {"q": query, "c": category, "pr": price, "ty": group_type, "lang": language,
              "srt": sort, "p": page if page and page > 1 else None}
    props = fetch_page_props("/discovery", params, "discovery")
    target = redirect_target(props)
    if target and target.startswith("/discovery"):
        from urllib.parse import parse_qs, urlparse
        redirected = {k: v[0] for k, v in parse_qs(urlparse(target).query).items() if v}
        if redirected != {k: str(v) for k, v in params.items() if v is not None}:
            props = fetch_page_props("/discovery", redirected, "discovery")
    return props


def fetch_community_feed(slug, label=None, page=1):
    return fetch_page_props(f"/{slug}", {"group": slug, "c": label, "p": page if page > 1 else None},
                            f"community {slug}")


def fetch_community_about(slug):
    return fetch_page_props(f"/{slug}/about", {"group": slug}, f"community {slug}")


def fetch_community_plans(slug):
    return fetch_page_props(f"/{slug}/plans", {"group": slug}, f"community {slug} plans")


def fetch_community_members(slug, tab=None, sort_type=None, levels=None, page=1):
    params = {"group": slug, "t": tab if tab and tab != "member" else None, "sortType": sort_type,
              "levels": levels, "p": page if page > 1 else None}
    return fetch_page_props(f"/{slug}/-/members", params, f"community {slug} members")


def fetch_community_leaderboards(slug):
    return fetch_page_props(f"/{slug}/-/leaderboards", {"group": slug}, f"community {slug} leaderboards")


def fetch_community_classroom(slug):
    return fetch_page_props(f"/{slug}/classroom", {"group": slug}, f"community {slug} classroom")


def fetch_community_course(slug, course, module_id=None):
    params = {"group": slug, "course": course, "md": module_id}
    return fetch_page_props(f"/{slug}/classroom/{course}", params, f"course {course} of {slug}")


def fetch_community_calendar(slug, cal_date=None):
    return fetch_page_props(f"/{slug}/calendar", {"group": slug, "calDate": cal_date},
                            f"community {slug} calendar")


def fetch_community_search(slug, query, tab=None, page=1):
    params = {"group": slug, "q": query, "t": tab if tab and tab != "posts" else None,
              "p": page if page > 1 else None}
    return fetch_page_props(f"/{slug}/-/search", params, f"community {slug} search")


def fetch_post(slug, post):
    return fetch_page_props(f"/{slug}/{post}", {"group": slug, "post": post}, f"post {slug}/{post}")


def fetch_user(handle, tab=None, page=1):
    params = {"user": handle, "t": tab, "p": page if page > 1 else None}
    return fetch_page_props(f"/@{handle}", params, f"user @{handle}")


def fetch_comments(post_id, group_id, created_after=None, limit=25, pinned=False):
    params = {"group-id": group_id, "limit": limit, "created-gt": created_after,
              "pinned": "true" if pinned else None}
    return fetch_api(f"/posts/{post_id}/comments", params, f"comments of post {post_id}")


def fetch_reviews(group_id, limit=10, offset=0):
    return fetch_api(f"/groups/{group_id}/reviews", {"limit": limit, "offset": offset or None},
                     f"reviews of community {group_id}")
