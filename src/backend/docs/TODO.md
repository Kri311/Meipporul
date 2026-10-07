## TODO
[] fine tune NER in order to gather proper elements from Tamil news
[] automate feed fetch -> {deduplication, fetch news on desired topics, remove html parsing, remove emojis, advertisements, english text on tamil outlet} -> {fetch topic, vector embeddings, NER, cluster_id, event representation from NER} -> csv file

- vector embeddings, NER, cluster with NER, summarization

### NLP pipeline

- problem statement: NER entities are low in quality and most of them aren't detected properly
- aim: develop a pipeline which removes all the newline & whitespaces in bw text, removes tamil morphology (word with suffixes) and give just root word, remove designation in bw the entities, mismatch of NER entities
- so we'll develop a pipeline, which contains finetuned NER model for both tamil & english text. take use of ML prediction Gazetteers (Dictionaries) and context rules to guarantee a sure hit on NER entities and extract appropriate precision, recall, F1 score and macros scores also
- for tamil morphology - use indic-nlp-library or thamizhi-morph to extract root word before checking with Gazetters
- dont use ML part to predict dates
- Extract Person, Organization, Location, and Event using the ML model. Extract Date purely using Regex and Rule-based parsers (like Python's dateparser).
- okay let us implement this NLP pipeline in nlp/ directory.
we'll take existing base model for the NER for both tamil and english
implement the pipeline with ML prediction + gazzetteers + context rules and get the appropriate results metrics as discussed for both tamil and english