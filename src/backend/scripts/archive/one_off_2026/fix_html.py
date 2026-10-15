import re

filepath = 'src/backend/ingestion/tasks/text_cleaning.py'
with open(filepath, 'r') as f:
    content = f.read()

# We need to add html.unescape to clean_html
replacement = """import html
def clean_html(raw_html):
    \"\"\"Removes HTML tags and normalizes whitespace.\"\"\"
    if not raw_html:
        return ""
    raw_html = str(raw_html)
    # Always unescape HTML entities like &amp; or &quot;
    raw_html = html.unescape(raw_html)
    
    # If the input doesn't contain HTML markup, treat it as plain text.
    if "<" not in raw_html or ">" not in raw_html:
        text = raw_html.strip()
    else:
        soup = BeautifulSoup(raw_html, "html.parser")
        text = soup.get_text(separator="\\n").strip()"""

content = re.sub(r'def clean_html\(raw_html\):.*?text = soup\.get_text\(separator="\\n"\)\.strip\(\)', replacement, content, flags=re.DOTALL)

with open(filepath, 'w') as f:
    f.write(content)
