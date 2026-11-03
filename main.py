"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json. Params go through the same schemas the API uses, so defaults
are filled in and a community name or link both work.
"""
import json
import os

from skool import api, schemas

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


def run(schema_cls, fn, **params):
    return fn(**schema_cls().load(params))


if __name__ == "__main__":
    # a community name or any skool.com community link — owner, socials, price, tiers, members, rating
    save("community_the_ai_advantage.json",
         run(schemas.CommunitySchema, api.community_details, community="the-ai-advantage"))

    # 30 communities per page, filter by keyword, category, price, type and language
    save("search_real_estate.json",
         run(schemas.CommunitiesSearchSchema, api.communities_search, query="real estate"))

    # 30 members per page — name, bio, socials, level, points, role and join date
    save("members_the_ai_advantage.json",
         run(schemas.CommunityMembersSchema, api.community_members, community="the-ai-advantage"))
