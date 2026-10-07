import os
import sys
import time
import numpy as np
import logging
from datetime import datetime
from typing import Optional, Tuple, List, Any
from sklearn.cluster import DBSCAN, AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_distances

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from backend.models.database import (
    SessionLocal, Article, NewsCluster, ClusteringRun, ArticleCluster
)

# Configuration
DBSCAN_EPS = float(os.getenv("DBSCAN_EPS", "0.15"))           # cosine distance threshold
DBSCAN_MIN_SAMPLES = int(os.getenv("DBSCAN_MIN_SAMPLES", "2"))
AGGLO_DISTANCE_THRESHOLD = float(os.getenv("AGGLO_DISTANCE_THRESHOLD", "0.15"))
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "Tamil-ai/tamil-embed-base")

# Logging setup
log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(log_dir, 'pipeline.log'),
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ClusteringService")

class ClusteringService:
    """Runs batch clustering algorithms on embedded articles."""
    
    def _fetch_embedded_articles(self, db: Any) -> List[Any]:
        """Fetch all articles that have embeddings."""
        articles = db.query(Article).filter(
            Article.embedding.isnot(None)
        ).all()
        return articles
    
    def _compute_centroid(self, embeddings: np.ndarray) -> np.ndarray:
        """Compute the L2-normalized centroid of a set of embeddings."""
        centroid = np.mean(embeddings, axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm
        return centroid
    
    def _save_results(self, db: Any, labels: np.ndarray, articles: List[Any], 
                      embeddings: np.ndarray, run: Any, algorithm: str) -> Tuple[int, int]:
        """Save clustering results to news_clusters and article_clusters tables."""
        unique_labels = set(labels)
        unique_labels.discard(-1)  # -1 = noise in DBSCAN
        
        cluster_map = {}  # local_label -> NewsCluster.id
        
        for label in sorted(unique_labels):
            # Find articles in this cluster
            member_indices = [i for i, l in enumerate(labels) if l == label]
            member_embeddings = embeddings[member_indices]
            centroid = self._compute_centroid(member_embeddings)
            
            representative_article = articles[member_indices[0]]
            
            cluster = NewsCluster(
                representative_title=representative_article.title,
                cluster_key=f"{algorithm}_run{run.id}_cluster{label}",
                label=None,  # to be filled by topic_modeling later
                algorithm=algorithm,
                algorithm_version="1.0",
                embedding_model_version=EMBEDDING_MODEL_NAME,
                article_count=len(member_indices),
                centroid_embedding=centroid.tolist(),
            )
            db.add(cluster)
            db.flush()
            cluster_map[label] = cluster.id
        
        # Save article-cluster assignments
        noise_count = 0
        for i, label in enumerate(labels):
            if label == -1:
                noise_count += 1
                continue
            
            cluster_id = cluster_map[label]
            
            # Also update the article's direct cluster_id for backward compatibility
            articles[i].cluster_id = cluster_id
            
            # Compute similarity to centroid
            member_indices = [j for j, l in enumerate(labels) if l == label]
            centroid = self._compute_centroid(embeddings[member_indices])
            sim = float(np.dot(embeddings[i], centroid))
            
            ac = ArticleCluster(
                article_id=articles[i].id,
                cluster_id=cluster_id,
                clustering_run_id=run.id,
                similarity_score=round(sim, 4),
            )
            db.add(ac)
        
        # Update run metadata
        run.num_clusters = len(unique_labels)
        run.num_noise = noise_count
        
        db.commit()
        return len(unique_labels), noise_count
    
    def run_dbscan(self, eps: Optional[float] = None, min_samples: Optional[int] = None) -> Optional[Any]:
        """Run DBSCAN clustering on all embedded articles."""
        eps = eps or DBSCAN_EPS
        min_samples = min_samples or DBSCAN_MIN_SAMPLES
        
        db = SessionLocal()
        try:
            articles = self._fetch_embedded_articles(db)
            if len(articles) < min_samples:
                logger.info(f"Not enough articles ({len(articles)}) for DBSCAN (min_samples={min_samples})")
                return None
            
            logger.info(f"Running DBSCAN on {len(articles)} articles (eps={eps}, min_samples={min_samples})...")
            
            embeddings = np.array([a.embedding for a in articles])
            
            # Compute cosine distance matrix
            start = time.time()
            distance_matrix = cosine_distances(embeddings)
            
            clusterer = DBSCAN(eps=eps, min_samples=min_samples, metric='precomputed')
            labels = clusterer.fit_predict(distance_matrix)
            elapsed = time.time() - start
            
            # Create clustering run record
            run = ClusteringRun(
                algorithm="dbscan",
                algorithm_version="sklearn",
                embedding_model=EMBEDDING_MODEL_NAME,
                embedding_model_version=EMBEDDING_MODEL_NAME,
                parameters={"eps": eps, "min_samples": min_samples},
                num_articles=len(articles),
            )
            db.add(run)
            db.flush()
            
            num_clusters, num_noise = self._save_results(db, labels, articles, embeddings, run, "dbscan")
            
            logger.info(f"DBSCAN complete in {elapsed:.2f}s: {num_clusters} clusters, {num_noise} noise points")
            return run
            
        except Exception as e:
            db.rollback()
            logger.error(f"DBSCAN error: {e}")
            raise
        finally:
            db.close()
    
    def run_agglomerative(self, distance_threshold: Optional[float] = None) -> Optional[Any]:
        """Run Agglomerative Clustering on all embedded articles."""
        distance_threshold = distance_threshold or AGGLO_DISTANCE_THRESHOLD
        
        db = SessionLocal()
        try:
            articles = self._fetch_embedded_articles(db)
            if len(articles) < 2:
                logger.info(f"Not enough articles ({len(articles)}) for Agglomerative Clustering")
                return None
            
            logger.info(f"Running Agglomerative Clustering on {len(articles)} articles (threshold={distance_threshold})...")
            
            embeddings = np.array([a.embedding for a in articles])
            
            start = time.time()
            distance_matrix = cosine_distances(embeddings)
            
            clusterer = AgglomerativeClustering(
                n_clusters=None,
                distance_threshold=distance_threshold,
                metric='precomputed',
                linkage='average'
            )
            labels = clusterer.fit_predict(distance_matrix)
            elapsed = time.time() - start
            
            run = ClusteringRun(
                algorithm="agglomerative",
                algorithm_version="sklearn",
                embedding_model=EMBEDDING_MODEL_NAME,
                embedding_model_version=EMBEDDING_MODEL_NAME,
                parameters={"distance_threshold": distance_threshold, "linkage": "average"},
                num_articles=len(articles),
            )
            db.add(run)
            db.flush()
            
            num_clusters, num_noise = self._save_results(db, labels, articles, embeddings, run, "agglomerative")
            
            logger.info(f"Agglomerative complete in {elapsed:.2f}s: {num_clusters} clusters, {num_noise} noise points")
            return run
            
        except Exception as e:
            db.rollback()
            logger.error(f"Agglomerative error: {e}")
            raise
        finally:
            db.close()
    
    def run_all(self) -> Tuple[Optional[Any], Optional[Any]]:
        """Run all clustering algorithms sequentially."""
        logger.info("Starting clustering pipeline...")
        dbscan_run = self.run_dbscan()
        agglo_run = self.run_agglomerative()
        logger.info("Clustering pipeline complete.")
        return dbscan_run, agglo_run


def run_clustering_pipeline() -> None:
    """Entry point for standalone execution."""
    service = ClusteringService()
    service.run_all()

if __name__ == "__main__":
    run_clustering_pipeline()
