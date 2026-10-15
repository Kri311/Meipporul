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
import argparse

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


def run_pipeline(reembed_all=False):
    """Run embedding generation and clustering over current article rows."""
    logger.info("=" * 60)
    logger.info("Starting Semantic Pipeline (Embeddings + Clustering)")
    logger.info("=" * 60)

    # Step 1: Generate embeddings for all pending articles
    logger.info("[Step 1/2] Generating embeddings...")
    embedding_svc = EmbeddingService()
    total_embedded = embedding_svc.process_pending_articles(reembed_all=reembed_all)
    logger.info(f"[Step 1/2] Embedded {total_embedded} articles.")

    # Run clustering even when no vectors changed: this also recovers clusters
    # after a prior interrupted run or a fresh DB whose vectors already exist.
    logger.info("[Step 2/2] Running DBSCAN event clustering...")
    clustering_svc = ClusteringService()
    clustering_svc.run_all()
    logger.info("[Step 2/2] Clustering complete.")

    logger.info("Semantic Pipeline complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate E5 embeddings and cluster events")
    parser.add_argument("--reembed-all", action="store_true",
                        help="recompute embeddings for every article with clean text")
    args = parser.parse_args()
    run_pipeline(reembed_all=args.reembed_all)
