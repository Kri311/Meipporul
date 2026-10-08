# Veritas Lens - Interactive Development Report

> Historical development report. Current runtime behavior and commands are
> maintained in the repository README and ARTICLE_REPROCESSING.md.

## Objective
Build the RSS feed ingestion service with Docker, aligned with Phase 1 of `JOURNAL.md`. This will be built interactively to ensure a thorough understanding of the architecture, components, and data flow.

## Progress Tracker
- [x] Create project structure and code space
- [x] Step 1: Set up the Local environment (`setup_local_infra.sh`)
- [x] Step 2: Define Python dependencies (`requirements.txt`)
- [x] Step 3: Configure the news sources (`config/sources.yaml`)
- [x] Step 4: Set up the Database Connection & Schema (`ingestion/models/database.py`)
- [x] Step 5: Configure Celery App and Broker (`ingestion/main.py`)
- [x] Step 6: Implement RSS Fetching Task (`ingestion/tasks/fetch_feed.py`)
- [x] Step 7: Test the full pipeline locally

## Current Status
We have successfully completed all 7 steps of Phase 1! The entire architecture is built:
1. A local setup script installs PostgreSQL, Redis, and `pgvector`.
2. The `sources.yaml` decouples our outlet definitions from the Python code.
3. The `database.py` defines a strict data schema, ensuring article provenance and semantic readiness via `pgvector`.
4. `fetch_feed.py` intelligently checks RSS length and seamlessly falls back to `trafilatura` to extract the *full* text of the article directly from the URL.

```
veritas_lens_alt/
├── setup_local_infra.sh     # Automates installation of PG16, Redis, and pgvector
├── .env.example             # Environment variables template
├── config/
│   └── sources.yaml         # Configuration for RSS feeds
├── ingestion/               # Python application for fetching feeds
│   ├── requirements.txt     # Python dependencies
│   ├── main.py              # Celery application entry point
│   ├── tasks/
│   │   ├── __init__.py
│   │   └── fetch_feed.py    # RSS parsing and URL normalization logic
│   └── models/
│       ├── __init__.py
│       └── database.py      # SQLAlchemy/SQLModel models for Postgres
└── REPORT.md                # This progress tracker
```

**Next up:** The pipeline is completely ready for local execution! To run it:
1. Run `./setup_local_infra.sh` to configure PostgreSQL and Redis on your machine (one-time).
2. Set up your Python environment using pyenv/venv and run `pip install -r requirements.txt`.
3. Start the entire system (Database Init, Celery Worker, and Celery Beat) with a single command:
   ```bash
   python main.py
   ```
### new problem
as the bias rating for the tamil news outlet isn't posted in any forms of liable organisation. we need to look for an alternative like we need to take upon a labelling in order to classify the news from the news outlets in a ordered one in terms of bias.
Based on political party might go on a wrong route as no news channels expose their support to a particular party and they remain conservative/variable regarding to the ruling party.

we can't go with the left/center/right in our tamilnadu's politics bias as it's not a two party ruling society but multi party ruling one. and also DMK/ADMK ruled binary political system is thrown out by a newly formed TVK party formed by vijay on 2022.

for bias part,
   - either we can go with a new type of bias classifying system, else
   - we could go with training a bias system for this case study.
- take the precision recall f1 score macro scores also and save it as seperate column inthe zero shot metrics ...
- I have updated the zero_shot_metrics.csv to include separate columns for precision, recall, f1_score, macro_precision, macro_recall, and macro_f1.

However, there is a very important machine learning caveat here: I had to set their values to "N/A" for now.

Why can't we calculate Precision/Recall yet?
To calculate Precision, Recall, or an F1 score, the mathematical formula requires Ground Truth (also known as a "Gold Standard").

True Positives: Entities the model guessed correctly.
False Positives: Entities the model guessed incorrectly.
False Negatives: Entities the model missed entirely.
Because we are running a zero-shot pipeline on raw, unlabeled news data directly from your database, the system doesn't have an answer key to check its work against. It doesn't know if the extracted entity is correct or wrong, so it mathematically cannot calculate an F1 score.

How we will solve this:
This is exactly why we need the fine-tuning pipeline! Our next steps should be:

We will use the auto-annotator to generate a small set of "predictions".
You (or a team) will quickly manually review/correct a few hundred of them to create a Gold Standard Dataset.
Once we have that Gold Standard, we can plug it back into this script, and those "N/A" columns will populate with the actual Precision, Recall, and Macro F1 scores!
