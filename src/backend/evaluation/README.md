# Model and pipeline evaluation

Evaluation outputs are written under `src/backend/evaluation/results/` as
appropriate CSV, JSON, and PNG artifacts. Use reviewed human labels as the
gold answer key. Automatically generated NER/topic labels are weak supervision
and must not be reported as gold-standard model quality.

## NER

Fine-tuning and evaluation code is in `src/backend/ner_pipeline/finetune/`.
The evaluator reports exact BIO-span precision, recall, micro/macro F1,
token accuracy, per-entity support, and language-separated scores. English
and Tamil results should be inspected separately. A reliable score requires
reviewed gold BIO labels; scores against auto-annotator output measure
agreement with that teacher/rule pipeline, not correctness against reality.

## Event clustering

Annotate pairs in `annotations/event_pairs.csv` with
`guid_a,guid_b,same_event` (canonical URLs may be used in the ID fields).
Include positive and negative pairs and review them independently. Run:

```bash
PYTHONPATH=./src python src/backend/evaluation/evaluate_event_clustering.py
```

The evaluator compares pair labels with current PostgreSQL cluster assignments
and reports pairwise accuracy, positive precision/recall/F1, binary macro
scores, and language-separated results where supported. It evaluates the
current E5+DBSCAN clustering; it does not train the clustering model.
Threshold changes should be compared on the same frozen reviewed pair set.

## Topic classification

Prepare a bilingual annotation sheet with
`./scripts/prepare_topic_labels.sh`, review/correct the `topic` labels, then
run `./scripts/train_topic_classifier.sh <labels.csv>`. The comparison records
E5-only versus E5+NER performance, language-separated metrics, and the selected
model under `src/backend/models/topic_classifier/`. Weak `suggested_topic`
labels should be manually corrected before treating metrics as an estimate of
real-world accuracy.

## Summarisation

The summariser is fine-tunable using reviewed bilingual article bodies and
multi-bullet references. Prepare examples with
`./scripts/prepare_summary_labels.sh`; fill in 3–7 factual bullets in the
article's language, and group related stories in `event_group` so event-level
coverage does not leak across train/validation splits. Fine-tune with
`./scripts/train_summarizer.sh <labels.csv>`. The trainer records validation
loss and dataset metadata with the LoRA adapter.

To measure generated summary quality, annotate
`annotations/summaries.csv` with `language,article_guids,reference_summary`
(use `|` between article GUIDs belonging to one event) and run:

```bash
PYTHONPATH=./src python src/backend/evaluation/evaluate_summarization.py
```

The evaluator reports per-language ROUGE-1/2/L F1 and character n-gram chrF
where the required packages and references are available. Automatic
extractive fallback bullets and abstractive model bullets should be evaluated
against the same human references; persisted summaries may need regeneration
after changing a model or evaluation configuration.

## Interpretation

An empty annotation template produces no meaningful quality score. Report
dataset size, language, class/entity support, and whether labels are human
reviewed or weakly generated alongside each metric. Keep validation examples
independent from model fitting and avoid using the same event in both training
and validation data.
