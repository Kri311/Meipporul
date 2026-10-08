"""
Veritas Lens — Embedding Metrics Report
=========================================

Evaluates Tamil-ai/tamil-embed-base embeddings using classification metrics.
Uses KNN on embeddings as features for two classification tasks:
  1. Language Classification (Tamil vs English)
  2. Orientation Bucket Classification (IND / CON / DRV / MIXED)

Metrics computed:
  - Accuracy
  - Precision (per-class and weighted)
  - Recall (per-class and weighted)
  - F1 Score (per-class and weighted)
  - Macro F1 Score
  - Confusion Matrix
  - Cross-lingual retrieval Precision@K

Also reports embedding quality stats:
  - Encoding speed (articles/sec)
  - Cross-lingual similarity distributions
  - Intra-language separation ratio

Usage:
    python -m embeddings.embedding_metrics_report
    python -m embeddings.embedding_metrics_report --sample 300
    python -m embeddings.embedding_metrics_report --cpu  # Force CPU mode
"""

import os
import sys
import csv
import time
import argparse
import numpy as np
from collections import Counter
from datetime import datetime

# ── Configuration ──
MODEL_NAME = "Tamil-ai/tamil-embed-base"
EMBEDDING_DIM = 768
BATCH_SIZE = 50

# Orientation bucket mapping: outlet_slug → orientation_bucket
# (derived from backend.config/sources.yaml)
OUTLET_ORIENTATION = {
    "the_hindu_english": "IND",
    "ndtv": "IND",
    "bbc_tamil": "IND",
    "times_of_india": "IND",
    "dinamani": "IND",
    "indian_express": "IND",
    "tamil_one_india": "IND",
    "tamil_mykhel": "IND",
    "tamil_gizbot": "IND",
    "news18_india": "CON",
    "news18_tamil_nadu": "CON",
    "republic_tv": "CON",
    "tamil_asianet": "CON",
    "vikatan": "DRV",
    "google_news_tamil": "MIXED",
    "google_news_english": "MIXED",
}


def load_articles(csv_path: str, sample_size: int = None):
    """Load articles from raw_processed.csv with language and orientation labels."""
    print(f"\nLoading articles from {csv_path}...")

    if not os.path.exists(csv_path):
        print(f"File not found: {csv_path}")
        sys.exit(1)

    articles = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("clean_text") and row.get("title") and row.get("language") in ("ta", "en"):
                outlet = row.get("outlet_slug", "")
                orientation = OUTLET_ORIENTATION.get(outlet, "UNKNOWN")
                if orientation != "UNKNOWN":
                    row["orientation_bucket"] = orientation
                    articles.append(row)

    print(f"   Loaded {len(articles)} articles (with known orientation)")

    if sample_size and sample_size < len(articles):
        np.random.seed(42)
        indices = np.random.choice(len(articles), sample_size, replace=False)
        articles = [articles[i] for i in indices]
        print(f"   Sampled {len(articles)} articles")

    # Print distribution
    lang_dist = Counter(a["language"] for a in articles)
    orient_dist = Counter(a["orientation_bucket"] for a in articles)
    print(f"   Languages:    {dict(lang_dist)}")
    print(f"   Orientations: {dict(orient_dist)}")

    return articles


def generate_embeddings(articles: list, use_gpu: bool = True):
    """Generate embeddings for all articles using Tamil-ai/tamil-embed-base."""
    from sentence_transformers import SentenceTransformer
    import torch

    device = "cuda" if (use_gpu and torch.cuda.is_available()) else "cpu"
    if use_gpu and not torch.cuda.is_available():
        print(" GPU requested but not available. Falling back to CPU.")

    print(f"\nLoading model: {MODEL_NAME} on {device.upper()}")
    load_start = time.time()
    model = SentenceTransformer(MODEL_NAME, device=device)
    load_time = time.time() - load_start
    print(f"   Model loaded in {load_time:.1f}s")

    # Prepare texts
    texts = []
    for art in articles:
        combined = f"{art['title']}. {art['clean_text']}"
        if len(combined) > 3000:
            combined = combined[:3000]
        texts.append(combined)

    # Encode
    print(f"   Encoding {len(texts)} articles...")
    encode_start = time.time()

    all_embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        batch_embeddings = model.encode(
            batch,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=32
        )
        all_embeddings.append(batch_embeddings)
        print(f"   Batch {i // BATCH_SIZE + 1}/{(len(texts) + BATCH_SIZE - 1) // BATCH_SIZE}: "
              f"{len(batch)} articles embedded")

    embeddings = np.vstack(all_embeddings)
    encode_time = time.time() - encode_start
    speed = len(texts) / encode_time

    print(f"Generated {len(embeddings)} embeddings in {encode_time:.2f}s "
          f"({speed:.1f} articles/sec)")

    del model
    return embeddings, encode_time, speed


