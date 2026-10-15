"""Persist article summaries, then build event summaries from those bullets.

Run after clustering. The model is used only for changed article content;
cluster summaries are a source-aware, deterministic merge of member summaries.
"""

import argparse
import hashlib
import json
import logging
from datetime import datetime

from backend.models.database import Article, NewsCluster, SessionLocal, init_db
from backend.summarization.common import MODEL_NAME, merge_article_bullets, summarize_event_bullets

logger = logging.getLogger("persist_summaries")
EVENT_MERGE_VERSION = "source-bullets-complete-dedupe-v1"


def _language(article):
    value = str(article.language or "").casefold().split("-")[0]
    return "ta" if value in {"ta", "tam", "tamil"} else "en" if value in {"en", "eng", "english"} else None


def _article_hash(article, language):
    digest = hashlib.sha256()
    digest.update(MODEL_NAME.encode("utf-8"))
    digest.update(language.encode("utf-8"))
    digest.update(str(article.id).encode("ascii"))
    digest.update((article.title or "").encode("utf-8", errors="ignore"))
    digest.update((article.content_hash or "").encode("ascii", errors="ignore"))
    digest.update((article.clean_text or "").encode("utf-8", errors="ignore"))
    return digest.hexdigest()


def _cluster_hash(members, language):
    digest = hashlib.sha256()
    digest.update(EVENT_MERGE_VERSION.encode("utf-8"))
    digest.update(MODEL_NAME.encode("utf-8"))
    digest.update(language.encode("utf-8"))
    for article in sorted(members, key=lambda row: row.id):
        digest.update(str(article.id).encode("ascii"))
        digest.update((getattr(article, f"summary_{language}_hash", None) or "").encode("ascii"))
        digest.update(json.dumps(
            getattr(article, f"summary_{language}_bullets", None) or [],
            ensure_ascii=False, sort_keys=True,
        ).encode("utf-8"))
    return digest.hexdigest()


def _persist_article_summary(article, *, force=False):
    language = _language(article)
    if not language or not article.clean_text:
        return False
    hash_field = f"summary_{language}_hash"
    bullets_field = f"summary_{language}_bullets"
    content_hash = _article_hash(article, language)
    if (not force and getattr(article, hash_field, None) == content_hash
            and getattr(article, bullets_field, None)):
        # Keep the unified source-language summary column populated for older
        # rows that only had the bilingual compatibility fields.
        stored = getattr(article, bullets_field) or []
        if article.summary != stored:
            article.summary = stored
            if article.summary_generated_at is None:
                article.summary_generated_at = datetime.utcnow()
            return True
        return False
    bullets = summarize_event_bullets([article], language)
    setattr(article, bullets_field, bullets)
    article.summary = bullets
    setattr(article, hash_field, content_hash)
    article.summary_generated_at = datetime.utcnow()
    logger.info("Stored %s article summary for article %s (%d bullets)", language, article.id, len(bullets))
    return True


def _persist_cluster_summary(cluster, members, language, *, force=False):
    hash_field = f"summary_{language}_hash"
    bullets_field = f"summary_{language}_bullets"
    same_language = [article for article in members if _language(article) == language]
    if not same_language:
        changed = bool(getattr(cluster, bullets_field, None))
        setattr(cluster, bullets_field, [])
        setattr(cluster, hash_field, None)
        return changed
    content_hash = _cluster_hash(same_language, language)
    if (not force and getattr(cluster, hash_field, None) == content_hash
            and getattr(cluster, bullets_field, None)):
        return False
    bullets = merge_article_bullets(same_language, language)
    setattr(cluster, bullets_field, bullets)
    setattr(cluster, hash_field, content_hash)
    cluster.summary_generated_at = datetime.utcnow()
    logger.info("Merged %s event summary for cluster %s from %d articles (%d bullets)",
                language, cluster.id, len(same_language), len(bullets))
    return True


def persist_summaries(*, force=False, limit=None):
    init_db()
    db = SessionLocal()
    article_count = cluster_count = articles_updated = clusters_updated = 0
    try:
        articles_query = db.query(Article).filter(
            Article.clean_text.isnot(None), Article.clean_text != ""
        ).order_by(Article.id)
        if limit:
            articles_query = articles_query.limit(limit)
        articles = articles_query.all()

        # Summarize all articles independently so each bullet set stays linked
        # to one source body, even when clustering later changes.
        for index, article in enumerate(articles, start=1):
            article_count += 1
            if _persist_article_summary(article, force=force):
                articles_updated += 1
            if index % 25 == 0:
                db.commit()

        db.commit()

        clusters_query = db.query(NewsCluster).filter(
            NewsCluster.article_count > 0
        ).order_by(NewsCluster.id)
        if limit:
            clusters_query = clusters_query.limit(limit)
        for cluster in clusters_query.all():
            members = db.query(Article).filter(
                Article.cluster_id == cluster.id,
                Article.clean_text.isnot(None), Article.clean_text != "",
            ).order_by(Article.published_at.asc().nullsfirst(), Article.id).all()
            if not members:
                continue
            cluster_count += 1
            for language in ("en", "ta"):
                if _persist_cluster_summary(cluster, members, language, force=force):
                    clusters_updated += 1
            # The singular summary column is the stable event-level export
            # contract; keep both native-language bullet sets together.
            cluster.summary = {
                "en": cluster.summary_en_bullets or [],
                "ta": cluster.summary_ta_bullets or [],
            }
            if cluster_count % 25 == 0:
                db.commit()

        db.commit()
        print(
            f"Summary persistence complete: articles={article_count}, articles_updated={articles_updated}, "
            f"events={cluster_count}, event_language_summaries_updated={clusters_updated}, model={MODEL_NAME}"
        )
    except Exception:
        db.rollback()
        logger.exception("Summary persistence failed")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="regenerate article and event summaries")
    parser.add_argument("--limit", type=int, help="process at most this many articles and events")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    persist_summaries(force=args.force, limit=args.limit)
