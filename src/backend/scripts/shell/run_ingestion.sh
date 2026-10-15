#!/bin/bash
cd "$(dirname "$0")/../../../.."

set -e
echo "======================================"
echo "   [Phase 1] Ingestion Pipeline       "
echo "======================================"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# We run the standalone fetcher which parses RSS, cleans data, and inserts to DB
PYTHONPATH="./src" python src/backend/scripts/fetch_rss_standalone.py

echo "Ingestion completed."
