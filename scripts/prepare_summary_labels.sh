#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_common.sh"
exec "$PYTHON_BIN" -m backend.summarization.prepare_training_data "$@"
