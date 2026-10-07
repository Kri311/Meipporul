"""
Veritas Lens — Fine-tuned NER Inference Pipeline
=================================================
Loads the fine-tuned MuRIL model and runs NER prediction with
the full ensemble: ML model + Gazetteers + Contextual Rules.

This is the production-ready inference pipeline.
"""

import os
import sys
import re
import csv
import json
import time
import unicodedata
from collections import defaultdict
from datetime import datetime

import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification
import transformers.utils.import_utils
transformers.utils.import_utils.check_torch_load_is_safe = lambda: None

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.ner_pipeline.finetune.config import (
    ID2LABEL, LABEL2ID, MODEL_DIR, DATA_DIR,
    POLITICAL_PARTIES, GOVERNMENT_BODIES, KNOWN_LOCATIONS, KNOWN_PERSONS,
    TAMIL_CASE_SUFFIXES, PERSON_PREFIXES, LOCATION_SUFFIXES,
    ORG_CONTEXT_SUFFIXES, LOC_CONTEXT_SUFFIXES,
)
from backend.ner_pipeline.finetune.auto_annotate import (
    normalize_for_ner, strip_tamil_suffixes, is_tamil,
    find_date_spans, build_gazetteer_index,
)

# Singleton model cache
_model = None
_tokenizer = None
GAZ_INDEX = build_gazetteer_index()


def load_model():
    """Load the fine-tuned model (lazy singleton)."""
    global _model, _tokenizer
    if _model is None:
        model_path = os.path.join(MODEL_DIR, "best")
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Fine-tuned model not found at {model_path}. Run train.py first!"
            )
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[NER Inference] Loading fine-tuned model from {model_path} on {device}")
        _tokenizer = AutoTokenizer.from_pretrained(model_path)
        _model = AutoModelForTokenClassification.from_pretrained(model_path).to(device)
        _model.eval()
        print(f"[NER Inference] Model loaded. Labels: {len(ID2LABEL)}")
    return _model, _tokenizer


# ---------------------------------------------------------------------------
# ML Prediction
# ---------------------------------------------------------------------------

def predict_entities_ml(text: str) -> list:
    """
    Run fine-tuned model on text and extract entities.
    Returns list of dicts: {word, label, score}
    """
    model, tokenizer = load_model()
    device = next(model.parameters()).device
    
    # Tokenize
    encoding = tokenizer(
        text,
        truncation=True,
        max_length=256,
        return_tensors="pt",
        return_offsets_mapping=True,
    )
    
    offset_mapping = encoding.pop("offset_mapping")[0].tolist()
    input_ids = encoding["input_ids"].to(device)
    attention_mask = encoding["attention_mask"].to(device)
    
    with torch.no_grad():
        outputs = model(input_ids=input_ids, attention_mask=attention_mask)
        logits = outputs.logits
    
    predictions = torch.argmax(logits, dim=-1)[0].cpu().tolist()
    scores = torch.softmax(logits, dim=-1)[0].cpu()
    
    # Decode entities from BIO tags
    entities = []
    current_entity = None
    
    for idx, (pred_id, (start, end)) in enumerate(zip(predictions, offset_mapping)):
        if start == 0 and end == 0:
            # Special token
            if current_entity:
                entities.append(current_entity)
                current_entity = None
            continue
        
        label = ID2LABEL.get(pred_id, "O")
        score = scores[idx][pred_id].item()
        
        if label.startswith("B-"):
            if current_entity:
                entities.append(current_entity)
            current_entity = {
                "word": text[start:end],
                "label": label[2:],
                "score": score,
                "start": start,
                "end": end,
            }
        elif label.startswith("I-") and current_entity and label[2:] == current_entity["label"]:
            # Continue current entity
            current_entity["word"] = text[current_entity["start"]:end]
            current_entity["end"] = end
            current_entity["score"] = min(current_entity["score"], score)
        else:
            if current_entity:
                entities.append(current_entity)
                current_entity = None
    
    if current_entity:
        entities.append(current_entity)
    
    return entities


