import re

with open('src/backend/ingestion/tasks/text_cleaning.py', 'r') as f:
    content = f.read()

# Add new junk patterns to INLINE_JUNK
new_junk = """
        r"(?i)From live updates to exclusive reports to in-depth explainers.*",
        r"(?i)Disclaimer: Comments reflect.*",
        r"(?i)Please keep discussions respectful and constructive.*",
        r"(?i)Abusive, defamatory, or illegal comments will be removed.*",
        r"(?i)may disable any comment at its discretion.*",
        r"(?i)By posting, you agree to our Terms of Use and Privacy Policy.*",
        r"(?i)Comments reflect users views, not s.*",
"""

content = content.replace("INLINE_JUNK = [", "INLINE_JUNK = [" + new_junk)

with open('src/backend/ingestion/tasks/text_cleaning.py', 'w') as f:
    f.write(content)
