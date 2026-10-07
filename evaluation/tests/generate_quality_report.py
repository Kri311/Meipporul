import csv
import os
from collections import Counter
from statistics import median
from datetime import datetime

def generate_report():
    csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw_processed.csv')
    
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
        return
        
    total_articles = 0
    sources = Counter()
    length_cats = Counter()
    languages = Counter()
    
    word_counts = []
    
    missing_titles = 0
    missing_content = 0
    missing_dates = 0
    
    urls = []
    titles = []
    
    dates_day = Counter()
    dates_month = Counter()

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_articles += 1
            sources[row.get('outlet_slug', 'Unknown')] += 1
            length_cats[row.get('article_length', 'Unknown')] += 1
            languages[row.get('language', 'Unknown')] += 1
            
            # Text
            text = row.get('clean_text', '')
            if not text.strip():
                missing_content += 1
            else:
                word_counts.append(len(text.split()))
                
            # Title
            title = row.get('title', '')
            if not title.strip():
                missing_titles += 1
            titles.append(title.strip())
            
            # URL
            url = row.get('canonical_url', '')
            urls.append(url)
            
            # Date
            date_str = row.get('published_at', '')
            if not date_str.strip():
                missing_dates += 1
            else:
                try:
                    # Typical datetime string from db/csv looks like "2026-09-06 04:03:50" or similar
                    dt = datetime.fromisoformat(date_str.split('.')[0])
                    dates_day[dt.strftime("%Y-%m-%d")] += 1
                    dates_month[dt.strftime("%Y-%m")] += 1
                except Exception:
                    pass

    dup_urls = len(urls) - len(set(urls))
    dup_titles = len(titles) - len(set(titles))
    
    avg_wc = sum(word_counts) / len(word_counts) if word_counts else 0
    med_wc = median(word_counts) if word_counts else 0
    min_wc = min(word_counts) if word_counts else 0
    max_wc = max(word_counts) if word_counts else 0
    
    report = f"""
=========================================================
                DATA QUALITY REPORT
=========================================================
Total Articles       : {total_articles}

--- QUALITY ISSUES ---
Missing Titles       : {missing_titles}
Missing Content      : {missing_content}
Missing Dates        : {missing_dates}
Duplicate URLs       : {dup_urls}
Duplicate Titles     : {dup_titles}

--- WORD COUNT METRICS ---
Average Word Count   : {avg_wc:.2f}
Median Word Count    : {med_wc}
Min Word Count       : {min_wc}
Max Word Count       : {max_wc}

--- ARTICLE LENGTH CATEGORIES ---
"""
    for k, v in length_cats.most_common():
        report += f"  {k:<10}: {v}\n"
        
    report += "\n--- LANGUAGE DISTRIBUTION ---\n"
    for k, v in languages.most_common():
        report += f"  {k:<10}: {v}\n"
        
    report += "\n--- ARTICLES BY SOURCE ---\n"
    for k, v in sources.most_common():
        report += f"  {k:<22}: {v}\n"
        
    report += "\n--- ARTICLES PER MONTH ---\n"
    if not dates_month:
        report += "  No valid dates parsed.\n"
    for k, v in sorted(dates_month.items()):
        report += f"  {k:<10}: {v}\n"

    report += "\n--- ARTICLES PER DAY (Top 5) ---\n"
    for k, v in dates_day.most_common(5):
        report += f"  {k:<10}: {v}\n"
        
    print(report)

    # Export metrics to CSV history
    history_csv = os.path.join(os.path.dirname(__file__), '..', 'data', 'quality_metrics_history.csv')
    file_exists = os.path.exists(history_csv)
    
    with open(history_csv, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                'timestamp', 'total_articles', 'missing_titles', 'missing_content', 
                'missing_dates', 'duplicate_urls', 'duplicate_titles', 
                'avg_word_count', 'median_word_count', 'min_word_count', 'max_word_count',
                'short_articles', 'medium_articles', 'long_articles',
                'english_articles', 'tamil_articles'
            ])
            
        writer.writerow([
            datetime.now().isoformat(), total_articles, missing_titles, missing_content,
            missing_dates, dup_urls, dup_titles, 
            round(avg_wc, 2), med_wc, min_wc, max_wc,
            length_cats.get('short', 0), length_cats.get('medium', 0), length_cats.get('long', 0),
            languages.get('en', 0), languages.get('ta', 0)
        ])
    print(f"\n[INFO] Quality metrics appended to data/quality_metrics_history.csv")

if __name__ == "__main__":
    generate_report()
