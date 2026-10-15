#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
exec "$PYTHON_BIN" src/backend/semantic_processing/embeddings_and_clustering.py "$@"
