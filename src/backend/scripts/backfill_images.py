#!/usr/bin/env python3
"""Fetch lead images for dated articles and sync PostgreSQL + CSV.

This operation only fills empty image_url values. It preserves all existing
columns and article content in trafiltura_preprocessed.csv.
"""

import argparse
import csv
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from backend.models.database import SessionLocal, Article
from backend.ingestion.tasks.text_cleaning import article_page_matches_title

CSV_PATH = os.path.join(PROJECT_ROOT, "src", "backend", "data", "trafiltura_preprocessed.csv")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
IMAGE_META_KEYS = ("og:image", "og:image:url", "twitter:image", "twitter:image:src")


def valid_image_url(candidate, page_url):
    if not candidate:
        return None
    candidate = urljoin(page_url, candidate.strip())
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if any(token in parsed.path.casefold() for token in ("logo", "avatar", "icon", "sprite", "placeholder", "default-image")):
        return None
    return candidate


def image_from_html(html_bytes, page_url):
    if not html_bytes:
        return None
    soup = BeautifulSoup(html_bytes, "html.parser")
    for key in IMAGE_META_KEYS:
        node = soup.find("meta", property=key)
        if node is None:
            node = soup.find("meta", attrs={"name": key})
        if node is not None and node.get("content"):
            candidate = valid_image_url(node["content"], page_url)
            if candidate:
                return candidate

    for selector in (
        "article img[src]", "main img[src]", "article img[data-src]",
        "main img[data-src]", "article img[srcset]", "main img[srcset]",
    ):
        image = soup.select_one(selector)
        if image:
            candidate = image.get("src") or image.get("data-src")
            if not candidate and image.get("srcset"):
                candidate = image["srcset"].split(",", 1)[0].strip().split()[0]
            candidate = valid_image_url(candidate, page_url)
            if candidate:
                return candidate
    return None


def fetch_image(row, timeout):
    url = (row.get("canonical_url") or "").strip()
    if not url:
        return row.get("guid", ""), None, "missing_url"
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            timeout=timeout,
            allow_redirects=True,
        )
        if response.status_code != 200:
            return row.get("guid", ""), None, f"http_{response.status_code}"
        if not article_page_matches_title(response.content, row.get("title", "")):
            return row.get("guid", ""), None, "title_mismatch"
        return row.get("guid", ""), image_from_html(response.content, response.url), "ok"
    except requests.RequestException as exc:
        return row.get("guid", ""), None, type(exc).__name__


def load_csv(path):
    with open(path, "r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")
        fieldnames = list(reader.fieldnames)
        rows = list(reader)
    if "image_url" not in fieldnames:
        fieldnames.append("image_url")
        for row in rows:
            row["image_url"] = ""
    return fieldnames, rows


def write_csv_atomic(path, fieldnames, rows):
    folder = os.path.dirname(path)
    fd, temp_path = tempfile.mkstemp(prefix=".image_backfill_", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=CSV_PATH, help="Processed CSV to update")
    parser.add_argument("--workers", type=int, default=5, help="Concurrent publisher requests")
    parser.add_argument("--timeout", type=float, default=15, help="Per-page request timeout")
    parser.add_argument("--delay", type=float, default=0.15, help="Pause between request batches")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument(
        "--refresh", action="store_true",
        help="Refetch and replace existing images for all dated articles (use to repair mismatched/old images)",
    )
    args = parser.parse_args()
    if args.workers < 1 or args.batch_size < 1:
        parser.error("--workers and --batch-size must be positive")

    fieldnames, rows = load_csv(args.csv)
    # Repair images for the full dated archive, including newly collected news.
    eligible = []
    for row in rows:
        if (row.get("image_url") or "").strip() and not args.refresh:
            continue
        if not row.get("published_at"):
            continue
        eligible.append(row)

    print(f"Rows in CSV: {len(rows)}; dated rows needing images: {len(eligible)}")
    fetched = {}
    checked = {}
    outcomes = {}
    for start in range(0, len(eligible), args.batch_size):
        batch = eligible[start:start + args.batch_size]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(fetch_image, row, args.timeout) for row in batch]
            for future in as_completed(futures):
                guid, image_url, result = future.result()
                if guid:
                    checked[guid] = (image_url, result)
                if guid and image_url:
                    fetched[guid] = image_url
                outcomes[result] = outcomes.get(result, 0) + 1
        print(f"Checked {min(start + len(batch), len(eligible))}/{len(eligible)}; found {len(fetched)} images")
        if args.delay and start + args.batch_size < len(eligible):
            time.sleep(args.delay)

    # Persist DB first. If DB is unavailable, leave the CSV untouched.
    db = SessionLocal()
    try:
        csv_guids = [row.get("guid") for row in rows if row.get("guid")]
        db_rows = db.query(Article).filter(Article.guid.in_(csv_guids)).all() if csv_guids else []
        db_by_guid = {article.guid: article for article in db_rows}
        for guid, (image_url, result) in checked.items():
            article = db_by_guid.get(guid)
            if article and image_url and (args.refresh or not article.image_url):
                article.image_url = image_url
                db_by_guid[guid] = article
            elif article and args.refresh and result in {"ok", "title_mismatch"}:
                # A successful page check with no verified article image must
                # clear a previously stored, potentially unrelated thumbnail.
                article.image_url = None
                db_by_guid[guid] = article
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    synced = 0
    for row in rows:
        article = db_by_guid.get(row.get("guid"))
        if article and (args.refresh or article.image_url):
            row["image_url"] = article.image_url or ""
            synced += 1
    write_csv_atomic(args.csv, fieldnames, rows)
    print(f"Images fetched: {len(fetched)}; CSV rows synced from PostgreSQL: {synced}")
    print(f"Result counts: {outcomes}")
    print(f"Updated CSV: {args.csv}")


if __name__ == "__main__":
    main()
