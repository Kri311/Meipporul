# Veritas Lens — Implementation and Pipeline Report

**Updated:** 11 October 2026

**Scope:** implementation and execution flow represented by the repository
working tree. This report describes the code and pipeline configuration; it
does not claim that all external RSS sources, PostgreSQL services, model
downloads, GPU training, or end-to-end production runs were exercised during
this documentation update.

## 1. Project purpose

Veritas Lens collects English and Tamil news, keeps each article tied to its
publisher and source text, groups related coverage into event pages, assigns a
topic, and presents event summaries as bullet points. The stack is PostgreSQL
with pgvector, Python/SQLAlchemy, FastAPI, and a Next.js frontend.

The core design requirement is provenance: a title, article body, image,
entities, topic, and summary must remain associated with the same source
article/event. The implementation stores article and derived state in
PostgreSQL and exports a canonical CSV for inspection and annotation.

## 2. End-to-end execution order

### One-shot root runner

`scripts/run_pipeline.sh` performs:

1. `scripts/fetch_rss.sh` fetches configured feeds and persists eligible new
   articles.
2. `scripts/clean_dataset.sh` normalizes the article rows and refreshes the
   canonical export.
3. `scripts/run_ner.sh` extracts and links entities on the cleaned article
   text.
4. `scripts/run_semantics.sh` computes missing/stale embeddings and runs
   DBSCAN event clustering.
5. `topic_modeling.py` assigns article topics and majority-vote event topics.
6. `scripts/generate_summaries.sh` creates stale article summaries, merges
   their bullets into event summaries, produces event representations, and
   exports the final canonical CSV.

The optional `--train-ner` flag invokes NER data preparation and training
before the inference stage. Training is intentionally separate from ordinary
pipeline runs because it consumes substantial time and compute and requires
review of its training data.

### Recurring daemon

`scripts/start_daemon.sh` delegates to
`src/backend/scripts/shell/run_full_pipeline.sh`, which repeats ingestion and
the semantics/NER shell flow. Its default interval is five minutes, controlled
by `PIPELINE_INTERVAL_MINUTES`. The frontend independently polls its event
endpoints every 60 seconds while visible. Thus, UI refresh and full data
reprocessing are distinct schedules.

## 3. Feed ingestion and clean article data

### Sources and fetching

The shell pipeline's feed list is configured in
`src/backend/config/sources.yaml`. `fetch_rss_standalone.py` reads the feeds,
normalizes canonical URLs, applies freshness and duplicate checks, fetches
publisher pages for fuller text, and records provenance such as extraction
method and quality. Trafilatura is the primary page extractor; RSS description
or content provides a fallback when page extraction is unavailable. Feed
metadata supplies publication time, outlet, language hint, title, URL, images,
and a source description.

Freshness and exclusions are configurable in code/environment and source
cleaners. Duplicate identities include feed/article identifiers, content, and
canonical URLs. The exact age cutoff depends on active settings; archived
articles already in PostgreSQL are not deleted merely because they age out of
the fetch window.

### Cleanup, normalization, and export

Shared cleanup is implemented in
`src/backend/ingestion/tasks/text_cleaning.py` and is reused during feed
ingestion and CSV normalization. It handles HTML/entity decoding, whitespace,
title duplication, outlet-specific boilerplate, invalid/editor material,
language-sensitive text cleanup, and dateline extraction. Livemint byline and
editor metadata is removed through its outlet cleaner. Clean text is serialized
as a JSON object with headline and body, so punctuation and line breaks are
escaped safely rather than split manually.

PostgreSQL is the live source of truth. `csv_export.py` writes
`src/backend/data/trafiltura_preprocessed.csv` from stored records after
normalizing canonical text. The canonical export includes article provenance,
raw/clean text, topic/confidence/model, named entities, image URL, direct
`cluster_id`, an `embedding` column serialized as a JSON vector, a
source-language bullet-list `summary` column, and English/Tamil compatibility
summary columns. The database additionally keeps linked entities and
per-article/per-event summary hashes and timestamps. `raw_processed.csv`
remains an ingestion/staging export.

`init_db()` adds the `summary` JSON columns to existing article and event
tables and drops the retired `articles.semantic_text_hash` column. It runs
from ingestion/export/API startup paths so legacy databases are upgraded
before current ORM reads or writes use the schema. Existing article and event
bullets remain available in their language-specific compatibility fields and
are copied into the unified `summary` columns by summary persistence.

When normalization changes an article body, derived features that depend on
the prior content are invalidated so NER, embeddings, clustering, and summaries
can be refreshed rather than silently reused.

