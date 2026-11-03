"""Reference resolvers + the small vocabularies the /skool/* schemas need.

ONE param per input (tripadvisor QueryOrIdField convention): every
reference field accepts a bare identifier OR any www.skool.com link for the
same record. Resolvers raise ValueError with a user-facing message
(schema_fields.RefField turns it into a 400).

Identifier shapes (captured 2026-11-03):
  * community  the URL slug: https://www.skool.com/<slug>[/about|/classroom|...]
               (letters, digits, "-"; never "@..." or a reserved path)
  * post       "<community>/<post-slug>" OR https://www.skool.com/<slug>/<post-slug>
               (a post slug alone is ambiguous: Skool scopes it to the group)
  * user       "@handle" / "handle" OR https://www.skool.com/@handle
  * course     the 8-hex course name, the 32-hex course id, OR
               https://www.skool.com/<slug>/classroom/<name>[?md=<module id>]

Discovery vocabularies: the language names Skool's /discovery filter takes
(`lang=`), captured from the discovery page's `languages` list on
2026-11-03 (48 entries). Categories are ids that move, so api.py resolves a
category slug / name against the live list (categories/list) instead.
"""
import re
from urllib.parse import parse_qs, urlparse

SITE = "https://www.skool.com"
API = "https://api2.skool.com"

HEX32_RE = re.compile(r"^[0-9a-f]{32}$", re.I)
HEX8_RE = re.compile(r"^[0-9a-f]{8}$", re.I)
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$", re.I)
HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$", re.I)

# First path segments on www.skool.com that are not communities.
RESERVED = {
    "discovery", "about", "pricing", "login", "signup", "logout", "settings",
    "support", "legal", "privacy", "features", "careers", "contact", "chats",
    "chat", "notifications", "notifs", "refer", "partners", "affiliate-program",
    "app", "health", "maintenance", "payouts", "hormozi",
    "dean", "account-onboarding", "_next", "api",
}

# /<slug>/<second segment> values that are group tabs, not post slugs.
GROUP_TABS = {"about", "classroom", "calendar", "plans", "-", "--"}


def _host_is_skool(url):
    host = (urlparse(url).hostname or "").lower()
    return host == "skool.com" or host.endswith(".skool.com")


def _parsed_link(value):
    """A skool.com link -> (path segments, query dict); None when `value`
    is not a link. Raises ValueError for another site's link."""
    if not value.startswith(("http://", "https://", "//")):
        return None
    url = value if not value.startswith("//") else "https:" + value
    if not _host_is_skool(url):
        raise ValueError("Must be a skool.com link.")
    parsed = urlparse(url)
    segments = [s for s in parsed.path.split("/") if s]
    query = {k: v[0] for k, v in parse_qs(parsed.query).items() if v}
    return segments, query


def _community_segment(segment):
    slug = segment.lower()
    if slug.startswith("@") or slug in RESERVED or not SLUG_RE.match(slug):
        return None
    return slug


def resolve_community(value):
    """Bare slug or any www.skool.com community link -> the slug."""
    value = (value or "").strip()
    link = _parsed_link(value)
    if link is None:
        slug = _community_segment(value.strip("/"))
        if slug:
            return slug
        raise ValueError("Must be a Skool community name (ai-automation-society) "
                         "or a skool.com community link.")
    segments, _ = link
    slug = _community_segment(segments[0]) if segments else None
    if not slug:
        raise ValueError("Must be a skool.com community link "
                         "(https://www.skool.com/<community>).")
    return slug


def resolve_post(value):
    """"<community>/<post-slug>" or a skool.com post link ->
    "<community>/<post-slug>" (both lower-case slugs)."""
    value = (value or "").strip()
    link = _parsed_link(value)
    if link is None:
        segments = [s for s in value.split("/") if s]
    else:
        segments, _ = link
    if len(segments) == 2:
        slug = _community_segment(segments[0])
        post = segments[1].lower()
        if slug and post not in GROUP_TABS and SLUG_RE.match(post):
            return f"{slug}/{post}"
    raise ValueError("Must be a Skool post as <community>/<post-slug> or a skool.com "
                     "post link (https://www.skool.com/<community>/<post-slug>).")


def split_post(ref):
    """"<community>/<post-slug>" -> (community, post_slug)."""
    community, _, post = ref.partition("/")
    return community, post


