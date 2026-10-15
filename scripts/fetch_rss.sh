#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
exec "$PYTHON_BIN" src/backend/scripts/fetch_rss_standalone.py "$@"
