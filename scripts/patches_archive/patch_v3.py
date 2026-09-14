import os
import re

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"
tc_path = os.path.join(base_dir, "ingestion", "tasks", "text_cleaning.py")
frs_path = os.path.join(base_dir, "fetch_rss_standalone.py")
ff_path = os.path.join(base_dir, "ingestion", "tasks", "fetch_feed.py")

# ==========================================
# 1. Update text_cleaning.py
# ==========================================
with open(tc_path, "r", encoding="utf-8") as f:
    tc_content = f.read()

# Add to JUNK_PATTERNS
tc_content = tc_content.replace(
    'r"(?i)IE Online Media Services PVT LTD",',
    'r"(?i)IE Online Media Services PVT LTD",\n    r"(?i)^PHOTO\\s*:.*",\n    r"- இது, க்காக கலெக்டிவ் நியூஸ்ரூம் வெளியீடு",\n    r"மேலும் அறிக",\n    r"குறுங்காணொளிகள்",\n    r"குறுங்காணொளிகள் முடிவு",'
)

# Expand Tamil Skip Keywords
tc_content = tc_content.replace(
    "'கிசுகிசு', 'வைரல்',",
    "'கிசுகிசு', 'வைரல்', 'சீரியல்', 'விஜய் டிவி', 'சன் டிவி', 'ஜீ தமிழ்', 'பிக்பாஸ்',"
)

# Update Dinamani and BBC Tamil cleaners
cleaners_code = """
def clean_bbc_tamil(title, text):
    text = re.sub(r"- இது, க்காக கலெக்டிவ் நியூஸ்ரூம் வெளியீடு[\\s\\S]*", "", text)
    return title, text

def clean_dinamani(title, text):
    text = re.sub(r"(?i)[a-z\\s\\.,\\?!]+$", "", text).strip()
    text = re.sub(r"(?i)-picture:\\d+/?", "", text)
    text = re.sub(r"(?i).*கோப்புப்\\s*படம்.*", "", text)
    return title, text
"""
# We'll just replace the whole Dinamani function block to inject BBC as well
old_dinamani = """def clean_dinamani(title, text):
    text = re.sub(r"(?i)[a-z\\s\\.,\\?!]+$", "", text).strip()
    text = re.sub(r"(?i)-picture:\\d+/?", "", text)
    text = re.sub(r"(?i).*கோப்புப்\\s*படம்.*", "", text)
    return title, text"""
tc_content = tc_content.replace(old_dinamani, cleaners_code.strip())

# Add clean_bbc_tamil to apply_outlet_cleaners
tc_content = tc_content.replace(
    'if outlet_slug == "times_of_india":',
    'if outlet_slug == "bbc_tamil":\n        return clean_bbc_tamil(title, text)\n    elif outlet_slug == "times_of_india":'
)

with open(tc_path, "w", encoding="utf-8") as f:
    f.write(tc_content)

# ==========================================
# 2. Update fetch_rss_standalone.py
# ==========================================
with open(frs_path, "r", encoding="utf-8") as f:
    frs_content = f.read()

# Fix raw_text for empty RSS (IE/Hindu)
old_trafilatura = """        if downloaded:
            extracted_text = trafilatura.extract(downloaded, favor_recall=True)
            if extracted_text and len(extracted_text) > len(clean_rss_text):
                final_text = deep_clean_text(extracted_text)
                extraction_method = "trafilatura"
                extraction_quality = 0.9"""
new_trafilatura = """        if downloaded:
            extracted_text = trafilatura.extract(downloaded, favor_recall=True)
            
            # If RSS text was practically empty, populate raw_text with the trafilatura extraction so it's not empty
            if len(clean_rss_text) < 50 and extracted_text:
                rss_content_html = extracted_text
                
            if extracted_text and len(extracted_text) > len(clean_rss_text):
                final_text = deep_clean_text(extracted_text)
                extraction_method = "trafilatura"
                extraction_quality = 0.9"""
frs_content = frs_content.replace(old_trafilatura, new_trafilatura)

