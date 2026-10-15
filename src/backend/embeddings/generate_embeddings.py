"""
Veritas Lens — Standalone Embedding Generator
==============================================

Uses Tamil-ai/tamil-embed-base to generate 768-dimensional embeddings
for both Tamil and English articles. This model maps both languages
into the same vector space, enabling cross-lingual similarity search.

Usage:
    python -m embeddings.generate_embeddings              # From DB (eligible articles)
    python -m embeddings.generate_embeddings --from-csv   # From CSV file
"""

import os
import sys
import csv
import time
import argparse
import numpy as np

from sentence_transformers import SentenceTransformer

# Configuration
MODEL_NAME = "Tamil-ai/tamil-embed-base"
EMBEDDING_DIM = 768
BATCH_SIZE = 50  # Process articles in batches to manage memory

# Model Loader (lazy singleton)
_model = None

def get_model():
    """Load the Tamil-ai/tamil-embed-base model (cached after first call)."""
    global _model
    if _model is None:
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("GPU is required but not available. CPU execution is disabled.")
        print(f"[Embeddings] Loading model: {MODEL_NAME} on GPU")
        _model = SentenceTransformer(MODEL_NAME, device="cuda")
        print(f"[Embeddings] Model loaded. Output dimension: {EMBEDDING_DIM}")
    return _model


def generate_embedding(text: str) -> list:
    """Generate a single 768-dim embedding for a given text."""
    model = get_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def generate_embeddings_batch(texts: list) -> np.ndarray:
    """
    Generate embeddings for a batch of texts.
    
    Args:
        texts: List of strings to embed.
        
    Returns:
        numpy array of shape (len(texts), 768) with L2-normalized embeddings.
    """
    model = get_model()
    embeddings = model.encode(
        texts, 
        normalize_embeddings=True, 
        show_progress_bar=True,
        batch_size=32
    )
    return embeddings


# Database Mode: Process eligible articles from PostgreSQL
def embed_from_db(batch_limit: int = 50):
    """
    Fetch articles with processing_status='eligible' from PostgreSQL,
    generate embeddings using Tamil-ai/tamil-embed-base, and save them back.
    """
    # Import here to avoid circular imports when running standalone
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ingestion'))
    from models.database import SessionLocal, Article
    
    db = SessionLocal()
    try:
        articles = db.query(Article).filter(
            Article.processing_status == "eligible"
        ).limit(batch_limit).all()
        
        if not articles:
            print("[Embeddings] No eligible articles found.")
            return {"status": "no_eligible_articles", "count": 0}
        
        print(f"[Embeddings] Processing {len(articles)} eligible articles...")
        
        # Prepare texts: combine title + body for richer semantic representation
        texts = []
        for article in articles:
            combined = f"{article.title}. {article.clean_text}"
            # Truncate very long texts (tamil-embed-base max is ~512 tokens)
            if len(combined) > 3000:
                combined = combined[:3000]
            texts.append(combined)
        
        # Generate embeddings
        start_time = time.time()
        embeddings = generate_embeddings_batch(texts)
        elapsed = time.time() - start_time
        
        print(f"[Embeddings] Generated {len(embeddings)} embeddings in {elapsed:.2f}s "
              f"({len(embeddings)/elapsed:.1f} articles/sec)")
        
        # Save to database
        for i, article in enumerate(articles):
            article.embedding = embeddings[i].tolist()
            article.processing_status = "embedded"
        
        db.commit()
        print(f"[Embeddings]  Saved {len(articles)} embeddings to PostgreSQL.")
        return {"status": "success", "count": len(articles), "time_seconds": elapsed}
        
    except Exception as e:
        db.rollback()
        print(f"[Embeddings]  Error: {e}")
        raise
    finally:
        db.close()


