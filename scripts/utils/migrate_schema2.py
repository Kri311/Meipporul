from sqlalchemy import text
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from ingestion.models.database import engine, Base

def migrate():
    with engine.connect() as conn:
        print("Adding new columns to articles table...")
        try:
            conn.execute(text("ALTER TABLE articles ADD COLUMN semantic_text_hash VARCHAR"))
        except Exception as e:
            print("semantic_text_hash:", e)
        try:
            conn.execute(text("ALTER TABLE articles ADD COLUMN cluster_id INTEGER REFERENCES news_clusters(id)"))
        except Exception as e:
            print("cluster_id:", e)
        try:
            conn.execute(text("ALTER TABLE articles ADD COLUMN embedding_model VARCHAR"))
        except Exception as e:
            print("embedding_model:", e)
        try:
            conn.execute(text("ALTER TABLE articles ADD COLUMN embedding_created_at TIMESTAMP"))
        except Exception as e:
            print("embedding_created_at:", e)
            
        conn.commit()

if __name__ == "__main__":
    migrate()
