import csv
import sys
import os
import json
from collections import defaultdict
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from backend.models.database import SessionLocal, Article, NewsCluster

# Set up logging
log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(log_dir, 'pipeline.log'),
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("Event_Generation")

EVENT_CSV_FIELDNAMES = [
    "event_id", "headline", "start_date", "end_date", "location", 
    "people", "organizations", "topics", "articles_count", "sources",
    "summary", "summary_en_bullets", "summary_ta_bullets",
]

def generate_events(output_path=os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "data", "events_representation.csv")):
    logger.info("Starting Event Representation generation with Entity Linking...")
    db = SessionLocal()
    try:
        clusters = db.query(NewsCluster).all()
        
        events = []
        for cluster in clusters:
            articles = db.query(Article).filter(Article.cluster_id == cluster.id).all()
            if not articles:
                continue
                
            dates = [a.published_at for a in articles if a.published_at]
            start_date = min(dates).isoformat() if dates else ""
            end_date = max(dates).isoformat() if dates else ""
            
            # Aggregate NER using Cross-lingual Linked Entities
            merged_people = {}
            merged_orgs = {}
            merged_locs = defaultdict(int)
            
            sources = set()
            
            for art in articles:
                if art.outlet and art.outlet.slug:
                    sources.add(art.outlet.slug)
                
                linked = art.linked_entities
                if linked:
                    # People
                    for p in linked.get("PERSON", []):
                        key = p["kg_id"] if p.get("kg_id") else p["text"]
                        merged_people[key] = p
                    # Organizations
                    for o in linked.get("ORGANIZATION", []):
                        key = o["kg_id"] if o.get("kg_id") else o["text"]
                        merged_orgs[key] = o
                    # Locations (we count frequencies to find main location)
                    for l in linked.get("LOCATION", []):
                        key = l["canonical_en"] if l.get("kg_id") else l["text"]
                        merged_locs[key] += 1
                elif art.named_entities:
                    # Fallback for old articles without linked_entities
                    for p in art.named_entities.get("PERSON", []):
                        merged_people[p] = {"text": p, "kg_id": None, "canonical_en": p, "canonical_ta": p}
                    for o in art.named_entities.get("ORGANIZATION", []):
                        merged_orgs[o] = {"text": o, "kg_id": None, "canonical_en": o, "canonical_ta": o}
                    for l in art.named_entities.get("LOCATION", []):
                        merged_locs[l] += 1
                        
            main_location = max(merged_locs, key=merged_locs.get) if merged_locs else ""
            
            # Convert aggregated dicts to lists for JSON export
            people_list = list(merged_people.values())
            orgs_list = list(merged_orgs.values())
            
            events.append({
                "event_id": cluster.id,
                "headline": cluster.representative_title,
                "start_date": start_date,
                "end_date": end_date,
                "location": main_location,
                "people": json.dumps(people_list, ensure_ascii=False),
                "organizations": json.dumps(orgs_list, ensure_ascii=False),
                "topics": cluster.topic or "",
                "articles_count": len(articles),
                "sources": json.dumps(list(sources), ensure_ascii=False),
                "summary": json.dumps(cluster.summary or {
                    "en": cluster.summary_en_bullets or [],
                    "ta": cluster.summary_ta_bullets or [],
                }, ensure_ascii=False),
                "summary_en_bullets": json.dumps(cluster.summary_en_bullets or [], ensure_ascii=False),
                "summary_ta_bullets": json.dumps(cluster.summary_ta_bullets or [], ensure_ascii=False),
            })
            
        events.sort(key=lambda x: x.get('end_date', ''), reverse=True)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=EVENT_CSV_FIELDNAMES)
            writer.writeheader()
            for ev in events:
                writer.writerow(ev)
                
        logger.info(f"Generated {len(events)} event representations into {output_path}")
        print(f"Exported {len(events)} events to {output_path}")
    finally:
        db.close()

if __name__ == "__main__":
    generate_events()
