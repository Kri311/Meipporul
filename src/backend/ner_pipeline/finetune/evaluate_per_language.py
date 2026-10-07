import os
import sys
import json
import csv
import logging
from datetime import datetime
import torch
import numpy as np
from transformers import (
    AutoTokenizer,
    AutoModelForTokenClassification,
    Trainer,
    TrainingArguments,
    DataCollatorForTokenClassification,
)
import transformers.utils.import_utils
transformers.utils.import_utils.check_torch_load_is_safe = lambda: None

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.ner_pipeline.finetune.config import (
    MODEL_DIR, DATA_DIR, DATASET_DIR,
    NUM_LABELS, ID2LABEL, LABEL2ID, MAX_SEQ_LENGTH
)
from backend.ner_pipeline.finetune.train import NERDataset, compute_metrics

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Language_Evaluator")

class FilteredNERDataset(NERDataset):
    def __init__(self, jsonl_path: str, tokenizer, target_language: str, max_length: int = MAX_SEQ_LENGTH):
        self.samples = []
        self.tokenizer = tokenizer
        self.max_length = max_length
        
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    if data.get("language") == target_language:
                        self.samples.append(data)
        logger.info(f"Loaded {len(self.samples)} {target_language} samples from {jsonl_path}")

def save_lang_metrics_csv(lang_metrics_dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(DATA_DIR, f"finetune_language_evaluation_{timestamp}.csv")
    
    rows = []
    for lang, metrics in lang_metrics_dict.items():
        for etype in ["PERSON", "ORGANIZATION", "LOCATION", "EVENT", "DATE"]:
            rows.append({
                "language": lang,
                "entity_type": etype,
                "precision": metrics.get(f"eval_{etype}_precision", 0),
                "recall": metrics.get(f"eval_{etype}_recall", 0),
                "f1_score": metrics.get(f"eval_{etype}_f1", 0),
                "support": metrics.get(f"eval_{etype}_support", 0),
            })
        
        rows.append({
            "language": lang,
            "entity_type": "MACRO_AVG",
            "precision": metrics.get("eval_macro_precision", 0),
            "recall": metrics.get("eval_macro_recall", 0),
            "f1_score": metrics.get("eval_macro_f1", 0),
            "support": sum(r["support"] for r in rows[-5:]),
        })
        
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["language", "entity_type", "precision", "recall", "f1_score", "support"])
        writer.writeheader()
        writer.writerows(rows)
        
    logger.info(f"Language evaluation metrics saved to {csv_path}")

def evaluate_languages():
    best_model_dir = os.path.join(MODEL_DIR, "best")
    if not os.path.exists(best_model_dir):
        logger.error(f"Best model not found at {best_model_dir}. Run training first.")
        return
        
    tokenizer = AutoTokenizer.from_pretrained(best_model_dir)
    model = AutoModelForTokenClassification.from_pretrained(best_model_dir)
    
    val_path = os.path.join(DATASET_DIR, "val.jsonl")
    
    data_collator = DataCollatorForTokenClassification(tokenizer=tokenizer, padding=True, max_length=MAX_SEQ_LENGTH)
    
    args = TrainingArguments(output_dir="/tmp", per_device_eval_batch_size=16, report_to="none")
    trainer = Trainer(
        model=model,
        args=args,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
    )
    
    lang_metrics_dict = {}
    
    for lang in ['ta', 'en', 'combined']:
        logger.info(f"Evaluating language: {lang}")
        
        if lang == 'combined':
            dataset = NERDataset(val_path, tokenizer, max_length=MAX_SEQ_LENGTH)
        else:
            dataset = FilteredNERDataset(val_path, tokenizer, target_language=lang)
            
        if len(dataset) == 0:
            logger.info(f"No validation samples found for {lang}. Skipping.")
            continue
            
        metrics = trainer.evaluate(eval_dataset=dataset)
        lang_metrics_dict[lang] = metrics
        
        logger.info(f"--- {lang.upper()} Results ---")
        logger.info(f"Macro F1: {metrics.get('eval_macro_f1', 0)}")
        logger.info(f"Accuracy: {metrics.get('eval_token_accuracy', 0)}")
        
    save_lang_metrics_csv(lang_metrics_dict)
    
if __name__ == "__main__":
    evaluate_languages()
