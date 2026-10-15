import re
with open("src/backend/api.py", "r") as f:
    api_code = f.read()

replacement = """@app.get("/events/")
def get_events(lang: str = Query("en"), db: Session = Depends(get_db)):
    clusters = db.query(NewsCluster).order_by(NewsCluster.id.desc()).all()
    events = []
    
    for c in clusters:
        arts = db.query(Article).filter(Article.cluster_id == c.id).all()
        if not arts:
            continue
            
        image_url = None
        summary_text = ""
        coverage_counts = {"LEFT": 0, "CENTER": 0, "RIGHT": 0}
        
        for a in arts:
            if a.image_url and not image_url:
                image_url = a.image_url
            if a.clean_text and len(summary_text) < 200:
                summary_text = a.clean_text[:200] + "..."
                
            orientation = get_orientation(a.outlet.orientation_bucket if a.outlet else None)
            coverage_counts[orientation] += 1
            
        total = sum(coverage_counts.values()) or 1
        coverage = {k: int((v / total) * 100) for k, v in coverage_counts.items()}
        
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
            "coverage": coverage,
            "articles": []
        })
    return events"""

api_code = re.sub(r'@app.get\("/events/"\).*?return events', replacement, api_code, flags=re.DOTALL)

with open("src/backend/api.py", "w") as f:
    f.write(api_code)
