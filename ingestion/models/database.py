import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, JSON, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from pgvector.sqlalchemy import Vector

# Get database URL from environment, default to local if not set
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://veritas_admin:veritas_secret_password@localhost:5432/veritas_lens")

# Create SQLAlchemy Engine and Session
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Outlet(Base):
    """Represents a news outlet (e.g., The Hindu Tamil, Dinamalar)"""
    __tablename__ = "outlets"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    language_set = Column(String) # e.g., 'ta,en'
    homepage_url = Column(String)
    orientation_bucket = Column(String, index=True) # IND, CON, DRV, OPP
    orientation_confidence = Column(Float)
    active = Column(Boolean, default=True)

    # Relationships
    rss_feeds = relationship("RssFeed", back_populates="outlet")
    articles = relationship("Article", back_populates="outlet")


class RssFeed(Base):
    """Represents a specific RSS feed URL belonging to an outlet"""
    __tablename__ = "rss_feeds"

    id = Column(Integer, primary_key=True, index=True)
    outlet_id = Column(Integer, ForeignKey("outlets.id"), nullable=False)
    feed_url = Column(String, unique=True, nullable=False)
    category = Column(String)
    enabled = Column(Boolean, default=True)
    last_success_at = Column(DateTime, nullable=True)
    consecutive_failures = Column(Integer, default=0)

    # Relationships
    outlet = relationship("Outlet", back_populates="rss_feeds")
    feed_runs = relationship("FeedRun", back_populates="rss_feed")
    articles = relationship("Article", back_populates="rss_feed")


class FeedRun(Base):
    """Tracks every time our Celery worker attempts to fetch an RSS feed"""
    __tablename__ = "feed_runs"

    id = Column(Integer, primary_key=True, index=True)
    rss_feed_id = Column(Integer, ForeignKey("rss_feeds.id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    http_status = Column(Integer, nullable=True)
    entries_seen = Column(Integer, default=0)
    entries_new = Column(Integer, default=0)
    entries_failed = Column(Integer, default=0)
    error_code = Column(String, nullable=True)

    # Relationships
    rss_feed = relationship("RssFeed", back_populates="feed_runs")


class Article(Base):
    """The core table storing the raw, cleaned, and embedded news article"""
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    outlet_id = Column(Integer, ForeignKey("outlets.id"), nullable=False)
    rss_feed_id = Column(Integer, ForeignKey("rss_feeds.id"), nullable=True)
    guid = Column(String, unique=True, index=True, nullable=False) # RSS unique ID
    canonical_url = Column(String, nullable=False)
    original_url = Column(String, nullable=False)
    
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    author = Column(String, nullable=True)
    published_at = Column(DateTime, nullable=True)
    
    # NLP and Language fields
    language = Column(String(10), index=True)      # 'ta', 'en', 'mixed'
    article_length = Column(String(20))            # 'short', 'medium', 'long'
    data_fetch_via = Column(String(50), default="Native RSS") # 'Native RSS', 'Google News RSS'
    
    # 3. Text & Content
    raw_text = Column(Text, nullable=True)
    clean_text = Column(Text, nullable=True)
    content_hash = Column(String, nullable=True)
    
    extraction_method = Column(String, nullable=True) # 'rss' or 'trafilatura'
    extraction_quality = Column(Float, nullable=True)
    processing_status = Column(String, default="pending") # pending, extracted, embedded, failed
    
    # Vector Embedding using pgvector (768 dimensions for Tamil-ai/tamil-embed-base)
    embedding = Column(Vector(768), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    outlet = relationship("Outlet", back_populates="articles")
    rss_feed = relationship("RssFeed", back_populates="articles")


def init_db():
    """Initializes the database schema and pgvector extension"""
    with engine.connect() as conn:
        # Create the pgvector extension if it doesn't exist
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")

if __name__ == "__main__":
    from sqlalchemy import text
    init_db()
