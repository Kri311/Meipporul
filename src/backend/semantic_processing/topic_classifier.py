"""Bilingual event-topic taxonomy, annotation workflow, and A/B classifier.

Experiment A: multilingual-e5-base embeddings + Logistic Regression.
Experiment B: fine-tuned google/muril-base-cased sequence classifier.

Suggested taxonomy labels seed the training data. These are weak labels and can
be reviewed or corrected in the topic column before training.
"""

import csv
import hashlib
import json
import os
import random
import re
import shutil
import logging
import threading
from pathlib import Path

import yaml

BACKEND_DIR = Path(__file__).resolve().parents[1]
TAXONOMY_PATH = BACKEND_DIR / "config" / "topic_taxonomy.yaml"
MODEL_DIR = BACKEND_DIR / "models" / "topic_classifier"
TAXONOMY = yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))["topics"]
TOPIC_IDS = list(TAXONOMY)
LEGACY_TOPIC_MAP = {"culture_and_lifestyle": "other_current_affairs"}
ZERO_SHOT_MODEL = os.getenv(
    "TOPIC_ZERO_SHOT_MODEL", "MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli"
)
ZERO_SHOT_MIN_SCORE = float(os.getenv("TOPIC_ZERO_SHOT_MIN_SCORE", "0.45"))
ZERO_SHOT_MIN_MARGIN = float(os.getenv("TOPIC_ZERO_SHOT_MIN_MARGIN", "0.05"))
SUPERVISED_MIN_SCORE = float(os.getenv("TOPIC_SUPERVISED_MIN_SCORE", "0.45"))
SUPERVISED_MIN_MARGIN = float(os.getenv("TOPIC_SUPERVISED_MIN_MARGIN", "0.05"))
SUPERVISED_NON_OTHER_MIN_SCORE = float(os.getenv("TOPIC_NON_OTHER_MIN_SCORE", "0.30"))
TOPIC_RULE_OVERRIDE_MIN_SCORE = int(os.getenv("TOPIC_RULE_OVERRIDE_MIN_SCORE", "5"))
logger = logging.getLogger(__name__)


def normalize_topic_id(topic):
    """Map removed or unknown labels to the current fallback category."""
    topic = str(topic or "").strip()
    topic = LEGACY_TOPIC_MAP.get(topic, topic)
    return topic if topic in TAXONOMY else "other_current_affairs"


def topic_labels(language="en"):
    key = "label_ta" if language == "ta" else "label_en"
    return {topic: values[key] for topic, values in TAXONOMY.items()}


def _topic_rule_scores(title, text):
    """Score taxonomy keywords, weighting headline matches above body mentions."""
    title_text = str(title or "").casefold()
    body_text = str(text or "")[:1800].casefold()
    scores = {}
    for topic, values in TAXONOMY.items():
        score = 0
        for language in ("en", "ta"):
            for keyword in values["keywords"].get(language, []):
                term = keyword.casefold()
                if language == "en":
                    import re
                    pattern = r"(?<![a-z0-9])" + re.escape(term).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
                    title_hits = len(re.findall(pattern, title_text))
                    body_hits = len(re.findall(pattern, body_text))
                else:
                    title_hits = title_text.count(term)
                    body_hits = body_text.count(term)
                score += title_hits * 5 + min(body_hits, 3)
        scores[topic] = score
    return scores


def classify_topic_rules(title, text, outlet_slug="", location=""):
    """Bilingual keyword fallback; returns taxonomy IDs only."""
    scores = _topic_rule_scores(title, text)
    best_topic, best_score = max(scores.items(), key=lambda item: item[1])
    return normalize_topic_id(best_topic) if best_score else "other_current_affairs"


def _strong_topic_rule(title, body):
    """Use clear headline keyword evidence to recover an existing topic.

    This is a safety net for classifier abstentions. A single body mention is
    not enough; by default the score requires at least one taxonomy keyword in
    the headline (headline hits are weighted by five).
    """
    # The override intentionally considers headline text only. Body mentions
    # can be incidental (a story may quote another unrelated event).
    scores = _topic_rule_scores(title, "")
    topic, score = max(scores.items(), key=lambda item: item[1])
    if topic != "other_current_affairs" and score >= TOPIC_RULE_OVERRIDE_MIN_SCORE:
        return topic
    return None


def _use_rule_if_classifier_abstained(title, body, model_name):
    topic = _strong_topic_rule(title, body)
    if topic:
        return topic, f"{model_name}+headline_keyword_fallback"
    return "other_current_affairs", model_name


def _best_existing_topic(class_scores):
    """Return a well-supported non-Other class, if one stands out."""
    ranked = sorted(
        ((normalize_topic_id(label), float(score)) for label, score in class_scores
         if normalize_topic_id(label) != "other_current_affairs"),
        key=lambda item: item[1], reverse=True,
    )
    if not ranked:
        return None
    topic, score = ranked[0]
    margin = score - (ranked[1][1] if len(ranked) > 1 else 0.0)
    if score >= SUPERVISED_NON_OTHER_MIN_SCORE and margin >= SUPERVISED_MIN_MARGIN:
        return topic
    return None


def article_input(title, body):
    return f"headline: {title or ''}\nbody: {body or ''}"[:5000]


