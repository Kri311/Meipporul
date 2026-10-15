"""Create a bilingual article-to-bullet-summary annotation template."""

import argparse
import csv
import hashlib
import os
import random
import re

from backend.ingestion.tasks.text_cleaning import parse_clean_article


def prepare(input_csv, output_csv, per_language=250, seed=29, force=False):
    if os.path.exists(output_csv) and not force:
        raise FileExistsError(f"Refusing to overwrite {output_csv}; pass --force to replace it.")
    buckets = {"en": [], "ta": []}
    seen = {"en": set(), "ta": set()}
    with open(input_csv, encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            language = (row.get("language") or "").casefold().split("-")[0]
            if language not in buckets:
                continue
            title, body = parse_clean_article(row.get("clean_text"), row.get("title", ""))
            body = re.sub(r"\s+", " ", body or row.get("description", "")).strip()
            if len(body) < 200:
                continue
            identity = row.get("guid") or hashlib.sha256(
                re.sub(r"\s+", " ", f"{title} {body[:600]}".casefold()).encode("utf-8")
            ).hexdigest()
            if identity in seen[language]:
                continue
            seen[language].add(identity)
            buckets[language].append({
                "article_id": hashlib.sha256(str(identity).encode("utf-8")).hexdigest(),
                "event_group": "",
                "outlet_slug": row.get("outlet_slug", ""),
                "language": language,
                "title": title,
                "body": body[:6000],
                "summary_bullets": "",
            })

    rng = random.Random(seed)
    rows = []
    for language, candidates in buckets.items():
        rng.shuffle(candidates)
        rows.extend(candidates[:per_language])
    rows.sort(key=lambda row: (row["language"], row["article_id"]))
    os.makedirs(os.path.dirname(os.path.abspath(output_csv)), exist_ok=True)
    fields = ["article_id", "event_group", "outlet_slug", "language", "title", "body", "summary_bullets"]
    with open(output_csv, "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {output_csv}; en={sum(r['language']=='en' for r in rows)}, ta={sum(r['language']=='ta' for r in rows)}")
    print("Fill summary_bullets with 3-7 reviewed factual bullets in the article's language.")
    print("Fill event_group with a shared ID for articles covering the same event to keep them in one split.")


if __name__ == "__main__":
    default_input = os.path.join(os.path.dirname(__file__), "..", "data", "trafiltura_preprocessed.csv")
    default_output = os.path.join(os.path.dirname(__file__), "..", "data", "summary_labels_to_annotate.csv")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=os.path.abspath(default_input))
    parser.add_argument("--output", default=os.path.abspath(default_output))
    parser.add_argument("--per-language", type=int, default=250)
    parser.add_argument("--seed", type=int, default=29)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    prepare(args.input, args.output, args.per_language, args.seed, args.force)
