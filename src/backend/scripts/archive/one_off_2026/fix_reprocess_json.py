import re

with open('src/backend/scripts/reprocess_articles.py', 'r') as f:
    content = f.read()

# Replace the block that creates formatted_clean_text
# Old block:
# t_clean_json = t_clean.replace('"', "'")
# c_clean_json = cleaned_body.replace('"', "'")
# formatted_clean_text = json.dumps({"title": t_clean_json, "content": c_clean_json}, ensure_ascii=False, separators=(',', ':'))

replacement = """
                t_clean_json = re.sub(r"\\s+", " ", t_clean).strip().replace('"', "'")
                c_clean_json = re.sub(r"\\s+", " ", cleaned_body).strip().replace('"', "'")
                formatted_clean_text = json.dumps({t_clean_json: c_clean_json}, ensure_ascii=False, separators=(',', ':'))
"""

content = re.sub(
    r'\s*t_clean_json = t_clean\.replace\(\'"\', "\'"\)\s*c_clean_json = cleaned_body\.replace\(\'"\', "\'"\)\s*formatted_clean_text = json\.dumps\(\{"title": t_clean_json, "content": c_clean_json\}, ensure_ascii=False, separators=\(\',\', \':\'\)\)',
    lambda m: replacement,
    content
)

with open('src/backend/scripts/reprocess_articles.py', 'w') as f:
    f.write(content)
