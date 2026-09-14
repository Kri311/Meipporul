import os
import re

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"
tc_path = os.path.join(base_dir, "ingestion", "tasks", "text_cleaning.py")
rss_path = os.path.join(base_dir, "fetch_rss_standalone.py")
feed_path = os.path.join(base_dir, "ingestion", "tasks", "fetch_feed.py")

with open(tc_path, "r", encoding="utf-8") as f:
    tc_content = f.read()

# Make sure deep_clean_text doesn't discard location before callers can read it
tc_content = tc_content.replace("    _, result = extract_dateline_location(result.strip())\n", "")

with open(tc_path, "w", encoding="utf-8") as f:
    f.write(tc_content)

print("Updated text_cleaning.py in patch_location2")
