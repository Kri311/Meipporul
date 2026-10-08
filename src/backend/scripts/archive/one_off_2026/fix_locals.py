import re

def update_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # In fetch_rss_standalone.py, the variable is clean_title. In fetch_feed.py, it's title_clean.
    # We will just replace the whole line with the correct one.
    if 'fetch_rss_standalone' in filepath:
        content = content.replace("clean_title if 'clean_title' in locals() else title_clean", "clean_title")
    else:
        content = content.replace("clean_title if 'clean_title' in locals() else title_clean", "title_clean")

    with open(filepath, 'w') as f:
        f.write(content)

update_file('src/backend/scripts/fetch_rss_standalone.py')
update_file('src/backend/ingestion/tasks/fetch_feed.py')
