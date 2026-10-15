"""
Veritas Lens — NER Fine-tuning Trainer
=======================================
Fine-tunes google/muril-base-cased for token classification (NER)
on auto-annotated news data (Tamil + English).

Optimised for RTX 3050/4050 Laptop GPU (~6 GB VRAM):
  - Batch size 8, fp16, gradient accumulation
  - Max sequence length 256 tokens
"""

import os
import sys
import json
import csv
import time
import logging
from datetime import datetime

import numpy as np
import torch
from torch.utils.data import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForTokenClassification,
    TrainingArguments,
    Trainer,
    DataCollatorForTokenClassification,
    EarlyStoppingCallback,
)
import transformers.modeling_utils
transformers.modeling_utils.check_torch_load_is_safe = lambda: None



sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.ner_pipeline.finetune.config import (
    BASE_MODEL_NAME, MAX_SEQ_LENGTH,
    LABEL_LIST, LABEL2ID, ID2LABEL, NUM_LABELS,
    DATASET_DIR, DATA_DIR, MODEL_DIR,
    TRAIN_BATCH_SIZE, EVAL_BATCH_SIZE, LEARNING_RATE,
    NUM_EPOCHS, WEIGHT_DECAY, WARMUP_RATIO, FP16,
    GRADIENT_ACCUMULATION_STEPS,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("NER_Trainer")
EVENT_LOSS_WEIGHT = float(os.getenv("NER_EVENT_LOSS_WEIGHT", "2.5"))


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class NERDataset(Dataset):
    """Token classification dataset from BIO-tagged JSONL."""
    
    def __init__(self, jsonl_path: str, tokenizer, max_length: int = MAX_SEQ_LENGTH):
        self.samples = []
        self.tokenizer = tokenizer
        self.max_length = max_length
        
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self.samples.append(json.loads(line))
        
        logger.info(f"Loaded {len(self.samples)} samples from {jsonl_path}")
    
    def __len__(self):
        return len(self.samples)
    
    def __getitem__(self, idx):
        sample = self.samples[idx]
        tokens = sample["tokens"]
        bio_tags = sample["bio_tags"]

        def label_id(label):
            return LABEL2ID.get(label, LABEL2ID["O"])

        if getattr(self.tokenizer, "is_fast", False):
            # Fast tokenizers expose word_ids(), which maps each WordPiece
            # back to the whitespace token carrying its BIO label.
            encoding = self.tokenizer(
                tokens,
                is_split_into_words=True,
                truncation=True,
                max_length=self.max_length,
                padding=False,
            )
            aligned_labels = []
            previous_word_id = None
            for word_id in encoding.word_ids():
                if word_id is None:
                    aligned_labels.append(-100)
                else:
                    label = bio_tags[word_id] if word_id < len(bio_tags) else "O"
                    if word_id == previous_word_id and label.startswith("B-"):
                        label = "I-" + label[2:]
                    aligned_labels.append(label_id(label))
                previous_word_id = word_id
        else:
            # Slow MuRIL/BERT tokenizers do not implement word_ids().
            # Tokenize each source word separately, carry its BIO label across
            # pieces, and let the tokenizer add CLS/SEP plus the truncation mask.
            piece_ids = []
            piece_labels = []
            for word_index, word in enumerate(tokens):
                word_ids = self.tokenizer.encode(str(word), add_special_tokens=False)
                if not word_ids:
                    word_ids = [self.tokenizer.unk_token_id]
                label = bio_tags[word_index] if word_index < len(bio_tags) else "O"
                for piece_index, token_id in enumerate(word_ids):
                    piece_ids.append(token_id)
                    piece_label = label
                    if piece_index > 0 and label.startswith("B-"):
                        piece_label = "I-" + label[2:]
                    piece_labels.append(label_id(piece_label))

            encoding = self.tokenizer.prepare_for_model(
                piece_ids,
                add_special_tokens=True,
                truncation=True,
                max_length=self.max_length,
                padding=False,
                return_special_tokens_mask=True,
            )
            aligned_labels = []
            piece_index = 0
            for is_special in encoding.pop("special_tokens_mask"):
                if is_special:
                    aligned_labels.append(-100)
                else:
                    aligned_labels.append(
                        piece_labels[piece_index] if piece_index < len(piece_labels)
                        else label_id("O")
                    )
                    piece_index += 1

        encoding["labels"] = aligned_labels
        return {key: torch.tensor(value, dtype=torch.long) for key, value in encoding.items()}


class EventAwareTrainer(Trainer):
    """Give rare EVENT BIO labels a modest, configurable loss weight."""

    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
        import torch.nn.functional as F

        inputs = dict(inputs)
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        weights = torch.ones(NUM_LABELS, dtype=outputs.logits.dtype, device=outputs.logits.device)
        weights[LABEL2ID["B-EVENT"]] = EVENT_LOSS_WEIGHT
        weights[LABEL2ID["I-EVENT"]] = EVENT_LOSS_WEIGHT
        loss = F.cross_entropy(
            outputs.logits.reshape(-1, NUM_LABELS),
            labels.reshape(-1),
            weight=weights,
            ignore_index=-100,
        )
        return (loss, outputs) if return_outputs else loss


# ---------------------------------------------------------------------------
# Metrics Computation
# ---------------------------------------------------------------------------

def compute_metrics(eval_pred):
    """Return exact BIO-span precision/recall/F1 and secondary token accuracy."""
    predictions, labels = eval_pred
    predictions = np.argmax(predictions, axis=-1)

    entity_types = ["PERSON", "ORGANIZATION", "LOCATION", "EVENT", "DATE"]
    counts = {kind: {"tp": 0, "fp": 0, "fn": 0} for kind in entity_types}

    def spans(tags):
        found, active_type, active_start = set(), None, None
        for index, tag in enumerate(list(tags) + ["O"]):
            prefix, _, kind = tag.partition("-")
            if prefix == "I" and kind == active_type:
                continue
            if active_type is not None:
                found.add((active_type, active_start, index))
                active_type, active_start = None, None
            if prefix in {"B", "I"} and kind in counts:
                active_type, active_start = kind, index
        return found

    for pred_seq, label_seq in zip(predictions, labels):
        valid = [(int(p), int(y)) for p, y in zip(pred_seq, label_seq) if int(y) != -100]
        gold = spans([ID2LABEL.get(y, "O") for _, y in valid])
        predicted = spans([ID2LABEL.get(p, "O") for p, _ in valid])
        for kind in entity_types:
            gold_kind = {span for span in gold if span[0] == kind}
            pred_kind = {span for span in predicted if span[0] == kind}
            counts[kind]["tp"] += len(gold_kind & pred_kind)
            counts[kind]["fp"] += len(pred_kind - gold_kind)
            counts[kind]["fn"] += len(gold_kind - pred_kind)

    results = {}
    macro = {key: [] for key in ("precision", "recall", "f1")}
    totals = {key: 0 for key in ("tp", "fp", "fn")}
    for kind in entity_types:
        tp, fp, fn = (counts[kind][key] for key in ("tp", "fp", "fn"))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        results[f"{kind}_precision"] = round(precision, 4)
        results[f"{kind}_recall"] = round(recall, 4)
        results[f"{kind}_f1"] = round(f1, 4)
        results[f"{kind}_support"] = tp + fn
        # Standard macro averaging excludes classes absent from both gold and
        # predictions. Otherwise a language with no examples of a class gets
        # an artificial zero simply because the shared label set has it.
        if tp + fp + fn:
            macro["precision"].append(precision)
            macro["recall"].append(recall)
            macro["f1"].append(f1)
        for key in totals:
            totals[key] += counts[kind][key]
    for key, values in macro.items():
        results[f"macro_{key}"] = round(float(np.mean(values)), 4) if values else 0.0
    micro_p = totals["tp"] / (totals["tp"] + totals["fp"]) if totals["tp"] + totals["fp"] else 0.0
    micro_r = totals["tp"] / (totals["tp"] + totals["fn"]) if totals["tp"] + totals["fn"] else 0.0
    results["micro_precision"] = round(micro_p, 4)
    results["micro_recall"] = round(micro_r, 4)
    results["micro_f1"] = round(2 * micro_p * micro_r / (micro_p + micro_r), 4) if micro_p + micro_r else 0.0

    # Overall token-level accuracy is secondary and excludes padding.
    correct = 0
    total = 0
    for pred_seq, label_seq in zip(predictions, labels):
        for p, l in zip(pred_seq, label_seq):
            if l != -100:
                total += 1
                if p == l:
                    correct += 1
    results["token_accuracy"] = round(correct / total, 4) if total > 0 else 0.0
    
    return results


# ---------------------------------------------------------------------------
# CSV Metric Saving
# ---------------------------------------------------------------------------

def save_metrics_csv(metrics: dict, phase: str = "eval"):
    """Save evaluation metrics to CSV files in data/ directory."""
    os.makedirs(DATA_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # --- 1. Per-entity metrics CSV ---
    entity_csv = os.path.join(DATA_DIR, f"finetune_entity_metrics_{timestamp}.csv")
    rows = []
    for etype in ["PERSON", "ORGANIZATION", "LOCATION", "EVENT", "DATE"]:
        rows.append({
            "entity_type": etype,
            "precision": metrics.get(f"eval_{etype}_precision", metrics.get(f"{etype}_precision", 0)),
            "recall": metrics.get(f"eval_{etype}_recall", metrics.get(f"{etype}_recall", 0)),
            "f1_score": metrics.get(f"eval_{etype}_f1", metrics.get(f"{etype}_f1", 0)),
            "support": metrics.get(f"eval_{etype}_support", metrics.get(f"{etype}_support", 0)),
        })
    # Add macro row
    rows.append({
        "entity_type": "MACRO_AVG",
        "precision": metrics.get("eval_macro_precision", metrics.get("macro_precision", 0)),
        "recall": metrics.get("eval_macro_recall", metrics.get("macro_recall", 0)),
        "f1_score": metrics.get("eval_macro_f1", metrics.get("macro_f1", 0)),
        "support": sum(r["support"] for r in rows),
    })
    
    with open(entity_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["entity_type", "precision", "recall", "f1_score", "support"])
        writer.writeheader()
        writer.writerows(rows)
    
    logger.info(f"Entity metrics saved to {entity_csv}")
    
    # --- 2. Summary metrics CSV ---
    summary_csv = os.path.join(DATA_DIR, f"finetune_summary_{timestamp}.csv")
    summary = {
        "timestamp": timestamp,
        "phase": phase,
        "model": BASE_MODEL_NAME,
        "macro_precision": metrics.get("eval_macro_precision", metrics.get("macro_precision", 0)),
        "macro_recall": metrics.get("eval_macro_recall", metrics.get("macro_recall", 0)),
        "macro_f1": metrics.get("eval_macro_f1", metrics.get("macro_f1", 0)),
        "token_accuracy": metrics.get("eval_token_accuracy", metrics.get("token_accuracy", 0)),
        "eval_loss": metrics.get("eval_loss", 0),
        "validation_basis": "auto-generated weak labels; not human-reviewed ground truth",
    }
    
    with open(summary_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=summary.keys())
        writer.writeheader()
        writer.writerow(summary)
    
    logger.info(f"Summary metrics saved to {summary_csv}")
    
    return entity_csv, summary_csv


def save_consolidated_results_csv(eval_metrics, language_metrics, train_metrics,
                                  elapsed_seconds, timestamp=None, history=None):
    """Write definitions, aggregate/entity scores, and learning history to one CSV."""
    os.makedirs(DATA_DIR, exist_ok=True)
    timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    results_path = os.path.join(DATA_DIR, "ner_finetune_results.csv")
    entity_types = ["PERSON", "ORGANIZATION", "LOCATION", "EVENT", "DATE"]
    languages = ({"combined": eval_metrics} if eval_metrics else {}) | (language_metrics or {})
    fields = [
        "record_type", "run_timestamp", "model", "language", "entity_type", "precision",
        "recall", "f1_score", "support", "macro_precision", "macro_recall", "macro_f1",
        "micro_precision", "micro_recall", "micro_f1", "token_accuracy", "eval_loss",
        "train_loss", "train_runtime_seconds", "training_epochs", "epoch", "step",
        "learning_rate", "comment",
    ]
    rows = []
    definitions = [
        "Precision = exact predicted entity spans that match a reference span / all predicted spans.",
        "Recall = exact reference entity spans recovered / all reference spans.",
        "F1 = harmonic mean of exact-span precision and recall; entity_type rows are per class.",
        "MACRO_AVG averages only entity classes with reference or predicted support; no-support classes are excluded.",
        "MICRO scores aggregate true/false positives and negatives across entity types; token accuracy is secondary.",
        "Validation labels are auto-generated weak supervision, not human-reviewed gold annotations.",
        "EVENT support is the count of reference EVENT spans; support 0 means EVENT quality is not evaluated.",
        "train_history rows record Trainer log points; blank fields mean that metric was not logged at that step.",
    ]
    for definition in definitions:
        rows.append({
            "record_type": "definition",
            "run_timestamp": timestamp,
            "model": BASE_MODEL_NAME,
            "comment": definition,
        })
    for language, metrics in languages.items():
        for entity_type in ["MACRO_AVG", *entity_types]:
            prefix = "eval_"
            if entity_type == "MACRO_AVG":
                precision = metrics.get(f"{prefix}macro_precision", metrics.get("macro_precision", ""))
                recall = metrics.get(f"{prefix}macro_recall", metrics.get("macro_recall", ""))
                f1 = metrics.get(f"{prefix}macro_f1", metrics.get("macro_f1", ""))
                support = sum(metrics.get(f"{prefix}{kind}_support", metrics.get(f"{kind}_support", 0))
                              for kind in entity_types)
            else:
                precision = metrics.get(f"{prefix}{entity_type}_precision", metrics.get(f"{entity_type}_precision", ""))
                recall = metrics.get(f"{prefix}{entity_type}_recall", metrics.get(f"{entity_type}_recall", ""))
                f1 = metrics.get(f"{prefix}{entity_type}_f1", metrics.get(f"{entity_type}_f1", ""))
                support = metrics.get(f"{prefix}{entity_type}_support", metrics.get(f"{entity_type}_support", 0))
            rows.append({
                "record_type": "evaluation",
                "run_timestamp": timestamp,
                "model": BASE_MODEL_NAME,
                "language": language,
                "entity_type": entity_type,
                "precision": precision,
                "recall": recall,
                "f1_score": f1,
                "support": support,
                "macro_precision": metrics.get("eval_macro_precision", metrics.get("macro_precision", "")),
                "macro_recall": metrics.get("eval_macro_recall", metrics.get("macro_recall", "")),
                "macro_f1": metrics.get("eval_macro_f1", metrics.get("macro_f1", "")),
                "micro_precision": metrics.get("eval_micro_precision", metrics.get("micro_precision", "")),
                "micro_recall": metrics.get("eval_micro_recall", metrics.get("micro_recall", "")),
                "micro_f1": metrics.get("eval_micro_f1", metrics.get("micro_f1", "")),
                "token_accuracy": metrics.get("eval_token_accuracy", metrics.get("token_accuracy", "")),
                "eval_loss": metrics.get("eval_loss", ""),
                "train_loss": train_metrics.get("train_loss", ""),
                "train_runtime_seconds": train_metrics.get("train_runtime", elapsed_seconds),
                "training_epochs": train_metrics.get("epoch", ""),
                "comment": "Weak-label validation; see definition records above.",
            })
    for entry in history or []:
        rows.append({
            "record_type": "train_history",
            "run_timestamp": timestamp,
            "model": BASE_MODEL_NAME,
            "epoch": entry.get("epoch", ""),
            "step": entry.get("step", ""),
            "learning_rate": entry.get("learning_rate", ""),
            "train_loss": entry.get("loss", entry.get("train_loss", "")),
            "eval_loss": entry.get("eval_loss", ""),
            "macro_f1": entry.get("eval_macro_f1", ""),
            "token_accuracy": entry.get("eval_token_accuracy", ""),
            "comment": "Trainer log record.",
        })
    with open(results_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Consolidated NER results and definitions saved to %s", results_path)
    return results_path


def save_training_history_csv(trainer):
    """Save the full training log history as a CSV."""
    os.makedirs(DATA_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    history_csv = os.path.join(DATA_DIR, f"training_history_{timestamp}.csv")
    
    log_history = trainer.state.log_history
    if not log_history:
        return None
    
    # Collect all keys across all log entries
    all_keys = set()
    for entry in log_history:
        all_keys.update(entry.keys())
    all_keys = sorted(all_keys)
    
    with open(history_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys)
        writer.writeheader()
        for entry in log_history:
            writer.writerow({k: entry.get(k, "") for k in all_keys})
    
    logger.info(f"Training history saved to {history_csv}")
    return history_csv


def save_training_history_plot(trainer):
    """Plot train/eval loss and eval macro F1 from the trainer's epoch history."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib missing; NER training history plot skipped")
        return None
    history = trainer.state.log_history
    train_points = [(row.get("epoch"), row.get("loss")) for row in history if row.get("loss") is not None]
    eval_points = [(row.get("epoch"), row.get("eval_loss")) for row in history if row.get("eval_loss") is not None]
    f1_points = [(row.get("epoch"), row.get("eval_macro_f1")) for row in history if row.get("eval_macro_f1") is not None]
    if not (train_points or eval_points or f1_points):
        logger.warning("No epoch metrics were recorded; NER training plot skipped")
        return None
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    if train_points:
        axes[0].plot(*zip(*train_points), marker="o", label="Train loss")
    if eval_points:
        axes[0].plot(*zip(*eval_points), marker="o", label="Validation loss")
    axes[0].set(title="NER loss by epoch", xlabel="Epoch", ylabel="Loss")
    axes[0].legend()
    axes[0].grid(alpha=0.2)
    if f1_points:
        axes[1].plot(*zip(*f1_points), marker="o", color="#287a59", label="Exact-span macro F1")
    axes[1].set(title="NER validation quality", xlabel="Epoch", ylabel="Macro F1", ylim=(0, 1))
    axes[1].legend()
    axes[1].grid(alpha=0.2)
    fig.tight_layout()
    path = os.path.join(DATA_DIR, f"ner_training_curves_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    fig.savefig(path, dpi=160)
    plt.close(fig)
    logger.info("Training plot saved to %s", path)
    return path


def load_base_model(model_name):
    """Load MuRIL, retrying once if the HF cache races on a partial blob.

    Hugging Face may raise FileNotFoundError while copying a ``*.incomplete``
    cache blob after an interrupted/concurrent download. A forced retry asks
    the hub client to fetch the missing file again instead of leaving training
    stuck on that stale cache entry.
    """
    for attempt in range(2):
        force_download = attempt == 1
        try:
            tokenizer = AutoTokenizer.from_pretrained(
                model_name, force_download=force_download, use_fast=True
            )
            model = AutoModelForTokenClassification.from_pretrained(
                model_name,
                num_labels=NUM_LABELS,
                id2label=ID2LABEL,
                label2id=LABEL2ID,
                force_download=force_download,
            )
            return tokenizer, model
        except FileNotFoundError as exc:
            if attempt or ".incomplete" not in str(exc):
                raise
            logger.warning(
                "Hugging Face cache referenced a missing partial download; "
                "retrying %s with force_download=True. Ensure only one "
                "training process is downloading this model.",
                model_name,
            )


# ---------------------------------------------------------------------------
# Main Training Function
# ---------------------------------------------------------------------------

def count_event_spans(jsonl_path):
    """Count EVENT spans by language in a prepared JSONL split."""
    counts = {"en": 0, "ta": 0}
    with open(jsonl_path, encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            sample = json.loads(line)
            language = str(sample.get("language", "")).lower().split("-")[0]
            if language in counts:
                counts[language] += sum(tag == "B-EVENT" for tag in sample.get("bio_tags", []))
    return counts


def train():
    """Run the full fine-tuning pipeline."""
    
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # Check for training data
    train_path = os.path.join(DATASET_DIR, "train.jsonl")
    val_path = os.path.join(DATASET_DIR, "val.jsonl")
    
    if not os.path.exists(train_path) or not os.path.exists(val_path):
        logger.error("Training data not found. Run auto_annotate.py first!")
        logger.error(f"Expected: {train_path} and {val_path}")
        sys.exit(1)

    event_train_support = count_event_spans(train_path)
    event_val_support = count_event_spans(val_path)
    missing_support = [
        f"{language} train={event_train_support[language]}, val={event_val_support[language]}"
        for language in ("en", "ta")
        if event_train_support[language] == 0 or event_val_support[language] == 0
    ]
    if missing_support:
        raise ValueError(
            "EVENT training/evaluation needs EVENT spans for English and Tamil in both splits; "
            f"found {', '.join(missing_support)}. Regenerate annotations with "
            "./scripts/prepare_ner_data.sh and add/review more event examples before training."
        )
    logger.info("EVENT BIO spans: train=%s, validation=%s", event_train_support, event_val_support)
    logger.info("EVENT token loss weight: %s", EVENT_LOSS_WEIGHT)
    
    # --- 1. Load tokenizer and model ---
    # Support local pre-downloaded model
    local_model_path = "/tmp/muril-download"
    if os.path.exists(os.path.join(local_model_path, "pytorch_model.bin")):
        model_name = local_model_path
        logger.info(f"Loading model from local path: {model_name}")
    else:
        model_name = BASE_MODEL_NAME
        logger.info(f"Loading model from HuggingFace: {model_name}")
    
    tokenizer, model = load_base_model(model_name)
    
    logger.info(f"Model loaded. Labels: {NUM_LABELS}, Params: {model.num_parameters():,}")
    
    # --- 2. Load datasets ---
    train_dataset = NERDataset(train_path, tokenizer)
    val_dataset = NERDataset(val_path, tokenizer)
    
    data_collator = DataCollatorForTokenClassification(
        tokenizer=tokenizer,
        padding=True,
    )
    
    # --- 3. Training arguments ---
    output_dir = os.path.join(MODEL_DIR, "checkpoints")
    
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=NUM_EPOCHS,
        per_device_train_batch_size=TRAIN_BATCH_SIZE,
        per_device_eval_batch_size=EVAL_BATCH_SIZE,
        gradient_accumulation_steps=GRADIENT_ACCUMULATION_STEPS,
        gradient_checkpointing=True,
        learning_rate=LEARNING_RATE,
        weight_decay=WEIGHT_DECAY,
        warmup_ratio=WARMUP_RATIO,
        fp16=FP16 and torch.cuda.is_available(),
        # AdamW keeps two full-size optimizer states on the GPU. Adafactor
        # greatly reduces optimizer-state memory for this 5.6GB GPU target.
        optim="adafactor",
        eval_strategy="epoch",
        save_strategy="epoch",
        logging_strategy="steps",
        logging_steps=50,
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="macro_f1",
        greater_is_better=True,
        report_to="none",
        dataloader_num_workers=2,
        remove_unused_columns=False,
    )
    
    # --- 4. Trainer ---
    trainer = EventAwareTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=3)],
    )
    
    # --- 5. Train ---
    logger.info("Starting fine-tuning...")
    logger.warning(
        "NER validation data is generated by the weak annotator. Its F1 measures "
        "agreement with those labels, not independent real-world entity accuracy."
    )
    start_time = time.time()
    
    train_result = trainer.train()
    
    elapsed = time.time() - start_time
    logger.info(f"Training completed in {elapsed:.1f}s ({elapsed/60:.1f} min)")
    
    # --- 6. Evaluate ---
    logger.info("Running final evaluation...")
    eval_metrics = trainer.evaluate()
    
    logger.info("=== Final Evaluation Results ===")
    for key, value in sorted(eval_metrics.items()):
        logger.info(f"  {key}: {value}")
    
    # --- 7. Save model ---
    best_model_dir = os.path.join(MODEL_DIR, "best")
    trainer.save_model(best_model_dir)
    tokenizer.save_pretrained(best_model_dir)
    logger.info(f"Best model saved to {best_model_dir}")
    
    # --- 8. Save metrics as CSV ---
    history_plot = save_training_history_plot(trainer)

    # Language-separated validation for the saved best checkpoint.
    from backend.ner_pipeline.finetune.evaluate_per_language import evaluate_languages
    language_metrics = evaluate_languages(model_dir=best_model_dir, save_csv=False) or {}
    result_csv = save_consolidated_results_csv(
        eval_metrics,
        language_metrics or {},
        train_result.metrics,
        elapsed,
        history=trainer.state.log_history,
    )
    
    logger.info(f"\n{'='*60}")
    logger.info(f"FINE-TUNING COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Model:         {BASE_MODEL_NAME}")
    logger.info(f"Best model:    {best_model_dir}")
    logger.info(f"Macro F1:      {eval_metrics.get('eval_macro_f1', 'N/A')}")
    logger.info(f"Token Accuracy:{eval_metrics.get('eval_token_accuracy', 'N/A')}")
    logger.info(f"Results CSV:   {result_csv}")
    logger.info(f"History plot:  {history_plot}")
    for language, metrics in language_metrics.items():
        logger.info(
            "%s exact-span macro P/R/F1: %.4f / %.4f / %.4f",
            language.upper(), metrics.get("eval_macro_precision", 0),
            metrics.get("eval_macro_recall", 0), metrics.get("eval_macro_f1", 0),
        )
    logger.info(f"{'='*60}")
    
    return eval_metrics


if __name__ == "__main__":
    train()