def knn_classify(embeddings: np.ndarray, labels: list, k: int = 5, n_folds: int = 5):
    """
    K-fold cross-validated KNN classification using embedding cosine similarity.
    Returns (all_true_labels, all_predicted_labels) across all folds.
    """
    n = len(labels)
    indices = np.arange(n)
    np.random.seed(42)
    np.random.shuffle(indices)

    fold_size = n // n_folds
    all_true = []
    all_pred = []

    for fold in range(n_folds):
        # Split
        test_start = fold * fold_size
        test_end = test_start + fold_size if fold < n_folds - 1 else n
        test_idx = indices[test_start:test_end]
        train_idx = np.concatenate([indices[:test_start], indices[test_end:]])

        train_emb = embeddings[train_idx]
        test_emb = embeddings[test_idx]
        train_labels = [labels[i] for i in train_idx]

        # Cosine similarity (embeddings are L2-normalized → dot product = cosine sim)
        sim_matrix = np.dot(test_emb, train_emb.T)

        for i in range(len(test_idx)):
            top_k_indices = np.argsort(sim_matrix[i])[::-1][:k]
            top_k_labels = [train_labels[j] for j in top_k_indices]
            # Majority vote
            label_counts = Counter(top_k_labels)
            predicted = label_counts.most_common(1)[0][0]
            all_pred.append(predicted)
            all_true.append(labels[test_idx[i]])

    return all_true, all_pred


def compute_classification_metrics(y_true: list, y_pred: list, label_name: str):
    """Compute comprehensive classification metrics."""
    classes = sorted(set(y_true) | set(y_pred))
    n = len(y_true)

    # Overall accuracy
    accuracy = sum(1 for t, p in zip(y_true, y_pred) if t == p) / n

    # Per-class metrics
    per_class = {}
    for cls in classes:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == cls and p == cls)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != cls and p == cls)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == cls and p != cls)
        tn = sum(1 for t, p in zip(y_true, y_pred) if t != cls and p != cls)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        support = sum(1 for t in y_true if t == cls)

        per_class[cls] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        }

    # Macro averages (unweighted mean across classes)
    macro_precision = np.mean([m["precision"] for m in per_class.values()])
    macro_recall = np.mean([m["recall"] for m in per_class.values()])
    macro_f1 = np.mean([m["f1"] for m in per_class.values()])

    # Weighted averages (weighted by class support)
    total_support = sum(m["support"] for m in per_class.values())
    weighted_precision = sum(m["precision"] * m["support"] for m in per_class.values()) / total_support
    weighted_recall = sum(m["recall"] * m["support"] for m in per_class.values()) / total_support
    weighted_f1 = sum(m["f1"] * m["support"] for m in per_class.values()) / total_support

    # Confusion matrix
    confusion = {}
    for true_cls in classes:
        confusion[true_cls] = {}
        for pred_cls in classes:
            confusion[true_cls][pred_cls] = sum(
                1 for t, p in zip(y_true, y_pred) if t == true_cls and p == pred_cls
            )

    return {
        "label_name": label_name,
        "accuracy": accuracy,
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "macro_f1": macro_f1,
        "weighted_precision": weighted_precision,
        "weighted_recall": weighted_recall,
        "weighted_f1": weighted_f1,
        "per_class": per_class,
        "confusion_matrix": confusion,
        "classes": classes,
    }


