"""
Veritas Lens — Embedding Model Benchmark
==========================================

Compares three multilingual embedding models on the actual scraped
news dataset to determine which best aligns Tamil and English articles
in a shared vector space.

Models benchmarked:
    1. Tamil-ai/tamil-embed-base     (768d)  — Tamil-focused bilingual
    2. intfloat/multilingual-e5-base (768d)  — General multilingual
    3. BAAI/bge-m3                   (1024d) — Multi-functional multilingual

Metrics:
    - Cross-lingual cosine similarity distributions
    - Intra-language vs cross-language similarity
    - Encoding speed (articles/sec)
    - Mean cosine similarity for same-title heuristic pairs

Usage:
    python -m embeddings.benchmark_embeddings
    python -m embeddings.benchmark_embeddings --sample 200
"""

import os
import sys
import csv
import time
import argparse
import numpy as np

from collections import defaultdict

# Model Registry
MODELS = {
    "tamil-embed-base": {
        "hf_name": "Tamil-ai/tamil-embed-base",
        "dim": 768,
        "prefix": "",          # No prefix required
        "description": "Tamil-focused bilingual (Tamil + English)"
    }
}


# Data Loading
def load_articles(csv_path: str, sample_size: int = None):
    """Load articles from raw_processed.csv."""
    print(f"\n Loading articles from {csv_path}...")
    
    if not os.path.exists(csv_path):
        print(f" File not found: {csv_path}")
        sys.exit(1)
    
    articles = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("clean_text") and row.get("title") and row.get("language") in ("ta", "en"):
                articles.append(row)
    
    print(f"   Loaded {len(articles)} articles (ta + en only)")
    
    if sample_size and sample_size < len(articles):
        # Stratified sampling: proportional ta/en
        ta_articles = [a for a in articles if a["language"] == "ta"]
        en_articles = [a for a in articles if a["language"] == "en"]
        
        ta_ratio = len(ta_articles) / len(articles)
        ta_sample = int(sample_size * ta_ratio)
        en_sample = sample_size - ta_sample
        
        np.random.seed(42)
        ta_idx = np.random.choice(len(ta_articles), min(ta_sample, len(ta_articles)), replace=False)
        en_idx = np.random.choice(len(en_articles), min(en_sample, len(en_articles)), replace=False)
        
        articles = [ta_articles[i] for i in ta_idx] + [en_articles[i] for i in en_idx]
        print(f"   Sampled {len(articles)} articles (stratified)")
    
    ta_count = sum(1 for a in articles if a["language"] == "ta")
    en_count = sum(1 for a in articles if a["language"] == "en")
    print(f"   Tamil: {ta_count} | English: {en_count}")
    
    return articles


# Embedding Generation
def generate_embeddings_for_model(model_key: str, articles: list):
    """
    Generate embeddings for all articles using a specific model.
    Returns (embeddings_array, time_elapsed).
    """
    from sentence_transformers import SentenceTransformer
    import torch
    
    if not torch.cuda.is_available():
        raise RuntimeError("GPU is required but not available. CPU execution is disabled.")
    
    model_info = MODELS[model_key]
    hf_name = model_info["hf_name"]
    prefix = model_info["prefix"]
    
    print(f"   Model: {hf_name}")
    print(f"  Dimensions: {model_info['dim']} | Prefix: '{prefix}' ")
        
    print(f"  Loading model...")
    load_start = time.time()
    model = SentenceTransformer(hf_name, device="cuda")
    load_time = time.time() - load_start
    print(f"  Model loaded in {load_time:.1f}s")
    
    # Prepare texts
    texts = []
    for art in articles:
        combined = f"{art['title']}. {art['clean_text']}"
        if len(combined) > 3000:
            combined = combined[:3000]
        texts.append(f"{prefix}{combined}")
    
    # Encode
    print(f"  Encoding {len(texts)} articles...")
    encode_start = time.time()
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=True,
        batch_size=32
    )
    encode_time = time.time() - encode_start
    
    speed = len(texts) / encode_time
    print(f"   Done in {encode_time:.2f}s ({speed:.1f} articles/sec)")
    
    # Free GPU/CPU memory
    del model
    
    return embeddings, encode_time


