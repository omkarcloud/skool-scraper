"""Skool page data / API JSON -> clean dicts for every /skool/* endpoint.
Pure functions, no I/O.

Two upstream dialects carry the same records: the Next.js pageProps are
camelCase (pictureBubble, totalMembers) and api2.skool.com is snake_case
(picture_bubble, total_members). `_get(record, "total_members")` reads
either, so one user / post / group parser serves both.

Many metadata values are JSON serialized inside a string (levels, links,
owner, spData, displayPrice, videoLinksData, lpAttachmentsData, survey,
event location); `_json()` decodes them. Nanosecond integers (lastOffline,
lastComment, contentEdit) become ISO-8601 UTC. Empty strings are null.

Value conventions (shared with the other scraper packages):
  * keys    snake_case; `link` not `url`; booleans as questions
  * prices  numeric `amount` in major units + `currency`
  * dates   ISO-8601 as Skool prints them (UTC "Z" or the event's offset)

Fixtures captured 2026-11-03 (skool/fixtures/, the `_next/data` JSON with
the UI `translation` / growthBook / env blobs stripped): the AI Automation
Society (public, 478k members), its paid private sibling (price, plans,
reviews), AI Money Hub (reviewed public), the discovery directory, a post
page, api2 comment pages, a profile with followers / following, members,
leaderboards, classroom + course, calendar and in-community search.
"""
import json
import re
from datetime import datetime, timezone

from skool.refs import SITE, community_link, course_link, post_link, user_link

_CAMEL_RE = re.compile(r"_([a-z0-9])")
_NS_THRESHOLD = 10 ** 15      # ns since epoch (1.7e18); seconds would be 1.7e9


# ---- primitives ------------------------------------------------------------------

def _camel(name):
    return _CAMEL_RE.sub(lambda m: m.group(1).upper(), name)


def _get(record, name, default=None):
    """record[name] in snake_case OR camelCase; empty strings -> default."""
    if not isinstance(record, dict):
        return default
    for key in (name, _camel(name)):
        if key in record:
            value = record[key]
            if value is None or value == "":
                return default
            return value
    return default


def _meta(record):
    meta = _get(record, "metadata")
    return meta if isinstance(meta, dict) else {}


def _json(value, default=None):
    """A JSON document serialized inside a string -> the object."""
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return default
    try:
        return json.loads(value)
    except ValueError:
        return default


def _int(value):
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.replace(",", "")))
        except ValueError:
            return None
    return None


