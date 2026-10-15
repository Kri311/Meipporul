"""Bilingual, source-grounded bullet summaries for clustered news articles.

The model is loaded lazily on the first event-detail request. Long articles are
summarized in overlapping token windows. Distinct points are collected across
articles, with source sentences filling gaps when the model returns too little.
If the model is unavailable, the service falls back to source sentences rather
than failing the API.
"""

import hashlib
import logging
import os
import re
import threading
from collections import OrderedDict

from backend.ingestion.tasks.text_cleaning import parse_clean_article

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    _log_handler = logging.StreamHandler()
    _log_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(_log_handler)
    logger.propagate = False

BASE_MODEL_NAME = os.getenv("SUMMARY_BASE_MODEL", "csebuetnlp/mT5_multilingual_XLSum")
FINETUNED_MODEL_PATH = os.getenv(
    "SUMMARY_FINETUNED_MODEL_PATH",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models", "summarizer", "best")),
)
_configured_model = os.getenv("SUMMARY_MODEL_NAME", "auto").strip()
_prefer_finetuned = os.getenv("SUMMARY_PREFER_FINETUNED", "1").casefold() in {"1", "true", "yes"}
if (_prefer_finetuned and os.path.isdir(FINETUNED_MODEL_PATH) and
        _configured_model.casefold() in {"", "auto", BASE_MODEL_NAME.casefold()}):
    MODEL_NAME = FINETUNED_MODEL_PATH
else:
    MODEL_NAME = BASE_MODEL_NAME if _configured_model.casefold() in {"", "auto"} else _configured_model
MODEL_DEVICE = os.getenv("SUMMARY_DEVICE", "auto").casefold()
INPUT_TOKENS = 512
CHUNK_TOKENS = 448
CHUNK_OVERLAP = 48
MAX_NEW_TOKENS = 84
MAX_BULLETS = 7
MIN_EVENT_BULLETS = 4
CACHE_SIZE = 64

_model = None
_tokenizer = None
_device = None
_model_lock = threading.RLock()
_summary_cache = OrderedDict()
_last_summary_status = {"mode": "not_started", "language": None, "reason": None}


def article_body(article):
    return parse_clean_article(article.clean_text, article.title)[1]


def _clean_text(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _load_model():
    global _model, _tokenizer, _device
    if _model is not None:
        return _tokenizer, _model, _device

    with _model_lock:
        if _model is not None:
            return _tokenizer, _model, _device
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        torch_version = re.match(r"^(\d+)\.(\d+)", torch.__version__)
        if not torch_version or tuple(map(int, torch_version.groups())) < (2, 6):
            raise RuntimeError(
                f"The summarizer checkpoint requires PyTorch >=2.6.0 because Transformers "
                f"blocks unsafe .bin loading (installed: {torch.__version__}). Upgrade the "
                "project environment from requirements.txt, then restart the backend."
            )

        wanted = MODEL_DEVICE
        if wanted not in {"auto", "cpu", "cuda"}:
            logger.warning("Unknown SUMMARY_DEVICE=%s; using auto selection", wanted)
            wanted = "auto"
        use_cuda = wanted == "cuda" or (wanted == "auto" and torch.cuda.is_available())
        if use_cuda and not torch.cuda.is_available():
            logger.warning("CUDA requested for summarization but unavailable; using CPU")
            use_cuda = False
        device = "cuda" if use_cuda else "cpu"

        logger.info("Loading abstractive summarization model %s on %s", MODEL_NAME, device)
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, use_fast=False)
        load_options = {"dtype": torch.float16} if use_cuda else {}
        try:
            if os.path.isfile(os.path.join(MODEL_NAME, "adapter_config.json")):
                from peft import PeftConfig, PeftModel
                adapter_config = PeftConfig.from_pretrained(MODEL_NAME)
                base_model = AutoModelForSeq2SeqLM.from_pretrained(
                    adapter_config.base_model_name_or_path, **load_options
                )
                model = PeftModel.from_pretrained(base_model, MODEL_NAME)
            else:
                model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME, **load_options)
            model.to(device)
        except Exception as exc:
            # A CUDA build/runtime mismatch can fail during model loading before
            # it reports a conventional OOM. Retry on CPU so summaries still use
            # the configured abstractive model when possible.
            if not use_cuda:
                raise
            logger.warning("CUDA summarization model load failed (%s); retrying on CPU", exc)
            if "model" in locals():
                del model
            if "base_model" in locals():
                del base_model
            import gc
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            if os.path.isfile(os.path.join(MODEL_NAME, "adapter_config.json")):
                from peft import PeftConfig, PeftModel
                adapter_config = PeftConfig.from_pretrained(MODEL_NAME)
                base_model = AutoModelForSeq2SeqLM.from_pretrained(adapter_config.base_model_name_or_path)
                model = PeftModel.from_pretrained(base_model, MODEL_NAME)
            else:
                model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
            model.to("cpu")
            device = "cpu"
        model.eval()
        _tokenizer, _model, _device = tokenizer, model, device
        logger.info("Abstractive summarization model ready: model=%s device=%s", MODEL_NAME, device)
        return _tokenizer, _model, _device


