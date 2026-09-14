import os
import re

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"
path = os.path.join(base_dir, "ingestion", "tasks", "fetch_feed.py")

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

if "def normalize_str" not in content:
    top_level_func = """
def normalize_str(s):
    s = normalize_political_parties(s)
    return re.sub(r'[^a-zA-Z0-9\u0B80-\u0BFF]', '', s).lower()
"""
    content = content.replace("@celery_app.task", top_level_func + "\n@celery_app.task")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Fixed fetch_feed.py")
else:
    print("normalize_str already exists")
