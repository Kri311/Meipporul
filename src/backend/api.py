from fastapi import FastAPI, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from fastapi.middleware.cors import CORSMiddleware
import sys
import os
import json
import re
from datetime import datetime, timezone
import numpy as np

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from backend.models.database import SessionLocal, NewsCluster, Article, Outlet, init_db
from backend.ingestion.tasks.text_cleaning import is_usable_article_body
from backend.semantic_processing.topic_classifier import topic_labels, classify_event_topic
from backend.semantic_processing.clustering_service import (
    ClusteringService,
    CLUSTER_MAX_GAP_DAYS,
    event_pair_is_compatible,
)
from backend.summarization.common import extractive_summary_bullets, get_model_status as get_summarizer_model_status

app = FastAPI()


@app.on_event("startup")
def initialize_database_schema():
    # Includes additive topic fields used by article-level classification.
    init_db()

EVENT_MAX_ARTICLES = int(os.getenv("CLUSTER_MAX_ARTICLES", "50"))
EVENT_MAX_GAP_DAYS = CLUSTER_MAX_GAP_DAYS
EVENT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-base")

TOPIC_LABELS_TA = topic_labels("ta")
TOPIC_LABELS_EN = topic_labels("en")


def topic_label(topic, language):
    topic = (topic or "other_current_affairs").lower()
    labels = TOPIC_LABELS_TA if language == "ta" else TOPIC_LABELS_EN
    return labels.get(topic, labels["other_current_affairs"])


def _is_breaking_event(articles, source_count):
    """A recent story is breaking only after independent outlet coverage."""
    if source_count < 2:
        return False
    dates = [article.published_at for article in articles if article.published_at]
    if not dates:
        return False
    newest = max(
        date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date.astimezone(timezone.utc)
        for date in dates
    )
    age_hours = (datetime.now(timezone.utc) - newest).total_seconds() / 3600
    return -1 <= age_hours <= float(os.getenv("BREAKING_NEWS_WINDOW_HOURS", "24"))

def read_time(article_length):
    return {"short": "2m", "medium": "3m", "long": "5m"}.get(article_length, "3m")


def _source_key(article):
    outlet = getattr(article, "outlet", None)
    return (getattr(outlet, "slug", None) or getattr(outlet, "name", None) or article.outlet_id)


def language_codes(language):
    return ("ta", "tam", "tamil", "ta-in") if language == "ta" else ("en", "eng", "english", "en-in")


def published_sort_key(article):
    return article.published_at.timestamp() if article.published_at else 0


def _cluster_is_cohesive(articles):
    """Fail closed when persisted cluster members cannot support one event.

    This protects the feed while old cluster assignments await a new clustering
    pass, and keeps mixed summaries/entities/images out of event detail pages.
    """
    if len(articles) <= 1:
        return True
    if len(articles) > EVENT_MAX_ARTICLES:
        return False

    languages = {str(article.language or "").casefold().split("-")[0] for article in articles}
    if len(languages) != 1:
        return False

    dates = [article.published_at for article in articles if article.published_at]
    if len(dates) > 1 and (max(dates) - min(dates)).days > EVENT_MAX_GAP_DAYS:
        return False

    vectors = []
    for article in articles:
        if getattr(article, "embedding_model", None) != EVENT_EMBEDDING_MODEL:
            return False
        if article.embedding is None:
            return False
        vector = np.asarray(article.embedding, dtype=float)
        norm = np.linalg.norm(vector)
        if vector.shape != (768,) or not norm or not np.isfinite(norm):
            return False
        vectors.append(vector / norm)

    try:
        matrix = np.vstack(vectors)
    except ValueError:
        return False
    similarities = matrix @ matrix.T
    for left in range(len(articles)):
        for right in range(left + 1, len(articles)):
            similarity = float(similarities[left, right])
            if not np.isfinite(similarity):
                return False
            # Use the same semantic + NER rule as DBSCAN so stale cluster
            # assignments cannot mix unrelated stories in the public API.
            if not event_pair_is_compatible(articles[left], articles[right], similarity):
                return False
    return True


def _representative_article(articles):
    """Use the cluster medoid, not an arbitrary query-order row."""
    if not articles:
        return None
    vectors = [np.asarray(article.embedding, dtype=float) for article in articles if article.embedding is not None]
    if len(vectors) != len(articles):
        return articles[0]
    if any(vector.shape != (768,) or not np.isfinite(vector).all() for vector in vectors):
        return articles[0]
    centroid = np.mean(vectors, axis=0)
    norm = np.linalg.norm(centroid)
    if not norm:
        return articles[0]
    centroid = centroid / norm
    return max(articles, key=lambda article: float(np.dot(np.asarray(article.embedding, dtype=float), centroid)))


def _representative_title(articles, fallback=""):
    representative = _representative_article(articles)
    return (representative.title if representative else "") or fallback


def _stored_summary(owner, articles, language):
    """Read a pipeline summary; use only a cheap source extract if missing."""
    field = "summary_ta_bullets" if language == "ta" else "summary_en_bullets"
    bullets = getattr(owner, field, None) if owner is not None else None
    if isinstance(bullets, list) and bullets:
        return [str(bullet) for bullet in bullets if bullet]
    return extractive_summary_bullets(articles, language, max_sentences=8)


