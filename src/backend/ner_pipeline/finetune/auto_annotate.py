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
import hashlib
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
TAMIL_MONTHS = (
    "ஜனவரி|பிப்ரவரி|மார்ச்|ஏப்ரல்|மே|ஜூன்|ஜூலை|ஆகஸ்ட்|"
    "செப்டம்பர்|அக்டோபர்|நவம்பர்|டிசம்பர்"
)
TAMIL_DIGITS = r"\d\u0be6-\u0bef"
DATE_PATTERNS.extend([
    rf"[{TAMIL_DIGITS}]{{1,2}}\s*(?:{TAMIL_MONTHS})(?:\s*[{TAMIL_DIGITS}]{{2,4}})?",
    rf"(?:{TAMIL_MONTHS})\s*[{TAMIL_DIGITS}]{{1,2}}(?:,?\s*[{TAMIL_DIGITS}]{{2,4}})?",
])

_date_re = re.compile('|'.join(DATE_PATTERNS), re.IGNORECASE)


def find_date_spans(text: str) -> list:
    """Return list of (start, end) character spans for date expressions."""
    return [(m.start(), m.end()) for m in _date_re.finditer(text)]


# ---------------------------------------------------------------------------
# Zero-Shot Model Annotation (Babelscape)
# ---------------------------------------------------------------------------

_teacher_pipeline = None

_EVENT_MARKERS = {
    "en": re.compile(
        r"(?i)\b(?:operation|war|battle|attack|bombing|protest|strike|summit|"
        r"conference|tournament|world cup|olympics|election|festival|massacre|"
        r"crash|disaster|cyclone|flood|mission|campaign|riots?)\b"
    ),
    "ta": re.compile(
        r"(?:நடவடிக்கை|போர்|போராட்டம்|தாக்குதல்|குண்டுவெடிப்பு|கலவரம்|"
        r"மாநாடு|உச்சிமாநாடு|பேரணி|தேர்தல்|விழா|விளையாட்டுப் போட்டி|"
        r"விபத்து|பேரழிவு|புயல்|வெள்ளம்|மீட்பு நடவடிக்கை)"
    ),
}

# Weak EVENT spans are generated independently of the teacher's MISC class.
# The previous annotator only relabeled a teacher MISC span when a cue was
# nearby; in practice the teacher often returned no such spans, leaving the
# EVENT class empty. These patterns deliberately focus on named or compound
# event mentions rather than tagging every generic word such as "attack".
_EN_EVENT_SPAN_PATTERNS = [
    # Named operations/missions/campaigns: Operation Sindoor, Mission X, etc.
    re.compile(
        r"\b(?:Operation|Mission|Exercise|Campaign|Project)\s+"
        r"[A-Z0-9][\w’'-]*(?:\s+[A-Z0-9][\w’'-]*){0,2}\b"
    ),
    # Named event heads with at least one proper-cased word before the head.
    re.compile(
        r"\b(?:[A-Z][\w’'-]*\s+){1,3}"
        r"(?:War|Battle|Summit|Conference|Tournament|World\s+Cup|Grand\s+Prix|"
        r"Olympics|Election|Festival|Massacre|Bombing|Protest|Strike|Riot)\b"
    ),
]
_TA_EVENT_SPAN_PATTERN = re.compile(
    # Tamil does not have case distinctions. Capture short compounds ending
    # in an event head; avoid one-token generic mentions such as "போராட்டம்".
    r"(?<![\u0B80-\u0BFF])"
    r"[\u0B80-\u0BFF]+(?:\s+[\u0B80-\u0BFF]+){1,3}\s*"
    r"(?:நடவடிக்கை|போர்|போராட்டம்|தாக்குதல்|குண்டுவெடிப்பு|கலவரம்|"
    r"மாநாடு|உச்சிமாநாடு|பேரணி|தேர்தல்|விழா|விளையாட்டுப் போட்டி|"
    r"விபத்து|பேரழிவு|புயல்|வெள்ளம்|மீட்பு நடவடிக்கை)"
)


def find_weak_event_spans(text: str, language: str) -> list:
    """Find conservative weak EVENT character spans in English or Tamil text.

    These are training labels, not gold annotations. English patterns require
    a named event construction; Tamil patterns require a multiword compound
    ending in an event noun. The teacher MISC mapping remains an additional
    source of spans.
    """
    if language == "ta":
        return [(match.start(), match.end()) for match in _TA_EVENT_SPAN_PATTERN.finditer(text)]
    spans = []
    for pattern in _EN_EVENT_SPAN_PATTERNS:
        spans.extend((match.start(), match.end()) for match in pattern.finditer(text))
    # Keep non-overlapping longest spans; duplicate matches from patterns are
    # otherwise capable of producing invalid BIO sequences.
    selected = []
    for start, end in sorted(set(spans), key=lambda span: (span[0], -(span[1] - span[0]))):
        if selected and start < selected[-1][1]:
            if end > selected[-1][1]:
                selected[-1] = (selected[-1][0], end)
            continue
        selected.append((start, end))
    return selected


