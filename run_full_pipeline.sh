#!/bin/bash
set -e

echo "======================================"
echo "   Veritas Lens - Full Pipeline       "
echo "======================================"

echo "[1/4] Fetching latest RSS into PostgreSQL..."
# Using the patched fetch_rss_standalone.py
venv/bin/python3 fetch_rss_standalone.py

echo "[2/4] Running Semantic Processing & Incremental Clustering..."
venv/bin/python3 embeddings/pipeline.py

echo "[3/4] Classifying Topics for Clusters..."
venv/bin/python3 scripts/utils/classify_clusters.py

echo "[4/4] Exporting to CSV..."
venv/bin/python3 scripts/utils/export_csv.py

echo "======================================"
echo "Pipeline Completed Successfully!"