## 4. NER and entity normalization

`src/backend/ner_pipeline/zero_shot/nlp_pipeline.py` processes cleaned article
content and persists `named_entities` and `linked_entities`. It prefers the
local MuRIL checkpoint at `src/backend/ner_pipeline/finetune/model/best` when
the configuration enables it and the checkpoint exists; otherwise it uses
`Babelscape/wikineural-multilingual-ner`. The environment can explicitly
select the inference model and configure whether teacher fallback is allowed.

The NER pipeline includes confidence filtering, gazetteer/alias normalization,
Tamil morphology handling, and entity linking. Gazetteers improve recall and
normalize known mentions; they do not define a closed vocabulary, so the
transformer can detect names outside the listed entries. Entity types used by
downstream clustering include PERSON, ORGANIZATION, LOCATION, EVENT, and DATE
(with common label aliases normalized).

The MuRIL training path is implemented under
`src/backend/ner_pipeline/finetune/`. Automated or gazetteer-assisted BIO
labels are weak supervision. Scores from these labels are diagnostics and
should not be presented as gold-standard quality. Reliable precision, recall,
and F1 require a separately reviewed gold validation set.

## 5. Semantic embeddings and event clustering

### Embeddings

`embedding_service.py` uses `intfloat/multilingual-e5-base` and creates
normalized 768-dimensional vectors. The semantic input separates headline
from body and weights the headline more heavily so long article bodies do not
drown out the event identity. Long bodies are chunked before aggregation. Each
article stores its embedding, model name, and embedding timestamp. Text
normalization clears the vector when title/body input changes, and a model-name
mismatch triggers re-embedding. No separate semantic text hash is used.

### DBSCAN and NER corroboration

`clustering_service.py` uses DBSCAN with a precomputed cosine-distance matrix
over multilingual E5 vectors, allowing English and Tamil articles about the
same event to cluster together. It applies a publication-date guard before
clustering. Shared NER entities can reduce pair distance only by a bounded
amount and only when the E5 vectors are already sufficiently close, so shared
names alone cannot make unrelated events merge.

DBSCAN connects points transitively, which can produce a chain in which the
endpoints are not actually similar. A deterministic complete-link refinement
splits candidate clusters unless every cross-pair remains within the same
distance threshold and time span. Size limits are applied, and groups with
fewer than two stories remain noise instead of being published as multi-source
events. Current environment defaults include `DBSCAN_EPS=0.20`,
`DBSCAN_MIN_SAMPLES=2`, and a five-day maximum cluster gap; these are tunable
starting points, not universally optimal thresholds.

Run parameters and cluster assignments are saved in database tables. Event
identity reuse reduces ID churn between full-corpus runs; it is based on
semantic centroids, so manual same-event/different-event pair evaluation is
still needed to validate event quality.

## 6. Topic classification

`topic_classifier.py` implements supervised topic choices based on E5
embeddings and Logistic Regression, with an optional typed-NER feature fusion
experiment. It also supports the MuRIL sequence-classification experiment.
`selected.json` selects the supervised runtime artifact; the runtime falls
back to multilingual zero-shot classification if the selected artifact is
missing or cannot load, then to bilingual topic rules if model inference is
unavailable. Low-confidence or ambiguous supervised predictions map to the
`other_current_affairs` topic. `topic_modeling.py` stores article topics and
assigns event topics by member-article majority; tied events go to `Other`.

The E5+NER experiment chooses fusion only when its cross-validation macro-F1
gain passes a configured minimum. The saved results in the working tree
currently select E5-only because the observed fusion gain did not exceed that
gate. This is a conservative selection result, not evidence that NER can never
help. Suggested labels in generated annotation sheets are weak labels until
human reviewed; classifier metrics should be interpreted with that limitation.

## 7. Summarisation and persistence

### Model path

`common.py` uses a local fine-tuned mT5 LoRA adapter when available and
preferred. Without it, the base model is
`csebuetnlp/mT5_multilingual_XLSum`. It generates in the source language,
chunks long article bodies, checks language and source support, de-duplicates
candidate bullets, and uses source-sentence extraction if generation fails or
does not produce a sufficiently grounded result. It supports CUDA where
available and retries CPU when CUDA loading fails. Model weights load lazily
when the persistence job first needs inference.

### Precompute and serve

