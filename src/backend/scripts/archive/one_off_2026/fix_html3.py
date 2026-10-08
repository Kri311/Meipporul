with open('src/backend/ingestion/tasks/text_cleaning.py', 'r') as f:
    lines = f.readlines()

out_lines = []
skip = False
for line in lines:
    if line.startswith('def clean_html'):
        skip = True
        out_lines.append('import html\n')
        out_lines.append('def clean_html(raw_html):\n')
        out_lines.append('    if not raw_html: return ""\n')
        out_lines.append('    raw_html = html.unescape(str(raw_html))\n')
        out_lines.append('    if "<" not in raw_html or ">" not in raw_html:\n')
        out_lines.append('        text = raw_html.strip()\n')
        out_lines.append('    else:\n')
        out_lines.append('        soup = BeautifulSoup(raw_html, "html.parser")\n')
        out_lines.append('        text = soup.get_text(separator="\\n").strip()\n')
        out_lines.append('    return re.sub(r"^(?:[A-Za-z\\s]{3,20}|[\\u0B80-\\u0BFF\\s]{3,20})\\s*(?:\\||\\:\\-|\\:)\\s*","",text).strip()\n')
    elif skip and line.startswith('JUNK_PATTERNS'):
        skip = False
        out_lines.append(line)
    elif not skip:
        if line.startswith('import html'):
            continue
        out_lines.append(line)

with open('src/backend/ingestion/tasks/text_cleaning.py', 'w') as f:
    f.writelines(out_lines)