# Metrics Computation
def compute_cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors (assumes normalized)."""
    return float(np.dot(a, b))


def compute_metrics(embeddings: np.ndarray, articles: list, model_key: str):
    """
    Compute cross-lingual and intra-lingual similarity metrics.
    
    Returns a dict with all computed metrics.
    """
    model_info = MODELS[model_key]
    
    # Split by language
    ta_indices = [i for i, a in enumerate(articles) if a["language"] == "ta"]
    en_indices = [i for i, a in enumerate(articles) if a["language"] == "en"]
    
    ta_embeddings = embeddings[ta_indices]
    en_embeddings = embeddings[en_indices]
    
    metrics = {
        "model": model_key,
        "hf_name": model_info["hf_name"],
        "dim": model_info["dim"],
        "total_articles": len(articles),
        "tamil_count": len(ta_indices),
        "english_count": len(en_indices),
    }
    
    # ── 1. Cross-lingual similarity matrix ──
    # Compute cosine similarity between all Tamil and all English articles
    # (embeddings are already L2-normalized, so dot product = cosine sim)
    print(f"  Computing cross-lingual similarity matrix ({len(ta_indices)}×{len(en_indices)})...")
    cross_sim_matrix = np.dot(ta_embeddings, en_embeddings.T)
    
    metrics["cross_lingual_mean_sim"] = float(np.mean(cross_sim_matrix))
    metrics["cross_lingual_median_sim"] = float(np.median(cross_sim_matrix))
    metrics["cross_lingual_std_sim"] = float(np.std(cross_sim_matrix))
    metrics["cross_lingual_max_sim"] = float(np.max(cross_sim_matrix))
    metrics["cross_lingual_min_sim"] = float(np.min(cross_sim_matrix))
    
    # ── 2. Intra-language similarity ──
    # Tamil-Tamil similarity
    if len(ta_embeddings) > 1:
        ta_sim_matrix = np.dot(ta_embeddings, ta_embeddings.T)
        # Extract upper triangle (excluding diagonal)
        ta_upper = ta_sim_matrix[np.triu_indices_from(ta_sim_matrix, k=1)]
        metrics["ta_ta_mean_sim"] = float(np.mean(ta_upper))
        metrics["ta_ta_median_sim"] = float(np.median(ta_upper))
        metrics["ta_ta_std_sim"] = float(np.std(ta_upper))
    
    # English-English similarity
    if len(en_embeddings) > 1:
        en_sim_matrix = np.dot(en_embeddings, en_embeddings.T)
        en_upper = en_sim_matrix[np.triu_indices_from(en_sim_matrix, k=1)]
        metrics["en_en_mean_sim"] = float(np.mean(en_upper))
        metrics["en_en_median_sim"] = float(np.median(en_upper))
        metrics["en_en_std_sim"] = float(np.std(en_upper))
    
    # ── 3. Cross-lingual nearest neighbor analysis ──
    # For each Tamil article, find the most similar English article
    print(f"  Computing nearest-neighbor retrieval metrics...")
    
    ta_to_en_max_sims = np.max(cross_sim_matrix, axis=1)  # Best English match for each Tamil
    en_to_ta_max_sims = np.max(cross_sim_matrix, axis=0)  # Best Tamil match for each English
    
    metrics["ta→en_mean_best_sim"] = float(np.mean(ta_to_en_max_sims))
    metrics["ta→en_median_best_sim"] = float(np.median(ta_to_en_max_sims))
    metrics["en→ta_mean_best_sim"] = float(np.mean(en_to_ta_max_sims))
    metrics["en→ta_median_best_sim"] = float(np.median(en_to_ta_max_sims))
    
    # ── 4. High-similarity pair discovery ──
    # Count pairs with similarity > threshold (likely same-event candidates)
    for threshold in [0.7, 0.8, 0.9]:
        high_sim_count = int(np.sum(cross_sim_matrix > threshold))
        metrics[f"cross_pairs_above_{threshold}"] = high_sim_count
    
    # ── 5. Top-10 most similar cross-lingual pairs ──
    top_pairs = []
    flat_indices = np.argsort(cross_sim_matrix.ravel())[::-1][:10]
    for flat_idx in flat_indices:
        ta_i = flat_idx // cross_sim_matrix.shape[1]
        en_j = flat_idx % cross_sim_matrix.shape[1]
        sim = cross_sim_matrix[ta_i, en_j]
        ta_article = articles[ta_indices[ta_i]]
        en_article = articles[en_indices[en_j]]
        top_pairs.append({
            "similarity": f"{sim:.4f}",
            "tamil_title": ta_article["title"][:80],
            "english_title": en_article["title"][:80],
            "tamil_outlet": ta_article.get("outlet_slug", ""),
            "english_outlet": en_article.get("outlet_slug", ""),
        })
    metrics["top_cross_lingual_pairs"] = top_pairs
    
    return metrics


# Results Display
def print_results(all_results: list):
    """Pretty-print the benchmark comparison table."""
    
    print(f"   EMBEDDING BENCHMARK RESULTS")
        
    # Summary table
    header = f"{'Metric':<40} "
    for r in all_results:
        header += f"{'  ' + r['model']:<22}"
    print(header)
        
    rows = [
        ("Dimensions", "dim"),
        ("Encoding Time (s)", "encode_time"),
        ("Speed (articles/sec)", "speed"),
        ("", None),  # blank separator
        ("Cross-lingual Mean Sim", "cross_lingual_mean_sim"),
        ("Cross-lingual Median Sim", "cross_lingual_median_sim"),
        ("Cross-lingual Std Dev", "cross_lingual_std_sim"),
        ("Cross-lingual Max Sim", "cross_lingual_max_sim"),
        ("", None),
        ("Tamil-Tamil Mean Sim", "ta_ta_mean_sim"),
        ("English-English Mean Sim", "en_en_mean_sim"),
        ("", None),
        ("Tamil→English Best Match (mean)", "ta→en_mean_best_sim"),
        ("English→Tamil Best Match (mean)", "en→ta_mean_best_sim"),
        ("", None),
        ("Cross pairs > 0.7", "cross_pairs_above_0.7"),
        ("Cross pairs > 0.8", "cross_pairs_above_0.8"),
        ("Cross pairs > 0.9", "cross_pairs_above_0.9"),
    ]
    
    for label, key in rows:
        if key is None:
            print()
            continue
        row_str = f"  {label:<38} "
        for r in all_results:
            val = r.get(key, "N/A")
            if isinstance(val, float):
                row_str += f"  {val:<20.4f}"
            else:
                row_str += f"  {str(val):<20}"
        print(row_str)
    
    # Print top cross-lingual pairs for each model
    for r in all_results:
        print(f"   Top 10 Cross-Lingual Pairs — {r['model']}")
                pairs = r.get("top_cross_lingual_pairs", [])
        for i, p in enumerate(pairs, 1):
            print(f"  {i:>2}. sim={p['similarity']}  "
                  f"TA[{p['tamil_outlet']}]: {p['tamil_title']}")
            print(f"      {'':>14}  "
                  f"EN[{p['english_outlet']}]: {p['english_title']}")


def save_results_csv(all_results: list, output_path: str):
    """Save the summary metrics as a CSV file for analysis."""
    
    # Flatten results (exclude top_cross_lingual_pairs for CSV)
    flat_keys = set()
    for r in all_results:
        for k, v in r.items():
            if k != "top_cross_lingual_pairs":
                flat_keys.add(k)
    
    flat_keys = sorted(flat_keys)
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=flat_keys)
        writer.writeheader()
        for r in all_results:
            row = {k: r.get(k, "") for k in flat_keys if k != "top_cross_lingual_pairs"}
            writer.writerow(row)
    
    print(f"\n Benchmark results saved to: {output_path}")


def save_top_pairs_csv(all_results: list, output_dir: str):
    """Save the top cross-lingual pairs for each model."""
    for r in all_results:
        model_name = r["model"]
        pairs = r.get("top_cross_lingual_pairs", [])
        if not pairs:
            continue
        
        path = os.path.join(output_dir, f"top_pairs_{model_name}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=pairs[0].keys())
            writer.writeheader()
            writer.writerows(pairs)
        print(f"   Saved top pairs for {model_name} → {path}")


# Main Benchmark Runner
def run_benchmark(csv_path: str, sample_size: int = None, output_dir: str = None):
    """Run the full benchmark across all models."""
    
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(output_dir, exist_ok=True)
    
    # Load data
    articles = load_articles(csv_path, sample_size=sample_size)
    
    all_results = []
    
    for model_key in MODELS:
        try:
            # Generate embeddings
            embeddings, encode_time = generate_embeddings_for_model(model_key, articles)
            
            # Compute metrics
            metrics = compute_metrics(embeddings, articles, model_key)
            metrics["encode_time"] = encode_time
            metrics["speed"] = len(articles) / encode_time
            
            all_results.append(metrics)
            
            # Free memory
            del embeddings
            
        except Exception as e:
            print(f"\n Error benchmarking {model_key}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    if not all_results:
        print(" No models completed successfully.")
        return
    
    # Display results
    print_results(all_results)
    
    # Save results
    results_csv = os.path.join(output_dir, "benchmark_results.csv")
    save_results_csv(all_results, results_csv)
    save_top_pairs_csv(all_results, output_dir)
    
    print(f"   BENCHMARK COMPLETE")
    print(f"  Results saved to: {output_dir}")
    

# CLI
def main():
    parser = argparse.ArgumentParser(
        description="Benchmark embedding models for Tamil+English news"
    )
    parser.add_argument(
        "--input", type=str, default=None,
        help="Path to input CSV (default: data/raw_processed.csv)"
    )
    parser.add_argument(
        "--sample", type=int, default=None,
        help="Sample N articles (stratified) to speed up benchmarking"
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Directory to save results (default: embeddings/)"
    )
    args = parser.parse_args()
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(base_dir)
    
    input_csv = args.input or os.path.join(project_dir, "data", "raw_processed.csv")
    output_dir = args.output_dir or base_dir
    
    run_benchmark(input_csv, sample_size=args.sample, output_dir=output_dir)


if __name__ == "__main__":
    main()
