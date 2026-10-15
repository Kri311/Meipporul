"""
Veritas Lens — Zero-Shot NER Pipeline
======================================
Hybrid NER pipeline: Transformer model + Gazetteer + Tamil morphology
+ Contextual rules → Final entities.

Key design decisions:
  - Tamil articles keep entities in Tamil script (no English translation).
  - English articles use gazetteer canonical forms.
  - Processes article *content* (clean_text), not just the title.
  - Uses the local fine-tuned MuRIL checkpoint when available. Its labels are
    open-vocabulary values: the gazetteers normalize known aliases and add
    recall, but do not restrict which PERSON/ORGANIZATION/LOCATION mentions
    the transformer may extract. Babelscape is a load-failure fallback.
"""

import os
import sys
import time
import json
import re
from collections import defaultdict
import logging
import torch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from backend.models.database import SessionLocal, Article, init_db
from backend.ner_pipeline.zero_shot.normalization import (
    normalize_entity_text,
    strip_tamil_morphology,
)
from backend.ingestion.tasks.text_cleaning import parse_clean_article

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(log_dir, 'pipeline.log'),
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("NLP_Pipeline")

# ---------------------------------------------------------------------------
# Model selection — prefer the local fine-tuned MuRIL checkpoint when present.
# ---------------------------------------------------------------------------
_finetune_model_path = os.path.join(
    os.path.dirname(__file__), '..', 'finetune', 'model', 'best'
)
_default_teacher_model = "Babelscape/wikineural-multilingual-ner"
# Existing fine-tuned artifacts were trained/evaluated against auto-generated
# weak labels. Do not promote them over the independent multilingual baseline
# by file existence alone. Opt in after reviewing fresh article-level metrics.
_explicit_model = os.getenv("NER_MODEL_NAME")
_prefer_finetuned = os.getenv("NER_PREFER_FINETUNED_MODEL", "1").casefold() in {"1", "true", "yes"}
if _explicit_model:
    NER_MODEL_NAME = _explicit_model
elif _prefer_finetuned and os.path.exists(_finetune_model_path):
    NER_MODEL_NAME = _finetune_model_path
else:
    NER_MODEL_NAME = _default_teacher_model

NER_BATCH_SIZE = int(os.getenv("NER_BATCH_SIZE", "16"))
NER_MIN_CONFIDENCE = float(os.getenv("NER_MIN_CONFIDENCE", "0.35"))
# Process more sentences for better entity coverage from article body
# By default, NER sees every sentence. Set NER_MAX_SENTENCES to a positive
# value only when deliberately trading entity recall for throughput.
MAX_SENTENCES = int(os.getenv("NER_MAX_SENTENCES", "0"))

_ner_pipeline = None
_entity_linker = None

def get_entity_linker():
    global _entity_linker
    if _entity_linker is None:
        from backend.ner_pipeline.zero_shot.entity_linker import EntityLinker
        _entity_linker = EntityLinker()
    return _entity_linker


# ---------------------------------------------------------------------------
# Rich gazetteers (merged from finetune/config.py for broad coverage)
# ---------------------------------------------------------------------------
KNOWN_PERSONS_EN = [
    "M.K. Stalin", "Edappadi Palaniswami", "Annamalai", "Rahul Gandhi",
    "Narendra Modi", "Amit Shah", "Udhayanidhi Stalin",
]
KNOWN_PERSONS_TA = [
    "மு.க.ஸ்டாலின்", "எடப்பாடி பழனிசாமி", "அண்ணாமலை",
    "ராகுல் காந்தி", "நரேந்திர மோடி", "அமித் ஷா", "உதயநிதி ஸ்டாலின்",
]

KNOWN_LOCATIONS_EN = [
    "Chennai", "Madurai", "Coimbatore", "Tiruchirappalli", "Salem",
    "Tirunelveli", "Erode", "Vellore", "Thanjavur", "Dindigul",
    "Kanchipuram", "Cuddalore", "Thoothukudi", "Tiruvannamalai",
    "India", "Tamil Nadu",
]
KNOWN_LOCATIONS_TA = [
    "சென்னை", "மதுரை", "கோவை", "திருச்சி", "சேலம்",
    "திருநெல்வேலி", "ஈரோடு", "வேலூர்", "தஞ்சாவூர்", "திண்டுக்கல்",
    "காஞ்சிபுரம்", "கடலூர்", "தூத்துக்குடி", "திருவண்ணாமலை",
    "இந்தியா", "தமிழ்நாடு", "தமிழகம்",
]

