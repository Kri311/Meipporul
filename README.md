# Veritas Lens

Veritas Lens is an English and Tamil news aggregation project. It fetches RSS
items, extracts and cleans publisher articles, enriches each article with NER
and multilingual semantic embeddings, clusters related coverage into events,
assigns topics, stores bilingual bullet summaries, and serves event pages with
FastAPI and Next.js.

The current operational pipeline is driven by the scripts in `scripts/` and
`src/backend/scripts/shell/`. The root `REPORT.md` explains the implementation
in more detail. An updated, reproducible workflow diagram is available as
[`flow_chart/veritas_lens_workflow_updated.png`](flow_chart/veritas_lens_workflow_updated.png)
with editable source at
[`flow_chart/build_veritas_lens_diagram_updated.py`](flow_chart/build_veritas_lens_diagram_updated.py).

## Pipeline overview

```text
RSS feeds → article extraction → cleaning/normalization → PostgreSQL
    → bilingual NER → multilingual E5 embeddings → DBSCAN event clustering
    → topic classification → persisted article summaries → event bullet merge
    → CSV/event exports → FastAPI → Next.js
```

PostgreSQL is the live source of truth. `src/backend/data/trafiltura_preprocessed.csv`
is the canonical cleaned/enriched article export. `raw_processed.csv` is an
ingestion/staging export; downstream semantic processing uses the database
records and exports its results back to the canonical CSV.

The application/pipeline schema initializer adds JSON `summary` columns to
existing article and event tables and removes the retired
`articles.semantic_text_hash` column before current ORM workflows run.

## Install and configure

From the repository root:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set the PostgreSQL credentials and database URL in `.env` to match your local
database. The RSS and model scripts load `.env` when run through the project
scripts. Start PostgreSQL before running ingestion, enrichment, or the API.
GPU use depends on installing a PyTorch build compatible with your CUDA driver;
the scripts can fall back to CPU when model code supports it.

## Run the complete one-shot pipeline

```bash
./scripts/run_pipeline.sh
```

This runs RSS fetch → normalization/export → NER → E5 embeddings and DBSCAN →
topic assignment → article/event summary persistence → event and CSV exports.
For a small fetch smoke pass, use `./scripts/run_pipeline.sh --limit 20`.
`--train-ner` is an explicit, longer training path and should only be used
after reviewing the NER labels; it is not needed for ordinary daily refreshes.

To run the recurring RSS and enrichment daemon:

```bash
./scripts/start_daemon.sh
```

The daemon interval defaults to five minutes and can be changed with
`PIPELINE_INTERVAL_MINUTES`. It holds an instance lock so a second loop cannot
run concurrently. To keep only local services in development, use separate
terminals:

```bash
./scripts/start_backend.sh
./scripts/start_frontend.sh
```

The frontend refreshes event data while the page is open; the current client
poll interval is 60 seconds. A user who returns to an event page sees persisted
event data immediately, while a full new RSS/analysis cycle is controlled by
the daemon schedule.

## Models and stages

### RSS ingestion and cleaning

Feed definitions live in `src/backend/config/sources.yaml`. The fetcher
deduplicates items, applies publication freshness rules, extracts publisher
pages with Trafilatura when possible, and falls back to RSS content when page
extraction is unavailable. Shared cleanup in
`src/backend/ingestion/tasks/text_cleaning.py` removes markup, duplicate
headlines, outlet-specific/editor boilerplate, and malformed fragments;
language, body, title, and dateline metadata are normalized before persistence.
Outlet-specific rules also block known Livemint byline/editor blocks.

The exporter rebuilds `trafiltura_preprocessed.csv` from PostgreSQL. Its
current fields include source identity and provenance, title/description,
publication time, language, clean and raw text, topic metadata, NER JSON,
image URL, direct `cluster_id`, the `embedding` vector serialized as JSON,
one source-language `summary` bullet-list column, and English/Tamil
compatibility summary columns. Linked entities remain in PostgreSQL for
pipeline use.

### NER

Runtime inference in `src/backend/ner_pipeline/zero_shot/nlp_pipeline.py`
prefers the local fine-tuned MuRIL checkpoint when it exists and the
configuration enables it; Babelscape multilingual NER is the fallback. The
pipeline adds normalization, gazetteer aliases, and Tamil morphology handling
without restricting NER to a closed list of names. Extracted and linked
entities are stored on article rows and are reused by clustering and topic
classification.

The NER training tools are under `src/backend/ner_pipeline/finetune/` and
`scripts/`. Automatically generated weak labels are not gold labels; manually
reviewed validation data is needed before claiming model-quality metrics.

### Embeddings and event clustering

`intfloat/multilingual-e5-base` produces normalized 768-dimensional vectors
from headline-weighted article representations. The embedding service records
the model and timestamp; text normalization clears stale vectors and model
changes trigger re-embedding.