# CSV Mode: Generate embeddings from the canonical processed dataset.
def embed_from_csv(
    input_csv: str = None, 
    output_csv: str = None
):
    """
    Read articles from CSV, generate embeddings, and save to a new CSV
    with an 'embedding' column.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(base_dir)
    
    if input_csv is None:
        input_csv = os.path.join(project_dir, "data", "trafiltura_preprocessed.csv")
    if output_csv is None:
        output_csv = os.path.join(base_dir, "embedded_articles.csv")
    
    if not os.path.exists(input_csv):
        print(f"[Embeddings]  Input file not found: {input_csv}")
        return
    
    # Load articles
    print(f"[Embeddings] Loading articles from {input_csv}...")
    articles = []
    with open(input_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("clean_text") and row.get("title"):
                articles.append(row)
    
    print(f"[Embeddings] Loaded {len(articles)} articles with text content.")
    
    if not articles:
        print("[Embeddings] No articles to process.")
        return
    
    # Prepare texts
    texts = []
    for art in articles:
        combined = f"{art['title']}. {art['clean_text']}"
        if len(combined) > 3000:
            combined = combined[:3000]
        texts.append(combined)
    
    # Generate embeddings in batches
    print(f"[Embeddings] Generating {EMBEDDING_DIM}-dim embeddings with {MODEL_NAME}...")
    start_time = time.time()
    
    all_embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        batch_embeddings = generate_embeddings_batch(batch)
        all_embeddings.append(batch_embeddings)
        print(f"  Batch {i//BATCH_SIZE + 1}: {len(batch)} articles embedded")
    
    embeddings = np.vstack(all_embeddings)
    elapsed = time.time() - start_time
    
    print(f"[Embeddings]  Generated {len(embeddings)} embeddings in {elapsed:.2f}s "
          f"({len(embeddings)/elapsed:.1f} articles/sec)")
    
    # Save to output CSV
    print(f"[Embeddings] Saving to {output_csv}...")
    
    # Output fields: original metadata + embedding as comma-separated floats
    output_fields = [
        "content_hash", "guid", "outlet_slug", "title", "published_at",
        "language", "article_length", "data_fetch_via", "canonical_url",
        "extraction_method", "extraction_quality", "processing_status",
        "embedding"
    ]
    
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_fields)
        writer.writeheader()
        
        for i, art in enumerate(articles):
            emb_str = ",".join(f"{v:.6f}" for v in embeddings[i])
            writer.writerow({
                "content_hash": art.get("content_hash", ""),
                "guid": art.get("guid", ""),
                "outlet_slug": art.get("outlet_slug", ""),
                "title": art.get("title", ""),
                "published_at": art.get("published_at", ""),
                "language": art.get("language", ""),
                "article_length": art.get("article_length", ""),
                "data_fetch_via": art.get("data_fetch_via", ""),
                "canonical_url": art.get("canonical_url", ""),
                "extraction_method": art.get("extraction_method", ""),
                "extraction_quality": art.get("extraction_quality", ""),
                "processing_status": "embedded",
                "embedding": emb_str,
            })
    
    print(f"[Embeddings]  Saved {len(articles)} embedded articles to {output_csv}")
    
    # Print summary statistics
    ta_count = sum(1 for a in articles if a.get("language") == "ta")
    en_count = sum(1 for a in articles if a.get("language") == "en")
    print("\nEMBEDDING SUMMARY")
    print(f"  Model:           {MODEL_NAME}")
    print(f"  Dimensions:      {EMBEDDING_DIM}")
    print(f"  Total articles:  {len(articles)}")
    print(f"  Tamil articles:  {ta_count}")
    print(f"  English articles:{en_count}")
    print(f"  Time:            {elapsed:.2f}s")
    print(f"  Speed:           {len(articles)/elapsed:.1f} articles/sec")
    print(f"  Output:          {output_csv}")


# CLI Entry Point
def main():
    parser = argparse.ArgumentParser(
        description="Generate embeddings using Tamil-ai/tamil-embed-base"
    )
    parser.add_argument(
        "--from-csv", action="store_true",
        help="Generate embeddings from data/trafiltura_preprocessed.csv instead of DB"
    )
    parser.add_argument(
        "--input", type=str, default=None,
        help="Path to input CSV file (used with --from-csv)"
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Path to output CSV file (used with --from-csv)"
    )
    parser.add_argument(
        "--batch-limit", type=int, default=50,
        help="Max articles per batch for DB mode (default: 50)"
    )
    args = parser.parse_args()
    
    if args.from_csv:
        embed_from_csv(input_csv=args.input, output_csv=args.output)
    else:
        embed_from_db(batch_limit=args.batch_limit)


if __name__ == "__main__":
    main()