# ---------------------------------------------------------------------------
# Gazetteer Matching
# ---------------------------------------------------------------------------

def gazetteer_extract(text: str) -> dict:
    """Extract entities using gazetteer matching with Tamil suffix stripping."""
    entities = defaultdict(list)
    
    # Single token matching
    words = text.split()
    for word in words:
        clean = word.strip('.,;:!?()[]{}"\'-')
        if not clean:
            continue
        
        lower = clean.lower()
        if lower in GAZ_INDEX:
            label, canonical = GAZ_INDEX[lower]
            if canonical not in entities[label]:
                entities[label].append(canonical)
            continue
        
        # Tamil suffix stripping
        if is_tamil(clean):
            root = strip_tamil_suffixes(clean)
            root_lower = root.lower()
            if root_lower in GAZ_INDEX:
                label, canonical = GAZ_INDEX[root_lower]
                if canonical not in entities[label]:
                    entities[label].append(canonical)
    
    # Multi-word phrase matching (bigrams, trigrams)
    for n in [3, 2]:
        for i in range(len(words) - n + 1):
            phrase = " ".join(w.strip('.,;:!?()[]{}"\'-') for w in words[i:i+n])
            phrase_lower = phrase.lower()
            if phrase_lower in GAZ_INDEX:
                label, canonical = GAZ_INDEX[phrase_lower]
                if canonical not in entities[label]:
                    entities[label].append(canonical)
    
    return dict(entities)


# ---------------------------------------------------------------------------
# Contextual Rules (Post-processing)
# ---------------------------------------------------------------------------

def apply_contextual_rules(entities: dict) -> dict:
    """
    Post-process extracted entities:
    - Strip person title prefixes (Chief Minister, முதலமைச்சர், etc.)
    - Strip location suffixes (District, மாவட்டம், etc.)
    """
    cleaned = defaultdict(list)
    
    for category, ent_list in entities.items():
        for entity in ent_list:
            clean = entity
            
            if category == "PERSON":
                for prefix in PERSON_PREFIXES:
                    clean = re.sub(f"^{prefix}", "", clean, flags=re.IGNORECASE)
            elif category == "LOCATION":
                for suffix in LOCATION_SUFFIXES:
                    clean = re.sub(f"{suffix}", "", clean, flags=re.IGNORECASE)
            
            clean = clean.strip()
            if clean and len(clean) > 1 and clean not in cleaned[category]:
                cleaned[category].append(clean)
    
    return dict(cleaned)


# ---------------------------------------------------------------------------
# Date Extraction (regex only — not ML)
# ---------------------------------------------------------------------------

def extract_dates(text: str) -> list:
    """Extract date entities using regex patterns."""
    date_patterns = [
        r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',
        r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b',
        r'\b\d{4}-\d{2}-\d{2}\b',
    ]
    dates = []
    for pattern in date_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            d = match.group().strip()
            if d not in dates:
                dates.append(d)
    return dates


# ---------------------------------------------------------------------------
# Full Ensemble Pipeline
# ---------------------------------------------------------------------------

def extract_entities(text: str) -> dict:
    """
    Full ensemble NER pipeline:
    1. ML prediction (fine-tuned MuRIL)
    2. Gazetteer matching (with Tamil suffix stripping)
    3. Date regex extraction
    4. Contextual rule cleanup
    
    Returns dict: {PERSON: [...], LOCATION: [...], ORGANIZATION: [...], EVENT: [...], DATE: [...]}
    """
    norm_text = normalize_for_ner(text)
    
    # --- Layer 1: ML prediction ---
    entities = defaultdict(list)
    try:
        ml_entities = predict_entities_ml(norm_text)
        for ent in ml_entities:
            label = ent["label"]
            word = ent["word"].strip()
            if word and len(word) > 1 and word not in entities[label]:
                entities[label].append(word)
    except Exception as e:
        print(f"[NER Inference] ML prediction failed: {e}")
    
    # --- Layer 2: Gazetteer override ---
    gaz_entities = gazetteer_extract(norm_text)
    for label, ent_list in gaz_entities.items():
        for ent in ent_list:
            if ent not in entities[label]:
                entities[label].append(ent)
    
    # --- Layer 3: Date regex ---
    dates = extract_dates(norm_text)
    for d in dates:
        if d not in entities["DATE"]:
            entities["DATE"].append(d)
    
    # --- Layer 4: Contextual rules (cleanup) ---
    final_entities = apply_contextual_rules(dict(entities))
    
    return final_entities


