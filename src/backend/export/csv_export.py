import csv
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from backend.models.database import SessionLocal, Article, NewsCluster

CSV_FIELDNAMES = [
    "content_hash", "guid", "outlet_slug", "title", "description",
    "author", "published_at", "language", "article_length",
    "data_fetch_via", "canonical_url", "extraction_method",
    "extraction_quality", "processing_status", "raw_text", "clean_text", "topic",
    "cluster_id", "semantic_text_hash", "named_entities", "embedding"
]

def export_to_csv(output_path=os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "data", "raw_processed.csv")):
    db = SessionLocal()
    try:
        articles = db.query(Article).order_by(Article.published_at.desc().nulls_last()).all()
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=CSV_FIELDNAMES)
            writer.writeheader()
            
            for article in articles:
                ner_str = json.dumps(article.named_entities, ensure_ascii=False) if article.named_entities else ""
                # Ensure the embedding is exported as JSON string if exists
                emb_str = json.dumps(article.embedding.tolist() if hasattr(article.embedding, "tolist") else list(article.embedding)) if article.embedding is not None else ""
                
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
                    "topic": article.cluster.topic if article.cluster else "", 
                    "cluster_id": article.cluster_id,
                    "semantic_text_hash": article.semantic_text_hash,
                    "named_entities": ner_str,
                    "embedding": emb_str
                })
        print(f"Exported {len(articles)} articles to {output_path}")
    finally:
        db.close()

if __name__ == "__main__":
    export_to_csv()
