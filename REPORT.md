# Veritas Lens — Implementation Report

**Review scope:** repository source, configuration, scripts, schemas, and frontend as present in the working tree on 8 October 2026. This report describes code behavior; it does not claim that feeds, database services, model downloads, or production deployment were exercised during this review.

## 1. Project overview

Veritas Lens is a bilingual English/Tamil news aggregation and event-context application. Its principal flow is:

1. Read enabled publisher RSS feeds.
2. Normalize feed metadata and canonical URLs, filter unwanted items, then extract article text from the publisher page (Trafilatura) or RSS payload.
3. Clean and validate article content; persist articles and export CSV snapshots.
4. Run entity extraction and entity linking over article bodies.
5. Generate multilingual sentence embeddings and cluster semantically related articles into events.
6. Assign a topic to each event, aggregate event metadata, and serve a bilingual event feed and detail pages through FastAPI and Next.js.

The strongest implemented feature is an end-to-end batch event pipeline combining ingestion, script-aware text cleanup, NER, entity linking, embeddings, clustering, summaries, API, and UI. Topic assignment and article filtering are mostly keyword/rule based. The repository also contains older/alternate ingestion and NER/training paths, so not every script represents the currently invoked production-like flow.

## 2. Repository map and execution paths

### Main modules

| Area | Main implementation |
|---|---|
| Feed collection and extraction | `src/backend/scripts/fetch_rss_standalone.py`; shared worker alternative in `src/backend/ingestion/tasks/fetch_feed.py` |
| Shared text processing | `src/backend/ingestion/tasks/text_cleaning.py` |
| Persistence | `src/backend/models/database.py` (SQLAlchemy + PostgreSQL + pgvector) |
| NER and entity linking | `src/backend/ner_pipeline/zero_shot/nlp_pipeline.py`, `entity_linker.py`, `normalization.py` |
| Embeddings | `src/backend/semantic_processing/embedding_service.py` |
| Event clustering | `src/backend/semantic_processing/clustering_service.py` |
| Topic and event export | `topic_modeling.py`, `generate_events.py`, `export/csv_export.py` |
| Summaries and API | `src/backend/summarization/`, `src/backend/api.py` |
| Web UI | `src/frontend/src/app/`, `src/frontend/src/components/` |
| Operational scripts | `src/backend/scripts/shell/` |
| NER development/training | `src/backend/ner_pipeline/finetune/` |
| Evaluation | `src/backend/evaluation/`, `evaluation/` |

### The invoked batch daemon

`start_daemon.sh` launches `run_full_pipeline.sh`, which holds an instance lock and repeats every 15 minutes. Each cycle calls:

1. `run_ingestion.sh` → `fetch_rss_standalone.py`
2. `run_semantics_and_ner.sh` → canonicalize/export text, NER, embeddings + DBSCAN clustering, topic classification, event CSV, final enriched CSV

The shell scripts are the clearest description of the current intended local workflow. The fetcher uses PostgreSQL for persisted data and deduplication; it is not database-free in this invocation despite the standalone fetcher's historical docstring describing operation without PostgreSQL.

### Alternate Celery path

`src/backend/ingestion/main.py` configures Celery with Redis, a 5-minute RSS dispatch task, and a 2-minute embedding task. `src/backend/main.py` initializes the database and starts the Celery worker and beat scheduler. The Celery feed task is `ingestion/tasks/fetch_feed.py`; it shares cleaning functions but has a separate feed processing implementation. The RSS task's docstring says it uses RSS when content is long enough, but current code enters the page-fetch branch unconditionally (`if True`). Celery's embedding task embeds pending articles but does not invoke the full event, NER, topic, or export sequence.

This is a separate execution path from the 15-minute shell daemon, not a component called by it. Avoid running both modes at once unless duplicate ingestion and differing output state have been intentionally addressed.

## 3. Source configuration

Two YAML files are present:

- `src/backend/config/sources.yaml` is read by `fetch_rss_standalone.py` and is the feed set used by the shell daemon.
- `src/backend/ingestion/config/sources.yaml` is read by Celery's `load_sources_to_db()` at worker setup.

