"""
Veritas Lens — Shared Text Cleaning Utilities
==============================================

Pure utility functions for article text extraction and cleaning.
Extracted from fetch_feed.py so they can be reused by the standalone
RSS fetcher (fetch_rss_standalone.py) without importing Celery or DB.

Functions:
    clean_html       — Strip HTML tags and normalize whitespace
    deep_clean_text  — Aggressively remove paywall/junk/boilerplate
    detect_language  — Auto-detect Tamil vs English vs mixed
    get_canonical_url — Canonicalize URLs and follow Google News redirects
"""

import re
import os
import urllib.parse
import requests
from bs4 import BeautifulSoup
import html
import json
from difflib import SequenceMatcher
from datetime import datetime
from zoneinfo import ZoneInfo


NEWS_TIMEZONE = ZoneInfo("Asia/Kolkata")


def normalize_news_datetime(published_at):
    """Store publication timestamps as naive Asia/Kolkata wall time.

    The SQLAlchemy column is timezone-naive, so normalize aware feed dates
    before persistence to avoid silently mixing UTC and local timestamps.
    """
    if published_at and published_at.tzinfo is not None:
        return published_at.astimezone(NEWS_TIMEZONE).replace(tzinfo=None)
    return published_at


def is_recent_feed_date(published_at, max_age_days=None, now=None):
    """Accept dated RSS items in the rolling freshness window, using India time.

    Old articles already stored in the database remain available as history;
    this guard only prevents a feed's stale archive entries being ingested as
    fresh news. Set RSS_MAX_AGE_DAYS to widen/narrow the feed lookback.
    """
    if not published_at:
        return False
    try:
        max_age_days = int(max_age_days if max_age_days is not None else os.getenv("RSS_MAX_AGE_DAYS", "7"))
        current = now or datetime.now(NEWS_TIMEZONE)
        if current.tzinfo is None:
            current = current.replace(tzinfo=NEWS_TIMEZONE)
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=NEWS_TIMEZONE)
        published_date = published_at.astimezone(NEWS_TIMEZONE).date()
        age = (current.astimezone(NEWS_TIMEZONE).date() - published_date).days
        return 0 <= age <= max_age_days
    except (TypeError, ValueError, OverflowError):
        return False


def clean_html(raw_html):
    if not raw_html: return ""
    raw_html = html.unescape(str(raw_html))
    if "<" not in raw_html or ">" not in raw_html:
        text = raw_html.strip()
    else:
        soup = BeautifulSoup(raw_html, "html.parser")
        text = soup.get_text(separator="\n").strip()
    return text.strip()


def clean_article_title(title):
    """Return a plain, single-line title with markup and control characters removed."""
    title = clean_html(title)
    return re.sub(r"\s+", " ", title).strip()


def article_titles_match(expected, candidate):
    """Conservatively detect when a fetched page is for a different headline."""
    expected = clean_article_title(expected).casefold()
    candidate = clean_article_title(candidate).casefold()
    if not expected or not candidate:
        return True
    expected_tokens = re.findall(r"[\w\u0B80-\u0BFF]+", expected, flags=re.UNICODE)
    candidate_tokens = set(re.findall(r"[\w\u0B80-\u0BFF]+", candidate, flags=re.UNICODE))
    if not expected_tokens:
        return True
    shared = sum(token in candidate_tokens for token in expected_tokens)
    token_coverage = shared / len(expected_tokens)
    sequence_score = SequenceMatcher(None, expected, candidate).ratio()
    return sequence_score >= 0.48 or (len(expected_tokens) >= 3 and token_coverage >= 0.55)


def article_page_matches_title(page_html, expected_title):
    """Check publisher metadata/headlines before trusting extracted page data."""
    if not page_html:
        return True
    soup = BeautifulSoup(page_html, "html.parser")
    candidates = []
    for key in ("og:title", "twitter:title"):
        node = soup.find("meta", property=key) or soup.find("meta", attrs={"name": key})
        if node and node.get("content"):
            candidates.append(node["content"])
    for node in soup.select("h1")[:3]:
        text = node.get_text(" ", strip=True)
        if text:
            candidates.append(text)
    if soup.title and soup.title.get_text(strip=True):
        candidates.append(soup.title.get_text(" ", strip=True))
    if not candidates:
        return True
    return any(article_titles_match(expected_title, candidate) for candidate in candidates)


