import os
import re

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"

# files to fix
f1 = os.path.join(base_dir, "fetch_rss_standalone.py")
f2 = os.path.join(base_dir, "ingestion", "tasks", "fetch_feed.py")

for path in [f1, f2]:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Move import normalize_political_parties to the top
    if "normalize_political_parties" not in content[:1000]:
        # we'll replace the import block
        old_import = "classify_topic, apply_outlet_cleaners\n)"
        new_import = "classify_topic, apply_outlet_cleaners,\n    normalize_political_parties\n)"
        content = content.replace(old_import, new_import)

    # Move normalize_str to top level
    old_normalize_block = """            # Remove title duplication from body using a smarter line-by-line check BEFORE collapsing newlines
            import re
            
            def normalize_str(s):
                from ingestion.tasks.text_cleaning import normalize_political_parties
                s = normalize_political_parties(s)
                return re.sub(r'[^a-zA-Z0-9\u0B80-\u0BFF]', '', s).lower()"""
                
    new_normalize_block = """            # Remove title duplication from body using a smarter line-by-line check BEFORE collapsing newlines"""

    if old_normalize_block in content:
        content = content.replace(old_normalize_block, new_normalize_block)
        
        # Add normalize_str to the top level (after imports)
        top_level_func = """
def normalize_str(s):
    s = normalize_political_parties(s)
    return re.sub(r'[^a-zA-Z0-9\u0B80-\u0BFF]', '', s).lower()
"""
        # Find a good place to insert it. e.g. before def process_feed or def fetch_feed_task
        if "def process_feed" in content:
            content = content.replace("def process_feed", top_level_func + "\n\ndef process_feed")
        elif "def fetch_feed_task" in content:
            content = content.replace("@shared_task", top_level_func + "\n\n@shared_task")

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
        
print("Cleanup complete.")
