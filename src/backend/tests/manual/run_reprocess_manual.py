import sys
import os

sys.path.insert(0, os.path.join(os.path.abspath("."), "src"))
import backend.scripts.reprocess_articles as ra
# Temporarily mock the query to limit to 1
original_query = ra.SessionLocal().query
ra.run_reprocessing()
