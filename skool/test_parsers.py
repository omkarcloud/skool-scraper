"""Offline tests for the Skool parsers, reference resolvers and value
helpers.

    python -m pytest skool/test_parsers.py -q

Fixtures are real www.skool.com `_next/data` payloads and api2.skool.com
responses captured 2026-11-03 (skool/fixtures/): the AI Automation Society
(public, 478k members) across every tab, its private paid sibling (price,
tiers, reviews), AI Money Hub (reviewed, tiers without billing products),
the discovery directory (search + home + no-match redirect), a post page,
comment pages, a profile with its follower lists, and the three error
bodies (notFound JSON, stale-buildId 404 page, AWS WAF challenge). No
network.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skool import parsers as P, refs  # noqa: E402
from skool.fetch import parse_build_id  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SLUG = "ai-automation-society"


def fixture(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f) if name.endswith(".json") else f.read()


def props(name):
    return fixture(name)["pageProps"]


# ---- refs ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("ai-automation-society", "ai-automation-society"),
    ("AI-Automation-Society", "ai-automation-society"),
    ("https://www.skool.com/ai-automation-society", "ai-automation-society"),
    ("https://www.skool.com/ai-automation-society/about?x=1", "ai-automation-society"),
    ("https://skool.com/ai-automation-society/-/members", "ai-automation-society"),
    ("/ai-automation-society/", "ai-automation-society"),
])
def test_resolve_community(value, expected):
    assert refs.resolve_community(value) == expected


@pytest.mark.parametrize("value", ["", "@nateherk", "discovery", "https://www.skool.com/@nateherk",
                                   "https://example.com/ai-automation-society", "a b", "_next"])
def test_resolve_community_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_community(value)


@pytest.mark.parametrize("value,expected", [
    ("ai-automation-society/new-video-every-claude", "ai-automation-society/new-video-every-claude"),
    ("https://www.skool.com/ai-automation-society/new-video-every-claude?p=1",
     "ai-automation-society/new-video-every-claude"),
    ("/AI-Automation-Society/New-Video/", "ai-automation-society/new-video"),
])
def test_resolve_post(value, expected):
    assert refs.resolve_post(value) == expected
    assert refs.split_post(expected) == tuple(expected.split("/"))


@pytest.mark.parametrize("value", ["", "new-video-every-claude", "ai-automation-society/about",
                                   "https://www.skool.com/ai-automation-society", "a/b/c",
                                   "https://example.com/g/p"])
def test_resolve_post_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_post(value)


@pytest.mark.parametrize("value,expected", [
    ("nateherk", "nateherk"), ("@NateHerk", "nateherk"), ("https://www.skool.com/@nateherk", "nateherk"),
    ("https://www.skool.com/@nateherk?t=followers", "nateherk"),
])
def test_resolve_user(value, expected):
    assert refs.resolve_user(value) == expected


@pytest.mark.parametrize("value", ["", "@", "https://www.skool.com/ai-automation-society",
                                   "https://example.com/@nateherk", "nate herk"])
def test_resolve_user_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_user(value)


@pytest.mark.parametrize("value,expected", [
    ("3d31807e", "3d31807e"), ("993C60AA26514DF388CC82561FE33E42", "993c60aa26514df388cc82561fe33e42"),
    ("https://www.skool.com/ai-automation-society/classroom/3d31807e?md=87dcf10a8b2e4e17be8aee82c2c2f11e",
     "3d31807e"),
])
def test_resolve_course(value, expected):
    assert refs.resolve_course(value) == expected


@pytest.mark.parametrize("value", ["", "start-here", "https://www.skool.com/ai-automation-society/about",
                                   "https://example.com/x/classroom/3d31807e"])
def test_resolve_course_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_course(value)


def test_course_link_community():
    assert refs.course_link_community("https://www.skool.com/ai-automation-society/classroom/3d31807e") == SLUG
    assert refs.course_link_community("3d31807e") is None


@pytest.mark.parametrize("value,expected", [
    ("en", "english"), ("English", "english"), ("es", "spanish"), ("all", "all"), ("yue", "cantonese"),
])
def test_resolve_language(value, expected):
    assert refs.resolve_language(value) == expected


def test_resolve_language_rejects():
    with pytest.raises(ValueError):
        refs.resolve_language("klingon")


# ---- value helpers -----------------------------------------------------------------

def test_get_reads_both_dialects():
    assert P._get({"total_members": 3}, "total_members") == 3
    assert P._get({"totalMembers": 3}, "total_members") == 3
    assert P._get({"totalMembers": ""}, "total_members", "x") == "x"
    assert P._get(None, "x") is None


def test_iso_from_ns_and_seconds():
    assert P._iso_from_ns(1793696805226726100) == "2026-11-03T09:06:45Z"
    assert P._iso_from_ns(1793696805) == "2026-11-03T09:06:45Z"
    assert P._iso_from_ns(0) is None
    assert P._iso_from_ns("junk") is None


def test_price():
    assert P._price('{"currency":"usd","amount":4900,"recurring_interval":"month"}') == \
        {"amount": 49.0, "currency": "USD", "interval": "month"}
    assert P._price("") is None
    assert P._price("{bad json") is None
    assert P._price({"amount": 1000}) == {"amount": 10.0, "currency": "USD", "interval": "one_time"}


def test_rich_text():
    assert P._rich_text("plain") == "plain"
    assert P._rich_text('[v2][{"type":"paragraph"}]') is None
    assert P._rich_text('[v2][{"type":"paragraph","children":[{"text":"Hello"},{"text":" world"}]}]') == \
        "Hello\n world"
    assert P._rich_text("") is None


# ---- discovery -------------------------------------------------------------------

def test_discovery_search_page():
    result = P.parse_discovery(props("discovery_search_ai.json"))
    assert result["pagination"] == {"page": 1, "items_per_page": 30, "total_pages": 34, "total_count": 1000}
    assert result["query"] == "ai"
    assert result["filters"]["language"] == "english" and result["filters"]["sort"] == "trending"
    assert len(result["results"]) == 30
    card = result["results"][0]
    assert card["slug"] == "ai-money-hub" and card["link"] == "https://www.skool.com/ai-money-hub"
    assert card["price"] == {"amount": 49.0, "currency": "USD", "interval": "month"}
    assert card["is_free"] is False
    assert card["members_count"] == 3097
    assert card["rating"] == {"average": 5.0, "count": 3}
    assert card["id"] == "4c29068bb10947359c46a4bd12473aaf"
    assert all((c["price"] is None) == c["is_free"] for c in result["results"])
    assert all(c["link"] == f"https://www.skool.com/{c['slug']}" for c in result["results"])


def test_discovery_home_vocabularies():
    home = props("discovery_home.json")
    categories = P.parse_categories(home)
    assert categories[0] == {"id": "4be4645a84f64e03ad53b589e6a94d5a", "slug": "ai_automation", "name": "AI Automation"}
    assert len(categories) == 31
    languages = P.parse_languages(home)
    assert len(languages) == 48 and languages[0]["code"] == "EN"
    # the search page carries no categories
    assert P.parse_categories(props("discovery_search_ai.json")) == []


def test_discovery_nomatch_is_a_redirect():
    redirect = props("discovery_nomatch_redirect.json")
    assert redirect["__N_REDIRECT"] == "/discovery?q=zzqqxxnomatch&lang=all"
    assert P.parse_discovery(redirect)["results"] == []


# ---- community record ------------------------------------------------------------

@pytest.fixture(scope="module")
def public_community():
    return P.parse_community(props("community_about_public.json"))


@pytest.fixture(scope="module")
def private_community():
    return P.parse_community(props("community_about_private.json"), props("community_plans_private.json"))


def test_public_community(public_community):
    c = public_community
    assert c["id"] == "b51c57150c70495899bf4bc8aaee8166" and c["slug"] == SLUG
    assert c["name"] == "AI Automation Society" and c["link"] == "https://www.skool.com/ai-automation-society"
    assert c["is_private"] is False and c["is_free"] is True and c["price"] is None and c["plans"] is None
    assert c["members_count"] == 478577 and c["admins_count"] == 16 and c["online_members_count"] == 1303
    assert c["posts_count"] == 26704 and c["courses_count"] == 17 and c["lessons_count"] == 296
    assert c["min_level_to_post"] == 2 and c["rules_count"] == 3
    assert c["rating"] is None and c["affiliate_commission_percent"] is None
    assert len(c["levels"]) == 9 and c["levels"][0]["title"] == "AI Explorer 🛠️"
    assert len(c["channels"]) == 7 and c["channels"][0]["posts_count"] == 16134
    assert c["links"][1]["link"] == "https://get.glaido.com/nate"
    assert c["join_questions"][0] == {"question": "What is your email address?", "type": "email", "options": None}
    assert c["tabs"] == {"audio_chat": False, "calendar": True, "classroom": True, "map": True}
    assert c["landing_page_attachments"][3]["type"] == "video"
    assert c["landing_page_attachments"][3]["length_ms"] == 58087
    assert c["owner"]["handle"] == "nateherk" and c["owner"]["socials"]["youtube"] == "https://www.youtube.com/@nateherk"
    assert c["created_at"] == "2024-10-15T02:49:53.91923Z"
    assert c["has_more_reviews"] is False


def test_private_community_pricing(private_community):
    c = private_community
    assert c["is_private"] is True and c["is_free"] is False
    assert c["price"] == {"amount": 129.0, "currency": "USD", "interval": "month"}
    assert c["rating"] == {"average": 4.9, "count": 95} and c["affiliate_commission_percent"] == 20
    assert c["has_more_reviews"] is True
    tiers = {p["tier"]: p for p in c["plans"]}
    assert tiers["standard"]["prices"] == {"monthly": {"amount": 129.0, "currency": "USD", "interval": "month"}}
    assert tiers["premium"]["prices"] == {"annual": {"amount": 799.0, "currency": "USD", "interval": "year"}}
    assert tiers["vip"]["is_active"] is False and tiers["vip"]["deactivated_at"] == "2025-11-20T10:26:02.482075Z"
    assert tiers["standard"]["benefits"][0] == "One new premium course unlocks every 30 days"
    assert c["retention_video"]["length_ms"] == 51090


def test_reviewed_public_community_without_plans_page():
    c = P.parse_community(props("community_about_reviewed.json"))
    assert c["rating"] == {"average": 5.0, "count": 3} and c["is_private"] is True
    assert c["price"] == {"amount": 49.0, "currency": "USD", "interval": "month"}
    # the about page lists the tiers but carries no billing products
    assert [p["tier"] for p in c["plans"]] == ["standard", "premium"]
    assert all(p["prices"] is None for p in c["plans"])


def test_parse_community_survives_empty_props():
    c = P.parse_community({})
    assert c["id"] is None and c["slug"] is None and c["link"] is None and c["plans"] is None
    assert c["levels"] is None and c["owner"] is None and c["tabs"] is None


# ---- feed / posts --------------------------------------------------------------------

def test_feed_page():
    feed = P.parse_feed(props("community_feed.json"), SLUG)
    assert feed["pagination"] == {"page": 1, "items_per_page": 30, "total_pages": 891, "total_count": 26704}
    assert feed["community"]["name"] == "AI Automation Society"
    assert len(feed["channels"]) == 7
    assert len(feed["posts"]) == 33          # 30 + the 3 pinned posts Skool prepends
    post = feed["posts"][0]
    assert post["id"] == "353d0b255a1448a4afc5e68e0708d3d3"
    assert post["link"] == "https://www.skool.com/ai-automation-society/new-video-every-claude-20-concept-explained-for-non-coders"
    assert post["is_pinned"] is True and post["upvotes"] == 296 and post["comments_count"] == 162
    assert post["channel"]["name"] == "YouTube Resources 📚"
    assert post["videos"][0]["video_id"] == "tcb5q_6jwvY" and post["videos"][0]["length_ms"] == 1300000
    assert post["author"]["handle"] == "nateherk" and post["author"]["level"] == 9
    assert len(post["contributors"]) == 5 and set(post["contributors"][0]) == {"id", "handle", "name", "link", "picture"}
    assert post["created_at"] == "2026-10-30T23:27:12.908891Z"
    assert post["edited_at"] == "2026-10-30T23:32:55Z"
    assert post["last_comment_at"] == "2026-11-03T08:42:20Z"


def test_feed_past_the_end_is_empty():
    feed = P.parse_feed(props("community_feed_past_end.json"), SLUG, page=900)
    assert feed["posts"] == [] and feed["pagination"]["page"] == 900 and feed["pagination"]["total_pages"] == 891


def test_private_feed_is_a_redirect():
    assert props("community_feed_private_redirect.json")["__N_REDIRECT"] == "/ai-automation-society-plus/about"


def test_post_page():
    post = P.parse_post_page(props("post_page.json"), SLUG)
    assert post["id"] == "353d0b255a1448a4afc5e68e0708d3d3" and post["is_pinned"] is True
    assert post["title"].startswith("🚀New Video")
    assert post["followers_count"] == 0 and post["poll"] is None
    assert post["community_id"] == "b51c57150c70495899bf4bc8aaee8166"
    assert P.parse_post_page({}, SLUG) is None


# ---- comments ---------------------------------------------------------------------------

def test_comments_page():
    page = P.parse_comments(fixture("api_comments_head.json"))
    assert len(page["comments"]) == 25 and page["next_cursor"] == "1793427191345148"
    assert page["pinned_comment"] is None
    first = page["comments"][0]
    assert first["id"] == "e5dc1a5258654acca3a9f5f958c1eef3" and first["upvotes"] == 28
    assert first["author"]["handle"] == "geraldgerlich" and first["author"]["location"] == "München / Munich"
    assert first["replies_count"] == 4 and first["replies"][0]["parent_id"] == first["id"]
    assert first["last_reply_at"] == "2026-11-01T16:13:54Z"   # last_comment 1793549634905798000 ns
    assert sum(c["replies_count"] for c in page["comments"]) == 14


def test_comments_last_page_has_no_cursor():
    tail = P.parse_comments(fixture("api_comments_tail.json"))
    assert len(tail["comments"]) == 25 and tail["next_cursor"] == "1793633356558124"
    assert P.parse_comments({"post_tree": {"children": []}, "last": 0}) == \
        {"comments": [], "pinned_comment": None, "next_cursor": None}
    assert P.parse_comments(None)["comments"] == []


# ---- members / leaderboards ---------------------------------------------------------

def test_members_page():
    page = P.parse_members(props("community_members.json"))
    assert page["pagination"] == {"page": 1, "items_per_page": 30, "total_pages": 15953, "total_count": 478561}
    assert page["counts"] == {"members": 478561, "admins": 16, "online": 1303}
    assert page["tab"] == "member" and page["sort"] == "-memberapprovedat"
    member = page["members"][0]
    assert member["handle"] == "muhammad-atif-9850" and member["is_online"] is True
    assert member["level"] == 1 and member["level_points"] == {"current_level_at": 0, "next_level_at": 5}
    assert member["socials"] == {"facebook": None, "instagram": None, "linkedin": None, "twitter": None,
                                 "youtube": None, "website": "http://revupdigitals.com"}
    assert member["membership"]["role"] == "member"
    assert member["membership"]["joined_at"] == "2025-06-18T09:53:43.296345Z"
    assert member["membership"]["requested_at"] == "2025-06-18T08:10:15Z"


def test_admin_tab():
    page = P.parse_members(props("community_members_admin.json"))
    assert page["tab"] == "admin" and page["pagination"]["total_count"] == 16 and page["pagination"]["total_pages"] == 1
    assert {m["membership"]["role"] for m in page["members"]} == {"group-admin", "group-moderator"}


def test_leaderboards():
    boards = P.parse_leaderboards(props("community_leaderboards.json"))
    assert len(boards["all_time"]["ranking"]) == 10
    top = boards["all_time"]["ranking"][0]
    assert top["rank"] == 1 and top["points"] == 81147 and top["user"]["handle"] == "muskan-ahlawat-4812"
    assert boards["past_30_days"]["ranking"][0]["points"] == 3292
    assert boards["past_7_days"]["updated_at"] == "2026-11-03T08:54:51.870947212Z"
    assert len(boards["levels"]) == 9 and boards["levels"][8]["number"] == 9
    assert P.parse_leaderboards({}) == {"all_time": None, "past_30_days": None, "past_7_days": None, "levels": None}


# ---- classroom --------------------------------------------------------------------------

def test_classroom_list():
    courses = P.parse_classroom(props("community_classroom.json"), SLUG)
    assert len(courses) == 17
    first = courses[0]
    assert first["name"] == "3d31807e" and first["title"] == "Start Here" and first["type"] == "course"
    assert first["link"] == "https://www.skool.com/ai-automation-society/classroom/3d31807e"
    assert first["lessons_count"] == 3 and first["has_access"] is True and first["is_published"] is True
    assert "children" not in first


def test_course_tree():
    course = P.parse_course(props("community_course.json"), SLUG)
    assert course["id"] == "993c60aa26514df388cc82561fe33e42" and course["selected_lesson_id"] == "87dcf10a8b2e4e17be8aee82c2c2f11e"
    assert [c["title"] for c in course["children"]] == ["Rules and Guidelines 🛠️", "Requesting Help🆘",
                                                        "Jump In! Introduce Yourself"]
    lesson = course["children"][0]
    assert lesson["type"] == "module"
    assert lesson["link"] == "https://www.skool.com/ai-automation-society/classroom/3d31807e?md=87dcf10a8b2e4e17be8aee82c2c2f11e"
    assert lesson["video"]["length_ms"] == 67238 and lesson["video"]["link"].startswith("https://www.loom.com/")
    assert lesson["description"] is None and lesson["resources"] is None
    assert P.parse_course({}, SLUG) is None


def test_course_redirect_carries_the_first_lesson():
    assert props("community_course_redirect.json")["__N_REDIRECT"] == \
        "/ai-automation-society/classroom/3d31807e?md=87dcf10a8b2e4e17be8aee82c2c2f11e"


# ---- calendar ---------------------------------------------------------------------------

def test_calendar():
    cal = P.parse_calendar(props("community_calendar.json"))
    assert cal["timezone"] == "America/Los_Angeles" and cal["has_events"] is True and len(cal["events"]) == 7
    event = cal["events"][0]
    assert event["id"] == "8c9c538406fb40358185a5c2aa3c8f47" and event["occurrence_id"] == "1793023200"
    assert event["start_at"] == "2026-10-26T09:00:00-05:00" and event["timezone"] == "America/Chicago"
    assert event["location"] == "https://www.skool.com/ai-automation-society-plus/about"
    assert event["has_access"] is True and event["recurrence"] is None
    api_event = P.parse_event(fixture("api_event.json"))
    assert api_event["recurrence"] == {"frequency": "weekly", "interval": 2, "days": [1]}
    assert P.parse_calendar({}) == {"timezone": None, "has_events": False, "events": []}


# ---- reviews ----------------------------------------------------------------------------

def test_reviews_api_and_about_dialects():
    api = P.parse_reviews(fixture("api_reviews.json"))
    assert len(api["reviews"]) == 10 and api["has_more"] is True
    review = api["reviews"][0]
    assert review["rating"] == 5 and review["is_currently_paying"] is True
    assert review["author"]["handle"] and review["member_since"]
    about = P.parse_reviews(props("community_about_private.json")["reviewsData"])
    assert len(about["reviews"]) == 5 and about["has_more"] is True
    assert P.parse_reviews({"reviews": None}) == {"reviews": [], "has_more": False}


# ---- in-community search ----------------------------------------------------------------

def test_search_posts():
    result = P.parse_search(props("community_search_posts.json"), SLUG, "posts")
    assert result["pagination"] == {"page": 1, "items_per_page": 10, "total_pages": 100, "total_count": 1000}
    assert result["counts"] == {"posts": 1000, "members": 1718, "courses": 64} and result["query"] == "claude"
    hit = result["results"][0]
    assert hit["slug"] == "claude-cowork-and-claude-code" and "<em>claude</em>" in hit["content_highlight"]
    assert hit["link"] == "https://www.skool.com/ai-automation-society/claude-cowork-and-claude-code"


def test_search_members_and_courses():
    members = P.parse_search(props("community_search_members.json"), SLUG, "members")
    assert members["pagination"]["total_count"] == 3418 and members["pagination"]["total_pages"] == 342
    assert members["results"][0]["handle"] == "armando-montoya-4949"
    assert members["results"][0]["membership"]["role"] == "member"
    courses = P.parse_search(props("community_search_courses.json"), SLUG, "courses")
    assert courses["pagination"] == {"page": 1, "items_per_page": 10, "total_pages": 7, "total_count": 64}
    lesson = courses["results"][0]
    assert lesson["title"] == "Prerequisites & Setup"
    assert lesson["course"] == {"name": "dda699b7", "title": "7 Day AIS Challenge", "section": "Start Here"}
    assert lesson["link"] == "https://www.skool.com/ai-automation-society/classroom/dda699b7?md=55d161e649224e06bec7b972ba1ea877"
    assert "<em>Claude</em>" in lesson["description_highlight"]


# ---- profiles ----------------------------------------------------------------------------

def test_profile():
    user = P.parse_profile(props("user_profile.json"))
    assert user["handle"] == "nateherk" and user["link"] == "https://www.skool.com/@nateherk"
    assert user["stats"] == {"posts": 4925, "contributions": 4925, "followers": 498856, "following": 20,
                             "communities": 20}
    assert user["mrr_status"] == "diamond"
    assert [c["slug"] for c in user["communities_created"]] == ["ai-automation-society", "ai-automation-society-plus"]
    assert user["communities_created"][1]["price"] == {"amount": 129.0, "currency": "USD", "interval": "month"}
    assert [c["slug"] for c in user["communities_joined"]] == ["platinum", "skoolers"]
    assert user["activity"]["start_date"] == "2025-11-10T00:00:00Z" and len(user["activity"]["daily_counts"]) == 359
    assert user["last_online_at"] == "2026-11-01T19:00:41Z"
    assert P.parse_profile({}) is None


def test_follow_lists():
    followers = P.parse_follow_list(props("user_followers.json"), "followers")
    assert followers["pagination"] == {"page": 1, "items_per_page": 30, "total_pages": 16629, "total_count": 498857}
    assert followers["users"][0]["handle"] == "yasmine-seidu-7033"
    following = P.parse_follow_list(props("user_following.json"), "following")
    assert following["pagination"]["total_count"] == 20 and following["users"][0]["handle"] == "liamottley"
    assert P.parse_follow_list({}, "followers")["users"] == []


def test_api_user_record():
    user = P.parse_user(fixture("api_user.json"))
    assert user["handle"] == "nateherk" and user["socials"]["instagram"] == "https://www.instagram.com/nateherk/"
    assert user["level"] is None and user["joined_skool_at"] == "2024-08-22T15:27:52.39198Z"
    assert P.parse_user(None) is None
    assert P.parse_user({})["id"] is None


# ---- error bodies ----------------------------------------------------------------------

def test_error_bodies():
    assert fixture("not_found.json") == {"notFound": True}
    assert parse_build_id(fixture("stale_build_404.html")) == "1793658950759"
    challenge = fixture("waf_challenge.html")
    assert "awswaf" in challenge.lower() and parse_build_id(challenge) is None


def test_stale_build_404_is_retried_even_when_another_thread_refreshed(monkeypatch):
    """Two threads hit a stale buildId at once: the first refreshes the
    shared id, the second must still see ITS 404 as stale (retry), not as
    a missing entity."""
    from skool import fetch

    class Resp:
        status_code = 404
        text = fixture("stale_build_404.html")   # carries buildId 1793658950759
        headers = {}

    class Sess:
        def get(self, *a, **k):
            return Resp()
    monkeypatch.setattr(fetch, "_session", lambda: Sess())
    monkeypatch.setattr(fetch, "_build_id", lambda: "old-build")
    # another thread already stored the fresh id before this request's 404 came back
    monkeypatch.setitem(fetch._build, "id", "1793658950759")
    monkeypatch.setattr(fetch.config, "MAX_RETRIES", 1)
    with pytest.raises(fetch._StaleBuild):
        fetch.fetch_page_props("/x/about", {"group": "x"}, "community x")
    # the same 404 page for a request that already used the fresh id is a real miss
    monkeypatch.setattr(fetch, "_build_id", lambda: "1793658950759")
    with pytest.raises(fetch.SkoolNotFound):
        fetch.fetch_page_props("/x/about", {"group": "x"}, "community x")
