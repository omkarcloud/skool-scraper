"""The 14 Skool endpoints. Every path is served with and without the
`/skool` prefix, so code generated against the hosted API on RapidAPI
(paths like /communities/details) runs unchanged against this server.

Params are validated by the marshmallow schemas in skool/schemas.py (ONE
param per input: `community` takes a community name or skool.com link;
`post` a post link or `<community>/<post-slug>`; `user` a handle or profile
link; `course` a course name, id or classroom link); unknown params are
rejected. Private communities answer posts / members / courses / events /
search with 404 and `"reason": "private"` — their details, plans and
reviews stay public."""
import json
from urllib.parse import urlencode

from bottle import request, response, route

from schema_fields import load_query
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from skool import api, schemas


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The request query as unicode strings (bottle 0.12's .get() hands back
    latin-1 decoded bytes, so getunicode is mandatory)."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _page_link(path, params, page):
    if not page:
        return None
    query = {k: v for k, v in params.items() if v not in (None, "", False)}
    query["page"] = page
    scheme, host = request.urlparts.scheme, request.urlparts.netloc
    return f"{scheme}://{host}{path}?{urlencode(query, doseq=True)}"


def paginate(result, path, params):
    """Lift the `pagination` block into the flat shape the hosted API
    returns: count / per_page / current_page / total_pages / next / previous."""
    pagination = result.pop("pagination", None) or {}
    result.pop("count", None)   # per-page count; `count` is the total
    page = _as_int(pagination.get("page")) or _as_int(params.get("page")) or 1
    if "has_next" in pagination:
        has_next = bool(pagination["has_next"])
        total_pages = pagination.get("total_pages")
        if total_pages is not None:
            total_pages = _as_int(total_pages, None)
    else:
        total_pages = max(_as_int(pagination.get("total_pages")), 0)
        has_next = page < total_pages
    out = {
        "count": pagination.get("total_count"),
        "per_page": pagination.get("items_per_page"),
        "current_page": page,
        "total_pages": total_pages,
        "next": _page_link(path, params, page + 1 if has_next else None),
        "previous": _page_link(path, params, page - 1 if page > 1 else None),
    }
    out.update(result)
    return out


def _error_body(message, exc):
    """{"error": message} plus the machine-readable `reason` (e.g. "private")
    and its details when the module sets them."""
    body = {"error": message}
    reason = getattr(exc, "reason", None)
    if reason:
        body["reason"] = reason
        for key, value in (getattr(exc, "details", None) or {}).items():
            body.setdefault(key, value)
    return body


def call(label, schema_cls, impl, paginated=False):
    """Validate, run, map errors: bad params -> 400, missing entity -> 404,
    blocks / transport -> 502, anything else -> 500."""
    raw = query_dict()
    data, error = load_query(schema_cls, raw)
    if error:
        return json_response(error, 400)
    try:
        result = impl(**data)
    except ValueError as e:
        return json_response({"error": str(e)}, 400)
    except BadRequest as e:
        return json_response(_error_body(f"skool rejected the request: {e}", e), 400)
    except NotFound as e:
        return json_response(_error_body(str(e) or "not found", e), 404)
    except Blocked as e:
        return json_response({"error": f"skool blocked the request, retry later: {e}"}, 502)
    except UpstreamError as e:
        return json_response({"error": f"skool {label} failed: {e}"}, 502)
    except Exception as e:                 # parser surprises
        return json_response({"error": f"skool {label} failed: {type(e).__name__}: {e}"}, 500)
    if paginated:
        result = paginate(result, request.path, raw)
    return json_response(result)


ENDPOINTS = [
    ("/communities/details", schemas.CommunitySchema, api.community_details, False),
    ("/categories/list", schemas.CategoriesSchema, api.categories_list, False),
    ("/communities/search", schemas.CommunitiesSearchSchema, api.communities_search, True),
    ("/communities/posts", schemas.CommunityPostsSchema, api.community_posts, True),
    ("/posts/details", schemas.PostSchema, api.post_details, False),
    ("/posts/comments", schemas.PostCommentsSchema, api.post_comments, False),
    ("/communities/members", schemas.CommunityMembersSchema, api.community_members, True),
    ("/communities/leaderboard", schemas.CommunitySchema, api.community_leaderboard, False),
    ("/communities/courses", schemas.CommunityCoursesSchema, api.community_courses, False),
    ("/communities/events", schemas.CommunityEventsSchema, api.community_events, False),
    ("/communities/reviews", schemas.CommunityReviewsSchema, api.community_reviews, True),
    ("/communities/search_posts", schemas.CommunitySearchSchema, api.community_search, True),
    ("/users/details", schemas.UserSchema, api.user_details, False),
    ("/users/followers", schemas.UserFollowersSchema, api.user_followers, True),
]


def mount(path, schema_cls, impl, paginated):
    """Serve a handler at /path and /skool/path."""
    label = path.strip("/")

    def handler():
        return call(label, schema_cls, impl, paginated)

    handler.__name__ = "skool_" + label.replace("/", "_").replace("-", "_")
    route(path, method="GET")(handler)
    route("/skool" + path, method="GET")(handler)


for _path, _schema, _impl, _paginated in ENDPOINTS:
    mount(_path, _schema, _impl, _paginated)


@route("/", method="GET")
@route("/health", method="GET")
def health():
    return json_response({"status": "ok", "endpoints": [p for p, *_ in ENDPOINTS]})
