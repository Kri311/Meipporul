from backend.ingestion.tasks.text_cleaning import classify_topic, is_usable_article_body


def test_common_substring_us_does_not_force_world_news():
    assert classify_topic("Business focuses on local investment", "The company expanded its services") == "economy"


def test_international_headline_is_world_news():
    assert classify_topic("China and India agree on new border talks", "Officials met this week") == "world_news"


def test_local_place_is_a_topic_and_not_forced_by_outlet():
    assert classify_topic("Vellore hospital receives new equipment", "Local officials announced the project") == "local_news"


def test_single_word_or_short_extraction_is_rejected():
    assert not is_usable_article_body("Breaking")
    assert not is_usable_article_body("A short fragment with only a few words.")


def test_real_article_body_passes_quality_gate():
    body = "The district administration announced a new water project today. " * 4
    assert is_usable_article_body(body)