Event clustering uses cosine-distance DBSCAN over the multilingual E5 space,
so English and Tamil coverage can join the same event. Publication-date guards
prevent stale merges. Typed NER overlap (person, organization, event, date,
and location) can only provide a bounded boost when E5 similarity is already
meaningful. A deterministic complete-link
refinement splits DBSCAN's transitive chains unless every cross-pair stays
within the configured distance threshold. Articles left as noise remain
individual stories rather than being forced into an unrelated event.

Relevant settings include `EMBEDDING_MODEL_NAME`, `EMBEDDING_DEVICE`,
`DBSCAN_EPS`, `DBSCAN_MIN_SAMPLES`, and `CLUSTER_MAX_GAP_DAYS` in `.env`.

### Topic classification

The bilingual topic classifier supports E5 embeddings plus Logistic
Regression, E5+typed-NER feature fusion, and a fine-tuned MuRIL experiment.
`selected.json` determines the supervised runtime model. Fusion is selected
only if its cross-validation improvement passes the configured gain threshold;
multilingual zero-shot and keyword/rule classification provide fallbacks.
Low-confidence or ambiguous supervised predictions map to the `Other`
taxonomy topic. `topic_modeling.py` classifies articles and assigns each event
the majority member topic, using `Other` for ties.

Prepare a 500-row bilingual topic annotation template (250 per language):

```bash
./scripts/prepare_topic_labels.sh \
  --input src/backend/data/trafiltura_preprocessed.csv \
  --output src/backend/data/topic_labels_500_to_annotate.csv \
  --per-language 250
```

Review the `suggested_topic` values into `topic`, then compare E5-only with
E5+NER and save the selected model and evaluation output:

```bash
./scripts/train_topic_classifier.sh src/backend/data/topic_labels_500_to_annotate.csv
```

The trained artifacts and metrics are written under
`src/backend/models/topic_classifier/`. The quality of the model depends on
reviewed labels; suggested labels are weak supervision until corrected.

### Summarisation

`src/backend/summarization/common.py` uses a fine-tuned local LoRA adapter when
available; otherwise it uses `csebuetnlp/mT5_multilingual_XLSum`. It processes
English and Tamil separately, chunks long bodies, checks generated points
against source text, and falls back to extractive source sentences when model
loading, language validation, or grounding fails.

`persist_summaries.py` generates and stores each article's bullets only when
its content or configured model identifier changes. Event bullets are a deterministic, de-duplicated
merge of stored summaries from member articles, so opening an event does not
trigger fresh model generation. Summary JSON and hashes are stored in
PostgreSQL, and bullet columns are included in the canonical CSV export.

Prepare a bilingual human-reviewed summary dataset:

```bash
./scripts/prepare_summary_labels.sh --per-language 250
```

Fill `summary_bullets` with factual English or Tamil bullet points, and use a
shared `event_group` for related articles. Then fine-tune the mT5 base model:

```bash
./scripts/train_summarizer.sh src/backend/data/summary_labels_to_annotate.csv --epochs 3
```

At least 20 reviewed examples per language and independent train/validation
groups are required by the trainer. Fine-tuning is an offline step; normal
pipeline runs do not train models.

To rebuild model-derived values for existing database articles after a model
or schema change, run the explicit full refresh once:

```bash
./scripts/run_pipeline.sh --refresh-existing
```

It reruns NER for every cleaned article, recomputes all E5 embeddings,
reclassifies topics, forces article and event summary regeneration, updates
event `cluster_id` assignments, and exports the resulting database state.
Ordinary runs remain incremental for NER, embeddings, and summaries while
reclustering the stored vector corpus.

## Evaluation

Evaluation scripts and annotation templates are under
`src/backend/evaluation/`. Event clustering requires reviewed article pairs
(`guid_a,guid_b,same_event`). Summarisation requires human reference bullets
for each language. NER scores require a reviewed gold BIO dataset. The
evaluators report metrics only when an answer key exists; auto-annotated data
must be identified as weak supervision, not gold.

See [`src/backend/evaluation/README.md`](src/backend/evaluation/README.md) for
the current annotation formats and metrics.

## Main implementation map

| Stage | Implementation |
|---|---|
| Feed configuration | `src/backend/config/sources.yaml` |
| RSS fetch and page extraction | `src/backend/scripts/fetch_rss_standalone.py` |
| Cleaning/normalization | `src/backend/ingestion/tasks/text_cleaning.py` |
| PostgreSQL schema | `src/backend/models/database.py` |
| NER and entity linking | `src/backend/ner_pipeline/zero_shot/` |
| Embeddings and DBSCAN | `src/backend/semantic_processing/` |
| Topic model and runtime selection | `src/backend/semantic_processing/topic_classifier.py`, `topic_modeling.py` |
| Summary inference and persistence | `src/backend/summarization/` |
| Enriched CSV/event export | `src/backend/export/csv_export.py`, `generate_events.py` |
| Backend API | `src/backend/api.py` |
| Frontend | `src/frontend/` |
| End-to-end scripts | `scripts/`, `src/backend/scripts/shell/` |