def resolve_user(value):
    """"@handle" / "handle" or https://www.skool.com/@handle -> the handle."""
    value = (value or "").strip()
    link = _parsed_link(value)
    if link is None:
        handle = value.strip("/")
    else:
        segments, _ = link
        handle = segments[0] if segments else ""
    handle = handle.lstrip("@").lower()
    if link is not None and not (segments and segments[0].startswith("@")):
        raise ValueError("Must be a skool.com profile link (https://www.skool.com/@handle).")
    if handle and HANDLE_RE.match(handle):
        return handle
    raise ValueError("Must be a Skool handle (@nateherk) or a skool.com profile link.")


def resolve_course(value):
    """8-hex course name, 32-hex course id, or a classroom link ->
    "<name>" or "<name>?md=<module id>" style token kept as given:
    returns the course name (8 hex) or id (32 hex). A classroom link may
    also carry the module id; api.py reads it from the link separately."""
    value = (value or "").strip()
    link = _parsed_link(value)
    if link is None:
        token = value.lower()
        if HEX8_RE.match(token) or HEX32_RE.match(token):
            return token
        raise ValueError("Must be a Skool course name (8 hex chars), course id "
                         "(32 hex chars) or a skool.com classroom link.")
    segments, _ = link
    if len(segments) >= 3 and segments[1].lower() == "classroom":
        token = segments[2].lower()
        if HEX8_RE.match(token) or HEX32_RE.match(token):
            return token
    raise ValueError("Must be a skool.com classroom link "
                     "(https://www.skool.com/<community>/classroom/<course>).")


def course_link_community(value):
    """The community slug inside a classroom link, else None (so a bare
    course name still needs the `community` param)."""
    value = (value or "").strip()
    try:
        link = _parsed_link(value)
    except ValueError:
        return None
    if link is None:
        return None
    segments, _ = link
    return _community_segment(segments[0]) if segments else None


def community_link(slug):
    return f"{SITE}/{slug}"


def post_link(slug, post):
    return f"{SITE}/{slug}/{post}"


def user_link(handle):
    return f"{SITE}/@{handle}"


def course_link(slug, course_name, module_id=None):
    link = f"{SITE}/{slug}/classroom/{course_name}"
    return f"{link}?md={module_id}" if module_id else link


# ---- discovery vocabularies ---------------------------------------------------

# ISO 639-1 code -> the name Skool's discovery `lang=` filter takes.
LANGUAGES = {
    "en": "english", "de": "german", "es": "spanish", "fr": "french", "zh": "chinese",
    "it": "italian", "nl": "dutch", "vi": "vietnamese", "ar": "arabic", "he": "hebrew",
    "da": "danish", "ro": "romanian", "tr": "turkish", "pl": "polish", "cs": "czech",
    "hu": "hungarian", "sv": "swedish", "pt": "portuguese", "bg": "bulgarian",
    "no": "norwegian", "fi": "finnish", "hr": "croatian", "lv": "latvian", "sk": "slovak",
    "sr": "serbian", "mn": "mongolian", "ht": "haitian", "th": "thai", "sl": "slovenian",
    "ru": "russian", "lt": "lithuanian", "am": "amharic", "ms": "malay", "et": "estonian",
    "el": "greek", "uk": "ukrainian", "sw": "swahili", "ja": "japanese", "tl": "filipino",
    "fa": "persian", "cy": "welsh", "ko": "korean", "yue": "cantonese", "id": "indonesian",
    "la": "latin", "bn": "bengali", "ca": "catalan", "hi": "hindi",
}
LANGUAGE_NAMES = frozenset(LANGUAGES.values())
ALL_LANGUAGES = "all"


def resolve_language(value):
    """"en" / "english" / "all" -> the `lang=` token Skool takes."""
    value = (value or "").strip().lower()
    if value in (ALL_LANGUAGES, "any", "*"):
        return ALL_LANGUAGES
    if value in LANGUAGES:
        return LANGUAGES[value]
    if value in LANGUAGE_NAMES:
        return value
    raise ValueError("Must be a language name or ISO code Skool lists (english / en, "
                     "spanish / es, ...) or 'all'.")


# Member sort choices -> the members page's `sortType` token.
MEMBER_SORTS = {"newest": "-memberapprovedat", "last_active": "-memberlastoffline",
                "points": "-memberpoints"}
MEMBER_TABS = ("member", "admin", "online")
DISCOVERY_PRICES = ("free", "paid")
DISCOVERY_TYPES = ("public", "private")
DISCOVERY_SORTS = ("trending", "top")
SEARCH_TYPES = ("posts", "members", "courses")
FOLLOW_TYPES = ("followers", "following")
