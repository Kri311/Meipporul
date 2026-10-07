import re
with open("src/backend/api.py", "r") as f:
    api_code = f.read()

replacement = """        for a in arts:
            if a.image_url and not image_url:
                image_url = a.image_url
            if a.clean_text and len(summary_text) < 200:
                txt = a.clean_text
                if txt.startswith('{'):
                    import json
                    try:
                        parsed = json.loads(txt)
                        txt = " ".join(str(v) for v in parsed.values())
                    except:
                        txt = txt.replace('{', '').replace('}', '').replace('"', '')
                if len(txt) > 250:
                    summary_text = txt[:250].rsplit(' ', 1)[0] + "..."
                else:
                    summary_text = txt"""

api_code = re.sub(r'        for a in arts:\n            if a.image_url and not image_url:\n                image_url = a.image_url\n            if a.clean_text and len\(summary_text\) < 200:\n                summary_text = a.clean_text\[:200\] \+ "\.\.\."', replacement, api_code, flags=re.DOTALL)

with open("src/backend/api.py", "w") as f:
    f.write(api_code)
