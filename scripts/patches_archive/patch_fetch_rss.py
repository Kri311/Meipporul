import re
import os

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"
files_to_patch = [
    os.path.join(base_dir, "fetch_rss_standalone.py"),
    os.path.join(base_dir, "ingestion", "tasks", "fetch_feed.py")
]

old_normalize_str = """            def normalize_str(s):
                return re.sub(r'[^a-zA-Z0-9\u0B80-\u0BFF]', '', s).lower()"""

new_normalize_str = """            def normalize_str(s):
                from ingestion.tasks.text_cleaning import normalize_political_parties
                s = normalize_political_parties(s)
                return re.sub(r'[^a-zA-Z0-9\u0B80-\u0BFF]', '', s).lower()"""

for path in files_to_patch:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    if old_normalize_str in content:
        content = content.replace(old_normalize_str, new_normalize_str)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Patched {path}")
    else:
        print(f"Could not find old_normalize_str in {path}")
