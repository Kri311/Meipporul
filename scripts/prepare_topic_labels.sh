#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_common.sh"
"$PYTHON_BIN" -m backend.semantic_processing.topic_classifier --prepare-labels "$@"
