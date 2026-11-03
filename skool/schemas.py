"""Marshmallow request schemas for every /skool/* route.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair):

    community   a community slug ("ai-automation-society") OR any skool.com
                community link
    post        "<community>/<post-slug>" OR a skool.com post link
    user        "@handle" / "handle" OR a skool.com profile link
    course      a course name (8 hex), course id (32 hex) OR a classroom link
    category    a discovery category slug / name / id (resolved live)
    language    an ISO 639-1 code or Skool's language name, or "all"
    cursor      the `next_cursor` of the previous comments page

Page caps follow the site: discovery stops at 1000 results (34 pages of
30), a feed runs to its last page (total / 30), member rosters to
total / 30, in-community search to 100 pages.
"""
from marshmallow import ValidationError, validates_schema

from schema_fields import (BaseSchema, ChoiceField, LimitField, PageField, PositiveInt, QueryField, RefField,
                           StrippedString, YearMonthField)
from skool import refs

DISCOVERY_MAX_PAGE = 34       # 1000 results / 30 per page
FEED_MAX_PAGE = 5000          # the largest community has ~900 feed pages
MEMBERS_MAX_PAGE = 50000      # 478k members / 30 per page
SEARCH_MAX_PAGE = 100         # Skool's own totalPostPages cap
REVIEWS_MAX_LIMIT = 50        # api2 accepts up to 50 per call


class CommunityRefField(RefField):
    resolver = staticmethod(refs.resolve_community)


class PostRefField(RefField):
    resolver = staticmethod(refs.resolve_post)


class UserRefField(RefField):
    resolver = staticmethod(refs.resolve_user)


class CourseRefField(RefField):
    resolver = staticmethod(refs.resolve_course)


class LanguageField(RefField):
    resolver = staticmethod(refs.resolve_language)


class CursorField(StrippedString):
    """The `next_cursor` of the previous comments page (absent = first page)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        if not value.isdigit():
            raise ValidationError("Must be the next_cursor of the previous comments page.")
        return value


_COMMUNITY = {"description": "community name as in its skool.com link (ai-automation-society), or the link itself"}


class CommunitiesSearchSchema(BaseSchema):
    query = QueryField(required=False, load_default=None, metadata={
        "description": "keyword to search community names and descriptions; omit to browse"})
    category = StrippedString(required=False, load_default=None, metadata={
        "description": "discovery category slug, name or id (see /skool/categories/list), e.g. ai_automation"})
    price = ChoiceField(refs.DISCOVERY_PRICES, metadata={"description": "free or paid communities only"})
    type = ChoiceField(refs.DISCOVERY_TYPES, metadata={"description": "public or private communities only"})
    language = LanguageField(required=False, load_default=None, metadata={
        "description": "community language as an ISO code or name (en / english, es / spanish, ...), or all; "
                       "default english"})
    sort = ChoiceField(refs.DISCOVERY_SORTS, metadata={
        "description": "trending (default) or top; top needs a query"})
    page = PageField(max_page=DISCOVERY_MAX_PAGE, metadata={"description": "page of 30 communities (max 34)"})

    @validates_schema
    def _top_needs_query(self, data, **kwargs):
        if data.get("sort") == "top" and not data.get("query"):
            raise ValidationError("sort=top needs a query (Skool only ranks search results).", "sort")


class CommunitySchema(BaseSchema):
    community = CommunityRefField(metadata=_COMMUNITY)


class CommunityPostsSchema(BaseSchema):
    community = CommunityRefField(metadata=_COMMUNITY)
    channel = StrippedString(required=False, load_default=None, metadata={
        "description": "feed channel (category) name or id to filter by, as listed in channels"})
    page = PageField(max_page=FEED_MAX_PAGE, metadata={"description": "feed page of 30 posts, newest first"})


class CommunityMembersSchema(BaseSchema):
    community = CommunityRefField(metadata=_COMMUNITY)
    tab = ChoiceField(refs.MEMBER_TABS, load_default="member", metadata={
        "description": "member (everyone, default), admin (admins and moderators) or online"})
    sort = ChoiceField(refs.MEMBER_SORTS, metadata={
        "description": "newest (default, by join date), last_active or points"})
    level = PositiveInt(max_value=9, metadata={"description": "only members at this level (1-9)"})
    page = PageField(max_page=MEMBERS_MAX_PAGE, metadata={"description": "page of 30 members"})


class CommunityCoursesSchema(BaseSchema):
    community = CommunityRefField(metadata=_COMMUNITY)
    course = CourseRefField(required=False, load_default=None, metadata={
        "description": "a course name (8 hex chars), id or classroom link to return its lessons; omit to list courses"})


class CommunityEventsSchema(BaseSchema):
    community = CommunityRefField(metadata=_COMMUNITY)
    month = YearMonthField(metadata={"description": "calendar month as YYYY-MM; default the current month"})


class CommunityReviewsSchema(BaseSchema):
    community = CommunityRefField(metadata=_COMMUNITY)
    page = PageField(max_page=1000, metadata={"description": "page of reviews, newest first"})
    limit = LimitField(default=10, max_size=REVIEWS_MAX_LIMIT, metadata={"description": "reviews per page (max 50)"})


class CommunitySearchSchema(BaseSchema):
    community = CommunityRefField(metadata=_COMMUNITY)
    query = QueryField(metadata={"description": "text to search inside the community"})
    type = ChoiceField(refs.SEARCH_TYPES, load_default="posts", metadata={
        "description": "posts (default), members or courses (matching lessons)"})
    page = PageField(max_page=SEARCH_MAX_PAGE, metadata={"description": "page of 10 results"})


class PostSchema(BaseSchema):
    post = PostRefField(metadata={
        "description": "post as <community>/<post-slug>, or its skool.com link"})


class PostCommentsSchema(BaseSchema):
    post = PostRefField(metadata={
        "description": "post as <community>/<post-slug>, or its skool.com link"})
    cursor = CursorField(metadata={"description": "next_cursor from the previous page; omit for the first 25 comments"})


class UserSchema(BaseSchema):
    user = UserRefField(metadata={"description": "Skool handle (@nateherk) or profile link"})


class UserFollowersSchema(BaseSchema):
    user = UserRefField(metadata={"description": "Skool handle (@nateherk) or profile link"})
    type = ChoiceField(refs.FOLLOW_TYPES, load_default="followers", metadata={
        "description": "followers (default) or following"})
    page = PageField(max_page=MEMBERS_MAX_PAGE, metadata={"description": "page of 30 users"})


class CategoriesSchema(BaseSchema):
    """No parameters."""
