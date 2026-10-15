# Pipeline status and follow-up work

The current implementation and run commands are documented in the root
[`README.md`](../../../README.md) and [`REPORT.md`](../../../REPORT.md). This file
tracks remaining validation and operational tasks; it does not claim the
models have already been validated against gold data.

## Implemented pipeline

- RSS acquisition, page extraction, outlet-specific cleaning, canonical
  PostgreSQL persistence, and `trafiltura_preprocessed.csv` export.
- English/Tamil NER with optional fine-tuned MuRIL, baseline fallback,
  normalization, entity linking, and persisted article entities.
- Multilingual E5 embeddings with content/model change detection.
- Cosine-distance DBSCAN with language/date guards, bounded NER
  corroboration, and complete-link refinement to reduce chaining.
- E5 Logistic Regression topic classification, optional E5+NER fusion,
  selection metadata, and zero-shot/rule fallbacks.
- Persisted source-linked article bullet summaries and deterministic event
  bullet merging; model inference is not required on every event-page request.
- Root one-shot and recurring scripts that order fetch, cleanup, NER,
  embeddings/clustering, topic assignment, summaries, and exports.
- `--refresh-existing` backfill path for re-running NER and embeddings for the
  stored corpus, forcing summary regeneration, and exporting refreshed values.

## Follow-up validation

- Create a reviewed bilingual NER gold set and report per-language and
  per-entity precision, recall, and F1.
- Review topic suggestions and evaluate E5-only and E5+NER on a larger,
  balanced human-labeled set before changing the selected runtime model.
- Label same-event and different-event article pairs; tune DBSCAN thresholds
  using event-level precision/recall and check cluster member provenance.
- Create reviewed English and Tamil multi-bullet summary references; evaluate
  factuality, language correctness, coverage, ROUGE, and chrF before promoting
  a fine-tuned summarizer.
- Exercise a complete live cycle against the configured PostgreSQL database
  and GPU environment; verify that changes in article content invalidate the
  correct NER, embedding, cluster, and summary state.
- Monitor feed failures, article extraction quality, source image relevance,
  disk usage for checkpoints, and GPU memory during model training/inference.

## Current sequence

```text
RSS → cleanup and canonical export → NER → E5 embeddings → DBSCAN
    → article/event topics → per-article bullets → event bullet merge
    → event representation and final CSV → API/UI
```

Sentence embeddings are not translation. English and Tamil content remain in
their source language lanes; cross-language translation would need a separate
model and quality review.
