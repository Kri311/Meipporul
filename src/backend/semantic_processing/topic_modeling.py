import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from backend.models.database import SessionLocal, NewsCluster, Article
from backend.ingestion.tasks.text_cleaning import classify_topic

def classify_all_clusters():
    db = SessionLocal()
    try:
        clusters = db.query(NewsCluster).filter(NewsCluster.topic.is_(None)).all()
        print(f"Classifying {len(clusters)} clusters...")
        
        for cluster in clusters:
            # We can use the representative title and a sample of text from its articles
            articles = db.query(Article).filter(Article.cluster_id == cluster.id).limit(3).all()
            combined_text = cluster.representative_title + " " + " ".join([a.clean_text for a in articles if a.clean_text])
            
            topic = classify_topic(cluster.representative_title, combined_text, outlet_slug="")
            cluster.topic = topic
            
        db.commit()
        print("Topic classification complete.")
    finally:
        db.close()

if __name__ == "__main__":
    classify_all_clusters()
