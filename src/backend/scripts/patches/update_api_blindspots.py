import re
with open("src/backend/api.py", "r") as f:
    api_code = f.read()

replacement = """@app.get("/events/{event_id}/blindspots")
def get_event_blindspots(event_id: int, lang: str = Query("en"), db: Session = Depends(get_db)):
    c = db.query(NewsCluster).filter(NewsCluster.id == event_id).first()
    arts = db.query(Article).filter(Article.cluster_id == c.id).all()
    
    entities = []
    for a in arts:
        if a.linked_entities:
            for p in a.linked_entities.get("PERSON", []):
                entities.append({"type": "PERSON", "reason": p.get("canonical_en") or p.get("text"), "score": 1.0})
            for p in a.linked_entities.get("LOCATION", []):
                entities.append({"type": "LOCATION", "reason": p.get("canonical_en") or p.get("text"), "score": 1.0})
            for p in a.linked_entities.get("ORGANIZATION", []):
                entities.append({"type": "ORG", "reason": p.get("canonical_en") or p.get("text"), "score": 1.0})
    
    # deduplicate
    unique = []
    seen = set()
    for e in entities:
        if e["reason"] not in seen:
            seen.add(e["reason"])
            unique.append(e)
            
    return unique[:8]"""

api_code = re.sub(r'@app.get\("/events/{event_id}/blindspots"\).*?return \[\]', replacement, api_code, flags=re.DOTALL)

with open("src/backend/api.py", "w") as f:
    f.write(api_code)
