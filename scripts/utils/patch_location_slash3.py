import os

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"
tc_path = os.path.join(base_dir, "ingestion", "tasks", "text_cleaning.py")

with open(tc_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "pattern = r'^\\s*(?:\\[(?P<loc1>[^\\]]+)\\]|(?P<loc2>[a-zA-Z\\u0B80-\\u0BFF\\s]{2,30}))\\s*(?:\\([^\\)]+\\))?\\s*(?::-|\\:|\\||\\-|\\u2013|\\u2014)\\s*'" in line:
        lines[i] = "    pattern = r'^\\s*(?:\\[(?P<loc1>[^\\]]+)\\]|(?P<loc2>[a-zA-Z\\u0B80-\\u0BFF\\s\\/,&]{2,50}))\\s*(?:\\([^\\)]+\\))?\\s*(?::-|\\:|\\||\\-|\\u2013|\\u2014)\\s*'\n"
        print("Line replaced!")

with open(tc_path, "w", encoding="utf-8") as f:
    f.writelines(lines)
