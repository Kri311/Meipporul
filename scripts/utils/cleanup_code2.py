import os
import re

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"
path = os.path.join(base_dir, "ingestion", "tasks", "fetch_feed.py")

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old_normalize_block = """            # Remove title duplication from body using a smarter line-by-line check BEFORE collapsing newlines
            import re
            
            def normalize_str(s):
                from ingestion.tasks.text_cleaning import normalize_political_parties
                s = normalize_political_parties(s)
                return re.sub(r'[^a-zA-Z0-9\u0B80-\u0BFF]', '', s).lower()"""
                
new_normalize_block = """            # Remove title duplication from body using a smarter line-by-line check BEFORE collapsing newlines"""

if old_normalize_block in content:
    content = content.replace(old_normalize_block, new_normalize_block)
    
    # Add normalize_str to the top level
    top_level_func = """
def normalize_str(s):
    s = normalize_political_parties(s)
    return re.sub(r'[^a-zA-Z0-9\u0B80-\u0BFF]', '', s).lower()
"""
    content = content.replace("@celery_app.task", top_level_func + "\n\n@celery_app.task")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
    
print("Cleanup complete for fetch_feed.py.")
