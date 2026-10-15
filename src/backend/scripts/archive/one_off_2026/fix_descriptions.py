import re

def update_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # We need to find where c_clean is defined and prepend description if necessary.
    # In fetch_rss_standalone.py: c_clean = re.sub(r"\s+", " ", final_text).strip() if final_text else ""
    # We will inject the description logic right before it.
    
    injection = """
            d_clean = clean_html(getattr(entry, "description", ""))
            d_clean_norm = normalize_str(d_clean)
            c_clean_norm = normalize_str(final_text)
            
            if d_clean and len(d_clean) > 20 and d_clean_norm not in c_clean_norm:
                # Prepend the description to the final text
                final_text = f"{d_clean}\\n\\n{final_text}"
            
            t_clean = re.sub(r"\\s+", " ", clean_title if 'clean_title' in locals() else title_clean).strip()
            c_clean = re.sub(r"\\s+", " ", final_text).strip() if final_text else ""
    """
    
    # We replace the t_clean and c_clean lines with our injection
    content = re.sub(
        r'\s*t_clean = re\.sub\(r"\\s\+", " ", [^\n]+\n\s*c_clean = re\.sub\(r"\\s\+", " ", final_text\)\.strip\(\) if final_text else ""',
        lambda m: injection,
        content
    )

    with open(filepath, 'w') as f:
        f.write(content)

update_file('src/backend/scripts/fetch_rss_standalone.py')
update_file('src/backend/ingestion/tasks/fetch_feed.py')
