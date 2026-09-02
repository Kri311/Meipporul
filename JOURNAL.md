# Veritas Lens — Master Development Journal

> **Project type:** Production-oriented Tamil + English news intelligence platform
>
> **Core idea:** Aggregate Tamil news from major outlets, preserve the original reporting, group articles covering the same real-world event, show publisher-level political orientation as a *source provenance signal*, compare how different outlets frame the same event, and surface coverage gaps / blind spots.
>
> **Project status:** Architecture + research baseline consolidated
>
> **Last consolidated:** 2026-09-02 IST
>
> **Primary implementation constraint:** Local-first, Dockerized, reproducible, observable, and small enough to develop on a local workstation.
>
> **Important product principle:** Veritas Lens does **not** decide what political side is "correct" and must not present an automatically inferred political orientation as objective fact. Outlet bias/orientation labels come from documented external sources or an explicitly maintained project label registry. Article-level analysis describes measurable framing differences, omissions, sourcing patterns, entities, claims, and coverage distribution rather than declaring an article "propaganda" or "fabricated" without evidence.

---

## 0. What This Project Is

Veritas Lens is a bilingual Tamil/English news aggregation and comparative media-analysis product inspired by the *comparison* and *Blindspot* concepts used by Ground News, but adapted for Tamil news and for a learning-oriented, fully self-built AI engineering stack.

The initial political-orientation taxonomy defined for the project is:

| Code | Product label | Intended meaning |
|---|---|---|
| `DRV` | Pro-Dravidian | Outlet/source classified in the project's Dravidian orientation bucket |
| `OPP` | Opposition | Outlet/source classified around the current project definition of opposition-oriented coverage: TVK / AIADMK / BJP ecosystem |
| `CON` | Conservative | Conservative orientation; exact membership is variable and must be documented rather than guessed |
| `IND` | Independent | Baseline/reference bucket for relatively independent sources |

These labels are **source-level metadata**, not an article-level model prediction by default. The project must retain the provenance of each label: who assigned it, what source/method was used, when it was last reviewed, and what confidence or disagreement exists.

### Product objective

The product should let a user answer questions such as:

- What is happening today in Tamil Nadu / India / the world?
- Which Tamil outlets are covering the same event?
- How is the event described across `DRV`, `OPP`, `CON`, and `IND` sources?
- Which entities, quotes, claims, and topics are common across outlets?
- Which important parts appear only in some coverage?
- Which events have strong coverage from one orientation but weak/no coverage from others?
- How does headline wording differ across outlets?
- Can a user open the original article and inspect the evidence behind a generated summary?

### Product philosophy

The platform is a **lens**, not a replacement newsroom.

The core UI should always preserve the distinction between:

1. **What the source reported**
2. **What the system extracted or inferred**
3. **What the source-level orientation label says**
4. **What the system does not know**

That separation is a foundational design rule for the database, APIs, ML pipelines, UI, and evaluation strategy.

---

# 1. Existing Project Decisions

The previous project journal established the product as a live, deployable Tamil news bias aggregator rather than a one-off ML experiment, defined the four orientation buckets, required explanation-driven development, and established a single project root with phase-gated documentation. fileciteturn0file1L7-L20

The implementation plan then established the initial ingestion flow: scheduled RSS fetching, full article extraction, sentence embeddings, and PostgreSQL + pgvector storage. It also explicitly proposed PostgreSQL, Redis, Celery-style scheduling, RSS parsing, Trafilatura/newspaper-style extraction, and vector storage as the first build stage. fileciteturn0file0L8-L24

The current master plan keeps those decisions but expands them into a complete product architecture.

---

# 2. System Design at a Glance

## 2.1 End-to-end architecture

```text
                    ┌──────────────────────────────┐
                    │ Tamil / English RSS Feeds    │
                    │ 15+ initial publishers       │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │ Ingestion API / RSS Fetcher  │
                    │ feedparser + HTTP client     │
                    └──────────────┬───────────────┘
                                   │ raw metadata
                                   ▼
                    ┌──────────────────────────────┐
                    │ Normalization + URL Canonical │
                    │ dedupe + source validation   │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │ Article Extraction Worker    │
                    │ Trafilatura + fallback       │
                    └──────────────┬───────────────┘
                                   │ clean article
                                   ▼
        ┌────────────────────────────────────────────────────────┐
        │                 PostgreSQL 16 + pgvector                │
        │                                                        │
        │ outlets │ feed_runs │ articles │ entities │ events     │
        │ claims  │ comparisons │ summaries │ model_runs         │
        └──────────────┬───────────────────────┬─────────────────┘
                       │                       │
             vector / text search       structured metadata
                       │                       │
                       ▼                       ▼
             ┌────────────────┐      ┌────────────────────┐
             │ NLP Workers    │      │ FastAPI Backend    │
             │ embeddings     │      │ auth/cache/routing │
             │ NER            │      └─────────┬──────────┘
             │ topics         │                │
             │ clustering     │                │ REST/JSON
             │ summarization  │                ▼
             └───────┬────────┘      ┌────────────────────┐
                     │               │ Next.js Frontend   │
                     ▼               │ dashboards/cards   │
           ┌────────────────────┐    │ bilingual UI      │
           │ Event Intelligence │    └────────────────────┘
           │ comparison engine  │
           │ blindspot engine   │
           │ framing analysis    │
           └────────────────────┘

Infrastructure:
  Redis → Celery broker/result backend
  Celery Beat → periodic scheduling
  Prometheus/Grafana → observability
  Docker Compose → local orchestration
  Nginx/Caddy → production reverse proxy
```

## 2.2 Containers

Initial local stack:

| Container | Initial image / runtime | Responsibility |
|---|---|---|
| `postgres` | `pgvector/pgvector:pg16` | relational data + vectors + search metadata |
| `redis` | `redis:7-alpine` | Celery broker / lightweight cache |
| `worker` | custom Python slim image | RSS, extraction, normalization, NLP workers |
| `beat` | same Python image | Celery Beat scheduler |
| `api` | custom Python slim image | FastAPI backend |
| `frontend` | Node-based production build | Next.js web application |
| `prometheus` | official Prometheus image | metrics collection |
| `grafana` | official Grafana image | local monitoring dashboards |

For the first milestone, only `postgres`, `redis`, and ingestion worker are mandatory. The original implementation plan explicitly defined those first three containers. fileciteturn0file0L26-L32

Docker Compose healthchecks and dependency conditions will be used so services do not simply start in an assumed-ready state. Docker Compose supports `service_healthy` dependency gates tied to healthchecks. 

---

# 3. Non-Negotiable Engineering Principles

## 3.1 No silent partial outputs

The requirement "no room for errors and partial outputs" is treated as an engineering goal, not a claim that failures can be eliminated.

The implementation must instead make failures explicit and recoverable:

- every pipeline stage writes status fields;
- each article has a lifecycle state;
- failed work is retried with backoff;
- permanently failed items go to a dead-letter/review state;
- downstream stages do not assume upstream success;
- generated output carries a `model_run_id` and source article IDs;
- missing data results in a visible "insufficient coverage" state rather than a fabricated conclusion;
- every scheduled job has health and freshness metrics;
- every model output has version metadata;
- every database mutation is idempotent where practical.

Celery supports automatic retries and exponential backoff for transient failures, which is useful for RSS/HTTP dependencies. 

## 3.2 Raw data must never be destroyed

For every article, keep:

- original RSS payload or normalized feed record;
- original URL;
- canonical URL;
- extraction timestamp;
- extracted title;
- raw extracted text where legally appropriate for the project;
- cleaned text;
- language detection result;
- extraction status;
- content hash;
- model versions.

Cleaned text is a derivative. Never overwrite the raw representation.

## 3.3 Provenance first

Every important derived object must point backward:

```text
summary → event → article → outlet → bias-label source
                    ↘ model run
```

This makes the UI explainable and the model evaluation reproducible.

## 3.4 Separate source orientation from article framing

`DRV / OPP / CON / IND` is not the same thing as a prediction that the article is biased.

The product should distinguish:

- source orientation label;
- factuality/reliability metadata, if independently available;
- article framing signals;
- headline sentiment / loaded-language measurements;
- topic/entity emphasis;
- omitted-vs-covered facts, where measurable;
- quotation balance;
- event coverage distribution.

This avoids collapsing all media analysis into one oversimplified score.

---

# 4. Lessons from Ground News — What to Borrow and What to Improve

Ground News states that its publication bias ratings are based on ratings from three independent monitoring organizations, and its methodology considers wording, story choices, and political affiliation. It also treats source-level factuality separately from bias. citeturn343013search0turn343013search2

Ground News also groups articles from different publications covering the same event into a single story and presents perspective differences in one view. citeturn343013search3

Its Blindspot concept identifies stories with political undertones that are disproportionately covered by one side of the political spectrum, using explicit coverage-distribution rules. citeturn343013search0

