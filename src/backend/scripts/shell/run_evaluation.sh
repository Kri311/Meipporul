#!/bin/bash
cd "$(dirname "$0")/../../../.."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "======================================"
echo "   NER Zero-Shot Evaluation           "
echo "======================================"
echo "Evaluating NER model and appending metrics to evaluation/ner_metrics.csv..."

PYTHONPATH="./src" python src/backend/ner_pipeline/zero_shot/evaluate_zero_shot.py

echo "======================================"
echo "   Evaluation Completed!              "
echo "======================================"
