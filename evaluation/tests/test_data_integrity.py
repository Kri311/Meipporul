import csv
import os
import pytest
import re

CSV_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw_processed.csv')

@pytest.fixture(scope="module")
def articles():
    """Load the CSV data once for all tests."""
    data = []
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)
    return data

def test_file_exists(articles):
    """Verify the data file was created."""
    assert os.path.exists(CSV_PATH), "raw_processed.csv does not exist."
    assert len(articles) > 0, "No articles found in the CSV."

def test_no_html_tags(articles):
    """Ensure no HTML tags slipped through the cleaning phase."""
    html_regex = re.compile(r'<[^>]+>')
    failed_articles = 0
    
    for article in articles:
        if html_regex.search(article.get('clean_text', '')):
            failed_articles += 1
            
    assert failed_articles == 0, f"{failed_articles} articles contain residual HTML tags."

def test_length_requirements(articles):
    """Validate article length categorizations and minimum limits."""
    for article in articles:
        clean_text = article.get('clean_text', '')
        word_count = len(clean_text.split())
        char_count = len(clean_text)
        
        # Minimum character limit enforcement
        assert char_count >= 200, "Found article with fewer than 200 characters."
        
        # Category verification
        category = article.get('article_length', '')
        if category == 'short':
            assert word_count < 250, "Short article exceeds 249 words."
        elif category == 'medium':
            assert word_count >= 250, "Medium article has fewer than 250 words."
            assert word_count < 800, "Medium article exceeds 799 words."
        elif category == 'long':
            assert word_count >= 800, "Long article has fewer than 800 words."

def test_unwanted_keywords_removed(articles):
    """Verify blocked commercial and mobile keywords are completely absent."""
    blocked_keywords = [
        'smartphone', 'prepaid', 'postpaid', 'bsnl', 'jio plan', 
        'airtel plan', 'vi plan', 'flipkart', 'lpg price'
    ]
    
    failed_articles = 0
    for article in articles:
        title_lower = article.get('title', '').lower()
        url_lower = article.get('canonical_url', '').lower()
        for keyword in blocked_keywords:
            if keyword in title_lower or keyword in url_lower:
                failed_articles += 1
                break
                
    assert failed_articles == 0, f"{failed_articles} articles contain blocked commercial keywords in title or URL."

def test_boilerplate_removed(articles):
    """Check for absence of 'Loading stories' and 'Recommended' sections."""
    boilerplate_terms = ['loading stories', 'recommended for you']
    
    for article in articles:
        text_lower = article.get('clean_text', '').lower()
        for term in boilerplate_terms:
            assert term not in text_lower, f"Found boilerplate text: '{term}'"

def test_unique_guids(articles):
    """Ensure deduplication was successful by checking GUID uniqueness."""
    guids = [article.get('guid') for article in articles]
    unique_guids = set(guids)
    assert len(guids) == len(unique_guids), "Duplicate GUID values detected."