def prepare_annotation_template(input_csv, output_csv, per_language=250, seed=17):
    """Create a balanced bilingual annotation template from eligible articles.

    Suggestions are weak labels. Keep the existing annotation file untouched by
    writing the larger template to a separately named output file.
    """
    from backend.ingestion.tasks.text_cleaning import parse_clean_article

    groups = {"en": [], "ta": []}
    seen = {"en": set(), "ta": set()}
    with open(input_csv, encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            language = (row.get("language") or "").casefold().split("-")[0]
            if language not in groups:
                continue
            title, body = parse_clean_article(row.get("clean_text"), row.get("title", ""))
            body = body.strip() or row.get("description", "")
            if len(title) < 8 or len(body) < 40:
                continue
            # Feeds may repeat an article or omit GUIDs. Deduplicate on normalized
            # title plus a body prefix so repeated records do not inflate training.
            fingerprint_text = re.sub(r"\s+", " ", f"{title} {body[:500]}".casefold()).strip()
            fingerprint = hashlib.sha256(fingerprint_text.encode("utf-8")).hexdigest()
            if fingerprint in seen[language]:
                continue
            seen[language].add(fingerprint)
            suggested_topic = classify_topic_rules(title, body)
            groups[language].append({
                "guid": row.get("guid", ""),
                "outlet_slug": row.get("outlet_slug", ""),
                "language": language,
                "title": title,
                "text": body[:1800],
                "suggested_topic": suggested_topic,
                "topic": suggested_topic,
            })
    rng = random.Random(seed)
    rows = []
    for language, candidates in groups.items():
        buckets = {topic: [] for topic in TOPIC_IDS}
        for row in candidates:
            buckets[row["suggested_topic"]].append(row)
        for bucket in buckets.values():
            rng.shuffle(bucket)
        # Round-robin across taxonomy buckets. If a suggested class has few
        # examples, take all of them and continue filling from other classes.
        selected = []
        while len(selected) < per_language:
            progressed = False
            for topic in TOPIC_IDS:
                if buckets[topic] and len(selected) < per_language:
                    selected.append(buckets[topic].pop())
                    progressed = True
            if not progressed:
                break
        rows.extend(selected)
    rows.sort(key=lambda row: (row["language"], row["guid"]))
    os.makedirs(os.path.dirname(os.path.abspath(output_csv)), exist_ok=True)
    with open(output_csv, "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["guid", "outlet_slug", "language", "title", "text", "suggested_topic", "topic"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} annotation rows to {output_csv}")
    print(f"Requested up to {per_language} rows per language; available: "
          f"en={len(groups['en'])}, ta={len(groups['ta'])}")
    print("The topic label is initialized from suggested_topic; review or correct it before training if needed:")
    for topic, values in TAXONOMY.items():
        print(f"  {topic}: {values['label_en']} / {values['label_ta']}")


def _read_labels(path):
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            topic = (row.get("topic") or row.get("suggested_topic") or "").strip()
            if not topic:
                continue
            topic = normalize_topic_id(topic)
            row["topic"] = topic
            rows.append(row)
    if not rows:
        raise ValueError("No topic or suggested_topic labels found in the annotation CSV.")
    return rows


def run_ab_experiment(labels_csv, test_size=0.2, seed=17, epochs=3):
    """Fit both models on one stratified split and select by held-out macro F1."""
    import numpy as np
    from sklearn.metrics import accuracy_score, classification_report, f1_score
    from sklearn.model_selection import train_test_split
    from sklearn.linear_model import LogisticRegression
    from sentence_transformers import SentenceTransformer

    rows = _read_labels(labels_csv)
    labels = [normalize_topic_id(row.get("topic") or row.get("suggested_topic")) for row in rows]
    languages = [(row.get("language") or "en").casefold().split("-")[0] for row in rows]
    if not {"en", "ta"}.issubset(set(languages)):
        raise ValueError("The A/B experiment needs English and Tamil rows with topic suggestions.")
    if min(languages.count("en"), languages.count("ta")) < 5:
        raise ValueError("Add at least 5 labeled rows for each language before comparing the models.")
    counts = {topic: labels.count(topic) for topic in set(labels)}
    too_small = [topic for topic, count in counts.items() if count < 5]
    if too_small:
        raise ValueError(f"At least 5 labeled rows per represented class are needed for a held-out comparison: {too_small}")
    texts = [article_input(row.get("title"), row.get("text")) for row in rows]
    split_groups = [f"{language}:{label}" for language, label in zip(languages, labels)]
    split_strata = split_groups if min(split_groups.count(group) for group in set(split_groups)) >= 2 else labels
    train_idx, test_idx = train_test_split(
        np.arange(len(rows)), test_size=test_size, random_state=seed, stratify=split_strata
    )
    y_train = [labels[i] for i in train_idx]
    y_test = [labels[i] for i in test_idx]
    test_languages = [languages[i] for i in test_idx]
    if set(test_languages) != {"en", "ta"}:
        raise ValueError("The held-out split must contain both English and Tamil examples; add more labeled rows and retry.")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    min_free_gib = float(os.getenv("TOPIC_MIN_FREE_DISK_GB", "1.5"))
    free_gib = shutil.disk_usage(MODEL_DIR).free / (1024 ** 3)
    if free_gib < min_free_gib:
        raise RuntimeError(
            f"Topic experiment needs about {min_free_gib:.1f} GiB of free disk space "
            f"to save MuRIL; only {free_gib:.2f} GiB is available. Remove old training "
            "checkpoints or free disk space, then retry."
        )

    import torch
    requested_device = os.getenv("TOPIC_DEVICE", "auto").casefold()
    device = "cuda" if requested_device != "cpu" and torch.cuda.is_available() else "cpu"
    e5 = SentenceTransformer(os.getenv("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-base"), device=device)
    vectors = e5.encode([f"passage: {text}" for text in texts], normalize_embeddings=True,
                        batch_size=32, show_progress_bar=True)
    lr = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=seed)
    lr.fit(vectors[train_idx], y_train)
    lr_predictions = lr.predict(vectors[test_idx])
    from joblib import dump
    lr_dir = MODEL_DIR / "e5_logistic_regression"
    lr_dir.mkdir(parents=True, exist_ok=True)
    dump(lr, lr_dir / "classifier.joblib")
    (lr_dir / "labels.json").write_text(json.dumps(lr.classes_.tolist()), encoding="utf-8")
    language_scores = _language_scores(y_test, lr_predictions, test_languages)
    results = {
        "e5_logistic_regression": {
            "macro_f1": float(f1_score(y_test, lr_predictions, average="macro")),
            "accuracy": float(accuracy_score(y_test, lr_predictions)),
            "language_scores": language_scores,
            "mean_language_macro_f1": sum(item["macro_f1"] for item in language_scores.values()) / len(language_scores),
            "report": classification_report(y_test, lr_predictions, labels=TOPIC_IDS, output_dict=True, zero_division=0),
            "model": os.getenv("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-base"),
            "artifact_ready": True,
        }
    }

    # E5 and MuRIL are both transformer models. The E5 encoder is no longer
    # needed once embeddings and the LR baseline are ready; keep its weights
    # from occupying VRAM during MuRIL fine-tuning.
    del e5
    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    _train_muril(texts, labels, train_idx, test_idx, y_train, y_test, test_languages, epochs, results, seed)
    metrics_path = MODEL_DIR / "experiment_metrics.json"
    metrics_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    eligible = {
        name: values for name, values in results.items()
        if values.get("artifact_ready", True)
    }
    selected = max(eligible, key=lambda name: eligible[name]["mean_language_macro_f1"])
    (MODEL_DIR / "selected.json").write_text(json.dumps({
        "selected": selected, "selection_metric": "mean_english_tamil_macro_f1",
        "training_labels": "suggested_topic (weak labels; topic column may be reviewed)",
        "scores": {name: values["mean_language_macro_f1"] for name, values in results.items()},
        "labels_csv": str(Path(labels_csv).resolve()),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"selected": selected, "results": {
        name: {"macro_f1": value["macro_f1"], "accuracy": value["accuracy"],
              "language_scores": value["language_scores"],
              "mean_language_macro_f1": value["mean_language_macro_f1"]}
        for name, value in results.items()
    }, "metrics": str(metrics_path)}, indent=2))


