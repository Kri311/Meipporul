#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_common.sh"
"$PYTHON_BIN" src/backend/ner_pipeline/finetune/prepare_data.py
exec "$PYTHON_BIN" src/backend/ner_pipeline/finetune/auto_annotate.py "$@"