def is_weak_event_mention(sentence: str, start: int, end: int, word: str, language: str) -> bool:
    """Conservatively map teacher MISC spans to EVENT only beside event cues.

    WikiNeural's MISC class mixes many kinds of miscellaneous spans, so it is
    never mapped directly. A nearby explicit event noun is required. These
    remain weak labels and must not be reported as human-gold evaluation.
    """
    lang = "ta" if language == "ta" else "en"
    if _EVENT_MARKERS[lang].search(word or ""):
        return True
    # Require the cue to be adjacent to the candidate span to avoid converting
    # unrelated nationalities/organizations into events due to distant context.
    neighborhood = f"{sentence[max(0, start - 36):start]} {sentence[end:end + 36]}"
    return bool(_EVENT_MARKERS[lang].search(neighborhood))


def get_zero_shot_entities(text: str, language: str | None = None) -> list:
    """
    Run a separate multilingual teacher model on the text.

    Do not use the local fine-tuned checkpoint here: generating its training
    labels from its own predictions creates a self-training feedback loop and
    makes validation appear better without adding independent information.
    Returns list of dicts with keys: word, entity_group, start, end, score.
    """
    global _teacher_pipeline
    from backend.ner_pipeline.zero_shot.nlp_pipeline import is_valid_entity

    if _teacher_pipeline is None:
        import torch
        from transformers import pipeline
        teacher_name = os.getenv(
            "NER_TEACHER_MODEL_NAME", "Babelscape/wikineural-multilingual-ner"
        )
        _teacher_pipeline = pipeline(
            "ner", model=teacher_name, aggregation_strategy="simple",
            device=0 if torch.cuda.is_available() else -1,
        )
        print(f"[AutoAnnotator] Weak-label teacher: {teacher_name}")
    ner = _teacher_pipeline
    
    entities = []
    minimum_score = float(os.getenv("NER_TEACHER_MIN_CONFIDENCE", "0.70"))
    for match in list(re.finditer(r'[^.!?।ஃ\n]+(?:[.!?।ஃ]+|$)', text))[:10]:
        sent = match.group().strip()
        if len(sent) <= 5:
            continue
        sentence_start = match.start() + len(match.group()) - len(match.group().lstrip())
        results = ner(sent)
        for ent in results:
            group = ent.get('entity_group', ent.get('entity', ''))
            word = ent.get('word', '').strip()
            score = float(ent.get('score', 0.0) or 0.0)

            if score < minimum_score:
                continue
            
            if not is_valid_entity(word):
                continue
                
            # Map tags
            mapped = None
            if group in ('PER', 'PERSON'): mapped = 'PERSON'
            elif group in ('ORG', 'ORGANIZATION'): mapped = 'ORGANIZATION'
            elif group in ('LOC', 'LOCATION', 'GPE'): mapped = 'LOCATION'
            elif group in ("MISC", "MISCELLANEOUS") and is_weak_event_mention(
                sent, int(ent.get("start") or 0), int(ent.get("end") or 0), word,
                (language or ("ta" if re.search(r"[\u0B80-\u0BFF]", sent) else "en")),
            ):
                # Only event-cued MISC spans receive weak EVENT labels. Generic
                # MISC spans remain outside the event class.
                mapped = "EVENT"
            
            if mapped:
                entities.append({
                    'word': word,
                    'entity_group': mapped,
                    'score': score,
                    'start': sentence_start + int(ent.get('start') or 0),
                    'end': sentence_start + int(ent.get('end') or 0),
                })
    
    return entities


# ---------------------------------------------------------------------------
# BIO Tag Assignment (Ensemble: zero-shot + gazetteer + rules)
# ---------------------------------------------------------------------------

