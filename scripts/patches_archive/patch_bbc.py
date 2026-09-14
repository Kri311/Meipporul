import os
import re

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"
tc_path = os.path.join(base_dir, "ingestion", "tasks", "text_cleaning.py")

with open(tc_path, "r", encoding="utf-8") as f:
    tc_content = f.read()

old_bbc = """def clean_bbc_tamil(title, text):
    text = re.sub(r"- இது, க்காக கலெக்டிவ் நியூஸ்ரூம் வெளியீடு[\\s\\S]*", "", text)
    return title, text"""

new_bbc = """def clean_bbc_tamil(title, text):
    # Remove footer
    text = re.sub(r"- இது, க்காக கலெக்டிவ் நியூஸ்ரூம் வெளியீடு[\\s\\S]*", "", text)
    # Remove author header block
    text = re.sub(r"(?im)^-?\\s*(எழுதியவர்,|பதவி,|பிரசுரிக்கப்பட்டது|வாசிக்கும் நேரம்:).*?$", "", text)
    return title, text"""

tc_content = tc_content.replace(old_bbc, new_bbc)

with open(tc_path, "w", encoding="utf-8") as f:
    f.write(tc_content)
    
print("Updated clean_bbc_tamil")
