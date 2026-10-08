"""Celery adapter for the shared multilingual embedding implementation."""

from backend.ingestion.main import celery_app
from backend.semantic_processing.embedding_service import EmbeddingService


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def generate_embeddings_batch(self):
    """Embed up to 50 changed articles using the canonical 768-d model."""
    try:
        count = EmbeddingService().process_pending_articles(limit=50)
        return {"status": "success", "embedded_count": count}
    except Exception as exc:
        raise self.retry(exc=exc)