def _article_event(event_id, title, articles, language, topic=None, summary_owner=None):
    """Build an event card from its persisted summary without model inference."""
    articles = sorted(articles, key=published_sort_key, reverse=True)
    representative = _representative_article(articles)
    owner = summary_owner or (articles[0].cluster if articles and articles[0].cluster_id else articles[0] if articles else None)
    bullets = _stored_summary(owner, articles, language)
    summary_text = " ".join(bullets)
    first_image = representative.image_url if representative else None
    if not topic:
        topic = articles[0].topic if articles else None
    if not topic:
        sample_body = " ".join(get_article_body(a.clean_text, a.title)[:500] for a in articles[:3])
        topic = classify_event_topic(title, sample_body, language=language)
    label = topic_label(topic or "general", language)
    source_count = len({_source_key(a) for a in articles if _source_key(a) is not None})
    return {
        "id": event_id,
        "title": title or (articles[0].title if articles else ""),
        "image_url": first_image,
        "source_count": source_count,
        "breaking_news": _is_breaking_event(articles, source_count),
        "article_count": len(articles),
        "topic": label,
        "tags": [label],
        "summary": summary_text,
        "summary_bullets": bullets,
        "coverage": {},
        "articles": [
            {
                "id": a.id,
                "title": a.title,
                "image_url": a.image_url,
                "url": a.canonical_url,
                "source_id": a.outlet.name if a.outlet else "News",
                "published_at": a.published_at.isoformat() if a.published_at else "",
                "article_length": a.article_length,
                "read_time": read_time(a.article_length),
            }
            for a in articles
        ],
    }


ENTITY_CATEGORY_MAP = {
    "PER": "people", "PERSON": "people",
    "ORG": "organizations", "ORGANIZATION": "organizations",
    "LOC": "locations", "LOCATION": "locations", "GPE": "locations",
    "EVENT": "events", "DATE": "dates",
}


def _article_entities(article, language):
    """Normalize article NER and linked entity payloads for the detail API."""
    result = {key: [] for key in ("people", "organizations", "locations", "events", "dates")}
    seen = {key: set() for key in result}
    for source, is_linked in (
        (getattr(article, "named_entities", None), False),
        (getattr(article, "linked_entities", None), True),
    ):
        if not isinstance(source, dict):
            continue
        for raw_group, values in source.items():
            group = re.sub(r"^[BI]-", "", str(raw_group).strip().upper())
            category = ENTITY_CATEGORY_MAP.get(group)
            if not category:
                continue
            if isinstance(values, (str, dict)):
                values = [values]
            for value in values or []:
                if isinstance(value, dict):
                    if is_linked:
                        name = (
                            value.get("canonical_ta") if language == "ta"
                            else value.get("canonical_en")
                        ) or value.get("text") or value.get("word") or value.get("entity")
                    else:
                        name = value.get("text") or value.get("word") or value.get("entity")
                else:
                    name = value
                name = str(name or "").strip()
                if name and name.casefold() not in seen[category]:
                    seen[category].add(name.casefold())
                    result[category].append(name)
    return result


