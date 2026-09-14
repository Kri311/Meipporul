import re
import os
import yaml

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"

# 1. Update text_cleaning.py for "Pvt Ltd" and JUNK_PATTERNS
tc_path = os.path.join(base_dir, "ingestion", "tasks", "text_cleaning.py")
with open(tc_path, "r", encoding="utf-8") as f:
    tc_content = f.read()

# Make sure we remove old "IE Online Media Services PVT LTD" and add robust one
tc_content = re.sub(r'r"\(\?i\)IE Online Media Services PVT LTD",', r'r"(?i)IE Online Media Services PVT LTD",\n    r"(?i).*Pvt Ltd\.?$",\n    r"(?i)The Indian Express.*",', tc_content)

with open(tc_path, "w", encoding="utf-8") as f:
    f.write(tc_content)

# 2. Update configs to add ABP Nadu, Hindustan Times, Livemint
conf_path_1 = os.path.join(base_dir, "config", "sources.yaml")
conf_path_2 = os.path.join(base_dir, "ingestion", "config", "sources.yaml")

def add_new_sources(conf_path):
    with open(conf_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    slugs = [s["slug"] for s in data["sources"]]
    
    if "abp_nadu" not in slugs:
        data["sources"].append({
            "slug": "abp_nadu",
            "name": "ABP Nadu",
            "language": "ta",
            "homepage": "https://tamil.abplive.com",
            "rss": ["https://tamil.abplive.com/home/feed"],
            "enabled": True,
            "orientation_bucket": "IND",
            "orientation_confidence": 0.85,
            "fetch_interval_minutes": 15,
            "rate_limit_per_minute": 30,
            "category": "general"
        })
    if "hindustan_times" not in slugs:
        data["sources"].append({
            "slug": "hindustan_times",
            "name": "Hindustan Times",
            "language": "en",
            "homepage": "https://www.hindustantimes.com",
            "rss": ["https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml"],
            "enabled": True,
            "orientation_bucket": "IND",
            "orientation_confidence": 0.85,
            "fetch_interval_minutes": 15,
            "rate_limit_per_minute": 30,
            "category": "general"
        })
    if "livemint" not in slugs:
        data["sources"].append({
            "slug": "livemint",
            "name": "Livemint",
            "language": "en",
            "homepage": "https://www.livemint.com",
            "rss": ["https://www.livemint.com/rss/news"],
            "enabled": True,
            "orientation_bucket": "IND",
            "orientation_confidence": 0.85,
            "fetch_interval_minutes": 15,
            "rate_limit_per_minute": 30,
            "category": "general"
        })
    
    with open(conf_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)

add_new_sources(conf_path_1)
add_new_sources(conf_path_2)

# 3. Patch fetch_rss_standalone.py (Trafilatura UTF-8 + Title prepend + BOM)
frs_path = os.path.join(base_dir, "fetch_rss_standalone.py")
with open(frs_path, "r", encoding="utf-8") as f:
    frs_content = f.read()

# Fix Trafilatura encoding handling
old_trafilatura = """
        try:
            resp = requests.get(canonical_url, headers=HTTP_HEADERS, timeout=10)
            downloaded = resp.text if resp.status_code == 200 else None
        except Exception:
            downloaded = None

        if downloaded:
            extracted_text = trafilatura.extract(downloaded, favor_recall=True)"""
new_trafilatura = """
        try:
            resp = requests.get(canonical_url, headers=HTTP_HEADERS, timeout=10)
            # Use content (bytes) to let Trafilatura handle encoding properly
            downloaded = resp.content if resp.status_code == 200 else None
        except Exception:
            downloaded = None

        if downloaded:
            extracted_text = trafilatura.extract(downloaded, favor_recall=True)"""
frs_content = frs_content.replace(old_trafilatura, new_trafilatura)

# Prepend Title to Clean Text
old_process = """
            # Apply per-outlet cleaners and classify topic
            clean_title, final_text = apply_outlet_cleaners(clean_title, final_text, outlet_slug, canonical_url)
            topic = classify_topic(clean_title, final_text, outlet_slug)
"""
new_process = """
            # Apply per-outlet cleaners and classify topic
            clean_title, final_text = apply_outlet_cleaners(clean_title, final_text, outlet_slug, canonical_url)
            
            # STANDARD: Ensure content explicitly begins with the Title followed by the Body
            # This fulfills the expectation of having the Title at the start of the content.
            final_text = f"{clean_title}\\n\\n{final_text}"
            
            topic = classify_topic(clean_title, final_text, outlet_slug)
"""
if "# STANDARD" not in frs_content:
    frs_content = frs_content.replace(old_process, new_process)

# Fix CSV BOM writing
old_csv_open = 'with open(CSV_PATH, "a", newline="", encoding="utf-8") as csvfile:'
new_csv_open = 'with open(CSV_PATH, "a", newline="", encoding="utf-8-sig") as csvfile:' # utf-8-sig adds BOM for Excel
frs_content = frs_content.replace(old_csv_open, new_csv_open)

with open(frs_path, "w", encoding="utf-8") as f:
    f.write(frs_content)


# 4. Patch fetch_feed.py
ff_path = os.path.join(base_dir, "ingestion", "tasks", "fetch_feed.py")
with open(ff_path, "r", encoding="utf-8") as f:
    ff_content = f.read()

# Fix Trafilatura encoding handling
old_trafilatura_ff = """
                try:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                    }
                    resp = requests.get(canonical_url, headers=headers, timeout=10)
                    downloaded = resp.text if resp.status_code == 200 else None
                except Exception:
                    downloaded = None

                if downloaded:
                    # Extract main article body (removes headers, footers, sidebars)
                    extracted_text = trafilatura.extract(downloaded, favor_recall=True)"""
new_trafilatura_ff = """
                try:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                    }
                    resp = requests.get(canonical_url, headers=headers, timeout=10)
                    downloaded = resp.content if resp.status_code == 200 else None
                except Exception:
                    downloaded = None

                if downloaded:
                    # Extract main article body (removes headers, footers, sidebars)
                    extracted_text = trafilatura.extract(downloaded, favor_recall=True)"""
ff_content = ff_content.replace(old_trafilatura_ff, new_trafilatura_ff)

# Prepend Title
old_process_ff = """
            # Apply per-outlet cleaners and classify topic
            title_clean, final_text = apply_outlet_cleaners(clean_html(title), final_text, outlet_slug, canonical_url)
            topic = classify_topic(title_clean, final_text, outlet_slug)
"""
new_process_ff = """
            # Apply per-outlet cleaners and classify topic
            title_clean, final_text = apply_outlet_cleaners(clean_html(title), final_text, outlet_slug, canonical_url)
            
            # STANDARD: Ensure content explicitly begins with the Title followed by the Body
            final_text = f"{title_clean}\\n\\n{final_text}"
            
            topic = classify_topic(title_clean, final_text, outlet_slug)
"""
if "# STANDARD" not in ff_content:
    ff_content = ff_content.replace(old_process_ff, new_process_ff)

# Fix CSV BOM writing
old_csv_open_ff = 'with open(csv_path, "a", newline="", encoding="utf-8") as csvfile:'
new_csv_open_ff = 'with open(csv_path, "a", newline="", encoding="utf-8-sig") as csvfile:'
ff_content = ff_content.replace(old_csv_open_ff, new_csv_open_ff)

with open(ff_path, "w", encoding="utf-8") as f:
    f.write(ff_content)

print("Patch applied successfully.")
