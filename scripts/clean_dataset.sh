#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
exec "$PYTHON_BIN" src/backend/export/csv_export.py "$@"