def clean_article_body(body, title="", language=None):
    """Clean extracted article text and remove a repeated title at the start."""
    body = deep_clean_text(body)
    if not body:
        return ""

    lines = [re.sub(r"\s+", " ", line).strip() for line in body.splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    if lines:
        # Some wire headlines/taxonomy labels are prepended to the article by
        # the source template (e.g. "- Rape:"). They are metadata, not prose.
        lines[0] = re.sub(
            r"(?i)^\s*[-–—]?\s*(?:rape|crime|politics|sports|business|update|report)\s*:\s*",
            "",
            lines[0],
        ).strip()
        if not lines[0]:
            lines.pop(0)
    token_pattern = re.compile(r"[\w\u0B80-\u0BFF]+", flags=re.UNICODE)
    title_tokens = [match.group(0).casefold() for match in token_pattern.finditer(title or "")]
    while lines and title_tokens:
        first_matches = list(token_pattern.finditer(lines[0]))
        first_tokens = [match.group(0).casefold() for match in first_matches]
        prefix_tokens = first_tokens[:len(title_tokens)]
        prefix_score = SequenceMatcher(None, " ".join(title_tokens), " ".join(prefix_tokens)).ratio()
        exact = prefix_tokens == title_tokens
        if exact or (len(title_tokens) >= 3 and prefix_score >= 0.84):
            if len(first_tokens) > len(title_tokens):
                remainder = lines[0][first_matches[len(title_tokens) - 1].end():].lstrip(" \t:|–—-.,")
                if remainder:
                    lines[0] = remainder
                    break
            lines.pop(0)
            while lines and not lines[0]:
                lines.pop(0)
        else:
            break
    body = "\n".join(lines).strip()
    if language not in {"en", "ta"}:
        language = detect_language(body)
        if language == "mixed":
            tamil_chars = len(re.findall(r"[\u0B80-\u0BFF]", body))
            latin_chars = len(re.findall(r"[A-Za-z]", body))
            language = "ta" if tamil_chars > latin_chars else "en"
    body = filter_language_sentences(body, language)
    body = re.sub(r"\s+", " ", body).strip()
    # Trafilatura occasionally retains an outlet's literal teaser marker at the
    # end of an otherwise complete article. Keep the article text, not the UI
    # prompt that invites readers to expand it.
    body = re.sub(r"(?:\s*\.{3}|\s*…)+\s*$", "", body).strip()
    # Normalize common Indian-rupee spellings without changing the amount.
    body = re.sub(r"(?i)\bRs\.?\s*(?=\d)", "Rs. ", body)
    # Trafilatura and RSS snippets sometimes start with separators or stray
    # punctuation left behind by a removed dateline/headline. Keep the first
    # actual letter/number (including Tamil) as the beginning of the article.
    body = re.sub(r"^[\s\W_]+", "", body, flags=re.UNICODE).strip()
    return normalize_political_parties(body, language)


def format_clean_article(title, body):
    """Encode the required {title: content} shape as valid JSON."""
    return json.dumps({clean_article_title(title): body}, ensure_ascii=False, separators=(",", ":"))


def build_article_description(description, body, title="", max_length=300):
    """Keep the supplied description, or derive a short lead from the article."""
    description = clean_html(description)
    if description:
        return description
    body = clean_article_body(body, title)
    if not body:
        return ""
    lead = re.split(r"(?<=[.!?।])\s+", body, maxsplit=1)[0].strip()
    if len(lead) > max_length:
        lead = lead[:max_length].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return lead


def parse_clean_article(value, fallback_title=""):
    """Read the canonical {title: body} JSON while accepting legacy plain text."""
    if not value:
        return clean_article_title(fallback_title), ""
    try:
        payload = json.loads(value) if isinstance(value, str) else value
        if isinstance(payload, dict) and payload:
            title, body = next(iter(payload.items()))
            return clean_article_title(title or fallback_title), str(body or "").strip()
    except (ValueError, TypeError):
        pass
    return clean_article_title(fallback_title), str(value).strip()


PARTY_TAMIL = {
    "DMK": "திமுக", "AIADMK": "அதிமுக", "BJP": "பாஜக", "TVK": "தவெக",
    "PMK": "பாமக", "DMDK": "தேமுதிக", "NTK": "நாதக", "VCK": "விசிக",
    "MDMK": "மதிமுக", "CPI": "சிபிஐ", "CPM": "சிபிஎம்", "AMMK": "அமமுக",
    "INC": "காங்கிரஸ்", "AAP": "ஆம் ஆத்மி", "TMC": "தமாகா", "MNM": "மநீம",
}


def normalize_political_parties(text, language="en"):
    """Normalize party aliases without converting a Tamil article into English."""
    if not text:
        return ""
    en_to_ta = {
        "DMK": (r"(?i)\bD\.?M\.?K\.?\b", r"(?i)திராவிட\s*முன்னேற்றக்\s*கழகம்"),
        "AIADMK": (r"(?i)\bA\.?I\.?A\.?D\.?M\.?K\.?\b", r"(?i)அண்ணா\s*திராவிட\s*முன்னேற்றக்\s*கழகம்"),
        "BJP": (r"(?i)\bB\.?J\.?P\.?\b", r"(?i)பாரதிய\s*ஜனதா\s*கட்சி"),
        "TVK": (r"(?i)\bT\.?V\.?K\.?\b", r"(?i)தமிழக\s*வெற்றிக்\s*கழகம்"),
        "PMK": (r"(?i)\bP\.?M\.?K\.?\b",), "DMDK": (r"(?i)\bD\.?M\.?D\.?K\.?\b",),
        "NTK": (r"(?i)\bN\.?T\.?K\.?\b",), "VCK": (r"(?i)\bV\.?C\.?K\.?\b",),
        "MDMK": (r"(?i)\bM\.?D\.?M\.?K\.?\b",), "CPI": (r"(?i)\bC\.?P\.?I\.?\b",),
        "CPM": (r"(?i)\bC\.?P\.?M\.?\b",), "AMMK": (r"(?i)\bA\.?M\.?M\.?K\.?\b",),
        "INC": (r"(?i)\bI\.?N\.?C\.?\b",), "AAP": (r"(?i)\bA\.?A\.?P\.?\b",),
        "TMC": (r"(?i)\bT\.?M\.?C\.?\b",), "MNM": (r"(?i)\bM\.?N\.?M\.?\b",),
    }
    tamil_aliases = {
        "DMK": r"(?i)தி\.?மு\.?க", "AIADMK": r"(?i)அ\.?தி\.?மு\.?க",
        "BJP": r"(?i)பா\.?ஜ\.?க", "TVK": r"(?i)த\.?வெ\.?க",
        "PMK": r"(?i)பா\.?ம\.?க", "DMDK": r"(?i)தே\.?மு\.?தி\.?க",
        "NTK": r"(?i)நா\.?த\.?க", "VCK": r"(?i)வி\.?சி\.?க",
        "MDMK": r"(?i)ம\.?தி\.?மு\.?க", "CPI": r"(?i)சி\.?பி\.?ஐ", "CPM": r"(?i)சி\.?பி\.?எம்",
    }
    if language == "ta":
        for abbr, patterns in en_to_ta.items():
            for pattern in patterns:
                text = re.sub(pattern, PARTY_TAMIL[abbr], text)
        for abbr, pattern in {
            "DMK": tamil_aliases["DMK"], "AIADMK": tamil_aliases["AIADMK"],
            "BJP": tamil_aliases["BJP"], "TVK": tamil_aliases["TVK"],
            "PMK": tamil_aliases["PMK"], "DMDK": tamil_aliases["DMDK"],
            "NTK": tamil_aliases["NTK"], "VCK": tamil_aliases["VCK"],
            "MDMK": tamil_aliases["MDMK"], "CPI": tamil_aliases["CPI"], "CPM": tamil_aliases["CPM"],
        }.items():
            text = re.sub(pattern, PARTY_TAMIL[abbr], text)
        return text
    for abbr, pattern in tamil_aliases.items():
        text = re.sub(pattern, abbr, text)
    return text


def filter_language_sentences(text, language):
    """Drop sentences written predominantly in the other script, not Latin names/numbers."""
    if language not in {"ta", "en"}:
        return text
    kept = []
    for sentence in re.split(r"(?<=[.!?।])\s+|\n+", text or ""):
        tamil = len(re.findall(r"[\u0B80-\u0BFF]", sentence))
        latin = len(re.findall(r"[A-Za-z]", sentence))
        if language == "ta" and tamil == 0 and latin >= 12:
            continue
        if language == "en" and tamil > 0 and tamil > latin:
            continue
        if sentence.strip():
            kept.append(sentence.strip())
    return " ".join(kept)
JUNK_PATTERNS = [
    # Subscription / Paywall prompts
    r"(?i)you are logged in[\s\S]{0,50}loading",
    r"(?i)you don't have any active subscription",
    r"(?i)subscribe\s*now",
    r"(?i)subscribed with another email\?.*?login with that one",
    r"(?i)your active subscription\(s\)",
    r"(?i)account subscription benefits.*?unlock these with subscription",
    r"(?i)products you've access to",
    r"(?i)additional subscription benefits",
    r"(?i)account settings",
    r"(?i)need help with your subscription\?",
    r"(?i)premium\s*stories?,?\s*editorials?,?\s*opinions?",
    r"(?i)already\s*a\s*subscriber\?.*?sign\s*in",
    r"(?i)start\s*your\s*\d+[\s-]*day\s*free\s*trial",
    r"(?i)get\s*unlimited\s*access",
    r"(?i)sign\s*up\s*for\s*newsletter",
    r"(?i)download\s*(the|our)?\s*app",
    # Cookie / privacy banners
    r"(?i)we\s*use\s*cookies.*?accept",
    r"(?i)by\s*continuing.*?you\s*agree\s*to\s*our",
    r"(?i)privacy\s*policy\s*\|\s*terms\s*(of\s*use|and\s*conditions)",
    # Social media / sharing CTAs
    r"(?i)share\s*(this|on)\s*(facebook|twitter|whatsapp|instagram|x\.com)",
    r"(?i)follow\s*us\s*on\s*(facebook|twitter|instagram|youtube|x\.com)",
    r"(?i)(like|comment|share|bookmark)\s*\d*\s*$",
    # Navigation / breadcrumb
    r"(?i)^\s*(home|news|india|world|sports|entertainment|business|opinion|lifestyle)\s*[>|/]\s*",
    r"(?i)^\s*-?\s*(published|reported|authored|written)\s*by\s*:?.*$",
    r"(?i)^\s*published\s*:?\s*$",
    r"(?i)^\s*updated\s*:?\s*$",
    r"(?i)^\s*updated\s*:?.*?(am|pm)\s*ist.*$",
    r"(?i)\d+\s*mins?\s*read",
    r"(?i)^\s*read\s*more\s*:?\s*$",
    r"(?i)^\s*also\s*read\s*:?\s*$",
    r"(?i)^\s*related\s*(news|stories|articles)\s*:?\s*$",
    # Ads / promotional
    r"(?i)^\s*advertisement\s*$",
    r"(?i)^\s*sponsored\s*$",
    r"(?i)^\s*promoted\s*content\s*$",
    r"(?i)Story continues below this ad",
    r"(?i)Loading recommendations",
    r"(?i)pic\.twitter\.com/\w+",
    r"(?i)IE Online Media Services PVT LTD",
    r"(?i)^PHOTO\s*:.*",
    r"- இது, க்காக கலெக்டிவ் நியூஸ்ரூம் வெளியீடு",
    r"மேலும் அறிக",
    r"குறுங்காணொளிகள்",
    r"குறுங்காணொளிகள் முடிவு",
    r"(?i).*Pvt Ltd\.?$",
    r"(?i)The Indian Express.*",
    r"(?i)-picture:\d+/?",
    r"(?i)Published by:\w+",
    r"(?i).*கோப்புப்\s*படம்.*",
    r"(?i)is a Special Correspondent",

    # Subscribe / Membership / Newsletter
    r"(?i)Sign in to unlock member-only benefits",
    r"(?i)Access \d+ free stories every month",
    r"(?i)Save stories to read later",
    r"(?i)Access to comment on every story",
    r"(?i)Sign-up/manage your newsletter subscriptions with a single click",
    r"(?i)Get notified by email for early access to discounts & offers",
    
    # Device limit errors
    r"(?i)\$\{ ind \+ 1 \} \$\{ device \}Last active - \$\{ la \}",
    r"(?i)Looks like you are already logged in from more than \d+ devices",
    r"(?i)To continue logging in, remove at least one device",
    
    # Random headers / comment rules
    r"(?i)Live NowStates CitiesChildren",
    r"(?i)FoodEnvironment Real Estate Agriculture",
    r"(?i)Comments have to be in English, and in full",
    r"(?i)Contact us at instagram",
    r"(?i)Follow us on facebook",
    r"(?i)follow us on instagram",

    # Tamil junk equivalents
    r"(?i)மேலும்\s*படிக்க",
    r"(?i)செய்திகளை\s*உடனுக்குடன்\s*படிக்க",
    r"(?i)ஆப்\s*டவுன்லோடு\s*செய்யுங்கள்",
    r"(?i)Follow\s*Us\s*On\s*Social\s*Media",
    r"(?i)தினமணி\s*செய்திமடலைப்\s*பெற",
    r"(?i)வாட்ஸ்ஆப்\s*சேனலில்\s*பின்தொடர",
    r"(?i)தினமணியைத்\s*தொடர",
    r"(?i)உடனுக்குடன்\s*செய்திகளை\s*அறிய.*App\s*பதிவிறக்கம்\s*செய்யவும்",
    r"(?i)^\s*for\s*more\s*updates?.*$",
    r"(?i)^\s*watch\s*live.*$",
    r"(?i)^\s*follow\s*us.*$",
    r"(?i)மேலும்\s*செய்திகளுக்கு",
    r"(?i)மேலும்\s*விவரங்களுக்கு",
    r"(?i)நேரலையில்\s*காண",
    r"(?i)நேரலை\s*டிவி",
    r"(?i)எங்களை\s*(பின்)?தொடர",
]
JUNK_RE = [re.compile(p) for p in JUNK_PATTERNS]

# Lines shorter than this are likely navigation fragments, not article prose
MIN_LINE_LENGTH = 15



NON_LOCATION_PREFIXES = {
    'note', 'update', 'warning', 'report', 'breaking', 'alert', 'live', 'opinion',
    'editorial', 'analysis', 'watch', 'photos', 'video', 'special report',
    'முக்கிய செய்தி', 'செய்தி', 'நேரலை', 'சிறப்பு செய்தி', 'அறிவிப்பு', 'எச்சரிக்கை'
}

def extract_dateline_location(text):
    """
    Extracts dateline location prefix (e.g. 'Chennai: ', 'NEW DELHI - ', 'சென்னை | ', 'புதுடெல்லி:')
    from the beginning of the text, returning (location, cleaned_text).
    Removes the location prefix from cleaned_text.
    """
    if not text:
        return '', ''
    footer = re.search(r"(?i)\bIn\s+([A-Z][A-Za-z .'-]{1,35})\s*\|\s*(?:LPG|CNG)\s+Price[^\n]*$", text)
    footer_location = footer.group(1).strip() if footer else ""
    if footer:
        text = text[:footer.start()].rstrip()
    label = re.match(r"(?i)^\s*(?:[-–—]\s*)?(?:location|rape|crime|politics|sports|business|update|report)\s*:\s*", text)
    if label:
        text = text[label.end():]
    pattern = r'^\s*(?:\[(?P<loc1>[^\]]+)\]|(?P<loc2>[a-zA-Z\u0B80-\u0BFF][a-zA-Z\u0B80-\u0BFF\s\/,&.-]{1,45}))\s*(?:\([^\)]+\))?\s*(?::-|\:|\||\-|\u2013|\u2014)\s*'
    match = re.match(pattern, text)
    if match:
        raw_loc = (match.group('loc1') or match.group('loc2') or '').strip()
        cleaned_text = text[match.end():].strip()
        if raw_loc.lower() in NON_LOCATION_PREFIXES or raw_loc.lower() in {"rape", "crime", "politics", "business", "sports"}:
            return footer_location, cleaned_text
        return raw_loc, cleaned_text
    return footer_location, text.strip()

def deep_clean_text(text):
    """
    Aggressively strips paywall banners, subscription prompts,
    navigation breadcrumbs, social media CTAs, cookie notices,
    and other boilerplate from extracted article text.
    
    Strategy:
      1. Full-text regex pass to strip inline junk (paywall fragments glued to article text).
      2. Split into lines.
      3. Drop any line matching a known junk pattern.
      4. Drop very short orphan lines (navigation crumbs).
      5. Collapse excessive blank lines.
      6. Return only the actual article prose.
    """
    if not text:
        return ""
        
    # Strip any stray HTML tags like <p> that trafilatura/BeautifulSoup missed
    text = re.sub(r'<[^>]+>', ' ', text)

    # ── Pass 1: Full-text inline junk removal ──
    # Trafilatura sometimes glues paywall/subscription text directly
    # to the end of a paragraph without any newline separator.
    INLINE_JUNK = [
        r"(?i)From live updates to exclusive reports to in-depth explainers.*",
        r"(?i)Disclaimer: Comments reflect.*",
        r"(?i)Disclaimer:\s*This story has been[\s\S]*$",
        r"(?i)Please keep discussions respectful and constructive.*",
        r"(?i)Abusive, defamatory, or illegal comments will be removed.*",
        r"(?i)may disable any comment at its discretion.*",
        r"(?i)By posting, you agree to our Terms of Use and Privacy Policy.*",
        r"(?i)Comments reflect users views, not s.*",
        r"(?i)Get Current Updates on India News,\s*Entertainment News,\s*Cricket News\s+along with Latest News and Web Stories from India and around the world\.?\s*$",
        r"(?i)Published from a wire agency feed without modifications to the text\.?\s*Only the headline has been changed\.?",
        r"(?i)Get Latest real-time updates[\s\S]*$",
        r"(?i)Oops!?\s*Looks like you have exceeded the limit to bookmark the image[\s\S]*$",
        r"(?i)Wait for it\s*[.…]*",
        r"(?i)Awards and Recognition\s*:[\s\S]*$",
        r"(?i)\b[A-Z][A-Za-z'’\-]*(?:\s+[A-Z][A-Za-z'’\-]*){1,4}\s+is a journalist who reports and writes on\b[\s\S]*$",
        r"(?i)\bIn\s+[A-Z][A-Za-z .'-]{1,35}\s*\|\s*(?:LPG|CNG)\s+Price\b[\s\S]*$",

        r"You are logged in[\s\S]{0,200}?Loading\.{0,3}",
        r"You don't have any [Aa]ctive [Ss]ubscription[\s\S]{0,500}?[Nn]eed help with your subscription\??",
        r"Subscribed with another email\?[\s\S]{0,200}?[Ll]ogin with that one\.?",
        r"Your active subscription\(s\)[\s\S]{0,300}?[Aa]ccount [Ss]ettings",
        r"Account subscription benefits[\s\S]{0,300}?[Uu]nlock these with [Ss]ubscription",
        r"Products you've access to[\s\S]{0,200}?[Aa]dditional [Ss]ubscription [Bb]enefits",
        r"Premium [Ss]tories,?\s*[Ee]ditorials,?\s*[Oo]pinions[\s\S]{0,100}?[Uu]nlock",
        r"Already a subscriber\?[\s\S]{0,100}?[Ss]ign [Ii]n",
        r"Start your \d+[\s-]*day free trial[\s\S]{0,100}",
        r"(?i)Published[\s\-]*[\w\s,:]+[AP]M IST",
        r"(?i)Updated[\s\-:]*[\w\s,:]+[AP]M IST",
        r"(?i)\d+\s*mins?\s*read.*?updated.*?ist",
        r"(?i)Read\s*more\s*:?",
        r"Read Comments",
        r"(?i)LIVE\s*TV",
        r"(?i)Watch\s*LIVE.*",
        r"(?i)For\s*more\s*updates?",
        r"(?i)Subscribe\s*to.*",
        r"(?i)You\s*Can\s*Also\s*Check\s*:.*?(LPG|CNG)\s*Price.*?",
        r"(?i)You\s*Can\s*Also\s*Check\s*:.*$",
        r"(?i)(பதிவு|மாற்றம்)\s*செய்யப்பட்டது.*",
        r"(?i)Follow\s*us\s*on.*",
        r"(?i)பின்னூட்டத்தில்\s*வெளியாகும்\s*கருத்துகளுக்கு\s*அவற்றைப்\s*பதிவிடுவோரே\s*முழுப்\s*பொறுப்பு[^\n]*",
        r"(?i)We\s*have\s*migrated\s*to\s*a\s*new\s*commenting\s*platform[^\n]*",
        r"(?i)Loading\s*stories.*",
        r"(?i)Recommended\s*stories[^\n]*",
        r"(?i)Recommended\s*for\s*you[^\n]*",
        r"(?i)Got\s*Question\s*about\s*the\s*News\?[^\n]*",
    ]
    for pattern in INLINE_JUNK:
        text = re.sub(pattern, "", text)

    # ── Pass 2: Line-by-line cleaning ──
    lines = text.split("\n")
    cleaned = []

    for line in lines:
        stripped = line.strip()

        # Skip empty lines (we'll normalize later)
        if not stripped:
            cleaned.append("")
            continue

        # Skip if it matches any junk pattern
        if any(pat.search(stripped) for pat in JUNK_RE):
            continue

        # Skip very short orphan lines that are likely UI elements
        # (but keep them if they look like Tamil script — shorter words are common)
        has_tamil = bool(re.search(r'[\u0B80-\u0BFF]', stripped))
        if len(stripped) < MIN_LINE_LENGTH and not has_tamil:
            # Allow short lines only if they end with sentence punctuation
            if not re.search(r'[.!?\u0964]$', stripped):
                continue

        cleaned.append(stripped)

    # Collapse 3+ blank lines into one
    result = "\n".join(cleaned)
    result = re.sub(r'\n{3,}', '\n\n', result)
    
    # Retain source names and original party forms; language-aware party normalization follows.
    # ── Pass 4: UTF-8 Enforcement & Emoji/Symbol Removal ──
    # Keep only ASCII (English + punctuation) and Tamil Unicode block.
    # This automatically strips emojis and weird symbols.
    # ASCII: \x00-\x7F
    # Tamil: \u0B80-\u0BFF
    # Note: re.sub will remove anything NOT in this character class
    result = re.sub(r'[^\x00-\x7F\u0B80-\u0BFF\s]', '', result)
    
    # Ensure strict UTF-8 encoding (removes any malformed bytes)
    result = result.encode('utf-8', 'ignore').decode('utf-8')
    
    
    # Strip dateline prefixes like "Chennai | " or "சென்னை: " from the VERY BEGINNING of the text
    
    return result.strip()


def detect_language(text):
    """
    Auto-detect whether an article is Tamil, English, or mixed
    by checking the ratio of Tamil Unicode characters.
    This replaces the old outlet-level language inheritance so
    all articles sit in one unified timeline.
    """
    if not text:
        return "unknown"
    # Count Tamil script characters (Unicode block U+0B80–U+0BFF)
    tamil_chars = len(re.findall(r'[\u0B80-\u0BFF]', text))
    alpha_chars = len(re.findall(r'[a-zA-Z\u0B80-\u0BFF]', text))
    if alpha_chars == 0:
        return "unknown"
    ratio = tamil_chars / alpha_chars
    if ratio >= 0.35:
        return "ta"
    return "en"

def get_canonical_url(url):
    """Removes tracking parameters from URLs to prevent duplicate articles. 
    Also follows Google News redirects."""
    if not url: return ""
    
    # Follow Google News redirects to get the actual article URL
    if "news.google.com/rss/articles/" in url:
        try:
            resp = requests.head(url, allow_redirects=True, timeout=5)
            url = resp.url
        except Exception:
            pass

    parsed = urllib.parse.urlparse(url)
    clean_query = urllib.parse.urlencode([
        (k, v) for k, v in urllib.parse.parse_qsl(parsed.query)
        if not k.startswith('utm_') and not k.startswith('fbclid')
    ])
    return urllib.parse.urlunparse(parsed._replace(query=clean_query))


# ─── Skip Keywords ───
# Keywords to filter out unwanted topics (entertainment, astrology, ayurveda, etc.)
SKIP_KEYWORDS = [
    # English Entertainment & Gossip
    'cinema', 'actor', 'actress', 'movie', 'film', 'box office', 'review', 'trailer',
    'bollywood', 'kollywood', 'tollywood', 'hollywood', 'celebrity', 'gossip', 'tv show',
    'bigg boss', 'big boss', '/photogallery/', '/explanations/',
    '/videos/', '/video/', '/shorts/', '/photos/', '/photo/', '/gallery/', '/web-stories/', '/podcasts/', '/podcast/',
    
    # Tamil Entertainment & Gossip
    'சினிமா', 'நடிகர்', 'நடிகை', 'படம்', 'திரைப்படம்', 'பாக்ஸ் ஆபிஸ்', 'விமர்சனம்', 'ட்ரைலர்', 'டிரெய்லர்',
    'பாலிவுட்', 'கோலிவுட்', 'டாலிவுட்', 'ஹாலிவுட்', 'பிரபலம்', 'கிசுகிசு', 'டிவி ஷோ',
    'சீரியல்', 'விஜய் டிவி', 'சன் டிவி', 'ஜீ தமிழ்', 'பிக்பாஸ்', 'வைரல்',
    'பொழுதுபோக்கு', 'கவர்ச்சி', 'படுக்கையறை', 'உறவு',

    # English Astrology & Remedies
    'astrology', 'horoscope', 'zodiac', 'vastu', 'ayurveda', 'ayurvedic', 'remedy', 'remedies',
    
    # Tamil Astrology & Remedies
    'ஜோதிடம்', 'ராசிபலன்', 'ராசி', 'வாஸ்து', 'ஆயுர்வேதம்', 'பரிகாரம்', 'ஜாதகம்', 'சனிப்பெயர்ச்சி', 'குருப்பெயர்ச்சி',

    # English Sensationalism & Rumors
    'rumor', 'rumours', 'fake news', 'viral video', 'bizarre', 'shocking', 'scandal',
    
    # Tamil Sensationalism & Rumors
    'வதந்தி', 'போலி செய்தி', 'வைரல் வீடியோ', 'அதிர்ச்சி', 'சர்ச்சை', 'ஸ்கேண்டல்', 'பகீர்',

    # English Lifestyle & Miscellany
    'lottery', 'kerala lottery', 'win news', 'entertainment', 'gaming', 'video game', 'esports',
    'tips', 'tricks', 'recipe', 'food recipe', 'dish', 'ingredient', 'cook', 'baking',
    'health tips', 'lifestyle', 'wellness', 'weight loss', 'home remedies', 'fitness',
    '/lifestyle/', '/health/', '/wellness/', '/fitness/', '/cooking/', '/recipe/',
    'recruitment', 'hiring', 'job opening', 'vacancy',
    
    # Tamil Lifestyle & Miscellany
    'லாட்டரி', 'கேரளா லாட்டரி', 'கேமிங்', 'வீடியோ கேம்',
    'டிப்ஸ்', 'குறிப்புகள்', 'ரெசிபி', 'சமையல்', 'உணவு', 'சாப்பாடு', 'ருசியான', 'சுவையான', 'சிறப்பம்சங்கள்',
    'ஆரோக்கியக் குறிப்புகள்', 'உடல்நலக் குறிப்புகள்', 'லைஃப்ஸ்டைல்', 'வாழ்க்கை முறை', 'டயட்', 'எடை குறைப்பு', 'நல்வாழ்வு',
    'நியமனம்', 'வேலைவாய்ப்பு',

    # English Tech & E-commerce
    'unboxing', 'specifications', 'price in india', 'smartphone review', 'phone review', 'gadget review', 'hands-on', 'hands on', 'first look',
    'offer', 'discount', 'amazon sale', 'flipkart sale', 'recharge plan', 'data plan', 'telecom plan', 'jio plan', 'airtel plan', 'vi plan', 'broadband plan',
    'mobile', 'smartphone', 'smartphones', 'smart tv', 'prepaid', 'postpaid', 'validity', 'bsnl', 'vodafone', 'idea', 'jio', 'airtel', 'vi', 'launch',
    
    # Tamil Tech & E-commerce
    'அன்பாக்சிங்', 'இந்திய விலை', 'ஸ்மார்ட்போன் விமர்சனம்', 'போன் விமர்சனம்',
    'ஆஃபர்', 'சலுகை', 'தள்ளுபடி', 'அமேசான் சேல்', 'பிளிப்கார்ட் சேல்', 'ரீசார்ஜ்', 'டேட்டா திட்டம்', 'டெலிகாம்', 'ஜியோ திட்டம்', 'ஏர்டெல் திட்டம்', 'வி திட்டம்', 'பிராட்பேண்ட்',
    'மொபைல்', 'ஸ்மார்ட்போன்', 'ஸ்மார்ட் டிவி', 'ப்ரீபெய்ட்', 'போஸ்ட்பெய்ட்', 'வேலிடிட்டி', 'பிஎஸ்என்எல்', 'வோடபோன்', 'ஐடியா', 'ஜியோ', 'ஏர்டெல்', 'அறிமுகம்'
]

FESTIVAL_KEYWORDS = [
    'festival', 'diwali', 'deepavali', 'pongal', 'navratri', 'pooja', 'pujan',
    'பண்டிகை', 'தீபாவளி', 'பொங்கல்', 'நவராத்திரி', 'பூஜை', 'திருவிழா', 'விநாயகர்', 'சதுர்த்தி', 'கிருஷ்ண', 'ஜெயந்தி'
]

BREAKING_NEWS_KEYWORDS = ['breaking', 'flash', 'alert', 'முக்கிய செய்தி', 'பிரேக்கிங்']


# ─── Topic Classification & Outlet Cleaners ───

TOPIC_KEYWORDS = {
    "politics": ["election", "parliament", "minister", "government", "bjp", "dmk", "congress", "aiadmk", "tvk", "pmk", "vck", "ntk", "தேர்தல்", "நாடாளுமன்றம்", "முதல்வர்", "அமைச்சர்", "அரசியல்", "சட்டமன்றம்", "எம்.எல்.ஏ"],
    "world_news": ["international", "global", "united states", "u.s.", "china", "ukraine", "nato", "russia", "israel", "gaza", "united nations", "சர்வதேச", "உலக", "அமெரிக்கா", "சீனா", "ரஷ்யா", "இலங்கை"],
    "economy": ["economy", "gdp", "inflation", "rbi", "stock market", "rupee", "business", "company", "கடன்", "பொருளாதாரம்", "பணவீக்கம்", "பங்குச்சந்தை", "ரூபாய்", "வர்த்தகம்", "பட்ஜெட்"],
    "crime_law": ["murder", "arrest", "police", "court", "fir", "cbi", "supreme court", "high court", "கொலை", "கைது", "காவல்", "நீதிமன்றம்", "வழக்கு", "தீர்ப்பு", "சிபிஐ", "போலீஸ்"],
    "science_health": ["research", "vaccine", "hospital", "climate", "space", "isro", "nasa", "health", "disease", "ஆராய்ச்சி", "தடுப்பூசி", "மருத்துவம்", "காலநிலை", "சுகாதாரம்", "விண்வெளி", "இஸ்ரோ", "மருத்துவமனை"],
    "sports": ["cricket", "ipl", "match", "tournament", "champion", "olympics", "tennis", "football", "கிரிக்கெட்", "போட்டி", "வெற்றி", "ஐபிஎல்", "விளையாட்டு", "ஒலிம்பிக்"],
    "education": ["school", "university", "exam", "neet", "syllabus", "students", "college", "பள்ளி", "பல்கலைக்கழகம்", "தேர்வு", "நீட்", "மாணவர்கள்", "கல்லூரி", "கல்வி"],
    "technology": ["technology", "artificial intelligence", "artificial intelligence", "ai", "software", "cyber", "smartphone", "டிஜிட்டல்", "தொழில்நுட்பம்", "செயற்கை நுண்ணறிவு"],
    "local_news": ["vellore", "chennai", "coimbatore", "madurai", "salem", "tiruchirappalli", "tirunelveli", "காஞ்சிபுரம்", "வேலூர்", "சென்னை", "மதுரை", "கோவை", "சேலம்", "தமிழ்நாடு"],
}

def classify_topic(title, text, outlet_slug="", location=""):
    """Classify from headline and article prose; use token boundaries for English."""
    title_text = str(title or "").casefold()
    body_text = str(text or "")[:1200].casefold()
    location_text = str(location or "").casefold()
    scores = {topic: 0 for topic in TOPIC_KEYWORDS}
    for topic, keywords in TOPIC_KEYWORDS.items():
        for keyword in keywords:
            term = keyword.casefold()
            if re.search(r"[a-z]", term):
                pattern = r"(?<![a-z0-9])" + re.escape(term).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
                title_hits = len(re.findall(pattern, title_text))
                body_hits = len(re.findall(pattern, body_text))
                location_hits = len(re.findall(pattern, location_text))
            else:
                title_hits = title_text.count(term)
                body_hits = body_text.count(term)
                location_hits = location_text.count(term)
            scores[topic] += title_hits * (5 if topic == "local_news" else 4) + min(body_hits, 3) + location_hits * 2
    best_score = max(scores.values(), default=0)
    if not best_score:
        return "general"
    # Stable topic ordering breaks ties; headline mentions carry most weight.
    return next(topic for topic, score in scores.items() if score == best_score)


def is_usable_article_body(body, minimum_chars=100, minimum_words=12):
    """Reject extraction debris (empty snippets, one-word bodies, UI fragments)."""
    value = re.sub(r"\s+", " ", str(body or "")).strip()
    words = re.findall(r"[A-Za-z0-9஀-௿]+", value)
    letters = re.findall(r"[A-Za-z஀-௿]", value)
    return len(value) >= minimum_chars and len(words) >= minimum_words and len(letters) >= 60

def clean_times_of_india(title, text):
    title = re.sub(r"^\s*-\s*", "", title)
    text = re.sub(r"^[A-Za-z\s]{3,20}\s*:\s*", "", text)
    text = re.sub(r"(?i)In\s+[A-Za-z]+\s*\|\s*LPG\s+Price.*$", "", text).strip()
    return title, text

def clean_bbc_tamil(title, text):
    # Remove footer
    text = re.sub(r"- இது, க்காக கலெக்டிவ் நியூஸ்ரூம் வெளியீடு[^\n]*", "", text)
    # Remove author header block
    text = re.sub(r"(?im)^-?\s*(எழுதியவர்,|பதவி,|பிரசுரிக்கப்பட்டது|வாசிக்கும் நேரம்:).*?$", "", text)
    return title, text

def clean_dinamani(title, text):
    match = re.search(r'([\u0B80-\u0BFF][\.\?!]?\s*)[^\u0B80-\u0BFF]*$', text)
    if match:
        non_tamil_part = text[match.end(1):]
        if re.search(r'[a-zA-Z]{2,}', non_tamil_part):
            text = text[:match.end(1)].strip()
            
    text = re.sub(r"(?i)-picture:\d+/?", "", text)
    text = re.sub(r"(?i).*கோப்புப்\s*படம்.*", "", text)
    return title, text

def clean_indian_express(title, text):
    text = re.sub(r"(?i)Story continues below this ad", "", text)
    text = re.sub(r"(?i)Loading recommendations", "", text)
    text = re.sub(r"(?i)pic\.twitter\.com/\w+", "", text)
    text = re.sub(r"(?i)IE Online Media Services PVT LTD", "", text)
    text = re.sub(r"(?i).*Pvt Ltd\.?$", "", text)
    text = re.sub(r"(?i).*The Indian Express.*", "", text)
    text = re.sub(r"(?i).*is a Special Correspondent.*", "", text)
    return title, text

def clean_tamil_oneindia(title, text):
    text = re.sub(r"^[A-Za-z\u0B80-\u0BFF\s]{3,20}\s*:\s*", "", text)
    return title, text

def clean_news18(title, text, url=""):
    text = re.sub(r"^[A-Za-z\s]+\s*\|\s*", "", text)
    if text.startswith(title):
        text = text[len(title):].strip()
    text = re.sub(r"^\s*-\s*Published\s*by\s*:\s*[A-Za-z\.]+\s*", "", text, flags=re.IGNORECASE)
    return title, text

def clean_tamil_mykhel(title, text, url=""):
    return title, text

def apply_outlet_cleaners(title, text, outlet_slug, url=""):
    if outlet_slug == "bbc_tamil":
        return clean_bbc_tamil(title, text)
    elif outlet_slug == "times_of_india":
        return clean_times_of_india(title, text)
    elif outlet_slug == "dinamani":
        return clean_dinamani(title, text)
    elif outlet_slug == "indian_express":
        return clean_indian_express(title, text)
    elif outlet_slug == "tamil_one_india":
        return clean_tamil_oneindia(title, text)
    elif outlet_slug in ["news18_india", "news18_tamil_nadu"]:
        return clean_news18(title, text, url)
    elif outlet_slug == "tamil_mykhel":
        return clean_tamil_mykhel(title, text, url)
    return title, text
