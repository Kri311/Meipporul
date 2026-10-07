"""
Veritas Lens — Semantic Processing Pipeline
=============================================
Orchestrates embedding generation and clustering using the modular
EmbeddingService and ClusteringService.

This script is called by scripts/run_semantics_and_ner.sh.
"""

import os
import sys
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from backend.semantic_processing.embedding_service import EmbeddingService, run_embedding_pipeline
from backend.semantic_processing.clustering_service import ClusteringService, run_clustering_pipeline

# Logging
log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(log_dir, 'pipeline.log'),
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("SemanticPipeline")


def run_pipeline():
    """Run the full semantic pipeline: embeddings → clustering."""
    logger.info("=" * 60)
    logger.info("Starting Semantic Pipeline (Embeddings + Clustering)")
    logger.info("=" * 60)

    # Step 1: Generate embeddings for all pending articles
    logger.info("[Step 1/2] Generating embeddings...")
    embedding_svc = EmbeddingService()
    total_embedded = embedding_svc.process_pending_articles()
    logger.info(f"[Step 1/2] Embedded {total_embedded} articles.")

    # Step 2: Run batch clustering (DBSCAN + Agglomerative)
    if total_embedded > 0:
        logger.info("[Step 2/2] Running batch clustering...")
        clustering_svc = ClusteringService()
        clustering_svc.run_all()
        logger.info("[Step 2/2] Clustering complete.")
    else:
        logger.info("[Step 2/2] No new embeddings — skipping clustering.")

    logger.info("Semantic Pipeline complete.")


if __name__ == "__main__":
    run_pipeline()
