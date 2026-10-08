import re
with open('src/backend/scripts/reprocess_articles.py', 'r') as f:
    content = f.read()

content = content.replace("from backend.ingestion.tasks.text_cleaning import deep_clean_text, clean_html, normalize_str", "from backend.ingestion.tasks.text_cleaning import deep_clean_text, clean_html")

injection = """
def normalize_political_parties(s):
    if not s: return ""
    PARTY_MAP = {
        r'(?i)\\bதி\\.?மு\\.?க\\b': 'DMK',
        r'(?i)\\bஅ\\.?தி\\.?மு\\.?க\\b': 'AIADMK',
        r'(?i)\\bபா\\.?ஜ\\.?க\\b': 'BJP',
        r'(?i)\\bகாங்கிரஸ்\\b': 'Congress',
    }
    for k, v in PARTY_MAP.items():
        s = re.sub(k, v, s)
    return s

def normalize_str(s):
    s = normalize_political_parties(s)
    return re.sub(r'[^a-zA-Z0-9஀-௿]', '', s).lower()

"""
content = content.replace("import trafilatura", "import trafilatura\nimport re" + injection)

# Revert the limit(1) from earlier testing
content = content.replace("articles_query.limit(1).yield_per(100)", "articles_query.yield_per(100)")

with open('src/backend/scripts/reprocess_articles.py', 'w') as f:
    f.write(content)
