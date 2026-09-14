import os
import re

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"
tc_path = os.path.join(base_dir, "ingestion", "tasks", "text_cleaning.py")

with open(tc_path, "r", encoding="utf-8") as f:
    tc_content = f.read()

# Just use regex sub to replace the exact pattern line
tc_content = re.sub(
    r"pattern = r'\^\\s\*\(\?:\\[\(\?P<loc1>\[\^\\\]\]\+\)\\]\|\(\?P<loc2>\[a-zA-Z\\u0B80-\\u0BFF\\s\]\{2,30\}\)\)\\s\*\(\?:\\\(\[\^\\\)\]\+\\\)\)\?\\s\*\(\?::-\|\\:\|\\\|\|\\-\|\\u2013\|\\u2014\)\\s\*'",
    r"pattern = r'^\\s*(?:\\[(?P<loc1>[^\\]]+)\\]|(?P<loc2>[a-zA-Z\\u0B80-\\u0BFF\\s\\/,]{2,50}))\\s*(?:\\([^\\)]+\\))?\\s*(?::-|\\:|\\||\\-|\\u2013|\\u2014)\\s*'",
    tc_content
)

with open(tc_path, "w", encoding="utf-8") as f:
    f.write(tc_content)

print("Updated text_cleaning.py")
