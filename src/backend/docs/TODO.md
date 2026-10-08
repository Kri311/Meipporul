# Pipeline status and next steps

The intended current contract and run commands are documented in the
repository README and ARTICLE_REPROCESSING.md. This list tracks remaining work;
it is not a claim that model quality has already been validated.

## Implemented in the current pipeline

- Shared Trafilatura article extraction and junk cleanup for RSS and historical
  reprocessing.
- Separate headline/description/body fields; clean_text is JSON, not a
  hand-built quoted string.
- Tamil-oriented English-sentence filtering and party acronym normalization.
- Location capture from datelines/TOI footers for NER.
- Multilingual 768-dimensional embedding configuration and parsed body input.
- English and Tamil source-grounded extractive event summary modules.
- Language-filtered event API responses and matching frontend lanes.

## Still required

- Evaluate NER precision/recall separately on reviewed Tamil and English sets;
  repair training labels and gazetteers based on measured errors.
- Add repeatable tests for the full 21-column CSV schema, scraper-cleaner
  fixtures per outlet, Tamil script purity, JSON quoting, and API language
  separation.
- Evaluate the current centroid reuse and 30-day maximum date-gap defaults;
  measure false merges/splits and tune against reviewed event timelines.
- Replace placeholder/legacy metadata model labels with values read from
  runtime configuration.
- Review all enabled source URLs and their allowed fetch cadence.
- Validate summary factuality and coverage with editors in both languages.

## Runtime sequence

1. Fetch and extract RSS articles.
2. Run NER on article body text and retain extracted dateline locations.
3. Generate/update embeddings from the headline plus parsed body.
4. Cluster semantically related coverage and assign topics.
5. Generate native-language event summaries and export enriched CSV data.

Sentence embeddings are not machine translation. Current language views retain
the original article language; any cross-language article translation requires
a separately specified translation workflow and quality review.