POLITICAL_PARTIES_EN = [
    "DMK", "AIADMK", "BJP", "Congress", "INC", "NTK", "PMK", "VCK",
    "MDMK", "CPI", "CPI(M)", "AMMK", "DMDK", "TMC", "MNM",
]
POLITICAL_PARTIES_TA = [
    "திமுக", "அதிமுக", "பாஜக", "காங்கிரஸ்", "நாதக", "பாமக",
    "விசிக", "மதிமுக", "அமமுக", "தேமுதிக",
]

GOVERNMENT_BODIES_EN = [
    "Supreme Court", "High Court", "Election Commission", "Parliament",
    "Legislative Assembly", "Lok Sabha", "Rajya Sabha",
]
GOVERNMENT_BODIES_TA = [
    "உச்ச நீதிமன்றம்", "உயர் நீதிமன்றம்", "தேர்தல் ஆணையம்",
    "நாடாளுமன்றம்", "சட்டமன்றம்", "மக்களவை", "மாநிலங்களவை",
]

# Bidirectional alias map:  alias (lowered) → (canonical, entity_type)
# Built once at import time.
_ALIAS_MAP = {}


def _build_alias_map():
    """Build a bidirectional alias lookup: alias → (canonical_en, canonical_ta)."""
    # Person pairs: (english, tamil)
    person_pairs = list(zip(KNOWN_PERSONS_EN, KNOWN_PERSONS_TA))
    for en, ta in person_pairs:
        _ALIAS_MAP[en.lower()] = {"en": en, "ta": ta, "type": "PERSON"}
        _ALIAS_MAP[ta] = {"en": en, "ta": ta, "type": "PERSON"}

    # Location pairs
    loc_pairs = list(zip(KNOWN_LOCATIONS_EN, KNOWN_LOCATIONS_TA))
    for en, ta in loc_pairs:
        _ALIAS_MAP[en.lower()] = {"en": en, "ta": ta, "type": "LOCATION"}
        _ALIAS_MAP[ta] = {"en": en, "ta": ta, "type": "LOCATION"}

    # Org pairs
    org_pairs = list(zip(POLITICAL_PARTIES_EN, POLITICAL_PARTIES_TA))
    for en, ta in org_pairs:
        _ALIAS_MAP[en.lower()] = {"en": en, "ta": ta, "type": "ORGANIZATION"}
        _ALIAS_MAP[ta] = {"en": en, "ta": ta, "type": "ORGANIZATION"}

    gov_pairs = list(zip(GOVERNMENT_BODIES_EN, GOVERNMENT_BODIES_TA))
    for en, ta in gov_pairs:
        _ALIAS_MAP[en.lower()] = {"en": en, "ta": ta, "type": "ORGANIZATION"}
        _ALIAS_MAP[ta] = {"en": en, "ta": ta, "type": "ORGANIZATION"}


_build_alias_map()

# ---------------------------------------------------------------------------
# Also load the JSON gazetteer for additional aliases
# ---------------------------------------------------------------------------
_gazetteer = None