They define publisher slug/name, language, homepage, RSS URL(s), enabled status, orientation bucket/confidence, interval/rate-limit metadata, and category. Enabled examples include The Hindu, NDTV, BBC Tamil, Times of India, Dinamani, Indian Express, One India Tamil, MyKhel Tamil, News18 (English and Tamil), Republic, Vikatan, ABP Nadu, Hindustan Times, and Livemint. Asianet and Google News entries are disabled in the shown source config. Exact active counts depend on which YAML file is used.

The standalone fetcher honors `enabled`, RSS URLs, outlet slug/name, and language only as source metadata; it detects actual language from article text. Several fields (`fetch_interval_minutes`, `rate_limit_per_minute`, `category`, `topic_override`, and orientation) are stored or declared but are not applied as per-feed scheduling/throttling/topic overrides in the standalone loop. The Celery scheduler dispatches all enabled feeds at its global schedule rather than each feed's interval. Celery sync creates or updates outlets and inserts missing feed rows, but does not visibly delete stale rows or update existing feed attributes comprehensively.

The duplicate YAML files create configuration drift risk. The standalone script reads `backend/config/sources.yaml`; Celery reads `backend/ingestion/config/sources.yaml`. Changes need to be kept aligned or consolidated.

## 4. RSS ingestion and article extraction

`fetch_rss_standalone.py` loads existing `(outlet, GUID)`, `(outlet, content hash)`, and `(outlet, canonical URL)` identities from both PostgreSQL and `src/backend/data/raw_processed.csv`. For each enabled source/feed it:

1. Parses the feed with `feedparser` and skips invalid feeds with no entries.
2. Skips missing/repeated GUIDs and matching content hashes or URLs.
3. Filters based on title/URL keyword rules, including entertainment, astrology, lifestyle, recruitment, technology/e-commerce, and media-only content. Festival stories are excluded unless their title or URL contains a configured breaking-news term.
4. Parses publication dates and accepts items published in the configurable rolling freshness window (seven days by default, using Asia/Kolkata calendar dates). Undated, future-dated, and stale feed entries are skipped; stored historical articles remain in the archive.
5. Resolves canonical URLs by removing `utm_*` and `fbclid` query parameters and attempting to follow Google News RSS redirects with a HEAD request.
6. Fetches the publisher page with a browser-like user agent and a 10-second timeout. It always attempts extraction; Trafilatura is called with `favor_recall=True`, comments and tables disabled. If extraction fails, it falls back to cleaned RSS content.
7. Finds image metadata from publisher Open Graph/Twitter tags, article images, or RSS media fields (the worker path has its own image extraction implementation).
8. Requires at least 200 characters of cleaned text in the standalone fetcher, then applies outlet rules, dateline extraction, title deduplication, language detection, and another body quality check.
9. Computes a SHA-256 content hash; classifies article length as short (<250 words), medium (<800), or long; builds a description from RSS description or body lead; formats `clean_text` as a JSON object containing title and body.
10. Saves article records to PostgreSQL in a batch, then appends successful rows to `raw_processed.csv`.

The fetcher's dedupe keys are scoped by outlet, so identical syndication across different outlets is retained. The database schema makes GUID globally unique, which can conflict if publishers reuse a GUID across outlets. The database commit occurs before CSV append; a CSV write failure can therefore leave persisted articles absent from that CSV until a later database export.

Extraction method and quality are recorded (`trafilatura`, nominal quality 0.9; RSS fallback, 0.5). These values are fixed heuristics, not measured extraction confidence. A successful HTTP 200 does not guarantee Trafilatura extracted a complete article. FeedRun telemetry exists only in the Celery path.

## 5. Cleaning and normalization

`text_cleaning.py` is shared by the fetcher, reprocessor, exporter, and semantic code. The implemented cleanup stages are:

- **HTML and entities:** HTML-unescape and BeautifulSoup text extraction; clean title markup/control spacing.
- **Boilerplate removal:** broad regex and line rules remove paywalls, login/subscription prompts, cookie banners, newsletter/app prompts, navigation, related-story labels, social links, advertisements, author/footer clutter, and Tamil equivalents. Very short non-Tamil lines without sentence punctuation are treated as likely UI fragments. Unsupported scripts/symbols are stripped to ASCII plus the Tamil Unicode block.
- **Publisher-specific cleanup:** cleaners for outlets such as Times of India, BBC Tamil, Dinamani, Indian Express, One India, News18, and MyKhel.
- **Datelines and locations:** recognize common English/Tamil location prefixes, remove them from prose, and preserve the location as a LOCATION entity. Some footer location patterns are also recognized.
- **Headline duplication:** compare the opening body line/token sequence with the headline and remove repeated headlines while preserving any remainder.
- **Language handling:** count Tamil-script characters relative to Latin/Tamil alphabetic characters; `>=35%` Tamil yields `ta`, otherwise `en`. Sentence filtering can remove lines dominated by the other script. This is a heuristic and may misclassify mixed-language stories or Latin transliterations.
- **Political aliases:** normalize party acronyms and Tamil aliases to consistent forms, while keeping Tamil articles in Tamil script.
- **Final formatting:** collapse whitespace/newlines into a continuous body, strip stray leading punctuation and trailing ellipsis/teaser markers, normalize `Rs` spelling, and serialize as `{"headline":"article body"}` with JSON escaping.
- **Quality/topic rules:** reject short or otherwise unusable bodies. `classify_topic` scores keyword matches in title/body across politics, world news, economy, science/health, sports, crime/law, education, technology, and local news, then defaults to general.

`format_clean_article()` and `parse_clean_article()` establish and read the canonical JSON contract. Older plain-text records are accepted. The downstream embedding and summary code parses the JSON instead of embedding or summarizing the JSON syntax itself.

The exact rule inventory is extensive and publisher-sensitive; it is heuristic, not a learned boilerplate detector. Overbroad patterns can remove legitimate prose, and new publishers may need additional rules.

## 6. Database and data products

`database.py` defines `outlets`, `rss_feeds`, `feed_runs`, `articles`, `news_clusters`, `clustering_runs`, and `article_clusters`. PostgreSQL's `vector` extension is enabled at initialization. Article rows store source metadata, raw/clean text, content and semantic hashes, extraction metadata, NER/linking JSON, 768-dimensional vector, model/timestamps, processing status, and a direct event cluster ID. Cluster run and article-cluster tables preserve run parameters and similarity scores; the direct article foreign key supports current API queries.

Environment config is limited: `DATABASE_URL` overrides the local default in `database.py`; `.env.example` contains database identity placeholders but the shown source does not load that file automatically. `setup_local_infra.sh` installs PostgreSQL 16, pgvector, and Redis, and creates a local database/user. `requirements.txt` lists Python dependencies including feedparser, Trafilatura, SQLAlchemy, pgvector, FastAPI-related Pydantic, Transformers, Sentence Transformers, Torch, and evaluation dependencies.

Key data products:

- `src/backend/data/raw_processed.csv`: staging/live export with model and entity fields.
- `src/backend/data/trafiltura_preprocessed.csv`: canonicalized article export, with headline/body JSON and image URL. Despite the name, this is not raw Trafilatura output; it is normalized data from PostgreSQL.
- `src/backend/data/events_representation.csv`: aggregated event rows produced from database clusters and entities.
- `logs/`: daemon and pipeline logs.

`csv_export.py` normalizes all dated rows before writing the final export. If the canonical body/title changed, it clears the embedding, semantic hash, and direct cluster assignment so derived features can be rebuilt. It persists changes before export and uses a sibling `.tmp` file plus atomic replace for each CSV. Article rows with missing/short bodies are omitted from the canonical export.

## 7. Named entity recognition and entity linking

The invoked NER pipeline is `zero_shot/nlp_pipeline.py` (the directory name is historical; this is a transformer-based pipeline). It loads the local fine-tuned model under `ner_pipeline/finetune/model/best` if that directory exists, otherwise defaults to `Babelscape/wikineural-multilingual-ner`; `NER_MODEL_NAME` can override selection. Batch size defaults to 16. By default it processes all body sentences (`NER_MAX_SENTENCES=0`).

