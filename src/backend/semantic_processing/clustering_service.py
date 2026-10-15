import os
import sys
import time
import heapq
import unicodedata
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
DBSCAN_EPS = float(os.getenv("DBSCAN_EPS", "0.12"))
DBSCAN_MIN_SAMPLES = int(os.getenv("DBSCAN_MIN_SAMPLES", "2"))
AGGLO_DISTANCE_THRESHOLD = float(os.getenv("AGGLO_DISTANCE_THRESHOLD", "0.15"))
CLUSTER_MAX_GAP_DAYS = int(os.getenv("CLUSTER_MAX_GAP_DAYS", "5"))
CLUSTER_MAX_ARTICLES = int(os.getenv("CLUSTER_MAX_ARTICLES", "50"))
CLUSTER_MIN_CENTROID_SIMILARITY = float(os.getenv("CLUSTER_MIN_CENTROID_SIMILARITY", "0.72"))
CLUSTER_MIN_PAIRWISE_SIMILARITY = float(os.getenv("CLUSTER_MIN_PAIRWISE_SIMILARITY", "0.88"))
CLUSTER_ENTITYLESS_MIN_SIMILARITY = float(os.getenv("CLUSTER_ENTITYLESS_MIN_SIMILARITY", "0.92"))
CLUSTER_ORG_ONLY_MIN_SIMILARITY = float(os.getenv("CLUSTER_ORG_ONLY_MIN_SIMILARITY", "0.90"))
CLUSTER_PERSON_ONLY_MIN_SIMILARITY = float(os.getenv("CLUSTER_PERSON_ONLY_MIN_SIMILARITY", "0.90"))
CLUSTER_ID_REUSE_SIMILARITY = float(os.getenv("CLUSTER_ID_REUSE_SIMILARITY", "0.90"))
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-base")
EMBEDDING_REPRESENTATION_VERSION = "semantic-v4-multilingual-date-strict"
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


def _article_entity_sets(article: Any) -> dict:
    """Return normalized entity values while preserving their NER categories."""
    aliases = {
        "PER": "PERSON", "PERSON": "PERSON", "ORG": "ORGANIZATION",
        "ORGANIZATION": "ORGANIZATION", "GPE": "LOCATION", "LOC": "LOCATION",
        "LOCATION": "LOCATION", "EVENT": "EVENT", "DATE": "DATE",
    }
    result = {group: set() for group in ("PERSON", "ORGANIZATION", "LOCATION", "EVENT", "DATE")}
    for source in (getattr(article, "linked_entities", None), getattr(article, "named_entities", None)):
        if not isinstance(source, dict):
            continue
        for raw_group, values in source.items():
            group = aliases.get(str(raw_group).removeprefix("B-").removeprefix("I-").upper())
            if not group:
                continue
            if isinstance(values, (str, dict)):
                values = [values]
            for entity in values or []:
                if isinstance(entity, dict):
                    value = (entity.get("kg_id") or entity.get("canonical_en") or
                             entity.get("canonical_ta") or entity.get("text") or
                             entity.get("word") or entity.get("entity"))
                else:
                    value = entity
                normalized = " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())
                if normalized:
                    result[group].add(normalized)
    return result


def _entity_names_overlap(left: set, right: set) -> bool:
    """Match exact names and common aliases such as “PM Modi” / “Modi's”."""
    for left_name in left:
        left_tokens = {"".join(char for char in token if char.isalnum()) for token in left_name.split()}
        left_tokens.discard("")
        for right_name in right:
            if left_name == right_name:
                return True
            right_tokens = {"".join(char for char in token if char.isalnum()) for token in right_name.split()}
            right_tokens.discard("")
            if any(len(token) >= 4 for token in left_tokens & right_tokens):
                return True
    return False


_GENERIC_ORG_TERMS = (
    "court", "courts", "judiciary", "tribunal", "நீதிமன்றம்", "நீதிமன்ற",
    "நீதித்துறை", "காவல்துறை", "police",
)
_COURT_TERMS = ("court", "நீதிமன்றம்", "நீதிமன்ற")


