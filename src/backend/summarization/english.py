from backend.summarization.common import (
    extractive_summary,
    extractive_summary_bullets,
    summarize_event as summarize,
    summarize_event_bullets as summarize_bullets,
)


def summarize_event(articles):
    return summarize(articles, "en")


def summarize_event_bullets(articles):
    return summarize_bullets(articles, "en")


def summarize_event_preview(articles):
    """Fast extractive teaser for event cards; full generation runs on detail."""
    return extractive_summary(articles, "en", max_sentences=8)


def summarize_event_preview_bullets(articles):
    return extractive_summary_bullets(articles, "en", max_sentences=8)
