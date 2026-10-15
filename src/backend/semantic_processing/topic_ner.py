"""NER features used by the bilingual event-topic classifier.

The transformer NER model is only used while preparing training features. At
inference time, the topic classifier consumes the entities already persisted
by the article NER stage (including linked/canonical entities).
"""

import json
import os
import re
import unicodedata
from collections import defaultdict

ENTITY_ALIASES = {
    "PER": "PERSON", "PERSON": "PERSON",
    "ORG": "ORGANIZATION", "ORGANIZATION": "ORGANIZATION",
    "LOC": "LOCATION", "LOCATION": "LOCATION", "GPE": "LOCATION",
    "EVENT": "EVENT",
}
TOPIC_ENTITY_TYPES = ("PERSON", "ORGANIZATION", "LOCATION", "EVENT")
MIN_CONFIDENCE = float(os.getenv("NER_MIN_CONFIDENCE", "0.35"))
MAX_ENTITY_TOKENS = int(os.getenv("TOPIC_NER_MAX_ENTITY_TOKENS", "5"))


def _clean_entity(value):
    if isinstance(value, dict):
        value = (value.get("canonical_en") or value.get("canonical_ta") or
                 value.get("text") or value.get("entity"))
    if not isinstance(value, str):
        return ""
    value = unicodedata.normalize("NFC", value)
    value = re.sub(r"\s+", " ", value).strip(" \t\r\n,;:|\"'`()[]{}")
    if not value or len(value) < 2 or len(value.split()) > MAX_ENTITY_TOKENS:
        return ""
    if re.fullmatch(r"[\W_\d]+", value, flags=re.UNICODE):
        return ""
    return value


def normalize_entity_payload(payload):
    """Normalize list/string/dict entity payloads to typed deduplicated names."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            return {}
    if not isinstance(payload, dict):
        return {}

    result = defaultdict(list)
    seen = defaultdict(set)
    for raw_type, raw_values in payload.items():
        entity_type = ENTITY_ALIASES.get(str(raw_type).upper())
        if entity_type not in TOPIC_ENTITY_TYPES:
            continue
        values = raw_values if isinstance(raw_values, (list, tuple, set)) else [raw_values]
        for raw_value in values:
            name = _clean_entity(raw_value)
            key = name.casefold()
            if name and key not in seen[entity_type]:
                result[entity_type].append(name)
                seen[entity_type].add(key)
    return dict(result)


def entity_feature_dict(payload):
    """Build sparse, typed NER features; names and type counts are separate."""
    entities = normalize_entity_payload(payload)
    features = {}
    for entity_type in TOPIC_ENTITY_TYPES:
        names = entities.get(entity_type, [])
        features[f"type-count:{entity_type}"] = min(len(names), 5)
        for name in names:
            features[f"entity:{entity_type}:{name.casefold()}"] = 1
    return features


def extract_training_entities(texts, languages, batch_size=16):
    """Run NER on sentence-sized chunks to avoid silently truncating articles."""
    from backend.ner_pipeline.zero_shot.nlp_pipeline import (
        get_ner_pipeline, is_valid_entity, resolve_entity, segment_sentences,
        _run_ner,
    )

    ner = get_ner_pipeline()
    extracted = []
    type_counts = defaultdict(int)
    for start in range(0, len(texts), batch_size):
        batch_texts = [str(text or "")[:5000] for text in texts[start:start + batch_size]]
        batch_languages = languages[start:start + batch_size]
        for article_text, language in zip(batch_texts, batch_languages):
            mapped = defaultdict(list)
            sentences = segment_sentences(article_text)[:20]
            if not sentences and article_text.strip():
                sentences = [article_text.strip()]
            for sentence_start in range(0, len(sentences), batch_size):
                sentence_batch = sentences[sentence_start:sentence_start + batch_size]
                outputs = _run_ner(ner, sentence_batch)
                if len(sentence_batch) == 1 and outputs and isinstance(outputs[0], dict):
                    outputs = [outputs]
                for entities in outputs:
                    for item in entities or []:
                        label = str(item.get("entity_group", item.get("entity", ""))).upper()
                        entity_type = ENTITY_ALIASES.get(label)
                        if entity_type not in TOPIC_ENTITY_TYPES:
                            continue
                        try:
                            confidence = float(item.get("score", 1.0))
                        except (TypeError, ValueError):
                            confidence = 0.0
                        if confidence < MIN_CONFIDENCE:
                            continue
                        raw_name = str(item.get("word") or "").strip()
                        if not is_valid_entity(raw_name):
                            continue
                        canonical = resolve_entity(raw_name, entity_type, language)
                        clean = _clean_entity(canonical or raw_name)
                        if clean and clean.casefold() not in {x.casefold() for x in mapped[entity_type]}:
                            mapped[entity_type].append(clean)
                            type_counts[entity_type] += 1
            extracted.append(dict(mapped))
    print("NER training features extracted:", dict(type_counts))
    return extracted
