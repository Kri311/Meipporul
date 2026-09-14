import csv
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from ingestion.models.database import SessionLocal, Article, Outlet

def import_csv():
    csv_path = "data/raw_processed.csv"
    if not os.path.exists(csv_path):
        print("No CSV found.")
        return
        
    db = SessionLocal()
    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                outlet = db.query(Outlet).filter(Outlet.slug == row['outlet_slug']).first()
                if not outlet:
                    continue
                
                # Check if exists
                if db.query(Article).filter(Article.guid == row['guid']).first():
                    continue
                
                art = Article(
                    outlet_id=outlet.id,
                    guid=row['guid'],
                    canonical_url=row['canonical_url'],
                    original_url=row['canonical_url'],
                    title=row['title'],
                    description=row['description'],
                    author=row['author'],
                    published_at=datetime.fromisoformat(row['published_at']) if row['published_at'] else None,
                    language=row['language'],
                    article_length=row['article_length'],
                    data_fetch_via=row['data_fetch_via'],
                    raw_text=row['raw_text'],
                    clean_text=row['clean_text'],
                    content_hash=row['content_hash'],
                    extraction_method=row['extraction_method'],
                    extraction_quality=float(row['extraction_quality']) if row['extraction_quality'] else 0.0,
                    processing_status="extracted"
                )
                db.add(art)
                count += 1
            
            db.commit()
            print(f"Imported {count} articles into PostgreSQL.")
    finally:
        db.close()

if __name__ == "__main__":
    import_csv()
