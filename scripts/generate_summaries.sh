#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_common.sh"
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  echo "Usage: $0 [--force] [--limit N]"
  echo "Persists missing/stale article summaries, merges event bullets, and exports the canonical CSV."
  exit 0
fi
"$PYTHON_BIN" src/backend/summarization/persist_summaries.py "$@"
"$PYTHON_BIN" src/backend/semantic_processing/generate_events.py
"$PYTHON_BIN" src/backend/export/csv_export.py