### What Veritas Lens should adopt

- event-level story grouping;
- source orientation badges;
- one event → many source perspectives;
- headline comparison;
- article-by-article source links;
- visual coverage distribution;
- blindspot / asymmetric-coverage discovery;
- transparent methodology page;
- source ownership / provenance metadata where available;
- user ability to inspect the original reporting.

### What Veritas Lens should improve for the Tamil context

Ground News's bias methodology is explicitly grounded in the U.S. political system. citeturn343013search0

Therefore, Veritas Lens must **not** blindly import the seven-category U.S. political spectrum or pretend that a Tamil Nadu political taxonomy maps cleanly to it.

Instead:

```text
External / documented source classification
          ↓
Project taxonomy mapping
          ↓
DRV / OPP / CON / IND
          ↓
coverage statistics
          ↓
article framing analysis
```

The mapping must be versioned.

### Blindspot adaptation

We should not copy Ground News's exact formula. We should build our own testable rule suitable for the four-bucket Tamil system.

Initial candidate definition:

> A blindspot candidate is an event where the number and weighted share of sources covering it are substantially concentrated in one orientation bucket, after controlling for outlet count, publication volume, time window, and minimum article quality.

Example initial rule (to be tuned using labeled validation data):

```text
eligible event:
  ≥ 4 distinct outlets
  ≥ 12 total articles OR ≥ 4 distinct sources
  event age ≤ 72h

asymmetric coverage candidate:
  dominant_bucket_share ≥ 0.70
  AND dominant_bucket has ≥ 3 outlets
  AND every non-dominant bucket has ≤ 1 outlet
  OR total coverage ratio ≥ 3:1

confidence:
  increase with outlet diversity
  decrease when many articles come from one syndication chain
  decrease when event cluster purity is low
```

This is a starting hypothesis, not a final scientific threshold.

---

# 5. Phase 0 — Product Contract and Governance

## Goal

Freeze what the product is before coding the whole system.

## Why

Without a product contract, features will continuously change the architecture.

## Deliverables

```text
rules.md
JOURNAL.md
implementation_plan.md
ARCHITECTURE.md
DATA_DICTIONARY.md
MODEL_CARD.md
EVALUATION.md
THREAT_MODEL.md
```

## Define

- source onboarding rules;
- outlet bias-label provenance policy;
- article retention policy;
- crawler ethics / robots and rate-limiting policy;
- acceptable extraction methods;
- minimum article-quality requirements;
- model approval criteria;
- release gates;
- incident process;
- output disclaimer language;
- bilingual language policy;
- copyright-safe UI policy.

## Exit criteria

- product scope frozen;
- taxonomy defined;
- database entities agreed;
- phase gates documented.

---

# 6. Phase 1 — Source Registry and RSS Ingestion

The existing implementation plan makes this the first engineering milestone and specifies 15+ Tamil outlets, RSS metadata extraction, article extraction, embeddings, and PostgreSQL storage. fileciteturn0file0L12-L24

## Goal

Create a reliable feed-ingestion system that continuously discovers articles.

## Why

Everything downstream depends on a stable article corpus.

## Sources

Start with major Tamil news publishers that provide usable RSS feeds. Maintain a configuration-driven source registry rather than hard-coding them in Python.

`config/sources.yaml`:

```yaml
sources:
  - slug: example_outlet
    name: Example Tamil News
    language: ta
    homepage: https://example.com
    rss:
      - https://example.com/feed
    enabled: true
    fetch_interval_minutes: 15
    rate_limit_per_minute: 30
    category: general
```

Do not add a feed solely because it is politically convenient. Selection should be based on audience relevance, availability, stability, and source diversity.

## Pipeline

```text
Celery Beat
   ↓
fetch_feed(source_id)
   ↓
validate XML / content type
   ↓
parse entries
   ↓
canonicalize URL
   ↓
compute content identity
   ↓
upsert article metadata
   ↓
enqueue extract_article(article_id)
```

## Reliability rules

For every feed:

- timeout;
- connection retry;
- exponential backoff;
- user agent;
- rate limiting;
- feed response hash;
- feed-run record;
- HTTP status tracking;
- last-success timestamp;
- consecutive failure counter.

Celery Beat is the scheduler that emits periodic tasks to workers, and Celery's documentation notes that only one scheduler should run a given schedule to avoid duplicate dispatch. citeturn343013search8

## Dedupe strategy

Use multiple signals:

1. normalized canonical URL;
2. URL hash;
3. source ID + GUID if RSS provides one;
4. normalized title hash as a secondary signal;
5. content hash after extraction.

Never use title similarity alone as an identity key.

## Database additions

```text
outlets
rss_feeds
feed_runs
articles
article_fetch_attempts
```

## Exit criteria

- all configured feeds can be fetched;
- failed feeds are visible;
- duplicate entries do not create duplicate article rows;
- each feed records freshness;
- the first 50+ valid articles are present;
- no downstream worker consumes an article marked invalid.

The original implementation plan also defines the first success criteria as clean Docker boot, PostgreSQL tables, 15-minute fetching, extraction, embeddings, deduplication, and at least 50 articles. fileciteturn0file0L85-L92

---

# 7. Phase 2 — Article Retrieval and Content Extraction

## Goal

Convert an RSS link into the best available representation of the article body.

## Why

RSS often provides only title, summary, timestamp, and URL. Event clustering, entity extraction, framing analysis, and summarization require full text.

## Primary tool

**Trafilatura** as first extractor, with source-specific fallback extractors only when justified.

Do not create a giant "scrape everything" abstraction. Extraction should be modular:

```text
extract_article(url)
  ├─ trafilatura
  ├─ source-specific parser if needed
  └─ failure / manual review state
```

## Extraction output

```json
{
  "title": "...",
  "author": "...",
  "published_at": "...",
  "updated_at": "...",
  "text": "...",
  "language": "ta",
  "word_count": 1234,
  "extraction_method": "trafilatura",
  "extraction_quality": 0.94
}
```

## Quality checks

Reject or quarantine extracted content when:

- body is empty;
- body is mostly navigation text;
- character-to-word ratio is suspicious;
- repeated paragraphs exceed threshold;
- extracted content is extremely short compared with RSS metadata;
- page is an error / paywall / consent wall;
- language mismatch is severe.

## Extraction quality score

Build a deterministic heuristic initially:

```text
quality = weighted(
  body_length_score,
  alphabet_ratio,
  repetition_penalty,
  title_overlap,
  paragraph_count,
  boilerplate_penalty
)
```

Later compare against a human-labeled extraction-quality set.

---

# 8. Phase 3 — Data Cleaning, Normalization, and Language Handling

## Goal

Create clean text for NLP without losing the raw article.

## Transformations

- normalize Unicode;
- normalize whitespace;
- remove boilerplate;
- de-duplicate repeated paragraphs;
- normalize punctuation where safe;
- preserve Tamil script;
- preserve named entities;
- remove navigation / footer text;
- remove tracking parameters from URLs;
- detect language;
- detect mixed-language sections.

## Do not over-clean Tamil

Do **not** blindly stem or aggressively remove stopwords before embeddings. Tamil morphology, proper nouns, names, and inflection are important for event clustering.

Maintain at least three text forms:

```text
raw_text
clean_text
ntext_for_model
```

The final field can contain model-specific normalization.

## Language labels

Use:

- `ta` Tamil
- `en` English
- `mixed` mixed Tamil/English
- `unknown`

Store confidence.

## Bilingual strategy

The core architecture must remain language-neutral:

```text
article.language
       ↓
language-aware tokenization / NER
       ↓
shared multilingual embeddings
       ↓
shared event space
```

This allows a Tamil and English article covering the same event to enter the same event cluster.

---

# 9. Phase 4 — PostgreSQL + pgvector Data Model

The existing design uses PostgreSQL 16 + pgvector so embeddings live next to article metadata and content. fileciteturn0file1L30-L42

pgvector supports exact nearest-neighbor search plus approximate HNSW and IVFFlat indexes. HNSW generally provides a useful speed/recall trade-off at the cost of higher memory and slower index build times. citeturn343013search1

## Core schema

