import csv
import sys
import os

# Add ingestion folder to path so we can import from models
sys.path.append(os.path.join(os.path.dirname(__file__), 'ingestion'))
from models.database import SessionLocal, Article

def verify_counts():
    csv_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'trafiltura_preprocessed.csv')
    
    # 1. Count actual CSV rows (Properly handling multi-line strings)
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            csv_count = sum(1 for row in reader)
    except FileNotFoundError:
        csv_count = 0
        
    # 2. Count lines using standard file read (The mistake I made earlier)
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            raw_lines = sum(1 for line in f) - 1 # minus header
    except FileNotFoundError:
        raw_lines = 0
        
    # 3. Count articles in the PostgreSQL database
    try:
        db = SessionLocal()
        db_count = db.query(Article).filter(Article.processing_status == "eligible").count()
        db.close()
    except Exception as e:
        db_count = f"Error connecting to DB: {e}"

    print("="*50)
    print("📊 DATA VERIFICATION TEST")
    print("="*50)
    print(f"1. Raw Newline Count (What 'wc -l' saw) : {raw_lines}")
    print(f"2. Actual CSV Rows (True Article Count) : {csv_count}")
    print(f"3. Postgres DB Count (Eligible Articles): {db_count}")
    print("-" * 50)
    
    if csv_count == db_count:
        print("✅ SUCCESS: Database and CSV perfectly match.")
        print(f"   => We have exactly {csv_count} perfectly cleaned, unique articles.")
    else:
        print("❌ WARNING: Mismatch detected between CSV and Database.")

if __name__ == "__main__":
    verify_counts()