def get_model_status():
    """Return in-process summarizer state without triggering a model download."""
    with _model_lock:
        if _model is not None:
            return {"model": MODEL_NAME, "loaded": True, "device": _device,
                    "last_summary": dict(_last_summary_status)}
        return {"model": MODEL_NAME, "loaded": False, "device": None,
                "last_summary": dict(_last_summary_status)}


def _generate_once(text, max_new_tokens=MAX_NEW_TOKENS):
    import torch

    tokenizer, model, device = _load_model()
    encoded = tokenizer(
        text, return_tensors="pt", truncation=True, max_length=INPUT_TOKENS
    )
    encoded = {key: value.to(device) for key, value in encoded.items()}
    with torch.inference_mode():
        generated = model.generate(
            **encoded,
            max_new_tokens=max_new_tokens,
            num_beams=4,
            no_repeat_ngram_size=2,
            do_sample=False,
            early_stopping=True,
        )
    return _clean_text(tokenizer.decode(
        generated[0], skip_special_tokens=True, clean_up_tokenization_spaces=False
    ))


def _generate(text, max_new_tokens=MAX_NEW_TOKENS):
    """Serialize model inference and retry on CPU if CUDA runs out of memory."""
    global _model, _device
    with _model_lock:
        try:
            return _generate_once(text, max_new_tokens)
        except RuntimeError as exc:
            if _device != "cuda" or "out of memory" not in str(exc).casefold():
                raise
            import torch
            logger.warning("CUDA OOM during summary generation; retrying on CPU")
            torch.cuda.empty_cache()
            _model.to("cpu")
            _device = "cpu"
            return _generate_once(text, max_new_tokens)


def _split_sentences(text):
    text = _clean_text(text)
    # The model may return numbered/bulleted lines or a short paragraph.
    text = re.sub(r"\s*(?:\n+|(?<=[.!?।])\s+)", "\n", text)
    pieces = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
        if line:
            pieces.append(line)
    return pieces


def _matches_language(text, language):
    letters = re.findall(r"[^\W\d_]", text, flags=re.UNICODE)
    if not letters:
        return False
    if language == "ta":
        tamil_letters = re.findall(r"[\u0B80-\u0BFF]", text)
        return bool(tamil_letters) and len(tamil_letters) / len(letters) >= 0.35
    latin_letters = re.findall(r"[A-Za-z\u00C0-\u024F]", text)
    return bool(latin_letters) and len(latin_letters) / len(letters) >= 0.65


_SUMMARY_STOPWORDS = {
    "en": {"the", "and", "for", "with", "from", "that", "this", "their", "they", "will",
           "said", "says", "are", "was", "were", "has", "have", "had", "into", "after",
           "before", "under", "over", "about", "more", "than", "its", "who", "which",
           "when", "where", "what", "how", "not", "but", "also", "been", "being"},
    "ta": {"இந்த", "அந்த", "என்று", "என", "க்கு", "கள்", "உடன்", "மற்றும்", "ஆக", "மீது",
           "முன்பு", "பிறகு", "தனது", "அவர்", "அவர்கள்", "ஒரு", "பல", "இதன்", "அதில்"},
}