def load_gazetteer():
    global _gazetteer
    if _gazetteer is None:
        gazetteer_path = os.path.join(os.path.dirname(__file__), 'gazetteer.json')
        if os.path.exists(gazetteer_path):
            with open(gazetteer_path, 'r', encoding='utf-8') as f:
                _gazetteer = json.load(f)
        else:
            _gazetteer = {}
    return _gazetteer


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------
def get_ner_pipeline():
    global _ner_pipeline
    if _ner_pipeline is None:
        from transformers import pipeline
        configured_device = 0 if torch.cuda.is_available() else -1
        candidates = [NER_MODEL_NAME]
        allow_teacher_fallback = os.getenv("NER_ALLOW_TEACHER_FALLBACK", "1").casefold() in {"1", "true", "yes"}
        if allow_teacher_fallback and NER_MODEL_NAME != "Babelscape/wikineural-multilingual-ner":
            candidates.append("Babelscape/wikineural-multilingual-ner")
        devices = [configured_device, -1] if configured_device == 0 else [-1]
        last_error = None
        for model_name in candidates:
            for device in dict.fromkeys(devices):
                logger.info("Loading NER model %s on %s", model_name, "GPU" if device == 0 else "CPU")
                try:
                    # The local checkpoint includes tokenizer.json. Fast
                    # tokenization preserves offsets for Hugging Face's NER
                    # aggregation pipeline, which the slow tokenizer lacks.
                    if os.path.isdir(model_name):
                        from transformers import AutoModelForTokenClassification, AutoTokenizer
                        tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
                        model = AutoModelForTokenClassification.from_pretrained(model_name)
                        _ner_pipeline = pipeline(
                            "ner", model=model, tokenizer=tokenizer,
                            aggregation_strategy="simple", device=device,
                        )
                    else:
                        _ner_pipeline = pipeline(
                            "ner", model=model_name,
                            aggregation_strategy="simple", device=device,
                        )
                    return _ner_pipeline
                except Exception as exc:
                    last_error = exc
                    logger.exception("NER model load failed (%s on %s)", model_name, device)
        raise RuntimeError("All configured and fallback NER model/device combinations failed") from last_error
    return _ner_pipeline


def _run_ner(ner, sentences):
    """Retry inference on CPU if the GPU runs out of memory."""
    try:
        return ner(sentences)
    except RuntimeError as exc:
        if not torch.cuda.is_available() or "out of memory" not in str(exc).casefold():
            raise
        logger.warning("CUDA ran out of memory during NER; retrying this batch on CPU")
        torch.cuda.empty_cache()
        ner.model.to("cpu")
        ner.device = torch.device("cpu")
        return ner(sentences)


def normalize_text(text: str) -> str:
    """Normalize unicode, spacing, and quotes."""
    text = re.sub(r'\s+', ' ', text)
    text = text.replace('\u201c', '"').replace('\u201d', '"')
    return text.strip()


def segment_sentences(text: str) -> list:
    """Simple regex-based sentence segmentation for EN/TA."""
    sentences = re.split(r'(?<=[.!?।ஃ])\s+|\n+', text)
    return [s for s in sentences if len(s) > 5]


# ---------------------------------------------------------------------------
# Contextual rules — strip designations from entity strings
# ---------------------------------------------------------------------------
PERSON_PREFIXES = [
    r"^Chief\s+Minister\s+", r"^Prime\s+Minister\s+", r"^Minister\s+",
    r"^President\s+", r"^Governor\s+", r"^Mr\.\s*", r"^Mrs\.\s*",
    r"^Ms\.\s*", r"^Dr\.\s*", r"^Sri\.\s*", r"^Shri\.\s*",
    r"^முதலமைச்சர்\s+", r"^முதல்வர்\s+", r"^பிரதமர்\s+",
    r"^அமைச்சர்\s+", r"^ஆளுநர்\s+",
    r"^திரு\.\s*", r"^திருமதி\.\s*", r"^டாக்டர்\s*", r"^செல்வி\.\s*",
    r"^எம்\.பி\.\s+", r"^எம்\.எல்\.ஏ\.\s+", r"^தலைவர்\s+",
]

LOCATION_SUFFIXES = [
    r"\s+District$", r"\s+City$", r"\s+State$", r"\s+Town$",
    r"\s+மாவட்டம்$", r"\s+ஊராட்சி$", r"\s+ஒன்றியம்$",
    r"\s+மாநகராட்சி$", r"\s+பஞ்சாயத்து$", r"\s+நகரம்$",
    r"\s+பேரூராட்சி$",
]


