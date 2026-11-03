"""The /skool/* endpoint functions (route_glue's route_table calls them
with the schema's loaded kwargs).

Caching lives here (cache.cached_call, keyed on the validated params). The
community record (about page + plans page for tiered communities) is
cached ONCE per slug under skool.community and sliced by details, reviews
(the group id) and posts (channel names), so hitting them all on one
community costs one upstream fetch. A post page is cached once per
community/post and serves both posts/details and the comment pages (which
need the post id and group id).

Private communities: Skool answers their feed / members / classroom /
calendar / search with a redirect to the about page; those endpoints raise
NotFound with reason "private" (the about page, plans and reviews stay
public and work).
"""
import calendar
import re
from datetime import date, datetime, timezone

from cache import cached_call
from skool import cache_config as ttl
from skool import parsers, refs
from skool.fetch import (SkoolNotFound, fetch_comments, fetch_community_about, fetch_community_calendar,
                         fetch_community_classroom, fetch_community_course, fetch_community_feed,
                         fetch_community_leaderboards, fetch_community_members, fetch_community_plans,
                         fetch_community_search, fetch_discovery, fetch_post, fetch_reviews, fetch_user,
                         redirect_target)

DISCOVERY_PAGE_SIZE = 30
COMMENTS_PAGE_SIZE = 25
_MD_RE = re.compile(r"[?&]md=([0-9a-f]{32})")


def _private(slug, what):
    return SkoolNotFound(f"community {slug} is private: its {what} are visible to members only",
                         reason="private", community=slug)


def _check_public(props, slug, what):
    """A redirect to /<slug>/about means the content is members-only."""
    target = redirect_target(props)
    if target:
        # "/<slug>/about?rdref=..." for a private community
        if target.split("?", 1)[0].rstrip("/").endswith("/about"):
            raise _private(slug, what)
        raise SkoolNotFound(f"community {slug} {what} not found")
    return props


def _community_summary(record):
    return {k: record[k] for k in ("id", "slug", "name", "link")}


def _page_community(props, slug):
    """The identity block of the community a page belongs to (every
    community page carries currentGroup)."""
    group = props.get("currentGroup") if isinstance(props.get("currentGroup"), dict) else {}
    return {"id": parsers._text(group.get("id")), "slug": slug,
            "name": parsers._text(parsers._get(parsers._meta(group), "display_name")),
            "link": refs.community_link(slug)}


# ---- categories/list ----------------------------------------------------------

def _directory_vocab():
    props = fetch_discovery()
    return {"categories": parsers.parse_categories(props), "languages": parsers.parse_languages(props)}


def _vocab():
    return cached_call("skool.categories", {}, _directory_vocab, ttl.CATEGORIES_CACHE)


def categories_list(**data):
    vocab = _vocab()
    return {"categories": vocab["categories"], "languages": vocab["languages"]}


def _category_id(value):
    """A category slug / name / id -> the id Skool's `c=` filter takes."""
    if not value:
        return None
    token = value.strip().lower()
    for cat in _vocab()["categories"]:
        if token in {(cat.get("id") or "").lower(), (cat.get("slug") or "").lower(), (cat.get("name") or "").lower()}:
            return cat["id"]
    raise ValueError(f"unknown category '{value}' (see /skool/categories/list for the slugs).")


# ---- communities/search ---------------------------------------------------------

def _communities_search(query=None, category=None, price=None, type=None, language=None, sort=None, page=1):
    category_id = _category_id(category)
    props = fetch_discovery(query=query, category=category_id, price=price, group_type=type, language=language,
                            sort=sort, page=page)
    if redirect_target(props):   # the no-match redirect already followed once; nothing more to show
        return {"query": query, "filters": {"category_id": category_id, "price": price, "type": type,
                                            "language": language, "sort": sort},
                "results": [], "pagination": {"page": page, "items_per_page": DISCOVERY_PAGE_SIZE,
                                              "total_pages": 0, "total_count": 0}}
    result = parsers.parse_discovery(props, page=page, per_page=DISCOVERY_PAGE_SIZE)
    if category:
        result["filters"]["category"] = category
    return result


