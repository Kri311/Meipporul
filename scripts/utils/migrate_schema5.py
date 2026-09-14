from sqlalchemy import text
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from ingestion.models.database import engine

def migrate():
    cols = [
        "ALTER TABLE articles ADD COLUMN semantic_text_hash VARCHAR",
        "ALTER TABLE articles ADD COLUMN cluster_id INTEGER REFERENCES news_clusters(id)",
        "ALTER TABLE articles ADD COLUMN embedding_model VARCHAR",
        "ALTER TABLE articles ADD COLUMN embedding_created_at TIMESTAMP"
    ]
    
    for col in cols:
        try:
            with engine.begin() as conn:
                conn.execute(text(col))
                print(f"Success: {col}")
        except Exception as e:
            print(f"Failed: {col} -> {e}")

if __name__ == "__main__":
    migrate()
