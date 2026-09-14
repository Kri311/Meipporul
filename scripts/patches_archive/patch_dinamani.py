import os
import re

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"
tc_path = os.path.join(base_dir, "ingestion", "tasks", "text_cleaning.py")

with open(tc_path, "r", encoding="utf-8") as f:
    tc_content = f.read()

old_dinamani = """def clean_dinamani(title, text):
    text = re.sub(r"(?i)[a-z\\s\\.,\\?!]+$", "", text).strip()
    text = re.sub(r"(?i)-picture:\\d+/?", "", text)
    text = re.sub(r"(?i).*கோப்புப்\\s*படம்.*", "", text)
    return title, text"""

new_dinamani = """def clean_dinamani(title, text):
    match = re.search(r'([\\u0B80-\\u0BFF][\\.\\?!]?\\s*)[^\\u0B80-\\u0BFF]*$', text)
    if match:
        non_tamil_part = text[match.end(1):]
        if re.search(r'[a-zA-Z]{2,}', non_tamil_part):
            text = text[:match.end(1)].strip()
            
    text = re.sub(r"(?i)-picture:\\d+/?", "", text)
    text = re.sub(r"(?i).*கோப்புப்\\s*படம்.*", "", text)
    return title, text"""

tc_content = tc_content.replace(old_dinamani, new_dinamani)

with open(tc_path, "w", encoding="utf-8") as f:
    f.write(tc_content)

print("Updated clean_dinamani")
