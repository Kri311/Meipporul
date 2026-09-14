import pytest
from embeddings.pipeline import get_model, generate_semantic_text, EMBEDDING_MODEL_NAME
import numpy as np

def test_model_loading():
    model = get_model()
    assert model is not None
    # We should be using the multilingual model
    assert "paraphrase-multilingual-mpnet-base-v2" in EMBEDDING_MODEL_NAME

def test_cross_lingual_similarity():
    model = get_model()
    
    eng_text = "India defeats Australia in cricket match"
    tam_text = "கிரிக்கெட் போட்டியில் ஆஸ்திரேலியாவை இந்தியா வீழ்த்தியது"
    unrelated = "Apple announces new iPhone model"
    
    emb_eng = model.encode(eng_text, normalize_embeddings=True)
    emb_tam = model.encode(tam_text, normalize_embeddings=True)
    emb_unr = model.encode(unrelated, normalize_embeddings=True)
    
    sim_match = np.dot(emb_eng, emb_tam)
    sim_unrelated = np.dot(emb_eng, emb_unr)
    
    assert sim_match > 0.80, f"Expected high similarity between EN and TA, got {sim_match}"
    assert sim_unrelated < 0.50, f"Expected low similarity with unrelated, got {sim_unrelated}"

def test_semantic_text_generation():
    class DummyArticle:
        title = "Test Title"
        clean_text = "Test Body"
    
    art = DummyArticle()
    assert generate_semantic_text(art) == "Test Title Test Body"