def event_pair_is_compatible(left: Any, right: Any, similarity: float) -> bool:
    """Require semantic similarity plus matching, sufficiently specific NER.

    If both stories have person/event anchors, at least one anchor must agree.
    A single shared person needs a higher semantic score because
    unrelated reports often mention the same public figure. Broad institutions
    such as courts cannot connect pairs by themselves. Missing or weak NER
    requires a still higher semantic score.
    """
    if not np.isfinite(similarity) or similarity < CLUSTER_MIN_PAIRWISE_SIMILARITY:
        return False
    left_entities, right_entities = _article_entity_sets(left), _article_entity_sets(right)

    left_person_event = left_entities["PERSON"] | left_entities["EVENT"]
    right_person_event = right_entities["PERSON"] | right_entities["EVENT"]
    if left_person_event and right_person_event:
        shared_events = left_entities["EVENT"] & right_entities["EVENT"]
        shared_people_exact = left_entities["PERSON"] & right_entities["PERSON"]
        shared_people = bool(shared_people_exact) or _entity_names_overlap(
            left_entities["PERSON"], right_entities["PERSON"]
        )
        if shared_events:
            return True
        if not shared_people:
            return False

        def specific_orgs(entity_set):
            return {
                name for name in entity_set["ORGANIZATION"]
                if not any(term in name for term in _GENERIC_ORG_TERMS)
            }

        shared_orgs = specific_orgs(left_entities) & specific_orgs(right_entities)
        if len(shared_people_exact) >= 2 or shared_orgs:
            return True
        return similarity >= CLUSTER_PERSON_ONLY_MIN_SIMILARITY

    left_courts = {name for name in left_entities["ORGANIZATION"] if any(term in name for term in _COURT_TERMS)}
    right_courts = {name for name in right_entities["ORGANIZATION"] if any(term in name for term in _COURT_TERMS)}
    if left_courts and right_courts:
        # A court name is a broad topic anchor, not proof that two reports cover
        # the same case. Require person/event overlap above to connect such pairs.
        return False

    def specific_orgs(entity_set):
        return {
            name for name in entity_set["ORGANIZATION"]
            if not any(term in name for term in _GENERIC_ORG_TERMS)
        }

    left_orgs, right_orgs = specific_orgs(left_entities), specific_orgs(right_entities)
    if left_orgs and right_orgs:
        return bool(left_orgs & right_orgs) and similarity >= CLUSTER_ORG_ONLY_MIN_SIMILARITY

    # If one side has an identity entity and the other does not, or the only
    # shared institutions are generic, avoid merging on broad topical wording.
    return similarity >= CLUSTER_ENTITYLESS_MIN_SIMILARITY

