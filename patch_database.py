import os
import re

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"
db_path = os.path.join(base_dir, "ingestion", "models", "database.py")

with open(db_path, "r", encoding="utf-8") as f:
    content = f.read()

# Add NewsCluster model before Article
cluster_model = """
class NewsCluster(Base):
    \"\"\"Represents a real-world news event cluster\"\"\"
    __tablename__ = "news_clusters"

    id = Column(Integer, primary_key=True, index=True)
    representative_title = Column(String, nullable=False)
    topic = Column(String, nullable=True)
    article_count = Column(Integer, default=1)
    centroid_embedding = Column(Vector(768), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    articles = relationship("Article", back_populates="cluster")
"""

if "class NewsCluster" not in content:
    content = content.replace("class Article(Base):", cluster_model + "\nclass Article(Base):")

# Update Article model with new fields
article_fields = """    
    # 3. Text & Content
    raw_text = Column(Text, nullable=True)
    clean_text = Column(Text, nullable=True)
    content_hash = Column(String, nullable=True)
    semantic_text_hash = Column(String, nullable=True)
    
    extraction_method = Column(String, nullable=True) # 'rss' or 'trafilatura'
    extraction_quality = Column(Float, nullable=True)
    processing_status = Column(String, default="pending") # pending, extracted, embedded, failed
    
    # Cluster relationship
    cluster_id = Column(Integer, ForeignKey("news_clusters.id"), nullable=True)
    cluster = relationship("NewsCluster", back_populates="articles")
    
    # Vector Embedding using pgvector (768 dimensions)
    embedding = Column(Vector(768), nullable=True)
    embedding_model = Column(String, nullable=True)
    embedding_created_at = Column(DateTime, nullable=True)
"""

old_article_fields = """    # 3. Text & Content
    raw_text = Column(Text, nullable=True)
    clean_text = Column(Text, nullable=True)
    content_hash = Column(String, nullable=True)
    
    extraction_method = Column(String, nullable=True) # 'rss' or 'trafilatura'
    extraction_quality = Column(Float, nullable=True)
    processing_status = Column(String, default="pending") # pending, extracted, embedded, failed
    
    # Vector Embedding using pgvector (768 dimensions for Tamil-ai/tamil-embed-base)
    embedding = Column(Vector(768), nullable=True)"""

if "semantic_text_hash" not in content:
    content = content.replace(old_article_fields, article_fields)

with open(db_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Updated database.py")
