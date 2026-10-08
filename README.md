# Veritas Lens

Veritas Lens collects RSS news from the English and Tamil outlets in
src/backend/config/sources.yaml, extracts article pages, groups related
coverage into event timelines, and serves those events through a FastAPI API and
a Next.js interface.

## Article data contract

The live daemon's final export is
src/backend/data/trafiltura_preprocessed.csv. It contains 2026 articles and
the requested fields through `topic`, plus `image_url` for the news-feed cards:

content_hash, guid, outlet_slug, title, description, author, published_at, language, article_length, data_fetch_via, canonical_url, extraction_method, extraction_quality, processing_status, raw_text, clean_text, topic, image_url

- title is the standalone, markup-free headline.
- description remains the RSS/page description; it is not folded into the body.
- raw_text preserves Trafilatura's extracted page text.
- clean_text is valid JSON with one key/value: {"headline":"article body"}.
  JSON serialization safely escapes quotes and newlines. Read it as JSON; do
  not split on quotes or concatenate JSON manually.
- The body is title-deduplicated, boilerplate-cleaned, and kept complete rather
  than cut off with an ellipsis. Tamil rows are kept in Tamil script and common
  political abbreviations are normalized in Tamil. Dateline locations are
  stored in named_entities under LOCATION.
- These exported values are taken from PostgreSQL; the pipeline writes the
  canonical body/title back to PostgreSQL before exporting. `topic` comes from
  the associated event cluster. PostgreSQL also keeps NER and embedding fields
  for downstream processing; they are intentionally not part of this CSV view.

The 2026 reprocessor reads raw_processed.csv, fetches each eligible canonical
URL in batches, skips unavailable/invalid articles and atomically replaces the
output only after successful completion. --batch-size is a checkpoint
interval, not a maximum row count.

## Architecture

- RSS collection and Trafilatura extraction: src/backend/ingestion/ and
  src/backend/scripts/fetch_rss_standalone.py.
- Shared cleanup and JSON parsing: src/backend/ingestion/tasks/text_cleaning.py.
- Historical export: src/backend/scripts/reprocess_articles.py.
- Local cleanup without another fetch: src/backend/scripts/clean_processed_export.py.
- NER: src/backend/ner_pipeline/zero_shot/nlp_pipeline.py.
- Cross-lingual semantic embeddings: src/backend/semantic_processing/embedding_service.py
  (defaults to intfloat/multilingual-e5-base, 768 dimensions to match pgvector).
- Event grouping uses multilingual semantic similarity, a conservative
  entity tie-break, a configurable date-gap boundary (14 days by default), and
  reused event centroids; topics are
  classified after clustering in src/backend/semantic_processing/.
- Bilingual event summaries: event cards use a fast extractive preview; opening
  an event generates a hierarchical abstractive summary from all article bodies
  using csebuetnlp/mT5_multilingual_XLSum, with Tamil and English kept separate.
  The model is lazy-loaded, uses CUDA FP16 when available, and falls back to CPU
  or sentence extraction if inference cannot run. See src/backend/summarization/.
- API: src/backend/api.py; UI: src/frontend/.

Sentence Transformers provide embeddings, not translations. The app therefore
filters event coverage into native English and Tamil lanes and summarizes only
articles written in the selected language. Translation of complete articles is
not part of this pipeline.

## Run the historical data refresh

From the repository root:

```bash
source venv/bin/activate
PYTHONPATH=./src python3 src/backend/scripts/reprocess_articles.py
```

The background wrapper writes progress to logs/reprocess_daemon.log:

```bash
bash src/backend/scripts/shell/start_reprocess_daemon.sh
tail -f logs/reprocess_daemon.log
```

The real-time RSS daemon is separate:

```bash
bash src/backend/scripts/shell/start_daemon.sh
tail -f logs/rss_daemon.log
bash src/backend/scripts/shell/stop_daemon.sh
```

## Backfill images for previously collected articles

Start PostgreSQL first, then fill missing 2026 `image_url` values from RSS/page
metadata and article HTML. The script updates matching database rows and
atomically rewrites only the image column in the processed CSV:

```bash
sudo pg_ctlcluster 16 main start
source venv/bin/activate
PYTHONPATH=./src python src/backend/scripts/backfill_images.py
```

The backfill can take a while because it contacts each publisher page. It is
safe to rerun; rows that already have images are skipped.