For each selected article, it parses cleaned JSON body text, normalizes/splits it into sentences, runs a Hugging Face token-classification pipeline, maps recognized PER/ORG/LOC/EVENT tags into PERSON/ORGANIZATION/LOCATION/EVENT, validates and resolves results with script-aware alias/gazetteer/context rules, and adds date matches from regex. Dateline LOCATION values already stored at ingestion are retained. It writes `named_entities`, derives `linked_entities`, and marks the article completed.

Entity linking uses a local `knowledge_graph.json`, not a live Wikidata lookup. It maps known names/aliases to a stored Q-ID and canonical English/Tamil names; unknown entities are retained with null `kg_id`. The `gazetteer.json` and normalization helpers support alias lookup and Tamil suffix/initial normalization. Entity linking thus supports cross-language identity for the finite local knowledge graph, while general unseen names are not translated or resolved.

The NER batch query currently includes `eligible`, `extracted`, `pending`, and `embedded` rows. It does not select only rows missing entities, so subsequent invocations can rerun NER over prior rows. The line `lang = article.language ... else "ta"` defaults unknown languages to Tamil. The date regex shown recognizes numeric dates and English month names, not a broad set of Tamil date expressions.

### Fine-tuning path

`ner_pipeline/finetune/` contains MuRIL (`google/muril-base-cased`) data preparation, automatic weak annotation, training, prediction, and per-language evaluation utilities. Config defines entity labels, training parameters, gazetteers, and political/government/location rules. Existing dataset files and model checkpoints are present. Auto-annotation uses gazetteer/context/date rules and may incorporate model predictions. Since labels are automatically generated, resulting training/evaluation scores are diagnostics rather than gold-standard quality claims. The currently invoked runtime NER code prefers this local model whenever the `model/best` directory exists.

## 8. Embeddings and semantic representation

`EmbeddingService` defaults to `intfloat/multilingual-e5-base` (768 dimensions, matching `Vector(768)`), loads lazily on CUDA when available or CPU otherwise, and supports `EMBEDDING_MODEL_NAME` and `EMBEDDING_BATCH_SIZE` settings. It builds the source-language E5 passage `passage: headline body` after parsing the stored JSON text. Long inputs are chunked at sentence/word boundaries around 1,800 characters. The service encodes normalized chunks, averages their vectors, and L2-normalizes the result.

The service computes a SHA-256 semantic-text hash and compares it with the stored hash to avoid embedding unchanged content. Changed articles receive the vector, model name, creation time, and `embedded` processing status. The scheduled Celery adapter processes up to 50 changed articles; the shell pipeline calls the standalone service without that cap. E5 passage prefixes and a shared multilingual model enable cross-language semantic comparison in principle; embeddings do not translate text and should not be described as translations.

## 9. Event clustering and semantics

`ClusteringService` runs DBSCAN over cosine distances by default, with `DBSCAN_EPS=0.11` and `DBSCAN_MIN_SAMPLES=2`. An agglomerative option exists (`AGGLO_DISTANCE_THRESHOLD=0.15`) but `run_all()` currently invokes only DBSCAN and returns no agglomerative result.

Before DBSCAN, pairwise distances are modified by hard guards and a small entity tie-break:

- Cross-language pairs are assigned distance 1, so Tamil and English articles are not merged into one cluster.
- Pairs more than `CLUSTER_MAX_GAP_DAYS` (default 14) apart are assigned distance 1.
- Shared linked/named PERSON or ORG entities can lower already-close semantic distance by 0.02 when the original cosine distance is at most 0.20. Location-only overlap is deliberately ignored. Shared names do not independently cause a merge.
- DBSCAN results are split to control chained clusters by time span (14 days), max size (default 50), minimum centroid cohesion (default 0.82), and minimum similarity between every pair in an emitted group (default 0.88). Groups of one are left as noise/unclustered. The pairwise check specifically guards against A↔B↔C chaining where A and C are different stories.