class ClusteringService:
    """Runs batch clustering algorithms on embedded articles."""
    
    def _fetch_embedded_articles(self, db: Any) -> List[Any]:
        """Fetch only complete vectors produced by the configured E5 model."""
        articles = db.query(Article).filter(
            Article.embedding.isnot(None),
            Article.embedding_model == EMBEDDING_MODEL_NAME,
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
    def _entity_aware_distances(articles: List[Any], embeddings: np.ndarray, eps: float) -> np.ndarray:
        """Use E5 cosine distance with NER compatibility and publication-date guards."""
        distances = cosine_distances(embeddings)
        dates = [article.published_at for article in articles]
        valid_dates = np.asarray([date is not None for date in dates], dtype=bool)
        if valid_dates.any():
            ordinal_days = np.asarray([date.date().toordinal() if date else 0 for date in dates])
            date_gap = np.abs(ordinal_days[:, None] - ordinal_days[None, :])
            date_blocked = valid_dates[:, None] & valid_dates[None, :] & (date_gap > CLUSTER_MAX_GAP_DAYS)
            distances[date_blocked] = 1.0

        # NER checks only apply to semantically plausible neighbors. Stories
        # that already fail DBSCAN's semantic radius do not need Python-level
        # entity comparisons across the entire corpus matrix.
        candidates = np.argwhere(np.triu(distances <= eps, k=1))
        for left, right in candidates:
            similarity = 1.0 - float(distances[left, right])
            if not event_pair_is_compatible(articles[left], articles[right], similarity):
                distances[left, right] = distances[right, left] = 1.0
        return distances

    def _split_chained_clusters(
        self, labels: np.ndarray, articles: List[Any], distance_matrix: np.ndarray, eps: float
    ) -> np.ndarray:
        """Refine DBSCAN candidates with deterministic complete-link merges.

        DBSCAN can connect A to C through B even when A and C are too far apart.
        Start with singleton groups and merge the closest pair of groups only
        when every cross-pair satisfies semantic, NER, and date constraints.
        """
        refined = np.full(len(labels), -1, dtype=int)
        next_label = max((int(label) for label in labels if label >= 0), default=-1) + 1

        # Build each DBSCAN candidate once; avoid rescanning all labels for every
        # candidate cluster during a full-corpus run.
        by_label = {}
        for index, label in enumerate(labels):
            if int(label) >= 0:
                by_label.setdefault(int(label), []).append(index)

        max_articles = max(2, CLUSTER_MAX_ARTICLES)
        for original in sorted(by_label):
            indices = by_label[original]
            indices.sort(key=lambda i: (
                articles[i].published_at.timestamp() if articles[i].published_at else 0,
                articles[i].id or i,
            ))

            # Each active group stores its members and the sorted identifier key
            # used by the previous deterministic tie-break rule.
            groups = {}
            active = set()
            pair_stats = {}
            merge_heap = []
            next_group = 0

            for index in indices:
                article_key = str(articles[index].id or index)
                groups[next_group] = {
                    "members": [index],
                    "key": (article_key,),
                    "size": 1,
                    "min_date": articles[index].published_at,
                    "max_date": articles[index].published_at,
                }
                active.add(next_group)
                next_group += 1

            def pair_key(left, right):
                return (left, right) if left < right else (right, left)

            def within_time_window(left, right):
                dates = [date for date in (left["min_date"], left["max_date"],
                                            right["min_date"], right["max_date"])
                         if date is not None]
                return not dates or (max(dates) - min(dates)).days <= CLUSTER_MAX_GAP_DAYS

            def add_candidate(left_id, right_id, max_distance, average_distance):
                left, right = groups[left_id], groups[right_id]
                if max_distance > eps or left["size"] + right["size"] > max_articles:
                    return
                if not within_time_window(left, right):
                    return
                key = pair_key(left_id, right_id)
                pair_stats[key] = (max_distance, average_distance)
                tie_break = tuple(sorted(left["key"] + right["key"]))
                heapq.heappush(merge_heap, (average_distance, tie_break, key[0], key[1]))

            # Initial singleton distances are read a row at a time. NumPy handles
            # each row comparison; Python only visits pairs that can actually merge.
            for offset, left_id in enumerate(indices):
                candidate_ids = indices[offset + 1:]
                if not candidate_ids:
                    continue
                candidate_distances = distance_matrix[left_id, candidate_ids]
                for position in np.flatnonzero(candidate_distances <= eps):
                    add_candidate(offset, offset + 1 + int(position),
                                  float(candidate_distances[int(position)]),
                                  float(candidate_distances[int(position)]))

            while merge_heap:
                average_distance, tie_break, left_id, right_id = heapq.heappop(merge_heap)
                if left_id not in active or right_id not in active:
                    continue
                stats = pair_stats.get((left_id, right_id))
                if stats is None or stats[1] != average_distance:
                    continue

                left, right = groups[left_id], groups[right_id]
                merged_size = left["size"] + right["size"]
                merged_members = sorted(left["members"] + right["members"])
                merged_key = tuple(sorted(left["key"] + right["key"]))
                dates = [date for date in (left["min_date"], left["max_date"],
                                            right["min_date"], right["max_date"])
                         if date is not None]
                merged = {
                    "members": merged_members,
                    "key": merged_key,
                    "size": merged_size,
                    "min_date": min(dates) if dates else None,
                    "max_date": max(dates) if dates else None,
                }

                active.remove(left_id)
                active.remove(right_id)
                merged_id = next_group
                next_group += 1
                groups[merged_id] = merged
                active.add(merged_id)

                # Complete-link maximums and cross-pair means can be updated from
                # cached group statistics without rebuilding distance submatrices.
                for other_id in sorted(active):
                    if other_id == merged_id:
                        continue
                    left_stats = pair_stats.get(pair_key(left_id, other_id))
                    right_stats = pair_stats.get(pair_key(right_id, other_id))
                    if left_stats is None or right_stats is None:
                        continue
                    other_size = groups[other_id]["size"]
                    total_pairs = merged_size * other_size
                    average = (
                        left_stats[1] * left["size"] * other_size
                        + right_stats[1] * right["size"] * other_size
                    ) / total_pairs
                    add_candidate(merged_id, other_id,
                                  max(left_stats[0], right_stats[0]), average)

            for group_id in sorted(active):
                members = groups[group_id]["members"]
                if len(members) < 2:
                    continue
                refined[members] = next_label
                next_label += 1
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
        # assignments for noise points and groups that moved. Also clear rows
        # with missing/stale vectors: their old cluster ID must not collide with
        # a new event ID that gets reused by centroid matching.
        db.query(Article).filter(Article.cluster_id.isnot(None)).update(
            {Article.cluster_id: None}, synchronize_session=False
        )
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
                    algorithm_version="2.2",
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
        eps = DBSCAN_EPS if eps is None else eps
        min_samples = DBSCAN_MIN_SAMPLES if min_samples is None else min_samples
        
        db = SessionLocal()
        try:
            articles = self._fetch_embedded_articles(db)
            if len(articles) < min_samples:
                logger.info(f"Not enough articles ({len(articles)}) for DBSCAN (min_samples={min_samples})")
                return None
            
            logger.info(f"Running DBSCAN on {len(articles)} articles (eps={eps}, min_samples={min_samples})...")
            
            embeddings = np.asarray([a.embedding for a in articles], dtype=np.float32)
            if embeddings.ndim != 2 or embeddings.shape[1] != 768:
                raise ValueError(
                    f"Expected 768-dimensional {EMBEDDING_MODEL_NAME} vectors; got {embeddings.shape}"
                )
            
            # Compute cosine distance matrix
            start = time.time()
            # DBSCAN operates directly on cosine distances between the normalized
            # multilingual-e5-base article embeddings, with language/date guards.
            distance_matrix = self._entity_aware_distances(articles, embeddings, eps)
            
            clusterer = DBSCAN(eps=eps, min_samples=min_samples, metric='precomputed')
            labels = clusterer.fit_predict(distance_matrix)
            labels = self._split_chained_clusters(labels, articles, distance_matrix, eps)
            elapsed = time.time() - start
            
            # Create clustering run record
            run = ClusteringRun(
                algorithm="dbscan",
        algorithm_version="sklearn-dbscan-multilingual-semantic-ner-complete-link-v8",
                embedding_model=EMBEDDING_MODEL_NAME,
                embedding_model_version=CLUSTER_EMBEDDING_VERSION,
                parameters={
                    "eps": eps,
                    "min_samples": min_samples,
                    "max_gap_days": CLUSTER_MAX_GAP_DAYS,
                    "max_articles": CLUSTER_MAX_ARTICLES,
                    "refinement": "deterministic_complete_link",
                    "refinement_distance_threshold": eps,
                    "entity_policy": "person/event match required when both sides have anchors; one shared person needs a higher score; generic courts do not link cases; weak/missing NER requires a high semantic score",
                    "pairwise_min_similarity": CLUSTER_MIN_PAIRWISE_SIMILARITY,
                    "entityless_min_similarity": CLUSTER_ENTITYLESS_MIN_SIMILARITY,
                    "organization_only_min_similarity": CLUSTER_ORG_ONLY_MIN_SIMILARITY,
                    "person_only_min_similarity": CLUSTER_PERSON_ONLY_MIN_SIMILARITY,
                    "cross_language_matching": "enabled via multilingual E5 cosine distance",
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
            distance_matrix = self._entity_aware_distances(articles, embeddings, distance_threshold)
            
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
