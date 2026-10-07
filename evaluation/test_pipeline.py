import os
import sys
import time
import logging


import os; project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..")); sys.path.insert(0, os.path.join(project_root, "src"))

from backend.models.database import SessionLocal, Article, Outlet, RssFeed, init_db
from backend.ingestion.tasks.fetch_feed import process_single_feed
from backend.ingestion.tasks.embeddings import generate_embeddings_batch

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def run_test():
    logger.info("Connecting to database...")
    
    # Ensure DB tables exist
    init_db()
    
    db = SessionLocal()
    
    # 1. Sync outlets if not present (simulate worker startup)
    from backend.ingestion.main import load_sources_to_db
    load_sources_to_db()
    
    outlets = db.query(Outlet).count()
    feeds = db.query(RssFeed).count()
    logger.info(f"DB populated with {outlets} outlets and {feeds} feeds.")
    
    if feeds == 0:
        logger.error("No feeds found. Exiting test.")
        return

    # 2. Test RSS Fetching
    # Let's pick a reliable fast feed like BBC Tamil or The Hindu
    test_feed = db.query(RssFeed).filter(RssFeed.feed_url.like('%thehindu%')).first()
    if not test_feed:
        test_feed = db.query(RssFeed).first()
        
    logger.info(f"\n--- Testing RSS Fetching ---")
    logger.info(f"Target Feed: {test_feed.feed_url}")
    
    articles_before = db.query(Article).count()
    
    # Call celery task directly passing None for self
    try:
        fetch_result = process_single_feed(test_feed.id)
    except Exception as e:
        logger.error(f"Fetch failed: {e}")
        fetch_result = None
    articles_after = db.query(Article).count()
    
    new_articles = articles_after - articles_before
    logger.info(f"Fetch function returned: {fetch_result}")
    logger.info(f"Database now has {new_articles} new articles from this run.")
    
    # 3. Test Embedding generation
    logger.info(f"\n--- Testing Embedding Generation ---")
    eligible = db.query(Article).filter(Article.processing_status == 'eligible').count()
    logger.info(f"Found {eligible} articles eligible for embeddings.")
    
    if eligible > 0:
        logger.info("Triggering embedding generation batch...")
        start_time = time.time()
        try:
            emb_result = generate_embeddings_batch()
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            emb_result = None
        elapsed = time.time() - start_time
        
        logger.info(f"Embedding function returned: {emb_result} (took {elapsed:.2f}s)")
        
        embedded = db.query(Article).filter(Article.processing_status == 'embedded').count()
        logger.info(f"Total articles successfully embedded in DB: {embedded}")
        
        # Verify vector dimensions
        sample = db.query(Article).filter(Article.processing_status == 'embedded').first()
        if sample and sample.embedding is not None:
            logger.info(f"Sample embedding verified (dimensions: {len(sample.embedding)})")
    
    db.close()
    logger.info("\n PIPELINE TEST COMPLETE")

if __name__ == "__main__":
    run_test()
