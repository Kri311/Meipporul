import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from backend.models.database import SessionLocal, NewsCluster, Article, init_db
from backend.semantic_processing.topic_classifier import classify_event_topic_details
from backend.ingestion.tasks.text_cleaning import parse_clean_article

def classify_all_clusters():
    init_db()
    db = SessionLocal()
    try:
        articles = db.query(Article).filter(
            Article.clean_text.isnot(None), Article.clean_text != ""
        ).all()
        clusters = db.query(NewsCluster).filter(NewsCluster.article_count > 0).all()
        print(f"Classifying {len(articles)} articles and {len(clusters)} event clusters...")
        cluster_article_topics = defaultdict(list)
        topic_counts = Counter()

        for index, article in enumerate(articles, start=1):
            title, body = parse_clean_article(article.clean_text, article.title)
            entities = {}
            for source in (article.named_entities or {}, article.linked_entities or {}):
                if not isinstance(source, dict):
                    continue
                for entity_type, values in source.items():
                    entities.setdefault(entity_type, [])
                    if isinstance(values, (list, tuple, set)):
                        entities[entity_type].extend(values)
                    elif values:
                        entities[entity_type].append(values)
            result = classify_event_topic_details(
                title, body, entities=entities, language=article.language
            )
            article.topic = result["topic"]
            article.topic_confidence = result.get("confidence")
            article.topic_model = result.get("model")
            topic_counts[article.topic] += 1
            if article.cluster_id:
                cluster_article_topics[article.cluster_id].append(result)
            if index % 100 == 0:
                print(f"Classified {index}/{len(articles)} articles")

        # An event inherits the topic supported by most of its member articles.
        # A tie is treated as an outlier rather than forced into a topic.
        for cluster in clusters:
            member_results = cluster_article_topics.get(cluster.id, [])
            if not member_results:
                cluster.topic = "other_current_affairs"
                continue
            counts = Counter(result["topic"] for result in member_results)
            ranked = counts.most_common()
            if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
                cluster.topic = "other_current_affairs"
                continue
            cluster.topic = ranked[0][0]

        db.commit()
        print("Article topic counts:", dict(topic_counts))
        print("Topic classification complete.")
    finally:
        db.close()

if __name__ == "__main__":
    classify_all_clusters()
