"""Offline tests for the /skool/* request schemas.

    python -m pytest skool/test_schemas.py -q
"""
import os
import sys

import pytest
from marshmallow import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skool import schemas  # noqa: E402

LINK = "https://www.skool.com/ai-automation-society"


def errors(schema, data):
    with pytest.raises(ValidationError) as info:
        schema().load(data)
    return info.value.normalized_messages()


def test_community_schema_accepts_slug_and_link():
    assert schemas.CommunitySchema().load({"community": " AI-Automation-Society "}) == \
        {"community": "ai-automation-society"}
    assert schemas.CommunitySchema().load({"community": LINK + "/about"}) == {"community": "ai-automation-society"}


@pytest.mark.parametrize("value", ["", "@nateherk", "https://example.com/x", "discovery"])
def test_community_schema_rejects(value):
    assert "community" in errors(schemas.CommunitySchema, {"community": value})


def test_community_schema_rejects_sibling_params():
    assert "url" in errors(schemas.CommunitySchema, {"community": "x", "url": LINK})
    assert "community" in errors(schemas.CommunitySchema, {})


def test_search_schema_defaults_and_filters():
    loaded = schemas.CommunitiesSearchSchema().load({})
    assert loaded == {"query": None, "category": None, "price": None, "type": None, "language": None,
                      "sort": None, "page": 1}
    loaded = schemas.CommunitiesSearchSchema().load({"query": " ai ", "price": "Paid", "type": "PUBLIC",
                                                     "language": "es", "sort": "Top", "page": "34",
                                                     "category": "ai_automation"})
    assert loaded == {"query": "ai", "category": "ai_automation", "price": "paid", "type": "public",
                      "language": "spanish", "sort": "top", "page": 34}
    assert schemas.CommunitiesSearchSchema().load({"language": "All"})["language"] == "all"


def test_search_schema_rejects():
    assert "page" in errors(schemas.CommunitiesSearchSchema, {"page": "35"})
    assert "price" in errors(schemas.CommunitiesSearchSchema, {"price": "cheap"})
    assert "language" in errors(schemas.CommunitiesSearchSchema, {"language": "klingon"})
    messages = errors(schemas.CommunitiesSearchSchema, {"sort": "top"})
    assert "sort" in messages and "needs a query" in messages["sort"][0]


def test_posts_schema():
    loaded = schemas.CommunityPostsSchema().load({"community": LINK, "channel": "General Discussion 💬", "page": "3"})
    assert loaded == {"community": "ai-automation-society", "channel": "General Discussion 💬", "page": 3}
    assert "page" in errors(schemas.CommunityPostsSchema, {"community": LINK, "page": "0"})


def test_members_schema():
    loaded = schemas.CommunityMembersSchema().load({"community": LINK, "tab": "Admin", "sort": "points", "level": "5"})
    assert loaded == {"community": "ai-automation-society", "tab": "admin", "sort": "-memberpoints", "level": 5,
                      "page": 1}
    assert schemas.CommunityMembersSchema().load({"community": LINK})["tab"] == "member"
    assert "tab" in errors(schemas.CommunityMembersSchema, {"community": LINK, "tab": "banned"})
    assert "level" in errors(schemas.CommunityMembersSchema, {"community": LINK, "level": "10"})
    assert "sort" in errors(schemas.CommunityMembersSchema, {"community": LINK, "sort": "oldest"})


def test_courses_schema():
    assert schemas.CommunityCoursesSchema().load({"community": LINK}) == {"community": "ai-automation-society",
                                                                          "course": None}
    loaded = schemas.CommunityCoursesSchema().load({"community": LINK, "course": LINK + "/classroom/3d31807e?md=x"})
    assert loaded["course"] == "3d31807e"
    assert "course" in errors(schemas.CommunityCoursesSchema, {"community": LINK, "course": "start-here"})


def test_events_schema():
    assert schemas.CommunityEventsSchema().load({"community": LINK}) == {"community": "ai-automation-society",
                                                                         "month": None}
    assert schemas.CommunityEventsSchema().load({"community": LINK, "month": "2026-12"})["month"] == "2026-12"
    assert "month" in errors(schemas.CommunityEventsSchema, {"community": LINK, "month": "2026-13"})
    assert "month" in errors(schemas.CommunityEventsSchema, {"community": LINK, "month": "December"})


def test_reviews_schema():
    assert schemas.CommunityReviewsSchema().load({"community": LINK}) == {"community": "ai-automation-society",
                                                                          "page": 1, "limit": 10}
    assert schemas.CommunityReviewsSchema().load({"community": LINK, "limit": "50", "page": "2"})["limit"] == 50
    assert "limit" in errors(schemas.CommunityReviewsSchema, {"community": LINK, "limit": "51"})


def test_content_search_schema():
    loaded = schemas.CommunitySearchSchema().load({"community": LINK, "query": "claude", "type": "Courses"})
    assert loaded == {"community": "ai-automation-society", "query": "claude", "type": "courses", "page": 1}
    assert "query" in errors(schemas.CommunitySearchSchema, {"community": LINK})
    assert "type" in errors(schemas.CommunitySearchSchema, {"community": LINK, "query": "x", "type": "events"})
    assert "page" in errors(schemas.CommunitySearchSchema, {"community": LINK, "query": "x", "page": "101"})


def test_post_schemas():
    assert schemas.PostSchema().load({"post": LINK + "/new-video"}) == {"post": "ai-automation-society/new-video"}
    assert schemas.PostSchema().load({"post": "ai-automation-society/new-video"}) == \
        {"post": "ai-automation-society/new-video"}
    assert "post" in errors(schemas.PostSchema, {"post": "new-video"})
    loaded = schemas.PostCommentsSchema().load({"post": LINK + "/new-video", "cursor": "1793427191345148"})
    assert loaded == {"post": "ai-automation-society/new-video", "cursor": "1793427191345148"}
    assert schemas.PostCommentsSchema().load({"post": LINK + "/new-video"})["cursor"] is None
    assert "cursor" in errors(schemas.PostCommentsSchema, {"post": LINK + "/new-video", "cursor": "abc"})


def test_user_schemas():
    assert schemas.UserSchema().load({"user": "@NateHerk"}) == {"user": "nateherk"}
    assert schemas.UserSchema().load({"user": "https://www.skool.com/@nateherk"}) == {"user": "nateherk"}
    assert "user" in errors(schemas.UserSchema, {"user": LINK})
    loaded = schemas.UserFollowersSchema().load({"user": "nateherk", "type": "Following", "page": "2"})
    assert loaded == {"user": "nateherk", "type": "following", "page": 2}
    assert schemas.UserFollowersSchema().load({"user": "nateherk"})["type"] == "followers"
    assert "type" in errors(schemas.UserFollowersSchema, {"user": "nateherk", "type": "friends"})


def test_categories_schema_takes_nothing():
    assert schemas.CategoriesSchema().load({}) == {}
    assert "query" in errors(schemas.CategoriesSchema, {"query": "x"})
