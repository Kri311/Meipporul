# Model evaluation

Evaluation outputs are written to `src/backend/evaluation/results/` as CSV,
JSON and PNG charts. Add only reviewed human labels to the templates in
`annotations/`; weakly auto-annotated labels are reported separately and must
not be presented as gold-standard quality.

- NER: the fine-tuning/evaluation scripts report exact BIO-span precision,
  recall, micro/macro F1, token accuracy, per-entity support, and epoch plots.
  Existing auto-annotated validation labels are weak supervision, not human
  gold.
- Event clustering: label article pairs with `guid_a,guid_b,same_event`. The
  evaluator reports pairwise accuracy, positive precision/recall/F1, binary
  macro scores, and language-separated plots from current database cluster IDs.
- Summarization: provide `language,article_guids,reference_summary` and use `|`
  between GUIDs in one event. The evaluator reports per-language macro ROUGE-1,
  ROUGE-2, ROUGE-L F1, and character n-gram chrF.

The current summary implementation is extractive and has no trainable weights;
ROUGE/chrF evaluation measures it against references but does not fine-tune it.
Embedding generation uses a pretrained model, and clustering has no train step;
event-pair labels are required before event-quality scores or a supervised
embedding fine-tune can be claimed.
