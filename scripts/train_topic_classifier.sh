#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_common.sh"
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <annotated-labels.csv>" >&2
  echo "Compares E5-only with E5 + NER, tunes on CV, and saves the selected model trained on all rows." >&2
  exit 2
fi
"$PYTHON_BIN" -m backend.semantic_processing.topic_classifier --labels "$1" --e5-ner
