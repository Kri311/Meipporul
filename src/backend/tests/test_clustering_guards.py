from datetime import datetime, timedelta

import numpy as np

from backend.semantic_processing.clustering_service import ClusteringService


class ArticleStub:
    def __init__(self, index, published_at, language="en"):
        self.id = index
        self.published_at = published_at
        self.language = language


def test_cluster_splitter_breaks_time_chains():
    base = datetime(2026, 1, 1)
    articles = [ArticleStub(i, base + timedelta(days=d)) for i, d in enumerate((0, 1, 15, 16))]
    embeddings = np.asarray([[1.0, 0.0], [0.99, 0.01], [0.0, 1.0], [0.01, 0.99]])
    labels = ClusteringService()._split_chained_clusters(np.asarray([0, 0, 0, 0]), articles, embeddings)
    assert labels[0] == labels[1] >= 0
    assert labels[2] == labels[3] >= 0
    assert labels[0] != labels[2]


def test_distance_matrix_never_clusters_different_languages():
    articles = [ArticleStub(1, datetime(2026, 1, 1), "en"), ArticleStub(2, datetime(2026, 1, 1), "ta")]
    distances = ClusteringService._entity_aware_distances(articles, np.asarray([[1.0, 0.0], [1.0, 0.0]]))
    assert distances[0, 1] == 1.0
