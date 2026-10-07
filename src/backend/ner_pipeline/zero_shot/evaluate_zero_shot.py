"""
Veritas Lens — Zero-Shot NER Evaluation
=========================================
Evaluates the NER pipeline on articles from the database, computing
Precision, Recall, and F1 scores for PERSON, LOCATION, ORGANIZATION,
and EVENT — separately for Tamil and English.

Outputs:
  - evaluation/ner_metrics.csv      — per-article metrics
  - evaluation/ner_extractions.csv  — per-article extracted entities
  - evaluation/ner_macro_scores.csv — macro-averaged scores per run
"""

import sys
import os
import time
import csv
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from backend.models.database import SessionLocal, Article
from backend.ner_pipeline.zero_shot.nlp_pipeline import (
    normalize_text,
    segment_sentences,
    get_ner_pipeline,
    is_valid_entity,
    resolve_entity,
    MAX_SENTENCES,
)

# ---------------------------------------------------------------------------
# Ground truth — populate with manual annotations for real evaluation
# Format: { article_id: { "PERSON": [...], "LOCATION": [...], ... } }
# ---------------------------------------------------------------------------
GROUND_TRUTH = {}

ENTITY_TYPES = ["PERSON", "LOCATION", "ORGANIZATION", "EVENT"]


def calculate_metrics(predicted: list, truth: list) -> tuple:
    """Calculate Precision, Recall, F1 for two entity lists.

    Returns (precision, recall, f1, is_valid) where is_valid is False
    when both sets are empty (true negative — skip from macro average).
    """
    pred_set = set(predicted)
    truth_set = set(truth)

    # If both empty, this is a true negative — not informative
    if not pred_set and not truth_set:
        return (0.0, 0.0, 0.0, False)

    tp = len(pred_set & truth_set)
    fp = len(pred_set - truth_set)
    fn = len(truth_set - pred_set)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return (precision, recall, f1, True)


