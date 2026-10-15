"""
Veritas Lens — Tamil Text Normalization
========================================
Handles punctuation/spacing quirks and morphological suffix stripping
for Tamil entity text. Used by the NER pipeline.
"""

import re


# ---------------------------------------------------------------------------
# Tamil morphological case suffixes
# ---------------------------------------------------------------------------
# These are the CORRECT Unicode forms that actually appear at the end of
# inflected Tamil nouns.  The previous version used independent vowel
# codepoints (e.g. ஐ U+0B90) which never match dependent vowel signs
# (e.g. ை U+0BC8) found in real inflected words.
#
# Ordered longest-first so we always strip the most specific suffix.
# ---------------------------------------------------------------------------
TAMIL_CASE_SUFFIXES = [
    # Ablative / complex forms (longest first)
    "யிலிருந்து",        # -yilirunthu (from)
    "த்திலிருந்து",       # -tthilirunthu (from)
    # Locative
    "த்தில்",            # -tthil (in)
    "களில்",             # -kalil (in, plural)
    "யில்",              # -yil (in)
    "வில்",              # -vil (in)
    # Genitive
    "த்தின்",            # -tthin (of)
    "களின்",             # -kalin (of)
    "யின்",              # -yin (of)
    "வின்",              # -vin (of)
    # Accusative
    "களை",              # -kalai (plural accusative)
    # Plural
    "கள்",              # -kal (plural)
    # Dative
    "க்கு",              # -kku (to/for)
    "யிடம்",             # -yidam (with/at person)
    # Instrumental
    "யால்",              # -yaal (by)
    # Sociative
    "யோடு",             # -yodu (with)
    "யுடன்",             # -yudan (with)
    # Simple postpositions
    "உடன்",             # udan (with)
    "இடம்",              # idam (at/with person)
]


def normalize_entity_text(text: str) -> str:
    """Normalize punctuation and spacing quirks in Tamil entity text.

    Specifically handles variations of Tamil initials:
        மு.க. ஸ்டாலின்  →  மு.க.ஸ்டாலின்
        மு க ஸ்டாலின்   →  மு.க.ஸ்டாலின்
        மு.க.,ஸ்டாலின்  →  மு.க.ஸ்டாலின்
    """
    text = text.strip()

    # Remove comma after dot:  மு.க.,ஸ்டாலின் → மு.க.ஸ்டாலின்
    text = re.sub(r'\.,', '.', text)

    # Normalize space after dot for Tamil initials:
    # மு.க. ஸ்டாலின் → மு.க.ஸ்டாலின்
    text = re.sub(r'([அ-ஹ])\.\s+', r'\1.', text)

    # Single Tamil letter followed by space → add dot:
    # மு க ஸ்டாலின் → மு.க.ஸ்டாலின்
    text = re.sub(r'\b([அ-ஹ])\s+', r'\1.', text)

    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def strip_tamil_morphology(word: str) -> str:
    """Strip common Tamil case-marker suffixes to recover the root word.

    This is a heuristic stemmer for entity matching — not a full
    morphological analyser.  It strips the longest matching suffix
    from ``TAMIL_CASE_SUFFIXES`` while keeping at least 2 characters
    in the result.

    Examples:
        சென்னையில்  →  சென்னை
        மோடியிடம்   →  மோடி
        கோவையிலிருந்து → கோவை
    """
    stripped = word
    for suffix in TAMIL_CASE_SUFFIXES:
        if stripped.endswith(suffix) and len(stripped) - len(suffix) >= 2:
            stripped = stripped[: -len(suffix)]
            break  # strip only the longest matching suffix
    return stripped
