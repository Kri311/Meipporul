#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
"$PYTHON_BIN" - <<'PY'
from backend.semantic_processing.embedding_service import EmbeddingService
from backend.ner_pipeline.zero_shot.nlp_pipeline import get_ner_pipeline
from backend.summarization.common import _load_model as load_summarizer

print("Loading multilingual-e5-base embeddings...")
EmbeddingService()._get_model()
print("Loading configured multilingual NER model...")
get_ner_pipeline()
print("Loading configured mT5 summarizer...")
load_summarizer()
print("All configured models loaded successfully and are cached locally.")
PY
