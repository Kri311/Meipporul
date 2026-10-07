#!/bin/bash
cd "$(dirname "$0")/../../../.."

set -e
echo "======================================"
echo "   [Phase 2] Semantics & NER Pipeline "
echo "======================================"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "[1/5] Running Semantic Processing & Incremental Clustering..."
PYTHONPATH="./src" python src/backend/semantic_processing/embeddings_and_clustering.py

echo "[2/5] Classifying Topics for Clusters..."
PYTHONPATH="./src" python src/backend/semantic_processing/topic_modeling.py

echo "[3/5] Extracting Named Entities (NER)..."
PYTHONPATH="./src" python src/backend/ner_pipeline/zero_shot/nlp_pipeline.py

echo "[4/5] Generating Event Representations..."
PYTHONPATH="./src" python src/backend/semantic_processing/generate_events.py

echo "[5/5] Exporting full enriched dataset to CSV..."
PYTHONPATH="./src" python src/backend/export/csv_export.py

echo "Semantics & NER Pipeline Completed Successfully!"
