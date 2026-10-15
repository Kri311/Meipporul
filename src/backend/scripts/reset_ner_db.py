"""Queue existing cleaned articles for NER reprocessing.

This intentionally changes only NER fields and processing status in PostgreSQL.
It does not delete CSV exports, embeddings, clusters, or model artifacts.
"""

import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(project_root, "src"))

from backend.models.database import Article, SessionLocal
from sqlalchemy import or_


def reset_ner():
    db = SessionLocal()
    try:
        articles = db.query(Article).filter(
            Article.clean_text.isnot(None),
            Article.clean_text != "",
            or_(
                Article.named_entities.isnot(None),
                Article.linked_entities.isnot(None),
                Article.processing_status == "completed",
            ),
        ).all()
        for article in articles:
            article.named_entities = None
            article.linked_entities = None
            article.processing_status = "embedded"
        db.commit()
        print(f"Queued {len(articles)} cleaned articles for NER reprocessing.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    reset_ner()