def evaluate_zero_shot(limit: int = 50):
    """Run the full evaluation pipeline."""
    db = SessionLocal()
    try:
        articles = db.query(Article).filter(
            Article.clean_text.isnot(None),
            Article.clean_text != "",
        ).limit(limit).all()

        if not articles:
            print("No articles found in DB.")
            return

        print(f"Evaluating {len(articles)} articles for Zero-Shot NER...")
        ner_pipeline = get_ner_pipeline()

        extractions_data = []
        metrics_data = []

        # Accumulators for macro scores per language
        macro_accum = {
            "en": {cat: {"p": [], "r": [], "f1": []} for cat in ENTITY_TYPES},
            "ta": {cat: {"p": [], "r": [], "f1": []} for cat in ENTITY_TYPES},
        }

        for idx, article in enumerate(articles):
            lang = article.language if article.language in ("en", "ta") else "ta"
            norm_text = normalize_text(article.clean_text)
            sentences = segment_sentences(norm_text)
            target_sentences = sentences[:MAX_SENTENCES]

            entities = defaultdict(list)

            start_time = time.time()
            if target_sentences:
                results = ner_pipeline(target_sentences)
                for sentence_result in results:
                    for ent in sentence_result:
                        group = ent.get('entity_group', ent.get('entity', ''))
                        word = ent.get('word', '').strip()

                        if not is_valid_entity(word):
                            continue

                        mapped_group = None
                        if group in ('PER', 'PERSON', 'B-PERSON', 'I-PERSON'):
                            mapped_group = 'PERSON'
                        elif group in ('ORG', 'ORGANIZATION', 'B-ORGANIZATION', 'I-ORGANIZATION'):
                            mapped_group = 'ORGANIZATION'
                        elif group in ('LOC', 'LOCATION', 'B-LOCATION', 'I-LOCATION'):
                            mapped_group = 'LOCATION'
                        elif group in ('MISC', 'EVENT', 'B-EVENT', 'I-EVENT'):
                            mapped_group = 'EVENT'

                        if mapped_group:
                            resolved = resolve_entity(word, mapped_group, lang)
                            if resolved and resolved not in entities[mapped_group]:
                                entities[mapped_group].append(resolved)

            elapsed = time.time() - start_time

            # --- Metrics against ground truth ---
            ground_truth = GROUND_TRUTH.get(article.id, {})
            has_truth = bool(ground_truth)

            row = {
                "article_id": article.id,
                "language": lang,
                "processing_time_sec": round(elapsed, 4),
            }

            for cat in ENTITY_TYPES:
                row[f"num_{cat.lower()}"] = len(entities.get(cat, []))

                if has_truth:
                    p, r, f1, valid = calculate_metrics(
                        entities.get(cat, []), ground_truth.get(cat, [])
                    )
                    row[f"p_{cat.lower()}"] = round(p, 4)
                    row[f"r_{cat.lower()}"] = round(r, 4)
                    row[f"f1_{cat.lower()}"] = round(f1, 4)
                    if valid:
                        macro_accum[lang][cat]["p"].append(p)
                        macro_accum[lang][cat]["r"].append(r)
                        macro_accum[lang][cat]["f1"].append(f1)
                else:
                    row[f"p_{cat.lower()}"] = ""
                    row[f"r_{cat.lower()}"] = ""
                    row[f"f1_{cat.lower()}"] = ""

            metrics_data.append(row)

            extractions_data.append({
                "article_id": article.id,
                "headline": article.title,
                "language": lang,
                "PERSON": ", ".join(entities.get("PERSON", [])),
                "LOCATION": ", ".join(entities.get("LOCATION", [])),
                "ORGANIZATION": ", ".join(entities.get("ORGANIZATION", [])),
                "EVENT": ", ".join(entities.get("EVENT", [])),
            })

        # --- Write CSVs ---
        project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')
        )
        eval_dir = os.path.join(project_root, "evaluation")
        os.makedirs(eval_dir, exist_ok=True)

        # Per-article metrics (fresh write — no duplicates)
        metrics_csv = os.path.join(eval_dir, "ner_metrics.csv")
        if metrics_data:
            fieldnames = list(metrics_data[0].keys())
            with open(metrics_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(metrics_data)

        # Per-article extractions (fresh write)
        extractions_csv = os.path.join(eval_dir, "ner_extractions.csv")
        if extractions_data:
            fieldnames = ["article_id", "headline", "language",
                          "PERSON", "LOCATION", "ORGANIZATION", "EVENT"]
            with open(extractions_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(extractions_data)

        # --- Macro scores CSV (append per run) ---
        macro_csv = os.path.join(eval_dir, "ner_macro_scores.csv")
        macro_rows = []
        for lang_code in ("en", "ta"):
            macro_p_all, macro_r_all, macro_f1_all = [], [], []
            for cat in ENTITY_TYPES:
                scores = macro_accum[lang_code][cat]
                if scores["f1"]:
                    macro_p_all.append(sum(scores["p"]) / len(scores["p"]))
                    macro_r_all.append(sum(scores["r"]) / len(scores["r"]))
                    macro_f1_all.append(sum(scores["f1"]) / len(scores["f1"]))

            macro_rows.append({
                "timestamp": datetime.utcnow().isoformat(),
                "language": lang_code,
                "num_articles": sum(
                    1 for m in metrics_data if m["language"] == lang_code
                ),
                "macro_precision": round(
                    sum(macro_p_all) / len(macro_p_all), 4
                ) if macro_p_all else "",
                "macro_recall": round(
                    sum(macro_r_all) / len(macro_r_all), 4
                ) if macro_r_all else "",
                "macro_f1": round(
                    sum(macro_f1_all) / len(macro_f1_all), 4
                ) if macro_f1_all else "",
            })

        if macro_rows:
            file_exists = os.path.isfile(macro_csv)
            with open(macro_csv, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=macro_rows[0].keys())
                if not file_exists:
                    writer.writeheader()
                writer.writerows(macro_rows)

        # --- Console output ---
        print(f"Evaluation complete. {len(metrics_data)} articles processed.")
        print(f"  Metrics:      {metrics_csv}")
        print(f"  Extractions:  {extractions_csv}")
        print(f"  Macro scores: {macro_csv}")

        print("\nMACRO SCORES BY LANGUAGE:")
        for lang_code in ("en", "ta"):
            print(f"--- Language: {lang_code.upper()} ---")
            for cat in ENTITY_TYPES:
                scores = macro_accum[lang_code][cat]
                if scores["f1"]:
                    p = sum(scores["p"]) / len(scores["p"])
                    r = sum(scores["r"]) / len(scores["r"])
                    f1 = sum(scores["f1"]) / len(scores["f1"])
                    print(f"  {cat}: P={p:.4f}, R={r:.4f}, F1={f1:.4f}")
                else:
                    print(f"  {cat}: No ground truth data available.")

    finally:
        db.close()


if __name__ == '__main__':
    evaluate_zero_shot(50)