def _grounded_in_source(summary, source):
    """Reject summary points with unsupported names or weak lexical evidence."""
    source = _clean_text(source)
    source_folded = source.casefold()

    # English title-case multiword entities are a strong signal of an invented
    # place, organization, or person when the source never mentions them.
    for match in re.finditer(
        r"\b[A-Z][a-z]+(?:\s+(?:(?:of|the|and)\s+)?[A-Z][a-z]+)+\b", summary
    ):
        entity = re.sub(r"^(?:The|A|An)\s+", "", match.group(0)).casefold()
        if entity and entity not in source_folded:
            return False

    def tokens(text):
        return [token.casefold() for token in re.findall(r"[\w\u0B80-\u0BFF]+", text)]

    source_tokens = set(tokens(source))
    content = [token for token in tokens(summary)
               if len(token) >= 3 and token not in _SUMMARY_STOPWORDS["ta"]
               and token not in _SUMMARY_STOPWORDS["en"]]
    if not content:
        return False

    def is_supported(token):
        if token in source_tokens:
            return True
        # Match simple English inflections and Tamil agglutinative forms where
        # a meaningful token occurs as a substring of the source word.
        if re.fullmatch(r"[a-z]+", token):
            stem = re.sub(r"(?:ing|ed|es|s)$", "", token)
            return len(stem) >= 3 and any(
                stem == source_token or stem == re.sub(r"s$", "", source_token)
                for source_token in source_tokens
            )
        if re.search(r"[\u0B80-\u0BFF]", token) and len(token) >= 4:
            return any(token in word or word in token for word in source_tokens
                       if re.search(r"[\u0B80-\u0BFF]", word))
        return False

    support_ratio = sum(is_supported(token) for token in content) / len(content)
    # Tamil morphology and subject attribution are especially easy for a
    # generative model to alter while keeping the topic vocabulary. Be more
    # conservative in Tamil; uncertain content should come from the articles.
    minimum_support = 0.85 if re.search(r"[\u0B80-\u0BFF]", summary) else 0.65
    return support_ratio >= minimum_support


def _token_chunks(text, tokenizer):
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if not token_ids:
        return []
    chunks = []
    step = CHUNK_TOKENS - CHUNK_OVERLAP
    for start in range(0, len(token_ids), step):
        chunk_ids = token_ids[start:start + CHUNK_TOKENS]
        if not chunk_ids:
            break
        chunks.append(tokenizer.decode(chunk_ids, skip_special_tokens=True))
        if start + CHUNK_TOKENS >= len(token_ids):
            break
    return chunks


def _event_key(articles, language):
    digest = hashlib.sha256()
    digest.update(language.encode("utf-8"))
    for article in articles:
        digest.update((article.title or "").encode("utf-8", errors="ignore"))
        digest.update(article_body(article).encode("utf-8", errors="ignore"))
    return digest.hexdigest()


def _fallback_bullets(articles, language, max_bullets):
    return extractive_summary_bullets(articles, language, max_bullets)


def _summary_prompt(text, language, title=""):
    if language == "ta":
        instruction = "செய்தி உள்ளடக்கத்தை உண்மையான முக்கிய அம்சங்களாக சுருக்கவும்"
    else:
        instruction = "summarize English news into concise factual bullet points"
    return f"{instruction}\nheadline: {title}\nbody: {text}"


def _bullet_key(text):
    return re.sub(r"[^\w\u0B80-\u0BFF]", "", text.casefold())


def _not_redundant(candidate, selected):
    """Reject duplicate source points and paraphrases already represented."""
    candidate_words = set(re.findall(r"[\w\u0B80-\u0BFF]+", candidate.casefold()))
    if not candidate_words:
        return False
    for current in selected:
        current_words = set(re.findall(r"[\w\u0B80-\u0BFF]+", current.casefold()))
        overlap = len(candidate_words & current_words) / max(1, min(len(candidate_words), len(current_words)))
        if overlap >= 0.72:
            return False
    return True


