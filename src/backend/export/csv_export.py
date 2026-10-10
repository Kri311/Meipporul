import csv
import sys
import os
import json
import hashlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from backend.models.database import SessionLocal, Article, NewsCluster
from backend.ingestion.tasks.text_cleaning import (
    build_article_description,
    clean_article_body,
    clean_article_title,
    clean_html,
    detect_language,
    extract_dateline_location,
    format_clean_article,
    normalize_political_parties,
    parse_clean_article,
)

CSV_FIELDNAMES = [
    "content_hash", "guid", "outlet_slug", "title", "description",
    "author", "published_at", "language", "article_length",
    "data_fetch_via", "canonical_url", "extraction_method",
    "extraction_quality", "processing_status", "raw_text", "clean_text", "topic",
    "cluster_id", "semantic_text_hash", "named_entities", "embedding"
]
PREPROCESSED_FIELDNAMES = [
    "content_hash", "guid", "outlet_slug", "title", "description", "author",
    "published_at", "language", "article_length", "data_fetch_via",
    "canonical_url", "extraction_method", "extraction_quality",
    "processing_status", "raw_text", "clean_text", "topic", "image_url",
]
DATA_DIR = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "data")
TRAFILTURA_CSV_PATH = os.path.join(DATA_DIR, "trafiltura_preprocessed.csv")
RAW_CSV_PATH = os.path.join(DATA_DIR, "raw_processed.csv")
# Keep the old constant name for import compatibility, but make the processed
# dataset the live/default export used by the application pipeline.
LIVE_CSV_PATH = TRAFILTURA_CSV_PATH


def export_to_csv(output_path=LIVE_CSV_PATH, trafiltura_output_path=None):
    db = SessionLocal()
    try:
        articles = db.query(Article).order_by(Article.published_at.desc().nulls_last()).all()
        
        output_paths = list(dict.fromkeys(path for path in (output_path, trafiltura_output_path) if path))
        def serialize_raw_article(article):
            ner_str = json.dumps(article.named_entities, ensure_ascii=False) if article.named_entities else ""
            embedding = article.embedding
            emb_str = json.dumps(embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)) if embedding is not None else ""
            return {
                "content_hash": article.content_hash,
                "guid": article.guid,
                "outlet_slug": article.outlet.slug if article.outlet else "",
                "title": article.title,
                "description": article.description,
                "author": article.author,
                "published_at": article.published_at.isoformat() if article.published_at else "",
                "language": article.language,
                "article_length": article.article_length,
                "data_fetch_via": article.data_fetch_via,
                "canonical_url": article.canonical_url,
                "extraction_method": article.extraction_method,
                "extraction_quality": article.extraction_quality,
                "processing_status": article.processing_status,
                "raw_text": article.raw_text,
                "clean_text": article.clean_text,
                "topic": article.cluster.topic if article.cluster else "",
                "cluster_id": article.cluster_id,
                "semantic_text_hash": article.semantic_text_hash,
                "named_entities": ner_str,
                "embedding": emb_str,
            }

        def normalize_trafiltura_article(article):
            """Persist the canonical cleaned values before exporting them."""
            title = clean_article_title(article.title)
            _, clean_body = parse_clean_article(article.clean_text, title)
            body_source = clean_body or clean_html(article.raw_text)
            location, body_source = extract_dateline_location(body_source)
            language = article.language if article.language in {"en", "ta"} else detect_language(body_source)
            body = clean_article_body(body_source, title, language=language)
            title = normalize_political_parties(title, language)
            body = clean_article_body(body, title, language=language)
            if not title or len(body) < 100:
                return None

            entities = dict(article.named_entities or {})
            locations = list(entities.get("LOCATION", []))
            if location and location not in locations:
                locations.append(location)
            if locations:
                entities["LOCATION"] = locations

            content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
            changed = content_hash != (article.content_hash or "") or title != (article.title or "") or format_clean_article(title, body) != (article.clean_text or "")
            article.title = title
            article.description = build_article_description(article.description, body, title)
            article.language = language
            article.article_length = "short" if len(body.split()) < 250 else "medium" if len(body.split()) < 800 else "long"
            article.content_hash = content_hash
            article.clean_text = format_clean_article(title, body)
            article.named_entities = entities
            if changed:
                # Derived features from pre-cleaned text are stale and must be recomputed.
                article.embedding = None
                article.semantic_text_hash = None
                article.cluster_id = None
            if changed or not entities:
                article.processing_status = "pending"
            return article

        def serialize_trafiltura_article(article):
            return {
                "content_hash": article.content_hash,
                "guid": article.guid,
                "outlet_slug": article.outlet.slug if article.outlet else "",
                "title": article.title,
                "description": article.description,
                "author": article.author,
                "published_at": article.published_at.isoformat() if article.published_at else "",
                "language": article.language,
                "article_length": article.article_length,
                "data_fetch_via": article.data_fetch_via,
                "canonical_url": article.canonical_url,
                "extraction_method": article.extraction_method,
                "extraction_quality": article.extraction_quality,
                "processing_status": article.processing_status,
                "raw_text": article.raw_text,
                "clean_text": article.clean_text,
                "topic": article.cluster.topic if article.cluster else "",
                "image_url": article.image_url or "",
            }

        for path in output_paths:
            is_trafiltura_output = path == TRAFILTURA_CSV_PATH or path == trafiltura_output_path
            export_articles = [
                article for article in articles
                if not is_trafiltura_output or article.published_at
            ]
            if is_trafiltura_output:
                export_articles = [
                    normalized for article in export_articles
                    if (normalized := normalize_trafiltura_article(article)) is not None
                ]
                db.commit()
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            temp_path = path + ".tmp"
            try:
                with open(temp_path, "w", newline="", encoding="utf-8-sig") as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=PREPROCESSED_FIELDNAMES if is_trafiltura_output else CSV_FIELDNAMES)
                    writer.writeheader()
                    serialize = serialize_trafiltura_article if is_trafiltura_output else serialize_raw_article
                    written = 0
                    for article in export_articles:
                        row = serialize(article)
                        if row is not None:
                            writer.writerow(row)
                            written += 1
                    csvfile.flush()
                    os.fsync(csvfile.fileno())
                os.replace(temp_path, path)
            except Exception:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise
            print(f"Exported {written} articles to {path}")
    finally:
        db.close()

if __name__ == "__main__":
    export_to_csv()
