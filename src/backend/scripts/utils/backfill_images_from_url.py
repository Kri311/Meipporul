import sys, os, re, requests, time, concurrent.futures
sys.path.insert(0, os.path.join(os.path.abspath('.'), 'src'))
from backend.models.database import SessionLocal, Article
from bs4 import BeautifulSoup

def fetch_image(article_id, url):
    try:
        resp = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, "html.parser")
            meta_og = soup.find("meta", property="og:image")
            if meta_og and meta_og.get("content"):
                return article_id, meta_og["content"]
            meta_tw = soup.find("meta", attrs={"name": "twitter:image"})
            if meta_tw and meta_tw.get("content"):
                return article_id, meta_tw["content"]
    except Exception:
        pass
    return article_id, None

db = SessionLocal()
arts = db.query(Article).filter(Article.image_url.is_(None)).all()
print(f"Found {len(arts)} articles without images. Starting backfill...")
db.close()

def chunked_arts(arts, size):
    for i in range(0, len(arts), size):
        yield arts[i:i+size]

total_updated = 0
# Process in batches to manage DB connections
for batch in chunked_arts(arts, 50):
    updates = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_image, a.id, a.canonical_url): a for a in batch}
        for future in concurrent.futures.as_completed(futures):
            aid, img_url = future.result()
            if img_url:
                updates[aid] = img_url
    
    if updates:
        db = SessionLocal()
        db_arts = db.query(Article).filter(Article.id.in_(updates.keys())).all()
        for a in db_arts:
            a.image_url = updates[a.id]
        db.commit()
        db.close()
        total_updated += len(updates)
        print(f"Updated {total_updated} images so far...")

print(f"Completed! Backfilled {total_updated} total images.")
