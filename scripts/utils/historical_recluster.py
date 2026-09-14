import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from ingestion.models.database import SessionLocal, Article, NewsCluster

def full_recluster():
    """Wipes all cluster associations and re-runs clustering incrementally from oldest to newest."""
    db = SessionLocal()
    try:
        print("Wiping existing clusters...")
        db.query(Article).update({Article.cluster_id: None, Article.processing_status: 'extracted'})
        db.query(NewsCluster).delete()
        db.commit()
        print("Clusters wiped. Please run `python embeddings/pipeline.py` to rebuild from scratch.")
    finally:
        db.close()

if __name__ == "__main__":
    full_recluster()
