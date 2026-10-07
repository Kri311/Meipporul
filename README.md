# Veritas Lens

## Overview
Veritas Lens is a comprehensive text analytics and news aggregation pipeline that processes and clusters multilingual news articles. It focuses on scraping, ingesting, and analyzing news feeds (primarily Indian news sources) to provide consolidated events, determine political or editorial orientations (e.g., Left, Center, Right), and perform Named Entity Recognition (NER).

The system consists of a Python-based backend that orchestrates data ingestion, semantic embeddings, clustering, and API services, alongside a Next.js-based frontend for visualizing the aggregated events.

## Architecture

### Backend
* **Language & Framework:** Python, FastAPI (for REST API orchestration).
* **Database:** PostgreSQL 16 with `pgvector` extension for storing articles, embeddings, and clustering data.
* **Task Queue:** Celery with Redis broker for asynchronous background processing and cron-style RSS feed polling.
* **AI & NLP Models:**
  * **Embeddings:** `BAAI/bge-m3` via `sentence-transformers`
  * **NER (Named Entity Recognition):** Mistral (`mistralai/Mistral-Small-3.1-24B-Instruct-2503`)
  * **Clustering algorithm:** DBSCAN + Agglomerative Clustering
* **Data Processing Libraries:** `trafilatura` (article extraction), `feedparser` (RSS parsing), `torch`, `SQLAlchemy`.

### Frontend
* **Framework:** Next.js (version 16.3.1), React 19.
* **Package Manager:** Bun (or npm/yarn).

## Repository Structure

* `/src/backend`: Contains the Python backend application, API endpoints, background tasks, and machine learning pipelines.
* `/src/frontend`: Next.js web interface.
* `/src/backend/scripts`: Utility scripts for database resetting, isolated testing, and shell scripts for local infrastructure setup.
* `/evaluation`: Scripts and generated metrics/CSV files for pipeline testing and NER accuracy assessment.
* `/retrieved_data`: Directory for storing raw scraped articles and cache.

## Configuration

### Environment Variables
Environment variables are managed via a `.env` file at the root of the project. Copy the provided `.env.example` to `.env` and configure accordingly.

```ini
POSTGRES_USER=veritas_admin
POSTGRES_PASSWORD=veritas_secret_password
POSTGRES_DB=veritas_lens
```

### Source Configuration
News sources and their specific parameters are configured in `src/backend/config/sources.yaml`. This file defines the feeds to scrape, language, categorization, orientation confidence, and rate limits.

Example configuration parameters per source:
* `slug`: Unique identifier for the source.
* `rss`: List of RSS feed URLs.
* `language`: Primary language code (e.g., `en`, `ta`).
* `orientation_bucket`: Editorial orientation classification (`IND`, `CON`, `DRV`, `MIXED`).
* `fetch_interval_minutes`: Polling frequency for Celery Beat.
* `rate_limit_per_minute`: Constraints for the scraper.

## Prerequisites

* **Python:** 3.10 or higher.
* **Node.js & Bun:** Required for running the Next.js frontend application.
* **PostgreSQL:** Version 16 with `pgvector` extension installed.
* **Redis:** Required for Celery task queuing.

## Setup Instructions

### 1. Local Infrastructure Setup
A shell script is provided to automatically provision PostgreSQL, pgvector, and Redis on Debian/Ubuntu-based systems.

```bash
cd src/backend/scripts/shell
chmod +x setup_local_infra.sh
./setup_local_infra.sh
```
This script sets up the `veritas_lens` database, user roles, and installs the required vector extensions.

### 2. Backend Installation
Return to the project root, create a Python virtual environment, and install the dependencies.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Frontend Installation
Navigate to the frontend directory and install the Node dependencies.

```bash
cd src/frontend
bun install
# Alternatively: npm install
```

## Running the Application

### Backend Services
There are multiple ways to execute the backend pipeline depending on your environment needs.

**Method A: Celery Orchestration (Recommended)**
Run the main entrypoint which initializes the database, starts the Celery worker, and launches the Celery beat scheduler for polling.

```bash
# From the project root
python src/backend/main.py
```

**Method B: Background Daemon (Shell Loop)**
Alternatively, you can run the pipeline sequentially as a background daemon script without Celery.

```bash
# From the project root
./src/backend/scripts/shell/start_daemon.sh
```
To stop the daemon, execute `./src/backend/scripts/shell/stop_daemon.sh`.

**Method C: API Server**
Start the FastAPI server separately to serve JSON data to the frontend.

```bash
# Ensure your PYTHONPATH is set to the src directory
export PYTHONPATH=$(pwd)/src:$PYTHONPATH
uvicorn backend.api:app --host 0.0.0.0 --port 8000
```

### Frontend Service
Start the Next.js development server.

```bash
cd src/frontend
bun run dev
# Alternatively: npm run dev
```
The application interface will be accessible at `http://localhost:3000`.

## API Endpoints

The FastAPI application provides the following core endpoints:
* `GET /events/`: Retrieves the latest clustered news events. Supports language translation via the `lang` query parameter (e.g., `?lang=ta`).
* `GET /events/{event_id}`: Retrieves comprehensive details for a specific event cluster, including orientation coverage metrics and extracted entities (people, locations).
* `GET /metadata`: Returns configuration details about the current models in use and the pipeline status.

## Evaluation & Testing

The `/evaluation` directory contains scripts to assess the accuracy of the pipeline. You can run evaluations for the NER pipeline and semantic clustering. Generated metrics are output as CSV files (e.g., `ner_metrics.csv`). Additional tests can be executed via `pytest`.
