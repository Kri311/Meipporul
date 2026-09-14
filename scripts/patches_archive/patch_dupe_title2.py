import os
import re

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"
files_to_patch = [
    os.path.join(base_dir, "fetch_rss_standalone.py"),
    os.path.join(base_dir, "ingestion", "tasks", "fetch_feed.py")
]

for path in files_to_patch:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    old_cond = "if norm_first and (norm_first in norm_title or norm_title in norm_first):"
    new_cond = "if norm_first and (norm_first in norm_title or norm_title in norm_first or (len(norm_first) >= 15 and norm_first[:15] == norm_title[:15])):"
    
    content = content.replace(old_cond, new_cond)
        
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

print("Patch 2 applied.")