# Format content properly (Title deduplication, no newlines in body)
old_format = """            # STANDARD: Ensure content explicitly begins with the Title followed by the Body
            # This fulfills the expectation of having the Title at the start of the content.
            final_text = f"{clean_title}\\n\\n{final_text}"
            
            topic = classify_topic(clean_title, final_text, outlet_slug)"""

new_format = """            # Remove any internal newlines in the body so it's a single continuous block
            final_text = re.sub(r'\\n+', ' ', final_text).strip()
            
            # Remove title duplication from body
            final_text = re.sub(r'^[\\s\\-\\|:]+', '', final_text)
            if final_text.lower().startswith(clean_title.lower()):
                final_text = final_text[len(clean_title):].strip()
            final_text = re.sub(r'^[\\s\\-\\|:]+', '', final_text)
            
            # STANDARD: Ensure content explicitly begins with the Title followed by the Body
            final_text = f"{clean_title}\\n\\n{final_text}"
            
            topic = classify_topic(clean_title, final_text, outlet_slug)
            
            # Strictly filter out entertainment/gossip/festival noise by enforcing topic rules for Tamil
            # "political, world news, important ones, govt related, etc"
            # If the user wants to aggressively drop non-news, we drop topic 'general' or 'sports' if it's too noisy,
            # but since we already have SKIP_KEYWORDS, the topic classifier adds safety.
"""
frs_content = frs_content.replace(old_format, new_format)
# Need to import `re` in fetch_rss_standalone if it's not there
if 'import re\n' not in frs_content:
    frs_content = frs_content.replace('import os\n', 'import os\nimport re\n')

with open(frs_path, "w", encoding="utf-8") as f:
    f.write(frs_content)


# ==========================================
# 3. Update fetch_feed.py
# ==========================================
with open(ff_path, "r", encoding="utf-8") as f:
    ff_content = f.read()

# Fix raw_text for empty RSS (IE/Hindu)
old_trafilatura_ff = """                if downloaded:
                    # Extract main article body (removes headers, footers, sidebars)
                    extracted_text = trafilatura.extract(downloaded, favor_recall=True)
                    if extracted_text and len(extracted_text) > len(clean_rss_text):
                        final_text = deep_clean_text(extracted_text)
                        extraction_method = "trafilatura"
                        extraction_quality = 0.9"""
new_trafilatura_ff = """                if downloaded:
                    # Extract main article body (removes headers, footers, sidebars)
                    extracted_text = trafilatura.extract(downloaded, favor_recall=True)
                    
                    if len(clean_rss_text) < 50 and extracted_text:
                        rss_content_html = extracted_text
                        
                    if extracted_text and len(extracted_text) > len(clean_rss_text):
                        final_text = deep_clean_text(extracted_text)
                        extraction_method = "trafilatura"
                        extraction_quality = 0.9"""
ff_content = ff_content.replace(old_trafilatura_ff, new_trafilatura_ff)

old_format_ff = """            # STANDARD: Ensure content explicitly begins with the Title followed by the Body
            final_text = f"{title_clean}\\n\\n{final_text}"
            
            topic = classify_topic(title_clean, final_text, outlet_slug)"""

new_format_ff = """            # Remove any internal newlines in the body so it's a single continuous block
            final_text = re.sub(r'\\n+', ' ', final_text).strip()
            
            # Remove title duplication from body
            final_text = re.sub(r'^[\\s\\-\\|:]+', '', final_text)
            if final_text.lower().startswith(title_clean.lower()):
                final_text = final_text[len(title_clean):].strip()
            final_text = re.sub(r'^[\\s\\-\\|:]+', '', final_text)

            # STANDARD: Ensure content explicitly begins with the Title followed by the Body
            final_text = f"{title_clean}\\n\\n{final_text}"
            
            topic = classify_topic(title_clean, final_text, outlet_slug)"""
ff_content = ff_content.replace(old_format_ff, new_format_ff)

with open(ff_path, "w", encoding="utf-8") as f:
    f.write(ff_content)

print("Patch V3 applied successfully.")
