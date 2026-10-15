import re

with open("src/backend/scripts/reprocess_articles.py", "r") as f:
    content = f.read()

# We want to replace the `articles_query.yield_per(100)` loop with a limit/offset loop.

new_loop = """
        batch_size = 20
        offset = 0
        batch_num = 1
        
        while True:
            batch = articles_query.order_by(Article.id).limit(batch_size).offset(offset).all()
            if not batch:
                break
                
            print(f"\\n==========================================")
            print(f"   STARTING BATCH {batch_num} (Articles {offset + 1} to {offset + len(batch)})")
            print(f"==========================================")
            
            for article in batch:
                if article.guid in processed_guids:
                    skipped_count += 1
                    continue
                    
                print(f"Processing ID {article.id} | URL: {article.canonical_url}")
"""

# Replace `for article in articles_query.yield_per(100):` and everything before it that manages counters
# Wait, the counters are initialized before the loop.
# Let's target the for loop.

replacement_logic = """
        processed_count = 0
        skipped_count = 0
        failed_count = 0
        
        batch_size = 20
        offset = 0
        batch_num = 1
        
        while True:
            batch = articles_query.order_by(Article.id).limit(batch_size).offset(offset).all()
            if not batch:
                break
                
            print(f"\\n==========================================")
            print(f"   STARTING BATCH {batch_num} (Articles {offset + 1} to {offset + len(batch)})")
            print(f"==========================================")
            
            for article in batch:
"""

content = re.sub(r'\s*processed_count = 0\s*skipped_count = 0\s*failed_count = 0\s*for article in articles_query\.yield_per\(100\):', replacement_logic, content)

# Also need to increment offset and batch_num at the end of the `while` loop.
# The `time.sleep(0.5)` is at the end of the `for article in batch:` loop.
# After the `for` loop, we increment.

content = content.replace("time.sleep(0.5) # Gentile rate limit", "time.sleep(0.5) # Gentle rate limit")

# We will inject the increment right before the `print(f"Finished! Processed:...")` which is outside the loop.
# But wait! If we do a simple replace, we have to respect the indent levels.

