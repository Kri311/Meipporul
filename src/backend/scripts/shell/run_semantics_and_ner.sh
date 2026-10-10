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

# Canonicalize and persist article text first. This resets embeddings/clusters
# only for rows whose body actually changed, so subsequent stages recompute them.
echo "[0/5] Normalizing dated article text before enrichment..."
PYTHONPATH="./src" python src/backend/export/csv_export.py

echo "[1/5] Extracting Named Entities from clean article bodies..."
PYTHONPATH="./src" python src/backend/ner_pipeline/zero_shot/nlp_pipeline.py

echo "[2/5] Generating multilingual semantic embeddings and event clusters..."
PYTHONPATH="./src" python src/backend/semantic_processing/embeddings_and_clustering.py

echo "[3/5] Classifying topics for event clusters..."
PYTHONPATH="./src" python src/backend/semantic_processing/topic_modeling.py

echo "[4/5] Generating Event Representations..."
PYTHONPATH="./src" python src/backend/semantic_processing/generate_events.py

echo "[5/5] Exporting full enriched dataset to CSV..."
PYTHONPATH="./src" python src/backend/export/csv_export.py

echo "Semantics & NER Pipeline Completed Successfully!"
