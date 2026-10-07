"""
Veritas Lens — NER Fine-tuning Pipeline
========================================
Complete fine-tuning pipeline for Named Entity Recognition.

Pipeline Steps:
  1. prepare_data.py   → Extract articles from DB to JSON corpora
  2. auto_annotate.py  → Generate BIO-tagged training data (weak supervision)
  3. train.py          → Fine-tune MuRIL model on the annotated data
  4. predict.py        → Run ensemble inference (ML + Gazetteers + Rules)

All evaluation metrics are saved as CSV in the data/ subdirectory.
"""
