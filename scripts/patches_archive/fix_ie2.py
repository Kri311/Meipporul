import os
import re

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"
tc_path = os.path.join(base_dir, "ingestion", "tasks", "text_cleaning.py")

with open(tc_path, "r", encoding="utf-8") as f:
    tc_content = f.read()

bad_block = """    text = re.sub(r"(?i)IE Online Media Services PVT LTD",
    r"(?i)^PHOTO\s*:.*",
    r"- இது, க்காக கலெக்டிவ் நியூஸ்ரூம் வெளியீடு",
    r"மேலும் அறிக",
    r"குறுங்காணொளிகள்",
    r"குறுங்காணொளிகள் முடிவு", "", text)"""
    
good_block = """    text = re.sub(r"(?i)IE Online Media Services PVT LTD", "", text)"""

tc_content = tc_content.replace(bad_block, good_block)

# Clean up JUNK_PATTERNS duplicates
import re
tc_content = re.sub(r'(r"\(\?i\).*Pvt Ltd\\.\?\$",\n\s*r"\(\?i\)The Indian Express.*",\n\s*)+', r'r"(?i).*Pvt Ltd\\.?$",\n    r"(?i)The Indian Express.*",\n    ', tc_content)

with open(tc_path, "w", encoding="utf-8") as f:
    f.write(tc_content)

print("Fixed clean_indian_express and JUNK_PATTERNS duplicates")
