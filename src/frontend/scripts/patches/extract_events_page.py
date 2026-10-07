import json

with open('/home/owl/.gemini/antigravity/brain/4338ba78-2c95-4719-a5cc-a26ab7dc18f6/.system_generated/logs/transcript_full.jsonl', 'r') as f:
    for line in f:
        data = json.loads(line)
        if data.get('type') == 'GENERIC' and 'The command exited with code 0' in data.get('content', ''):
            content = data['content']
            if 'PerspectiveMatrix matrix={matrix}' in content and 'OrientationBar coverage={event.coverage}' in content:
                with open('extracted_events_page.txt', 'a') as out:
                    out.write(content + "\n====================\n")