def _float(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _flag(value):
    """Skool's 0/1 flags -> bool; absent -> None."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return bool(_int(value))


def _text(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _iso_from_ns(value):
    """1793696805226726100 (ns) / 1793696805 (s) -> ISO-8601 UTC."""
    number = _int(value)
    if not number:
        return None
    seconds = number / 1e9 if number > _NS_THRESHOLD else float(number)
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None


def _iso(value):
    """Skool's RFC-3339 stamps kept as given (empty / zero dates -> null)."""
    value = _text(value)
    if not value or value.startswith("0001-01-01"):
        return None
    return value


def _price(value):
    """displayPrice / a billing product -> {amount, currency, interval} or
    None (free)."""
    data = _json(value) if isinstance(value, str) else value
    if not isinstance(data, dict):
        return None
    amount = _int(_get(data, "amount"))
    if amount is None:
        return None
    return {
        "amount": amount / 100.0,
        "currency": (_text(_get(data, "currency")) or "usd").upper(),
        "interval": _text(_get(data, "recurring_interval")) or "one_time",
    }


# ---- users -------------------------------------------------------------------------

def _socials(meta):
    socials = {
        "facebook": _text(_get(meta, "link_facebook")),
        "instagram": _text(_get(meta, "link_instagram")),
        "linkedin": _text(_get(meta, "link_linkedin")),
        "twitter": _text(_get(meta, "link_twitter")),
        "youtube": _text(_get(meta, "link_youtube")),
        "website": _text(_get(meta, "link_website")),
    }
    return socials if any(socials.values()) else None


def parse_user(record):
    """A user record (post author, member, leaderboard row, follower,
    reviewer, api2 /users/<id>) -> the public profile fields."""
    if not isinstance(record, dict):
        return None
    meta = _meta(record)
    sp = _json(_get(meta, "sp_data")) or {}
    handle = _text(_get(record, "name"))
    first = _text(_get(record, "first_name"))
    last = _text(_get(record, "last_name"))
    name = " ".join(part for part in (first, last) if part) or None
    points = _int(sp.get("pts"))
    level = _int(sp.get("lv"))
    user = {
        "id": _text(_get(record, "id")),
        "handle": handle,
        "name": name,
        "first_name": first,
        "last_name": last,
        "link": user_link(handle) if handle else None,
        "bio": _text(_get(meta, "bio")),
        "location": _text(_get(meta, "location")),
        "picture": _text(_get(meta, "picture_profile")),
        "picture_small": _text(_get(meta, "picture_bubble")),
        "socials": _socials(meta),
        "level": level,
        "points": points,
        "level_points": ({"current_level_at": _int(sp.get("pcl")), "next_level_at": _int(sp.get("pnl"))}
                         if sp else None),
        "activity_status": _text(_get(meta, "act_status")),
        "is_online": _flag(_get(meta, "online")),
        "last_online_at": _iso_from_ns(_get(meta, "last_offline")),
        "timezone": _text(_get(record, "time_zone")),
        "myers_briggs": _text(_get(meta, "myers_briggs")),
        "joined_skool_at": _iso(_get(record, "created_at")),
    }
    return user


def _user_lite(record):
    """The contributor / follower shape: id, handle, name, picture only."""
    user = parse_user(record)
    if not user:
        return None
    return {k: user[k] for k in ("id", "handle", "name", "link", "picture")}


# ---- communities -------------------------------------------------------------------

def _rating(meta):
    average = _float(_get(meta, "review_average_rating"))
    count = _int(_get(meta, "review_count"))
    if average is None and count is None:
        return None
    return {"average": average, "count": count or 0}


def parse_community_card(record):
    """A discovery card / profile membership card -> the compact community."""
    group = record.get("group") if isinstance(record, dict) and isinstance(record.get("group"), dict) else record
    if not isinstance(group, dict):
        return None
    meta = _meta(group)
    slug = _text(_get(group, "name"))
    price = _price(_get(meta, "display_price"))
    privacy = _flag(_get(meta, "privacy"))
    return {
        "id": _text(_get(group, "id")),
        "slug": slug,
        "name": _text(_get(meta, "display_name")),
        "link": community_link(slug) if slug else None,
        "description": _text(_get(meta, "description")),
        "price": price,
        "is_free": price is None,
        "is_private": privacy,
        "members_count": _int(_get(meta, "total_members")),
        "rating": _rating(meta),
        "logo": _text(_get(meta, "logo_url")),
        "cover": _text(_get(meta, "cover_small_url")),
        "color": _text(_get(meta, "color")),
        "initials": _text(_get(meta, "initials")),
        "created_at": _iso(_get(group, "created_at")),
        "updated_at": _iso(_get(group, "updated_at")),
    }


def parse_discovery(props, page=1, per_page=30):
    """The discovery directory page -> cards + pagination (Skool caps a
    query at 1000 results = 34 pages; `numGroups` is that capped total)."""
    cards = [parse_community_card(g) for g in (props.get("groups") or []) if isinstance(g, dict)]
    cards = [c for c in cards if c]
    total = _int(props.get("numGroups"))
    total_pages = (total + per_page - 1) // per_page if total else 0
    return {
        "query": _text(props.get("searchQueryParam")),
        "filters": {
            "category_id": _text(props.get("categoryParam")),
            "price": _text(props.get("priceParam")),
            "type": _text(props.get("typeParam")),
            "language": _text(props.get("languageParam")),
            "sort": _text(props.get("sortParam")),
        },
        "results": cards,
        "pagination": {
            "page": _int(props.get("page")) or page,
            "items_per_page": per_page,
            "total_pages": total_pages,
            "total_count": total or 0,
        },
    }


def parse_categories(props):
    """The discovery page's category list (only sent with no query)."""
    out = []
    for cat in props.get("categories") or []:
        if not isinstance(cat, dict):
            continue
        out.append({"id": _text(cat.get("id")), "slug": _text(cat.get("slug")), "name": _text(cat.get("name"))})
    return out


def parse_languages(props):
    out = []
    for lang in props.get("languages") or []:
        if isinstance(lang, dict):
            out.append({"code": _text(lang.get("code")), "name": _text(lang.get("name")),
                        "display_name": _text(lang.get("displayName"))})
    return out


def _levels(meta):
    data = _json(_get(meta, "levels")) or {}
    out = []
    for level in data.get("levels") or []:
        if isinstance(level, dict):
            out.append({"number": _int(level.get("number")), "name": _text(level.get("name")),
                        "title": _text(level.get("title")),
                        "percent_of_members": _int(level.get("percent_of_members"))})
    return out


def _links(meta):
    data = _json(_get(meta, "links")) or {}
    out = []
    for link in data.get("links") or []:
        if isinstance(link, dict) and link.get("url"):
            out.append({"label": _text(link.get("label")), "link": _text(link.get("url")),
                        "is_public": _flag(link.get("public"))})
    return out


def _landing_attachments(meta):
    data = _json(_get(meta, "lp_attachments_data")) or {}
    out = []
    for item in data.get("attachments_data") or []:
        if not isinstance(item, dict):
            continue
        image = item.get("image") or {}
        video = item.get("video") or {}
        kind = _int(item.get("landing_page_attachment_type"))
        if video.get("video_url"):
            out.append({"type": "video", "link": _text(video.get("video_url")),
                        "thumbnail": _text(video.get("original_thumbnail_url")),
                        "length_ms": _int(video.get("video_length_ms"))})
        elif image.get("original_url"):
            out.append({"type": "image", "link": _text(image.get("original_url")),
                        "small_link": _text(image.get("small_url"))})
        elif kind is not None:
            out.append({"type": "other", "link": None})
    return out


def _video(value):
    data = _json(value) if isinstance(value, str) else value
    if not isinstance(data, dict) or not data.get("video_url"):
        return None
    return {"link": _text(data.get("video_url")), "thumbnail": _text(data.get("video_thumbnail")),
            "length_ms": _int(data.get("video_length_ms"))}


def _survey(meta):
    data = _json(_get(meta, "survey")) or {}
    out = []
    for q in data.get("survey") or []:
        if isinstance(q, dict) and q.get("question"):
            out.append({"question": _text(q.get("question")), "type": _text(q.get("type")),
                        "options": [o for o in (q.get("options") or []) if isinstance(o, str)] or None})
    return out


def _tabs(meta):
    data = _json(_get(meta, "tabs"))
    if not isinstance(data, dict) or not data:
        return None
    return {name.replace("-", "_"): bool((cfg or {}).get("visible")) for name, cfg in data.items()
            if isinstance(cfg, dict)} or None


def parse_labels(labels):
    """currentGroup.labels (the feed's channels / categories)."""
    out = []
    for label in labels or []:
        if not isinstance(label, dict):
            continue
        meta = _meta(label)
        out.append({"id": _text(label.get("id")), "name": _text(_get(meta, "display_name")),
                    "description": _text(_get(meta, "description")), "color": _text(_get(meta, "color")),
                    "posts_count": _int(_get(meta, "posts"))})
    return out


def parse_plans(products):
    """groupMembershipProducts (about / plans page) -> membership tiers."""
    out = []
    for product in products or []:
        if not isinstance(product, dict):
            continue
        meta = _meta(product)
        benefits = _json(_get(meta, "benefits")) or []
        prices = {}
        for key, name in (("monthly_billing_product", "monthly"), ("annual_billing_product", "annual"),
                          ("one_time_billing_product", "one_time")):
            price = _price(_get(product, key))
            if price:
                prices[name] = price
        out.append({
            "id": _text(product.get("id")),
            "tier": _text(_get(product, "tier")),
            "model": _text(_get(product, "model")),
            "benefits": [b for b in benefits if isinstance(b, str)] or None,
            "prices": prices or None,
            "is_active": _get(product, "deactivated_at") is None,
            "activated_at": _iso(_get(product, "activated_at")),
            "deactivated_at": _iso(_get(product, "deactivated_at")),
        })
    return out


def parse_community(about_props, plans_props=None):
    """The about page (+ optional plans page) -> the full community record."""
    group = about_props.get("currentGroup") or {}
    meta = _meta(group)
    slug = _text(_get(group, "name"))
    owner = _json(_get(meta, "owner"))
    price = _price(_get(meta, "display_price"))
    privacy = _flag(_get(meta, "privacy"))
    products = (plans_props or {}).get("groupMembershipProducts") or about_props.get("groupMembershipProducts")
    reviews = about_props.get("reviewsData") if isinstance(about_props.get("reviewsData"), dict) else {}
    return {
        "id": _text(_get(group, "id")),
        "slug": slug,
        "name": _text(_get(meta, "display_name")),
        "link": community_link(slug) if slug else None,
        "description": _text(_get(meta, "description")),
        "landing_page_description": _text(_get(meta, "lp_description")),
        "landing_page_attachments": _landing_attachments(meta) or None,
        "is_private": privacy,
        "is_free": price is None,
        "price": price,
        "plans": parse_plans(products) or None,
        "affiliate_commission_percent": _int(_get(meta, "afl_percent")),
        "rating": _rating(meta),
        "members_count": _int(_get(meta, "total_members")),
        "admins_count": _int(_get(meta, "total_admins")),
        "online_members_count": _int(_get(meta, "total_online_members")),
        "posts_count": _int(_get(meta, "total_posts")),
        "courses_count": _int(_get(meta, "num_courses")),
        "lessons_count": _int(_get(meta, "num_modules")),
        "rules_count": _int(_get(meta, "total_rules")),
        "min_level_to_post": _int(_get(meta, "min_post_level")),
        "levels": _levels(meta) or None,
        "channels": parse_labels(group.get("labels")) or None,
        "links": _links(meta) or None,
        "join_questions": _survey(meta) if _flag(_get(meta, "survey_enabled")) else None,
        "tabs": _tabs(meta),
        "retention_video": _video(_get(meta, "retention_video")),
        "owner": parse_user(owner) if isinstance(owner, dict) else None,
        "logo": _text(_get(meta, "logo_url")),
        "logo_large": _text(_get(meta, "logo_big_url")),
        "cover": _text(_get(meta, "cover_small_url")),
        "favicon": _text(_get(meta, "favicon_url")),
        "color": _text(_get(meta, "color")),
        "initials": _text(_get(meta, "initials")),
        "has_more_reviews": bool(reviews.get("hasMore")) if reviews else None,
        "created_at": _iso(_get(group, "created_at")),
        "updated_at": _iso(_get(group, "updated_at")),
    }


# ---- posts ---------------------------------------------------------------------------

def _videos(meta):
    data = _json(_get(meta, "video_links_data")) or []
    out = []
    for video in data if isinstance(data, list) else []:
        if isinstance(video, dict) and video.get("url"):
            out.append({"link": _text(video.get("url")), "video_id": _text(video.get("video_id")),
                        "title": _text(video.get("title")), "thumbnail": _text(video.get("thumbnail")),
                        "length_ms": _int(video.get("len_ms"))})
    return out


def _attachments(meta):
    data = _json(_get(meta, "attachments_data")) or []
    out = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        link = _text(item.get("url") or item.get("original_url") or (item.get("image") or {}).get("original_url"))
        if link:
            out.append({"link": link, "name": _text(item.get("name") or item.get("file_name")),
                        "type": _text(item.get("type") or item.get("mime_type"))})
    return out


def _contributors(meta):
    data = _json(_get(meta, "contributors")) or []
    return [u for u in (_user_lite(c) for c in data if isinstance(c, dict)) if u]


def parse_post(record, labels=None, slug=None):
    """A post record (feed row, post page, search hit) -> the post."""
    if not isinstance(record, dict):
        return None
    meta = _meta(record)
    post_slug = _text(_get(record, "name"))
    group_slug = slug
    label_id = _text(_get(record, "label_id")) or _text(_get(meta, "labels"))
    label = None
    if label_id and labels:
        label = next((l for l in labels if l.get("id") == label_id), None)
    return {
        "id": _text(_get(record, "id")),
        "slug": post_slug,
        "title": _text(_get(meta, "title")),
        "link": post_link(group_slug, post_slug) if group_slug and post_slug else None,
        "content": _text(_get(meta, "content")),
        "content_highlight": _text(_get(meta, "content_hl")),
        "author": parse_user(_get(record, "user")),
        "channel": label or ({"id": label_id} if label_id else None),
        "is_pinned": bool(_int(_get(meta, "pinned"))),
        "upvotes": _int(_get(meta, "upvotes")) or 0,
        "comments_count": _int(_get(meta, "comments")) or 0,
        "last_comment_at": _iso_from_ns(_get(meta, "last_comment")),
        "videos": _videos(meta) or None,
        "attachments": _attachments(meta) or None,
        "image_preview": _text(_get(meta, "image_preview")),
        "contributors": _contributors(meta) or None,
        "community_id": _text(_get(record, "group_id")),
        "created_at": _iso(_get(record, "created_at")),
        "updated_at": _iso(_get(record, "updated_at")),
        "edited_at": _iso_from_ns(_get(meta, "content_edit")),
    }


def parse_feed(props, slug, page=1, per_page=30):
    """A community feed page -> posts + pagination + the channel list."""
    group = props.get("currentGroup") or {}
    labels = parse_labels(group.get("labels"))
    posts = [parse_post(t.get("post"), labels, slug) for t in (props.get("postTrees") or []) if isinstance(t, dict)]
    posts = [p for p in posts if p]
    total = _int(props.get("total"))
    total_pages = (total + per_page - 1) // per_page if total else 0
    return {
        "community": {"id": _text(group.get("id")), "slug": slug, "name": _text(_get(_meta(group), "display_name")),
                      "link": community_link(slug)},
        "channel_id": _text(props.get("channelId")),
        "channels": labels or None,
        "posts": posts,
        "pagination": {"page": _int(props.get("page")) or page, "items_per_page": per_page,
                       "total_pages": total_pages, "total_count": total or 0},
    }


def parse_post_page(props, slug):
    """The post page -> the post (comments load from api2 separately)."""
    tree = props.get("postTree") or {}
    post = parse_post(tree.get("post"), parse_labels((props.get("currentGroup") or {}).get("labels")), slug)
    if post is None:
        return None
    post["is_pinned"] = bool(props.get("isPinned")) or post["is_pinned"]
    post["followers_count"] = _int(props.get("followers"))
    poll = props.get("poll")
    post["poll"] = poll if isinstance(poll, dict) else None
    return post


# ---- comments ------------------------------------------------------------------------

def _comment(node):
    post = node.get("post") if isinstance(node, dict) else None
    if not isinstance(post, dict):
        return None
    meta = _meta(post)
    replies = [c for c in (_comment(child) for child in (node.get("children") or [])) if c]
    return {
        "id": _text(_get(post, "id")),
        "content": _text(_get(meta, "content")),
        "author": parse_user(_get(post, "user")),
        "upvotes": _int(_get(meta, "upvotes")) or 0,
        "attachments": _attachments(meta) or None,
        "parent_id": _text(_get(post, "parent_id")),
        "created_at": _iso(_get(post, "created_at")),
        "updated_at": _iso(_get(post, "updated_at")),
        "last_reply_at": _iso_from_ns(_get(meta, "last_comment")),
        "replies_count": len(replies),
        "replies": replies,
    }


def parse_comments(payload):
    """api2 /posts/<id>/comments -> {comments, pinned, next_cursor}."""
    tree = payload.get("post_tree") if isinstance(payload, dict) else None
    comments = [c for c in (_comment(n) for n in ((tree or {}).get("children") or [])) if c]
    pinned_tree = payload.get("pinned_post_tree") if isinstance(payload, dict) else None
    pinned = _comment(pinned_tree) if isinstance(pinned_tree, dict) and pinned_tree.get("post") else None
    last = _int(payload.get("last")) if isinstance(payload, dict) else None
    return {"comments": comments, "pinned_comment": pinned,
            "next_cursor": str(last) if last else None}


# ---- members / leaderboards ----------------------------------------------------------

def parse_member(record):
    """A members-page row (user + member) or a search hit (member + user)."""
    if not isinstance(record, dict):
        return None
    if isinstance(record.get("member"), dict):
        user_record, membership = record, record["member"]
    elif isinstance(record.get("user"), dict):
        user_record, membership = record["user"], record
    else:
        user_record, membership = record, {}
    user = parse_user(user_record)
    if user is None:
        return None
    user["membership"] = {
        "role": _text(_get(membership, "role")),
        "joined_at": _iso(_get(membership, "approved_at")),
        "requested_at": _iso_from_ns(_get(_meta(membership), "requested_at")),
        "last_online_at": _iso(_get(membership, "last_offline")) or user.get("last_online_at"),
    } if membership else None
    return user


def parse_members(props, page=1):
    per_page = _int(props.get("itemsPerPage")) or 30
    members = [m for m in (parse_member(u) for u in (props.get("users") or [])) if m]
    total = _int(props.get("total")) or 0
    return {
        "tab": _text(props.get("tabName")) or "member",
        "sort": _text(props.get("sortType")) or "-memberapprovedat",
        "levels": _text(props.get("levels")),
        "counts": {"members": _int(props.get("totalMembers")), "admins": _int(props.get("totalAdmins")),
                   "online": _int(props.get("totalOnlineMembers"))},
        "members": members,
        "pagination": {"page": _int(props.get("page")) or page, "items_per_page": per_page,
                       "total_pages": _int(props.get("totalPages")) or ((total + per_page - 1) // per_page),
                       "total_count": total},
    }


def _board(board):
    if not isinstance(board, dict):
        return None
    rows = []
    for row in board.get("users") or []:
        if isinstance(row, dict):
            rows.append({"rank": _int(row.get("rank")), "points": _int(row.get("points")),
                         "user": parse_user(row.get("user"))})
    return {"updated_at": _iso(board.get("updatedAt")), "ranking": rows}


def parse_leaderboards(props):
    levels = []
    for level in props.get("groupLevels") or []:
        if isinstance(level, dict):
            levels.append({"number": _int(level.get("number")), "name": _text(level.get("name")),
                           "title": _text(level.get("title")),
                           "percent_of_members": _int(_get(level, "percent_of_members"))})
    return {
        "all_time": _board(props.get("allTime")),
        "past_30_days": _board(props.get("past30Days")),
        "past_7_days": _board(props.get("past7Days")),
        "levels": levels or None,
    }


# ---- classroom -----------------------------------------------------------------------

def _rich_text(value):
    """A lesson description: plain text, or Skool's "[v2][...]" block JSON
    -> the concatenated text."""
    text = _text(value)
    if not text:
        return None
    if text.startswith("[v2]"):
        blocks = _json(text[4:]) or []
        parts = []

        def walk(node):
            if isinstance(node, dict):
                if isinstance(node.get("text"), str):
                    parts.append(node["text"])
                for key in ("children", "content"):
                    walk(node.get(key))
            elif isinstance(node, list):
                for item in node:
                    walk(item)
        walk(blocks)
        joined = "\n".join(p for p in parts if p and p.strip())
        return joined or None
    return text


def _resources(meta):
    data = _json(_get(meta, "resources")) or []
    out = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict):
            link = _text(item.get("url") or item.get("link") or item.get("original_url"))
            out.append({"title": _text(item.get("title") or item.get("name")), "link": link,
                        "type": _text(item.get("type"))})
    return out


def parse_course_unit(node, slug, course_name=None):
    """A classroom unit (course / set / module) with its children."""
    unit = node.get("course") if isinstance(node, dict) and isinstance(node.get("course"), dict) else node
    if not isinstance(unit, dict):
        return None
    meta = _meta(unit)
    unit_type = _text(_get(unit, "unit_type"))
    name = _text(_get(unit, "name"))
    unit_id = _text(_get(unit, "id"))
    if unit_type == "course":
        course_name = name
        link = course_link(slug, name) if slug and name else None
    else:
        link = course_link(slug, course_name, unit_id) if slug and course_name and unit_id else None
    video_link = _text(_get(meta, "video_link"))
    children = [c for c in (parse_course_unit(child, slug, course_name)
                            for child in (node.get("children") or [] if isinstance(node, dict) else []))
                if c]
    out = {
        "id": unit_id,
        "name": name,
        "type": unit_type,
        "title": _text(_get(meta, "title")),
        "link": link,
        "description": _rich_text(_get(meta, "desc")),
        "cover": _text(_get(meta, "cover_image")),
        "has_access": _flag(_get(meta, "has_access")),
        "is_private": _flag(_get(meta, "privacy")),
        "lessons_count": _int(_get(meta, "num_modules")),
        "video": ({"link": video_link, "thumbnail": _text(_get(meta, "video_thumbnail")),
                   "length_ms": _int(_get(meta, "video_len_ms"))} if video_link else None),
        "resources": _resources(meta) or None,
        "is_published": _int(_get(unit, "state")) == 2 if _get(unit, "state") is not None else None,
        "created_at": _iso(_get(unit, "created_at")),
        "updated_at": _iso(_get(unit, "updated_at")),
    }
    if unit_type == "course" or children:
        out["children"] = children
    return out


def parse_classroom(props, slug):
    courses = [c for c in (parse_course_unit(c, slug) for c in (props.get("allCourses") or [])) if c]
    for course in courses:
        course.pop("children", None)
    return courses


def parse_course(props, slug):
    tree = props.get("course")
    course = parse_course_unit(tree, slug) if isinstance(tree, dict) else None
    if course is None:
        return None
    course["selected_lesson_id"] = _text(props.get("selectedModule"))
    return course


# ---- calendar ------------------------------------------------------------------------

def parse_event(record):
    if not isinstance(record, dict):
        return None
    meta = _meta(record)
    location = _json(_get(meta, "location")) or {}
    return {
        "id": _text(_get(record, "id")),
        "occurrence_id": _text(_get(record, "occurrence_id")),
        "title": _text(_get(meta, "title")),
        "description": _text(_get(meta, "description")),
        "start_at": _iso(_get(record, "start_time")),
        "end_at": _iso(_get(record, "end_time")),
        "timezone": _text(_get(meta, "timezone")),
        "location": _text(location.get("location_info")) if isinstance(location, dict) else None,
        "location_type_code": _int(location.get("location_type")) if isinstance(location, dict) else None,
        "cover": _text(_get(meta, "cover_image")),
        "has_access": _flag(_get(meta, "has_access")),
        "recurrence": record.get("recurrence") if isinstance(record.get("recurrence"), dict) else None,
        "community_id": _text(_get(record, "group_id")),
        "created_at": _iso(_get(record, "created_at")),
        "updated_at": _iso(_get(record, "updated_at")),
    }


def parse_calendar(props):
    events = [e for e in (parse_event(e) for e in (props.get("events") or [])) if e]
    return {"timezone": _text(props.get("timezone")), "has_events": bool(props.get("groupHasEvents")),
            "events": events}


# ---- reviews -------------------------------------------------------------------------

def parse_review(record):
    if not isinstance(record, dict):
        return None
    return {
        "id": _text(_get(record, "id")),
        "rating": _int(_get(record, "rating")),
        "body": _text(_get(record, "body")),
        "author": parse_user(_get(record, "user")),
        "member_since": _iso(_get(record, "member_since")),
        "is_currently_paying": _flag(_get(record, "member_currently_paying")),
        "created_at": _iso(_get(record, "created_at")),
        "updated_at": _iso(_get(record, "updated_at")),
    }


def parse_reviews(payload):
    """api2 /groups/<id>/reviews or the about page's reviewsData."""
    data = payload if isinstance(payload, dict) else {}
    reviews = [r for r in (parse_review(r) for r in (data.get("reviews") or [])) if r]
    return {"reviews": reviews, "has_more": bool(_get(data, "has_more"))}


# ---- in-community search -----------------------------------------------------------------

def parse_search(props, slug, search_type, page=1, per_page=10):
    labels = parse_labels((props.get("currentGroup") or {}).get("labels"))
    totals = {"posts": _int(props.get("totalPosts")) or 0, "members": _int(props.get("totalMembers")) or 0,
              "courses": _int(props.get("totalCourses")) or 0}
    if search_type == "members":
        results = [m for m in (parse_member(m) for m in (props.get("members") or [])) if m]
    elif search_type == "courses":
        results = []
        for lesson in props.get("courses") or []:
            unit = parse_course_unit(lesson, slug, _text(_get(_meta(lesson), "course_name")))
            if unit:
                meta = _meta(lesson)
                unit["course"] = {"name": _text(_get(meta, "course_name")), "title": _text(_get(meta, "course_title")),
                                  "section": _text(_get(meta, "set_title"))}
                unit["description_highlight"] = _text(_get(meta, "desc_hl"))
                results.append(unit)
    else:
        results = [p for p in (parse_post(t.get("post"), labels, slug) for t in (props.get("postTrees") or [])
                               if isinstance(t, dict)) if p]
    total = totals[search_type]
    total_pages = _int(props.get("totalPostPages")) if search_type == "posts" else None
    if total_pages is None:
        total_pages = (total + per_page - 1) // per_page
    return {
        "query": _text(props.get("searchQuery")),
        "type": search_type,
        "counts": totals,
        "results": results,
        "pagination": {"page": _int(props.get("page")) or page, "items_per_page": per_page,
                       "total_pages": total_pages, "total_count": total},
    }


# ---- profiles ----------------------------------------------------------------------------

def parse_profile(props):
    data = props.get("renderData") if isinstance(props.get("renderData"), dict) else {}
    record = data.get("user") or props.get("currentUser")
    user = parse_user(record)
    if user is None:
        return None
    activity = data.get("dailyActivities") if isinstance(data.get("dailyActivities"), dict) else {}
    user["stats"] = {
        "posts": _int(data.get("totalPosts")),
        "contributions": _int(data.get("totalContributions")),
        "followers": _int(data.get("totalFollowers")),
        "following": _int(data.get("totalFollowing")),
        "communities": _int(data.get("totalGroups")),
    }
    user["mrr_status"] = _text(_get(_meta(record), "mrr_status"))
    user["communities_created"] = [c for c in (parse_community_card(g) for g in (data.get("groupsCreatedByUser") or []))
                                   if c] or None
    user["communities_joined"] = [c for c in (parse_community_card(g) for g in (data.get("groupsMemberOf") or []))
                                  if c] or None
    user["activity"] = ({"start_date": _iso(activity.get("startDate")), "end_date": _iso(activity.get("endDate")),
                         "daily_counts": [_int(c) or 0 for c in (activity.get("counts") or [])]}
                        if activity else None)
    return user


def parse_follow_list(props, follow_type, page=1, per_page=30):
    """The profile's followers / following tab: items are {src, dst} edges;
    followers are the `src` side, following the `dst` side."""
    side = "src" if follow_type == "followers" else "dst"
    users = [u for u in (parse_user(item.get(side)) for item in (props.get("items") or []) if isinstance(item, dict))
             if u]
    total = _int(props.get("total")) or 0
    return {
        "type": follow_type,
        "users": users,
        "pagination": {"page": _int(props.get("page")) or page, "items_per_page": per_page,
                       "total_pages": (total + per_page - 1) // per_page, "total_count": total},
    }
