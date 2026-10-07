"""
Veritas Lens — Cross-lingual Entity Linking
=============================================
Maps extracted text entities (Tamil/English) to unified Knowledge Graph IDs
(Wikidata Q-identifiers). This allows the system to recognize that
"Chennai" and "சென்னை" are the exact same entity.
"""

import os
import json
import logging

logger = logging.getLogger("EntityLinker")

class EntityLinker:
    def __init__(self):
        self.kg = {}
        self._load_kg()

    def _load_kg(self):
        """Load the local knowledge graph mapping."""
        kg_path = os.path.join(os.path.dirname(__file__), 'knowledge_graph.json')
        if os.path.exists(kg_path):
            with open(kg_path, 'r', encoding='utf-8') as f:
                self.kg = json.load(f)
        else:
            logger.warning(f"Knowledge graph file not found at {kg_path}")

    def link_entities(self, named_entities: dict) -> dict:
        """
        Takes a dict of named_entities (e.g. {"PERSON": ["M.K. Stalin"]})
        and returns a dict of linked entities with kg_id and canonical names.
        
        Format:
        {
            "PERSON": [
                {
                    "text": "M.K. Stalin",
                    "kg_id": "Q3530664",
                    "canonical_en": "M. K. Stalin",
                    "canonical_ta": "மு. க. ஸ்டாலின்"
                }
            ]
        }
        """
        linked = {}
        for entity_type, entities in named_entities.items():
            linked_list = []
            for text in entities:
                # Try direct match
                match = self.kg.get(text)
                
                # Try case-insensitive match
                if not match:
                    for key, val in self.kg.items():
                        if key.lower() == text.lower():
                            match = val
                            break
                            
                if match:
                    linked_list.append({
                        "text": text,
                        "kg_id": match["kg_id"],
                        "canonical_en": match["en"],
                        "canonical_ta": match["ta"]
                    })
                else:
                    # Unlinked entity
                    linked_list.append({
                        "text": text,
                        "kg_id": None,
                        "canonical_en": text,
                        "canonical_ta": text
                    })
            linked[entity_type] = linked_list
            
        return linked
