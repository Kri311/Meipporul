"""Bilingual, hierarchical abstractive summaries for clustered news articles.

The model is loaded lazily on the first event-detail request. Long articles are
summarized in overlapping token windows, then their summaries are reduced into
one event summary. If the model is unavailable, the service falls back to
source sentences rather than failing the API.
"""

import hashlib
import logging
import os
import re
import threading
from collections import OrderedDict

from backend.ingestion.tasks.text_cleaning import parse_clean_article

logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("SUMMARY_MODEL_NAME", "csebuetnlp/mT5_multilingual_XLSum")
MODEL_DEVICE = os.getenv("SUMMARY_DEVICE", "auto").casefold()
INPUT_TOKENS = 512
CHUNK_TOKENS = 448
CHUNK_OVERLAP = 48
MAX_NEW_TOKENS = 84
MAX_BULLETS = 5
CACHE_SIZE = 64

_model = None
_tokenizer = None
_device = None
_model_lock = threading.RLock()
_summary_cache = OrderedDict()


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
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        load_options = {"torch_dtype": torch.float16} if use_cuda else {}
        try:
            model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME, **load_options)
            model.to(device)
        except (RuntimeError, torch.cuda.OutOfMemoryError) as exc:
            if not use_cuda or "out of memory" not in str(exc).casefold():
                raise
            logger.warning("GPU memory is insufficient for summarization; loading model on CPU")
            if "model" in locals():
                del model
            import gc
            gc.collect()
            torch.cuda.empty_cache()
            model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
            model.to("cpu")
            device = "cpu"
        model.eval()
        _tokenizer, _model, _device = tokenizer, model, device
        return _tokenizer, _model, _device


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
            num_beams=2,
            no_repeat_ngram_size=3,
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
    if language != "ta":
        return bool(re.search(r"[A-Za-z]", text))
    letters = re.findall(r"[^\W\d_]", text, flags=re.UNICODE)
    tamil_letters = re.findall(r"[\u0B80-\u0BFF]", text)
    return bool(tamil_letters) and len(tamil_letters) / max(len(letters), 1) >= 0.35


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


def _pack_texts(texts, tokenizer):
    """Pack map summaries into groups that fit one model input window."""
    groups, current, current_tokens = [], [], 0
    for text in texts:
        count = len(tokenizer.encode(text, add_special_tokens=False))
        if current and current_tokens + count > INPUT_TOKENS - 16:
            groups.append(current)
            current, current_tokens = [], 0
        current.append(text)
        current_tokens += count
    if current:
        groups.append(current)
    return groups


def _event_key(articles, language):
    digest = hashlib.sha256()
    digest.update(language.encode("utf-8"))
    for article in articles:
        digest.update((article.title or "").encode("utf-8", errors="ignore"))
        digest.update(article_body(article).encode("utf-8", errors="ignore"))
    return digest.hexdigest()


def _fallback_bullets(articles, language, max_bullets):
    return extractive_summary_bullets(articles, language, max_bullets)


def summarize_event_bullets(articles, language, max_bullets=MAX_BULLETS):
    """Generate concise, same-language, source-grounded event-summary bullets."""
    articles = list(articles or [])
    if not articles:
        return []
    cache_key = _event_key(articles, language)
    with _model_lock:
        cached = _summary_cache.get(cache_key)
        if cached is not None:
            _summary_cache.move_to_end(cache_key)
            return list(cached[:max_bullets])

    cache_result = False
    try:
        tokenizer, _, _ = _load_model()
        article_chunks = []
        seen_bodies = set()
        for article in articles:
            body = article_body(article)
            normalized = re.sub(r"[^\w\u0B80-\u0BFF]", "", body.casefold())
            if not body or normalized in seen_bodies:
                continue
            seen_bodies.add(normalized)
            source_text = _clean_text(f"{article.title or ''}. {body}")
            article_chunks.extend(_token_chunks(source_text, tokenizer))

        if not article_chunks:
            return []

        # Map: summarize every token window, including the later sections of
        # long stories. Reduce: recursively merge article/chunk summaries.
        summaries = [_generate(chunk) for chunk in article_chunks]
        summaries = [summary for summary in summaries if summary]
        while len(summaries) > 1:
            groups = _pack_texts(summaries, tokenizer)
            if len(groups) == len(summaries):
                groups = [summaries[index:index + 2] for index in range(0, len(summaries), 2)]
            reduced = [_generate("\n".join(group)) for group in groups]
            reduced = [summary for summary in reduced if summary]
            if not reduced:
                break
            summaries = reduced

        generated_text = summaries[0] if summaries else ""
        if not generated_text or not _matches_language(generated_text, language):
            logger.warning("Abstractive output did not match language %s; using source-sentence fallback", language)
            bullets = _fallback_bullets(articles, language, max_bullets)
        else:
            bullets = _split_sentences(generated_text)[:max_bullets]
            if not bullets:
                bullets = _fallback_bullets(articles, language, max_bullets)
            else:
                cache_result = True
    except Exception:
        logger.exception("Abstractive summary failed; using source-sentence fallback")
        bullets = _fallback_bullets(articles, language, max_bullets)

    if cache_result:
        with _model_lock:
            _summary_cache[cache_key] = list(bullets)
            _summary_cache.move_to_end(cache_key)
            while len(_summary_cache) > CACHE_SIZE:
                _summary_cache.popitem(last=False)
    return bullets[:max_bullets]


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
