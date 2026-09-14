from sqlalchemy import text
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from ingestion.models.database import engine, Base

def migrate():
    Base.metadata.create_all(bind=engine)

    cols = [
        "ALTER TABLE articles ADD COLUMN semantic_text_hash VARCHAR",
        "ALTER TABLE articles ADD COLUMN cluster_id INTEGER REFERENCES news_clusters(id)",
        "ALTER TABLE articles ADD COLUMN embedding_model VARCHAR",
        "ALTER TABLE articles ADD COLUMN embedding_created_at TIMESTAMP"
    ]
    
    for col in cols:
        with engine.begin() as conn:
            try:
                conn.execute(text(col))
                print(f"Success: {col}")
            except Exception as e:
                print(f"Failed: {col}")

if __name__ == "__main__":
    migrate()
