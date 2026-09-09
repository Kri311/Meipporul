#!/usr/bin/env python3
"""
Veritas Lens — Standalone RSS Feed Fetcher

Fetches articles from ALL enabled RSS feeds defined in config/sources.yaml
and writes them directly to data/raw_processed.csv.

NO Celery, Redis, or PostgreSQL required.

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
    python fetch_rss_standalone.py --fresh      # Start with a fresh CSV
    python fetch_rss_standalone.py --limit 50   # Optionally cap at N articles
"""

import argparse
import csv
import hashlib
import os
import sys
import time
from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser
import requests
import trafilatura
import yaml

# Ensure project root is in the Python path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from ingestion.tasks.text_cleaning import (
    clean_html, deep_clean_text, detect_language, get_canonical_url,
    SKIP_KEYWORDS, FESTIVAL_KEYWORDS, BREAKING_NEWS_KEYWORDS,
)

# ─── Constants ───
CSV_FIELDNAMES = [
    "content_hash", "guid", "outlet_slug", "title", "description",
    "author", "published_at", "language", "article_length",
    "data_fetch_via", "canonical_url", "extraction_method",
    "extraction_quality", "processing_status", "raw_text", "clean_text"
]

CSV_PATH = os.path.join(PROJECT_ROOT, "data", "raw_processed.csv")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "sources.yaml")

# Minimum clean text length to accept an article (quality gate)
MIN_CLEAN_TEXT_LENGTH = 200

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}


def load_existing_data(csv_path):
    """Load existing identifiers from the CSV for deduplication (scoped per outlet)."""
    guids = set()
    content_hashes = set()
    existing_urls = set()
    
    if not os.path.exists(csv_path):
        return guids, content_hashes, existing_urls
        
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
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
        print(f"Warning: Could not read existing CSV for dedup: {e}")
        
    return guids, content_hashes, existing_urls


def load_sources(config_path):
    """Load enabled RSS sources from config/sources.yaml."""
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


def extract_article_text(entry, canonical_url):
    """
    Extract article text from an RSS entry.
    Falls back to Trafilatura if the RSS content is too short (<500 chars).
    Returns (final_text, extraction_method, extraction_quality, rss_content_html).
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

    # If RSS text is too short, scrape the full article with Trafilatura
    if len(clean_rss_text) < 500:
        try:
            resp = requests.get(canonical_url, headers=HTTP_HEADERS, timeout=10)
            downloaded = resp.text if resp.status_code == 200 else None
        except Exception:
            downloaded = None

        if downloaded:
            extracted_text = trafilatura.extract(downloaded, favor_recall=True)
            if extracted_text and len(extracted_text) > len(clean_rss_text):
                final_text = deep_clean_text(extracted_text)
                extraction_method = "trafilatura"
                extraction_quality = 0.9

    # Fallback to RSS text
    if not final_text:
        final_text = deep_clean_text(clean_rss_text)
        extraction_quality = 0.5

    return final_text, extraction_method, extraction_quality, rss_content_html


def parse_pub_date(entry):
    """Extract publish date from an RSS entry."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6])
    elif hasattr(entry, "published"):
        try:
            return parsedate_to_datetime(entry.published)
        except Exception:
            return datetime.utcnow()
    return datetime.utcnow()


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

            # Normalization
            original_url = getattr(entry, "link", "")
            canonical_url = get_canonical_url(original_url)
            title = getattr(entry, "title", "")
            clean_title = clean_html(title)
            pub_date = parse_pub_date(entry)
            
            # 2. Canonical URL Deduplication
            if canonical_url and (outlet_slug, canonical_url) in existing_urls:
                skipped_dup += 1
                continue

            # Extract and clean article text
            final_text, extraction_method, extraction_quality, rss_content_html = \
                extract_article_text(entry, canonical_url)

            # Quality gate: skip articles with insufficient content
            if not final_text or len(final_text) < MIN_CLEAN_TEXT_LENGTH:
                filtered_quality += 1
                continue

            # Compute content hash
            content_hash = hashlib.sha256(final_text.encode("utf-8")).hexdigest()

            # 3. Content-Hash Deduplication (same exact article text)
            if (outlet_slug, content_hash) in content_hashes:
                skipped_dup += 1
                continue

            # Detect language and article length
            detected_lang = detect_language(final_text)
            word_count = len(final_text.split())
            if word_count < 250:
                article_length_cat = "short"
            elif word_count < 800:
                article_length_cat = "medium"
            else:
                article_length_cat = "long"

            article_row = {
                "content_hash": content_hash,
                "guid": guid,
                "outlet_slug": outlet_slug,
                "title": clean_title,
                "description": clean_html(getattr(entry, "description", "")),
                "author": getattr(entry, "author", ""),
                "published_at": pub_date.isoformat() if pub_date else "",
                "language": detected_lang,
                "article_length": article_length_cat,
                "data_fetch_via": data_fetch_via,
                "canonical_url": canonical_url,
                "extraction_method": extraction_method,
                "extraction_quality": extraction_quality,
                "processing_status": "eligible",
                "raw_text": rss_content_html,
                "clean_text": final_text,
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

    # Write new articles to CSV
    if new_articles:
        file_exists = os.path.exists(CSV_PATH)
        with open(CSV_PATH, "a", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=CSV_FIELDNAMES)
            if not file_exists:
                writer.writeheader()
            for article in new_articles:
                writer.writerow(article)

        print(f"Written {len(new_articles)} new articles to {CSV_PATH}")
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
        description="Standalone RSS fetcher for Veritas Lens - writes directly to data/raw_processed.csv"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Optional: cap the number of new articles to fetch (default: no limit, fetch all)"
    )
    parser.add_argument(
        "--fresh", action="store_true",
        help="Start with a fresh CSV (deletes existing data)"
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

    # Handle --fresh flag
    if args.fresh and os.path.exists(CSV_PATH):
        os.remove(CSV_PATH)
        print(f"Deleted existing {CSV_PATH}")

    # Load existing identifiers for deduplication
    existing_guids, content_hashes, existing_urls = load_existing_data(CSV_PATH)
    print(f"Existing articles in CSV: {len(existing_guids)}")
    if args.limit:
        print(f"Target: up to {args.limit} new articles")
    else:
        print(f"Target: ALL available articles (no limit)")

    if args.interval:
        print(f"Mode: Continuous (Fetching every {args.interval} minutes)")
    
    print()

    # Load sources from config/sources.yaml
    sources = load_sources(CONFIG_PATH)
    total_feeds = sum(len(s.get("rss", [])) for s in sources)
    print(f"Loaded {len(sources)} enabled sources ({total_feeds} feeds) from config/sources.yaml")
    
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
