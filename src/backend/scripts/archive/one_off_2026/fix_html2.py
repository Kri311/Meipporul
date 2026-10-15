with open('src/backend/ingestion/tasks/text_cleaning.py', 'r') as f:
    content = f.read()

content = content.replace('text = soup.get_text(separator="\n").strip()', 'text = soup.get_text(separator="\\n").strip()')

with open('src/backend/ingestion/tasks/text_cleaning.py', 'w') as f:
    f.write(content)
