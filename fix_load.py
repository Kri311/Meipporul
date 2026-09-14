with open("fetch_rss_standalone.py", "r") as f:
    text = f.read()
import re
text = re.sub(r'def load_existing_data\(csv_path\):.*?return guids, content_hashes, existing_urls', 
r'''def load_existing_data():
    """Load existing identifiers from PostgreSQL for deduplication (scoped per outlet)."""
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
        
    return guids, content_hashes, existing_urls''', text, flags=re.DOTALL)
with open("fetch_rss_standalone.py", "w") as f:
    f.write(text)
