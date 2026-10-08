"""Evaluate existing event assignments against manually labeled article pairs.

Input CSV columns: guid_a,guid_b,same_event. Gold labels must be human-reviewed.
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from backend.evaluation.metrics import RESULTS_DIR, binary_metrics, plot_metric_groups, timestamp, write_csv, write_json
from backend.models.database import SessionLocal, Article

ANNOTATIONS_DIR = os.path.join(os.path.dirname(__file__), "annotations")
DEFAULT_PAIRS = os.path.join(ANNOTATIONS_DIR, "event_pairs.csv")


def parse_bool(value):
    text = str(value).strip().casefold()
    if text in {"1", "true", "yes", "same"}:
        return 1
    if text in {"0", "false", "no", "different", "diff"}:
        return 0
    raise ValueError(f"Invalid same_event value: {value!r}")


def evaluate(pairs_path):
    with open(pairs_path, newline="", encoding="utf-8-sig") as handle:
        pairs = list(csv.DictReader(handle))
    if not pairs:
        raise ValueError(f"No labeled pairs in {pairs_path}; annotate the template first.")
    for required in ("guid_a", "guid_b", "same_event"):
        if required not in pairs[0]:
            raise ValueError(f"Missing required column {required!r} in {pairs_path}")

    guids = {row[key].strip() for row in pairs for key in ("guid_a", "guid_b") if row.get(key)}
    db = SessionLocal()
    try:
        articles = db.query(Article).filter(Article.guid.in_(guids)).all()
        lookup = {article.guid: article for article in articles}
        grouped = {"ta": ([], []), "en": ([], [])}
        skipped = 0
        for row in pairs:
            left, right = lookup.get(row.get("guid_a", "").strip()), lookup.get(row.get("guid_b", "").strip())
            if not left or not right:
                skipped += 1
                continue
            lang_left = (left.language or "").casefold()
            lang_right = (right.language or "").casefold()
            lang = "ta" if lang_left in {"ta", "tam", "tamil", "ta-in"} else "en" if lang_left in {"en", "eng", "english", "en-in"} else None
            if lang is None or lang != ("ta" if lang_right in {"ta", "tam", "tamil", "ta-in"} else "en" if lang_right in {"en", "eng", "english", "en-in"} else None):
                skipped += 1
                continue
            gold = parse_bool(row["same_event"])
            predicted = int(left.cluster_id is not None and left.cluster_id == right.cluster_id)
            grouped[lang][0].append(gold)
            grouped[lang][1].append(predicted)
    finally:
        db.close()

    results = {}
    for lang, (gold, prediction) in grouped.items():
        if gold:
            results[lang] = binary_metrics(gold, prediction)
    if not results:
        raise ValueError("No valid same-language pairs matched article records in PostgreSQL.")

    stamp = timestamp()
    payload = {
        "task": "article_pair_event_clustering",
        "prediction": "same cluster_id",
        "gold_label_source": "human_annotated_pairs",
        "skipped_pairs": skipped,
        "by_language": results,
    }
    json_path = os.path.join(RESULTS_DIR, f"event_clustering_{stamp}.json")
    csv_path = os.path.join(RESULTS_DIR, f"event_clustering_{stamp}.csv")
    png_path = os.path.join(RESULTS_DIR, f"event_clustering_{stamp}.png")
    write_json(json_path, payload)
    write_csv(csv_path, [
        {"language": lang, **{k: v for k, v in metric.items() if k != "per_class"}}
        for lang, metric in results.items()
    ], ["language", "accuracy", "precision", "recall", "f1", "macro_precision", "macro_recall", "macro_f1", "same_event_support", "pair_count"])
    plot_metric_groups(png_path, ["Accuracy", "Macro P", "Macro R", "Macro F1", "Same-event F1"], results,
                       "Event-clustering pair metrics by language", "Score", ["accuracy", "macro_precision", "macro_recall", "macro_f1", "f1"])
    print(f"Event-clustering evaluation saved: {csv_path}, {json_path}, {png_path}")
    for lang, metric in results.items():
        print(f"{lang}: pairs={metric['pair_count']} accuracy={metric['accuracy']:.4f} macro_f1={metric['macro_f1']:.4f} same_event_f1={metric['f1']:.4f}")
    print(f"Skipped pairs: {skipped}; scores require reviewed human pair labels.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", default=DEFAULT_PAIRS)
    args = parser.parse_args()
    evaluate(args.pairs)
