import csv
import os
from models.database import SessionLocal, Article

def dump_to_csv():
    db = SessionLocal()
    articles = db.query(Article).all()
    
    csv_dir = "retrieved_data"
    os.makedirs(csv_dir, exist_ok=True)
    csv_path = os.path.join(csv_dir, "articles.csv")
    
    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["guid", "outlet_slug", "title", "published_at", "language", "canonical_url", "extraction_method", "clean_text"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for article in articles:
            writer.writerow({
                "guid": article.guid,
                "outlet_slug": article.outlet.slug if article.outlet else "",
                "title": article.title,
                "published_at": article.published_at.isoformat() if article.published_at else "",
                "language": article.language,
                "canonical_url": article.canonical_url,
                "extraction_method": article.extraction_method,
                "clean_text": article.clean_text
            })
            
    print(f"Dumped {len(articles)} articles to {csv_path}")

if __name__ == "__main__":
    dump_to_csv()