def compute_cross_lingual_metrics(embeddings: np.ndarray, articles: list):
    """Compute cross-lingual retrieval and similarity metrics."""
    ta_indices = [i for i, a in enumerate(articles) if a["language"] == "ta"]
    en_indices = [i for i, a in enumerate(articles) if a["language"] == "en"]

    ta_emb = embeddings[ta_indices]
    en_emb = embeddings[en_indices]

    # Cross-lingual similarity matrix
    cross_sim = np.dot(ta_emb, en_emb.T)

    # Intra-language similarity
    ta_intra = np.dot(ta_emb, ta_emb.T)
    en_intra = np.dot(en_emb, en_emb.T)

    ta_upper = ta_intra[np.triu_indices_from(ta_intra, k=1)]
    en_upper = en_intra[np.triu_indices_from(en_intra, k=1)]

    metrics = {
        "cross_lingual_mean_sim": float(np.mean(cross_sim)),
        "cross_lingual_median_sim": float(np.median(cross_sim)),
        "cross_lingual_std_sim": float(np.std(cross_sim)),
        "cross_lingual_max_sim": float(np.max(cross_sim)),
        "cross_lingual_min_sim": float(np.min(cross_sim)),
        "ta_ta_mean_sim": float(np.mean(ta_upper)),
        "en_en_mean_sim": float(np.mean(en_upper)),
        "ta_en_ratio": float(np.mean(cross_sim) / np.mean(np.concatenate([ta_upper, en_upper]))),
        "cross_pairs_above_0.7": int(np.sum(cross_sim > 0.7)),
        "cross_pairs_above_0.8": int(np.sum(cross_sim > 0.8)),
        "cross_pairs_above_0.9": int(np.sum(cross_sim > 0.9)),
    }

    return metrics