def _event_entities(articles, language):
    """Combine normalized member NER into a deduplicated event-level view."""
    categories = ("people", "organizations", "locations", "events", "dates")
    result = {category: [] for category in categories}
    seen = {category: set() for category in categories}
    for article in articles:
        for category, values in _article_entities(article, language).items():
            for value in values:
                key = value.casefold()
                if key not in seen[category]:
                    seen[category].add(key)
                    result[category].append(value)
    return result


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_article_body(clean_text, title=""):
    """Read current and legacy clean_text JSON without repeating the headline."""
    text = clean_text or ""
    if text.lstrip().startswith("{"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                if isinstance(parsed.get("content"), str):
                    text = parsed["content"]
                elif len(parsed) == 1:
                    text = str(next(iter(parsed.values())))
                else:
                    text = " ".join(str(value) for value in parsed.values())
        except (json.JSONDecodeError, TypeError):
            pass

    text = re.sub(r"\s+", " ", str(text)).strip()
    title = re.sub(r"\s+", " ", title or "").strip()
    if title and text[:len(title)].casefold() == title.casefold():
        remainder = text[len(title):]
        if not remainder or not re.match(r"[\w\u0B80-\u0BFF]", remainder[0], flags=re.UNICODE):
            text = remainder.lstrip(" \t\r\n:|–—-.")
    return text


def _is_displayable(article):
    return is_usable_article_body(get_article_body(article.clean_text, article.title))

@app.get("/events/")
def get_events(lang: str = Query("en"), db: Session = Depends(get_db)):
    lang = "ta" if lang == "ta" else "en"

    # Read article rows directly, not only the latest N cluster rows. During
    # reprocessing, new/cleaned articles may temporarily have no cluster_id.
    articles = db.query(Article).options(
        joinedload(Article.outlet), joinedload(Article.cluster)
    ).filter(
        func.lower(Article.language).in_(language_codes(lang)),
        Article.clean_text.isnot(None),
    ).all()
    articles = [article for article in articles if _is_displayable(article)]

    by_cluster = {}
    standalone = []
    for article in articles:
        if article.cluster_id and article.cluster:
            by_cluster.setdefault(article.cluster_id, []).append(article)
        else:
            standalone.append(article)

    dated_events = []
    for cluster_id, members in by_cluster.items():
        cluster = members[0].cluster
        if not _cluster_is_cohesive(members):
            # An invalid legacy assignment must not mix titles, summaries,
            # article images, sources, or NER entities in the public feed.
            standalone.extend(members)
            continue
        dated_events.append((
            max((published_sort_key(a) for a in members), default=0),
            _article_event(cluster_id, _representative_title(members, cluster.representative_title), members, lang, cluster.topic),
        ))
    for article in standalone:
        # Negative IDs reserve a collision-free namespace for temporary items.
        dated_events.append((published_sort_key(article), _article_event(
            -article.id, article.title, [article], lang, summary_owner=article
        )))
    dated_events.sort(key=lambda item: item[0], reverse=True)
    return [event for _, event in dated_events]

@app.get("/events/{event_id}")
def get_event(event_id: int, lang: str = Query("en"), db: Session = Depends(get_db)):
    lang = "ta" if lang == "ta" else "en"

    if event_id < 0:
        article = db.query(Article).options(joinedload(Article.outlet)).filter(
            Article.id == -event_id,
            func.lower(Article.language).in_(language_codes(lang)),
            Article.clean_text.isnot(None),
        ).first()
        if not article:
            return {"error": "not found"}
        arts = [article]
        c = article.cluster
    else:
        c = db.query(NewsCluster).filter(NewsCluster.id == event_id).first()
        if not c:
            return {"error": "not found"}
        arts = db.query(Article).options(joinedload(Article.outlet)).filter(
            Article.cluster_id == c.id,
            func.lower(Article.language).in_(language_codes(lang)),
            Article.clean_text.isnot(None),
        ).all()
    arts = [article for article in arts if _is_displayable(article)]
    if not arts:
        return {"error": "not found"}
    if event_id >= 0 and not _cluster_is_cohesive(arts):
        return {"error": "not found"}
    arts.sort(key=published_sort_key, reverse=True)
    
    representative = _representative_article(arts)
    image_url = representative.image_url if representative else None
    summary_owner = arts[0] if event_id < 0 else c
    summary_bullets = _stored_summary(summary_owner, arts, lang)
    summary_text = " ".join(summary_bullets)
            
    articles_data = []
    
    for a in arts:
        article_entities = _article_entities(a, lang)
        articles_data.append({
            "id": a.id,
            "title": a.title,
            "image_url": a.image_url,
            "url": a.canonical_url,
            "source_id": a.outlet.name if a.outlet else "News",
            "published_at": a.published_at.isoformat() if a.published_at else "",
            "article_length": a.article_length,
            "read_time": read_time(a.article_length),
            "entities": article_entities,
        })
                
    title = _representative_title(arts, c.representative_title if c else "")
    if event_id < 0:
        article_body = get_article_body(arts[0].clean_text, arts[0].title)
        topic_value = arts[0].topic or classify_event_topic(
            arts[0].title, article_body, language=lang
        )
    else:
        topic_value = c.topic if c else "general"
    topic = topic_label(topic_value, lang)
    source_count = len({_source_key(a) for a in arts if _source_key(a) is not None})
    
    return {
        "id": event_id,
        "title": title,
        "summary": summary_text,
        "summary_bullets": summary_bullets,
        "entities": _event_entities(arts, lang),
        "image_url": image_url,
        "source_count": source_count,
        "breaking_news": _is_breaking_event(arts, source_count),
        "article_count": len(arts),
        "tags": [topic],
        "articles": articles_data,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

@app.get("/metadata")
def get_metadata():
    local_ner_model = os.path.join(
        os.path.dirname(__file__), "ner_pipeline", "finetune", "model", "best"
    )
    default_ner_model = (
        local_ner_model
        if os.path.isdir(local_ner_model)
        and os.getenv("NER_PREFER_FINETUNED_MODEL", "1").casefold() in {"1", "true", "yes"}
        else "Babelscape/wikineural-multilingual-ner"
    )
    return {
        "models": {
            "ner": os.getenv("NER_MODEL_NAME", default_ner_model),
            "embeddings": os.getenv("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-base"),
            "summarization": os.getenv("SUMMARY_MODEL_NAME", "csebuetnlp/mT5_multilingual_XLSum"),
            "topic_classification": os.getenv(
                "TOPIC_ZERO_SHOT_MODEL", "MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli"
            ),
            "clustering": "multilingual E5 cosine DBSCAN with strict NER compatibility, complete-link, and date guards"
        },
        "topic_taxonomy": "new bilingual editorial taxonomy",
        "version": "Veritas Lens v2.0 (Local)",
        "pipeline_status": "Active"
    }


@app.get("/summarizer/status")
def get_summarizer_status():
    """Inspect mT5 load/use state without downloading model weights."""
    return get_summarizer_model_status()
