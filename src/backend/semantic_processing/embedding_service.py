import os
import sys
import time
import hashlib
from datetime import datetime
import numpy as np
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from backend.models.database import SessionLocal, Article

log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(log_dir, 'pipeline.log'),
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("EmbeddingService")

# Configuration
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "Tamil-ai/tamil-embed-base")
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
EMBEDDING_DIM = 768
MAX_TEXT_LENGTH = 3000

class EmbeddingService:
    """Handles article embedding generation with text hashing and metadata tracking."""
    
    def __init__(self):
        self._model = None
    
    def _get_model(self):
        """Lazy singleton model loading."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loading {EMBEDDING_MODEL_NAME} on {device}...")
            self._model = SentenceTransformer(EMBEDDING_MODEL_NAME, device=device)
        return self._model
    
    @staticmethod
    def generate_semantic_text(article) -> str:
        """Build the text to embed: title + clean_text, truncated."""
        title = (article.title or "").strip()
        body = (article.clean_text or "").strip()
        text = f"{title} {body}".strip()
        return text[:MAX_TEXT_LENGTH]
    
    @staticmethod
    def compute_text_hash(text: str) -> str:
        """SHA-256 hash of the semantic text for change detection."""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
    
    def needs_reembedding(self, article) -> bool:
        """Check if the article content has changed since last embedding."""
        if article.embedding is None:
            return True
        text = self.generate_semantic_text(article)
        current_hash = self.compute_text_hash(text)
        return current_hash != article.semantic_text_hash
    
    def embed_batch(self, texts: list) -> np.ndarray:
        """Generate normalized embeddings for a batch of texts."""
        model = self._get_model()
        embeddings = model.encode(
            texts, 
            batch_size=EMBEDDING_BATCH_SIZE, 
            normalize_embeddings=True,
            show_progress_bar=False
        )
        return embeddings
    
    def process_pending_articles(self, limit: int = None) -> int:
        """Process all pending articles that need embedding."""
        db = SessionLocal()
        total_embedded = 0
        try:
            while True:
                # Find articles needing embedding
                query = db.query(Article).filter(
                    Article.clean_text.isnot(None),
                    Article.clean_text != "",
                    Article.embedding.is_(None)
                ).filter(
                    Article.processing_status.in_(["extracted", "eligible", "pending"])
                )
                
                batch_limit = min(limit - total_embedded, EMBEDDING_BATCH_SIZE) if limit else EMBEDDING_BATCH_SIZE
                articles = query.limit(batch_limit).all()
                
                if not articles:
                    break
                
                texts = []
                hashes = []
                for article in articles:
                    text = self.generate_semantic_text(article)
                    texts.append(text)
                    hashes.append(self.compute_text_hash(text))
                
                start = time.time()
                embeddings = self.embed_batch(texts)
                elapsed = time.time() - start
                
                for i, article in enumerate(articles):
                    article.embedding = embeddings[i].tolist()
                    article.semantic_text_hash = hashes[i]
                    article.embedding_model = EMBEDDING_MODEL_NAME
                    article.embedding_created_at = datetime.utcnow()
                    article.processing_status = "embedded"
                
                db.commit()
                total_embedded += len(articles)
                logger.info(f"Embedded {len(articles)} articles in {elapsed:.2f}s ({len(articles)/elapsed:.1f} art/sec). Total: {total_embedded}")
                
                if limit and total_embedded >= limit:
                    break
                    
        except Exception as e:
            db.rollback()
            logger.error(f"Embedding error: {e}")
            raise
        finally:
            db.close()
        
        return total_embedded

def run_embedding_pipeline():
    """Entry point for standalone execution."""
    service = EmbeddingService()
    total = service.process_pending_articles()
    logger.info(f"Embedding pipeline complete. Total embedded: {total}")

if __name__ == "__main__":
    run_embedding_pipeline()