def format_report(
    lang_metrics: dict,
    orient_metrics: dict,
    cross_metrics: dict,
    encode_time: float,
    speed: float,
    total_articles: int,
):
    """Format the full metrics report as a string."""
    lines = []
    sep = "=" * 72

    lines.append(sep)
    lines.append("   VERITAS LENS — EMBEDDING METRICS REPORT")
    lines.append(f"   Model: {MODEL_NAME}")
    lines.append(f"   Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
    lines.append(sep)

    # ── Encoding Performance ──
    lines.append("")
    lines.append("── ENCODING PERFORMANCE ──")
    lines.append(f"  Total articles:   {total_articles}")
    lines.append(f"  Embedding dim:    {EMBEDDING_DIM}")
    lines.append(f"  Encoding time:    {encode_time:.2f}s")
    lines.append(f"  Speed:            {speed:.1f} articles/sec")

    # ── Classification Report: Language ──
    lines.append("")
    lines.append(sep)
    lines.append("── TASK 1: LANGUAGE CLASSIFICATION (KNN, k=5, 5-fold CV) ──")
    lines.append(f"  Classes: {lang_metrics['classes']}")
    lines.append("")
    lines.append(f"  {'Metric':<30} {'Value':>10}")
    lines.append(f"  {'-'*30} {'-'*10}")
    lines.append(f"  {'Accuracy':<30} {lang_metrics['accuracy']:>10.4f}")
    lines.append(f"  {'Macro Precision':<30} {lang_metrics['macro_precision']:>10.4f}")
    lines.append(f"  {'Macro Recall':<30} {lang_metrics['macro_recall']:>10.4f}")
    lines.append(f"  {'Macro F1 Score':<30} {lang_metrics['macro_f1']:>10.4f}")
    lines.append(f"  {'Weighted Precision':<30} {lang_metrics['weighted_precision']:>10.4f}")
    lines.append(f"  {'Weighted Recall':<30} {lang_metrics['weighted_recall']:>10.4f}")
    lines.append(f"  {'Weighted F1 Score':<30} {lang_metrics['weighted_f1']:>10.4f}")

    lines.append("")
    lines.append("  Per-Class Breakdown:")
    lines.append(f"  {'Class':<10} {'Precision':>10} {'Recall':>10} {'F1':>10} {'Support':>10}")
    lines.append(f"  {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
    for cls in lang_metrics["classes"]:
        m = lang_metrics["per_class"][cls]
        lines.append(f"  {cls:<10} {m['precision']:>10.4f} {m['recall']:>10.4f} "
                      f"{m['f1']:>10.4f} {m['support']:>10}")

    lines.append("")
    lines.append("  Confusion Matrix:")
    header = f"  {'True/Pred':<10}" + "".join(f" {cls:>8}" for cls in lang_metrics["classes"])
    lines.append(header)
    for true_cls in lang_metrics["classes"]:
        row = f"  {true_cls:<10}"
        for pred_cls in lang_metrics["classes"]:
            row += f" {lang_metrics['confusion_matrix'][true_cls][pred_cls]:>8}"
        lines.append(row)

    # ── Classification Report: Orientation Bucket ──
    lines.append("")
    lines.append(sep)
    lines.append("── TASK 2: ORIENTATION BUCKET CLASSIFICATION (KNN, k=5, 5-fold CV) ──")
    lines.append(f"  Classes: {orient_metrics['classes']}")
    lines.append("")
    lines.append(f"  {'Metric':<30} {'Value':>10}")
    lines.append(f"  {'-'*30} {'-'*10}")
    lines.append(f"  {'Accuracy':<30} {orient_metrics['accuracy']:>10.4f}")
    lines.append(f"  {'Macro Precision':<30} {orient_metrics['macro_precision']:>10.4f}")
    lines.append(f"  {'Macro Recall':<30} {orient_metrics['macro_recall']:>10.4f}")
    lines.append(f"  {'Macro F1 Score':<30} {orient_metrics['macro_f1']:>10.4f}")
    lines.append(f"  {'Weighted Precision':<30} {orient_metrics['weighted_precision']:>10.4f}")
    lines.append(f"  {'Weighted Recall':<30} {orient_metrics['weighted_recall']:>10.4f}")
    lines.append(f"  {'Weighted F1 Score':<30} {orient_metrics['weighted_f1']:>10.4f}")

    lines.append("")
    lines.append("  Per-Class Breakdown:")
    lines.append(f"  {'Class':<10} {'Precision':>10} {'Recall':>10} {'F1':>10} {'Support':>10}")
    lines.append(f"  {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
    for cls in orient_metrics["classes"]:
        m = orient_metrics["per_class"][cls]
        lines.append(f"  {cls:<10} {m['precision']:>10.4f} {m['recall']:>10.4f} "
                      f"{m['f1']:>10.4f} {m['support']:>10}")

    lines.append("")
    lines.append("  Confusion Matrix:")
    header = f"  {'True/Pred':<10}" + "".join(f" {cls:>8}" for cls in orient_metrics["classes"])
    lines.append(header)
    for true_cls in orient_metrics["classes"]:
        row = f"  {true_cls:<10}"
        for pred_cls in orient_metrics["classes"]:
            row += f" {orient_metrics['confusion_matrix'][true_cls][pred_cls]:>8}"
        lines.append(row)

    # ── Cross-Lingual Embedding Quality ──
    lines.append("")
    lines.append(sep)
    lines.append("── CROSS-LINGUAL EMBEDDING QUALITY ──")
    lines.append(f"  {'Metric':<40} {'Value':>12}")
    lines.append(f"  {'-'*40} {'-'*12}")
    lines.append(f"  {'Cross-lingual Mean Similarity':<40} {cross_metrics['cross_lingual_mean_sim']:>12.4f}")
    lines.append(f"  {'Cross-lingual Median Similarity':<40} {cross_metrics['cross_lingual_median_sim']:>12.4f}")
    lines.append(f"  {'Cross-lingual Std Dev':<40} {cross_metrics['cross_lingual_std_sim']:>12.4f}")
    lines.append(f"  {'Cross-lingual Max Similarity':<40} {cross_metrics['cross_lingual_max_sim']:>12.4f}")
    lines.append(f"  {'Cross-lingual Min Similarity':<40} {cross_metrics['cross_lingual_min_sim']:>12.4f}")
    lines.append(f"  {'Tamil-Tamil Mean Similarity':<40} {cross_metrics['ta_ta_mean_sim']:>12.4f}")
    lines.append(f"  {'English-English Mean Similarity':<40} {cross_metrics['en_en_mean_sim']:>12.4f}")
    lines.append(f"  {'Cross/Intra Similarity Ratio':<40} {cross_metrics['ta_en_ratio']:>12.4f}")
    lines.append(f"  {'Cross-lingual Pairs > 0.7':<40} {cross_metrics['cross_pairs_above_0.7']:>12}")
    lines.append(f"  {'Cross-lingual Pairs > 0.8':<40} {cross_metrics['cross_pairs_above_0.8']:>12}")
    lines.append(f"  {'Cross-lingual Pairs > 0.9':<40} {cross_metrics['cross_pairs_above_0.9']:>12}")

    lines.append("")
    lines.append(sep)
    lines.append("  END OF REPORT")
    lines.append(sep)

    return "\n".join(lines)


def save_classification_csv(lang_metrics: dict, orient_metrics: dict, output_path: str):
    """Save classification metrics to a CSV for downstream analysis."""
    rows = []

    for task_name, metrics in [("language", lang_metrics), ("orientation", orient_metrics)]:
        # Overall row
        rows.append({
            "task": task_name,
            "class": "OVERALL",
            "accuracy": f"{metrics['accuracy']:.4f}",
            "macro_precision": f"{metrics['macro_precision']:.4f}",
            "macro_recall": f"{metrics['macro_recall']:.4f}",
            "macro_f1": f"{metrics['macro_f1']:.4f}",
            "weighted_precision": f"{metrics['weighted_precision']:.4f}",
            "weighted_recall": f"{metrics['weighted_recall']:.4f}",
            "weighted_f1": f"{metrics['weighted_f1']:.4f}",
            "precision": "",
            "recall": "",
            "f1": "",
            "support": "",
        })
        # Per-class rows
        for cls in metrics["classes"]:
            m = metrics["per_class"][cls]
            rows.append({
                "task": task_name,
                "class": cls,
                "accuracy": "",
                "macro_precision": "",
                "macro_recall": "",
                "macro_f1": "",
                "weighted_precision": "",
                "weighted_recall": "",
                "weighted_f1": "",
                "precision": f"{m['precision']:.4f}",
                "recall": f"{m['recall']:.4f}",
                "f1": f"{m['f1']:.4f}",
                "support": str(m["support"]),
            })

    fieldnames = [
        "task", "class", "accuracy",
        "macro_precision", "macro_recall", "macro_f1",
        "weighted_precision", "weighted_recall", "weighted_f1",
        "precision", "recall", "f1", "support",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nClassification metrics saved to: {output_path}")


def run_report(csv_path: str, sample_size: int = None, use_gpu: bool = True, output_dir: str = None):
    """Run the full embedding metrics report."""
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(output_dir, exist_ok=True)

    # 1. Load data
    articles = load_articles(csv_path, sample_size=sample_size)

    # 2. Generate embeddings
    embeddings, encode_time, speed = generate_embeddings(articles, use_gpu=use_gpu)

    # 3. Language classification (Tamil vs English)
    print("\nRunning Language Classification (KNN, k=5, 5-fold CV)...")
    lang_labels = [a["language"] for a in articles]
    lang_true, lang_pred = knn_classify(embeddings, lang_labels, k=5, n_folds=5)
    lang_metrics = compute_classification_metrics(lang_true, lang_pred, "Language")

    # 4. Orientation classification (IND / CON / DRV / MIXED)
    print("Running Orientation Bucket Classification (KNN, k=5, 5-fold CV)...")
    orient_labels = [a["orientation_bucket"] for a in articles]
    orient_true, orient_pred = knn_classify(embeddings, orient_labels, k=5, n_folds=5)
    orient_metrics = compute_classification_metrics(orient_true, orient_pred, "Orientation")

    # 5. Cross-lingual embedding quality metrics
    print("Computing Cross-Lingual Embedding Quality Metrics...")
    cross_metrics = compute_cross_lingual_metrics(embeddings, articles)

    # 6. Format and save report
    report_text = format_report(
        lang_metrics, orient_metrics, cross_metrics,
        encode_time, speed, len(articles)
    )

    # Print report
    print("\n" + report_text)

    # Save report to file
    report_path = os.path.join(output_dir, "metrics_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\nFull report saved to: {report_path}")

    # Save metrics CSV
    csv_output = os.path.join(output_dir, "classification_metrics.csv")
    save_classification_csv(lang_metrics, orient_metrics, csv_output)

    print("\nEMBEDDING METRICS REPORT COMPLETE")


# ── CLI Entry Point ──
def main():
    parser = argparse.ArgumentParser(
        description="Generate embedding evaluation metrics report using Tamil-ai/tamil-embed-base"
    )
    parser.add_argument(
        "--input", type=str, default=None,
        help="Path to input CSV (default: data/raw_processed.csv)"
    )
    parser.add_argument(
        "--sample", type=int, default=None,
        help="Sample N articles to speed up evaluation"
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Directory to save results (default: embeddings/)"
    )
    parser.add_argument(
        "--cpu", action="store_true",
        help="Force CPU mode even if GPU is available"
    )
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(base_dir)

    input_csv = args.input or os.path.join(project_dir, "data", "raw_processed.csv")
    output_dir = args.output_dir or base_dir

    run_report(input_csv, sample_size=args.sample, use_gpu=not args.cpu, output_dir=output_dir)


if __name__ == "__main__":
    main()
