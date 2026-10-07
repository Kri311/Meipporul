import os
import yaml
from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init

from backend.models.database import SessionLocal, Outlet, RssFeed, init_db, engine

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Initialize Celery app
celery_app = Celery(
    "veritas_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["ingestion.tasks.fetch_feed", "ingestion.tasks.embeddings"] # Register our tasks module
)

# Celery Configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600, # 1 hour max task execution time
    broker_connection_retry_on_startup=True,
)

# Set up periodic tasks (Celery Beat)
celery_app.conf.beat_schedule = {
    "fetch-all-rss-feeds-every-5-mins": {
    "task": "ingestion.tasks.fetch_feed.dispatch_all_feeds",
    "schedule": crontab(minute="*/5"),
    },
    "generate-embeddings-every-2-mins": {
        "task": "ingestion.tasks.embeddings.generate_embeddings_batch",
        "schedule": crontab(minute="*/2"),
    },
}

def load_sources_to_db():
    """Reads sources.yaml and ensures the outlets and feeds exist in the database."""
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "sources.yaml")
    
    if not os.path.exists(config_path):
        print(f"Warning: Configuration file not found at {config_path}")
        return
        
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    db = SessionLocal()
    try:
        sources = config.get("sources", [])
        for src in sources:
            # Upsert Outlet
            outlet = db.query(Outlet).filter(Outlet.slug == src["slug"]).first()
            if not outlet:
                outlet = Outlet(
                    slug=src["slug"],
                    name=src["name"],
                    language_set=src["language"],
                    homepage_url=src["homepage"],
                    orientation_bucket=src["orientation_bucket"],
                    orientation_confidence=src["orientation_confidence"],
                    active=src.get("enabled", True)
                )
                db.add(outlet)
                db.flush() # Flush to get outlet.id for the rss feeds
            else:
                # Update properties in case they changed in YAML
                outlet.orientation_bucket = src["orientation_bucket"]
                outlet.orientation_confidence = src["orientation_confidence"]
            
            # Upsert RSS Feeds for this outlet
            for feed_url in src.get("rss", []):
                feed = db.query(RssFeed).filter(RssFeed.feed_url == feed_url).first()
                if not feed:
                    feed = RssFeed(
                        outlet_id=outlet.id,
                        feed_url=feed_url,
                        category=src.get("category", "general"),
                        enabled=src.get("enabled", True)
                    )
                    db.add(feed)
        db.commit()
        print(f"Successfully synced {len(sources)} sources into the Postgres database.")
    except Exception as e:
        db.rollback()
        print(f"Error loading sources into DB: {e}")
    finally:
        db.close()

# Initialize DB and Source configuration on worker boot
@celery_app.on_after_configure.connect
def setup_initialization(sender, **kwargs):
    print("Initializing Database Schema...")
    init_db()
    print("Syncing sources from backend.config...")
    load_sources_to_db()

@worker_process_init.connect
def init_worker(**kwargs):
    """Dispose SQLAlchemy engine on fork to prevent TCP connection sharing bugs."""
    engine.dispose()
