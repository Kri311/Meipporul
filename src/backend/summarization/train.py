"""Fine-tune multilingual XLSum mT5 for bilingual, multi-bullet news summaries.

Input CSV must contain language, body, summary_bullets and article_id. Optional
event_group values keep related article rows together in the train/validation split.
"""

import argparse
import csv
import json
import logging
import os
import random
import re
import shutil
from pathlib import Path

import torch
from torch.utils.data import Dataset
from transformers import (
    AutoModelForSeq2SeqLM,
    AutoTokenizer,
    DataCollatorForSeq2Seq,
    Trainer,
    TrainingArguments,
)

BASE_MODEL = os.getenv("SUMMARY_BASE_MODEL", "csebuetnlp/mT5_multilingual_XLSum")
OUTPUT_DIR = Path(os.getenv(
    "SUMMARY_FINETUNED_MODEL_PATH",
    str(Path(__file__).resolve().parents[1] / "models" / "summarizer" / "best"),
))
MAX_SOURCE_TOKENS = int(os.getenv("SUMMARY_TRAIN_MAX_SOURCE_TOKENS", "448"))
MAX_TARGET_TOKENS = int(os.getenv("SUMMARY_TRAIN_MAX_TARGET_TOKENS", "192"))
logger = logging.getLogger("summary_finetune")


def _bullets(value):
    value = str(value or "").strip()
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            values = parsed
        else:
            values = [value]
    except json.JSONDecodeError:
        values = re.split(r"\r?\n+", value)
    result = []
    for item in values:
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", str(item)).strip()
        if line and line not in result:
            result.append(line)
    return result


def _prompt(language, title, body):
    if language == "ta":
        instruction = "செய்தி உள்ளடக்கத்தை உண்மையான முக்கிய அம்சங்களாக சுருக்கவும்"
    else:
        instruction = "summarize English news into concise factual bullet points"
    return f"{instruction}\nheadline: {title}\nbody: {body}"


def _read_examples(path):
    examples = []
    with open(path, encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            language = (row.get("language") or "").casefold().split("-")[0]
            points = _bullets(row.get("summary_bullets"))
            body = re.sub(r"\s+", " ", row.get("body", "")).strip()
            if language not in {"en", "ta"} or not body or not points:
                continue
            examples.append({
                "article_id": row.get("article_id") or row.get("guid") or str(len(examples)),
                "event_group": row.get("event_group") or row.get("event_id") or "",
                "language": language,
                "title": re.sub(r"\s+", " ", row.get("title", "")).strip(),
                "body": body,
                "target": "\n".join(f"- {point}" for point in points),
            })
    return examples


def _split_examples(examples, validation_fraction, seed):
    rng = random.Random(seed)
    train, validation = [], []
    for language in ("en", "ta"):
        language_rows = [row for row in examples if row["language"] == language]
        group_rows = {}
        for row in language_rows:
            group = row["event_group"] or row["article_id"]
            group_rows.setdefault(group, []).append(row)
        group_ids = list(group_rows)
        rng.shuffle(group_ids)
        if len(group_ids) < 2:
            raise ValueError(f"Need at least two independent article/event groups for {language}.")
        validation_count = min(len(group_ids) - 1, max(1, round(len(group_ids) * validation_fraction)))
        validation_groups = set(group_ids[:validation_count])
        for group, rows in group_rows.items():
            (validation if group in validation_groups else train).extend(rows)
    return train, validation


class SummaryDataset(Dataset):
    def __init__(self, examples, tokenizer):
        self.rows = []
        for row in examples:
            source = _prompt(row["language"], row["title"], row["body"])
            encoded = tokenizer(
                source, max_length=MAX_SOURCE_TOKENS, truncation=True, padding=False,
            )
            target = tokenizer(
                text_target=row["target"], max_length=MAX_TARGET_TOKENS,
                truncation=True, padding=False,
            )
            self.rows.append({"input_ids": encoded["input_ids"], "attention_mask": encoded["attention_mask"],
                              "labels": target["input_ids"]})

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        return self.rows[index]


def train(labels_csv, *, epochs=3, validation_fraction=0.15, seed=29, overwrite=False):
    if OUTPUT_DIR.exists() and not overwrite:
        raise FileExistsError(f"{OUTPUT_DIR} exists; pass --overwrite to replace it.")
    torch_version = tuple(int(part) for part in re.match(r"^(\d+)\.(\d+)", torch.__version__).groups())
    if torch_version < (2, 6):
        raise RuntimeError(f"PyTorch >=2.6 is required for safe checkpoint loading; found {torch.__version__}.")
    examples = _read_examples(labels_csv)
    language_counts = {language: sum(row["language"] == language for row in examples) for language in ("en", "ta")}
    if min(language_counts.values()) < 20:
        raise ValueError(f"Need at least 20 reviewed summary pairs per language; found {language_counts}.")
    train_rows, val_rows = _split_examples(examples, validation_fraction, seed)
    logger.info("Examples: total=%d train=%d validation=%d languages=%s", len(examples), len(train_rows), len(val_rows), language_counts)

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, use_fast=False)
    model = AutoModelForSeq2SeqLM.from_pretrained(BASE_MODEL)
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()
    try:
        from peft import LoraConfig, TaskType, get_peft_model
    except ImportError as exc:
        raise RuntimeError("Install peft from requirements.txt before summarizer fine-tuning.") from exc
    model = get_peft_model(model, LoraConfig(
        task_type=TaskType.SEQ_2_SEQ_LM,
        r=int(os.getenv("SUMMARY_LORA_R", "8")),
        lora_alpha=int(os.getenv("SUMMARY_LORA_ALPHA", "16")),
        lora_dropout=float(os.getenv("SUMMARY_LORA_DROPOUT", "0.05")),
        target_modules=["q", "v"],
    ))
    model.print_trainable_parameters()

    output_dir = OUTPUT_DIR.parent / "training"
    output_dir.mkdir(parents=True, exist_ok=True)
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=epochs,
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=int(os.getenv("SUMMARY_GRADIENT_ACCUMULATION", "8")),
        learning_rate=float(os.getenv("SUMMARY_LEARNING_RATE", "2e-4")),
        weight_decay=0.01,
        warmup_ratio=0.05,
        fp16=torch.cuda.is_available(),
        gradient_checkpointing=True,
        optim="adafactor",
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        report_to="none",
        dataloader_num_workers=0,
        label_names=["labels"],
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=SummaryDataset(train_rows, tokenizer),
        eval_dataset=SummaryDataset(val_rows, tokenizer),
        data_collator=DataCollatorForSeq2Seq(tokenizer=tokenizer, model=model),
    )
    trainer.train()
    metrics = trainer.evaluate()
    if OUTPUT_DIR.exists() and overwrite:
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(OUTPUT_DIR))
    tokenizer.save_pretrained(str(OUTPUT_DIR))
    (OUTPUT_DIR / "training_metadata.json").write_text(json.dumps({
        "base_model": BASE_MODEL,
        "languages": language_counts,
        "train_examples": len(train_rows),
        "validation_examples": len(val_rows),
        "target_format": "one factual bullet per line",
        "validation_loss": metrics.get("eval_loss"),
        "labels_csv": str(Path(labels_csv).resolve()),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved LoRA fine-tuned summarizer to {OUTPUT_DIR}")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", required=True, help="Reviewed summary label CSV")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--validation-fraction", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=29)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    train(args.labels, epochs=args.epochs, validation_fraction=args.validation_fraction,
          seed=args.seed, overwrite=args.overwrite)
