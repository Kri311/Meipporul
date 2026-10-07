"""
Veritas Lens — Auto-Annotator for NER Fine-tuning
==================================================
Generates weak-supervision BIO-tagged data from the zero-shot pipeline
+ gazetteers + regex rules.  Applies Tamil morphological suffix stripping
when matching against gazetteers so that "சென்னையில்" correctly maps
to "சென்னை" (LOCATION).

Output: JSONL files with tokens + BIO tags ready for fine-tuning.
"""

import os
import sys
import json
import re
import unicodedata
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.ner_pipeline.finetune.config import (
    DATASET_DIR, ENTITY_TYPES, LABEL2ID,
    POLITICAL_PARTIES, GOVERNMENT_BODIES, KNOWN_LOCATIONS, KNOWN_PERSONS,
    TAMIL_CASE_SUFFIXES, ORG_CONTEXT_SUFFIXES, LOC_CONTEXT_SUFFIXES,
)


# ---------------------------------------------------------------------------
# Text Normalisation
# ---------------------------------------------------------------------------

def normalize_for_ner(text: str) -> str:
    """Clean text for NER: normalize unicode, remove extra whitespace."""
    if not text:
        return ""
    # Unicode NFC normalization
    text = unicodedata.normalize("NFC", text)
    # Remove URLs
    text = re.sub(r'https?://\S+|www\.\S+', '', text)
    # Remove hashtags but keep the word
    text = re.sub(r'#(\w+)', r'\1', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    # Normalize quotes
    text = text.replace('\u201c', '"').replace('\u201d', '"')
    text = text.replace('\u2018', "'").replace('\u2019', "'")
    return text.strip()


def tokenize_simple(text: str) -> list:
    """
    Simple whitespace + punctuation tokenizer that preserves token offsets.
    Returns list of (token, start, end) tuples.
    """
    tokens = []
    # Split on whitespace first, then separate trailing punctuation
    for match in re.finditer(r'\S+', text):
        word = match.group()
        start = match.start()
        # Separate leading punctuation
        while word and word[0] in '([{"\'':
            tokens.append((word[0], start, start + 1))
            word = word[1:]
            start += 1
        # Separate trailing punctuation
        trailing = []
        while word and word[-1] in '.,:;!?)]\u0964\u0965"\'':
            trailing.insert(0, (word[-1], start + len(word) - 1, start + len(word)))
            word = word[:-1]
        if word:
            tokens.append((word, start, start + len(word)))
        tokens.extend(trailing)
    return tokens


# ---------------------------------------------------------------------------
# Tamil Morphological Suffix Stripping (for gazetteer matching)
# ---------------------------------------------------------------------------

def strip_tamil_suffixes(word: str) -> str:
    """
    Strip common Tamil case-marker suffixes to get the root form.
    E.g. "சென்னையில்" → "சென்னை", "ஸ்டாலினின்" → "ஸ்டாலின்"
    """
    # Sort by length (longest first) to avoid partial stripping
    sorted_suffixes = sorted(TAMIL_CASE_SUFFIXES, key=len, reverse=True)
    for suffix in sorted_suffixes:
        if word.endswith(suffix) and len(word) > len(suffix) + 1:
            return word[:-len(suffix)]
    return word


def is_tamil(text: str) -> bool:
    """Check if text contains Tamil characters."""
    return bool(re.search(r'[\u0B80-\u0BFF]', text))


# ---------------------------------------------------------------------------
# Gazetteer & Rule-based Annotation
# ---------------------------------------------------------------------------

def build_gazetteer_index():
    """Build a lookup dict: normalised_form → (original, label)."""
    index = {}
    for name in KNOWN_PERSONS:
        index[name.lower()] = ("PERSON", name)
    for name in POLITICAL_PARTIES:
        index[name.lower()] = ("ORGANIZATION", name)
    for name in GOVERNMENT_BODIES:
        index[name.lower()] = ("ORGANIZATION", name)
    for name in KNOWN_LOCATIONS:
        index[name.lower()] = ("LOCATION", name)
    return index


GAZ_INDEX = build_gazetteer_index()


def match_gazetteer(token: str) -> str | None:
    """
    Check if a token (or its morphologically stripped form) matches
    any gazetteer entry.  Returns the entity type or None.
    """
    lower = token.lower()
    if lower in GAZ_INDEX:
        return GAZ_INDEX[lower][0]
    # Try stripping Tamil suffixes
    if is_tamil(token):
        root = strip_tamil_suffixes(token)
        if root.lower() in GAZ_INDEX:
            return GAZ_INDEX[root.lower()][0]
    return None


def match_context_suffix(token: str) -> str | None:
    """
    If the token ends with a known org/loc suffix word, classify accordingly.
    Handles agglutinated Tamil forms like "திமுககட்சி".
    """
    for suffix in ORG_CONTEXT_SUFFIXES:
        if token.endswith(suffix) and len(token) > len(suffix):
            return "ORGANIZATION"
    for suffix in LOC_CONTEXT_SUFFIXES:
        if token.endswith(suffix) and len(token) > len(suffix):
            return "LOCATION"
    return None


# ---------------------------------------------------------------------------
# Date Detection (pure regex — not ML)
# ---------------------------------------------------------------------------

DATE_PATTERNS = [
    # DD-MM-YYYY or DD/MM/YYYY
    r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',
    # Month DD, YYYY
    r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b',
    # YYYY-MM-DD
    r'\b\d{4}-\d{2}-\d{2}\b',
]

_date_re = re.compile('|'.join(DATE_PATTERNS), re.IGNORECASE)


def find_date_spans(text: str) -> list:
    """Return list of (start, end) character spans for date expressions."""
    return [(m.start(), m.end()) for m in _date_re.finditer(text)]


# ---------------------------------------------------------------------------
# Zero-Shot Model Annotation (Babelscape)
# ---------------------------------------------------------------------------

def get_zero_shot_entities(text: str) -> list:
    """
    Run the Babelscape zero-shot NER model on the text.
    Returns list of dicts with keys: word, entity_group, start, end, score.
    """
    from backend.ner_pipeline.zero_shot.nlp_pipeline import get_ner_pipeline, is_valid_entity
    
    ner = get_ner_pipeline()
    
    # Segment into sentences to avoid max_length issues
    sentences = re.split(r'(?<=[.!?|।])\s+', text)
    sentences = [s for s in sentences if len(s) > 5]
    
    entities = []
    char_offset = 0
    
    for sent in sentences[:10]:  # Process up to 10 sentences
        results = ner(sent)
        for ent in results:
            group = ent.get('entity_group', ent.get('entity', ''))
            word = ent.get('word', '').strip()
            score = ent.get('score', 0.0)
            
            if not is_valid_entity(word):
                continue
                
            # Map tags
            mapped = None
            if group == 'PER': mapped = 'PERSON'
            elif group == 'ORG': mapped = 'ORGANIZATION'
            elif group == 'LOC': mapped = 'LOCATION'
            elif group == 'MISC': mapped = 'EVENT'
            
            if mapped:
                entities.append({
                    'word': word,
                    'entity_group': mapped,
                    'score': score,
                })
        
        char_offset += len(sent) + 1  # +1 for the space
    
    return entities


# ---------------------------------------------------------------------------
# BIO Tag Assignment (Ensemble: zero-shot + gazetteer + rules)
# ---------------------------------------------------------------------------

def annotate_tokens_bio(text: str, use_model: bool = True) -> dict:
    """
    Given a raw text string, produce BIO-tagged token annotations.
    
    Strategy (ensemble):
    1. Tokenize text
    2. Run zero-shot NER model to get entity spans
    3. For each token, check gazetteer match (with Tamil suffix stripping)
    4. Check context suffix rules
    5. Check date regex
    6. Assign BIO tags with priority: Gazetteer > Model > Context Rules
    
    Returns dict with 'tokens' and 'bio_tags' lists.
    """
    norm_text = normalize_for_ner(text)
    token_tuples = tokenize_simple(norm_text)
    
    if not token_tuples:
        return {"tokens": [], "bio_tags": []}
    
    tokens = [t[0] for t in token_tuples]
    bio_tags = ["O"] * len(tokens)
    
    # --- Layer 1: Date regex (highest priority for DATE) ---
    date_spans = find_date_spans(norm_text)
    for ds, de in date_spans:
        inside = False
        for i, (tok, ts, te) in enumerate(token_tuples):
            if ts >= ds and te <= de:
                bio_tags[i] = "B-DATE" if not inside else "I-DATE"
                inside = True
            elif inside:
                inside = False
    
    # --- Layer 2: Gazetteer matching ---
    for i, tok in enumerate(tokens):
        if bio_tags[i] != "O":
            continue  # Already tagged by date
        gaz_match = match_gazetteer(tok)
        if gaz_match:
            bio_tags[i] = f"B-{gaz_match}"
    
    # Multi-word gazetteer matching (bigrams and trigrams)
    for n in [3, 2]:
        for i in range(len(tokens) - n + 1):
            phrase = " ".join(tokens[i:i+n])
            phrase_lower = phrase.lower()
            if phrase_lower in GAZ_INDEX:
                label = GAZ_INDEX[phrase_lower][0]
                bio_tags[i] = f"B-{label}"
                for j in range(i+1, i+n):
                    bio_tags[j] = f"I-{label}"
    
    # --- Layer 3: Zero-shot model predictions ---
    if use_model:
        try:
            model_entities = get_zero_shot_entities(norm_text)
            for ent in model_entities:
                word = ent['word']
                label = ent['entity_group']
                # Find matching token(s) in our token list
                word_tokens = word.split()
                for i in range(len(tokens) - len(word_tokens) + 1):
                    if " ".join(tokens[i:i+len(word_tokens)]).lower() == word.lower():
                        # Only override if currently O
                        if bio_tags[i] == "O":
                            bio_tags[i] = f"B-{label}"
                            for j in range(i+1, i+len(word_tokens)):
                                if bio_tags[j] == "O":
                                    bio_tags[j] = f"I-{label}"
                        break
        except Exception:
            pass  # Model not available; continue with rules only
    
    # --- Layer 4: Context suffix rules ---
    for i, tok in enumerate(tokens):
        if bio_tags[i] != "O":
            continue
        ctx_match = match_context_suffix(tok)
        if ctx_match:
            bio_tags[i] = f"B-{ctx_match}"
    
    return {"tokens": tokens, "bio_tags": bio_tags}


# ---------------------------------------------------------------------------
# Dataset Generation
# ---------------------------------------------------------------------------

def generate_bio_dataset(use_model: bool = True):
    """
    Read corpus JSONs, annotate each article, and write BIO-tagged JSONL
    files for training and validation.
    """
    import random
    from backend.ner_pipeline.finetune.config import TRAIN_SPLIT
    
    output_dir = DATASET_DIR
    os.makedirs(output_dir, exist_ok=True)
    
    # Load corpora
    all_samples = []
    
    for corpus_file in ["tamil_corpus.json", "english_corpus.json"]:
        fpath = os.path.join(DATASET_DIR, corpus_file)
        if not os.path.exists(fpath):
            print(f"[AutoAnnotator] Skipping {corpus_file} (not found)")
            continue
        
        with open(fpath, "r", encoding="utf-8") as f:
            articles = json.load(f)
        
        print(f"[AutoAnnotator] Processing {len(articles)} articles from {corpus_file}...")
        
        for idx, article in enumerate(articles):
            # Combine headline and content
            text = f"{article['headline']}. {article['content']}"
            
            # Segment into sentences and annotate each
            sentences = re.split(r'(?<=[.!?|।])\s+', text)
            sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
            
            for sent in sentences[:8]:  # Use first 8 sentences per article
                result = annotate_tokens_bio(sent, use_model=use_model)
                if result["tokens"]:
                    all_samples.append({
                        "tokens": result["tokens"],
                        "bio_tags": result["bio_tags"],
                        "language": article["language"],
                    })
            
            if (idx + 1) % 100 == 0:
                print(f"  Processed {idx + 1} articles, {len(all_samples)} sentences so far...")
    
    # Shuffle and split
    random.seed(42)
    random.shuffle(all_samples)
    
    split_idx = int(len(all_samples) * TRAIN_SPLIT)
    train_samples = all_samples[:split_idx]
    val_samples = all_samples[split_idx:]
    
    # Write JSONL
    train_path = os.path.join(output_dir, "train.jsonl")
    val_path = os.path.join(output_dir, "val.jsonl")
    
    for path, samples in [(train_path, train_samples), (val_path, val_samples)]:
        with open(path, "w", encoding="utf-8") as f:
            for sample in samples:
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    
    # Stats
    total_entities = sum(
        1 for s in all_samples for t in s["bio_tags"] if t.startswith("B-")
    )
    entity_counts = defaultdict(int)
    for s in all_samples:
        for tag in s["bio_tags"]:
            if tag.startswith("B-"):
                etype = tag[2:]
                entity_counts[etype] += 1
    
    print(f"\n[AutoAnnotator] Dataset Generation Complete")
    print(f"  Total sentences: {len(all_samples)}")
    print(f"  Train: {len(train_samples)}, Val: {len(val_samples)}")
    print(f"  Total entity mentions: {total_entities}")
    for etype, count in sorted(entity_counts.items()):
        print(f"    {etype}: {count}")
    print(f"  Saved to: {train_path}, {val_path}")
    
    return {
        "total_sentences": len(all_samples),
        "train_count": len(train_samples),
        "val_count": len(val_samples),
        "entity_counts": dict(entity_counts),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate BIO-tagged dataset for NER fine-tuning")
    parser.add_argument("--no-model", action="store_true", help="Skip zero-shot model (use only gazetteers + rules)")
    args = parser.parse_args()
    
    generate_bio_dataset(use_model=not args.no_model)
