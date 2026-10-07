import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, JSON, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from pgvector.sqlalchemy import Vector

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://veritas_admin:veritas@localhost:5432/veritas_lens")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Outlet(Base):
    __tablename__ = "outlets"
    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    language_set = Column(String)
    homepage_url = Column(String)
    orientation_bucket = Column(String, index=True)
    orientation_confidence = Column(Float)
    active = Column(Boolean, default=True)
    rss_feeds = relationship("RssFeed", back_populates="outlet")
    articles = relationship("Article", back_populates="outlet")

class RssFeed(Base):
    __tablename__ = "rss_feeds"
    id = Column(Integer, primary_key=True, index=True)
    outlet_id = Column(Integer, ForeignKey("outlets.id"), nullable=False)
    feed_url = Column(String, unique=True, nullable=False)
    category = Column(String)
    enabled = Column(Boolean, default=True)
    last_success_at = Column(DateTime, nullable=True)
    consecutive_failures = Column(Integer, default=0)
    outlet = relationship("Outlet", back_populates="rss_feeds")
    feed_runs = relationship("FeedRun", back_populates="rss_feed")
    articles = relationship("Article", back_populates="rss_feed")

class FeedRun(Base):
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
    rss_feed = relationship("RssFeed", back_populates="feed_runs")

class NewsCluster(Base):
    __tablename__ = "news_clusters"
    id = Column(Integer, primary_key=True, index=True)
    cluster_key = Column(String, nullable=True, index=True)
    representative_title = Column(String, nullable=False)
    topic = Column(String, nullable=True)
    label = Column(String, nullable=True)
    article_count = Column(Integer, default=1)
    centroid_embedding = Column(Vector(768), nullable=True)
    algorithm = Column(String, nullable=True)
    algorithm_version = Column(String, nullable=True)
    embedding_model_version = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    articles = relationship("Article", back_populates="cluster")

class ClusteringRun(Base):
    """Tracks each clustering execution with its parameters."""
    __tablename__ = "clustering_runs"

    id = Column(Integer, primary_key=True, index=True)
    algorithm = Column(String, nullable=False)        # 'dbscan', 'agglomerative'
    algorithm_version = Column(String, nullable=True)
    embedding_model = Column(String, nullable=False)
    embedding_model_version = Column(String, nullable=True)
    parameters = Column(JSON, nullable=True)           # {'eps': 0.15, 'min_samples': 2}
    num_articles = Column(Integer, default=0)
    num_clusters = Column(Integer, default=0)
    num_noise = Column(Integer, default=0)             # articles not assigned
    created_at = Column(DateTime, default=datetime.utcnow)

    article_clusters = relationship("ArticleCluster", back_populates="clustering_run")

class ArticleCluster(Base):
    """Many-to-many: an article can appear in multiple clustering runs."""
    __tablename__ = "article_clusters"

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey("articles.id"), nullable=False)
    cluster_id = Column(Integer, ForeignKey("news_clusters.id"), nullable=False)
    clustering_run_id = Column(Integer, ForeignKey("clustering_runs.id"), nullable=False)
    similarity_score = Column(Float, nullable=True)    # cosine sim to centroid
    created_at = Column(DateTime, default=datetime.utcnow)

    article = relationship("Article")
    cluster = relationship("NewsCluster")
    clustering_run = relationship("ClusteringRun", back_populates="article_clusters")

class Article(Base):
    __tablename__ = "articles"
    id = Column(Integer, primary_key=True, index=True)
    outlet_id = Column(Integer, ForeignKey("outlets.id"), nullable=False)
    rss_feed_id = Column(Integer, ForeignKey("rss_feeds.id"), nullable=True)
    guid = Column(String, unique=True, index=True, nullable=False)
    canonical_url = Column(String, nullable=False)
    original_url = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    author = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    published_at = Column(DateTime, nullable=True)
    language = Column(String(10), index=True)
    article_length = Column(String(20))
    data_fetch_via = Column(String(50), default="Native RSS")
    raw_text = Column(Text, nullable=True)
    clean_text = Column(Text, nullable=True)
    content_hash = Column(String, nullable=True)
    semantic_text_hash = Column(String, nullable=True)
    extraction_method = Column(String, nullable=True)
    extraction_quality = Column(Float, nullable=True)
    processing_status = Column(String, default="pending")
    cluster_id = Column(Integer, ForeignKey("news_clusters.id"), nullable=True)
    cluster = relationship("NewsCluster", back_populates="articles")
    embedding = Column(Vector(768), nullable=True)
    embedding_model = Column(String, nullable=True)
    embedding_created_at = Column(DateTime, nullable=True)
    named_entities = Column(JSON, nullable=True)
    linked_entities = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    outlet = relationship("Outlet", back_populates="articles")
    rss_feed = relationship("RssFeed", back_populates="articles")

def init_db():
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")

if __name__ == "__main__":
    from sqlalchemy import text
    init_db()