```text
outlets
  id
  slug
  name
  language_set
  homepage_url
  orientation_bucket
  orientation_confidence
  active

outlet_orientation_sources
  id
  outlet_id
  label
  source_name
  source_url
  methodology_note
  evidence_date
  reviewed_at
  reviewer
  confidence
  status

rss_feeds
  id
  outlet_id
  feed_url
  category
  enabled
  last_success_at
  consecutive_failures

feed_runs
  id
  rss_feed_id
  started_at
  finished_at
  http_status
  entries_seen
  entries_new
  entries_failed
  error_code

articles
  id
  outlet_id
  rss_feed_id
  guid
  canonical_url
  original_url
  title
  description
  author
  published_at
  updated_at
  language
  raw_text
  clean_text
  content_hash
  extraction_method
  extraction_quality
  processing_status
  embedding vector(384)
  created_at
  updated_at

article_entities
  id
  article_id
  entity_text
  normalized_text
  entity_type
  start_char
  end_char
  confidence

article_topics
  article_id
  topic_id
  score

events
  id
  title_ta
  title_en
  canonical_embedding
  first_seen_at
  last_seen_at
  cluster_version
  quality_score
  status

event_articles
  event_id
  article_id
  similarity_score
  assignment_method
  assignment_version

comparisons
  id
  event_id
  created_at
  coverage_window_start
  coverage_window_end
  source_count
  article_count

article_claims
  id
  article_id
  claim_text
  normalized_claim
  claim_type
  evidence_span
  confidence

article_quotes
  id
  article_id
  speaker_entity_id
  quote_text
  attribution_confidence

summaries
  id
  event_id
  language
  summary_type
  summary_text
  source_article_ids
  model_id
  prompt_version
  created_at

model_runs
  id
  model_name
  model_revision
  task
  language
  inference_config
  created_at

blindspots
  id
  event_id
  dominant_bucket
  distribution_json
  score
  confidence
  rule_version
  explanation_json
  created_at
```

## Search

Use PostgreSQL full-text search for lexical retrieval and pgvector for semantic retrieval. PostgreSQL supports text search, ranking, highlighting, and indexed full-text search; GIN is the preferred index type for many persistent text-search use cases. citeturn978058search1turn978058search8

Recommended hybrid retrieval:

```text
lexical score = PostgreSQL FTS / BM25-like ranking strategy
vector score  = cosine similarity
final score   = α * lexical + (1-α) * vector
```

The blend coefficient should be measured rather than assumed.

---

# 10. Phase 5 — Embeddings and Semantic Retrieval

## Goal

Create a shared semantic space for Tamil + English article/event matching.

## Primary local baseline

**`intfloat/multilingual-e5-small`**

Why:

- multilingual;
- 384-dimensional vectors;
- relatively small compared with large retrieval models;
- supports 100 languages according to its model card, while warning that low-resource languages can degrade; Tamil should therefore be explicitly benchmarked rather than assumed good. citeturn329442search2turn329442search7

This is an engineering baseline, not the final model.

## Tamil-focused challenger

**`Tamil-ai/tamil-embed-base`** should be evaluated as a Tamil-heavy challenger. Its model card describes Tamil semantic search, cross-lingual English-Tamil similarity, clustering and RAG as intended use cases, with a 0.3B parameter size and a reported 768-dimensional output with Matryoshka-style smaller dimensions available. citeturn783517search9

Because it is much larger than the 384-dimension E5-small baseline, it should be tested on a held-out Tamil/English event-matching benchmark before replacing the smaller baseline.

## Optional advanced challenger

**BGE-M3** is a larger multilingual model with 1024-dimension embeddings and long-context retrieval support, but it is not the local-first default because the memory footprint is substantially larger. citeturn329442search1

## Embedding policy

Every embedding must store:

```text
model_name
model_revision
embedding_dimension
normalization_method
created_at
```

Never mix vectors from incompatible models in the same production vector column.

## Chunking

For long articles:

- article-level embedding for broad retrieval;
- paragraph/sentence chunk embeddings for detailed comparison;
- aggregate event embedding from member articles.

Store both when necessary.

## Evaluation

Create a benchmark of:

- same-event Tamil ↔ Tamil pairs;
- same-event Tamil ↔ English pairs;
- different-event near-topic pairs;
- same politician but different events;
- recurring-event pairs (e.g., same issue over multiple days).

Metrics:

- Recall@1
- Recall@5
- Recall@10
- MRR
- nDCG@k
- pairwise cosine separation
- false merge rate
- false split rate

The winner is not the model with the highest raw cosine score. It is the model that produces the best event retrieval and cluster purity under the project workload.

---

# 11. Phase 6 — Named Entity Recognition

## Goal

Extract people, organizations, locations, political entities, places, and event-relevant entities that strengthen clustering and comparison.

## Primary candidate

**AI4Bharat IndicNER**.

Its model card states that IndicNER is fine-tuned for 11 Indian languages including Tamil and was benchmarked on human-annotated and public Indian NER datasets. citeturn343013search4

## Lightweight challenger

A community Tamil-specific NER model can be used as a comparison baseline, but model-card quality must be examined carefully. For example, `sathishmahi/tamil-ner-model` is a BERT-based Tamil NER model, but its card provides limited task detail and a relatively large model artifact, so it should not automatically become the production choice. citeturn783517search2turn783517search3

## NER is not clustering

This is a critical architecture decision.

Incorrect:

```text
NER → clusters
```

Correct:

```text
article
 ├─ embedding
 ├─ entities
 ├─ time
 ├─ normalized title
 ├─ location
 └─ topic signals
        ↓
  multi-signal event clustering
```

## Entity normalization

Tamil news will have spelling variation, transliteration, abbreviations, honorifics, and alternate names.

Maintain an alias graph:

```text
MK Stalin
M. K. Stalin
மு.க. ஸ்டாலின்
ஸ்டாலின்
```

These should not be merged solely by string equality. Use a combination of:

- exact normalized form;
- alias table;
- NER type;
- contextual embedding;
- co-occurring entities;
- source-specific variants.

## NER evaluation

Use a human-labeled test set stratified by:

- Tamil / English;
- people / organizations / locations;
- political names;
- transliterations;
- headlines / body text.

Metrics:

- entity-level precision;
- entity-level recall;
- entity-level F1;
- strict span F1;
- type accuracy;
- per-entity-category F1.

Because a news aggregator cares about downstream event linking, add:

- entity normalization accuracy;
- cluster improvement with vs without NER.

---

# 12. Phase 7 — Event Clustering

## Goal

Group articles that describe the same real-world event.

## Why

This is the heart of the Ground News-inspired experience.

A user should see:

```text
EVENT: Tamil Nadu cabinet reshuffle

DRV       8 outlets
OPP       4 outlets
CON       2 outlets
IND       3 outlets
```

instead of twenty disconnected article cards.

## Candidate algorithm

Start simple and measurable:

1. time window filter;
2. embedding nearest-neighbor search;
3. entity overlap score;
4. title similarity score;
5. location overlap;
6. optional topic compatibility;
7. HDBSCAN or agglomerative clustering over the resulting graph.

### Candidate pair score

```text
S(article_a, article_b) =
    0.55 * semantic_similarity
  + 0.20 * entity_overlap
  + 0.10 * title_similarity
  + 0.10 * temporal_proximity
  + 0.05 * location_overlap
```

These coefficients are initial hypotheses and must be tuned with evaluation data.

## Why HDBSCAN is useful

News streams have an unknown number of events, varying event sizes, and many noise articles. HDBSCAN can identify dense clusters and leave noise as `-1`; its library also exposes a density-based validity index from -1 to 1, where higher values indicate better clustering. citeturn978058search3

## Event identity

An event is not just "same topic".

Examples:

```text
Topic: Chennai traffic

Event A: 2026-09-01 metro disruption
Event B: 2026-09-02 highway accident
Event C: 2026-09-02 traffic restriction announcement
```

They may share entities and vocabulary but must not automatically merge.

## Event canonical representation

```json
{
  "event_id": "evt_123",
  "window": "2026-09-02T08:00Z/2026-09-03T08:00Z",
  "entities": ["..."],
  "locations": ["..."],
  "topics": ["..."],
  "representative_articles": ["..."],
  "cluster_confidence": 0.91
}
```

## Event-cluster evaluation

Create a manually labeled dataset where articles are mapped to gold event IDs.

Metrics:

- Adjusted Rand Index (ARI);
- Normalized Mutual Information (NMI);
- pairwise precision;
- pairwise recall;
- pairwise F1;
- cluster purity;
- B-cubed precision/recall/F1;
- false merge rate;
- false split rate;
- noise rate;
- HDBSCAN validity score.

The operational metrics matter most:

> **False merge is more damaging than false split.**

A wrong merge can make unrelated sources appear to disagree on the same event.

---

# 13. Phase 8 — Topic Classification

## Goal

Provide higher-level categories for search and navigation.

Possible taxonomy:

```text
Politics
Tamil Nadu
India
World
Business
Technology
Science
Education
Crime
Sports
Entertainment
Health
Environment
Government
Elections
Courts
Infrastructure
```

Topics should be hierarchical where useful:

```text
Politics
  ├─ Tamil Nadu Politics
  ├─ Elections
  └─ Parliament
```

## Approach

Start with zero-shot / embedding similarity to a fixed topic taxonomy.

Later fine-tune a Tamil/English classifier on the project's own labels.

## Evaluation