Each run records algorithm/model/parameters/counts. Article-to-cluster membership and cosine-to-centroid similarity are stored. The service calculates normalized centroids and reuses an existing event row if a new centroid similarity exceeds 0.90, helping preserve event IDs across full-corpus reruns without reusing IDs for merely adjacent semantic topics. Stale direct cluster IDs are cleared first; unused prior clusters are retained but their article count is set to zero. Cluster topic is filled in a subsequent keyword-classification step.

Clustering is therefore semantic similarity with language/time constraints and entity-aware tie-breaking, not a general-purpose topic model. The 14-day gap is enforced pairwise and again during splitting. Pairwise distance construction is quadratic in article count, and the current implementation runs over all embedded articles.

## 10. Topics and event representation

Article topic inference uses deterministic keyword scores. `topic_modeling.py` recomputes a cluster topic using its representative title plus up to three article bodies. The source YAML's `topic_override` is not wired into the shown classification call. `generate_events.py` exports cluster date range, representative headline, most frequent location, linked people and organizations, topic, article count, and outlet slugs. It uses linked canonical entities when present and falls back to raw NER values for older records.

The API can also infer a missing topic from sample article text for display. Topic labels have Tamil translations in `api.py`. This is not an embedding-trained topic model despite the module's semantic-processing placement.

## 11. Summarization

Event-card previews use extractive selection of distinct, reasonably long source sentences, sorted by a simple length score. Event detail uses the lazy-loaded `csebuetnlp/mT5_multilingual_XLSum` sequence-to-sequence model. The implementation chunks tokenized article text into overlapping windows, summarizes each window, recursively reduces summaries, caps output at five bullets, and caches successful outputs in a bounded in-memory LRU-like cache. It attempts to keep output in the requested language; if inference fails or output appears to be in the wrong language, it falls back to source sentences. CUDA FP16 is used when available; CUDA out-of-memory triggers a CPU retry.

English and Tamil items are fetched and summarized in separate language lanes. The UI summary is therefore same-language source coverage, not a translation of the other language's reports. Model-generated output is not guaranteed to be fact-perfect; evaluation scripts compare against human references when provided.

## 12. API and frontend

FastAPI exposes:

- `GET /events/?lang=en|ta`: filters dated articles for a language, groups clustered articles, and exposes unclustered articles as temporary singleton events. Results are sorted newest-first, so current-day coverage appears before older archive news. Unclustered IDs use negative article IDs to avoid collision with cluster IDs.
- `GET /events/{id}?lang=en|ta`: returns event metadata, detail summary, articles, source/article counts, topic tags, images, and merged entity groups.
- `GET /metadata`: reports model names and a pipeline version/status string.

The detail endpoint collects named and linked entities into people, organizations, locations, events, and dates. CORS is currently open to all origins. The endpoint currently returns `{"error":"not found"}` as a normal response object rather than an explicit HTTP 404. UI API origin configuration is in `src/frontend/src/lib/api.js`.

The Next.js app uses React, has an English/Tamil language switcher, event cards/list page, and event detail timeline with source links, dates, images, summaries, topics, reading time, and entity chips. The home page refreshes the event list every five minutes, and its API fetch is uncached, so an open tab picks up newly ingested items. The frontend README and components provide additional setup/design information. It is a consumer UI, not an editing or annotation interface.

## 13. Evaluation and testing assets

The repository includes tests for pipeline, semantic processing, integrity, summarization, topic/quality, and clustering guards. Evaluation modules cover event clustering and summaries; the zero-shot NER evaluator and fine-tuning evaluation scripts also exist. Event-clustering evaluation compares annotated same-event pairs to stored cluster assignments. Summarization evaluation computes ROUGE-1/2/L F1 and chrF against human references. The included annotations/results are project artifacts and may be incomplete; only human-reviewed labels support meaningful claims about quality. Existing PNG/JSON clustering outputs are prior results, not proof that the current working-tree code was rerun.

Tests were not run as part of this source review.

## 14. Configuration and operational controls

Main environment-driven settings found in code include:

| Setting | Default / effect |
|---|---|
| `DATABASE_URL` | Local PostgreSQL connection in `database.py` |
| `REDIS_URL` | `redis://localhost:6379/0` for Celery |
| `EMBEDDING_MODEL_NAME` | `intfloat/multilingual-e5-base` |
| `EMBEDDING_BATCH_SIZE` | 32 encoded chunks/items per model batch |
| `DBSCAN_EPS` / `DBSCAN_MIN_SAMPLES` | 0.11 / 2 |
| `CLUSTER_MAX_GAP_DAYS` | 14 |
| `CLUSTER_MAX_ARTICLES` | 50 |
| `CLUSTER_MIN_CENTROID_SIMILARITY` | 0.82 |
| `CLUSTER_MIN_PAIRWISE_SIMILARITY` | 0.88; rejects single-link chains with dissimilar endpoints |
| `CLUSTER_ID_REUSE_SIMILARITY` | 0.90 |
| `RSS_MAX_AGE_DAYS` | 7; live RSS ingestion lookback in Asia/Kolkata calendar days |
| `NER_MODEL_NAME` / `NER_BATCH_SIZE` | local fine-tuned model if present, otherwise Babelscape; batch 16 |
| `NER_MAX_SENTENCES` | 0 means no sentence cap |
| `SUMMARY_MODEL_NAME` / `SUMMARY_DEVICE` | mT5 multilingual XLSum / `auto` |

Shell scripts use PID files and `flock` guards for daemon startup/looping. The reprocessing scripts are separate maintenance tools from live polling. The README/runbook should be consulted before historical data replacement or database reset scripts.

## 15. Important implementation caveats and review findings

1. **Two ingestion architectures and configs:** standalone polling plus the Celery/Redis path coexist, with separate YAML source files and different schedules. This is the largest operational ambiguity.
2. **Feed configuration metadata is partly descriptive:** declared per-feed interval/rate limits and topic override are not enforced by the standalone flow; Celery uses global schedules.
3. **Freshness and history:** live ingestion now uses a rolling configurable seven-day RSS window; API and canonical export retain dated historical articles and order the newest first. The separate historical reprocessor and image backfill scripts remain explicitly 2026-specific maintenance tools.
4. **Dedup scope mismatch:** fetcher dedup is outlet-scoped while Article GUID has a global unique constraint. Cross-outlet GUID collisions can cause a database insert failure.
5. **Rule-based language/cleaning:** Tamil detection, sentence filtering, junk removal, and topic assignment use heuristics/regex. Misclassification and over-cleaning remain possible.
6. **NER data/status behavior:** NER reruns completed rows because its status query includes already enriched states, potentially adding substantial repeated work each cycle. Unknown language defaults to Tamil.
7. **Clustering behavior:** only DBSCAN is active in `run_all`; the agglomerative option is present but inactive. Language guards intentionally prevent bilingual articles from sharing a cluster, so cross-language coverage is not unified into one event cluster. Pairwise cohesion and stricter event-ID reuse now reduce single-link false merges, but human-reviewed pair labels remain necessary to tune thresholds.
8. **Model/version reporting:** the API metadata defaults can report the upstream NER model even when the local fine-tuned checkpoint is selected by runtime code. Treat `/metadata` as descriptive, not authoritative runtime introspection.
9. **Credential/config handling:** `.env.example` is present, but the code shown reads `os.getenv` directly and does not load it. `setup_local_infra.sh` creates a password different from the database module's hard-coded default URL password; local setup may require an explicit `DATABASE_URL` or synchronized credentials.
10. **Output semantics:** canonical CSV export is sourced from PostgreSQL and can mutate canonicalized text and reset derived data before writing. `raw_processed.csv` can be staging/live or a DB export depending on the command that last wrote it.
11. **Current working-tree edits:** this review was performed with existing uncommitted edits in README, API, clustering, event-pair annotations, and an untracked clustering result image. The report reflects those files as currently present and did not alter them.

## 16. Suggested next steps

