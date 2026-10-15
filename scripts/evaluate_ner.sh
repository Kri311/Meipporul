#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
exec "$PYTHON_BIN" src/backend/ner_pipeline/finetune/evaluate_per_language.py "$@"
