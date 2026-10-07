from fastapi import FastAPI, Depends, Query
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from backend.translator import translator_service
from backend.models.database import SessionLocal, NewsCluster, Article, Outlet

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_orientation(bucket):
    b = str(bucket).upper() if bucket else "CENTER"
    if "LEFT" in b: return "LEFT"
    if "RIGHT" in b: return "RIGHT"
    return "CENTER"

@app.get("/events/")
def get_events(lang: str = Query("en"), db: Session = Depends(get_db)):
    # Fetch clusters with more than 1 article efficiently
    from sqlalchemy.orm import joinedload
    
    # Eager load articles and outlets to avoid N+1 queries
    clusters = db.query(NewsCluster).order_by(NewsCluster.id.desc()).limit(150).all()
    
    cluster_ids = [c.id for c in clusters]
    arts_all = db.query(Article).options(joinedload(Article.outlet)).filter(Article.cluster_id.in_(cluster_ids)).all()
    
    arts_by_cluster = {}
    for a in arts_all:
        arts_by_cluster.setdefault(a.cluster_id, []).append(a)
    
    events = []
    
    for c in clusters:
        arts = arts_by_cluster.get(c.id, [])
        if not arts:
            continue
            
        image_url = None
        summary_text = ""
        
        for a in arts:
            if a.image_url and not image_url:
                image_url = a.image_url
            if a.clean_text and len(summary_text) < 200:
                txt = a.clean_text
                if txt.startswith('{'):
                    import json
                    try:
                        parsed = json.loads(txt)
                        txt = " ".join(str(v) for v in parsed.values())
                    except:
                        txt = txt.replace('{', '').replace('}', '').replace('"', '')
                if len(txt) > 250:
                    summary_text = txt[:250].rsplit(' ', 1)[0] + "..."
                else:
                    summary_text = txt
        
        topic = c.topic if c.topic else "General"
        
        # Translate
        title = c.representative_title
        if lang != "en":
            title = translator_service.translate(title, lang)
            summary_text = translator_service.translate(summary_text, lang)
            topic = translator_service.translate_topic(topic, lang)
        
        events.append({
            "id": c.id,
            "title": title,
            "image_url": image_url,
            "source_count": len(arts),
            "article_count": len(arts),
            "topic": topic,
            "tags": [topic],
            "summary": summary_text,
            "coverage": {},
            "articles": []
        })
    return events

@app.get("/events/{event_id}")
def get_event(event_id: int, lang: str = Query("en"), db: Session = Depends(get_db)):
    c = db.query(NewsCluster).filter(NewsCluster.id == event_id).first()
    if not c:
        return {"error": "not found"}
    arts = db.query(Article).filter(Article.cluster_id == c.id).all()
    
    image_url = None
    summary_text = ""
    for a in arts:
        if a.image_url and not image_url:
            image_url = a.image_url
        if a.clean_text and len(summary_text) < 200:
            txt = a.clean_text
            if txt.startswith('{'):
                import json
                try:
                    parsed = json.loads(txt)
                    txt = " ".join(str(v) for v in parsed.values())
                except:
                    txt = txt.replace('{', '').replace('}', '').replace('"', '')
            if len(txt) > 400:
                summary_text = txt[:400].rsplit(' ', 1)[0] + "..."
            else:
                summary_text = txt
            
    # Calculate coverage
    coverage_counts = {"LEFT": 0, "CENTER": 0, "RIGHT": 0}
    
    people = set()
    locations = set()
    articles_data = []
    
    for a in arts:
        orientation = get_orientation(a.outlet.orientation_bucket if a.outlet else None)
        coverage_counts[orientation] += 1
        
        articles_data.append({
            "id": a.id,
            "title": a.title,
            "image_url": a.image_url,
            "url": a.canonical_url,
            "orientation": orientation,
            "source_id": a.outlet.name if a.outlet else "News",
            "published_at": a.published_at.isoformat() if a.published_at else ""
        })
        
        if a.linked_entities:
            for p in a.linked_entities.get("PERSON", []):
                people.add(p.get("canonical_en") or p.get("text"))
            for p in a.linked_entities.get("LOCATION", []):
                locations.add(p.get("canonical_en") or p.get("text"))

    total = sum(coverage_counts.values()) or 1
    coverage = {
        k: int((v / total) * 100) for k, v in coverage_counts.items()
    }
                
    title = c.representative_title
    topic = c.topic if c.topic else "General"
    
    if lang != "en":
        title = translator_service.translate(title, lang)
        summary_text = translator_service.translate(summary_text, lang)
        topic = translator_service.translate_topic(topic, lang)
        
        for art in articles_data:
            art["title"] = translator_service.translate(art["title"], lang)
            
        entities["people"] = [translator_service.translate(p, lang) for p in entities["people"]]
        entities["locations"] = [translator_service.translate(p, lang) for p in entities["locations"]]

    return {
        "id": c.id,
        "title": title,
        "summary": summary_text,
        "image_url": image_url,
        "source_count": len(arts),
        "article_count": len(arts),
        "tags": [topic],
        "coverage": {},
        "articles": articles_data,
        "entities": {
            "people": list(people),
            "locations": list(locations)
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

@app.get("/metadata")
def get_metadata():
    return {
        "models": {
            "ner": "mistralai/Mistral-Small-3.1-24B-Instruct-2503",
            "embeddings": "BAAI/bge-m3",
            "clustering": "DBSCAN + Agglomerative"
        },
        "version": "Veritas Lens v2.0 (Local)",
        "pipeline_status": "Active"
    }
