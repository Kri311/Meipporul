from fastapi import FastAPI, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from fastapi.middleware.cors import CORSMiddleware
import sys
import os
import json
import re
import numpy as np

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from backend.models.database import SessionLocal, NewsCluster, Article, Outlet
from backend.ingestion.tasks.text_cleaning import is_usable_article_body, classify_topic
from backend.summarization.english import summarize_event_bullets as summarize_english_bullets
from backend.summarization.tamil import summarize_event_bullets as summarize_tamil_bullets
from backend.summarization.english import summarize_event_preview as summarize_english_preview
from backend.summarization.tamil import summarize_event_preview as summarize_tamil_preview
from backend.summarization.english import summarize_event_preview_bullets as summarize_english_preview_bullets
from backend.summarization.tamil import summarize_event_preview_bullets as summarize_tamil_preview_bullets

app = FastAPI()

EVENT_MIN_PAIRWISE_SIMILARITY = float(os.getenv("CLUSTER_MIN_PAIRWISE_SIMILARITY", "0.88"))
EVENT_MAX_ARTICLES = int(os.getenv("CLUSTER_MAX_ARTICLES", "50"))
EVENT_MAX_GAP_DAYS = int(os.getenv("CLUSTER_MAX_GAP_DAYS", "14"))

TOPIC_LABELS_TA = {
    "world_news": "உலக செய்திகள்", "politics": "அரசியல்",
    "economy": "பொருளாதாரம்", "science_health": "அறிவியல் மற்றும் சுகாதாரம்",
    "sports": "விளையாட்டு", "crime_law": "குற்றம் மற்றும் சட்டம்",
    "education": "கல்வி", "technology": "தொழில்நுட்பம்",
    "local_news": "உள்ளூர் செய்திகள்", "general": "பொது செய்திகள்",
}


def topic_label(topic, language):
    return TOPIC_LABELS_TA.get((topic or "general").lower(), topic or "பொது செய்திகள்") if language == "ta" else topic or "General"

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
    if len(dates) != len(articles):
        return False
    if (max(dates) - min(dates)).days > EVENT_MAX_GAP_DAYS:
        return False

    vectors = []
    for article in articles:
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
    upper = similarities[np.triu_indices(len(articles), k=1)]
    return bool(upper.size and np.isfinite(upper).all() and upper.min() >= EVENT_MIN_PAIRWISE_SIMILARITY)


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


def _article_event(event_id, title, articles, language, topic=None):
    """Build a cheap event-card preview; full abstractive inference is detail-only."""
    articles = sorted(articles, key=published_sort_key, reverse=True)
    representative = _representative_article(articles)
    summary_text = summarize_tamil_preview(articles) if language == "ta" else summarize_english_preview(articles)
    bullets = summarize_tamil_preview_bullets(articles) if language == "ta" else summarize_english_preview_bullets(articles)
    first_image = representative.image_url if representative else None
    if not topic:
        sample_body = " ".join(get_article_body(a.clean_text, a.title)[:500] for a in articles[:3])
        topic = classify_topic(title, sample_body)
    label = topic_label(topic or "general", language)
    return {
        "id": event_id,
        "title": title or (articles[0].title if articles else ""),
        "image_url": first_image,
        "source_count": len({_source_key(a) for a in articles if _source_key(a) is not None}),
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
        Article.published_at.isnot(None),
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
        dated_events.append((published_sort_key(article), _article_event(-article.id, article.title, [article], lang)))
    dated_events.sort(key=lambda item: item[0], reverse=True)
    return [event for _, event in dated_events]

@app.get("/events/{event_id}")
def get_event(event_id: int, lang: str = Query("en"), db: Session = Depends(get_db)):
    lang = "ta" if lang == "ta" else "en"

    if event_id < 0:
        article = db.query(Article).options(joinedload(Article.outlet)).filter(
            Article.id == -event_id,
            func.lower(Article.language).in_(language_codes(lang)),
            Article.published_at.isnot(None),
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
            Article.published_at.isnot(None),
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
    summary_bullets = summarize_tamil_bullets(arts) if lang == "ta" else summarize_english_bullets(arts)
    summary_text = " ".join(summary_bullets)
            
    entities = {"people": set(), "organizations": set(), "locations": set(), "events": set(), "dates": set()}
    category_map = {
        "PERSON": "people", "ORG": "organizations", "ORGANIZATION": "organizations",
        "LOCATION": "locations", "LOC": "locations", "GPE": "locations",
        "EVENT": "events", "DATE": "dates",
    }
    articles_data = []
    
    for a in arts:
        articles_data.append({
            "id": a.id,
            "title": a.title,
            "image_url": a.image_url,
            "url": a.canonical_url,
            "source_id": a.outlet.name if a.outlet else "News",
            "published_at": a.published_at.isoformat() if a.published_at else "",
            "article_length": a.article_length,
            "read_time": read_time(a.article_length)
        })
        
        for group, values in (a.named_entities or {}).items():
            key = category_map.get(str(group).upper())
            if key:
                for value in values or []:
                    name = value if isinstance(value, str) else value.get("text")
                    if name:
                        entities[key].add(name)
        for group, values in (a.linked_entities or {}).items():
            key = category_map.get(str(group).upper())
            if key:
                for value in values or []:
                    if isinstance(value, dict):
                        name = (value.get("canonical_ta") if lang == "ta" else value.get("canonical_en")) or value.get("text")
                    else:
                        name = str(value)
                    if name:
                        entities[key].add(name)
                
    title = _representative_title(arts, c.representative_title if c else "")
    if event_id < 0:
        article_body = get_article_body(arts[0].clean_text, arts[0].title)
        topic_value = classify_topic(arts[0].title, article_body)
    else:
        topic_value = c.topic if c else "general"
    topic = topic_label(topic_value, lang)
    
    return {
        "id": event_id,
        "title": title,
        "summary": summary_text,
        "summary_bullets": summary_bullets,
        "image_url": image_url,
        "source_count": len({_source_key(a) for a in arts if _source_key(a) is not None}),
        "article_count": len(arts),
        "tags": [topic],
        "articles": articles_data,
        "entities": {
            key: sorted(values) for key, values in entities.items()
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

@app.get("/metadata")
def get_metadata():
    return {
        "models": {
            "ner": os.getenv("NER_MODEL_NAME", "Babelscape/wikineural-multilingual-ner"),
            "embeddings": os.getenv("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-base"),
            "summarization": os.getenv("SUMMARY_MODEL_NAME", "csebuetnlp/mT5_multilingual_XLSum"),
            "clustering": "DBSCAN with entity-aware distance"
        },
        "version": "Veritas Lens v2.0 (Local)",
        "pipeline_status": "Active"
    }
