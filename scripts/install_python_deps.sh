#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
exec "$PYTHON_BIN" -m pip install -r requirements.txt