- macro F1;
- micro F1;
- per-topic precision / recall;
- confusion matrix;
- multilabel coverage;
- calibration / confidence reliability.

---

# 14. Phase 9 — Bias / Orientation Provenance Layer

## Goal

Represent source orientation labels in a transparent, auditable manner.

## Critical distinction

Do **not** train a model to decide:

```text
article → DRV/OPP/CON/IND
```

in the first version and present that as objective truth.

Instead:

```text
outlet → external rating evidence → project mapping → bucket
```

Then separately analyze article framing.

## Orientation table

Each outlet should have:

```text
outlet_id
bucket
source_of_label
source_url
methodology
label_date
review_date
review_status
confidence
notes
```

## Handling conflicting ratings

If independent labeling sources disagree:

```text
Source A: DRV
Source B: IND
Source C: OPP
```

Do not arbitrarily select one.

Display:

```text
Project classification: DRV
Confidence: Medium
Reason: 2/3 source agreement
```

or:

```text
Unresolved classification
Multiple independent sources disagree
```

## Change history

Bias classification must be temporal:

```text
outlet_orientation_history
  valid_from
  valid_to
  bucket
  source
```

That prevents historical articles from being retroactively relabeled without traceability.

---

# 15. Phase 10 — Article-Level Framing Analysis

## Goal

Show *how* different outlets cover an event without pretending that wording alone proves political bias.

## Features

For each article, extract:

- headline;
- subheadline;
- article lead;
- entities emphasized;
- quoted people;
- quote count;
- source types;
- attribution patterns;
- sentiment around entities;
- loaded/subjective lexical markers;
- modal language;
- certainty vs uncertainty;
- allegations vs verified claims;
- numerical facts;
- date/time claims;
- unique entities / facts not present elsewhere.

## Headline comparison

UI example:

```text
DRV
"Government announces major welfare expansion"

OPP
"Government launches costly welfare scheme amid criticism"

IND
"Cabinet approves new welfare programme"
```

The system should highlight lexical differences, but must not label the first sentence "biased" merely because it is positive.

## Framing indicators

Possible measurable indicators:

```text
Loaded-word rate
Quote diversity
Source diversity
Entity prominence
Allegation density
Modal certainty
Negative/positive lexical polarity
Headline-body similarity
Unique fact ratio
```

These become **signals**, not verdicts.

## Evaluation

Build a manually annotated corpus where human annotators mark:

- loaded language;
- framing;
- quotation imbalance;
- unsupported certainty;
- omission candidates;
- attribution clarity.

Measure:

- precision;
- recall;
- F1;
- inter-annotator agreement (Cohen's kappa or Krippendorff's alpha, depending on task design).

---

# 16. Phase 11 — Claim and Fact Extraction

## Goal

Move beyond summaries into structured event evidence.

## Claim representation

```text
claim_id
article_id
event_id
claim_text
normalized_claim
subject
predicate
object
claim_type
evidence_span
attribution
certainty
```

## Claim types

```text
FACTUAL_REPORT
ALLEGATION
QUOTE
PREDICTION
OPINION
ANNOUNCEMENT
STATISTIC
```

This helps the UI distinguish:

> "Minister said X"

from:

> "X happened"

The distinction is crucial in political news.

## Cross-source claim comparison

For the same event:

```text
Claim A appears in 9 articles
Claim B appears in 2 articles
Claim C appears in 1 article
```

This does **not** automatically mean Claim C is true or false. It means the claim is less widely represented in the current source sample.

---

# 17. Phase 12 — Summarization System

## Goal

Produce concise bilingual event summaries while preserving source provenance and disagreement.

## Model strategy

### Tamil/Indic-first candidate

**AI4Bharat IndicBART** supports Tamil and English and was designed for generation tasks such as summarization and translation. Its model card also notes that it is smaller than mBART and mT5-base, making it a useful local model candidate. citeturn783517search0turn783517search4

### Headline/summarization-specific candidate

**AI4Bharat MultiIndicHeadlineGeneration** is also based on IndicBART and supports Tamil among 11 Indian languages. citeturn783517search1

### Translation bridge

**IndicTrans2 distilled 200M** provides Indic→English and English→Indic models, including Tamil, and is a strong local translation candidate when bilingual output is needed. citeturn478786search1turn478786search7turn329442search10

### Larger challenger

`google/mt5-small` covers a very broad multilingual language set, but the model artifact is substantially larger than the IndicBART candidate, so it should be evaluated rather than adopted by default for this local-first project. citeturn478786search4turn478786search11

## Summarization architecture

Do **not** ask a model to summarize an entire multi-source event in one unrestricted generation step.

Use staged summarization:

```text
Article
  ↓
article summary
  ↓
claim/entity extraction
  ↓
event evidence aggregation
  ↓
neutral event summary
  ↓
bilingual rendering
```

## Two summary modes

### Mode A — Neutral event summary

A concise factual summary assembled from claims with source support.

### Mode B — Perspective summary

One summary per orientation bucket:

```text
How DRV sources report it
How OPP sources report it
How CON sources report it
How IND sources report it
```

This should be presented as:

> "Summary of coverage from sources classified as X"

not:

> "The X truth"

## Hallucination controls

Every generated sentence should have supporting article/claim IDs in the internal record.

Reject / regenerate when:

- names are not in source evidence;
- numbers do not match evidence;
- dates are invented;
- sentiment is introduced without support;
- causal relationships are generated without support.

## Summarization evaluation

Human reference summaries are required.

Automated metrics:

- ROUGE-1
- ROUGE-2
- ROUGE-L
- BERTScore
- factual consistency / entailment score
- source attribution accuracy
- entity preservation
- number preservation
- date preservation
- hallucination rate

But automatic metrics are not sufficient. Run human evaluation on:

```text
factuality
coverage
fluency
neutrality
attribution
bilingual faithfulness
```

Use Likert scales and inter-annotator agreement.

---

# 18. Phase 13 — Blindspot Engine

## Goal

Surface events where coverage is strongly asymmetric across the project's orientation buckets.

Ground News defines Blindspots around stories with political undertones that are disproportionately covered by one side and uses explicit distribution conditions. citeturn343013search0turn343013search9

## Veritas Lens version

Use a transparent scoring function.

```text
coverage_share(bucket)
source_diversity(bucket)
article_count(bucket)
syndication_penalty
cluster_confidence
source_quality_adjustment
```

Example score:

```text
blindspot_score =
    asymmetry
  × diversity_bonus
  × cluster_confidence
  × temporal_relevance
  × independence_bonus
```

Where:

```text
asymmetry = max_bucket_share - second_bucket_share
```

## Example output

```text
BLINDSPOT CANDIDATE

Event: X
Dominant orientation: OPP
Coverage:
  OPP  72%
  IND  14%
  DRV   8%
  CON   6%

Confidence: High
Reason:
  5 OPP outlets reported it
  2 IND outlets reported it
  1 DRV outlet reported it
  1 CON outlet reported it

Important limitation:
  Coverage imbalance does not prove ideological suppression.
```

This final limitation should be part of the product design, not hidden in a methodology page.

---

# 19. Phase 14 — Search and Retrieval API

## Goal

Let the frontend retrieve:

- latest articles;
- events;
- source perspectives;
- topic feeds;
- blindspots;
- article search;
- source pages;
- event timelines.

## FastAPI modules

```text
api/
  routers/
    articles.py
    events.py
    outlets.py
    blindspots.py
    search.py
    summaries.py
    health.py
  schemas/
  services/
  dependencies/
```

## API examples

```text
GET /api/v1/events
GET /api/v1/events/{event_id}
GET /api/v1/events/{event_id}/coverage
GET /api/v1/events/{event_id}/blindspot
GET /api/v1/articles/{article_id}
GET /api/v1/outlets
GET /api/v1/search?q=...
GET /api/v1/trending
GET /api/v1/health
GET /api/v1/ready
```

## API principles

- versioned endpoints;
- Pydantic schemas;
- pagination;
- server-side filtering;
- explicit sort order;
- consistent error envelopes;
- request IDs;
- structured logging;
- cache headers where appropriate;
- no direct DB access from frontend.

---

# 20. Phase 15 — Frontend Product Design

## Stack

**Next.js + TypeScript**

Core pages:

```text
/
/events/{id}
/blindspots
/search
/outlets/{id}
/topics/{topic}
/about/methodology
/about/sources
```

## Home page

Sections:

1. Top events
2. Blindspots
3. Fast-moving stories
4. Tamil / English toggle
5. Orientation distribution snapshot
6. Latest articles

## Event page

Primary experience:

```text
EVENT TITLE

What happened?
Neutral summary

Coverage breakdown
[DRV] [OPP] [CON] [IND]

HEADLINES
DRV → ...
OPP → ...
CON → ...
IND → ...

WHAT IS COMMON?
...

WHAT DIFFERS?
...

CLAIMS / EVIDENCE
...

TIMELINE
...

SOURCE ARTICLES
[Open original]
```

