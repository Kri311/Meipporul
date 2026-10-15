import sys
import os
sys.path.insert(0, os.path.join(os.path.abspath("."), "src"))
from backend.models.database import SessionLocal, Article

db = SessionLocal()
last_art = db.query(Article).order_by(Article.id.desc()).first()
print("RAW DB OUTPUT:")
print(last_art.clean_text[:200])
