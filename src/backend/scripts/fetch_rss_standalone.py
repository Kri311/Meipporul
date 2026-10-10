#!/usr/bin/env python3
"""
Veritas Lens — Standalone RSS Feed Fetcher

Fetches articles from ALL enabled RSS feeds defined in config/sources.yaml,
cleans and quality-checks them, stores them in PostgreSQL, and appends the
processed records to data/trafiltura_preprocessed.csv.

This command requires PostgreSQL; it does not require Celery or Redis.

Uses the exact same text cleaning, filtering, and extraction logic
as the Celery-based pipeline (ingestion/tasks/fetch_feed.py).

Quality gates:
  - GUID-based deduplication (no duplicate entries)
  - Content-hash deduplication (same article syndicated via different feeds)
  - Minimum 200 chars of clean text after deep cleaning
  - Skip keywords filter (entertainment, astrology, tech deals, etc.)
  - Trafilatura fallback for short RSS snippets (<500 chars)

Usage:
    python fetch_rss_standalone.py              # Fetch ALL available articles
    python fetch_rss_standalone.py --limit 50   # Optionally cap at N articles
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")), "src"))

import argparse
import csv
import hashlib
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import requests
import trafilatura
import yaml
import json
from bs4 import BeautifulSoup
from backend.models.database import SessionLocal, Article, Outlet, RssFeed

# Ensure project root is in the Python path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

from backend.ingestion.tasks.text_cleaning import (
    clean_html, deep_clean_text, detect_language, get_canonical_url,
    is_recent_feed_date, normalize_news_datetime,
    article_page_matches_title,
    SKIP_KEYWORDS, FESTIVAL_KEYWORDS, BREAKING_NEWS_KEYWORDS,
    classify_topic, apply_outlet_cleaners,
    normalize_political_parties,
    extract_dateline_location, clean_article_title, clean_article_body,
    format_clean_article, build_article_description
)

# ─── Constants ───
CSV_FIELDNAMES = [
    "content_hash", "guid", "outlet_slug", "title", "description",
    "author", "published_at", "language", "article_length",
    "data_fetch_via", "canonical_url", "extraction_method",
    "extraction_quality", "processing_status", "raw_text", "clean_text",
    "topic", "image_url",
]

CSV_PATH = os.path.join(PROJECT_ROOT, "src", "backend", "data", "trafiltura_preprocessed.csv")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "src", "backend", "config", "sources.yaml")

# Minimum clean text length to accept an article (quality gate)
MIN_CLEAN_TEXT_LENGTH = 200

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}


def load_existing_data():
    """Load PostgreSQL and CSV identifiers for scoped, repeatable RSS deduplication."""
    guids = set()
    content_hashes = set()
    existing_urls = set()
    
    db = SessionLocal()
    try:
        articles = db.query(Article.guid, Article.content_hash, Article.canonical_url, Outlet.slug).join(Outlet).all()
        for art in articles:
            if art.slug and art.guid:
                guids.add((art.slug, art.guid))
            if art.slug and art.content_hash:
                content_hashes.add((art.slug, art.content_hash))
            if art.slug and art.canonical_url:
                existing_urls.add((art.slug, art.canonical_url))
    finally:
        db.close()

    try:
        with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                outlet = row.get("outlet_slug", "")
                if not outlet:
                    continue
                if row.get("guid"):
                    guids.add((outlet, row["guid"]))
                if row.get("content_hash"):
                    content_hashes.add((outlet, row["content_hash"]))
                if row.get("canonical_url"):
                    existing_urls.add((outlet, row["canonical_url"]))
    except Exception as e:
        if os.path.exists(CSV_PATH):
            print(f"Warning: Could not read existing CSV for dedup: {e}")
        
    return guids, content_hashes, existing_urls


def load_sources(config_path):
    """Load enabled RSS sources from backend.config/sources.yaml."""
    if not os.path.exists(config_path):
        print(f"Error: Config file not found at {config_path}")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    sources = []
    for src in config.get("sources", []):
        if src.get("enabled", True):
            sources.append(src)
    return sources


def should_skip_entry(title_lower, url_lower):
    """Check if an RSS entry should be skipped based on keyword filters."""
    # Skip unwanted topics
    if any(kw in title_lower or kw in url_lower for kw in SKIP_KEYWORDS):
        return True

    # Skip festival news unless it's breaking
    is_breaking = any(b in title_lower or b in url_lower for b in BREAKING_NEWS_KEYWORDS)
    if not is_breaking and any(kw in title_lower or kw in url_lower for kw in FESTIVAL_KEYWORDS):
        return True

    return False


def _usable_image_url(url, base_url=""):
    if not url:
        return None
    absolute = urllib.parse.urljoin(base_url, str(url).strip())
    parsed = urllib.parse.urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
        return None
    if any(token in parsed.path.casefold() for token in ("logo", "avatar", "icon", "sprite", "placeholder", "default-image")):
        return None
    return absolute


def extract_page_image(downloaded, url=""):
    """Find a publisher's lead image when RSS does not expose one."""
    if not downloaded:
        return None
    try:
        soup = BeautifulSoup(downloaded, "html.parser")
        for key in ("og:image", "og:image:url", "twitter:image", "twitter:image:src"):
            node = soup.find("meta", property=key)
            if node is None:
                node = soup.find("meta", attrs={"name": key})
            if node is not None and node.get("content"):
                image = _usable_image_url(node["content"], url)
                if image:
                    return image
        image = soup.select_one("article img[src], main img[src]")
        if image:
            return _usable_image_url(image["src"], url)
    except Exception:
        pass
    return None

