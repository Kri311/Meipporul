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
from backend.ingestion.tasks.text_cleaning import parse_clean_article

# Configuration
DBSCAN_EPS = float(os.getenv("DBSCAN_EPS", "0.11"))           # cosine distance threshold
DBSCAN_MIN_SAMPLES = int(os.getenv("DBSCAN_MIN_SAMPLES", "2"))
AGGLO_DISTANCE_THRESHOLD = float(os.getenv("AGGLO_DISTANCE_THRESHOLD", "0.15"))
CLUSTER_MAX_GAP_DAYS = int(os.getenv("CLUSTER_MAX_GAP_DAYS", "14"))
CLUSTER_MAX_ARTICLES = int(os.getenv("CLUSTER_MAX_ARTICLES", "50"))
CLUSTER_MIN_CENTROID_SIMILARITY = float(os.getenv("CLUSTER_MIN_CENTROID_SIMILARITY", "0.82"))
CLUSTER_MIN_PAIRWISE_SIMILARITY = float(os.getenv("CLUSTER_MIN_PAIRWISE_SIMILARITY", "0.88"))
CLUSTER_ID_REUSE_SIMILARITY = float(os.getenv("CLUSTER_ID_REUSE_SIMILARITY", "0.90"))
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-base")
EMBEDDING_REPRESENTATION_VERSION = "semantic-v2-headline-weighted"
CLUSTER_EMBEDDING_VERSION = f"{EMBEDDING_MODEL_NAME}:{EMBEDDING_REPRESENTATION_VERSION}"

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
            Article.embedding.isnot(None),
            Article.published_at.isnot(None),
        ).all()
        return articles
    
    def _compute_centroid(self, embeddings: np.ndarray) -> np.ndarray:
        """Compute the L2-normalized centroid of a set of embeddings."""
        centroid = np.mean(embeddings, axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm
        return centroid

    @staticmethod
    def _entity_aware_distances(articles: List[Any], embeddings: np.ndarray) -> np.ndarray:
        """Use semantic similarity as the main signal; entities only break close ties."""
        distances = cosine_distances(embeddings)
        entity_sets = []
        for article in articles:
            values = set()
            if getattr(article, "linked_entities", None):
                for group, entities in article.linked_entities.items():
                    if group.upper() not in {"PERSON", "ORG", "ORGANIZATION", "GPE", "LOCATION"}:
                        continue
                    for entity in entities or []:
                        value = entity.get("kg_id") or entity.get("canonical_en") or entity.get("canonical_ta") or entity.get("text")
                        if value:
                            values.add(f"{group}:{str(value).casefold()}")
            if getattr(article, "named_entities", None):
                for group, entities in article.named_entities.items():
                    if group.upper() not in {"PERSON", "ORG", "ORGANIZATION", "GPE"}:
                        continue
                    for entity in entities or []:
                        if isinstance(entity, str):
                            values.add(f"{group}:{entity.casefold()}")
            entity_sets.append(values)
        for left in range(len(articles)):
            for right in range(left + 1, len(articles)):
                left_date = articles[left].published_at
                right_date = articles[right].published_at
                left_lang = str(getattr(articles[left], "language", "") or "").lower().split("-")[0]
                right_lang = str(getattr(articles[right], "language", "") or "").lower().split("-")[0]
                if left_lang and right_lang and left_lang != right_lang:
                    distances[left, right] = distances[right, left] = 1.0
                    continue
                if left_date and right_date and abs((left_date - right_date).days) > CLUSTER_MAX_GAP_DAYS:
                    distances[left, right] = distances[right, left] = 1.0
                    continue
                # Shared names must never merge unrelated events on their own.
                # Only grant a small tie-break when the article pair is already
                # semantically close; location-only overlap is intentionally ignored.
                shared = entity_sets[left].intersection(entity_sets[right])
                if shared and distances[left, right] <= 0.20:
                    distances[left, right] = distances[right, left] = max(0.0, distances[left, right] - 0.02)
        return distances

    def _split_chained_clusters(self, labels: np.ndarray, articles: List[Any], embeddings: np.ndarray) -> np.ndarray:
        """Break DBSCAN chains unless every member is close to every other member.

        DBSCAN's connected-neighbor rule is prone to chaining: A can be close to
        B and B close to C even when A and C describe different events. The
        pairwise condition makes each emitted event a cohesive group.
        """
        refined = np.full(len(labels), -1, dtype=int)
        next_label = max((int(label) for label in labels if label >= 0), default=-1) + 1
        for original in sorted(set(int(label) for label in labels if label >= 0)):
            indices = [i for i, label in enumerate(labels) if int(label) == original]
            indices.sort(key=lambda i: (articles[i].published_at.timestamp() if articles[i].published_at else 0, articles[i].id or i))
            groups, current = [], []
            anchor_date = None
            for idx in indices:
                published = articles[idx].published_at
                exceeds_span = bool(current and published and anchor_date and
                                    (published - anchor_date).days > CLUSTER_MAX_GAP_DAYS)
                exceeds_size = len(current) >= max(2, CLUSTER_MAX_ARTICLES)
                loses_cohesion = bool(current and float(np.dot(
                    self._compute_centroid(embeddings[current]), embeddings[idx]
                )) < CLUSTER_MIN_CENTROID_SIMILARITY)
                loses_pairwise_cohesion = bool(current and min(
                    float(np.dot(embeddings[idx], embeddings[member]))
                    for member in current
                ) < CLUSTER_MIN_PAIRWISE_SIMILARITY)
                if current and (exceeds_span or exceeds_size or loses_cohesion or loses_pairwise_cohesion):
                    groups.append(current)
                    current, anchor_date = [], None
                if not current:
                    anchor_date = published
                current.append(idx)
            if current:
                groups.append(current)
            for group in groups:
                if len(group) < 2:
                    continue
                assigned = original if len(groups) == 1 else next_label
                if len(groups) > 1:
                    next_label += 1
                refined[group] = assigned
        return refined
    
    def _save_results(self, db: Any, labels: np.ndarray, articles: List[Any], 
                      embeddings: np.ndarray, run: Any, algorithm: str) -> Tuple[int, int]:
        """Save clustering results to news_clusters and article_clusters tables."""
        unique_labels = set(labels)
        unique_labels.discard(-1)  # -1 = noise in DBSCAN
        
        cluster_map = {}  # local_label -> NewsCluster.id
        existing = db.query(NewsCluster).filter(
            NewsCluster.algorithm == algorithm,
            NewsCluster.embedding_model_version == CLUSTER_EMBEDDING_VERSION,
            NewsCluster.centroid_embedding.isnot(None),
        ).all()
        used_existing = set()
        # The run covers the complete embedded corpus, so discard stale direct
        # assignments for noise points and groups that moved.
        for article in articles:
            article.cluster_id = None
        
        for label in sorted(unique_labels):
            # Find articles in this cluster
            member_indices = [i for i, l in enumerate(labels) if l == label]
            member_embeddings = embeddings[member_indices]
            centroid = self._compute_centroid(member_embeddings)
            
            # Choose the member closest to the group centroid rather than the
            # first DB row (whose order is not meaningful). This keeps the
            # event headline aligned with the stories used for its summary.
            representative_index = max(
                member_indices,
                key=lambda index: float(np.dot(embeddings[index], centroid)),
            )
            representative_article = articles[representative_index]
            
            # Reuse the closest prior event centroid when the new group is still
            # semantically the same event; this prevents a fresh event ID on every
            # daemon cycle when the full corpus is reclustered.
            best = None
            best_similarity = CLUSTER_ID_REUSE_SIMILARITY
            for candidate in existing:
                if candidate.id in used_existing:
                    continue
                old_centroid = np.asarray(candidate.centroid_embedding, dtype=float)
                similarity = float(np.dot(centroid, old_centroid))
                if similarity > best_similarity:
                    best, best_similarity = candidate, similarity
            if best is None:
                cluster = NewsCluster(
                    representative_title=representative_article.title,
                    cluster_key=f"{algorithm}_event_{run.id}_{label}",
                    label=None,
                    algorithm=algorithm,
                    algorithm_version="2.1",
                    embedding_model_version=CLUSTER_EMBEDDING_VERSION,
                    article_count=len(member_indices),
                    centroid_embedding=centroid.tolist(),
                )
                db.add(cluster)
                db.flush()
            else:
                cluster = best
                used_existing.add(cluster.id)
                cluster.centroid_embedding = centroid.tolist()
                cluster.article_count = len(member_indices)
                cluster.updated_at = datetime.utcnow()
                cluster.representative_title = representative_article.title
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
        for cluster in existing:
            if cluster.id not in used_existing:
                cluster.article_count = 0
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
            distance_matrix = self._entity_aware_distances(articles, embeddings)
            
            clusterer = DBSCAN(eps=eps, min_samples=min_samples, metric='precomputed')
            labels = clusterer.fit_predict(distance_matrix)
            labels = self._split_chained_clusters(labels, articles, embeddings)
            elapsed = time.time() - start
            
            # Create clustering run record
            run = ClusteringRun(
                algorithm="dbscan",
                algorithm_version="sklearn",
                embedding_model=EMBEDDING_MODEL_NAME,
                embedding_model_version=CLUSTER_EMBEDDING_VERSION,
                parameters={
                    "eps": eps,
                    "min_samples": min_samples,
                    "max_gap_days": CLUSTER_MAX_GAP_DAYS,
                    "max_articles": CLUSTER_MAX_ARTICLES,
                    "min_centroid_similarity": CLUSTER_MIN_CENTROID_SIMILARITY,
                    "min_pairwise_similarity": CLUSTER_MIN_PAIRWISE_SIMILARITY,
                    "cluster_id_reuse_similarity": CLUSTER_ID_REUSE_SIMILARITY,
                },
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
            distance_matrix = self._entity_aware_distances(articles, embeddings)
            
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
        """Run one event clustering algorithm; avoid publishing duplicate event sets."""
        logger.info("Starting clustering pipeline...")
        dbscan_run = self.run_dbscan()
        logger.info("Clustering pipeline complete.")
        return dbscan_run, None


def run_clustering_pipeline() -> None:
    """Entry point for standalone execution."""
    service = ClusteringService()
    service.run_all()

if __name__ == "__main__":
    run_clustering_pipeline()
