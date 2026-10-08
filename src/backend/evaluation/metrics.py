import csv
import json
import os
from datetime import datetime

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


def timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def binary_metrics(y_true, y_pred):
    """Positive class is same-event / relevant; macro is over both classes."""
    counts = {label: {"tp": 0, "fp": 0, "fn": 0} for label in (0, 1)}
    correct = 0
    for truth, prediction in zip(y_true, y_pred):
        correct += int(truth == prediction)
        for label in (0, 1):
            if truth == label and prediction == label:
                counts[label]["tp"] += 1
            elif truth != label and prediction == label:
                counts[label]["fp"] += 1
            elif truth == label and prediction != label:
                counts[label]["fn"] += 1
    per_class = {}
    for label in (0, 1):
        tp, fp, fn = (counts[label][key] for key in ("tp", "fp", "fn"))
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        per_class[str(label)] = {
            "precision": p,
            "recall": r,
            "f1": 2 * p * r / (p + r) if p + r else 0.0,
            "support": tp + fn,
        }
    pos = per_class["1"]
    return {
        "accuracy": correct / len(y_true) if y_true else 0.0,
        "precision": pos["precision"], "recall": pos["recall"], "f1": pos["f1"],
        "macro_precision": sum(x["precision"] for x in per_class.values()) / 2,
        "macro_recall": sum(x["recall"] for x in per_class.values()) / 2,
        "macro_f1": sum(x["f1"] for x in per_class.values()) / 2,
        "same_event_support": pos["support"], "pair_count": len(y_true),
        "per_class": per_class,
    }


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temp_path, path)


def write_csv(path, rows, fieldnames):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def plot_metric_groups(path, labels, language_values, title, ylabel, metric_names):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib is unavailable; tabular metrics were still saved")
        return None
    import numpy as np

    positions = np.arange(len(labels))
    language_names = list(language_values)
    width = 0.8 / max(len(language_names), 1)
    fig, ax = plt.subplots(figsize=(max(7, len(labels) * 1.15), 4.8))
    for index, language in enumerate(language_names):
        values = [language_values[language].get(key, 0) for key in metric_names]
        offset = (index - (len(language_names) - 1) / 2) * width
        ax.bar(positions + offset, values, width, label="Tamil" if language == "ta" else "English")
    ax.set_xticks(positions, labels, rotation=15, ha="right")
    ax.set_ylim(0, 1)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.2)
    ax.legend()
    fig.tight_layout()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path
