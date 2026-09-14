import os

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"
rss_path = os.path.join(base_dir, "fetch_rss_standalone.py")

with open(rss_path, "r", encoding="utf-8") as f:
    content = f.read()

# Instead of saving to CSV, save to PostgreSQL.
old_import = "import yaml\nfrom ingestion.tasks.text_cleaning"
new_import = "import yaml\nfrom ingestion.models.database import SessionLocal, Article, RssFeed, Outlet\nfrom ingestion.tasks.text_cleaning"
if "SessionLocal" not in content:
    content = content.replace(old_import, new_import)

# Find the spot where it writes to CSV
old_csv_block = """        if new_articles:
            print(f"\\nWritten {len(new_articles)} new articles to {CSV_PATH}")
            file_exists = os.path.isfile(CSV_PATH)
            with open(CSV_PATH, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=CSV_FIELDNAMES)
                if not file_exists:
                    writer.writeheader()
                for article in new_articles:
                    writer.writerow(article)"""

new_db_block = """        if new_articles:
            print(f"\\nSaving {len(new_articles)} new articles to PostgreSQL...")
            db = SessionLocal()
            try:
                for article_dict in new_articles:
                    outlet = db.query(Outlet).filter(Outlet.slug == article_dict['outlet_slug']).first()
                    if not outlet:
                        continue
                    
                    art = Article(
                        outlet_id=outlet.id,
                        guid=article_dict['guid'],
                        canonical_url=article_dict['canonical_url'],
                        original_url=article_dict['canonical_url'],
                        title=article_dict['title'],
                        description=article_dict['description'],
                        author=article_dict['author'],
                        published_at=datetime.fromisoformat(article_dict['published_at']) if article_dict['published_at'] else None,
                        language=article_dict['language'],
                        article_length=article_dict['article_length'],
                        data_fetch_via=article_dict['data_fetch_via'],
                        raw_text=article_dict['raw_text'],
                        clean_text=article_dict['clean_text'],
                        content_hash=article_dict['content_hash'],
                        extraction_method=article_dict['extraction_method'],
                        extraction_quality=article_dict['extraction_quality'],
                        processing_status="extracted"
                    )
                    db.add(art)
                db.commit()
            except Exception as e:
                db.rollback()
                print(f"Error saving to DB: {e}")
            finally:
                db.close()
"""

if "Saving" not in content and old_csv_block in content:
    content = content.replace(old_csv_block, new_db_block)
    
# Remove CSV cleanup at start
old_cleanup = """    if args.fresh:
        if os.path.exists(CSV_PATH):
            os.remove(CSV_PATH)
            print(f"Deleted existing {CSV_PATH}")"""

new_cleanup = """    if args.fresh:
        print("Note: --fresh now just fetches everything into Postgres. To truly start fresh, you'd need to clear the DB.")"""

content = content.replace(old_cleanup, new_cleanup)

with open(rss_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Patched fetch_rss_standalone.py to use PostgreSQL.")
