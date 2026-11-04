# 🏫 Skool Scraper

Skool Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Skool data for free.

## ✨ What Can I Get?

- 🏫 **Full details on any Skool community** — owner & socials, price & tiers, members, rating, levels & join questions
- 🔍 **Search Skool's directory across 31 categories & 48 languages** — price, members & rating for every community
- 👥 **Every member of communities as big as 478K+** — name, bio, location, socials, level, points & join date
- 💬 **Posts, comments, courses & events** — full post text, nested replies, lesson videos, calendars, reviews & leaderboards

## 🎥 Example: A Full Skool Community

```json
{
  "id": "f09a730f782d4507a02c22164695a366",
  "slug": "the-ai-advantage",
  "name": "The AI Advantage",
  "link": "https://www.skool.com/the-ai-advantage",
  "description": "Founded by Tony Robbins, Dean Graziosi & Igor Pogany - AI Advantage is your go-to hub to simplify AI and confidently unlock real & repeatable results",
  "is_private": false,
  "is_free": true,
  "members_count": 130536,
  "online_members_count": 488,
  "posts_count": 21621,
  "courses_count": 9,
  "lessons_count": 95,
  "levels": [
    { "number": 1, "name": "Level 1", "title": "AI Newbie", "percent_of_members": 87 },
    { "number": 2, "name": "Level 2", "title": "AI Explorer", "percent_of_members": 6 }
  ],
  "channels": [
    { "id": "b8b5afa845d240adb6ee5478a2a1650a", "name": "General Discussion", "posts_count": 17405 }
  ],
  "join_questions": [
    { "question": "What's your experience level with AI (tools like ChatGPT, Claude, MidJourney etc.)", "type": "options" }
  ],
  "owner": {
    "handle": "tony-robbins-dean-graziosi-9241",
    "name": "Tony Robbins and Dean Graziosi",
    "link": "https://www.skool.com/@tony-robbins-dean-graziosi-9241"
  },
  "created_at": "2025-08-26T23:27:06.079551Z"
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Skool Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/skool-scraper
cd skool-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/communities/details?community=the-ai-advantage"
```

```json
{
  "id": "f09a730f782d4507a02c22164695a366",
  "slug": "the-ai-advantage",
  "name": "The AI Advantage",
  "link": "https://www.skool.com/the-ai-advantage",
  "is_private": false,
  "is_free": true,
  "price": null,
  "members_count": 130536,
  "online_members_count": 489,
  "posts_count": 21621,
  "courses_count": 9,
  "lessons_count": 95,
  "levels": [
    { "number": 1, "name": "Level 1", "title": "AI Newbie", "percent_of_members": 87 }
  ],
  "owner": {
    "handle": "tony-robbins-dean-graziosi-9241",
    "name": "Tony Robbins and Dean Graziosi",
    "link": "https://www.skool.com/@tony-robbins-dean-graziosi-9241"
  }
}
```

All 14 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

14 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Community Details | `/communities/details` | Owner, socials, price, tiers, members, rating and levels in one call |
| List Categories | `/categories/list` | Every discovery category and language, ready for search filters |
| Search Communities | `/communities/search` | 30 communities per page; filter by category, price, type, language |
| Community Posts | `/communities/posts` | The full feed, 30 posts per page, filterable by channel |
| Post Details | `/posts/details` | Full post text, author, upvotes, videos and attachments |
| Post Comments | `/posts/comments` | Every comment with its nested replies, 25 per page |
| Community Members | `/communities/members` | 30 members per page with bios, socials, level and points |
| Community Leaderboard | `/communities/leaderboard` | All-time, 30-day and 7-day top 10 plus level names |
| Community Courses | `/communities/courses` | Every course, or one course's lessons with video links |
| Community Events | `/communities/events` | One month of calendar events with times and locations |
| Community Reviews | `/communities/reviews` | Member reviews with star ratings, up to 50 per page |
| Search Community | `/communities/search_posts` | Matching posts, members or lessons inside one community |
| User Details | `/users/details` | Bio, socials, followers, activity and every community they run |
| User Followers | `/users/followers` | Anyone's followers or following list, 30 per page |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-skool-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-skool-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-skool-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/communities/search",
    params={"query": "real estate", "price": "paid"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Skool Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://www.omkar.cloud/l/skool-scraper-github-whatsapp)

[![Ask Us by Email about Skool Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Skool%20Scraper%20API&body=I%20need%20help%20using%20the%20Skool%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/skool-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/skool-scraper)
