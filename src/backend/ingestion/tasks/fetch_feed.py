import json
import csv
import os
import re
import hashlib
import urllib.parse
import requests
from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser
import trafilatura
from bs4 import BeautifulSoup

from backend.ingestion.main import celery_app
from backend.models.database import SessionLocal, RssFeed, FeedRun, Article
from backend.ingestion.tasks.text_cleaning import (
    clean_html, deep_clean_text, detect_language, get_canonical_url,
    SKIP_KEYWORDS, FESTIVAL_KEYWORDS, BREAKING_NEWS_KEYWORDS,
    classify_topic, apply_outlet_cleaners,
    normalize_political_parties,
    extract_dateline_location
)


def normalize_str(s):
    s = normalize_political_parties(s)
    return re.sub(r'[^a-zA-Z0-9஀-௿]', '', s).lower()

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_single_feed(self, feed_id: int):
    """
    Step 6 Logic:
    1. Records a FeedRun attempt.
    2. Parses the RSS feed.
    3. For each entry, checks if it exists.
    4. Evaluates RSS content length. If too short, uses Trafilatura to scrape the full article.
    5. Saves the resulting Article into PostgreSQL.
    """
    print(f"[Worker] Starting to process feed_id: {feed_id}")
    db = SessionLocal()
    feed = db.query(RssFeed).filter(RssFeed.id == feed_id).first()
    
    if not feed:
        db.close()
        return {"error": "Feed not found"}
        
    feed_run = FeedRun(rss_feed_id=feed.id)
    db.add(feed_run)
    db.commit()
    
    try:
        outlet_slug = feed.outlet.slug
        outlet_orientation = feed.outlet.orientation_bucket
        parsed = feedparser.parse(feed.feed_url)
        feed_run.http_status = getattr(parsed, 'status', 200)
        
        # Check if feed is completely invalid
        if getattr(parsed, 'bozo', False) and not parsed.entries:
            feed_run.error_code = "feed_parse_error"
            feed_run.finished_at = datetime.utcnow()
            feed.consecutive_failures += 1
            db.commit()
            return {"error": "Failed to parse feed"}

        feed_run.entries_seen = len(parsed.entries)
        
        for entry in parsed.entries:
            guid = getattr(entry, 'id', getattr(entry, 'link', ''))
            if not guid:
                continue


            title_lower = getattr(entry, 'title', '').lower()
            url_lower = getattr(entry, 'link', '').lower()
            
            is_breaking = any(b in title_lower or b in url_lower for b in BREAKING_NEWS_KEYWORDS)
            
            # Skip article if it contains unwanted topics
            if any(keyword in title_lower or keyword in url_lower for keyword in SKIP_KEYWORDS):
                feed_run.entries_failed += 1
                continue
                
            # Extra News18 filters
            if outlet_slug in ['news18_india', 'news18_tamil_nadu'] and any(kw in url_lower for kw in ['/photogallery/', '/explanations/', 'job', 'recruitment']):
                feed_run.entries_failed += 1
                continue
                
            # Allow festival news ONLY if it's breaking news
            if not is_breaking and any(keyword in title_lower or keyword in url_lower for keyword in FESTIVAL_KEYWORDS):
                feed_run.entries_failed += 1
                continue
                
            # Check if article already exists (Idempotency)
            existing = db.query(Article).filter(Article.guid == guid).first()
            if existing:
                continue
                
            original_url = getattr(entry, 'link', '')
            canonical_url = get_canonical_url(original_url)
            title = getattr(entry, 'title', '')
            
            # Determine Publish Date
            pub_date = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_date = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, 'published'):
                        try:
                    pub_date = parsedate_to_datetime(entry.published)
                except Exception:
                    pub_date = datetime.utcnow()
            else:
                pub_date = datetime.utcnow()

            # Architecture Check: RSS Content vs Trafilatura
            # Most RSS feeds only give a 2-sentence summary in 'description'.
            rss_content_html = ''
            if hasattr(entry, 'content'):
                rss_content_html = entry.content[0].value
            elif hasattr(entry, 'description'):
                rss_content_html = entry.description
                
            clean_rss_text = clean_html(rss_content_html)
            
            final_text = ""
            extraction_method = "rss"
            extraction_quality = 0.0
            
            # If the RSS text is less than 500 chars, it's a snippet. We must scrape the URL.
            if True:
                try:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                    }
                    resp = requests.get(canonical_url, headers=headers, timeout=10)
                    downloaded = resp.content if resp.status_code == 200 else None
                except Exception:
                    downloaded = None

                if downloaded:
                    # Extract main article body (removes headers, footers, sidebars)
                    extracted_text = trafilatura.extract(downloaded, favor_recall=True)
                    
                    if len(clean_rss_text) < 50 and extracted_text:
                        rss_content_html = extracted_text
                        
                    if extracted_text and len(extracted_text) > 10:
                        final_text = deep_clean_text(extracted_text)
                        extraction_method = "trafilatura"
                        extraction_quality = 0.9 # High confidence full article
            
            # Fallback to RSS text if Trafilatura fails or if RSS had the full text (>500 chars)
            if not final_text:
                final_text = deep_clean_text(clean_rss_text)
                extraction_quality = 0.5
            
            # Skip articles with no usable content after cleaning
            if not final_text or len(final_text) < 200:
                feed_run.entries_failed += 1
                continue
                
            # Hash to detect content changes later
            content_hash = hashlib.sha256(final_text.encode('utf-8')).hexdigest() if final_text else None
            
            # Auto-detect language from actual content (unified timeline)
            detected_lang = detect_language(final_text)
            
            # Apply per-outlet cleaners and classify topic
            loc, final_text = extract_dateline_location(final_text)
            title_clean, final_text = apply_outlet_cleaners(clean_html(title), final_text, outlet_slug, canonical_url)
            
            # Remove title duplication from body using a smarter line-by-line check BEFORE collapsing newlines
                
            norm_title = normalize_str(title_clean)
            
            lines = final_text.split('\n')
            while lines:
                first_line = re.sub(r'^[\s\-\|:]+', '', lines[0]).strip()
                norm_first = normalize_str(first_line)
                
                # Check if first line is heavily overlapping with title
                if norm_first and (norm_first in norm_title or norm_title in norm_first or (len(norm_first) >= 15 and norm_first[:15] == norm_title[:15])):
                    lines.pop(0)
                else:
                    break
                    
            final_text = '\n'.join(lines).strip()

            # Remove any internal newlines in the body so it's a single continuous block
            # Convert newlines (and any following whitespaces) into a single whitespace
            final_text = re.sub(r'\n+\s*', ' ', final_text).strip()

            # STANDARD: Ensure content explicitly begins with the Title followed by the Body
            final_text = f"{title_clean}\n\n{final_text}"
            
            topic = classify_topic(title_clean, final_text, outlet_slug, location=loc)
            
            # Categorize article length for summarizer models
            word_count = len(final_text.split())
            if word_count < 250:
                article_length_cat = "short"
            elif word_count < 800:
                article_length_cat = "medium"
            else:
                article_length_cat = "long"
            
            data_fetch_via = "Google News RSS" if "news.google.com" in feed.feed_url else "Native RSS"
            
            t_clean = re.sub(r"\s+", " ", title_clean).strip() if title_clean else ""
            c_clean = re.sub(r"\s+", " ", final_text).strip() if final_text else ""
            formatted_clean_text = json.dumps({t_clean: c_clean}, ensure_ascii=False, separators=(',', ':'))

            article = Article(
                outlet_id=feed.outlet_id,
                rss_feed_id=feed.id,
                guid=guid,
                canonical_url=canonical_url,
                original_url=original_url,
                title=title_clean,
                description=clean_html(getattr(entry, 'description', '')),
                author=getattr(entry, 'author', ''),
                published_at=pub_date,
                language=detected_lang,
                article_length=article_length_cat,
                data_fetch_via=data_fetch_via,
                raw_text=rss_content_html,
                clean_text=formatted_clean_text,
                content_hash=content_hash,
                extraction_method=extraction_method,
                extraction_quality=extraction_quality,
                processing_status="eligible",
            )
            
            db.add(article)
                    try:
                db.commit() # Commit per article to avoid losing progress if one fails
                feed_run.entries_new += 1
            except Exception as commit_err:
                db.rollback()
                feed_run.entries_failed += 1
                continue
            
            # --- Save to unified raw_processed.csv ---
            csv_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data")
            os.makedirs(csv_dir, exist_ok=True)
            
            csv_path = os.path.join(csv_dir, "raw_processed.csv")
            
            file_exists = os.path.exists(csv_path)
            with open(csv_path, "a", newline="", encoding="utf-8-sig") as csvfile:
                fieldnames = ["content_hash", "guid", "outlet_slug", "title", "description", "author", "published_at", "language", "article_length", "data_fetch_via", "canonical_url", "extraction_method", "extraction_quality", "processing_status", "raw_text", "clean_text", "topic"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow({
                    "content_hash": content_hash,
                    "guid": guid,
                    "outlet_slug": outlet_slug,
                    "title": article.title,
                    "description": article.description,
                    "author": article.author,
                    "published_at": pub_date.isoformat() if pub_date else "",
                    "language": detected_lang,
                    "article_length": article_length_cat,
                    "data_fetch_via": data_fetch_via,
                    "canonical_url": canonical_url,
                    "extraction_method": extraction_method,
                    "extraction_quality": extraction_quality,
                    "processing_status": "eligible",
                    "raw_text": rss_content_html,
                    "clean_text": formatted_clean_text,
                    "topic": topic
                })
            # -------------------

            
        feed_run.finished_at = datetime.utcnow()
        feed.last_success_at = datetime.utcnow()
        feed.consecutive_failures = 0
        db.commit()
        
        # Save counts before session closes
        new_count = feed_run.entries_new
        seen_count = feed_run.entries_seen
        
    except Exception as e:
        db.rollback()
        feed_run.error_code = str(e)[:250]
        feed_run.finished_at = datetime.utcnow()
        feed_run.entries_failed += 1
        feed.consecutive_failures += 1
        db.commit()
        raise self.retry(exc=e)
    finally:
        db.close()
        
    return {"feed_id": feed_id, "new_articles": new_count, "total_seen": seen_count}



def normalize_str(s):
    s = normalize_political_parties(s)
    return re.sub(r'[^a-zA-Z0-9஀-௿]', '', s).lower()

@celery_app.task
def dispatch_all_feeds():
    """
    Triggered every 15 minutes by Celery Beat.
    It reads all active feeds from Postgres and queues them for processing.
    """
    print("[Beat] Dispatching all active RSS feeds to the queue...")
    db = SessionLocal()
    try:
        active_feeds = db.query(RssFeed).filter(RssFeed.enabled == True).all()
        for feed in active_feeds:
            process_single_feed.delay(feed.id)
            print(f"[Beat] Queued feed {feed.id} ({feed.feed_url})")
            
        return {"dispatched_count": len(active_feeds)}
    finally:
        db.close()
