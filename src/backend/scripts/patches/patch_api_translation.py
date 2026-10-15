import re
with open("src/backend/api.py", "r") as f:
    api_code = f.read()

# Add import
api_code = api_code.replace("from backend.models.database import", "from backend.translator import translator_service\nfrom backend.models.database import")

# Update get_events
replacement_events = """        topic = c.topic if c.topic else "General"
        
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
            "coverage": coverage,
            "articles": []
        })"""

api_code = re.sub(r'        topic = c\.topic if c\.topic else "General".*?events\.append\(\{.*?\}\)', replacement_events, api_code, flags=re.DOTALL)

# Update get_event
replacement_event = """    title = c.representative_title
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
        "tags": [topic],"""

api_code = re.sub(r'    return \{\n        "id": c\.id,\n        "title": c\.representative_title,\n        "summary": summary_text,\n        "image_url": image_url,\n        "source_count": len\(arts\),\n        "article_count": len\(arts\),\n        "tags": \[c\.topic\] if c\.topic else \["News"\],', replacement_event, api_code, flags=re.DOTALL)

with open("src/backend/api.py", "w") as f:
    f.write(api_code)
