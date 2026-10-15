"""Evaluate bilingual extractive event summaries against human references.

Input CSV columns: language,article_guids,reference_summary. Separate multiple
article GUIDs in a row with '|'. Empty/unreviewed references are not scored.
"""
import argparse
import csv
import os
import re
import sys
import unicodedata
from collections import Counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from backend.evaluation.metrics import RESULTS_DIR, plot_metric_groups, timestamp, write_csv, write_json
from backend.models.database import SessionLocal, Article
from backend.summarization.english import summarize_event as summarize_english
from backend.summarization.tamil import summarize_event as summarize_tamil

ANNOTATIONS_DIR = os.path.join(os.path.dirname(__file__), "annotations")
DEFAULT_REFERENCES = os.path.join(ANNOTATIONS_DIR, "summaries.csv")


def tokens(text):
    text = unicodedata.normalize("NFC", text or "").casefold()
    return re.findall(r"[\w\u0B80-\u0BFF]+", text, flags=re.UNICODE)


def f1_from_overlap(overlap, pred_count, ref_count):
    precision = overlap / pred_count if pred_count else 0.0
    recall = overlap / ref_count if ref_count else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def rouge_n(prediction, reference, n):
    pred = Counter(tuple(prediction[i:i+n]) for i in range(max(0, len(prediction) - n + 1)))
    ref = Counter(tuple(reference[i:i+n]) for i in range(max(0, len(reference) - n + 1)))
    overlap = sum((pred & ref).values())
    return f1_from_overlap(overlap, sum(pred.values()), sum(ref.values()))


def rouge_l(prediction, reference):
    previous = [0] * (len(reference) + 1)
    for pred_token in prediction:
        current = [0]
        for index, ref_token in enumerate(reference, 1):
            current.append(previous[index - 1] + 1 if pred_token == ref_token else max(previous[index], current[-1]))
        previous = current
    return f1_from_overlap(previous[-1], len(prediction), len(reference))


def chrf(prediction, reference, max_order=6):
    pred = unicodedata.normalize("NFC", prediction or "").replace(" ", "")
    ref = unicodedata.normalize("NFC", reference or "").replace(" ", "")
    scores = []
    for n in range(1, max_order + 1):
        pred_grams = Counter(pred[i:i+n] for i in range(max(0, len(pred) - n + 1)))
        ref_grams = Counter(ref[i:i+n] for i in range(max(0, len(ref) - n + 1)))
        if pred_grams or ref_grams:
            scores.append(f1_from_overlap(sum((pred_grams & ref_grams).values()), sum(pred_grams.values()), sum(ref_grams.values())))
    return sum(scores) / len(scores) if scores else 0.0


def evaluate(references_path):
    with open(references_path, newline="", encoding="utf-8-sig") as handle:
        references = [row for row in csv.DictReader(handle) if (row.get("reference_summary") or "").strip()]
    if not references:
        raise ValueError(f"No human reference summaries in {references_path}; annotate the template first.")
    for column in ("language", "article_guids", "reference_summary"):
        if column not in references[0]:
            raise ValueError(f"Missing required column {column!r} in {references_path}")

    all_guids = {guid.strip() for row in references for guid in row["article_guids"].split("|") if guid.strip()}
    db = SessionLocal()
    try:
        articles = db.query(Article).filter(Article.guid.in_(all_guids)).all()
        lookup = {article.guid: article for article in articles}
    finally:
        db.close()

    by_language = {"ta": [], "en": []}
    skipped = 0
    for row in references:
        lang_value = row["language"].strip().casefold()
        lang = "ta" if lang_value in {"ta", "tam", "tamil"} else "en" if lang_value in {"en", "eng", "english"} else None
        grouped_articles = [lookup.get(guid.strip()) for guid in row["article_guids"].split("|") if guid.strip()]
        if lang is None or not grouped_articles or any(article is None for article in grouped_articles):
            skipped += 1
            continue
        if any((article.language or "").casefold() not in ({"ta", "tam", "tamil", "ta-in"} if lang == "ta" else {"en", "eng", "english", "en-in"}) for article in grouped_articles):
            skipped += 1
            continue
        predicted_text = summarize_tamil(grouped_articles) if lang == "ta" else summarize_english(grouped_articles)
        pred_tokens, ref_tokens = tokens(predicted_text), tokens(row["reference_summary"])
        by_language[lang].append({
            "rouge1_f1": rouge_n(pred_tokens, ref_tokens, 1),
            "rouge2_f1": rouge_n(pred_tokens, ref_tokens, 2),
            "rougeL_f1": rouge_l(pred_tokens, ref_tokens),
            "chrf": chrf(predicted_text, row["reference_summary"]),
        })
    results = {}
    for lang, examples in by_language.items():
        if examples:
            results[lang] = {
                metric: sum(example[metric] for example in examples) / len(examples)
                for metric in ("rouge1_f1", "rouge2_f1", "rougeL_f1", "chrf")
            }
            results[lang]["examples"] = len(examples)
    if not results:
        raise ValueError("No references matched articles in PostgreSQL for either language.")

    stamp = timestamp()
    payload = {
        "task": "extractive_event_summarization",
        "gold_label_source": "human_reference_summaries",
        "averaging": "macro mean over reference examples per language",
        "skipped_references": skipped,
        "by_language": results,
    }
    json_path = os.path.join(RESULTS_DIR, f"summarization_{stamp}.json")
    csv_path = os.path.join(RESULTS_DIR, f"summarization_{stamp}.csv")
    png_path = os.path.join(RESULTS_DIR, f"summarization_{stamp}.png")
    write_json(json_path, payload)
    write_csv(csv_path, [{"language": lang, **metrics} for lang, metrics in results.items()], ["language", "rouge1_f1", "rouge2_f1", "rougeL_f1", "chrf", "examples"])
    plot_metric_groups(png_path, ["ROUGE-1 F1", "ROUGE-2 F1", "ROUGE-L F1", "chrF"], results,
                       "Summary quality by language", "Macro score", ["rouge1_f1", "rouge2_f1", "rougeL_f1", "chrf"])
    print(f"Summarization evaluation saved: {csv_path}, {json_path}, {png_path}")
    for lang, metric in results.items():
        print(f"{lang}: n={metric['examples']} R1={metric['rouge1_f1']:.4f} R2={metric['rouge2_f1']:.4f} RL={metric['rougeL_f1']:.4f} chrF={metric['chrf']:.4f}")
    print("These scores are reference-dependent; only human-reviewed summaries are valid gold targets.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--references", default=DEFAULT_REFERENCES)
    args = parser.parse_args()
    evaluate(args.references)
