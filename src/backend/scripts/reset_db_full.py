import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(project_root, "src"))

from backend.models.database import SessionLocal, Article, NewsCluster, ClusteringRun, ArticleCluster, engine
from sqlalchemy import text

def reset_db_and_schema():
    print("Running DB migration (adding columns and dropping old clustering data)...")
    
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE news_clusters ADD COLUMN IF NOT EXISTS cluster_key VARCHAR;"))
            conn.execute(text("ALTER TABLE news_clusters ADD COLUMN IF NOT EXISTS algorithm VARCHAR;"))
            conn.execute(text("ALTER TABLE news_clusters ADD COLUMN IF NOT EXISTS algorithm_version VARCHAR;"))
            conn.execute(text("ALTER TABLE news_clusters ADD COLUMN IF NOT EXISTS embedding_model_version VARCHAR;"))
            conn.execute(text("ALTER TABLE news_clusters ADD COLUMN IF NOT EXISTS label VARCHAR;"))
            conn.commit()
            print("Successfully added new columns to news_clusters.")
        except Exception as e:
            print(f"Error altering news_clusters: {e}")
            conn.rollback()

    from backend.models.database import Base
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Delete ArticleClusters and ClusteringRuns first
        db.query(ArticleCluster).delete()
        db.query(ClusteringRun).delete()
        
        # Reset Articles
        articles = db.query(Article).all()
        for article in articles:
            article.named_entities = None
            article.embedding = None
            article.embedding_model = None
            article.embedding_created_at = None
            article.cluster_id = None
            if article.processing_status in ["embedded", "completed"]:
                article.processing_status = "extracted"
        
        db.commit()  # commit the article changes (removing foreign keys)
        
        # Now delete NewsClusters
        db.query(NewsCluster).delete()
        db.commit()
        
        print(f"Successfully reset embeddings, NER, and clusters for {len(articles)} articles.")
    except Exception as e:
        db.rollback()
        print(f"Database reset failed: {e}")
    finally:
        db.close()

if __name__ == '__main__':
    reset_db_and_schema()