def annotate_tokens_bio(text: str, use_model: bool = True, language: str | None = None) -> dict:
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
    
    # Longest-first phrase matching keeps complete gazetteer mentions intact.
    max_phrase = max((len(key.split()) for key in GAZ_INDEX), default=1)
    for n in range(max_phrase, 1, -1):
        for i in range(len(tokens) - n + 1):
            phrase = " ".join(tokens[i:i+n])
            phrase_lower = phrase.lower()
            if phrase_lower in GAZ_INDEX and all(tag == "O" for tag in bio_tags[i:i+n]):
                label = GAZ_INDEX[phrase_lower][0]
                bio_tags[i] = f"B-{label}"
                for j in range(i+1, i+n):
                    bio_tags[j] = f"I-{label}"

    # --- Layer 2b: Explicit named/compound event mention rules ---
    event_language = (language or ("ta" if is_tamil(norm_text) else "en")).lower().split("-")[0]
    for event_start, event_end in find_weak_event_spans(norm_text, event_language):
        matching = [i for i, (_, ts, te) in enumerate(token_tuples)
                    if ts < event_end and te > event_start]
        # Do not overwrite DATE or gazetteer spans. A named location/person
        # inside an event expression can therefore retain its own entity type.
        if matching and all(bio_tags[i] == "O" for i in matching):
            for offset, token_index in enumerate(matching):
                bio_tags[token_index] = f"{'B' if offset == 0 else 'I'}-EVENT"
    
    # --- Layer 3: Zero-shot model predictions ---
    if use_model:
        try:
            model_entities = get_zero_shot_entities(norm_text, language=event_language)
            for ent in model_entities:
                label = ent['entity_group']
                start, end = ent.get("start"), ent.get("end")
                matching = [i for i, (_, ts, te) in enumerate(token_tuples)
                            if start is not None and end is not None and ts < end and te > start]
                # Character offsets are the reliable alignment. Keep exact
                # token-string matching only as a fallback for model versions
                # that do not return offsets.
                if not matching:
                    word = ent["word"].strip()
                    word_tokens = word.split()
                    for i in range(len(tokens) - len(word_tokens) + 1):
                        if " ".join(tokens[i:i+len(word_tokens)]).casefold() == word.casefold():
                            matching = list(range(i, i + len(word_tokens)))
                            break
                if matching and all(bio_tags[i] == "O" for i in matching):
                    for offset, token_index in enumerate(matching):
                        bio_tags[token_index] = f"{'B' if offset == 0 else 'I'}-{label}"
        except Exception as exc:
            raise RuntimeError(
                "Teacher NER failed while generating weak labels. Use --no-model "
                "for gazetteer/date-only annotations or fix the teacher model setup."
            ) from exc
    
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
                result = annotate_tokens_bio(sent, use_model=use_model, language=article["language"])
                if result["tokens"]:
                    article_key = hashlib.sha256(
                        (article.get("headline", "") + "\n" + article.get("content", "")[:1000])
                        .casefold().encode("utf-8")
                    ).hexdigest()
                    all_samples.append({
                        "tokens": result["tokens"],
                        "bio_tags": result["bio_tags"],
                        "language": article["language"],
                        "article_id": article_key,
                        "label_source": (
                            "teacher_gazetteer_event_weak"
                            if any(tag.endswith("-EVENT") for tag in result["bio_tags"])
                            else "teacher_gazetteer_weak"
                        ),
                    })
            
            if (idx + 1) % 100 == 0:
                print(f"  Processed {idx + 1} articles, {len(all_samples)} sentences so far...")
    
    # Split by article, never by sentence. Sentence-level splitting leaks the
    # same article's entities into both training and validation.
    random.seed(42)
    article_ids = sorted({sample["article_id"] for sample in all_samples})
    if len(article_ids) < 2:
        raise ValueError("Need at least two distinct articles to create an article-level train/validation split.")
    # Stratify by language and whether an article carries an EVENT label, but
    # keep every article wholly in one split to prevent sentence leakage.
    article_meta = {}
    for sample in all_samples:
        meta = article_meta.setdefault(sample["article_id"], {"language": sample["language"], "has_event": False})
        meta["has_event"] = meta["has_event"] or any(tag == "B-EVENT" for tag in sample["bio_tags"])
    strata = defaultdict(list)
    for article_id, meta in article_meta.items():
        strata[(meta["language"], meta["has_event"])].append(article_id)
    train_article_ids = set()
    for stratum_ids in strata.values():
        random.shuffle(stratum_ids)
        if len(stratum_ids) < 2:
            # Preserve the only sample in train; the EVENT support guard below
            # will explain if a second independent event article is required.
            train_article_ids.update(stratum_ids)
            continue
        split_idx = min(len(stratum_ids) - 1, max(1, int(len(stratum_ids) * TRAIN_SPLIT)))
        train_article_ids.update(stratum_ids[:split_idx])
    if len(train_article_ids) == len(article_ids):
        train_article_ids.remove(article_ids[-1])
    train_samples = [sample for sample in all_samples if sample["article_id"] in train_article_ids]
    val_samples = [sample for sample in all_samples if sample["article_id"] not in train_article_ids]
    
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
    event_counts_by_language = defaultdict(int)
    for s in all_samples:
        for tag in s["bio_tags"]:
            if tag.startswith("B-"):
                etype = tag[2:]
                entity_counts[etype] += 1
                if etype == "EVENT":
                    event_counts_by_language[s["language"]] += 1
    
    print(f"\n[AutoAnnotator] Dataset Generation Complete")
    print(f"  Total sentences: {len(all_samples)}")
    print(f"  Train: {len(train_samples)}, Val: {len(val_samples)}")
    print(f"  Article groups: {len(train_article_ids)} train, {len(article_ids) - len(train_article_ids)} val")
    print("  Validation targets are teacher/gazetteer weak labels, not human-reviewed ground truth.")
    print(f"  Total entity mentions: {total_entities}")
    print(f"  EVENT mentions by language: {dict(event_counts_by_language)}")
    for etype, count in sorted(entity_counts.items()):
        print(f"    {etype}: {count}")
    print(f"  Saved to: {train_path}, {val_path}")
    
    return {
        "total_sentences": len(all_samples),
        "train_count": len(train_samples),
        "val_count": len(val_samples),
        "entity_counts": dict(entity_counts),
        "event_counts_by_language": dict(event_counts_by_language),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate BIO-tagged dataset for NER fine-tuning")
    parser.add_argument("--no-model", action="store_true", help="Skip zero-shot model (use only gazetteers + rules)")
    args = parser.parse_args()
    
    generate_bio_dataset(use_model=not args.no_model)
