#!/usr/bin/env python3
"""Re-clean an existing export locally and keep only complete 2026 articles."""

import argparse
import csv
import hashlib
import json
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from backend.ingestion.tasks.text_cleaning import (  # noqa: E402
    clean_article_body,
    clean_article_title,
    build_article_description,
    clean_html,
    detect_language,
    extract_dateline_location,
    format_clean_article,
    normalize_political_parties,
    classify_topic,
    parse_clean_article,
)

FIELDNAMES = [
    "content_hash", "guid", "outlet_slug", "title", "description", "author",
    "published_at", "language", "article_length", "data_fetch_via",
    "canonical_url", "extraction_method", "extraction_quality",
    "processing_status", "raw_text", "clean_text", "topic", "cluster_id",
    "semantic_text_hash", "named_entities", "embedding",
]


def reclean_export(path):
    temp_path = path + ".reclean.tmp"
    count = 0
    with open(path, "r", encoding="utf-8-sig", newline="") as input_file:
        reader = csv.DictReader(input_file)
        if reader.fieldnames != FIELDNAMES:
            raise ValueError("Input CSV does not match the expected 21-column schema.")
        with open(temp_path, "w", encoding="utf-8-sig", newline="") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=FIELDNAMES)
            writer.writeheader()
            for row in reader:
                try:
                    year = int((row.get("published_at") or "")[:4])
                except (TypeError, ValueError):
                    continue
                if year != 2026:
                    continue

                title = clean_article_title(row.get("title"))
                _, existing_body = parse_clean_article(row.get("clean_text"), title)
                source_text = existing_body or clean_html(row.get("raw_text", ""))
                location, source_text = extract_dateline_location(source_text)
                language = row.get("language") if row.get("language") in {"en", "ta"} else detect_language(source_text)
                body = clean_article_body(source_text, title, language=language)
                title = normalize_political_parties(title, language)
                body = clean_article_body(body, title, language=language)
                if not title or len(body) < 100:
                    continue
                words = len(body.split())
                content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
                try:
                    entities = json.loads(row.get("named_entities") or "{}")
                    if not isinstance(entities, dict):
                        entities = {}
                except (TypeError, ValueError):
                    entities = {}
                locations = entities.get("LOCATION", [])
                if not isinstance(locations, list):
                    locations = [locations] if locations else []
                if location and location not in locations:
                    locations.append(location)
                if locations:
                    entities["LOCATION"] = locations
                changed = content_hash != (row.get("content_hash") or "") or title != row.get("title")
                row.update({
                    "content_hash": content_hash,
                    "title": title,
                    "description": build_article_description(row.get("description", ""), body, title),
                    "language": language,
                    "article_length": "short" if words < 250 else "medium" if words < 800 else "long",
                    "processing_status": "cleaned",
                    "clean_text": format_clean_article(title, body),
                    "topic": classify_topic(title, body, row.get("outlet_slug", ""), location) if changed else row.get("topic", ""),
                    "cluster_id": "" if changed else row.get("cluster_id", ""),
                    "semantic_text_hash": "" if changed else row.get("semantic_text_hash", ""),
                    "named_entities": json.dumps(entities, ensure_ascii=False),
                    "embedding": "" if changed else row.get("embedding", ""),
                })
                writer.writerow(row)
                count += 1
            output_file.flush()
            os.fsync(output_file.fileno())
    os.replace(temp_path, path)
    print(f"Re-cleaned {count} 2026 rows from clean_text/raw_text: {path}")
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default=os.path.join(PROJECT_ROOT, "src", "backend", "data", "trafiltura_processed.csv"),
    )
    args = parser.parse_args()
    reclean_export(args.input)


if __name__ == "__main__":
    main()