def run_e5_experiment(labels_csv, test_size=0.2, seed=17):
    """Tune E5 + Logistic Regression, evaluate once, then fit deployable model on all rows."""
    import numpy as np
    import torch
    from joblib import dump
    from sklearn.metrics import accuracy_score, classification_report, f1_score
    from sklearn.model_selection import GridSearchCV, StratifiedKFold, train_test_split
    from sklearn.linear_model import LogisticRegression
    from sentence_transformers import SentenceTransformer

    rows = _read_labels(labels_csv)
    labels = [normalize_topic_id(row.get("topic") or row.get("suggested_topic")) for row in rows]
    languages = [(row.get("language") or "en").casefold().split("-")[0] for row in rows]
    if not {"en", "ta"}.issubset(set(languages)):
        raise ValueError("E5 training needs both English and Tamil labeled rows.")
    counts = {topic: labels.count(topic) for topic in set(labels)}
    too_small = {topic: count for topic, count in counts.items() if count < 5}
    if too_small:
        raise ValueError(f"Need at least 5 examples per represented topic for a holdout and CV: {too_small}")

    texts = [article_input(row.get("title"), row.get("text")) for row in rows]
    indices = np.arange(len(rows))
    split_groups = [f"{language}:{label}" for language, label in zip(languages, labels)]
    split_strata = split_groups if min(split_groups.count(group) for group in set(split_groups)) >= 2 else labels
    train_idx, test_idx = train_test_split(
        indices, test_size=test_size, random_state=seed, stratify=split_strata
    )
    y_train = [labels[i] for i in train_idx]
    y_test = [labels[i] for i in test_idx]
    test_languages = [languages[i] for i in test_idx]
    if set(test_languages) != {"en", "ta"}:
        raise ValueError("The held-out split must include both languages; add examples and retry.")

    model_name = os.getenv("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-base")
    requested_device = os.getenv("TOPIC_DEVICE", "auto").casefold()
    device = "cuda" if requested_device != "cpu" and torch.cuda.is_available() else "cpu"
    encoder = SentenceTransformer(model_name, device=device)
    # News articles are documents in E5's retrieval convention, so use the
    # passage prefix consistently for training, validation, and inference.
    vectors = encoder.encode([f"passage: {text}" for text in texts], normalize_embeddings=True,
                             batch_size=32, show_progress_bar=True)
    del encoder
    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    min_train_class = min(y_train.count(topic) for topic in set(y_train))
    folds = min(5, min_train_class)
    if folds < 2:
        raise ValueError("Not enough training examples per topic for cross-validation.")
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    search = GridSearchCV(
        LogisticRegression(max_iter=3000, class_weight="balanced", random_state=seed),
        {"C": [0.03, 0.1, 0.3, 1.0, 3.0, 10.0]},
        scoring="f1_macro", cv=cv, n_jobs=-1, refit=True,
    )
    search.fit(vectors[train_idx], y_train)
    validation_predictions = search.predict(vectors[test_idx])
    language_scores = _language_scores(y_test, validation_predictions, test_languages)

    # Do not deploy the holdout-only model: after reporting held-out metrics,
    # use all labeled rows to fit the final classifier.
    final_model = LogisticRegression(
        C=search.best_params_["C"], max_iter=3000, class_weight="balanced", random_state=seed
    ).fit(vectors, labels)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_dir = MODEL_DIR / "e5_logistic_regression"
    model_dir.mkdir(parents=True, exist_ok=True)
    dump(final_model, model_dir / "classifier.joblib")
    (model_dir / "labels.json").write_text(json.dumps(final_model.classes_.tolist()), encoding="utf-8")

    result = {
        "selected": "e5_logistic_regression",
        "selection_metric": "held_out_macro_f1; C selected by stratified CV on training split",
        "model": model_name,
        "embedding_prefix": "passage:",
        "device": device,
        "rows": len(rows),
        "language_counts": {language: languages.count(language) for language in sorted(set(languages))},
        "topic_counts": counts,
        "training_labels": "topic column (review suggested_topic weak labels before training)",
        "best_params": search.best_params_,
        "cross_validation_macro_f1": float(search.best_score_),
        "held_out": {
            "macro_f1": float(f1_score(y_test, validation_predictions, average="macro")),
            "accuracy": float(accuracy_score(y_test, validation_predictions)),
            "language_scores": language_scores,
            "report": classification_report(y_test, validation_predictions, labels=TOPIC_IDS,
                                            output_dict=True, zero_division=0),
        },
        "labels_csv": str(Path(labels_csv).resolve()),
        "deployment_fit_rows": len(rows),
    }
    (MODEL_DIR / "experiment_metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (MODEL_DIR / "selected.json").write_text(json.dumps({
        "selected": "e5_logistic_regression",
        "selection_metric": result["selection_metric"],
        "training_labels": result["training_labels"],
        "scores": {"e5_logistic_regression": result["held_out"]["macro_f1"]},
        "labels_csv": result["labels_csv"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run_e5_ner_fusion_experiment(labels_csv, test_size=0.2, seed=17):
    """Compare E5-only with E5 + typed NER features on one bilingual holdout."""
    import numpy as np
    import torch
    from joblib import dump
    from scipy.sparse import csr_matrix, hstack
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.feature_extraction.text import TfidfTransformer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, classification_report, f1_score
    from sklearn.model_selection import GridSearchCV, StratifiedKFold, train_test_split
    from sentence_transformers import SentenceTransformer
    from backend.semantic_processing.topic_ner import (
        entity_feature_dict, extract_training_entities,
    )

    rows = _read_labels(labels_csv)
    labels = [normalize_topic_id(row.get("topic") or row.get("suggested_topic")) for row in rows]
    languages = [(row.get("language") or "en").casefold().split("-")[0] for row in rows]
    if not {"en", "ta"}.issubset(set(languages)):
        raise ValueError("E5 + NER training needs both English and Tamil labeled rows.")
    counts = {topic: labels.count(topic) for topic in set(labels)}
    too_small = {topic: count for topic, count in counts.items() if count < 5}
    if too_small:
        raise ValueError(f"Need at least 5 examples per represented topic for a holdout and CV: {too_small}")

    texts = [article_input(row.get("title"), row.get("text")) for row in rows]
    # Persist these exact NER outputs alongside labels so the experiment is
    # reproducible and the source annotation file remains untouched.
    ner_entities = extract_training_entities(texts, languages)
    ner_dicts = [entity_feature_dict(entities) for entities in ner_entities]
    enriched_path = Path(labels_csv).with_name(Path(labels_csv).stem + "_ner_features.csv")
    with enriched_path.open("w", encoding="utf-8-sig", newline="") as stream:
        fields = list(rows[0].keys())
        if "ner_entities" not in fields:
            fields.append("ner_entities")
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row, entities in zip(rows, ner_entities):
            writer.writerow({**row, "ner_entities": json.dumps(entities, ensure_ascii=False)})

    indices = np.arange(len(rows))
    split_groups = [f"{language}:{label}" for language, label in zip(languages, labels)]
    split_strata = split_groups if min(split_groups.count(group) for group in set(split_groups)) >= 2 else labels
    train_idx, test_idx = train_test_split(
        indices, test_size=test_size, random_state=seed, stratify=split_strata
    )
    y_train = [labels[i] for i in train_idx]
    y_test = [labels[i] for i in test_idx]
    test_languages = [languages[i] for i in test_idx]
    if set(test_languages) != {"en", "ta"}:
        raise ValueError("The held-out split must include both languages; add examples and retry.")

    model_name = os.getenv("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-base")
    requested_device = os.getenv("TOPIC_DEVICE", "auto").casefold()
    device = "cuda" if requested_device != "cpu" and torch.cuda.is_available() else "cpu"
    encoder = SentenceTransformer(model_name, device=device)
    vectors = encoder.encode([f"passage: {text}" for text in texts], normalize_embeddings=True,
                             batch_size=32, show_progress_bar=True)
    del encoder
    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    min_train_class = min(y_train.count(topic) for topic in set(y_train))
    folds = min(5, min_train_class)
    if folds < 2:
        raise ValueError("Not enough training examples per topic for cross-validation.")
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    c_values = [0.03, 0.1, 0.3, 1.0, 3.0, 10.0]
    base_search = GridSearchCV(
        LogisticRegression(max_iter=3000, class_weight="balanced", random_state=seed),
        {"C": c_values}, scoring="f1_macro", cv=cv, n_jobs=-1,
    ).fit(vectors[train_idx], y_train)
    base_test_predictions = base_search.predict(vectors[test_idx])

    # Learn NER vocabulary only from the training partition. L2-normalize its
    # sparse channel, then tune its relative weight against E5 using CV.
    ner_vectorizer = DictVectorizer(sparse=True)
    ner_train_raw = ner_vectorizer.fit_transform([ner_dicts[i] for i in train_idx])
    ner_test_raw = ner_vectorizer.transform([ner_dicts[i] for i in test_idx])
    ner_transformer = TfidfTransformer(norm="l2", use_idf=False)
    ner_train = ner_transformer.fit_transform(ner_train_raw)
    ner_test = ner_transformer.transform(ner_test_raw)
    best_fusion = None
    fusion_searches = []
    for weight in (0.1, 0.25, 0.5, 1.0, 2.0):
        x_train = hstack([csr_matrix(vectors[train_idx]), ner_train * weight], format="csr")
        search = GridSearchCV(
            LogisticRegression(max_iter=3000, class_weight="balanced", random_state=seed),
            {"C": c_values}, scoring="f1_macro", cv=cv, n_jobs=-1,
        ).fit(x_train, y_train)
        fusion_searches.append({"ner_weight": weight, "C": search.best_params_["C"],
                                "cv_macro_f1": float(search.best_score_)})
        if best_fusion is None or search.best_score_ > best_fusion["search"].best_score_:
            best_fusion = {"weight": weight, "search": search}

    best_weight = best_fusion["weight"]
    best_fusion_search = best_fusion["search"]
    x_test_fused = hstack([csr_matrix(vectors[test_idx]), ner_test * best_weight], format="csr")
    fusion_test_predictions = best_fusion_search.predict(x_test_fused)
    base_cv = float(base_search.best_score_)
    fusion_cv = float(best_fusion_search.best_score_)
    # Select on training-only CV, with a minimum gain so noisy NER features do
    # not replace E5 based on a negligible score fluctuation. The held-out
    # partition remains reporting-only.
    min_fusion_gain = float(os.getenv("TOPIC_NER_MIN_CV_GAIN", "0.01"))
    selected = ("e5_ner_logistic_regression"
                if fusion_cv >= base_cv + min_fusion_gain
                else "e5_logistic_regression")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    # Save both candidates fitted on all labeled rows, even when one is not
    # selected, so comparative artifacts always match the recorded metrics.
    base_model = LogisticRegression(
        C=base_search.best_params_["C"], max_iter=3000,
        class_weight="balanced", random_state=seed,
    ).fit(vectors, labels)
    base_dir = MODEL_DIR / "e5_logistic_regression"
    base_dir.mkdir(parents=True, exist_ok=True)
    dump(base_model, base_dir / "classifier.joblib")
    (base_dir / "labels.json").write_text(json.dumps(base_model.classes_.tolist()), encoding="utf-8")

    final_vectorizer = DictVectorizer(sparse=True)
    all_ner_raw = final_vectorizer.fit_transform(ner_dicts)
    final_transformer = TfidfTransformer(norm="l2", use_idf=False)
    all_ner = final_transformer.fit_transform(all_ner_raw)
    all_fused = hstack([csr_matrix(vectors), all_ner * best_weight], format="csr")
    fusion_model = LogisticRegression(
        C=best_fusion_search.best_params_["C"], max_iter=3000,
        class_weight="balanced", random_state=seed,
    ).fit(all_fused, labels)
    fusion_dir = MODEL_DIR / "e5_ner_logistic_regression"
    fusion_dir.mkdir(parents=True, exist_ok=True)
    dump(fusion_model, fusion_dir / "classifier.joblib")
    dump(final_vectorizer, fusion_dir / "ner_vectorizer.joblib")
    dump(final_transformer, fusion_dir / "ner_transformer.joblib")
    (fusion_dir / "config.json").write_text(json.dumps({
        "embedding_model": model_name, "embedding_prefix": "passage:",
        "ner_feature_weight": best_weight,
    }, indent=2), encoding="utf-8")

    result = {
        "selected": selected,
        "selection_rule": f"E5 + NER must exceed E5-only CV macro F1 by at least {min_fusion_gain:.3f}; holdout used only for reporting",
        "model": model_name,
        "device": device,
        "rows": len(rows),
        "language_counts": {language: languages.count(language) for language in sorted(set(languages))},
        "topic_counts": counts,
        "training_labels": "topic column (suggested_topic weak labels unless manually reviewed)",
        "ner_confidence_threshold": os.getenv("NER_MIN_CONFIDENCE", "0.35"),
        "ner_feature_rows_with_entities": sum(bool(item) for item in ner_entities),
        "ner_entity_type_counts": {
            kind: sum(len(item.get(kind, [])) for item in ner_entities)
            for kind in ("PERSON", "ORGANIZATION", "LOCATION", "EVENT")
        },
        "e5_only": {
            "best_params": base_search.best_params_,
            "cv_macro_f1": base_cv,
            "held_out": {
                "macro_f1": float(f1_score(y_test, base_test_predictions, average="macro")),
                "accuracy": float(accuracy_score(y_test, base_test_predictions)),
                "language_scores": _language_scores(y_test, base_test_predictions, test_languages),
                "report": classification_report(y_test, base_test_predictions, labels=TOPIC_IDS,
                                                output_dict=True, zero_division=0),
            },
        },
        "e5_plus_ner": {
            "best_params": {"C": best_fusion_search.best_params_["C"], "ner_weight": best_weight},
            "cv_macro_f1": fusion_cv,
            "cv_gain_over_e5": fusion_cv - base_cv,
            "weight_search": fusion_searches,
            "held_out": {
                "macro_f1": float(f1_score(y_test, fusion_test_predictions, average="macro")),
                "accuracy": float(accuracy_score(y_test, fusion_test_predictions)),
                "language_scores": _language_scores(y_test, fusion_test_predictions, test_languages),
                "report": classification_report(y_test, fusion_test_predictions, labels=TOPIC_IDS,
                                                output_dict=True, zero_division=0),
            },
        },
        "labels_csv": str(Path(labels_csv).resolve()),
        "ner_features_csv": str(enriched_path.resolve()),
        "deployment_fit_rows": len(rows),
    }
    (MODEL_DIR / "experiment_metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (MODEL_DIR / "selected.json").write_text(json.dumps({
        "selected": selected,
        "selection_metric": result["selection_rule"],
        "training_labels": result["training_labels"],
        "scores": {"e5_logistic_regression": base_cv,
                   "e5_ner_logistic_regression": fusion_cv},
        "labels_csv": result["labels_csv"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _language_scores(y_true, predictions, languages):
    from sklearn.metrics import accuracy_score, f1_score
    result = {}
    for language in sorted(set(languages)):
        indices = [index for index, value in enumerate(languages) if value == language]
        truth = [y_true[index] for index in indices]
        predicted = [predictions[index] for index in indices]
        result[language] = {
            "macro_f1": float(f1_score(truth, predicted, average="macro")),
            "accuracy": float(accuracy_score(truth, predicted)),
            "support": len(indices),
        }
    return result


def _train_muril(texts, labels, train_idx, test_idx, y_train, y_test, test_languages, epochs, results, seed):
    import numpy as np
    import torch
    from sklearn.metrics import accuracy_score, classification_report, f1_score
    from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                              Trainer, TrainingArguments)

    model_name = "google/muril-base-cased"
    active_topics = sorted(set(labels))
    label_to_id = {label: index for index, label in enumerate(active_topics)}
    id_to_label = {index: label for label, index in label_to_id.items()}
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    max_length = int(os.getenv("TOPIC_MAX_LENGTH", "256"))
    encoded = tokenizer(texts, truncation=True, padding="max_length", max_length=max_length)

    class NewsTopicDataset(torch.utils.data.Dataset):
        def __init__(self, indices):
            self.indices = list(indices)
        def __len__(self):
            return len(self.indices)
        def __getitem__(self, position):
            index = self.indices[position]
            item = {key: torch.tensor(values[index]) for key, values in encoded.items()}
            item["labels"] = torch.tensor(label_to_id[labels[index]], dtype=torch.long)
            return item

    def metrics(prediction):
        logits, truth = prediction
        predicted = np.argmax(logits, axis=-1)
        return {"macro_f1": float(f1_score(truth, predicted, average="macro")),
                "accuracy": float(accuracy_score(truth, predicted))}

    model = AutoModelForSequenceClassification.from_pretrained(
        model_name, num_labels=len(active_topics), label2id=label_to_id, id2label=id_to_label
    )
    output_dir = MODEL_DIR / "muril_finetuned"
    train_batch_size = max(1, int(os.getenv("TOPIC_TRAIN_BATCH_SIZE", "2")))
    gradient_accumulation_steps = max(1, int(os.getenv("TOPIC_GRADIENT_ACCUMULATION_STEPS", "4")))
    args = TrainingArguments(
        output_dir=str(output_dir), num_train_epochs=epochs,
        per_device_train_batch_size=train_batch_size,
        per_device_eval_batch_size=max(1, min(2, train_batch_size)),
        gradient_accumulation_steps=gradient_accumulation_steps,
        gradient_checkpointing=torch.cuda.is_available(),
        learning_rate=2e-5, weight_decay=0.01, warmup_ratio=0.1,
        eval_strategy="epoch", save_strategy="no", load_best_model_at_end=False,
        logging_strategy="epoch", report_to="none", seed=seed,
        fp16=torch.cuda.is_available(),
    )
    trainer = Trainer(model=model, args=args,
                      train_dataset=NewsTopicDataset(train_idx),
                      eval_dataset=NewsTopicDataset(test_idx),
                      compute_metrics=metrics)
    trainer.train()
    output = trainer.predict(NewsTopicDataset(test_idx))
    predicted_ids = np.argmax(output.predictions, axis=-1)
    true_ids = [label_to_id[label] for label in y_test]
    predictions = [id_to_label[int(index)] for index in predicted_ids]
    language_scores = _language_scores(y_test, predictions, test_languages)
    results["muril_finetuned"] = {
        "macro_f1": float(f1_score(true_ids, predicted_ids, average="macro")),
        "accuracy": float(accuracy_score(true_ids, predicted_ids)),
        "language_scores": language_scores,
        "mean_language_macro_f1": sum(item["macro_f1"] for item in language_scores.values()) / len(language_scores),
        "report": classification_report(y_test, predictions, labels=TOPIC_IDS,
                                        output_dict=True, zero_division=0),
        "model": model_name,
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "artifact_ready": False,
    }
    try:
        trainer.save_model(str(output_dir))
        tokenizer.save_pretrained(output_dir)
        results["muril_finetuned"]["artifact_ready"] = True
    except Exception as exc:
        # Preserve the experiment metrics and allow a complete baseline model
        # to be selected even when disk exhaustion prevents saving MuRIL.
        results["muril_finetuned"]["artifact_error"] = str(exc)
        print(f"Warning: MuRIL metrics were computed, but its model/tokenizer could not be saved: {exc}")


class TrainedTopicClassifier:
    """Selected supervised classifier with multilingual zero-shot/rule fallbacks."""
    def __init__(self):
        self._backend = None
        self._model = None
        self._encoder = None
        self._tokenizer = None
        self._device = None
        self._ner_vectorizer = None
        self._ner_transformer = None
        self._ner_weight = 0.0
        self._zero_shot = None
        self._zero_shot_failure = None
        # FastAPI may classify multiple events concurrently. Serialize lazy
        # model initialization so requests cannot observe partial state.
        self._load_lock = threading.RLock()

    def _load_zero_shot(self):
        import torch
        from transformers import pipeline
        self._zero_shot = pipeline(
            "zero-shot-classification",
            model=ZERO_SHOT_MODEL,
            device=0 if torch.cuda.is_available() else -1,
        )
        self._backend = "multilingual_zero_shot"
        logger.info("Loaded multilingual zero-shot topic fallback %s", ZERO_SHOT_MODEL)

    def _load(self):
        with self._load_lock:
            self._load_locked()

    def _load_locked(self):
        # A backend identifier without its model is an invalid partial state.
        # Retry initialization instead of later failing at model.predict().
        if self._backend == "multilingual_zero_shot" and self._zero_shot is not None:
            return
        if self._backend in {"e5_logistic_regression", "e5_ner_logistic_regression", "muril_finetuned"} and self._model is not None:
            return
        self._backend = None
        requested_backend = os.getenv("TOPIC_CLASSIFIER_BACKEND", "auto").casefold()
        if requested_backend == "multilingual_zero_shot":
            try:
                self._load_zero_shot()
            except Exception as exc:
                self._zero_shot_failure = exc
                logger.warning("Could not load multilingual zero-shot topic model %s: %s", ZERO_SHOT_MODEL, exc)
            return
        selected_path = MODEL_DIR / "selected.json"
        if requested_backend != "auto":
            selected = requested_backend
        elif not selected_path.is_file():
            try:
                self._load_zero_shot()
            except Exception as exc:
                self._zero_shot_failure = exc
                logger.warning("No trained topic model is available and zero-shot loading failed: %s", exc)
            return
        else:
            selected = json.loads(selected_path.read_text(encoding="utf-8"))["selected"]
        try:
            if selected in {"e5_logistic_regression", "e5_ner_logistic_regression"}:
                from joblib import load
                from sentence_transformers import SentenceTransformer
                path = MODEL_DIR / selected
                self._model = load(path / "classifier.joblib")
                self._encoder = SentenceTransformer(os.getenv("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-base"))
                if selected == "e5_ner_logistic_regression":
                    config = json.loads((path / "config.json").read_text(encoding="utf-8"))
                    self._ner_vectorizer = load(path / "ner_vectorizer.joblib")
                    self._ner_transformer = load(path / "ner_transformer.joblib")
                    self._ner_weight = float(config["ner_feature_weight"])
            elif selected == "muril_finetuned":
                import torch
                from transformers import AutoModelForSequenceClassification, AutoTokenizer
                path = MODEL_DIR / selected
                self._device = "cuda" if torch.cuda.is_available() else "cpu"
                self._tokenizer = AutoTokenizer.from_pretrained(path)
                self._model = AutoModelForSequenceClassification.from_pretrained(path).to(self._device).eval()
            else:
                raise ValueError(f"Unknown topic classifier backend in selection: {selected}")
            self._backend = selected
        except Exception as exc:
            logger.exception("Could not load selected topic classifier %s; trying fallbacks", selected)
            self._backend = None
            self._model = self._encoder = None
            self._ner_vectorizer = self._ner_transformer = None
            try:
                self._load_zero_shot()
            except Exception as zero_shot_exc:
                self._zero_shot_failure = zero_shot_exc
                logger.warning("Multilingual zero-shot fallback failed: %s", zero_shot_exc)

    def predict_with_details(self, title, body, entities=None, language="en"):
        self._load()
        text = article_input(title, body)
        if self._backend == "multilingual_zero_shot":
            language = "ta" if str(language or "").lower().startswith("ta") else "en"
            descriptions = [
                (values.get(f"description_{language}") or values[f"label_{language}"])
                for topic, values in TAXONOMY.items()
                if topic != "other_current_affairs"
            ]
            topic_ids = [topic for topic in TOPIC_IDS if topic != "other_current_affairs"]
            template = (
                "இந்தச் செய்தி {} பற்றி உள்ளது."
                if language == "ta" else "This news article is about {}."
            )
            output = self._zero_shot(
                text,
                candidate_labels=descriptions,
                hypothesis_template=template,
                multi_label=True,
            )
            scored = sorted(
                zip(output["labels"], output["scores"]),
                key=lambda pair: float(pair[1]),
                reverse=True,
            )
            best_description, best_score = scored[0]
            best_topic = topic_ids[descriptions.index(best_description)]
            margin = float(best_score) - (float(scored[1][1]) if len(scored) > 1 else 0.0)
            model_name = ZERO_SHOT_MODEL
            if (float(best_score) < ZERO_SHOT_MIN_SCORE or margin < ZERO_SHOT_MIN_MARGIN
                    or best_topic == "other_current_affairs"):
                best_topic, model_name = _use_rule_if_classifier_abstained(
                    title, body, model_name
                )
            return {
                "topic": best_topic,
                "confidence": round(float(best_score), 4),
                "model": model_name,
                "margin": round(margin, 4),
            }
        if self._backend in {"e5_logistic_regression", "e5_ner_logistic_regression"}:
            if self._model is None or self._encoder is None:
                logger.error("Topic backend %s is missing its model or encoder; using rule fallback", self._backend)
                return None
            vector = self._encoder.encode([f"passage: {text}"], normalize_embeddings=True)
            if self._backend == "e5_ner_logistic_regression":
                from scipy.sparse import csr_matrix, hstack
                from backend.semantic_processing.topic_ner import entity_feature_dict
                ner_vector = self._ner_vectorizer.transform([entity_feature_dict(entities or {})])
                ner_vector = self._ner_transformer.transform(ner_vector) * self._ner_weight
                vector = hstack([csr_matrix(vector), ner_vector], format="csr")
            topic = normalize_topic_id(self._model.predict(vector)[0])
            raw_probabilities = self._model.predict_proba(vector)[0] if hasattr(self._model, "predict_proba") else []
            probabilities = sorted(raw_probabilities, reverse=True)
            score = float(probabilities[0]) if probabilities else 0.0
            margin = score - float(probabilities[1]) if len(probabilities) > 1 else score
            model_name = self._backend
            if (score < SUPERVISED_MIN_SCORE or margin < SUPERVISED_MIN_MARGIN
                    or topic == "other_current_affairs"):
                existing_topic = _best_existing_topic(
                    zip(getattr(self._model, "classes_", []), raw_probabilities)
                )
                if existing_topic:
                    topic = existing_topic
                    model_name = f"{model_name}+best_existing_topic"
                else:
                    topic, model_name = _use_rule_if_classifier_abstained(
                        title, body, model_name
                    )
            return {"topic": topic, "confidence": round(float(score), 4), "model": model_name}
        if self._backend == "muril_finetuned":
            if self._model is None or self._tokenizer is None:
                logger.error("MuRIL topic backend is missing its model or tokenizer; using rule fallback")
                return None
            import torch
            encoded = self._tokenizer(text, return_tensors="pt", truncation=True, max_length=384)
            encoded = {key: value.to(self._device) for key, value in encoded.items()}
            with torch.inference_mode():
                probabilities = torch.softmax(self._model(**encoded).logits, dim=-1)[0]
                prediction = int(probabilities.argmax().item())
            id_to_label = self._model.config.id2label
            score = float(probabilities[prediction].item())
            ranked = torch.sort(probabilities, descending=True).values
            margin = score - float(ranked[1].item()) if ranked.numel() > 1 else score
            topic = normalize_topic_id(id_to_label.get(prediction) or id_to_label.get(str(prediction)))
            model_name = self._backend
            if (score < SUPERVISED_MIN_SCORE or margin < SUPERVISED_MIN_MARGIN
                    or topic == "other_current_affairs"):
                class_scores = (
                    (id_to_label.get(index) or id_to_label.get(str(index)), float(value))
                    for index, value in enumerate(probabilities.tolist())
                )
                existing_topic = _best_existing_topic(class_scores)
                if existing_topic:
                    topic = existing_topic
                    model_name = f"{model_name}+best_existing_topic"
                else:
                    topic, model_name = _use_rule_if_classifier_abstained(
                        title, body, model_name
                    )
            return {
                "topic": topic,
                "confidence": round(score, 4),
                "model": model_name,
            }
        return None

    def predict(self, title, body, entities=None, language="en"):
        result = self.predict_with_details(title, body, entities=entities, language=language)
        return result["topic"] if result else None


def classify_event_topic_details(title, body, entities=None, language="en"):
    classifier = _get_classifier()
    result = classifier.predict_with_details(title, body, entities=entities, language=language)
    if result:
        return result
    return {
        "topic": classify_topic_rules(title, body),
        "confidence": 0.0,
        "model": "bilingual_keyword_fallback",
    }


def classify_event_topic(title, body, entities=None, language="en"):
    return classify_event_topic_details(title, body, entities=entities, language=language)["topic"]


_classifier = None
def _get_classifier():
    global _classifier
    if _classifier is None:
        _classifier = TrainedTopicClassifier()
    return _classifier


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Prepare and compare bilingual event-topic classifiers")
    parser.add_argument("--prepare-labels", action="store_true", help="Sample a new human annotation template")
    parser.add_argument("--input", default=str(BACKEND_DIR / "data" / "trafiltura_preprocessed.csv"))
    parser.add_argument("--output", default=str(BACKEND_DIR / "data" / "topic_labels_500_to_annotate.csv"))
    parser.add_argument("--per-language", type=int, default=250,
                        help="Rows to sample per language (default 250; 500 rows total)")
    parser.add_argument("--labels", help="Completed annotation CSV for A/B experiment")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--e5-only", action="store_true",
                        help="Tune and train only E5 embeddings + Logistic Regression")
    parser.add_argument("--e5-ner", action="store_true",
                        help="Compare E5-only against E5 + NER fusion and select by stratified CV")
    args = parser.parse_args()
    if args.prepare_labels:
        prepare_annotation_template(args.input, args.output, args.per_language)
    elif args.labels:
        if args.e5_ner:
            run_e5_ner_fusion_experiment(args.labels)
        elif args.e5_only:
            run_e5_experiment(args.labels)
        else:
            run_ab_experiment(args.labels, epochs=args.epochs)
    else:
        parser.error("Choose --prepare-labels or provide --labels after annotating the template")
