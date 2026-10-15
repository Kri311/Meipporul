#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_common.sh"

echo "Re-running NER for every article with cleaned text using the configured model..."
PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
  "$PYTHON_BIN" "$PROJECT_ROOT/src/backend/ner_pipeline/zero_shot/nlp_pipeline.py" --reprocess-all

echo "Rebuilding embeddings, event clusters, topics, summaries, and enriched CSV exports..."
"$PROJECT_ROOT/src/backend/scripts/shell/run_semantics_and_ner.sh"
