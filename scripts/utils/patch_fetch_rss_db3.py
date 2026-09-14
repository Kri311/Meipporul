import os
import re

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"
rss_path = os.path.join(base_dir, "fetch_rss_standalone.py")

with open(rss_path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace the CSV writing block
csv_write_pattern = r'# Write new articles to CSV\n\s*if new_articles:.*?(?=print\(f"Written \{len\(new_articles\)\} new articles)'
new_db_block = """# Write new articles to PostgreSQL
    if new_articles:
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
                    extraction_quality=article_dict.get('extraction_quality', 0.0),
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

content = re.sub(csv_write_pattern, new_db_block, content, flags=re.DOTALL)

with open(rss_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Patched fetch_rss_standalone.py to write to DB!")