## Bias visualization

Never use color alone.

Always pair orientation colors with:

- text labels;
- icons or shape indicators;
- accessible contrast;
- tooltips;
- legend.

The user should understand the data without needing to know the color scheme.

## Blindspot page

Card:

```text
⚠ Coverage imbalance

Event
Dominant orientation
Coverage distribution
Why flagged
How many outlets
Last updated
```

---

# 21. Phase 16 — Bilingual Architecture

## Goal

Tamil and English must be first-class languages, not English UI translated at the very end.

## UI

Use i18n keys:

```json
{
  "event.summary": {
    "ta": "சுருக்கம்",
    "en": "Summary"
  }
}
```

## Data

Store source-native content.

Generated fields:

```text
summary_ta
summary_en
```

Do not discard Tamil when producing English.

## Translation policy

When translation is generated:

```text
source language
translation model
model revision
translation direction
translation confidence
```

Keep the original available in every UI view.

## Cross-lingual consistency test

For a Tamil article and English rendering:

- same key entities;
- same dates;
- same numbers;
- same claim polarity;
- same named roles;
- no dropped negation.

---

# 22. Phase 17 — Evaluation Framework

Evaluation is not a final phase. It begins as soon as each ML component exists.

## 22.1 Master evaluation matrix

| Component | Gold data | Primary metrics | Product metric |
|---|---|---|---|
| RSS ingestion | feed logs | success rate, freshness | stale feed rate |
| Extraction | human article samples | precision/recall of body, quality score | valid article rate |
| Language ID | labeled samples | accuracy, macro F1 | wrong-language rate |
| NER | annotated spans | precision/recall/F1 | entity recall for events |
| Embeddings | paired articles | Recall@k, MRR, nDCG | same-event retrieval |
| Clustering | gold event IDs | ARI/NMI/B-cubed | false merge rate |
| Topics | multilabel dataset | macro/micro F1 | browse usefulness |
| Claim extraction | claim annotations | span F1, classification F1 | evidence coverage |
| Summarization | human refs | ROUGE/BERTScore + human eval | factuality/hallucination |
| Translation | bilingual references | BLEU/chrF + human eval | entity/number preservation |
| Blindspot engine | reviewed event set | precision/recall/F1 | useful signal rate |
| API | integration tests | error rate, latency | SLO compliance |
| Frontend | task tests | completion rate | user comprehension |

## 22.2 Dataset strategy

Create three distinct datasets:

### Train/development

Used for model tuning.

### Validation

Used for hyperparameter and threshold selection.

### Test

Frozen and never tuned against.

Split temporally where possible.

Example:

```text
train: Jan–Jun
validation: Jul
test: Aug
```

This is better than a random split when evaluating a news system because random splits can leak recurring events and outlet styles across sets.

## 22.3 Human annotation workflow

Build an annotation tool or spreadsheet first.

Annotate:

- event identity;
- entities;
- claims;
- framing signals;
- summary quality;
- bilingual faithfulness;
- blindspot validity.

Every annotation record includes:

```text
annotator_id
sample_id
label
confidence
rationale
created_at
```

## 22.4 Model-selection principle

Do not select the model with the best single metric.

Use a weighted acceptance rule:

```text
quality gate:
  factuality >= threshold
  hallucination <= threshold
  event-recall >= threshold
  latency <= threshold
  RAM <= local budget
```

Then select the best Pareto trade-off.

---

# 23. Phase 18 — Testing Strategy

## Unit tests

Test pure functions:

- URL canonicalization;
- title normalization;
- feed parsing;
- hash generation;
- entity normalization;
- scoring formulas;
- blindspot calculations;
- serialization.

## Integration tests

Run real containerized dependencies:

```text
Postgres
Redis
API
worker
```

Test:

```text
feed → DB → task → article → NLP → event → API
```

## Contract tests

The API schema should be tested independently from frontend assumptions.

## Regression tests

Maintain known examples:

```text
known_feed.xml
known_article.html
known_event.json
known_summary.json
```

Every major refactor runs these fixtures.

## Failure injection

Intentionally simulate:

- RSS timeout;
- invalid XML;
- 404 article;
- 429 rate limit;
- 500 server error;
- HTML parser failure;
- database restart;
- Redis restart;
- worker restart;
- model load failure;
- corrupt article text.

A production-like system is not demonstrated by the happy path.

---

# 24. Phase 19 — Celery Task Architecture

## Queue separation

Use queues by workload:

```text
feeds
extraction
nlp_light
nlp_heavy
clustering
summarization
maintenance
```

This prevents a slow summarization task from blocking ingestion.

## Task chain

```text
fetch_feed
   ↓
normalize_article
   ↓
extract_article
   ↓
clean_article
   ↓
detect_language
   ↓
extract_entities
   ↓
embed_article
   ↓
assign_event
   ↓
recompute_event
   ↓
update_blindspot
   ↓
refresh_frontend_cache
```

Only advance when the prior task reports a valid state.

## Idempotency

Each task must be safe to retry.

Example:

```python
@task(bind=True, autoretry_for=(TimeoutError,), retry_backoff=True)
def extract_article(self, article_id):
    ...
```

Use unique constraints and `upsert` patterns to prevent duplicate inserts.

---

# 25. Phase 20 — Redis Strategy

Redis has three initial jobs:

1. Celery broker
2. optional Celery result backend
3. short-lived application cache

Do not make Redis the source of truth.

PostgreSQL remains authoritative.

Cache examples:

```text
home:top_events
trending:24h
blindspots:24h
event:{id}:coverage
```

Use TTLs.

---

# 26. Phase 21 — Observability

## Metrics

Every service exposes metrics.

### Ingestion

```text
feeds_total
feeds_success_total
feeds_failure_total
articles_discovered_total
articles_extracted_total
articles_failed_total
feed_freshness_seconds
```

### NLP

```text
embedding_latency_seconds
ner_latency_seconds
summary_latency_seconds
model_load_seconds
model_memory_bytes
```

### API

```text
http_requests_total
http_request_duration_seconds
http_errors_total
```

### Product

```text
events_created_total
clusters_recomputed_total
blindspots_created_total
```

## Logs

Use structured JSON logs:

```json
{
  "timestamp": "...",
  "service": "worker",
  "task": "extract_article",
  "article_id": 123,
  "attempt": 2,
  "status": "failed",
  "error_code": "HTTP_TIMEOUT"
}
```

Never rely on free-form console text for debugging a production workflow.

---

# 27. Phase 22 — Security

## Minimum controls

- secrets in `.env`, never Git;
- least-privilege DB user;
- parameterized SQL / ORM;
- input validation;
- URL allow/deny checks where applicable;
- SSRF protections for server-side URL retrieval;
- request timeouts;
- size limits;
- rate limiting;
- sanitized HTML;
- Content Security Policy in production;
- dependency vulnerability scans.

## SSRF is especially important

Because the backend fetches URLs, never accept arbitrary server-side URLs from users without validation.

Protect against:

```text
localhost
127.0.0.1
::1
RFC1918 addresses
cloud metadata endpoints
internal DNS names
```

Use an outbound fetch layer with policy enforcement.

---

# 28. Phase 23 — Copyright and Source Attribution

The product should primarily display metadata, snippets, derived analysis, and links back to the original publishers rather than becoming a replacement archive of publisher content.

Design rules:

- prominently link original source;
- preserve publisher name;
- display publication time;
- avoid unnecessary reproduction of entire articles in the public UI;
- maintain a documented content-retention policy;
- respect robots.txt / publisher constraints where applicable;
- rate-limit crawling;
- identify the project user agent;
- record extraction provenance.

Legal requirements vary by jurisdiction; this project journal is an engineering specification, not legal advice.

---

# 29. Phase 24 — CI/CD

GitHub Actions pipeline:

```text
push / PR
  ↓
ruff / formatter
  ↓
mypy / type checks
  ↓
pytest
  ↓
Docker build
  ↓
container integration tests
  ↓
security/dependency scan
  ↓
artifact build
```

## Branch model

```text
main       → deployable
feature/*  → development
```

Avoid long-lived branches.

## Commit convention

```text
feat:
fix:
refactor:
test:
docs:
infra:
```

---

# 30. Phase 25 — Local Docker Development

## Recommended directory layout