`persist_summaries.py` generates an article's bullet summary when its content
or configured model identifier changes and stores it in the article `summary`
column as well as the language-specific compatibility field. It summarizes
articles independently to preserve the article/source relationship. It then
builds separate English and Tamil event summaries by merging stored member
article bullets in deterministic order and removing redundant points. Event
summary hashes change when member summary hashes or bullets change. The
event-level `summary` JSON stores both language arrays (`en` and `ta`), while
the article-level `summary` JSON stores that article's source-language bullets.
The event page/API can therefore serve stored bullets without running a model
each time a reader opens an event.

Fine-tuning uses reviewed English and Tamil article-to-bullet examples. The
preparation script writes `summary_labels_to_annotate.csv`; the trainer checks
for both languages and independent train/validation groups, uses LoRA and
gradient checkpointing, and saves model metadata and adapter files under
`src/backend/models/summarizer/best`. A fine-tuned artifact is not created
until that reviewed data and training command are run. Use `--force` after
replacing weights in place without changing the configured model path.

## 8. Topic, summary, and exports order

Topics are computed after NER and clustering because classification can use
article entities and event topics use member votes. Summaries are generated
after the article set and clusters are known. Event summaries are then merged
from article summaries. `generate_events.py` writes the event representation,
and the final `csv_export.py` refreshes the canonical article export with the
persisted topic and bullet fields.

This is the intended dependency order:

```text
clean text → NER → embeddings → DBSCAN → topic labels → article bullets
          → event bullet merge → event representation + canonical CSV
```

## 9. API and web application

FastAPI is implemented in `src/backend/api.py` and reads from PostgreSQL. It
serves event lists, event details, article/source metadata, images, topic
fields, and persisted summary bullets. The Next.js application under
`src/frontend/` renders English and Tamil event feeds and event detail pages.
The client refreshes visible event data every 60 seconds; this refresh does
not itself rerun RSS parsing or model inference.

Use `scripts/start_backend.sh` and `scripts/start_frontend.sh` for local
development. PostgreSQL must be reachable by the configured connection before
the backend or data pipeline can use it.

## 10. Operational commands

Install Python dependencies and configure `.env` first. The main commands,
from the repository root, are:

```bash
# Complete RSS-to-export one-shot pipeline
./scripts/run_pipeline.sh

# One-time full refresh for every existing database article
./scripts/run_pipeline.sh --refresh-existing

# Recurring RSS + enrichment daemon
./scripts/start_daemon.sh

# Persist summaries, merge event bullets, and refresh event/CSV exports
./scripts/generate_summaries.sh

# Prepare/review 500 topic labels, then compare E5 against E5+NER
./scripts/prepare_topic_labels.sh \
  --input src/backend/data/trafiltura_preprocessed.csv \
  --output src/backend/data/topic_labels_500_to_annotate.csv --per-language 250
./scripts/train_topic_classifier.sh src/backend/data/topic_labels_500_to_annotate.csv

# Prepare/review bilingual summary bullets and fine-tune mT5
./scripts/prepare_summary_labels.sh --per-language 250
./scripts/train_summarizer.sh src/backend/data/summary_labels_to_annotate.csv --epochs 3

# Local API and UI in separate terminals
./scripts/start_backend.sh
./scripts/start_frontend.sh
```

`requirements.txt` contains the runtime and training dependencies, including
PyTorch 2.6+ for safe checkpoint loading and PEFT for LoRA summariser training.
The full refresh re-runs NER, all embeddings, and all summaries, so it is a
longer, resource-heavy backfill; ordinary pipeline runs are incremental for
those per-article stages. GPU availability depends on the installed
PyTorch/CUDA build and free VRAM.

## 11. Evaluation and known limitations

Evaluation scripts live in `src/backend/evaluation/`. Event-clustering
precision/recall/F1 requires human same-event pair labels. Summarisation
comparison requires human reference summaries per language. NER precision,
recall, and F1 require reviewed gold BIO spans. Topic classification should be
evaluated on reviewed labels with language-separated scores. Weakly generated
labels can support experimentation, but their metrics do not establish
real-world quality.

The current pipeline does not automatically create human annotations or train
models on every RSS cycle. It uses the selected or fallback runtime models and
recomputes only stale/missing derived content where supported. RSS publishers
can change page structures, article availability, and image metadata, so
extraction quality remains source dependent. DBSCAN thresholds need to be
calibrated against a representative, manually labeled event-pair set.

## 12. Reproducible flow chart

Regenerate the updated picture and SVG from the Python source with:

```bash
python flow_chart/build_veritas_lens_diagram_updated.py
```

The source is the editable artifact; the PNG is the shareable rendering. The
diagram follows the visual styling of `flow_chart/flow_chart_template.jpeg`
and shows the online pipeline plus optional offline model training branches.
