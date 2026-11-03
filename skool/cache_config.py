"""Cache TTL per /skool/* endpoint (cache.py, keyed on the validated params).
Skool is a live community platform: feeds and comments move by the minute,
directories and profiles by the hour, course trees and plans by the week.
The community record (about + plans) is cached ONCE per slug and sliced by
details / reviews / courses, so hitting them all on one community costs
one upstream page.
"""
from datetime import timedelta

# Discovery directory: trending order reshuffles through the day.
SEARCH_CACHE = timedelta(hours=1)
# Category list: Skool adds categories rarely.
CATEGORIES_CACHE = timedelta(hours=24)
# One row per community slug: the parsed about page (+ plans for tiered
# communities). Member counts drift slowly; prices and owner rarely.
COMMUNITY_CACHE = timedelta(hours=6)
# Feed pages: new posts land continuously in big communities.
POSTS_CACHE = timedelta(minutes=15)
# Member roster pages: joins are continuous, order is stable per sort.
MEMBERS_CACHE = timedelta(hours=1)
# Leaderboards: Skool recomputes them every few minutes.
LEADERBOARD_CACHE = timedelta(minutes=30)
# Classroom tree + course pages: lessons are published occasionally.
COURSES_CACHE = timedelta(hours=6)
# Calendar month: events are scheduled days ahead.
EVENTS_CACHE = timedelta(hours=1)
# Reviews: a few per day on the busiest communities.
REVIEWS_CACHE = timedelta(hours=6)
# In-community search: the index trails the feed by minutes.
CONTENT_SEARCH_CACHE = timedelta(minutes=30)
# One row per post: title / body / counters (comments arrive separately).
POST_CACHE = timedelta(minutes=15)
# Comment pages: cursor-keyed, threads move by the minute.
COMMENTS_CACHE = timedelta(minutes=10)
# Profiles: follower counts and activity graph move by the hour.
USER_CACHE = timedelta(hours=1)
# Follower / following pages.
FOLLOWERS_CACHE = timedelta(hours=1)
