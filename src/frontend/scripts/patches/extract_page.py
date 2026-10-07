import json

with open('/home/owl/.gemini/antigravity/brain/4338ba78-2c95-4719-a5cc-a26ab7dc18f6/.system_generated/logs/transcript_full.jsonl', 'r') as f:
    for line in f:
        data = json.loads(line)
        if data.get('type') == 'GENERIC' and 'cat frontend/src/app/page.jsx 2>/dev/null || cat frontend/src/app/page.js' in data.get('content', ''):
            pass # wait, GENERIC for running task
        if data.get('type') == 'GENERIC' and 'The command exited with code 0' in data.get('content', ''):
            content = data['content']
            if 'fontWeight: 800,' in content and '{strings.latestStories}' in content:
                # We found the output! But wait, is it the full output?
                # The output is inside the content.
                # Let's save all GENERIC completed outputs that might be it.
                with open('extracted_page.txt', 'a') as out:
                    out.write(content + "\n====================\n")
