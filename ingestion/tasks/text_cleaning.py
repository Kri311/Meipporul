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
import urllib.parse
import requests
from bs4 import BeautifulSoup


def clean_html(raw_html):
    """Removes HTML tags and normalizes whitespace."""
    if not raw_html:
        return ""
    raw_html = str(raw_html)
    # If the input doesn't contain HTML markup, treat it as plain text.
    if "<" not in raw_html or ">" not in raw_html:
        text = raw_html.strip()
    else:
        soup = BeautifulSoup(raw_html, "html.parser")
        text = soup.get_text(separator="\n").strip()
    # Strip dateline prefixes
    text = re.sub(
        r"^(?:[A-Za-z\s]{3,20}|[\u0B80-\u0BFF\s]{3,20})\s*(?:\||\:\-|\:)\s*","",text).strip()
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



def normalize_political_parties(text):
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
        text = re.sub(tamil_pattern, eng_abbr, text)
    return text

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
    result = normalize_political_parties(result)
        
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
    result = re.sub(r"^(?:[A-Za-z\s]{3,20}|[\u0B80-\u0BFF\s]{3,20})\s*(?:\||\:\-|\:)\s*", "", result.strip())
    
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
    'politics': ['election', 'parliament', 'minister', 'bjp', 'dmk', 'congress', 'aiadmk', 'tvk', 'pmk', 'vck', 'ntk', 'தேர்தல்', 'நாடாளுமன்றம்', 'முதல்வர்', 'அமைச்சர்', 'அரசியல்', 'சட்டமன்றம்', 'எம்.எல்.ஏ'],
    'world_news': ['international', 'global', 'us', 'china', 'ukraine', 'nato', 'russia', 'israel', 'gaza', 'சர்வதேச', 'உலக', 'அமெரிக்கா', 'சீனா', 'ரஷ்யா', 'இலங்கை'],
    'economy': ['economy', 'gdp', 'inflation', 'rbi', 'stock market', 'rupee', 'market', 'business', 'பொருளாதாரம்', 'பணவீக்கம்', 'பங்குச்சந்தை', 'ரூபாய்', 'வர்த்தகம்', 'பட்ஜெட்'],
    'crime_law': ['murder', 'arrest', 'police', 'court', 'fir', 'cbi', 'supreme court', 'high court', 'கொலை', 'கைது', 'காவல்', 'நீதிமன்றம்', 'வழக்கு', 'தீர்ப்பு', 'சிபிஐ', 'போலீஸ்'],
    'science_health': ['research', 'vaccine', 'who', 'hospital', 'climate', 'space', 'isro', 'nasa', 'health', 'disease', 'ஆராய்ச்சி', 'தடுப்பூசி', 'மருத்துவம்', 'காலநிலை', 'சுகாதாரம்', 'விண்வெளி', 'இஸ்ரோ', 'மருத்துவமனை'],
    'sports': ['cricket', 'ipl', 'match', 'tournament', 'champion', 'olympics', 'tennis', 'football', 'கிரிக்கெட்', 'போட்டி', 'வெற்றி', 'ஐபிஎல்', 'விளையாட்டு', 'ஒலிம்பிக்'],
    'education': ['school', 'university', 'exam', 'neet', 'syllabus', 'students', 'college', 'பள்ளி', 'பல்கலைக்கழகம்', 'தேர்வு', 'நீட்', 'மாணவர்கள்', 'கல்லூரி', 'கல்வி'],
}

def classify_topic(title, text, outlet_slug=""):
    if outlet_slug == "bbc_tamil":
        return "world_news"
    if outlet_slug == "tamil_mykhel":
        return "sports"

    combined_text = (str(title) + " " + str(title) + " " + str(text)[:300]).lower()

    scores = {topic: 0 for topic in TOPIC_KEYWORDS}
    for topic, keywords in TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw in combined_text:
                scores[topic] += combined_text.count(kw)

    best_topic = max(scores, key=scores.get)
    if scores[best_topic] > 0:
        return best_topic
    return "general"

def clean_times_of_india(title, text):
    title = re.sub(r"^\s*-\s*", "", title)
    text = re.sub(r"^[A-Za-z\s]{3,20}\s*:\s*", "", text)
    text = re.sub(r"(?i)In\s+[A-Za-z]+\s*\|\s*LPG\s+Price.*$", "", text).strip()
    return title, text

def clean_bbc_tamil(title, text):
    # Remove footer
    text = re.sub(r"- இது, க்காக கலெக்டிவ் நியூஸ்ரூம் வெளியீடு[\s\S]*", "", text)
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