```text
veritas_lens/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
├── JOURNAL.md
├── rules.md
├── implementation_plan.md
├── ARCHITECTURE.md
├── DATA_DICTIONARY.md
├── EVALUATION.md
├── config/
│   ├── sources.yaml
│   ├── outlet_bias.yaml
│   ├── topics.yaml
│   └── models.yaml
├── database/
│   ├── schema.sql
│   ├── migrations/
│   └── init/
│       └── 01_init.sh
├── services/
│   ├── ingestion/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── app/
│   │       ├── main.py
│   │       ├── config.py
│   │       ├── tasks.py
│   │       ├── rss_fetcher.py
│   │       ├── extractor.py
│   │       ├── cleaner.py
│   │       ├── language.py
│   │       ├── embedder.py
│   │       ├── ner.py
│   │       ├── clustering.py
│   │       ├── summarizer.py
│   │       └── db.py
│   └── api/
│       ├── Dockerfile
│       └── app/
├── frontend/
│   ├── package.json
│   ├── next.config.ts
│   └── src/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   └── evaluation/
├── observability/
│   ├── prometheus.yml
│   └── grafana/
└── docs/
    ├── model_cards/
    ├── architecture/
    └── runbooks/
```

This expands the original proposed structure while preserving its core ingestion modules and configuration files. fileciteturn0file0L57-L81

---

# 31. Phase 26 — Model Packaging and Local Resource Budget

## Principle

Do not download five large models before measuring whether one smaller model is sufficient.

## Initial model stack

| Task | Default candidate | Reason |
|---|---|---|
| embeddings | `intfloat/multilingual-e5-small` | 384-d multilingual baseline |
| NER | `ai4bharat/IndicNER` | Tamil-specific Indian-language support |
| generation | `ai4bharat/IndicBART` | Tamil + English, smaller than mT5-base |
| translation | IndicTrans2 distilled 200M | local bilingual translation |
| topic classifier | embeddings + taxonomy first | no dedicated model required initially |
| event clustering | HDBSCAN + feature fusion | no language model required |

## Model-comparison track

Keep candidate models in `config/models.yaml` and run benchmark jobs before promotion.

```yaml
embedding:
  production: intfloat/multilingual-e5-small
  challengers:
    - Tamil-ai/tamil-embed-base
    - BAAI/bge-m3

ner:
  production: ai4bharat/IndicNER

generation:
  production: ai4bharat/IndicBART
  challengers:
    - google/mt5-small
```

## Quantization

Later evaluate:

- ONNX Runtime;
- dynamic quantization;
- int8 where quality permits;
- CPU inference;
- GPU inference if available.

Never quantize first and benchmark later. Benchmark full precision first, then measure quality loss.

---

# 32. Phase 27 — Database Optimization

For pgvector:

- begin with exact search;
- build a gold retrieval benchmark;
- add HNSW once the article volume justifies it;
- compare recall of approximate search against exact search.

pgvector explicitly recommends monitoring recall by comparing approximate results to exact search, and supports HNSW/IVFFlat tuning. citeturn343013search1

For PostgreSQL full-text search:

- use `tsvector`;
- use GIN where appropriate;
- add filters on outlet, date, language, topic, event.

PostgreSQL documentation describes indexed ranking, highlighting, and GIN/GiST text-search indexes. citeturn978058search1turn978058search8

---

# 33. Phase 28 — Product Intelligence Features to Add

The user's original idea already contains event comparison and blindspots. These features can make the project feel like a real product without abandoning the learning goals.

## Essential additions

### 1. Coverage timeline

Show when each orientation first reported the event.

```text
08:10  DRV
09:00  IND
11:20  OPP
14:05  CON
```

This is more informative than article count alone.

### 2. Headline evolution

Track how headlines change as an event develops.

### 3. Common facts / divergent facts

```text
COMMON ACROSS 8 SOURCES
...

ONLY IN 2 SOURCES
...
```

### 4. Source diversity score

A blindspot should be stronger when it appears in several independent outlets rather than many syndicated copies of one wire story.

### 5. Story origin graph

Detect whether many Tamil sites copied the same source material.

### 6. Quote network

Show which political figures dominate the quotation patterns.

### 7. Event timeline

Sequence claims and updates over time.

### 8. Article update tracking

When an article changes, store a version hash and timestamp.

### 9. "Why am I seeing this?" explanation

Show:

```text
You are seeing this story because:
  8 sources cover the same event
  3 orientation buckets are represented
  story has strong recent growth
```

### 10. Source profile

For each outlet:

- orientation provenance;
- publishing volume;
- topical distribution;
- average event age at publication;
- correction/update patterns where data exists;
- external factuality ratings where available.

---

# 34. Advanced Features for Later Phases

## A. Claim contradiction graph

```text
Claim A  ←→ Claim B
```

Display whether sources:

- agree;
- partially agree;
- disagree;
- discuss different sub-events.

## B. Story trajectory

Track an event over multiple days.

```text
BREAKING
  ↓
INITIAL REPORTS
  ↓
OFFICIAL RESPONSE
  ↓
OPPOSITION RESPONSE
  ↓
INVESTIGATION
  ↓
FOLLOW-UP
```

## C. Source reliability calibration

Do not infer factuality from ideology.

Build a separate evidence-driven source-quality layer if reliable external factuality signals exist.

Ground News itself treats factuality separately from political bias. citeturn343013search0turn343013search7

## D. User personalization

Later, users could choose:

```text
Show me more perspectives I don't usually read.
```

But personalization should never silently remove alternative sources.

## E. Alerting

Examples:

- event suddenly gets large coverage;
- blindspot score crosses a threshold;
- new orientation reports an event for the first time;
- article update detected.

---

# 35. Phase 29 — Production Deployment

## Local

```text
docker compose up -d
```

## Production target

A small VPS or cloud VM can initially host:

```text
reverse proxy
API
worker
beat
Redis
PostgreSQL
frontend
```

ML inference may later be split to a dedicated machine or GPU service.

## Production components

```text
Internet
  ↓
Cloudflare / reverse proxy
  ↓
Next.js
  ↓
FastAPI
  ↓
PostgreSQL / Redis
  ↓
Celery workers
```

## Backups

Daily PostgreSQL backups.

Retain:

- database dumps;
- configuration;
- migration versions;
- model manifest;
- evaluation reports.

Never rely on a Docker volume alone as a backup strategy.

---

# 36. Phase 30 — Health, Readiness, and Runbooks

Every service gets:

```text
/health
/ready
```

Readiness differs from liveness.

Example:

```text
/health = process responds
/ready  = process + DB + Redis + required model available
```

Docker Compose can gate startup on dependency health. citeturn978058search0turn978058search2

## Runbooks

Create:

```text
runbooks/
  rss-feed-failure.md
  database-recovery.md
  redis-recovery.md
  model-download-failure.md
  extraction-regression.md
  event-cluster-regression.md
  deployment-rollback.md
```

---

# 37. Phase 31 — Project Milestones / Gates

## Gate 0 — Architecture

```text
[ ] product requirements frozen
[ ] taxonomy defined
[ ] schema reviewed
[ ] source governance defined
```

## Gate 1 — Ingestion

```text
[ ] Docker boots
[ ] RSS fetch works
[ ] feed health visible
[ ] dedupe works
[ ] articles stored
```

## Gate 2 — NLP foundation

```text
[ ] language detection
[ ] embeddings
[ ] NER
[ ] evaluation dataset
```

## Gate 3 — Event intelligence

```text
[ ] event clustering
[ ] event evaluation
[ ] event API
```

## Gate 4 — Comparison

```text
[ ] source orientation provenance
[ ] headline comparison
[ ] common/different claims
```

## Gate 5 — Summarization

```text
[ ] article summaries
[ ] event summary
[ ] Tamil summary
[ ] English summary
[ ] factuality tests
```

## Gate 6 — Blindspots

```text
[ ] coverage distribution
[ ] blindspot scoring
[ ] reviewed validation set
```

## Gate 7 — Product

```text
[ ] frontend
[ ] search
[ ] event pages
[ ] methodology page
[ ] source pages
```

## Gate 8 — Production

```text
[ ] monitoring
[ ] backups
[ ] failure recovery
[ ] CI/CD
[ ] security checks
[ ] public deployment
```

---

# 38. Phase-by-Phase Learning Objectives

This project is explicitly a learning project, so each phase must teach an AI engineer concept.

| Phase | What you learn |
|---|---|
| 0 | requirements and system design |
| 1 | networking, HTTP, RSS, APIs, scheduling |
| 2 | crawling, parsing, reliability |
| 3 | text preprocessing, Unicode, multilingual NLP |
| 4 | SQL, schema design, indexing, transactions |
| 5 | embeddings, vector search, similarity |
| 6 | transformers, token classification, NER |
| 7 | unsupervised ML, clustering, similarity graphs |
| 8 | classification and taxonomy design |
| 9 | data provenance, labeling, evaluation design |
| 10 | NLP feature engineering and interpretability |
| 11 | information extraction and structured prediction |
| 12 | seq2seq generation and hallucination control |
| 13 | analytical scoring and product heuristics |
| 14 | API design and backend engineering |
| 15 | frontend architecture and visualization |
| 16 | multilingual product design |
| 17 | ML evaluation and experimental design |
| 18 | testing and failure engineering |
| 19 | asynchronous systems and distributed workers |
| 20 | caching / broker architecture |
| 21 | observability and SRE concepts |
| 22 | application security |
| 23 | data governance and source attribution |
| 24 | CI/CD |
| 25 | containerization and code organization |
| 26 | model optimization and deployment |
| 27 | database performance |
| 29 | cloud deployment |
| 30 | reliability engineering |

