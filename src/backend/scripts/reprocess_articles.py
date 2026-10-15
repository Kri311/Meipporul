#!/usr/bin/env python3
"""Re-fetch eligible rows from the canonical preprocessed news dataset."""

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime

import requests
import trafilatura
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from backend.ingestion.tasks.text_cleaning import (  # noqa: E402
    clean_article_body,
    clean_article_title,
    clean_html,
    detect_language,
    format_clean_article,
    extract_dateline_location,
    classify_topic,
    normalize_political_parties,
)

DATA_DIR = os.path.join(PROJECT_ROOT, "src", "backend", "data")
DEFAULT_INPUT = os.path.join(DATA_DIR, "trafiltura_preprocessed.csv")
DEFAULT_OUTPUT = os.path.join(DATA_DIR, "trafiltura_processed.csv")
FIELDNAMES = [
    "content_hash", "guid", "outlet_slug", "title", "description", "author",
    "published_at", "language", "article_length", "data_fetch_via",
    "canonical_url", "extraction_method", "extraction_quality",
    "processing_status", "raw_text", "clean_text", "topic", "cluster_id",
    "named_entities", "embedding", "summary",
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; VeritasLensNewsBot/1.0)",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
}


def is_2026(value):
    """Accept ISO timestamps and common date strings, but never infer a year."""
    value = (value or "").strip()
    if not value:
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).year == 2026
    except ValueError:
        return value[:4] == "2026"


def choose_title(source_title, metadata):
    title = clean_article_title(source_title)
    if title and "<" not in title and "{" not in title:
        return title
    return clean_article_title(getattr(metadata, "title", ""))


def fetch_article(session, url, timeout, source_title=""):
    """Return metadata, original extracted body, and cleaned body or None."""
    if not url:
        return None
    try:
        response = session.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"    unavailable: {exc}", flush=True)
        return None

    content_type = response.headers.get("Content-Type", "").lower()
    if content_type and "html" not in content_type and "xhtml" not in content_type:
        print(f"    skipped non-HTML response ({content_type})", flush=True)
        return None

    downloaded = response.content
    try:
        extracted = trafilatura.extract(
            downloaded,
            url=response.url,
            favor_recall=True,
            include_comments=False,
            include_tables=False,
            output_format="txt",
        )
        if not extracted:
            return None
        metadata = trafilatura.extract_metadata(downloaded, default_url=response.url)
    except Exception as exc:
        print(f"    extraction failed: {exc}", flush=True)
        return None
    title = choose_title(source_title, metadata)
    raw_text = extracted
    location, body_source = extract_dateline_location(extracted)
    body = clean_article_body(body_source, title)
    if not title or len(body) < 100:
        return None
    return metadata, title, raw_text, body, location


