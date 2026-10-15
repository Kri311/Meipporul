#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
DATASET_DIR="src/backend/ner_pipeline/finetune/dataset"
if [[ ! -f "$DATASET_DIR/train.jsonl" || ! -f "$DATASET_DIR/val.jsonl" ]]; then
  echo "NER training data is missing. Run ./scripts/prepare_ner_data.sh first." >&2
  exit 1
fi
exec "$PYTHON_BIN" src/backend/ner_pipeline/finetune/train.py "$@"