This is why the project is valuable as an AI-engineering curriculum: ML is embedded in a real software system rather than existing as a notebook isolated from databases, networking, OS scheduling, APIs, security, frontend, and deployment.

---

# 39. Recommended Technology Stack

## Backend

```text
Python 3.12+
FastAPI
Pydantic
SQLAlchemy / asyncpg
Celery
Redis
httpx
feedparser
Trafilatura
```

## ML / NLP

```text
PyTorch
Transformers
Sentence Transformers
Hugging Face Datasets / Evaluate
scikit-learn
HDBSCAN
IndicNLP utilities where needed
```

## Database

```text
PostgreSQL 16
pgvector
PostgreSQL FTS
```

## Frontend

```text
Next.js
TypeScript
Tailwind CSS
Recharts / lightweight charting library
```

## DevOps

```text
Docker
Docker Compose
GitHub Actions
Prometheus
Grafana
Nginx or Caddy
```

## Testing

```text
pytest
pytest-asyncio
httpx test client
Playwright
```

## Quality

```text
ruff
mypy
pre-commit
```

Pin exact package versions in lockfiles once implementation starts.

---

# 40. Proposed Repository Architecture

```text
veritas_lens/
│
├── config/
├── database/
├── services/
│   ├── ingestion/
│   ├── nlp/
│   ├── intelligence/
│   └── api/
│
├── frontend/
├── models/
│   ├── manifests/
│   ├── adapters/
│   └── benchmarks/
│
├── datasets/
│   ├── raw/
│   ├── annotations/
│   └── processed/
│
├── tests/
├── observability/
├── scripts/
├── docs/
├── docker-compose.yml
├── .env.example
├── JOURNAL.md
├── implementation_plan.md
├── rules.md
└── README.md
```

Do not put notebooks in the production import path.

Use notebooks only under:

```text
experiments/
```

with exported results committed separately.

---

# 41. Model Experiment Protocol

Every model experiment must create a record:

```text
experiment_id
hypothesis
dataset_version
model
model_revision
task
parameters
hardware
runtime
metrics
failure_cases
winner
notes
```

Example:

```text
EXP-EMB-003

Hypothesis:
Tamil-ai/tamil-embed-base will reduce Tamil-English event retrieval errors compared with multilingual-e5-small.

Dataset:
EVENTPAIR-v1

Metrics:
Recall@10
MRR
False merge rate
CPU latency
RAM

Decision:
Keep E5-small unless Tamil embed improves Recall@10 by ≥ X without exceeding local RAM budget.
```

This converts model selection from opinion into engineering evidence.

---

# 42. Data Quality Dashboard

Build an internal dashboard before public launch.

Widgets:

```text
Feeds healthy / total
Articles last 1h
Articles last 24h
Extraction success rate
Embedding backlog
NER backlog
Clustering backlog
Summarization backlog
Events last 24h
Blindspot candidates
Unknown orientation sources
```

The dashboard is part of the product engineering, not an optional afterthought.

---

# 43. Freshness Strategy

News is time-sensitive.

Every article/event has:

```text
published_at
first_seen_at
ingested_at
processed_at
last_updated_at
```

Sort feeds using an explicit ranking formula:

```text
recency_score
× source_quality_adjustment
× event_velocity
```

Avoid using raw publish time alone.

---

# 44. Deduplication and Syndication Detection

This is especially important for blindspots.

Ten websites may publish near-identical agency copy, which should not count as ten independent editorial decisions.

Build a syndication similarity layer:

```text
text similarity
+ sentence overlap
+ quote overlap
+ identical sequence of paragraphs
```

Then define:

```text
source_count
independent_source_count
article_count
```

Blindspot calculations should use `independent_source_count` where possible.

---

# 45. Political Taxonomy Governance

The current taxonomy is useful for the project, but it must not be hard-coded into model assumptions.

Treat orientation as data:

```yaml
orientation_taxonomy:
  version: 1
  buckets:
    DRV:
      label_ta: "திராவிட சார்பு"
      label_en: "Pro-Dravidian"
    OPP:
      label_ta: "எதிர்க்கட்சி சார்பு"
      label_en: "Opposition"
    CON:
      label_ta: "பழமைவாதம்"
      label_en: "Conservative"
    IND:
      label_ta: "சுயாதீன / சார்பற்ற"
      label_en: "Independent"
```

Store taxonomy version with every derived analytical result.

If the taxonomy changes later, historical output should remain reproducible.

---

# 46. What "Bias Score" Actually Means in Veritas Lens

The phrase "bias rating" should be used carefully.

A source-level label can be called:

> **Source orientation**

An article-level computed quantity can be called:

> **Framing signal**

A story-level quantity can be called:

> **Coverage imbalance**

Do not put one number on an article and imply:

```text
AI says this article is 83% biased.
```

unless a properly validated model, definition, calibration method, and evaluation dataset exist.

The first product release should instead communicate:

```text
Source orientation: OPP

Observed framing signals:
- headline contains stronger negative framing than median event headline
- 3/4 direct quotes come from one side
- article emphasizes allegation X
- claim Y appears only in this source group
```

That is more defensible and more useful.

---

# 47. Ethical Guardrails

The product discusses politically sensitive content. Therefore:

- never hide sources because they are politically inconvenient;
- never automatically equate bias with falsehood;
- never infer political identity from one article;
- separate source orientation from factuality;
- label uncertainty;
- preserve links to original reporting;
- make methodology public;
- allow correction requests;
- log changes to outlet labels;
- audit whether the blindspot engine disproportionately flags one bucket because of source-count imbalance.

## Audit question

For every major release ask:

> Does the system's output reflect the data, or did our scoring rules encode our assumptions?

This should become a recurring model-governance test.

---

# 48. MVP Scope — Do Not Build Everything at Once

The product has a large surface area. The development sequence must stay strict.

## MVP-1

```text
Docker
PostgreSQL + pgvector
Redis
Celery + Beat
15+ RSS feeds
article extraction
cleaning
embeddings
basic API
```

## MVP-2

```text
NER
event clustering
event pages
orientation labels
headline comparison
```

## MVP-3

```text
summaries
Tamil/English generation
blindspots
search
```

## MVP-4

```text
observability
security
CI/CD
production deployment
advanced claims/framing
```

Do not begin frontend polish before the underlying event model works.

---

# 49. Current First Implementation Target

The immediate development target remains the original Phase 0+1 ingestion pipeline.

The current plan is:

```text
1. docker-compose.yml
2. PostgreSQL + pgvector
3. Redis
4. ingestion worker
5. sources.yaml
6. outlet_bias.yaml
7. schema.sql
8. Celery Beat every 15 minutes
9. RSS fetch
10. URL dedupe
11. Trafilatura extraction
12. clean text
13. multilingual embedding
14. article INSERT
15. health / failure state
```

The initial implementation blueprint already specifies this structure and the corresponding files such as `sources.yaml`, `outlet_bias.yaml`, `schema.sql`, `01_init.sh`, `rss_fetcher.py`, `extractor.py`, `embedder.py`, `db.py`, `config.py`, and `tasks.py`. fileciteturn0file0L57-L81

---

# 50. First Definition of Done

The first end-to-end milestone is complete only when the following passes:

```text
[ ] docker compose up works from a clean checkout
[ ] Postgres is healthy
[ ] Redis is healthy
[ ] worker is healthy
[ ] Beat is running exactly once
[ ] all configured feeds report status
[ ] at least 50 valid articles are stored
[ ] duplicate URLs are rejected
[ ] extraction failures are recorded
[ ] embeddings exist for successful articles
[ ] vector dimensions match schema
[ ] no worker silently loses failures
[ ] retries are observable
[ ] logs include article/source/task IDs
[ ] database can be backed up and restored
```

Only after this gate passes should NER and clustering become the active focus.

---

# 51. Master Roadmap