def summarize_event_bullets(articles, language, max_bullets=MAX_BULLETS):
    """Generate concise, same-language, source-grounded event-summary bullets."""
    articles = list(articles or [])
    if not articles:
        return []
    global _last_summary_status
    language = "ta" if language == "ta" else "en"
    cache_key = _event_key(articles, language)
    with _model_lock:
        cached = _summary_cache.get(cache_key)
        if cached is not None:
            _summary_cache.move_to_end(cache_key)
            _last_summary_status = {"mode": "abstractive_cached", "language": language, "reason": None}
            logger.info("Summary served from abstractive cache: language=%s bullets=%d", language, len(cached))
            return list(cached[:max_bullets])

    cache_result = False
    chunk_count = 0
    try:
        logger.info("Generating event summary: language=%s articles=%d model=%s", language, len(articles), MODEL_NAME)
        tokenizer, _, _ = _load_model()
        bullets_by_article = []
        seen_bodies = set()
        for article in articles:
            body = article_body(article)
            normalized = re.sub(r"[^\w\u0B80-\u0BFF]", "", body.casefold())
            if not body or normalized in seen_bodies:
                continue
            seen_bodies.add(normalized)
            chunk_bullets = []
            chunks = _token_chunks(body, tokenizer)
            chunk_count += len(chunks)
            for chunk in chunks:
                source_text = _clean_text(f"{article.title or ''}. {chunk}")
                chunk_summary = _generate(_summary_prompt(chunk, language, article.title or ""))
                if chunk_summary and _matches_language(chunk_summary, language):
                    for point in _split_sentences(chunk_summary):
                        if not _grounded_in_source(point, chunk):
                            logger.warning("Discarding weakly grounded %s summary point", language)
                            continue
                        if len(point) >= 25 and _bullet_key(point) not in {
                            _bullet_key(existing) for existing in chunk_bullets
                        }:
                            chunk_bullets.append(point)
            if chunk_bullets:
                bullets_by_article.append(chunk_bullets)

        if not bullets_by_article:
            logger.warning("Abstractive output did not match language %s; using source-sentence fallback", language)
            bullets = _fallback_bullets(articles, language, max_bullets)
            _last_summary_status = {"mode": "extractive_fallback", "language": language,
                                   "reason": "empty_or_wrong_language_model_output"}
        else:
            # Keep chunk/article summaries as separate points instead of
            # reducing them into one short paragraph. Round-robin selection
            # spreads coverage across outlets and long-article sections.
            bullets = []
            max_depth = max((len(points) for points in bullets_by_article), default=0)
            for depth in range(max_depth):
                for article_points in bullets_by_article:
                    if depth >= len(article_points):
                        continue
                    point = article_points[depth]
                    if _not_redundant(point, bullets):
                        bullets.append(point)
                    if len(bullets) >= max_bullets:
                        break
                if len(bullets) >= max_bullets:
                    break

            # mT5 XLSum often returns one concise sentence per chunk. Add
            # distinct source sentences when needed so an event with several
            # verified details does not collapse to a single point.
            if len(bullets) < MIN_EVENT_BULLETS:
                for point in extractive_summary_bullets(articles, language, max_bullets):
                    if _not_redundant(point, bullets):
                        bullets.append(point)
                    if len(bullets) >= min(max_bullets, MIN_EVENT_BULLETS):
                        break
            cache_result = bool(bullets)
            _last_summary_status = {"mode": "abstractive", "language": language, "reason": None}
            logger.info("Abstractive summary generated: language=%s chunks=%d bullets=%d", language, chunk_count, len(bullets))
    except Exception:
        logger.exception("Abstractive summary failed; using source-sentence fallback")
        bullets = _fallback_bullets(articles, language, max_bullets)
        _last_summary_status = {"mode": "extractive_fallback", "language": language,
                               "reason": "model_load_or_generation_error"}

    if cache_result:
        with _model_lock:
            _summary_cache[cache_key] = list(bullets)
            _summary_cache.move_to_end(cache_key)
            while len(_summary_cache) > CACHE_SIZE:
                _summary_cache.popitem(last=False)
    return bullets[:max_bullets]


def merge_article_bullets(articles, language, max_bullets=MAX_BULLETS):
    """Create an event summary from persisted per-article bullets, without generation."""
    language = "ta" if language == "ta" else "en"
    field = "summary_ta_bullets" if language == "ta" else "summary_en_bullets"
    per_article = []
    def article_order(item):
        published = getattr(item, "published_at", None)
        return (published.timestamp() if published else 0, getattr(item, "id", None) or 0)

    for article in sorted(articles or [], key=article_order):
        raw = getattr(article, field, None)
        if isinstance(raw, str):
            try:
                import json
                raw = json.loads(raw)
            except (TypeError, ValueError):
                raw = [raw]
        points = [ _clean_text(point) for point in (raw or []) if _clean_text(point) ]
        if points:
            per_article.append(points)

    selected = []
    max_depth = max((len(points) for points in per_article), default=0)
    for depth in range(max_depth):
        for points in per_article:
            if depth < len(points) and _not_redundant(points[depth], selected):
                selected.append(points[depth])
                if len(selected) >= max_bullets:
                    return selected
    return selected


def summarize_event(articles, language):
    return " ".join(summarize_event_bullets(articles, language))


def extractive_summary(articles, language, max_sentences=4):
    """Fast source-sentence preview used on event-list cards and as fallback."""
    return " ".join(extractive_summary_bullets(articles, language, max_sentences))


def extractive_summary_bullets(articles, language, max_sentences=4):
    """Return distinct, reasonably informative sentences from source articles."""
    candidates = []
    seen = set()
    for article in articles:
        body = article_body(article)
        parts = re.split(r"(?<=[.!?।])\s+", body)
        for part in parts:
            sentence = _clean_text(part)
            key = re.sub(r"[^\w\u0B80-\u0BFF]", "", sentence.casefold())
            if len(sentence) >= 45 and key not in seen:
                seen.add(key)
                score = min(len(sentence), 260) - max(0, len(sentence) - 320)
                candidates.append((score, sentence))
    if not candidates:
        fallback = next((article_body(article) for article in articles if article_body(article)), "")
        return [fallback[:280].rsplit(" ", 1)[0]] if fallback else []
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [sentence for _, sentence in candidates[:max_sentences]]
