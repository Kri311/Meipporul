with open("fetch_rss_standalone.py", "r") as f:
    text = f.read()
    
# Find the literal newline inside the f-string
import re
text = re.sub(r'print\(f"\nSaving', r'print(f"\\nSaving', text)

with open("fetch_rss_standalone.py", "w") as f:
    f.write(text)
