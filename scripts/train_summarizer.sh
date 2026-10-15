#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_common.sh"
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  echo "Usage: $0 <reviewed-summary-labels.csv> [--epochs N] [--validation-fraction F] [--overwrite]"
  echo "CSV columns: article_id, language, title, body, summary_bullets; event_group is optional."
  exit 0
fi
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <reviewed-summary-labels.csv> [--epochs N] [--overwrite]" >&2
  echo "The CSV needs language, title, body, article_id, and summary_bullets columns." >&2
  exit 2
fi
LABELS_CSV="$1"
shift
exec "$PYTHON_BIN" -m backend.summarization.train --labels "$LABELS_CSV" "$@"
