import re

def update_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # The block in fetch_rss_standalone and fetch_feed is:
    # t_clean = re.sub(r"\s+", " ", ...).strip()
    # c_clean = re.sub(r"\s+", " ", final_text).strip() if final_text else ""
    # import json
    # t_clean = t_clean.replace('"', "'")
    # c_clean = c_clean.replace('"', "'")
    # formatted_clean_text = json.dumps({"title": t_clean, "content": c_clean}, ensure_ascii=False, separators=(',', ':'))

    replacement = """
            t_clean = t_clean.replace('"', "'")
            c_clean = c_clean.replace('"', "'")
            formatted_clean_text = json.dumps({t_clean: c_clean}, ensure_ascii=False, separators=(',', ':'))
"""

    content = re.sub(
        r'\s*t_clean = t_clean\.replace\(\'"\', "\'"\)\s*c_clean = c_clean\.replace\(\'"\', "\'"\)\s*formatted_clean_text = json\.dumps\(\{"title": t_clean, "content": c_clean\}, ensure_ascii=False, separators=\(\',\', \':\'\)\)',
        lambda m: replacement,
        content
    )

    with open(filepath, 'w') as f:
        f.write(content)

update_file('src/backend/scripts/fetch_rss_standalone.py')
update_file('src/backend/ingestion/tasks/fetch_feed.py')
