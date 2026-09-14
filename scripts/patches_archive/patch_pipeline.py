import os
import re

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"

# ==========================
# 1. Update text_cleaning.py
# ==========================
tc_path = os.path.join(base_dir, "ingestion", "tasks", "text_cleaning.py")
with open(tc_path, "r") as f: tc = f.read()

new_junk = """    # Ads / promotional
    r"(?i)^\\s*advertisement\\s*$",
    r"(?i)^\\s*sponsored\\s*$",
    r"(?i)^\\s*promoted\\s*content\\s*$",
    r"(?i)Story continues below this ad",
    r"(?i)Loading recommendations",
    r"(?i)pic\\.twitter\\.com/\\w+",
    r"(?i)IE Online Media Services PVT LTD",
    r"(?i)-picture:\\d+/?",
    r"(?i)Published by:\\w+",
    r"(?i)is a Special Correspondent",
"""
tc = tc.replace('    # Ads / promotional\n    r"(?i)^\\s*advertisement\\s*$",\n    r"(?i)^\\s*sponsored\\s*$",\n    r"(?i)^\\s*promoted\\s*content\\s*$",', new_junk)

new_skips = """    'mobile', 'smartphone', 'smartphones', 'smart tv', 'prepaid', 'postpaid', 'validity', 'bsnl', 'vodafone', 'idea', 'jio', 'airtel', 'vi', 'launch',
    'bigg boss', 'big boss', 'பிக் பாஸ்', 'கிசுகிசு', 'வைரல்', '/photogallery/', '/explanations/', 'recruitment', 'hiring', 'job opening', 'vacancy', 'நியமனம்', 'வேலைவாய்ப்பு',
"""
tc = tc.replace("    'mobile', 'smartphone', 'smartphones', 'smart tv', 'prepaid', 'postpaid', 'validity', 'bsnl', 'vodafone', 'idea', 'jio', 'airtel', 'vi', 'launch',", new_skips)

new_functions = '''
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
    title = re.sub(r"^\\s*-\\s*", "", title)
    text = re.sub(r"^[A-Za-z\\s]{3,20}\\s*:\\s*", "", text)
    text = re.sub(r"(?i)In\\s+[A-Za-z]+\\s*\\|\\s*LPG\\s+Price.*$", "", text).strip()
    return title, text

def clean_dinamani(title, text):
    text = re.sub(r"(?i)[a-z\\s\\.,\\?!]+$", "", text).strip()
    text = re.sub(r"(?i)-picture:\\d+/?", "", text)
    text = re.sub(r"(?i).*கோப்புப்\\s*படம்.*", "", text)
    return title, text

def clean_indian_express(title, text):
    text = re.sub(r"(?i)Story continues below this ad", "", text)
    text = re.sub(r"(?i)Loading recommendations", "", text)
    text = re.sub(r"(?i)pic\\.twitter\\.com/\\w+", "", text)
    text = re.sub(r"(?i)IE Online Media Services PVT LTD", "", text)
    text = re.sub(r"(?i).*is a Special Correspondent.*", "", text)
    return title, text

def clean_tamil_oneindia(title, text):
    text = re.sub(r"^[A-Za-z\\u0B80-\\u0BFF\\s]{3,20}\\s*:\\s*", "", text)
    return title, text

def clean_news18(title, text, url=""):
    text = re.sub(r"^[A-Za-z\\s]+\\s*\\|\\s*", "", text)
    if text.startswith(title):
        text = text[len(title):].strip()
    text = re.sub(r"^\\s*-\\s*Published\\s*by\\s*:\\s*[A-Za-z\\.]+\\s*", "", text, flags=re.IGNORECASE)
    return title, text

def clean_tamil_mykhel(title, text, url=""):
    return title, text

def apply_outlet_cleaners(title, text, outlet_slug, url=""):
    if outlet_slug == "times_of_india":
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
'''
with open(tc_path, "w") as f: f.write(tc + "\n" + new_functions)


# ==========================
# 2. Update fetch_rss_standalone.py
# ==========================
frs_path = os.path.join(base_dir, "fetch_rss_standalone.py")
with open(frs_path, "r") as f: frs = f.read()

