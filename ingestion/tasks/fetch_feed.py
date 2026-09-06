import csv
import os
import re
import hashlib
import urllib.parse
import requests
from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser
import trafilatura
from bs4 import BeautifulSoup

from main import celery_app
from models.database import SessionLocal, RssFeed, FeedRun, Article

def clean_html(raw_html):
    """Removes HTML tags and normalizes whitespace."""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator="\n").strip()
    # Strip dateline prefixes like "Chennai | " or "சென்னை: " from the VERY BEGINNING of the text
    text = re.sub(r"^(?:[A-Za-z\s]{3,20}|[\u0B80-\u0BFF\s]{3,20})\s*(?:\||:-|:)\s*", "", text).strip()
    return text


# ─── Paywall / Subscription / Navigation Junk Patterns ───
# These regex patterns match common non-article boilerplate that
# leaks through Trafilatura and RSS content extraction.
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
        r"(?i)You\s*Can\s*Also\s*Check\s*:.*?(LPG|CNG)\s*Price.*?",
        r"(?i)(பதிவு|மாற்றம்)\s*செய்யப்பட்டது.*",
        r"(?i)Follow\s*us\s*on.*",
        r"(?i)பின்னூட்டத்தில்\s*வெளியாகும்\s*கருத்துகளுக்கு\s*அவற்றைப்\s*பதிவிடுவோரே\s*முழுப்\s*பொறுப்பு[\s\S]*",
        r"(?i)We\s*have\s*migrated\s*to\s*a\s*new\s*commenting\s*platform[\s\S]*",
        r"(?i)Loading\s*stories.*",
        r"(?i)Recommended\s*stories[\s\S]*",
        r"(?i)Recommended\s*for\s*you[\s\S]*",
        r"(?i)Got\s*Question\s*about\s*the\s*News\?[\s\S]*",
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
    
    # ── Pass 2.5: News Outlet Anonymization ──
    # Strip common news outlet names from the text to prevent bias in summarization/clustering
    OUTLET_NAMES = [
        r"(?i)\b(the\s*hindu|times\s*of\s*india|indian\s*express|ndtv|news18|republic\s*tv|republic|bbc|vikatan|asianet\s*news|oneindia|dinamani|gizbot|mykhel)\b",
        r"(?i)\b(பிபிசி|விகடன்|நியூஸ்18|தினமணி|ஏசியாநெட்|தி\s*இந்து|என்டிடிவி)\b"
    ]
    for outlet_pat in OUTLET_NAMES:
        result = re.sub(outlet_pat, "", result)
    
    # ── Pass 3: Political Entity Normalization ──
    # Standardize Tamil abbreviations so the multilingual embedding model
    # perfectly aligns Tamil and English articles about the same party.
    PARTY_MAP = {
        r'(?i)\bதி\.?மு\.?க\b': 'DMK',
        r'(?i)\bஅ\.?தி\.?மு\.?க\b': 'AIADMK',
        r'(?i)\bபா\.?ஜ\.?க\b': 'BJP',
        r'(?i)\bகாங்கிரஸ்\b': 'Congress',
        r'(?i)\bத\.?வெ\.?க\b': 'TVK',
        r'(?i)\bபா\.?ம\.?க\b': 'PMK',
        r'(?i)\bதே\.?மு\.?தி\.?க\b': 'DMDK',
        r'(?i)\bநா\.?த\.?க\b': 'NTK',
        r'(?i)\bவி\.?சி\.?க\b': 'VCK',
        r'(?i)\bம\.?தி\.?மு\.?க\b': 'MDMK',
        r'(?i)\bசி\.?பி\.?ஐ\b': 'CPI',
        r'(?i)\bசி\.?பி\.?எம்\b': 'CPM',
        r'(?i)திராவிட\s*முன்னேற்றக்\s*கழகம்': 'DMK',
        r'(?i)அண்ணா\s*திராவிட\s*முன்னேற்றக்\s*கழகம்': 'AIADMK',
        r'(?i)தமிழக\s*வெற்றிக்\s*கழகம்': 'TVK',
        r'(?i)பாரதிய\s*ஜனதா\s*கட்சி': 'BJP',
        # English variations with and without dots
        r'(?i)\bD\.?M\.?K\.?\b': 'DMK',
        r'(?i)\bA\.?I\.?A\.?D\.?M\.?K\.?\b': 'AIADMK',
        r'(?i)\bB\.?J\.?P\.?\b': 'BJP',
        r'(?i)\bT\.?V\.?K\.?\b': 'TVK',
        r'(?i)\bP\.?M\.?K\.?\b': 'PMK',
        r'(?i)\bD\.?M\.?D\.?K\.?\b': 'DMDK',
        r'(?i)\bN\.?T\.?K\.?\b': 'NTK',
        r'(?i)\bV\.?C\.?K\.?\b': 'VCK',
        r'(?i)\bM\.?D\.?M\.?K\.?\b': 'MDMK',
        r'(?i)\bC\.?P\.?I\.?\b': 'CPI',
        r'(?i)\bC\.?P\.?M\.?\b': 'CPM',
    }
    
    for tamil_pattern, eng_abbr in PARTY_MAP.items():
        # Using regex to catch variations with or without dots (e.g. தி.மு.க or திமுக)
        result = re.sub(tamil_pattern, eng_abbr, result)
        
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
    result = re.sub(r"^(?:[A-Za-z\s]{3,20}|[\u0B80-\u0BFF\s]{3,20})\s*(?:\||:-|:)\s*", "", result.strip())
    
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
    if ratio > 0.6:
        return "ta"
    elif ratio < 0.15:
        return "en"
    else:
        return "mixed"

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

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_single_feed(self, feed_id: int):
    """
    Step 6 Logic:
    1. Records a FeedRun attempt.
    2. Parses the RSS feed.
    3. For each entry, checks if it exists.
    4. Evaluates RSS content length. If too short, uses Trafilatura to scrape the full article.
    5. Saves the resulting Article into PostgreSQL.
    """
    print(f"[Worker] Starting to process feed_id: {feed_id}")
    db = SessionLocal()
    feed = db.query(RssFeed).filter(RssFeed.id == feed_id).first()
    
    if not feed:
        db.close()
        return {"error": "Feed not found"}
        
    feed_run = FeedRun(rss_feed_id=feed.id)
    db.add(feed_run)
    db.commit()
    
    try:
        outlet_slug = feed.outlet.slug
        outlet_orientation = feed.outlet.orientation_bucket
        parsed = feedparser.parse(feed.feed_url)
        feed_run.http_status = getattr(parsed, 'status', 200)
        
        # Check if feed is completely invalid
        if getattr(parsed, 'bozo', False) and not parsed.entries:
            feed_run.error_code = "feed_parse_error"
            feed_run.finished_at = datetime.utcnow()
            feed.consecutive_failures += 1
            db.commit()
            return {"error": "Failed to parse feed"}

        feed_run.entries_seen = len(parsed.entries)
        
        for entry in parsed.entries:
            guid = getattr(entry, 'id', getattr(entry, 'link', ''))
            if not guid:
                continue

            # Keywords to filter out unwanted topics (entertainment, astrology, ayurveda, etc.)
            skip_keywords = [
                'cinema', 'actor', 'actress', 'movie', 'film', 'box office', 'review', 'trailer',
                'bollywood', 'kollywood', 'tollywood', 'hollywood', 'celebrity', 'gossip', 'tv show',
                '/videos/', '/video/', '/shorts/', '/photos/', '/photo/', '/gallery/', '/web-stories/', '/podcasts/', '/podcast/',
                'astrology', 'horoscope', 'zodiac', 'vastu', 'ayurveda', 'ayurvedic', 'remedy', 'remedies',
                'rumor', 'rumours', 'fake news', 'viral video', 'bizarre', 'shocking', 'scandal',
                'lottery', 'kerala lottery', 'win news', 'entertainment', 'gaming', 'video game', 'esports',
                'tips', 'tricks', 'recipe', 'food recipe', 'dish', 'ingredient', 'cook', 'baking',
                'unboxing', 'specifications', 'price in india', 'smartphone review', 'phone review', 'gadget review', 'hands-on', 'hands on', 'first look',
                'offer', 'discount', 'amazon sale', 'flipkart sale', 'recharge plan', 'data plan', 'telecom plan', 'jio plan', 'airtel plan', 'vi plan', 'broadband plan',
                'mobile', 'smartphone', 'smartphones', 'smart tv', 'prepaid', 'postpaid', 'validity', 'bsnl', 'vodafone', 'idea', 'jio', 'airtel', 'vi', 'launch',
                'சினிமா', 'நடிகர்', 'நடிகை', 'படம்', 'திரைப்படம்', 'விமர்சனம்', 'ஜோதிடம்', 'ராசிபலன்', 'வதந்தி', 'பொழுதுபோக்கு',
                'டிப்ஸ்', 'சமையல்', 'குறிப்பு', 'உணவு', 'சாப்பாடு', 'ருசியான', 'சுவையான', 'சிறப்பம்சங்கள்',
                'சலுகை', 'தள்ளுபடி', 'ரீசார்ஜ்', 'ஆஃபர்', 'டேட்டா திட்டம்', 'ஸ்மார்ட்போன்', 'ப்ரீபெய்ட்', 'போஸ்ட்பெய்ட்', 'வேலிடிட்டி', 'மொபைல்'
            ]
            
            festival_keywords = [
                'festival', 'diwali', 'deepavali', 'pongal', 'navratri', 'pooja', 'pujan', 'பண்டிகை'
            ]
            
            breaking_news_keywords = ['breaking', 'flash', 'alert', 'முக்கிய செய்தி', 'பிரேக்கிங்']
            
            title_lower = getattr(entry, 'title', '').lower()
            url_lower = getattr(entry, 'link', '').lower()
            
            is_breaking = any(b in title_lower or b in url_lower for b in breaking_news_keywords)
            
            # Skip article if it contains unwanted topics
            if any(keyword in title_lower or keyword in url_lower for keyword in skip_keywords):
                feed_run.entries_failed += 1
                continue
                
            # Allow festival news ONLY if it's breaking news
            if not is_breaking and any(keyword in title_lower or keyword in url_lower for keyword in festival_keywords):
                feed_run.entries_failed += 1
                continue
                
            # Check if article already exists (Idempotency)
            existing = db.query(Article).filter(Article.guid == guid).first()
            if existing:
                continue
                
            original_url = getattr(entry, 'link', '')
            canonical_url = get_canonical_url(original_url)
            title = getattr(entry, 'title', '')
            
            # Determine Publish Date
            pub_date = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_date = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, 'published'):
                try:
                    pub_date = parsedate_to_datetime(entry.published)
                except Exception:
                    pub_date = datetime.utcnow()
            else:
                pub_date = datetime.utcnow()

            # Architecture Check: RSS Content vs Trafilatura
            # Most RSS feeds only give a 2-sentence summary in 'description'.
            rss_content_html = ''
            if hasattr(entry, 'content'):
                rss_content_html = entry.content[0].value
            elif hasattr(entry, 'description'):
                rss_content_html = entry.description
                
            clean_rss_text = clean_html(rss_content_html)
            
            final_text = ""
            extraction_method = "rss"
            extraction_quality = 0.0
            
            # If the RSS text is less than 500 chars, it's a snippet. We must scrape the URL.
            if len(clean_rss_text) < 500:
                downloaded = trafilatura.fetch_url(canonical_url)
                if downloaded:
                    # Extract main article body (removes headers, footers, sidebars)
                    extracted_text = trafilatura.extract(downloaded, favor_recall=True)
                    if extracted_text and len(extracted_text) > len(clean_rss_text):
                        final_text = deep_clean_text(extracted_text)
                        extraction_method = "trafilatura"
                        extraction_quality = 0.9 # High confidence full article
            
            # Fallback to RSS text if Trafilatura fails or if RSS had the full text (>500 chars)
            if not final_text:
                final_text = deep_clean_text(clean_rss_text)
                extraction_quality = 0.5
            
            # Skip articles with no usable content after cleaning
            if not final_text or len(final_text) < 200:
                feed_run.entries_failed += 1
                continue
                
            # Hash to detect content changes later
            content_hash = hashlib.sha256(final_text.encode('utf-8')).hexdigest() if final_text else None
            
            # Auto-detect language from actual content (unified timeline)
            detected_lang = detect_language(final_text)
            
            # Categorize article length for summarizer models
            word_count = len(final_text.split())
            if word_count < 250:
                article_length_cat = "short"
            elif word_count < 800:
                article_length_cat = "medium"
            else:
                article_length_cat = "long"
            
            data_fetch_via = "Google News RSS" if "news.google.com" in feed.feed_url else "Native RSS"
            
            article = Article(
                outlet_id=feed.outlet_id,
                rss_feed_id=feed.id,
                guid=guid,
                canonical_url=canonical_url,
                original_url=original_url,
                title=clean_html(title),
                description=clean_html(getattr(entry, 'description', '')),
                author=getattr(entry, 'author', ''),
                published_at=pub_date,
                language=detected_lang,
                article_length=article_length_cat,
                data_fetch_via=data_fetch_via,
                raw_text=rss_content_html,
                clean_text=final_text,
                content_hash=content_hash,
                extraction_method=extraction_method,
                extraction_quality=extraction_quality,
                processing_status="eligible"
            )
            
            db.add(article)
            try:
                db.commit() # Commit per article to avoid losing progress if one fails
                feed_run.entries_new += 1
            except Exception as commit_err:
                db.rollback()
                feed_run.entries_failed += 1
                continue
            
            # --- Save to unified raw_processed.csv ---
            csv_dir = os.path.join(os.path.dirname(__file__), "..", "data")
            os.makedirs(csv_dir, exist_ok=True)
            
            csv_path = os.path.join(csv_dir, "raw_processed.csv")
            
            file_exists = os.path.exists(csv_path)
            with open(csv_path, "a", newline="", encoding="utf-8") as csvfile:
                fieldnames = ["content_hash", "guid", "outlet_slug", "title", "description", "author", "published_at", "language", "article_length", "data_fetch_via", "canonical_url", "extraction_method", "extraction_quality", "processing_status", "raw_text", "clean_text"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow({
                    "content_hash": content_hash,
                    "guid": guid,
                    "outlet_slug": outlet_slug,
                    "title": article.title,
                    "description": article.description,
                    "author": article.author,
                    "published_at": pub_date.isoformat() if pub_date else "",
                    "language": detected_lang,
                    "article_length": article_length_cat,
                    "data_fetch_via": data_fetch_via,
                    "canonical_url": canonical_url,
                    "extraction_method": extraction_method,
                    "extraction_quality": extraction_quality,
                    "processing_status": "eligible",
                    "raw_text": rss_content_html,
                    "clean_text": final_text
                })
            # -------------------

            
        feed_run.finished_at = datetime.utcnow()
        feed.last_success_at = datetime.utcnow()
        feed.consecutive_failures = 0
        db.commit()
        
        # Save counts before session closes
        new_count = feed_run.entries_new
        seen_count = feed_run.entries_seen
        
    except Exception as e:
        db.rollback()
        feed_run.error_code = str(e)[:250]
        feed_run.finished_at = datetime.utcnow()
        feed_run.entries_failed += 1
        feed.consecutive_failures += 1
        db.commit()
        raise self.retry(exc=e)
    finally:
        db.close()
        
    return {"feed_id": feed_id, "new_articles": new_count, "total_seen": seen_count}


@celery_app.task
def dispatch_all_feeds():
    """
    Triggered every 15 minutes by Celery Beat.
    It reads all active feeds from Postgres and queues them for processing.
    """
    print("[Beat] Dispatching all active RSS feeds to the queue...")
    db = SessionLocal()
    try:
        active_feeds = db.query(RssFeed).filter(RssFeed.enabled == True).all()
        for feed in active_feeds:
            process_single_feed.delay(feed.id)
            print(f"[Beat] Queued feed {feed.id} ({feed.feed_url})")
            
        return {"dispatched_count": len(active_feeds)}
    finally:
        db.close()
