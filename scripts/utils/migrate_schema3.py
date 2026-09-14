from sqlalchemy import text
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from ingestion.models.database import engine, Base

def migrate():
    # 1. Create tables (news_clusters)
    print("Creating all tables via SQLAlchemy...")
    Base.metadata.create_all(bind=engine)

    # 2. Add columns
    with engine.begin() as conn:
        print("Adding new columns to articles table...")
        cols = [
            "ALTER TABLE articles ADD COLUMN semantic_text_hash VARCHAR",
            "ALTER TABLE articles ADD COLUMN cluster_id INTEGER REFERENCES news_clusters(id)",
            "ALTER TABLE articles ADD COLUMN embedding_model VARCHAR",
            "ALTER TABLE articles ADD COLUMN embedding_created_at TIMESTAMP"
        ]
        for col in cols:
            try:
                conn.execute(text(col))
                print(f"Success: {col}")
            except Exception as e:
                print(f"Failed: {col} -> {e}")

if __name__ == "__main__":
    migrate()