def extract_article_text(entry, canonical_url, expected_title=""):
    """
    Extract article text from an RSS entry.
    Falls back to Trafilatura if the RSS content is too short (<500 chars).
    Returns (final_text, extraction_method, extraction_quality, rss_content_html, image_url).
    """
    # Get RSS content
    rss_content_html = ""
    if hasattr(entry, "content"):
        rss_content_html = entry.content[0].value
    elif hasattr(entry, "description"):
        rss_content_html = entry.description

    clean_rss_text = clean_html(rss_content_html)

    final_text = ""
    extraction_method = "rss"
    extraction_quality = 0.0

    # Always scrape the full article with Trafilatura to ensure completeness
    page_image = None
    page_url = canonical_url
    if True:
        try:
            resp = requests.get(canonical_url, headers=HTTP_HEADERS, timeout=10)
            # Use content (bytes) to let Trafilatura handle encoding properly
            downloaded = resp.content if resp.status_code == 200 else None
            page_url = resp.url or canonical_url
        except Exception:
            downloaded = None

        if downloaded:
            if not article_page_matches_title(downloaded, expected_title):
                # Do not attach another story's text or image through a stale
                # link or an unexpected publisher redirect.
                return "", "title_mismatch", 0.0, rss_content_html, None
            page_image = extract_page_image(downloaded, page_url)
            extracted_text = trafilatura.extract(
                downloaded, favor_recall=True, include_comments=False,
                include_tables=False
            )
            
            # If RSS text was practically empty, populate raw_text with the trafilatura extraction so it's not empty
            if extracted_text:
                rss_content_html = extracted_text
                
            if extracted_text and len(extracted_text) > 10:
                final_text = deep_clean_text(extracted_text)
                extraction_method = "trafilatura"
                extraction_quality = 0.9

    # Fallback to RSS text
    if not final_text:
        final_text = deep_clean_text(clean_rss_text)
        extraction_quality = 0.5

    return final_text, extraction_method, extraction_quality, rss_content_html, page_image


