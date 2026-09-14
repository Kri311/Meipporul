import csv
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from ingestion.models.database import SessionLocal, Article, NewsCluster

CSV_FIELDNAMES = [
    "content_hash", "guid", "outlet_slug", "title", "description",
    "author", "published_at", "language", "article_length",
    "data_fetch_via", "canonical_url", "extraction_method",
    "extraction_quality", "processing_status", "raw_text", "clean_text", "topic",
    "cluster_id", "semantic_text_hash"
]

def export_to_csv(output_path="data/raw_processed.csv"):
    db = SessionLocal()
    try:
        articles = db.query(Article).all()
        
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=CSV_FIELDNAMES)
            writer.writeheader()
            
            for article in articles:
                writer.writerow({
                    "content_hash": article.content_hash,
                    "guid": article.guid,
                    "outlet_slug": article.outlet.slug if article.outlet else "",
                    "title": article.title,
                    "description": article.description,
                    "author": article.author,
                    "published_at": article.published_at.isoformat() if article.published_at else "",
                    "language": article.language,
                    "article_length": article.article_length,
                    "data_fetch_via": article.data_fetch_via,
                    "canonical_url": article.canonical_url,
                    "extraction_method": article.extraction_method,
                    "extraction_quality": article.extraction_quality,
                    "processing_status": article.processing_status,
                    "raw_text": article.raw_text,
                    "clean_text": article.clean_text,
                    "topic": article.cluster.topic if article.cluster else "", # wait, topic is not on Article model?
                    "cluster_id": article.cluster_id,
                    "semantic_text_hash": article.semantic_text_hash
                })
        print(f"Exported {len(articles)} articles to {output_path}")
    finally:
        db.close()

if __name__ == "__main__":
    export_to_csv()