- Decide whether the supported runtime is the shell batch daemon or Celery; document one as canonical and either deprecate or reconcile the other.
- Consolidate the two source YAML files and make interval, rate-limit, category, and topic override behavior explicit.
- Keep the live RSS lookback configurable and decide whether a longer backfill mode is needed for new feeds.
- Calibrate headline/body weights and cluster thresholds against human-reviewed event pairs before treating generated groups as correct.
- Make NER incremental by selecting rows missing NER/linking output or whose semantic text hash has changed; correct its language fallback.
- Align fetcher and database dedupe keys and make database/CSV writes recoverable as a unit or rebuildable from one canonical store.
- Record actual model checkpoint identity in metadata and persist pipeline/version parameters with each enrichment stage.
- Add human-reviewed NER, clustering, and summary labels before publishing model-quality claims.

## 17. File guide

- Feed inventory: `src/backend/config/sources.yaml`, `src/backend/ingestion/config/sources.yaml`
- Feed implementation: `src/backend/scripts/fetch_rss_standalone.py`, `src/backend/ingestion/tasks/fetch_feed.py`
- Cleaning: `src/backend/ingestion/tasks/text_cleaning.py`
- Data schema: `src/backend/models/database.py`
- NER/linking: `src/backend/ner_pipeline/zero_shot/`
- Fine-tuning: `src/backend/ner_pipeline/finetune/`
- Embeddings/clustering: `src/backend/semantic_processing/`
- Summarization/API: `src/backend/summarization/`, `src/backend/api.py`
- Frontend: `src/frontend/`
- Operational scripts: `src/backend/scripts/shell/`
- Maintenance/export: `src/backend/scripts/reprocess_articles.py`, `src/backend/export/csv_export.py`
- Evaluation documentation: `src/backend/evaluation/README.md`, `src/backend/docs/ARTICLE_REPROCESSING.md`

## 18. Operational commands for annotation and clustering

Run from the repository root with the project's virtual environment active and PostgreSQL running:

```bash
source venv/bin/activate
export PYTHONPATH=./src

# Generate weakly labeled BIO train/validation files from the bundled corpora.
python src/backend/ner_pipeline/finetune/auto_annotate.py
# Manually review dataset/train.jsonl and dataset/val.jsonl, then train MuRIL.
python src/backend/ner_pipeline/finetune/train.py

# Apply the runtime NER model to database articles and then recalculate vectors/clusters.
python src/backend/ner_pipeline/zero_shot/nlp_pipeline.py
python src/backend/semantic_processing/embedding_service.py
DBSCAN_EPS=0.11 CLUSTER_MIN_PAIRWISE_SIMILARITY=0.88 \
  python src/backend/semantic_processing/clustering_service.py
python src/backend/semantic_processing/topic_modeling.py
python src/backend/export/csv_export.py

# Fill event_pairs.csv with human-reviewed GUIDs (or canonical URLs) and labels 1/0.
python src/backend/evaluation/evaluate_event_clustering.py
```

`auto_annotate.py` generates weak labels from bundled corpora; it does not
annotate live database articles and its output must be reviewed before training.
`clustering_service.py` can be run directly to force a full DBSCAN pass over
stored embeddings; `embeddings_and_clustering.py` skips clustering when it
generates zero new embeddings, so it is not the right command when only tuning
clustering thresholds. Clustering is evaluated, not trained: reviewed positive
and negative article pairs in `event_pairs.csv` are used by the evaluator.

## 19. Changes made for freshness and false event merges

Live RSS fetch now accepts dated items from the rolling `RSS_MAX_AGE_DAYS`
window (default seven Asia/Kolkata calendar days), so today's feed items are
eligible every poll while old RSS archive entries are not repeatedly ingested.
Previously stored dated articles remain in PostgreSQL, the API, and the full
canonical export, sorted newest first. The historical URL reprocessor and
image backfill remain 2026-specific maintenance tools.

The DBSCAN post-pass now requires every pair of articles in an emitted event
to meet the configured cosine similarity floor (default 0.88), in addition to
the existing centroid, time-span, and size checks. This prevents common
single-link chaining patterns from producing invalid multi-story summaries.
Existing event IDs are reused only above 0.90 centroid similarity. Clustering
runs now store the split and ID-reuse thresholds in their parameters, and
undated articles are excluded from event clustering/API display.
These changes reduce false associations; the thresholds should still be
calibrated using reviewed same-event/different-event pairs.