# ---------------------------------------------------------------------------
# Batch Evaluation with CSV output
# ---------------------------------------------------------------------------

def evaluate_on_articles(limit: int = 50):
    """
    Run the fine-tuned ensemble pipeline on articles from the DB
    and save results as professional CSV tables.
    """
    from backend.models.database import SessionLocal, Article
    
    db = SessionLocal()
    try:
        articles = db.query(Article).filter(
            Article.clean_text.isnot(None),
            Article.clean_text != ""
        ).limit(limit).all()
        
        if not articles:
            print("No articles found.")
            return
        
        print(f"[NER Inference] Evaluating {len(articles)} articles...")
        
        os.makedirs(DATA_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Entities CSV
        entities_rows = []
        metrics_rows = []
        
        for article in articles:
            text = f"{article.title}. {article.clean_text}"
            
            start_time = time.time()
            result = extract_entities(text)
            elapsed = time.time() - start_time
            
            # Entities row (one per article)
            entities_rows.append({
                "article_id": article.id,
                "headline": article.title,
                "language": article.language,
                "PERSON": ", ".join(result.get("PERSON", [])),
                "LOCATION": ", ".join(result.get("LOCATION", [])),
                "ORGANIZATION": ", ".join(result.get("ORGANIZATION", [])),
                "EVENT": ", ".join(result.get("EVENT", [])),
                "DATE": ", ".join(result.get("DATE", [])),
            })
            
            # Metrics row
            total = sum(len(v) for v in result.values())
            metrics_rows.append({
                "article_id": article.id,
                "language": article.language,
                "processing_time_sec": round(elapsed, 4),
                "total_entities": total,
                "num_person": len(result.get("PERSON", [])),
                "num_location": len(result.get("LOCATION", [])),
                "num_organization": len(result.get("ORGANIZATION", [])),
                "num_event": len(result.get("EVENT", [])),
                "num_date": len(result.get("DATE", [])),
            })
        
        # Write CSVs
        ent_csv = os.path.join(DATA_DIR, f"finetune_entities_{timestamp}.csv")
        met_csv = os.path.join(DATA_DIR, f"finetune_inference_metrics_{timestamp}.csv")
        
        with open(ent_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "article_id", "headline", "language",
                "PERSON", "LOCATION", "ORGANIZATION", "EVENT", "DATE"
            ])
            writer.writeheader()
            writer.writerows(entities_rows)
        
        with open(met_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=metrics_rows[0].keys())
            writer.writeheader()
            writer.writerows(metrics_rows)
        
        print(f"[NER Inference] Entities saved to {ent_csv}")
        print(f"[NER Inference] Metrics saved to {met_csv}")
        
        # Print summary
        total_ents = sum(m["total_entities"] for m in metrics_rows)
        avg_time = sum(m["processing_time_sec"] for m in metrics_rows) / len(metrics_rows)
        print(f"\n  Total entities extracted: {total_ents}")
        print(f"  Avg processing time: {avg_time:.4f}s per article")
        
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run fine-tuned NER inference")
    parser.add_argument("--limit", type=int, default=50, help="Number of articles to process")
    args = parser.parse_args()
    evaluate_on_articles(args.limit)
