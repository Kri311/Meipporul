# Article extraction and export

This document describes the separate historical URL reprocessing utility.
For the live RSS → NER → E5/DBSCAN → topic → persisted summaries workflow,
use the repository [README](../../../README.md) and [implementation report](../../../REPORT.md).

The live RSS pipeline and historical reprocessor use Trafilatura to extract
article pages. RSS description is retained independently in description;
clean_text is serialized JSON in the shape {"actual headline":"article body"}.
The database/CSV title remains the headline. JSON encoding preserves quotes,
backslashes, and line breaks without manual escaping.

## Cleaning and language policy

- Headline markup and repeated headline text are removed from the body.
- Common navigation, subscription prompts, comment disclaimers, and outlet
  footer boilerplate are removed before serialization.
- The Times of India price footer is removed; a detected dateline/footer
  location is seeded into named_entities as LOCATION for later NER.
- Section labels such as "- Rape:" are removed; they are not mislabeled as
  geographic entities.
- A Tamil article is filtered sentence-by-sentence to omit English-only
  sentences; English political party acronyms are rendered in Tamil script
  (for example, TVK as தவெக and BJP as பாஜக).
- Body extraction is not shortened for display. The embedding model has its
  own token window, but this does not truncate the stored clean_text.

## Historical 2026 reprocessing

The reprocessor reads src/backend/data/raw_processed.csv and selects only
records whose published_at year is 2026. It fetches each canonical URL in
checkpoint batches, skips inaccessible/non-HTML pages and articles without a
usable body, and writes the final 21-column schema to
src/backend/data/trafiltura_processed.csv.

When the body is refreshed, old derived cluster_id and embedding values are
cleared. named_entities starts with any extracted
LOCATION; the NER pipeline can then enrich that value. description and other
source metadata are retained where available. Output is first written to a
sibling .tmp file and atomically replaces the CSV only after a successful run.
No record-count maximum is imposed by batch-size.

Run once from the repository root:

```bash
source venv/bin/activate
PYTHONPATH=./src python3 src/backend/scripts/reprocess_articles.py
```

Optional controls:

```bash
PYTHONPATH=./src python3 src/backend/scripts/reprocess_articles.py --batch-size 50 --timeout 20 --delay 0.2
```

Run as a finite background job:

```bash
bash src/backend/scripts/shell/start_reprocess_daemon.sh
tail -f logs/reprocess_daemon.log
```

The real-time RSS daemon is a separate, continuous process:

```bash
bash src/backend/scripts/shell/start_daemon.sh
tail -f logs/rss_daemon.log
bash src/backend/scripts/shell/stop_daemon.sh
```

If an already-generated export needs the latest local cleanup rules but does
not need another network fetch, rebuild its clean_text from the preserved
raw_text with:

```bash
PYTHONPATH=./src python3 src/backend/scripts/clean_processed_export.py
```

This preserves descriptions and extraction text, refreshes location entities,
and clears derived embeddings and cluster assignments because the body may
have changed.

## Validation checks

After completion, confirm the final file (not only the temporary checkpoint)
exists and has the exact 21-column header. Parse clean_text with a CSV reader
and JSON parser to verify every non-empty value is a one-entry object. Inspect
a sample from each language for script leakage, title duplication, disclaimer
text, and missing descriptions. Re-running semantic processing is required
before treating the cleared embedding and cluster columns as populated.
