#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_common.sh"

TRAIN_NER=0
REFRESH_EXISTING=0
FETCH_ARGS=()
while (($#)); do
  case "$1" in
    --train-ner)
      TRAIN_NER=1
      shift
      ;;
    --refresh-existing)
      REFRESH_EXISTING=1
      shift
      ;;
    --limit)
      if (($# < 2)); then
        echo "--limit requires a number" >&2
        exit 2
      fi
      FETCH_ARGS+=(--limit "$2")
      shift 2
      ;;
    -h|--help)
      echo "Usage: ./scripts/run_pipeline.sh [--limit N] [--train-ner] [--refresh-existing]"
      echo "--train-ner prepares weak annotations from the canonical CSV and fine-tunes MuRIL before NER inference."
      echo "--refresh-existing reruns NER, all embeddings, topics, and summaries for existing database articles."
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: ./scripts/run_pipeline.sh [--limit N] [--train-ner] [--refresh-existing]" >&2
      exit 2
      ;;
  esac
done

"$PROJECT_ROOT/scripts/fetch_rss.sh" "${FETCH_ARGS[@]}"
"$PROJECT_ROOT/scripts/clean_dataset.sh"
if (( TRAIN_NER )); then
  "$PROJECT_ROOT/scripts/prepare_ner_data.sh"
  "$PROJECT_ROOT/scripts/train_ner.sh"
fi
if (( REFRESH_EXISTING )); then
  "$PROJECT_ROOT/scripts/run_ner.sh" --reprocess-all
  "$PROJECT_ROOT/scripts/run_semantics.sh" --reembed-all
else
  "$PROJECT_ROOT/scripts/run_ner.sh"
  "$PROJECT_ROOT/scripts/run_semantics.sh"
fi
"$PYTHON_BIN" src/backend/semantic_processing/topic_modeling.py
if (( REFRESH_EXISTING )); then
  "$PROJECT_ROOT/scripts/generate_summaries.sh" --force
else
  "$PROJECT_ROOT/scripts/generate_summaries.sh"
fi