def parse_pub_date(entry):
    """Extract publish date from an RSS entry."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        # feedparser normalizes parsed tuples to UTC but drops tzinfo.
        return normalize_news_datetime(datetime(*entry.published_parsed[:6], tzinfo=timezone.utc))
    elif hasattr(entry, "published"):
        try:
            return normalize_news_datetime(parsedate_to_datetime(entry.published))
        except Exception:
            return None
    return None



def normalize_str(s):
    s = normalize_political_parties(s)
    return re.sub(r'[^a-zA-Z0-9஀-௿]', '', s).lower()


def process_feed(source, existing_guids, content_hashes, existing_urls, new_articles, limit=None):
    """
    Process a single RSS source (may contain multiple feed URLs).
    Appends new article dicts to new_articles list.
    Returns (added_count, skipped_count, filtered_count).
    """
    outlet_slug = source["slug"]
    added = 0
    skipped_dup = 0
    filtered_quality = 0

    for feed_url in source.get("rss", []):
        # If a limit was explicitly set and we've reached it, stop
        if limit is not None and len(new_articles) >= limit:
            break

        try:
            parsed = feedparser.parse(feed_url)
        except Exception as e:
            print(f"Failed to parse {feed_url}: {e}")
            continue

        status = getattr(parsed, "status", "N/A")
        if getattr(parsed, "bozo", False) and not parsed.entries:
            print(f"{outlet_slug}: Feed parse error (status={status})")
            continue

        data_fetch_via = "Google News RSS" if "news.google.com" in feed_url else "Native RSS"

        for entry in parsed.entries:
            if limit is not None and len(new_articles) >= limit:
                break

            # 1. GUID Deduplication
            guid = getattr(entry, "id", getattr(entry, "link", ""))
            if not guid or (outlet_slug, guid) in existing_guids:
                skipped_dup += 1
                continue

            # Topic Filtering
            title_lower = getattr(entry, "title", "").lower()
            url_lower = getattr(entry, "link", "").lower()

            if should_skip_entry(title_lower, url_lower):
                filtered_quality += 1
                continue

            # Extra News18 filters
            if outlet_slug in ['news18_india', 'news18_tamil_nadu'] and any(kw in url_lower for kw in ['/photogallery/', '/explanations/', 'job', 'recruitment']):
                filtered_quality += 1
                continue

            # Normalization
            original_url = getattr(entry, "link", "")
            canonical_url = get_canonical_url(original_url)
            title = getattr(entry, "title", "")
            clean_title = clean_article_title(title)
            pub_date = parse_pub_date(entry)
            # Keep feed ingestion current while retaining already stored history.
            if not is_recent_feed_date(pub_date):
                continue
            
            # 2. Canonical URL Deduplication
            if canonical_url and (outlet_slug, canonical_url) in existing_urls:
                skipped_dup += 1
                continue

            # Extract and clean article text
            final_text, extraction_method, extraction_quality, rss_content_html, page_image = extract_article_text(
                entry, canonical_url, clean_title
            )
            # Only attach an image parsed from the article page itself. RSS
            # media can be feed artwork or a neighboring story's thumbnail.
            image_url = page_image

            # Quality gate: skip articles with insufficient content
            if not final_text or len(final_text) < MIN_CLEAN_TEXT_LENGTH:
                filtered_quality += 1
                continue

            # Apply per-outlet cleaners and classify topic
            loc, final_text = extract_dateline_location(final_text)
            clean_title, final_text = apply_outlet_cleaners(clean_title, final_text, outlet_slug, canonical_url)
            
            # Remove title duplication from body using a smarter line-by-line check BEFORE collapsing newlines
                
            norm_title = normalize_str(clean_title)
            
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
            final_text = clean_article_body(final_text, clean_title)
            
            # STANDARD: Ensure content explicitly begins with the Title followed by the Body
            # The user requested "newline follwed by a whitespace should be defined" in contents,
            # so we ensure the gap between title and body is exact.

            if len(final_text) < MIN_CLEAN_TEXT_LENGTH:
                filtered_quality += 1
                continue
            content_hash = hashlib.sha256(final_text.encode("utf-8")).hexdigest()
            if (outlet_slug, content_hash) in content_hashes:
                skipped_dup += 1
                continue
            detected_lang = detect_language(final_text)
            clean_title = normalize_political_parties(clean_title, detected_lang)
            
            topic = classify_topic(clean_title, final_text, outlet_slug, location=loc)
            
            # Strictly filter out entertainment/gossip/festival noise by enforcing topic rules for Tamil
            # "political, world news, important ones, govt related, etc"
            # If the user wants to aggressively drop non-news, we drop topic 'general' or 'sports' if it's too noisy,
            # but since we already have SKIP_KEYWORDS, the topic classifier adds safety.

            
            word_count = len(final_text.split())
            if word_count < 250:
                article_length_cat = "short"
            elif word_count < 800:
                article_length_cat = "medium"
            else:
                article_length_cat = "long"
            d_clean = clean_html(getattr(entry, "description", ""))
            formatted_clean_text = format_clean_article(clean_title, final_text)
            article_row = {
                "content_hash": content_hash,
                "guid": guid,
                "outlet_slug": outlet_slug,
                "title": clean_title,
                "description": build_article_description(
                    getattr(entry, "description", ""), final_text, clean_title
                ),
                "author": getattr(entry, "author", ""),
                "published_at": pub_date.isoformat() if pub_date else "",
                "language": detected_lang,
                "article_length": article_length_cat,
                "data_fetch_via": data_fetch_via,
                "original_url": original_url,
                "canonical_url": canonical_url,
                "extraction_method": extraction_method,
                "extraction_quality": extraction_quality,
                "processing_status": "eligible",
                "raw_text": rss_content_html,
                "clean_text": formatted_clean_text,
                "image_url": image_url,
                "topic": topic,
                "location": loc,
            }

            new_articles.append(article_row)
            existing_guids.add((outlet_slug, guid))
            content_hashes.add((outlet_slug, content_hash))
            existing_urls.add((outlet_slug, canonical_url))
            added += 1

    return added, skipped_dup, filtered_quality


def run_fetch_cycle(args, existing_guids, content_hashes, existing_urls, sources):
    """Executes a single cycle of fetching and saving RSS feeds."""
    new_articles = []
    total_skipped = 0
    total_filtered = 0
    start_time = time.time()

    current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'='*60}")
    print(f"  BATCH RUN START: {current_time_str}")
    print(f"{'='*60}", flush=True)

    for source in sources:
        if args.limit is not None and len(new_articles) >= args.limit:
            break

        slug = source["slug"]
        feed_count = len(source.get("rss", []))
        print(f"Processing {source['name']} ({slug}) [{feed_count} feed(s)]...", end=" ", flush=True)

        added, skipped, filtered = process_feed(
            source, existing_guids, content_hashes, existing_urls, new_articles, limit=args.limit
        )
        total_skipped += skipped
        total_filtered += filtered
        print(f"+{added} articles" + (f" (skipped {skipped} dup, {filtered} filtered)" if skipped + filtered > 0 else ""), flush=True)

    elapsed = time.time() - start_time
    print()

    # Write new articles to PostgreSQL
    if new_articles:
        print(f"\nSaving {len(new_articles)} new articles to PostgreSQL...")
        db = SessionLocal()
        saved_rows = []
        db_saved = False
        try:
            for article_dict in new_articles:
                outlet = db.query(Outlet).filter(Outlet.slug == article_dict['outlet_slug']).first()
                if not outlet:
                    continue
                
                art = Article(
                    outlet_id=outlet.id,
                    guid=article_dict['guid'],
                    canonical_url=article_dict['canonical_url'],
                    original_url=article_dict.get('original_url') or article_dict['canonical_url'],
                    title=article_dict['title'],
                    description=article_dict['description'],
                    author=article_dict['author'],
                    published_at=datetime.fromisoformat(article_dict['published_at']) if article_dict['published_at'] else None,
                    language=article_dict['language'],
                    article_length=article_dict['article_length'],
                    data_fetch_via=article_dict['data_fetch_via'],
                    raw_text=article_dict['raw_text'],
                    clean_text=article_dict['clean_text'],
                    image_url=article_dict.get("image_url"),
                    content_hash=article_dict['content_hash'],
                    extraction_method=article_dict['extraction_method'],
                    extraction_quality=article_dict.get('extraction_quality', 0.0),
                    named_entities={"LOCATION": [article_dict["location"]]} if article_dict.get("location") else {},
                    processing_status="extracted"
                )
                db.add(art)
                saved_rows.append(article_dict)
            db.commit()
            db_saved = True
        except Exception as e:
            db.rollback()
            print(f"Error saving to DB: {e}")
        finally:
            db.close()
            
        # Keep the live CSV export in sync only after a successful DB commit.
        if db_saved and saved_rows:
            file_exists = os.path.exists(CSV_PATH) and os.path.getsize(CSV_PATH) > 0
            csv_fields = CSV_FIELDNAMES
            if file_exists:
                with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as existing_csv:
                    existing_header = next(csv.reader(existing_csv), [])
                if existing_header:
                    csv_fields = existing_header
            with open(CSV_PATH, "a", newline="", encoding="utf-8-sig") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=csv_fields, extrasaction="ignore")
                if not file_exists:
                    writer.writeheader()
                for article_row in saved_rows:
                    writer.writerow({**article_row, "cluster_id": "", "semantic_text_hash": "", "named_entities": json.dumps({"LOCATION": article_row.get("location", [])} if article_row.get("location") else {}, ensure_ascii=False), "embedding": ""})
            print(f"Written {len(saved_rows)} new articles to PostgreSQL and {CSV_PATH}")
    else:
        print("No new articles found in this batch (all already in CSV or filtered out).")

    # Summary stats
    from collections import Counter
    
    end_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'-'*60}")
    print(f"  BATCH SUMMARY (Completed at {end_time_str})")
    print(f"{'-'*60}")
    
    if new_articles:
        outlets = Counter(a["outlet_slug"] for a in new_articles)
        langs = Counter(a["language"] for a in new_articles)
        methods = Counter(a["extraction_method"] for a in new_articles)

        print(f"  New articles added : {len(new_articles)}")
        print(f"  Duplicates skipped : {total_skipped}")
        print(f"  Filtered (quality) : {total_filtered}")
        print(f"  Time elapsed       : {elapsed:.1f}s")
        print()
        print(f"  Articles added by outlet:")
        for name, count in outlets.most_common():
            print(f"    - {name:25s} : {count} articles")
        print()
        print(f"  Articles added by language:")
        for lang, count in sorted(langs.items(), key=lambda x: -x[1]):
            print(f"    - {lang:25s} : {count} articles")
    else:
        print(f"  New articles added : 0")
        print(f"  Duplicates skipped : {total_skipped}")
        print(f"  Filtered (quality) : {total_filtered}")
        print(f"  Time elapsed       : {elapsed:.1f}s")

    # Final CSV count
    total = len(existing_guids)
    print(f"\nTotal historical articles now in CSV: {total}")
    print(f"{'='*60}\n", flush=True)
    return len(new_articles)


def main():
    parser = argparse.ArgumentParser(
        description="Fetch, clean, and append RSS articles to trafiltura_preprocessed.csv"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Optional: cap the number of new articles to fetch (default: no limit, fetch all)"
    )
    parser.add_argument(
        "--interval", type=int, default=None,
        help="Optional: run continuously in the background, fetching every N minutes"
    )
    args = parser.parse_args()

    print("Veritas Lens Standalone RSS Feed Fetcher")
    print()

    # Ensure data directory exists
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)

    # Load existing identifiers for deduplication
    existing_guids, content_hashes, existing_urls = load_existing_data()
    print(f"Existing articles in DB: {len(existing_guids)}")
    if args.limit:
        print(f"Target: up to {args.limit} new articles")
    else:
        print(f"Target: ALL available articles (no limit)")

    if args.interval:
        print(f"Mode: Continuous (Fetching every {args.interval} minutes)")
    
    print()

    # Load sources from backend.config/sources.yaml
    sources = load_sources(CONFIG_PATH)
    total_feeds = sum(len(s.get("rss", [])) for s in sources)
    print(f"Loaded {len(sources)} enabled sources ({total_feeds} feeds) from backend.config/sources.yaml")
    
    if args.interval:
        # Continuous loop
        while True:
            try:
                run_fetch_cycle(args, existing_guids, content_hashes, existing_urls, sources)
                print(f"Sleeping for {args.interval} minutes until next cycle...")
                time.sleep(args.interval * 60)
            except KeyboardInterrupt:
                print("\nBackground fetcher stopped.")
                break
            except Exception as e:
                print(f"\nError in fetch cycle: {e}")
                print(f"Retrying in {args.interval} minutes...")
                time.sleep(args.interval * 60)
    else:
        # Single run
        run_fetch_cycle(args, existing_guids, content_hashes, existing_urls, sources)


if __name__ == "__main__":
    main()
