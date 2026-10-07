import os
import sys
import json
import re
from typing import List, Dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from backend.models.database import SessionLocal, Article
from backend.ner_pipeline.zero_shot.nlp_pipeline import normalize_text, get_ner_pipeline, rule_based_extraction

def clean_and_normalize(text: str) -> str:
    """Normalize text: remove whitespaces, newlines, fix unicode, etc."""
    if not text:
        return ""
    # Remove URLs
    text = re.sub(r'http\S+|www.\S+', '', text)
    # Remove hashtags
    text = re.sub(r'#\w+', '', text)
    # Normalize unicode and whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.replace('"', '"').replace('"', '"')
    return text.strip()

def create_dataset():
    db = SessionLocal()
    try:
        # Fetch articles for dataset
        articles = db.query(Article).filter(
            Article.clean_text.isnot(None),
            Article.clean_text != ""
        ).limit(1000).all() # Limit to 1000 for creating training data
        
        dataset = []
        for article in articles:
            # Extract headline and content, clean them
            headline = clean_and_normalize(article.title)
            content = clean_and_normalize(article.clean_text)
            
            lang = article.language if article.language else 'unknown'
            
            dataset.append({
                "language": lang,
                "headline": headline,
                "content": content
            })
            
        # Group by language (Tamil, English, etc.)
        tamil_data = [d for d in dataset if d['language'] == 'ta']
        english_data = [d for d in dataset if d['language'] == 'en']
        mixed_data = [d for d in dataset if d['language'] not in ('ta', 'en')]
        
        output_dir = os.path.join(os.path.dirname(__file__), 'dataset')
        os.makedirs(output_dir, exist_ok=True)
        
        with open(os.path.join(output_dir, 'tamil_corpus.json'), 'w', encoding='utf-8') as f:
            json.dump(tamil_data, f, ensure_ascii=False, indent=2)
            
        with open(os.path.join(output_dir, 'english_corpus.json'), 'w', encoding='utf-8') as f:
            json.dump(english_data, f, ensure_ascii=False, indent=2)
            
        print(f"Prepared {len(tamil_data)} Tamil and {len(english_data)} English articles for fine-tuning.")
        print(f"Data saved to {output_dir}")
        
    finally:
        db.close()

if __name__ == "__main__":
    create_dataset()
