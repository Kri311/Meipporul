"""
Celery task for batch embedding generation using Tamil-ai/tamil-embed-base.

This task is triggered every 2 minutes by Celery Beat and processes
articles with processing_status == 'eligible'.

Model: Tamil-ai/tamil-embed-base (768 dimensions)
- Bilingual model trained on Tamil + English data
- Maps both languages into the same vector space
- No prefix required (unlike E5 models)
"""

from main import celery_app
from models.database import SessionLocal, Article
from sentence_transformers import SentenceTransformer

# Load model lazily at module level so it's loaded once per worker process
MODEL_NAME = "Tamil-ai/tamil-embed-base"
_model = None

def get_model():
    global _model
    if _model is None:
        print(f"[Worker] Loading NLP model {MODEL_NAME} for embeddings...")
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("GPU is required but not available. CPU execution is disabled.")
        _model = SentenceTransformer(MODEL_NAME, device="cuda")
        print(f"[Worker] Model loaded. Output: 768-dimensional embeddings.")
    return _model

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def generate_embeddings_batch(self):
    """
    Finds articles with processing_status == 'eligible',
    generates embeddings using Tamil-ai/tamil-embed-base,
    and updates the database.
    
    This model natively maps both Tamil and English text into
    the same 768-dimensional vector space — no prefix needed.
    """
    db = SessionLocal()
    try:
        # Get up to 50 eligible articles at a time to prevent memory bloat
        articles = db.query(Article).filter(Article.processing_status == "eligible").limit(50).all()
        if not articles:
            return {"status": "no_eligible_articles"}
        
        model = get_model()
        
        texts_to_embed = []
        for article in articles:
            # Combine title and clean_text for a richer semantic representation
            # Tamil-ai/tamil-embed-base does NOT require a "passage:" prefix
            combined_text = f"{article.title}. {article.clean_text}"
            # Truncate extremely long texts to save memory (model max ~512 tokens)
            if len(combined_text) > 3000:
                combined_text = combined_text[:3000]
            texts_to_embed.append(combined_text)
            
        print(f"[Worker] Generating embeddings for {len(texts_to_embed)} articles...")
        # Generate embeddings (L2-normalized for cosine similarity)
        embeddings = model.encode(texts_to_embed, normalize_embeddings=True, convert_to_tensor=False)
        
        # Save to DB
        for i, article in enumerate(articles):
            article.embedding = embeddings[i].tolist()
            article.processing_status = "embedded"
            
        db.commit()
        print(f"[Worker] Successfully saved {len(articles)} embeddings (768d, Tamil-ai/tamil-embed-base).")
        return {"status": "success", "embedded_count": len(articles)}
        
    except Exception as e:
        db.rollback()
        print(f"[Worker] Error generating embeddings: {e}")
        raise self.retry(exc=e)
    finally:
        db.close()
