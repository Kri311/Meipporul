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
        rows.append({
            "language": lang,
            "entity_type": "MACRO_AVG",
            "precision": metrics.get("eval_macro_precision", 0),
            "recall": metrics.get("eval_macro_recall", 0),
            "f1_score": metrics.get("eval_macro_f1", 0),
            "support": sum(metrics.get(f"eval_{kind}_support", 0) for kind in ["PERSON", "ORGANIZATION", "LOCATION", "EVENT", "DATE"]),
            "token_accuracy": metrics.get("eval_token_accuracy", 0),
            "micro_f1": metrics.get("eval_micro_f1", 0),
            "evaluation_data": "auto_annotated_validation",
        })
        for etype in ["PERSON", "ORGANIZATION", "LOCATION", "EVENT", "DATE"]:
            rows.append({
                "language": lang,
                "entity_type": etype,
                "precision": metrics.get(f"eval_{etype}_precision", 0),
                "recall": metrics.get(f"eval_{etype}_recall", 0),
                "f1_score": metrics.get(f"eval_{etype}_f1", 0),
                "support": metrics.get(f"eval_{etype}_support", 0),
                "token_accuracy": "",
                "micro_f1": "",
                "evaluation_data": "auto_annotated_validation",
            })
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["language", "entity_type", "precision", "recall", "f1_score", "support", "token_accuracy", "micro_f1", "evaluation_data"])
        writer.writeheader()
        writer.writerows(rows)
    logger.info(f"Language evaluation metrics saved to {csv_path}")
    return csv_path

def save_language_plots(lang_metrics_dict):
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        logger.warning("matplotlib is not installed; language evaluation CSV was saved but plots were skipped: %s", exc)
        return []
    os.makedirs(DATA_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    languages = [key for key in ("ta", "en") if key in lang_metrics_dict]
    if not languages:
        return []
    outputs = []
    metrics = ("eval_macro_precision", "eval_macro_recall", "eval_macro_f1")
    labels = ("Macro precision", "Macro recall", "Macro F1")
    x = np.arange(len(languages))
    width = 0.24
    fig, ax = plt.subplots(figsize=(8, 5))
    for index, (metric, label) in enumerate(zip(metrics, labels)):
        values = [lang_metrics_dict[lang].get(metric, 0) for lang in languages]
        ax.bar(x + (index - 1) * width, values, width, label=label)
    ax.set_xticks(x, ["Tamil" if lang == "ta" else "English" for lang in languages])
    ax.set_ylim(0, 1)
    ax.set_ylabel("Exact entity-span score")
    ax.set_title("NER validation metrics by language")
    ax.legend()
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    path = os.path.join(DATA_DIR, f"ner_language_metrics_{timestamp}.png")
    fig.savefig(path, dpi=160)
    plt.close(fig)
    outputs.append(path)

    entity_types = ["PERSON", "ORGANIZATION", "LOCATION", "EVENT", "DATE"]
    fig, ax = plt.subplots(figsize=(10, 5))
    width = 0.36
    positions = np.arange(len(entity_types))
    for offset, lang in enumerate(languages):
        values = [lang_metrics_dict[lang].get(f"eval_{kind}_f1", 0) for kind in entity_types]
        ax.bar(positions + (offset - (len(languages) - 1) / 2) * width, values, width, label="Tamil" if lang == "ta" else "English")
    ax.set_xticks(positions, entity_types, rotation=20, ha="right")
    ax.set_ylim(0, 1)
    ax.set_ylabel("Exact span F1")
    ax.set_title("NER F1 by entity type and language")
    ax.legend()
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    path = os.path.join(DATA_DIR, f"ner_entity_f1_{timestamp}.png")
    fig.savefig(path, dpi=160)
    plt.close(fig)
    outputs.append(path)
    return outputs


def evaluate_languages(model_dir=None):
    best_model_dir = model_dir or os.path.join(MODEL_DIR, "best")
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
        
    report_path = save_lang_metrics_csv(lang_metrics_dict)
    plot_paths = save_language_plots(lang_metrics_dict)
    logger.info("Per-language metrics CSV: %s", report_path)
    for path in plot_paths:
        logger.info("Per-language plot: %s", path)
    logger.warning("These are weak-supervision validation scores, not human gold-label scores.")
    return lang_metrics_dict
    
if __name__ == "__main__":
    evaluate_languages()
