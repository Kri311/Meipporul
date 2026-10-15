import os
import sys
import time
import re
from datetime import datetime
import numpy as np
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from backend.models.database import SessionLocal, Article
from backend.ingestion.tasks.text_cleaning import parse_clean_article

log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(log_dir, 'pipeline.log'),
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("EmbeddingService")

# Configuration
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-base")
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
EMBEDDING_DIM = 768
MAX_CHUNK_CHARS = 1800
HEADLINE_VECTOR_WEIGHT = float(os.getenv("HEADLINE_VECTOR_WEIGHT", "0.65"))

class EmbeddingService:
    """Generate and persist multilingual article embeddings."""
    
    def __init__(self):
        self._model = None
        self._device = None
    
    def _get_model(self):
        """Lazy singleton model loading."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            import torch
            requested_device = os.getenv("EMBEDDING_DEVICE", "auto").casefold()
            device = self._device or ("cuda" if requested_device == "cuda" else "cpu")
            if self._device is None and requested_device == "auto":
                device = "cuda" if torch.cuda.is_available() else "cpu"
            if device == "cuda" and not torch.cuda.is_available():
                logger.warning("CUDA was requested for embeddings but is unavailable; using CPU")
                device = "cpu"
            logger.info(f"Loading {EMBEDDING_MODEL_NAME} on {device}...")
            load_options = {}
            if os.getenv("HF_HUB_OFFLINE", "0").casefold() in {"1", "true", "yes"}:
                load_options["local_files_only"] = True
            self._model = SentenceTransformer(EMBEDDING_MODEL_NAME, device=device, **load_options)
            self._device = device
        return self._model
    
    @staticmethod
    def generate_semantic_text(article) -> str:
        """Build a versioned, separable headline/body representation, never JSON."""
        title, body = parse_clean_article(article.clean_text, article.title)
        title = (article.title or title).strip()
        return f"semantic-v2\nheadline: {title}\nbody: {body}"

    @staticmethod
    def _chunk_passage(text: str) -> list:
        """Split long articles at sentence/word boundaries so every part contributes."""
        prefix = "passage: "
        body = text[len(prefix):] if text.startswith(prefix) else text
        sentences = re.split(r"(?<=[.!?।])\s+", body)
        chunks, current = [], ""
        for sentence in sentences:
            words = sentence.split()
            pieces, piece = [], ""
            for word in words:
                if piece and len(piece) + len(word) + 1 > MAX_CHUNK_CHARS:
                    pieces.append(piece)
                    piece = word
                else:
                    piece = f"{piece} {word}".strip()
            if piece:
                pieces.append(piece)
            for part in pieces:
                if current and len(current) + len(part) + 1 > MAX_CHUNK_CHARS:
                    chunks.append(prefix + current)
                    current = part
                else:
                    current = f"{current} {part}".strip()
        if current:
            chunks.append(prefix + current)
        return chunks or [text]
    
    def needs_reembedding(self, article) -> bool:
        """Check whether this row lacks a vector from the configured E5 model.

        Text normalization clears the vector when its input changes. This
        avoids a separate semantic_text_hash column while retaining correct
        incremental re-embedding behavior.
        """
        return article.embedding is None or article.embedding_model != EMBEDDING_MODEL_NAME
    
    def embed_batch(self, texts: list) -> np.ndarray:
        """Combine headline-focused and body-context vectors per article.

        Averaging chunks from the entire body dilutes the headline on long
        stories, which can make unrelated coverage look similar. A weighted
        headline/body vector keeps event identity anchored to what the story
        is actually about while retaining article context.
        """
        model = self._get_model()
        components = []
        flat_passages = []
        for text in texts:
            headline = ""
            body = text
            if text.startswith("semantic-v2\n"):
                fields = text.split("\n", 2)
                headline = fields[1].removeprefix("headline: ").strip() if len(fields) > 1 else ""
                body = fields[2].removeprefix("body: ").strip() if len(fields) > 2 else ""
            headline_index = len(flat_passages)
            flat_passages.append(f"passage: {headline or body}")
            body_chunks = self._chunk_passage(f"passage: {body}") if body else []
            body_start = len(flat_passages)
            flat_passages.extend(body_chunks)
            components.append((headline_index, body_start, len(body_chunks)))

        try:
            encoded = model.encode(
                flat_passages,
                batch_size=EMBEDDING_BATCH_SIZE,
                normalize_embeddings=True,
                show_progress_bar=False
            )
        except RuntimeError as exc:
            import torch
            if self._device != "cuda" or "out of memory" not in str(exc).casefold():
                raise
            logger.warning("CUDA ran out of memory embedding a batch; retrying on CPU")
            self._model = None
            self._device = "cpu"
            import gc
            gc.collect()
            torch.cuda.empty_cache()
            encoded = self._get_model().encode(
                flat_passages,
                batch_size=EMBEDDING_BATCH_SIZE,
                normalize_embeddings=True,
                show_progress_bar=False
            )
        article_embeddings = []
        for headline_index, body_start, body_count in components:
            headline_vector = encoded[headline_index]
            if body_count:
                body_vector = np.mean(encoded[body_start:body_start + body_count], axis=0)
                body_norm = np.linalg.norm(body_vector)
                if body_norm:
                    body_vector = body_vector / body_norm
                vector = HEADLINE_VECTOR_WEIGHT * headline_vector + (1 - HEADLINE_VECTOR_WEIGHT) * body_vector
            else:
                vector = headline_vector
            norm = np.linalg.norm(vector)
            article_embeddings.append(vector / norm if norm else vector)
        return np.asarray(article_embeddings)
    
    def process_pending_articles(self, limit: int = None, reembed_all: bool = False) -> int:
        """Process missing/stale vectors, or refresh every clean article on request."""
        db = SessionLocal()
        total_embedded = 0
        last_seen_id = 0
        try:
            while True:
                if limit is not None and total_embedded >= limit:
                    break
                # Find articles needing embedding
                query = db.query(Article).filter(
                    Article.clean_text.isnot(None),
                    Article.clean_text != "",
                    Article.id > last_seen_id,
                )
                batch_limit = min(limit - total_embedded, EMBEDDING_BATCH_SIZE) if limit else EMBEDDING_BATCH_SIZE
                page = query.order_by(Article.id).limit(500).all()
                if not page:
                    break
                last_seen_id = page[-1].id
                candidates = page if reembed_all else [a for a in page if self.needs_reembedding(a)]
                articles = candidates[:batch_limit]

                if not articles:
                    continue
                
                texts = []
                for article in articles:
                    text = self.generate_semantic_text(article)
                    texts.append(text)
                
                start = time.time()
                embeddings = self.embed_batch(texts)
                elapsed = time.time() - start
                
                for i, article in enumerate(articles):
                    article.embedding = embeddings[i].tolist()
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

def run_embedding_pipeline(reembed_all=False):
    """Entry point for standalone execution."""
    service = EmbeddingService()
    total = service.process_pending_articles(reembed_all=reembed_all)
    logger.info(f"Embedding pipeline complete. Total embedded: {total}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate E5 embeddings for articles")
    parser.add_argument("--reembed-all", action="store_true",
                        help="recompute vectors for every article with clean text")
    args = parser.parse_args()
    run_embedding_pipeline(reembed_all=args.reembed_all)
