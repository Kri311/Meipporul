import os
import sys
import time
import hashlib
from datetime import datetime, timedelta
import numpy as np

# Configuration
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
CLUSTER_LOOKBACK_HOURS = int(os.getenv("CLUSTER_LOOKBACK_HOURS", "72"))
CLUSTER_SIMILARITY_THRESHOLD = float(os.getenv("CLUSTER_SIMILARITY_THRESHOLD", "0.85"))

# Add parent to path to import ingestion
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ingestion.models.database import SessionLocal, Article, NewsCluster

_model = None

def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[Pipeline] Loading {EMBEDDING_MODEL_NAME} on {device}...")
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME, device=device)
    return _model

def generate_semantic_text(article: Article) -> str:
    """Format the text to be embedded (title + clean_text)"""
    title = article.title.strip() if article.title else ""
    body = article.clean_text.strip() if article.clean_text else ""
    return f"{title} {body}".strip()

def process_batch():
    db = SessionLocal()
    try:
        # Find articles that need embedding
        articles = db.query(Article).filter(
            Article.clean_text.isnot(None),
            Article.clean_text != "",
            Article.processing_status != "embedded",
            Article.embedding.is_(None)
        ).limit(EMBEDDING_BATCH_SIZE).all()

        if not articles:
            print("[Pipeline] No pending articles found.")
            return False

        print(f"[Pipeline] Processing {len(articles)} articles...")
        
        texts = []
        hashes = []
        for article in articles:
            text = generate_semantic_text(article)
            texts.append(text)
            hashes.append(hashlib.md5(text.encode('utf-8')).hexdigest())

        # Generate Embeddings
        model = get_model()
        embeddings = model.encode(texts, batch_size=EMBEDDING_BATCH_SIZE, normalize_embeddings=True)
        
        # Incremental Clustering
        lookback_time = datetime.utcnow() - timedelta(hours=CLUSTER_LOOKBACK_HOURS)
        
        for i, article in enumerate(articles):
            emb_list = embeddings[i].tolist()
            
            # Save embedding
            article.embedding = emb_list
            article.semantic_text_hash = hashes[i]
            article.embedding_model = EMBEDDING_MODEL_NAME
            article.embedding_created_at = datetime.utcnow()
            article.processing_status = "embedded"
            
            # Clustering via pgvector similarity search
            # Find the most similar article within the lookback window
            # <=> is cosine distance for pgvector
            # Distance = 1 - CosineSimilarity. So threshold 0.85 means distance <= 0.15
            max_distance = 1.0 - CLUSTER_SIMILARITY_THRESHOLD
            
            # We look for any article with an assigned cluster that is similar enough
            similar_article = db.query(Article).filter(
                Article.id != article.id,
                Article.cluster_id.isnot(None),
                Article.published_at >= lookback_time,
                Article.embedding.cosine_distance(emb_list) <= max_distance
            ).order_by(Article.embedding.cosine_distance(emb_list)).first()
            
            if similar_article:
                # Join existing cluster
                article.cluster_id = similar_article.cluster_id
                cluster = db.query(NewsCluster).get(article.cluster_id)
                cluster.article_count += 1
                cluster.updated_at = datetime.utcnow()
                print(f"[Pipeline] Joined Cluster {cluster.id} (Similarity match)")
            else:
                # Create new cluster
                new_cluster = NewsCluster(
                    representative_title=article.title,
                    article_count=1,
                    centroid_embedding=emb_list
                )
                db.add(new_cluster)
                db.flush() # get ID
                article.cluster_id = new_cluster.id
                print(f"[Pipeline] Created New Cluster {new_cluster.id}")
                
        db.commit()
        return True
        
    except Exception as e:
        db.rollback()
        print(f"[Pipeline] Error: {e}")
        raise
    finally:
        db.close()

def run_pipeline():
    print("Starting Semantic Pipeline...")
    while True:
        has_more = process_batch()
        if not has_more:
            break

if __name__ == "__main__":
    run_pipeline()