## Run services

Start the API from the repository root:

```bash
source venv/bin/activate
PYTHONPATH=./src uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

Ensure PostgreSQL is running before starting the API or daemon.

Start the web application in a second terminal:

```bash
cd src/frontend
bun run dev
```

The API exposes GET /events/?lang=en|ta, GET /events/{id}?lang=en|ta,
and /metadata. Configure the frontend API origin with the environment
settings in src/frontend/src/lib/api.js.

## Fine-tuning and evaluation

Run commands from the repository root. Install the declared Python
dependencies first (Matplotlib is used for the PNG plots):

```bash
source venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=./src python3 src/backend/ner_pipeline/finetune/auto_annotate.py
PYTHONPATH=./src python3 src/backend/ner_pipeline/finetune/train.py
```

NER training writes overall and Tamil/English validation metrics, per-entity
CSV files, and training/language plots under
`src/backend/ner_pipeline/finetune/data/`. Its current train/validation tags
are automatically generated weak labels, so treat the scores as diagnostics,
not as human-gold model quality. Review and correct annotations before using
the scores for a final performance claim.

The NER trainer defaults to micro-batches of 1 with gradient accumulation,
gradient checkpointing, and Adafactor to fit a 5.6GB GPU. This lowers peak
memory at the cost of slower training.

The first event-detail request downloads the summarization checkpoint from
Hugging Face (about 2.3GB); allow network access and disk space for the cache.
It loads lazily, not during API startup. Device selection defaults to `auto`
(CUDA FP16 when available, CPU fallback on memory pressure). To force CPU for
the API process, start it with `SUMMARY_DEVICE=cpu`.

Event clustering uses pretrained embeddings and has no trainable fine-tuning
step. Event summaries are generated automatically with the pretrained bilingual
abstractive summarizer. To evaluate them, first add human-reviewed labels
to `src/backend/evaluation/annotations/event_pairs.csv` and
`src/backend/evaluation/annotations/summaries.csv` (the expected columns and
metric definitions are in `src/backend/evaluation/README.md`), then run:

```bash
PYTHONPATH=./src python3 src/backend/evaluation/evaluate_event_clustering.py
PYTHONPATH=./src python3 src/backend/evaluation/evaluate_summarization.py
```

The clustering evaluator compares same-event pairs with current cluster IDs;
the summarization evaluator compares each language's generated summary with
human references using ROUGE-1/2/L F1 and chrF. Human references are optional
evaluation data only; the app generates summaries automatically. These
evaluators require PostgreSQL to be
running and populated. CSV, JSON, and PNG results are written to
`src/backend/evaluation/results/`. Empty templates intentionally produce no
scores: meaningful event and summary metrics require gold labels/references.

## Start the RSS daemon once

From the repository root, start it once with:

```bash
bash src/backend/scripts/shell/start_daemon.sh
tail -f logs/rss_daemon.log
```

The start lock prevents duplicate launches and the pipeline-instance lock
prevents a second pipeline loop. Output is appended to `rss_daemon.log` once
(the pipeline no longer tees a second copy into the same log). Stop it with:

```bash
bash src/backend/scripts/shell/stop_daemon.sh
```

## Data and operational layout

- Durable code and configuration live under src/backend and src/frontend.
- Supported operational scripts live in src/backend/scripts/ and
  src/backend/scripts/shell/. Prior one-off patchers and manual smoke checks
  are preserved under src/backend/scripts/archive/ and
  src/backend/tests/manual/ rather than cluttering the project root.
- Historical reprocessing artifact (when that separate tool is used):
  src/backend/data/trafiltura_processed.csv.
- RSS source/staging export: src/backend/data/raw_processed.csv.
- Live enriched export: src/backend/data/trafiltura_preprocessed.csv, refreshed
  by the full daemon after ingestion and NER/semantic processing. RSS or page
  Open Graph/Twitter metadata supplies `image_url` where available.
- Daemon and pipeline logs: repository-root logs/.
- Reprocessing uses a sibling .tmp file as a safety checkpoint; the .csv
  appears/replaces only after successful completion.

See the extraction/runbook notes in src/backend/docs/ARTICLE_REPROCESSING.md
for recovery and validation details. Older research and implementation
journals in src/backend/docs/ are historical; this README and the runbook
describe the current intended contract.