frs = frs.replace(
    "SKIP_KEYWORDS, FESTIVAL_KEYWORDS, BREAKING_NEWS_KEYWORDS,",
    "SKIP_KEYWORDS, FESTIVAL_KEYWORDS, BREAKING_NEWS_KEYWORDS,\n    classify_topic, apply_outlet_cleaners"
)

frs = frs.replace(
    '"extraction_quality", "processing_status", "raw_text", "clean_text"',
    '"extraction_quality", "processing_status", "raw_text", "clean_text", "topic"'
)

frs = frs.replace(
    "            if should_skip_entry(title_lower, url_lower):",
    "            if should_skip_entry(title_lower, url_lower):\n                filtered_quality += 1\n                continue\n\n            # Extra News18 filters\n            if outlet_slug in ['news18_india', 'news18_tamil_nadu'] and any(kw in url_lower for kw in ['/photogallery/', '/explanations/', 'job', 'recruitment']):"
)

process_feed_repl = """            # Detect language and article length
            detected_lang = detect_language(final_text)
            
            # Apply per-outlet cleaners and classify topic
            clean_title, final_text = apply_outlet_cleaners(clean_title, final_text, outlet_slug, canonical_url)
            topic = classify_topic(clean_title, final_text, outlet_slug)
            
            word_count = len(final_text.split())"""
frs = frs.replace("            # Detect language and article length\n            detected_lang = detect_language(final_text)\n            word_count = len(final_text.split())", process_feed_repl)

frs = frs.replace(
    '"clean_text": final_text,',
    '"clean_text": final_text,\n                "topic": topic,'
)

with open(frs_path, "w") as f: f.write(frs)

# ==========================
# 3. Update fetch_feed.py
# ==========================
ff_path = os.path.join(base_dir, "ingestion", "tasks", "fetch_feed.py")
with open(ff_path, "r") as f: ff = f.read()

ff = ff.replace(
    "SKIP_KEYWORDS, FESTIVAL_KEYWORDS, BREAKING_NEWS_KEYWORDS,",
    "SKIP_KEYWORDS, FESTIVAL_KEYWORDS, BREAKING_NEWS_KEYWORDS,\n    classify_topic, apply_outlet_cleaners"
)

ff = ff.replace(
    "            if any(keyword in title_lower or keyword in url_lower for keyword in SKIP_KEYWORDS):",
    "            if any(keyword in title_lower or keyword in url_lower for keyword in SKIP_KEYWORDS):\n                feed_run.entries_failed += 1\n                continue\n                \n            # Extra News18 filters\n            if outlet_slug in ['news18_india', 'news18_tamil_nadu'] and any(kw in url_lower for kw in ['/photogallery/', '/explanations/', 'job', 'recruitment']):"
)

ff_repl = """            # Auto-detect language from actual content (unified timeline)
            detected_lang = detect_language(final_text)
            
            # Apply per-outlet cleaners and classify topic
            title_clean, final_text = apply_outlet_cleaners(clean_html(title), final_text, outlet_slug, canonical_url)
            topic = classify_topic(title_clean, final_text, outlet_slug)
            
            # Categorize article length for summarizer models"""
ff = ff.replace("            # Auto-detect language from actual content (unified timeline)\n            detected_lang = detect_language(final_text)\n            \n            # Categorize article length for summarizer models", ff_repl)

ff = ff.replace(
    'title=clean_html(title),',
    'title=title_clean,'
)

ff = ff.replace(
    'fieldnames = ["content_hash", "guid", "outlet_slug", "title", "description", "author", "published_at", "language", "article_length", "data_fetch_via", "canonical_url", "extraction_method", "extraction_quality", "processing_status", "raw_text", "clean_text"]',
    'fieldnames = ["content_hash", "guid", "outlet_slug", "title", "description", "author", "published_at", "language", "article_length", "data_fetch_via", "canonical_url", "extraction_method", "extraction_quality", "processing_status", "raw_text", "clean_text", "topic"]'
)

ff = ff.replace(
    '"clean_text": final_text\n                })',
    '"clean_text": final_text,\n                    "topic": topic\n                })'
)

with open(ff_path, "w") as f: f.write(ff)

print("Files successfully patched!")
