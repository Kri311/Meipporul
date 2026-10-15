import csv
import os
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from backend.ingestion.tasks.text_cleaning import parse_clean_article

def clean_and_normalize(text: str) -> str:
    """Normalize text: remove whitespaces, newlines, fix unicode, etc."""
    if not text:
        return ""
    # Remove URLs
    text = re.sub(r'http\S+|www.\S+', '', text)
    # Remove hashtags
    text = re.sub(r'#\w+', '', text)
    # Normalize unicode and whitespace
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r'\s+', ' ', text)
    text = text.replace('\u201c', '"').replace('\u201d', '"')
    text = text.replace('\u2018', "'").replace('\u2019', "'")
    return text.strip()

def create_dataset():
    project_root = Path(__file__).resolve().parents[4]
    csv_path = project_root / "src" / "backend" / "data" / "trafiltura_preprocessed.csv"
    output_dir = Path(__file__).resolve().parent / "dataset"
    output_dir.mkdir(parents=True, exist_ok=True)
    if not csv_path.is_file():
        raise FileNotFoundError(
            f"Canonical processed dataset not found: {csv_path}. Run RSS ingestion/export first."
        )

    dataset, seen = [], set()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            language = (row.get("language") or "").strip().lower().split("-")[0]
            if language not in {"en", "ta"}:
                continue
            title = clean_and_normalize(row.get("title", ""))
            _, body = parse_clean_article(row.get("clean_text", ""), title)
            body = clean_and_normalize(body)
            if not title or len(body) < 100:
                continue
            identity = (row.get("content_hash") or "").strip() or re.sub(r"\W+", "", body.casefold())
            if identity in seen:
                continue
            seen.add(identity)
            dataset.append({"language": language, "headline": title, "content": body})

    tamil_data = [item for item in dataset if item["language"] == "ta"]
    english_data = [item for item in dataset if item["language"] == "en"]
    for filename, rows in (("tamil_corpus.json", tamil_data), ("english_corpus.json", english_data)):
        with (output_dir / filename).open("w", encoding="utf-8") as output:
            import json
            json.dump(rows, output, ensure_ascii=False, indent=2)

    print(f"Source: {csv_path}")
    print(f"Prepared {len(tamil_data)} Tamil and {len(english_data)} English cleaned articles for annotation/fine-tuning.")
    print(f"Data saved to {output_dir}")

if __name__ == "__main__":
    create_dataset()
