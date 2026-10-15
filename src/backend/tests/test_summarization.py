import json

from backend.summarization import common


class Article:
    def __init__(self, title, body):
        self.title = title
        self.clean_text = json.dumps({title: body}, ensure_ascii=False)


class CharacterTokenizer:
    def encode(self, text, add_special_tokens=False):
        return [ord(char) for char in text]

    def decode(self, token_ids, skip_special_tokens=True):
        return "".join(chr(token_id) for token_id in token_ids)


def test_abstractive_summary_uses_full_text_and_returns_language_bullets(monkeypatch):
    article = Article("Update", "The government announced new measures. " * 80)
    generated_inputs = []
    monkeypatch.setattr(common, "_load_model", lambda: (CharacterTokenizer(), object(), "cpu"))

    def fake_generate(text, max_new_tokens=common.MAX_NEW_TOKENS):
        generated_inputs.append(text)
        return "Officials announced new measures. The plan begins next week."

    monkeypatch.setattr(common, "_generate", fake_generate)
    common._summary_cache.clear()

    bullets = common.summarize_event_bullets([article], "en")

    assert len(generated_inputs) > 1  # long body was chunked instead of truncated
    assert len(bullets) == 2
    assert all("announced" in bullet or "begins" in bullet for bullet in bullets)


def test_tamil_summary_is_returned_as_tamil_bullets(monkeypatch):
    article = Article("செய்தி", "அரசு புதிய திட்டத்தை அறிவித்தது. " * 20)
    monkeypatch.setattr(common, "_load_model", lambda: (CharacterTokenizer(), object(), "cpu"))
    monkeypatch.setattr(common, "_generate", lambda text, max_new_tokens=common.MAX_NEW_TOKENS: "அரசு புதிய திட்டத்தை அறிவித்தது. திட்டம் அடுத்த வாரம் தொடங்கும்.")
    common._summary_cache.clear()

    bullets = common.summarize_event_bullets([article], "ta")

    assert len(bullets) == 2
    assert all(any("\u0b80" <= char <= "\u0bff" for char in bullet) for bullet in bullets)


def test_model_failure_falls_back_to_source_sentences(monkeypatch):
    article = Article("Report", "Officials confirmed the detailed public safety response will continue through the coming week.")
    monkeypatch.setattr(common, "_load_model", lambda: (_ for _ in ()).throw(OSError("model unavailable")))
    common._summary_cache.clear()

    bullets = common.summarize_event_bullets([article], "en")

    assert bullets
    assert "public safety response" in bullets[0]
