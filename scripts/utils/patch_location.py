import os
import re

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"
tc_path = os.path.join(base_dir, "ingestion", "tasks", "text_cleaning.py")
rss_path = os.path.join(base_dir, "fetch_rss_standalone.py")
feed_path = os.path.join(base_dir, "ingestion", "tasks", "fetch_feed.py")

# 1. Update text_cleaning.py
with open(tc_path, "r", encoding="utf-8") as f:
    tc_content = f.read()

location_func_code = """
NON_LOCATION_PREFIXES = {
    'note', 'update', 'warning', 'report', 'breaking', 'alert', 'live', 'opinion',
    'editorial', 'analysis', 'watch', 'photos', 'video', 'special report',
    'முக்கிய செய்தி', 'செய்தி', 'நேரலை', 'சிறப்பு செய்தி', 'அறிவிப்பு', 'எச்சரிக்கை'
}

def extract_dateline_location(text):
    \"\"\"
    Extracts dateline location prefix (e.g. 'Chennai: ', 'NEW DELHI - ', 'சென்னை | ', 'புதுடெல்லி:')
    from the beginning of the text, returning (location, cleaned_text).
    Removes the location prefix from cleaned_text.
    \"\"\"
    if not text:
        return '', ''
    pattern = r'^\\s*(?:\\[(?P<loc1>[^\\]]+)\\]|(?P<loc2>[a-zA-Z\\u0B80-\\u0BFF\\s]{2,30}))\\s*(?:\\([^\\)]+\\))?\\s*(?::-|\\:|\\||\\-|\\u2013|\\u2014)\\s*'
    match = re.match(pattern, text)
    if match:
        raw_loc = (match.group('loc1') or match.group('loc2') or '').strip()
        cleaned_text = text[match.end():].strip()
        if raw_loc.lower() in NON_LOCATION_PREFIXES:
            return '', cleaned_text
        return raw_loc, cleaned_text
    return '', text.strip()
"""

# Insert location_func_code before deep_clean_text
tc_content = tc_content.replace("def deep_clean_text(text):", location_func_code + "\ndef deep_clean_text(text):")

# Replace dateline stripping line in deep_clean_text
old_strip_line = '    result = re.sub(r"^(?:[A-Za-z\\s]{3,20}|[\\u0B80-\\u0BFF\\s]{3,20})\\s*(?:\\||\\:\\-|\\:)\\s*", "", result.strip())'
new_strip_line = '    _, result = extract_dateline_location(result.strip())'
tc_content = tc_content.replace(old_strip_line, new_strip_line)

# Update classify_topic to accept location parameter
old_classify = 'def classify_topic(title, text, outlet_slug=""):'
new_classify = 'def classify_topic(title, text, outlet_slug="", location=""):'
tc_content = tc_content.replace(old_classify, new_classify)

old_comb_text = '    combined_text = (str(title) + " " + str(title) + " " + str(text)[:300]).lower()'
new_comb_text = '    combined_text = (str(title) + " " + str(title) + " " + str(location) + " " + str(location) + " " + str(text)[:300]).lower()'
tc_content = tc_content.replace(old_comb_text, new_comb_text)

with open(tc_path, "w", encoding="utf-8") as f:
    f.write(tc_content)
print("Updated text_cleaning.py")

# 2. Update fetch_rss_standalone.py and fetch_feed.py
for p in [rss_path, feed_path]:
    with open(p, "r", encoding="utf-8") as f:
        content = f.read()

    if "extract_dateline_location" not in content:
        content = content.replace("normalize_political_parties\n)", "normalize_political_parties,\n    extract_dateline_location\n)")

    old_clean_step = "clean_title, final_text = apply_outlet_cleaners(clean_title, final_text, outlet_slug, canonical_url)"
    new_clean_step = "loc, final_text = extract_dateline_location(final_text)\n            clean_title, final_text = apply_outlet_cleaners(clean_title, final_text, outlet_slug, canonical_url)"
    if "title_clean, final_text = apply_outlet_cleaners" in content:
        old_clean_step_feed = "title_clean, final_text = apply_outlet_cleaners(clean_html(title), final_text, outlet_slug, canonical_url)"
        new_clean_step_feed = "loc, final_text = extract_dateline_location(final_text)\n            title_clean, final_text = apply_outlet_cleaners(clean_html(title), final_text, outlet_slug, canonical_url)"
        content = content.replace(old_clean_step_feed, new_clean_step_feed)
    elif old_clean_step in content:
        content = content.replace(old_clean_step, new_clean_step)

    old_topic_call = "topic = classify_topic(clean_title, final_text, outlet_slug)"
    new_topic_call = "topic = classify_topic(clean_title, final_text, outlet_slug, location=loc)"
    if old_topic_call in content:
        content = content.replace(old_topic_call, new_topic_call)

    old_topic_call_feed = "topic = classify_topic(title_clean, final_text, outlet_slug)"
    new_topic_call_feed = "topic = classify_topic(title_clean, final_text, outlet_slug, location=loc)"
    if old_topic_call_feed in content:
        content = content.replace(old_topic_call_feed, new_topic_call_feed)

    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Updated {p}")

