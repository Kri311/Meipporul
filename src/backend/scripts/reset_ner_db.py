import sys
import os
import glob

# Ensure backend modules can be loaded
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(project_root, "src"))

from backend.models.database import SessionLocal, Article

def reset_ner():
    print("Connecting to database...")
    db = SessionLocal()
    try:
        articles = db.query(Article).filter(Article.named_entities.isnot(None)).all()
        count = len(articles)
        for article in articles:
            article.named_entities = None
            if article.processing_status == "completed":
                article.processing_status = "embedded" # Reset to just before NER
        db.commit()
        print(f"Successfully reset NER fields for {count} articles in PostgreSQL database.")
    except Exception as e:
        db.rollback()
        print(f"Database reset failed: {e}")
    finally:
        db.close()
        
    print("\nCleaning up old CSV files...")
    csv_paths = [
        os.path.join(project_root, "src", "backend", "ner_pipeline", "zero_shot", "data", "*.csv"),
        os.path.join(project_root, "retrieved_data", "*.csv")
    ]
    
    cleaned_count = 0
    for path_pattern in csv_paths:
        for f in glob.glob(path_pattern):
            try:
                os.remove(f)
                print(f"  Deleted: {f}")
                cleaned_count += 1
            except Exception as e:
                print(f"  Could not delete {f}: {e}")
                
    print(f"Deleted {cleaned_count} CSV files.")

if __name__ == '__main__':
    reset_ner()