def communities_search(**data):
    return cached_call("skool.search", data, _communities_search, ttl.SEARCH_CACHE)


# ---- the shared community record --------------------------------------------------

def _community_record(community):
    about = fetch_community_about(community)
    target = redirect_target(about)
    if target:
        raise SkoolNotFound(f"community {community} not found")
    plans = None
    if about.get("groupMembershipProducts"):
        # tiered pricing: the about page lists the tiers, the plans page
        # carries each tier's billing products (monthly / annual / one-time)
        try:
            plans = fetch_community_plans(community)
            if redirect_target(plans):
                plans = None
        except SkoolNotFound:
            plans = None
    return parsers.parse_community(about, plans)


def _record(community):
    return cached_call("skool.community", {"community": community}, _community_record, ttl.COMMUNITY_CACHE)


def community_details(community):
    return _record(community)


# ---- communities/posts ------------------------------------------------------------

def _channel_id(community, channel):
    if not channel:
        return None
    if refs.HEX32_RE.match(channel):
        return channel.lower()
    token = channel.strip().lower()
    for item in _record(community).get("channels") or []:
        if (item.get("name") or "").lower() == token:
            return item["id"]
    raise ValueError(f"unknown channel '{channel}' for {community} (see channels in /skool/communities/details).")


def _community_posts(community, channel=None, page=1):
    channel_id = _channel_id(community, channel)
    props = _check_public(fetch_community_feed(community, label=channel_id, page=page), community, "posts")
    return parsers.parse_feed(props, community, page=page)


def community_posts(**data):
    return cached_call("skool.posts", data, _community_posts, ttl.POSTS_CACHE)


# ---- communities/members ----------------------------------------------------------

def _community_members(community, tab="member", sort=None, level=None, page=1):
    props = _check_public(fetch_community_members(community, tab=tab, sort_type=sort,
                                                  levels=str(level) if level else None, page=page),
                          community, "members")
    result = parsers.parse_members(props, page=page)
    result["community"] = _page_community(props, community)
    return result


def community_members(**data):
    return cached_call("skool.members", data, _community_members, ttl.MEMBERS_CACHE)


# ---- communities/leaderboard ------------------------------------------------------

def _community_leaderboard(community):
    props = _check_public(fetch_community_leaderboards(community), community, "leaderboards")
    result = parsers.parse_leaderboards(props)
    result["community"] = _page_community(props, community)
    return result


def community_leaderboard(**data):
    return cached_call("skool.leaderboard", data, _community_leaderboard, ttl.LEADERBOARD_CACHE)


# ---- communities/courses ----------------------------------------------------------

def _classroom(community):
    props = _check_public(fetch_community_classroom(community), community, "courses")
    return parsers.parse_classroom(props, community)


def _course_tree(community, course):
    courses = _classroom(community)
    token = course.lower()
    match = next((c for c in courses if token in ((c.get("name") or "").lower(), (c.get("id") or "").lower())), None)
    if match is None:
        raise SkoolNotFound(f"course {course} not found in community {community}")
    name = match["name"]
    props = fetch_community_course(community, name)
    target = redirect_target(props)
    if target:
        # a bare course URL redirects to its first lesson (?md=<module id>)
        md = _MD_RE.search(target)
        if md:
            props = fetch_community_course(community, name, module_id=md.group(1))
        else:
            _check_public(props, community, "courses")
    tree = parsers.parse_course(props, community)
    if tree is None:
        raise SkoolNotFound(f"course {course} not found in community {community}")
    tree["lessons_count"] = tree.get("lessons_count") if tree.get("lessons_count") is not None else len(tree.get("children") or [])
    return tree


def _community_courses(community, course=None):
    summary = {"slug": community, "link": refs.community_link(community)}
    if course:
        return {"community": summary, "course": _course_tree(community, course)}
    courses = _classroom(community)
    return {"community": summary, "count": len(courses), "courses": courses}


def community_courses(**data):
    return cached_call("skool.courses", data, _community_courses, ttl.COURSES_CACHE)


# ---- communities/events -----------------------------------------------------------