def export_2026(input_path=DEFAULT_INPUT, output_path=DEFAULT_OUTPUT, batch_size=50,
                timeout=20, delay=0.2):
    """Rewrite the output from the source CSV; unavailable URLs are omitted."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    temp_path = output_path + ".tmp"
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(("GET",)),
    )
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    scanned = written = skipped = failed = 0
    batch_seen = 0
    snapshot_fd, snapshot_path = tempfile.mkstemp(
        prefix=".reprocess_input_", suffix=".tmp",
        dir=os.path.dirname(os.path.abspath(input_path)),
    )
    os.close(snapshot_fd)

    try:
        # Take a stable point-in-time snapshot so a running RSS daemon cannot
        # append half a multibyte character while this historical pass reads.
        copied = False
        for _ in range(3):
            before = os.stat(input_path)
            with open(input_path, "rb") as source_bytes, open(snapshot_path, "wb") as snapshot:
                shutil.copyfileobj(source_bytes, snapshot)
                snapshot.flush()
                os.fsync(snapshot.fileno())
            after = os.stat(input_path)
            if (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns):
                copied = True
                break
            time.sleep(0.5)
        if not copied:
            raise RuntimeError("The source CSV kept changing during snapshot; stop RSS writes and retry.")

        with open(snapshot_path, "r", encoding="utf-8-sig", errors="replace", newline="") as source_file:
            reader = csv.DictReader(source_file)
            if not reader.fieldnames or "canonical_url" not in reader.fieldnames:
                raise ValueError(f"Input CSV must include canonical_url: {input_path}")

            with open(temp_path, "w", encoding="utf-8-sig", newline="") as output_file:
                writer = csv.DictWriter(output_file, fieldnames=FIELDNAMES, extrasaction="ignore")
                writer.writeheader()

                for row in reader:
                    if not is_2026(row.get("published_at")):
                        skipped += 1
                        continue
                    scanned += 1
                    batch_seen += 1
                    url = (row.get("canonical_url") or row.get("guid") or "").strip()
                    print(f"[{scanned}] {row.get('outlet_slug', '')} {url}", flush=True)
                    result = fetch_article(session, url, timeout, row.get("title", ""))
                    if not result:
                        failed += 1
                        continue

                    metadata, metadata_title, raw_text, body, location = result
                    title = clean_article_title(row.get("title")) or metadata_title
                    # The page title is a fallback when stored titles are HTML or empty.
                    if not title:
                        title = clean_article_title(getattr(metadata, "title", ""))
                    if len(body) < 100:
                        failed += 1
                        continue

                    language = detect_language(body)
                    if language == "mixed":
                        tamil_chars = sum(1 for char in body if "\u0B80" <= char <= "\u0BFF")
                        latin_chars = sum(1 for char in body if char.isascii() and char.isalpha())
                        language = "ta" if tamil_chars > latin_chars else "en"
                    body = clean_article_body(body, title, language=language)
                    title = normalize_political_parties(title, language)
                    body = clean_article_body(body, title, language=language)
                    description = clean_html(row.get("description"))
                    if not description:
                        description = clean_html(getattr(metadata, "description", ""))
                    words = len(body.split())
                    article_length = "short" if words < 250 else "medium" if words < 800 else "long"
                    clean_text = format_clean_article(title, body)
                    row_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
                    writer.writerow({
                        "content_hash": row_hash,
                        "guid": row.get("guid", ""),
                        "outlet_slug": row.get("outlet_slug", ""),
                        "title": title,
                        "description": description,
                        "author": clean_html(row.get("author")) or clean_html(getattr(metadata, "author", "")),
                        "published_at": row.get("published_at", ""),
                        "language": language,
                        "article_length": article_length,
                        "data_fetch_via": row.get("data_fetch_via", ""),
                        "canonical_url": url,
                        "extraction_method": "trafilatura",
                        "extraction_quality": 0.9,
                        "processing_status": "cleaned",
                        "raw_text": raw_text,
                        "clean_text": clean_text,
                        "topic": classify_topic(title, body, row.get("outlet_slug", ""), location),
                        "cluster_id": "",
                        "named_entities": json.dumps({"LOCATION": [location]} if location else {}, ensure_ascii=False),
                        "embedding": "",
                        "summary": "[]",
                    })
                    written += 1
                    if batch_seen >= batch_size:
                        output_file.flush()
                        print(f"Batch checkpoint: scanned={scanned}, written={written}, unavailable={failed}", flush=True)
                        batch_seen = 0
                    if delay:
                        time.sleep(delay)

                output_file.flush()
                os.fsync(output_file.fileno())

        if not scanned:
            raise RuntimeError(
                "No 2026 source rows were found. The existing output was preserved; "
                "check the input dates and CSV header before retrying."
            )
        if not written:
            raise RuntimeError(
                "No 2026 articles were exported. The existing output was preserved; "
                "check network access, source URLs, and the extraction log before retrying."
            )
        os.replace(temp_path, output_path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
    finally:
        session.close()
        if os.path.exists(snapshot_path):
            os.remove(snapshot_path)

    print(
        f"Done. 2026 rows scanned={scanned}; exported={written}; "
        f"unavailable/invalid articles omitted={failed}; other years skipped={skipped}.\n"
        f"Output: {output_path}",
        flush=True,
    )
    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Source CSV (default: backend/data/trafiltura_preprocessed.csv)")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output CSV (default: backend/data/trafiltura_processed.csv)")
    parser.add_argument("--batch-size", type=int, default=50, help="Progress checkpoint interval; does not limit total rows")
    parser.add_argument("--timeout", type=int, default=20, help="Per-article HTTP timeout in seconds")
    parser.add_argument("--delay", type=float, default=0.2, help="Pause between requests in seconds")
    args = parser.parse_args()
    if args.batch_size < 1 or args.timeout < 1 or args.delay < 0:
        parser.error("batch-size and timeout must be positive, and delay cannot be negative")
    export_2026(args.input, args.output, args.batch_size, args.timeout, args.delay)


if __name__ == "__main__":
    main()
