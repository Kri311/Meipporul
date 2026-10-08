import re
with open('src/backend/ingestion/tasks/text_cleaning.py', 'r') as f:
    content = f.read()

replacement = """import html
def clean_html(raw_html):
    if not raw_html: return ""
    raw_html = html.unescape(str(raw_html))
    if "<" not in raw_html or ">" not in raw_html:
        text = raw_html.strip()
    else:
        soup = BeautifulSoup(raw_html, "html.parser")
        text = soup.get_text(separator="\\n").strip()
    return re.sub(r"^(?:[A-Za-z\\s]{3,20}|[\\u0B80-\\u0BFF\\s]{3,20})\\s*(?:\\||\\:\\-|\\:)\\s*","",text).strip()
"""

# Find where `import html` or `def clean_html` starts, to `def deep_clean_text`
content = re.sub(r'import html\ndef clean_html.*?def deep_clean_text', replacement + '\n\n# ─── Paywall / Subscription / Navigation Junk Patterns ───\n' + re.search(r'(JUNK_PATTERNS =.*?def deep_clean_text)', content, re.DOTALL).group(1), content, flags=re.DOTALL)

with open('src/backend/ingestion/tasks/text_cleaning.py', 'w') as f:
    f.write(content)
