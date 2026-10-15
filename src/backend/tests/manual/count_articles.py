import sys, os
sys.path.insert(0, os.path.join(os.path.abspath("."), "src"))
from backend.models.database import SessionLocal, Article
from sqlalchemy import extract
db = SessionLocal()
c = db.query(Article).filter(extract('year', Article.published_at) == 2026).count()
print(c)
