import re
with open("src/backend/api.py", "r") as f:
    api_code = f.read()

replacement = """@app.get("/events/")
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
                summary_text = a.clean_text[:200] + "..."
        
        topic = c.topic if c.topic else "General"
        
        events.append({
            "id": c.id,
            "title": c.representative_title,
            "image_url": image_url,
            "source_count": len(arts),
            "article_count": len(arts),
            "topic": topic,
            "tags": [topic],
            "summary": summary_text,
            "coverage": {},
            "articles": []
        })
    return events"""

api_code = re.sub(r'@app.get\("/events/"\).*?return events', replacement, api_code, flags=re.DOTALL)

with open("src/backend/api.py", "w") as f:
    f.write(api_code)
