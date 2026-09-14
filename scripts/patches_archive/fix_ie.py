import os
base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"
tc_path = os.path.join(base_dir, "ingestion", "tasks", "text_cleaning.py")

with open(tc_path, "r", encoding="utf-8") as f:
    tc_content = f.read()

bad_block = """    text = re.sub(r"(?i)IE Online Media Services PVT LTD",
    r"(?i).*Pvt Ltd\\.?$",
    r"(?i)The Indian Express.*", "", text)"""
    
good_block = """    text = re.sub(r"(?i)IE Online Media Services PVT LTD", "", text)
    text = re.sub(r"(?i).*Pvt Ltd\\.?$", "", text)
    text = re.sub(r"(?i).*The Indian Express.*", "", text)"""

tc_content = tc_content.replace(bad_block, good_block)

with open(tc_path, "w", encoding="utf-8") as f:
    f.write(tc_content)

print("Fixed clean_indian_express")
