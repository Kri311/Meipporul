import re

def update_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # We replace json.dumps({t_clean: c_clean}) with json.dumps({"title": t_clean, "content": c_clean})
    # Also replace " with ' in t_clean and c_clean just to be absolutely safe for their downstream parsers.
    
    replacement = """
            t_clean = t_clean.replace('"', "'")
            c_clean = c_clean.replace('"', "'")
            formatted_clean_text = json.dumps({"title": t_clean, "content": c_clean}, ensure_ascii=False, separators=(',', ':'))
"""
    
    content = re.sub(
        r'\s*formatted_clean_text = json\.dumps\(\{t_clean: c_clean\}[^\n]+',
        lambda m: replacement,
        content
    )

    with open(filepath, 'w') as f:
        f.write(content)

update_file('src/backend/scripts/fetch_rss_standalone.py')
update_file('src/backend/ingestion/tasks/fetch_feed.py')
