import os
import re

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"
files_to_patch = [
    os.path.join(base_dir, "fetch_rss_standalone.py"),
    os.path.join(base_dir, "ingestion", "tasks", "fetch_feed.py")
]

old_format = """            # Remove any internal newlines in the body so it's a single continuous block
            final_text = re.sub(r'\\n+', ' ', final_text).strip()
            
            # Remove title duplication from body
            final_text = re.sub(r'^[\\s\\-\\|:]+', '', final_text)
            if final_text.lower().startswith(clean_title.lower()):
                final_text = final_text[len(clean_title):].strip()
            final_text = re.sub(r'^[\\s\\-\\|:]+', '', final_text)
            
            # STANDARD: Ensure content explicitly begins with the Title followed by the Body
            final_text = f"{clean_title}\\n\\n{final_text}"
"""

new_format = """            # Remove title duplication from body using a smarter line-by-line check BEFORE collapsing newlines
            import re
            
            def normalize_str(s):
                return re.sub(r'[^a-zA-Z0-9\u0B80-\u0BFF]', '', s).lower()
                
            norm_title = normalize_str(clean_title)
            
            lines = final_text.split('\\n')
            while lines:
                first_line = re.sub(r'^[\\s\\-\\|:]+', '', lines[0]).strip()
                norm_first = normalize_str(first_line)
                
                # Check if first line is heavily overlapping with title
                if norm_first and (norm_first in norm_title or norm_title in norm_first):
                    lines.pop(0)
                else:
                    break
                    
            final_text = '\\n'.join(lines).strip()

            # Remove any internal newlines in the body so it's a single continuous block
            # Convert newlines (and any following whitespaces) into a single whitespace
            final_text = re.sub(r'\\n+\\s*', ' ', final_text).strip()
            
            # STANDARD: Ensure content explicitly begins with the Title followed by the Body
            # The user requested "newline follwed by a whitespace should be defined" in contents,
            # so we ensure the gap between title and body is exact.
            final_text = f"{clean_title}\\n\\n{final_text}"
"""

old_format_ff = """            # Remove any internal newlines in the body so it's a single continuous block
            final_text = re.sub(r'\\n+', ' ', final_text).strip()
            
            # Remove title duplication from body
            final_text = re.sub(r'^[\\s\\-\\|:]+', '', final_text)
            if final_text.lower().startswith(title_clean.lower()):
                final_text = final_text[len(title_clean):].strip()
            final_text = re.sub(r'^[\\s\\-\\|:]+', '', final_text)

            # STANDARD: Ensure content explicitly begins with the Title followed by the Body
            final_text = f"{title_clean}\\n\\n{final_text}"
"""

new_format_ff = """            # Remove title duplication from body using a smarter line-by-line check BEFORE collapsing newlines
            import re
            
            def normalize_str(s):
                return re.sub(r'[^a-zA-Z0-9\u0B80-\u0BFF]', '', s).lower()
                
            norm_title = normalize_str(title_clean)
            
            lines = final_text.split('\\n')
            while lines:
                first_line = re.sub(r'^[\\s\\-\\|:]+', '', lines[0]).strip()
                norm_first = normalize_str(first_line)
                
                # Check if first line is heavily overlapping with title
                if norm_first and (norm_first in norm_title or norm_title in norm_first):
                    lines.pop(0)
                else:
                    break
                    
            final_text = '\\n'.join(lines).strip()

            # Remove any internal newlines in the body so it's a single continuous block
            # Convert newlines (and any following whitespaces) into a single whitespace
            final_text = re.sub(r'\\n+\\s*', ' ', final_text).strip()

            # STANDARD: Ensure content explicitly begins with the Title followed by the Body
            final_text = f"{title_clean}\\n\\n{final_text}"
"""

for path in files_to_patch:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    if "clean_title" in old_format and "fetch_rss_standalone.py" in path:
        content = content.replace(old_format, new_format)
    elif "title_clean" in old_format_ff and "fetch_feed.py" in path:
        content = content.replace(old_format_ff, new_format_ff)
        
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

print("Patch applied.")
