import time
import os
import csv
import subprocess
from collections import Counter

csv_path = 'data/raw_processed.csv'
print("Waiting for fetch to finish...")

# Wait until fetch_rss_standalone.py is no longer running
while True:
    time.sleep(10)
    # Check if process is still running
    if subprocess.run(['pgrep', '-f', 'fetch_rss_standalone.py'], capture_output=True).returncode != 0:
        break

if not os.path.exists(csv_path):
    print("Error: CSV file not found!")
    exit(1)

print("\n--- ANALYSIS & VERIFICATION RESULTS ---\n")

outlets = Counter()
topics = Counter()
news18_tam_titles = []
news18_eng_titles = []
tamil_count = 0
english_count = 0

with open(csv_path, 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        slug = row.get('outlet_slug', '')
        topic = row.get('topic', 'N/A')
        lang = row.get('language', '')
        
        outlets[slug] += 1
        topics[topic] += 1
        
        if lang == 'ta':
            tamil_count += 1
        elif lang == 'en':
            english_count += 1
            
        if slug == 'news18_tamil_nadu' and len(news18_tam_titles) < 3:
            news18_tam_titles.append(f"[{topic}] {row['title']}")
            
        if slug == 'news18_india' and len(news18_eng_titles) < 3:
            news18_eng_titles.append(f"[{topic}] {row['title']}")

print(f"Total Articles Collected: {sum(outlets.values())}")
print(f"Total English: {english_count} | Total Tamil: {tamil_count}\n")

print("--- Outlet Distribution ---")
for o, c in outlets.most_common():
    print(f"  {o}: {c}")

print("\n--- Topic Distribution ---")
for t, c in topics.most_common():
    print(f"  {t}: {c}")

print("\n--- News18 Tamil Sample (First 3) ---")
for t in news18_tam_titles:
    print(f"  - {t}")

print("\n--- News18 English Sample (First 3) ---")
for t in news18_eng_titles:
    print(f"  - {t}")