def apply_contextual_rules(word: str) -> str:
    """Strip designations / titles / administrative suffixes."""
    cleaned = word
    for prefix in PERSON_PREFIXES:
        cleaned = re.sub(prefix, "", cleaned, flags=re.IGNORECASE)
    for suffix in LOCATION_SUFFIXES:
        cleaned = re.sub(suffix, "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


# ---------------------------------------------------------------------------
# Entity resolution — language-aware
# ---------------------------------------------------------------------------
def resolve_entity(word: str, entity_group: str, language: str = "en") -> str | None:
    """Resolve a raw NER token to a stable entity representation.

    For **Tamil** articles the entity is kept in Tamil script after
    normalization and morphological stripping.  For **English** articles
    we attempt gazetteer matching to obtain a stable English canonical form.

    Resolution pipeline:
        1. Normalize spacing/punctuation (Tamil initials).
        2. Strip titles and designations.
        3. Strip Tamil morphological case suffixes.
        4. Gazetteer lookup (language-aware).
        5. Fallback: return the cleaned string.
    """
    # Step 1: normalise punctuation / spacing
    normalized = normalize_entity_text(word)

    # Step 2: strip designations
    stripped = apply_contextual_rules(normalized)
    if not stripped:
        return None

    # Step 3: morphological stemming
    root = strip_tamil_morphology(stripped)
    if not root:
        root = stripped

    # Step 4: gazetteer lookup (language-aware)
    # Check the bidirectional alias map first
    lookup_keys = [root.lower(), root, stripped.lower(), stripped]
    for key in lookup_keys:
        if key in _ALIAS_MAP:
            entry = _ALIAS_MAP[key]
            # Return in the article's language
            return entry.get("ta") if language == "ta" else entry.get("en")

    # Also check the JSON gazetteer
    gazetteer = load_gazetteer()
    if entity_group in gazetteer:
        for entry in gazetteer[entity_group]:
            canonical = entry['canonical']
            aliases = entry.get('aliases', [])
            lowered_aliases = [a.lower() for a in aliases]
            for key in lookup_keys:
                if key in lowered_aliases:
                    if language == "ta":
                        # Find a Tamil alias to return
                        for alias in aliases:
                            if any('\u0B80' <= c <= '\u0BFF' for c in alias):
                                return alias
                    return canonical

    # Step 5: fallback — return the cleaned root
    return root


def is_valid_entity(word: str) -> bool:
    """Filter out garbage NER tokens."""
    word = re.sub(r"\s+", " ", str(word or "")).strip(" \t\r\n,;:|\"'`()[]{}")
    if word.startswith("##"):
        return False
    if re.match(r'^[\d\W_]+$', word):
        return False
    # Reject tokens that start with Tamil combining marks
    if re.match(r'^[\u0BBE-\u0BCC\u0BCD]', word):
        return False
    if len(word) < 2 or len(word) > 100 or len(word.split()) > 8:
        return False
    # Reject model fragments consisting only of punctuation / combining signs.
    if not re.search(r"[A-Za-z\u0B80-\u0BFF]", word):
        return False
    return True


# ---------------------------------------------------------------------------
# Main batch processing
# ---------------------------------------------------------------------------
def process_nlp_batch() -> bool:
    """Process a batch of articles through the NER pipeline."""
    db = SessionLocal()
    try:
        articles = db.query(Article).filter(
            Article.clean_text.isnot(None),
            Article.clean_text != "",
            Article.processing_status.in_(["eligible", "extracted", "pending", "embedded"]),
        ).limit(NER_BATCH_SIZE).all()

        if not articles:
            logger.info("No pending articles found for NLP pipeline.")
            return False

        logger.info(f"Processing NLP pipeline for {len(articles)} articles...")
        start_time = time.time()

        ner = get_ner_pipeline()

        for article in articles:
            lang = article.language if article.language in ("en", "ta") else "ta"
            parsed_title, body = parse_clean_article(article.clean_text, article.title)
            # Titles are often the densest, cleanest source of named entities.
            # Keep them in front so bounded processing still sees the headline.
            norm_text = normalize_text(". ".join(part for part in (parsed_title or article.title, body) if part))
            sentences = segment_sentences(norm_text)
            target_sentences = sentences[:MAX_SENTENCES] if MAX_SENTENCES > 0 else sentences

            # Start fresh. Previously persisted named_entities came from older
            # extractors and could contain whole headline fragments labelled as
            # LOCATION; carrying them forward made bad entities permanent.
            entities = defaultdict(list)

            if target_sentences:
                results = _run_ner(ner, target_sentences)
                for sentence_result in results:
                    for ent in sentence_result:
                        try:
                            confidence = float(ent.get("score", 1.0))
                        except (TypeError, ValueError):
                            confidence = 0.0
                        if confidence < NER_MIN_CONFIDENCE:
                            continue
                        group = ent.get('entity_group', ent.get('entity', ''))
                        word = ent.get('word', '').strip()

                        if not is_valid_entity(word):
                            continue

                        # Map model output tags to our entity types
                        mapped_group = None
                        if group in ('PER', 'PERSON', 'B-PERSON', 'I-PERSON'):
                            mapped_group = 'PERSON'
                        elif group in ('ORG', 'ORGANIZATION', 'B-ORGANIZATION', 'I-ORGANIZATION'):
                            mapped_group = 'ORGANIZATION'
                        elif group in ('LOC', 'LOCATION', 'B-LOCATION', 'I-LOCATION'):
                            mapped_group = 'LOCATION'
                        elif group in ('EVENT', 'B-EVENT', 'I-EVENT'):
                            mapped_group = 'EVENT'

                        if mapped_group:
                            resolved = resolve_entity(word, mapped_group, lang)
                            if resolved and resolved not in entities[mapped_group]:
                                entities[mapped_group].append(resolved)

            # Date extraction regex (language-agnostic fallback)
            tamil_months = (
                "ஜனவரி|பிப்ரவரி|மார்ச்|ஏப்ரல்|மே|ஜூன்|ஜூலை|ஆகஸ்ட்|"
                "செப்டம்பர்|அக்டோபர்|நவம்பர்|டிசம்பர்"
            )
            date_matches = re.findall(
                r'\b\d{4}-\d{1,2}-\d{1,2}\b'
                r'|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b'
                r'|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b'
                r'|\b\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}\b'
                rf'|[\d\u0be6-\u0bef]{{1,2}}\s*(?:{tamil_months})(?:\s*[\d\u0be6-\u0bef]{{2,4}})?'
                rf'|(?:{tamil_months})\s*[\d\u0be6-\u0bef]{{1,2}}(?:,?\s*[\d\u0be6-\u0bef]{{2,4}})?',
                norm_text,
                re.IGNORECASE,
            )
            for dm in date_matches:
                if dm not in entities["DATE"]:
                    entities["DATE"].append(dm)

            article.named_entities = dict(entities)
            linker = get_entity_linker()
            article.linked_entities = linker.link_entities(article.named_entities)
            article.processing_status = "completed"

        db.commit()

        elapsed = time.time() - start_time
        logger.info(
            f"NLP Pipeline finished {len(articles)} articles in {elapsed:.2f}s "
            f"({len(articles)/elapsed:.1f} art/sec)."
        )
        return True

    except Exception as e:
        db.rollback()
        logger.error(f"Error: {e}")
        raise
    finally:
        db.close()


def run_nlp_pipeline(reprocess_all=False):
    """Entry point: process all pending articles in batches."""
    init_db()
    if reprocess_all:
        db = SessionLocal()
        try:
            count = db.query(Article).filter(
                Article.clean_text.isnot(None), Article.clean_text != ""
            ).update({Article.processing_status: "pending"}, synchronize_session=False)
            db.commit()
            logger.info("Queued %s existing articles for NER reprocessing with %s", count, NER_MODEL_NAME)
        finally:
            db.close()
    logger.info("Starting Advanced NLP Pipeline...")
    while True:
        has_more = process_nlp_batch()
        if not has_more:
            break


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run multilingual article NER")
    parser.add_argument(
        "--reprocess-all", action="store_true",
        help="Re-run NER for every article with cleaned text, not only pending rows",
    )
    args = parser.parse_args()
    run_nlp_pipeline(reprocess_all=args.reprocess_all)