def _month_stamp(month):
    """YYYY-MM -> unix seconds at noon UTC on the 15th: Skool's calendar
    renders the month grid around that date whatever the exit's zone."""
    year, mon = (int(x) for x in month.split("-"))
    return int(datetime(year, mon, 15, 12, tzinfo=timezone.utc).timestamp())


def _community_events(community, month=None):
    month = month or date.today().strftime("%Y-%m")
    props = _check_public(fetch_community_calendar(community, cal_date=_month_stamp(month)), community, "events")
    result = parsers.parse_calendar(props)
    events = [e for e in result["events"] if (e.get("start_at") or "").startswith(month)]
    return {
        "community": _page_community(props, community),
        "month": month,
        "timezone": result["timezone"],
        "has_events": result["has_events"],
        "count": len(events),
        "events": events,
    }


def community_events(**data):
    return cached_call("skool.events", data, _community_events, ttl.EVENTS_CACHE)


# ---- communities/reviews ----------------------------------------------------------

def _community_reviews(community, page=1, limit=10):
    record = _record(community)
    payload = fetch_reviews(record["id"], limit=limit, offset=(page - 1) * limit)
    parsed = parsers.parse_reviews(payload)
    rating = record.get("rating") or {}
    total = rating.get("count")
    return {
        "community": _community_summary(record),
        "rating": record.get("rating"),
        "reviews": parsed["reviews"],
        "pagination": {"page": page, "items_per_page": limit, "has_next": parsed["has_more"],
                       "total_pages": ((total + limit - 1) // limit) if total else None,
                       "total_count": total},
    }


def community_reviews(**data):
    return cached_call("skool.reviews", data, _community_reviews, ttl.REVIEWS_CACHE)


# ---- communities/search_posts -------------------------------------------------------

def _community_search(community, query, type="posts", page=1):
    props = _check_public(fetch_community_search(community, query, tab=type, page=page), community, "contents")
    result = parsers.parse_search(props, community, type, page=page)
    result["community"] = _page_community(props, community)
    return result


def community_search(**data):
    return cached_call("skool.content_search", data, _community_search, ttl.CONTENT_SEARCH_CACHE)


# ---- posts/details ----------------------------------------------------------------

def _post_record(post):
    community, slug = refs.split_post(post)
    props = _check_public(fetch_post(community, slug), community, "posts")
    record = parsers.parse_post_page(props, community)
    if record is None:
        raise SkoolNotFound(f"post {post} not found")
    record["community"] = _page_community(props, community)
    return record


def _post(post):
    return cached_call("skool.post", {"post": post}, _post_record, ttl.POST_CACHE)


def post_details(post):
    return _post(post)


# ---- posts/comments ---------------------------------------------------------------

def _post_comments(post, cursor=None):
    record = _post(post)
    payload = fetch_comments(record["id"], record["community"]["id"], created_after=cursor,
                             limit=COMMENTS_PAGE_SIZE, pinned=cursor is None)
    parsed = parsers.parse_comments(payload)
    return {
        "post": {"id": record["id"], "slug": record["slug"], "title": record["title"], "link": record["link"],
                 "comments_count": record["comments_count"]},
        "count": len(parsed["comments"]),
        "pinned_comment": parsed["pinned_comment"],
        "comments": parsed["comments"],
        "next_cursor": parsed["next_cursor"],
    }


def post_comments(**data):
    return cached_call("skool.comments", data, _post_comments, ttl.COMMENTS_CACHE)


# ---- users/details ----------------------------------------------------------------

def _user_details(user):
    props = fetch_user(user)
    record = parsers.parse_profile(props)
    if record is None:
        raise SkoolNotFound(f"user @{user} not found")
    return record


def user_details(**data):
    return cached_call("skool.user", data, _user_details, ttl.USER_CACHE)


# ---- users/followers --------------------------------------------------------------

def _user_followers(user, type="followers", page=1):
    props = fetch_user(user, tab=type, page=page)
    result = parsers.parse_follow_list(props, type, page=page)
    result["user"] = parsers._user_lite((props.get("renderData") or {}).get("user") or props.get("currentUser"))
    return result


def user_followers(**data):
    return cached_call("skool.followers", data, _user_followers, ttl.FOLLOWERS_CACHE)