| Phase | Work | Status |
|---:|---|---|
| 0 | Product contract / governance | In progress |
| 1 | RSS ingestion | Current |
| 2 | Article extraction | Current |
| 3 | Cleaning / language | Planned |
| 4 | DB + pgvector | Current |
| 5 | Embeddings | Current |
| 6 | NER | Planned |
| 7 | Event clustering | Planned |
| 8 | Topic taxonomy | Planned |
| 9 | Orientation provenance | Planned |
| 10 | Framing analysis | Planned |
| 11 | Claim extraction | Planned |
| 12 | Summarization | Planned |
| 13 | Blindspots | Planned |
| 14 | FastAPI | Planned |
| 15 | Frontend | Planned |
| 16 | Bilingual product | Planned |
| 17 | Evaluation framework | Starts early; expands continuously |
| 18 | Testing | Continuous |
| 19 | Celery scaling | Planned |
| 20 | Redis caching | Planned |
| 21 | Observability | Planned |
| 22 | Security | Planned |
| 23 | Copyright/source governance | Planned |
| 24 | CI/CD | Planned |
| 25 | Docker production structure | Planned |
| 26 | Model optimization | Planned |
| 27 | DB performance | Planned |
| 28 | Advanced product intelligence | Later |
| 29 | Deployment | Later |
| 30 | Runbooks / reliability | Later |
| 31 | Final product release | Later |

The earlier implementation plan grouped the future work more coarsely into bias scoring, event clustering, frontend, summarization/intelligence, and hardening/deployment. This journal intentionally breaks those areas into smaller gates so the project can be built and learned sequentially. fileciteturn0file0L97-L105

---

# 52. Research References

## Product / media methodology

- Ground News — Rating System / Methodology: https://ground.news/rating-system
- Ground News — Media Bias: https://ground.news/media-bias
- Ground News — Blindspot explanation: https://ground.news/blindspot/about
- Ground News — FAQ: https://ground.news/frequently-asked-questions

Ground News explicitly distinguishes source bias, factuality, ownership, and Blindspot calculations. Its published methodology should be treated as product inspiration, not as a ready-made Tamil political methodology. 

## DravidianLangTech / Tamil NLP research

DravidianLangTech proceedings are useful for selecting benchmarks and designing failure analysis because the shared tasks repeatedly expose the difficulty of Tamil and other low-resource Dravidian languages. The 2024 proceedings include shared tasks on code-mixed Tamil sentiment analysis and fake-news detection, while the 2025 proceedings include Tamil-focused transformer experiments and AI-generated-content detection. These works also demonstrate why macro-F1, per-class analysis, and careful dataset design matter when classes are imbalanced or language resources are limited. citeturn842324search0turn842324search1

Useful starting points:

- DravidianLangTech 2025 proceedings: https://aclanthology.org/events/dravidianlangtech-2025/
- DravidianLangTech 2024 proceedings: https://aclanthology.org/events/dravidianlangtech-2024/
- DravidianLangTech 2023 proceedings: https://aclanthology.org/events/dravidianlangtech-2023/

## Indic NLP / models

- AI4Bharat IndicNER: https://huggingface.co/ai4bharat/IndicNER
- AI4Bharat IndicBART: https://huggingface.co/ai4bharat/IndicBART
- AI4Bharat MultiIndicHeadlineGeneration: https://huggingface.co/ai4bharat/MultiIndicHeadlineGeneration
- AI4Bharat IndicTrans2: https://github.com/AI4Bharat/IndicTrans2
- AI4Bharat IndicTrans2 distilled 200M: https://huggingface.co/ai4bharat/indictrans2-indic-en-dist-200M
- AI4Bharat model collection: https://huggingface.co/ai4bharat/collections
- AI4Bharat models portal: https://models.ai4bharat.org/

## Embedding / retrieval

- multilingual-e5-small: https://huggingface.co/intfloat/multilingual-e5-small
- Tamil-ai Tamil Embed Base: https://huggingface.co/Tamil-ai/tamil-embed-base
- BGE-M3: https://huggingface.co/BAAI/bge-m3
- sentence-transformers multilingual MiniLM: https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

## Infrastructure

- pgvector: https://github.com/pgvector/pgvector
- PostgreSQL 16 full-text search: https://www.postgresql.org/docs/16/textsearch.html
- Celery periodic tasks: https://docs.celeryq.dev/en/main/userguide/periodic-tasks.html
- Docker Compose health/dependencies: https://docs.docker.com/compose/how-tos/startup-order/

## Evaluation / methodology references to consult during implementation

- scikit-learn clustering metrics documentation
- HDBSCAN documentation
- Hugging Face Evaluate
- BERTScore
- ROUGE
- SacreBLEU / chrF
- DravidianLangTech shared tasks and ACL Anthology papers involving Tamil NLP
- relevant Tamil/Indic NER, summarization, sentiment, offensive-language and semantic-similarity datasets

---

# 53. Open Research Questions

These should remain explicit instead of being hidden assumptions.

1. Which independent sources provide defensible Tamil outlet orientation labels?
2. How should `OPP` be represented when TVK, AIADMK, and BJP are politically distinct rather than one homogeneous ideology?
3. How should `CON` be operationalized and validated?
4. Which embedding model performs best for Tamil↔English event matching on our own benchmark?
5. How much does NER improve cluster quality?
6. How do we distinguish a new event from a follow-up story?
7. How should syndicated wire-copy be counted in blindspot analysis?
8. What minimum number of independent sources produces a meaningful blindspot?
9. How can we measure framing without encoding partisan assumptions into the model?
10. Which summarization model produces the lowest unsupported-claim rate on Tamil political news?
11. Is translation-first summarization better or worse than native Tamil summarization?
12. How should article updates be versioned?
13. Which storage strategy remains practical after 1M+ articles?
14. Which pieces should stay local and which should move to cloud inference?
15. What is the minimum hardware needed for acceptable daily processing latency?

These questions should produce experiments, not premature architecture decisions.

---

# 54. Final Product Definition

At maturity, Veritas Lens should be able to take this:

```text
15–50+ Tamil/English news outlets
RSS feeds
continuous article updates
```

and produce this:

```text
                    VERITAS LENS

EVENT: [What happened]

Neutral summary

Coverage
DRV ████████
OPP ████
CON ██
IND ███

How headlines differ

What most sources agree on

What only some sources report

Timeline

Quotes

Claims

Blindspot signal

Source orientation + provenance

Original articles
```

The real engineering achievement is not the visual dashboard.

It is the complete chain:

```text
Internet
  ↓
HTTP / RSS
  ↓
Scheduling
  ↓
Async workers
  ↓
Data extraction
  ↓
Normalization
  ↓
PostgreSQL
  ↓
Vector search
  ↓
NER
  ↓
Embeddings
  ↓
Event clustering
  ↓
Information extraction
  ↓
Summarization
  ↓
Coverage analysis
  ↓
Blindspot detection
  ↓
FastAPI
  ↓
Next.js
  ↓
Docker
  ↓
Monitoring
  ↓
Deployment
```

That chain is the actual AI-engineering curriculum this project is meant to teach.

---

# 55. Journal Protocol Going Forward

For each implementation session, append a journal entry with this format:

```markdown
## [YYYY-MM-DD HH:MM IST] — <milestone>

### Goal

### What changed

### Files changed

### Technical decision

### Why

### Test evidence

### Failure / bug encountered

### What I learned

### Next gate

### Metrics / screenshots / logs
```

Never mark a phase complete because the code "looks right".

Mark it complete only when its acceptance tests, failure cases, and evaluation evidence pass.

---

# 56. Current Decision Register

| Decision | Status | Rationale |
|---|---|---|
| Docker-first | Approved | reproducible services and deployment learning |
| PostgreSQL + pgvector | Approved | relational + semantic data in one system |
| Redis + Celery | Approved | scheduled/background ingestion and NLP |
| RSS-first ingestion | Approved | structured discovery layer |
| Trafilatura-first extraction | Approved | practical article extraction baseline |
| Multilingual embedding | Approved | Tamil + English event matching |
| NER + embeddings for clustering | Approved | NER enriches, embeddings provide semantic grouping |
| Source-level orientation provenance | Approved | avoids ungrounded article bias classification |
| Blindspot engine | Approved | core product differentiator |
| FastAPI | Approved | clean API layer |
| Next.js + TypeScript | Approved | product-grade frontend |
| IndicNER candidate | Approved for benchmark | Tamil-capable Indian NER baseline |
| multilingual-e5-small candidate | Approved for benchmark | small local multilingual retrieval baseline |
| IndicBART candidate | Approved for benchmark | Tamil/English generation baseline |
| IndicTrans2 distilled | Approved for benchmark | bilingual translation with smaller model |
| HDBSCAN | Approved for benchmark | unknown cluster count + noise handling |
| Prometheus/Grafana | Planned | operational visibility |

---

# 57. Immediate Next Step

Do **not** jump to the bias model, frontend, or summarizer yet.

The next implementation gate is:

```text
PHASE 0/1

Create the Docker Compose stack
↓
Create Postgres schema
↓
Create source registry
↓
Create Celery Beat
↓
Fetch RSS
↓
Persist metadata
↓
Extract article
↓
Generate embedding
↓
Store article + vector
↓
Prove retries / dedupe / health
```

Once that pipeline is reliable, every later subsystem has a stable foundation to build on.
