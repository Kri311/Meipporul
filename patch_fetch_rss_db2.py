import os
import re

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"
rss_path = os.path.join(base_dir, "fetch_rss_standalone.py")

with open(rss_path, "r", encoding="utf-8") as f:
    content = f.read()

old_load = """def load_existing_data(csv_path):
    \"\"\"Load existing identifiers from the CSV for deduplication (scoped per outlet).\"\"\"
    guids = set()
    content_hashes = set()
    existing_urls = set()
    
    if not os.path.exists(csv_path):
        return guids, content_hashes, existing_urls
        
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                outlet = row.get("outlet_slug", "")
                if not outlet:
                    continue
                if row.get("guid"):
                    guids.add((outlet, row["guid"]))
                if row.get("content_hash"):
                    content_hashes.add((outlet, row["content_hash"]))
                if row.get("canonical_url"):
                    existing_urls.add(row["canonical_url"])
    except Exception as e:
        print(f"Error reading CSV {csv_path}: {e}")
        
    return guids, content_hashes, existing_urls"""

new_load = """def load_existing_data():
    \"\"\"Load existing identifiers from PostgreSQL for deduplication (scoped per outlet).\"\"\"
    guids = set()
    content_hashes = set()
    existing_urls = set()
    
    db = SessionLocal()
    try:
        articles = db.query(Article.guid, Article.content_hash, Article.canonical_url, Outlet.slug).join(Outlet).all()
        for art in articles:
            if art.slug and art.guid:
                guids.add((art.slug, art.guid))
            if art.slug and art.content_hash:
                content_hashes.add((art.slug, art.content_hash))
            if art.canonical_url:
                existing_urls.add(art.canonical_url)
    finally:
        db.close()
        
    return guids, content_hashes, existing_urls"""

content = content.replace(old_load, new_load)
content = content.replace("existing_guids, content_hashes, existing_urls = load_existing_data(CSV_PATH)", "existing_guids, content_hashes, existing_urls = load_existing_data()")
content = content.replace("Existing articles in CSV", "Existing articles in DB")

with open(rss_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Patched load_existing_data to use PostgreSQL.")
