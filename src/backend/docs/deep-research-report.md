# Project Journal: Tamil News Bias-Aware Aggregator

> Research proposal and historical notes; not a statement of current deployed
> behavior. See the root README and ARTICLE_REPROCESSING.md for the active
> pipeline contract. In particular, embeddings are not translations.

This project aims to build a **Tamil news aggregator** that collects important Tamil-language news from major outlets and displays them grouped by event with bias annotations, inspired by Ground News. The system will highlight how different outlets report the same event, and will include a “Blindspot” section for stories covered predominantly by one bias category. We will label each source’s bias (e.g. Pro-Dravidian, Opposition (TVK/AIADMK/BJP), Conservative, Independent) using curated ratings from independent media-monitoring organizations or research. The product will support both Tamil and English content (for example, English summaries of Tamil news) and will be fully containerized for development and deployment (Docker). 

## Phase 1: Data Sources and Collection 

- **Select Tamil News Outlets:** Identify leading Tamil news publishers (print and TV channels) focused on politics and current events. Examples include *Dina Thanthi*, *Dinamalar*, *Dinakaran*, *The Hindu (Tamil)*, *Puthiya Thalaimurai*, *News7 Tamil*, *Thanthi TV*, *Polimer News*, etc. We will focus on **Tamil-language articles** from these outlets (not cross-language English news from national papers). Non-news content (entertainment, astrology, health tips, rumors) will be filtered out by content keywords or topics, since the DravidianLangTech community emphasizes filtering out misinformation and spam. 

- **Bias Labeling Strategy:** For each outlet, assign a bias category based on its known political alignment. Since no public “AllSides” exists for Tamil, we will use expert research and consensus. Ground News assigns source biases via independent organizations (AllSides, Media Bias/Fact Check). We will adopt a similar approach: e.g. Dravidian-aligned outlets labeled *Pro-Dravidian*, national-right outlets as *Conservative/Opposition*, and others as *Independent*. These labels will be stored in our database for use in the UI. 

- **RSS Feed and Scraping:** Many Tamil outlets publish RSS/Atom feeds. For example, Oneindia Tamil provides several feeds for major news categories. We will inventory RSS URLs (news categories only) from each site. For outlets without RSS, we will implement a lightweight web-scraper to extract headlines and article links. A Celery task will periodically fetch all feeds and update URLs. The feed items include metadata (title, timestamp, summary) which we use to detect new articles.  

- **Celery Scheduling:** Use **Celery** (with Redis or RabbitMQ as broker) to schedule periodic data collection tasks. Celery is a proven distributed task queue that supports cron-like scheduling. For example, a “beat” scheduler can trigger RSS-fetch tasks every few minutes. Each task parses the feed, extracts new article links, and enqueues article-fetch tasks. This asynchronous pipeline ensures robustness (if one site fails, it doesn’t block others). 

- **Storage Planning:** All raw data will be stored in **PostgreSQL** (in Docker), using the **pgvector** extension for embedding vectors. PostgreSQL will hold tables like `articles` (id, title, content, source, published_at, bias_label, language, topic_id, vector_embedding, etc.) and `topics` or `events`. pgvector enables storing and searching vector embeddings directly in Postgres. This eliminates the need for a separate vector database: as pgvector’s docs note, it “enables vector storage and similarity search directly within Postgres, eliminating the need for a separate vector database”. We will store each article’s text embedding (e.g. sentence-transformer or LLM embedding) in a `vector` column, allowing similarity queries for clustering and search.

## Phase 2: System Architecture (Dockerized)

 *Figure: Conceptual system architecture for the Tamil news aggregator.* The architecture will be microservices-style, all running in Docker containers. Key components include: 

- **Ingestion Service:** A Python (Flask or FastAPI) service that interfaces with Celery to fetch RSS feeds and article pages. It uses libraries like `feedparser` and `requests/BeautifulSoup` to retrieve content.  
- **Database:** A Postgres container with pgvector for storing articles and embeddings. A separate Redis container will serve as Celery’s broker and result backend.  
- **Preprocessing Worker:** A Celery worker container that cleans HTML, normalizes text (removing boilerplate, scripts), and optionally translates into Tamil or English as needed. It then writes cleaned text into Postgres and triggers embedding generation.  
- **Embedding Service:** A container running a Python script to compute text embeddings (e.g., using Sentence-BERT or a small multilingual transformer). The embeddings (vectors) are stored via pgvector for semantic search.  
- **AI Model Service:** A container for running our NLP models (NER, summarization). We might use a framework like HuggingFace Transformers with a web API (Flask/Gunicorn) or a simple batch inference pipeline. This service will generate entity labels and summaries when triggered.  
- **Backend/API:** A web API container that serves processed data to the frontend. It can query Postgres (including vector similarity with pgvector) to fetch clustered articles and summary results.  
- **Frontend:** A React or Vue.js container (or static files served by Nginx) for the user interface. It will call the backend to display event groups, summaries, and allow filtering by bias.  

All services will be defined in a Docker Compose (or Kubernetes) setup for easy deployment. Docker ensures each component runs in a clean environment (e.g. Linux-based images, with the needed libraries). We will use Alpine or slim Python images to keep containers small. Routine tasks like renewing SSL certificates (for HTTPS) and system monitoring (Prometheus/Grafana) will also be included in deployment. 

## Phase 3: Data Processing and Event Grouping

Once articles are collected and stored, we perform NLP processing:

- **Data Cleaning:** Strip HTML tags, remove ads/footers, normalize Unicode, and extract the main article text. Libraries like Newspaper3k or Readability can help. For example, the InfoCore system used Newspaper3k for news scraping and entity extraction. We will similarly tokenize and preprocess text. 
- **Filtering Irrelevant Content:** We will heuristically drop articles that seem off-topic (e.g. containing keywords like “recipe”, “astrology”, “celebrity” etc.). This is crucial to avoid clutter and misinformation. As highlighted by the DravidianLangTech workshop, detecting misinformation and rumors is an important challenge; we will flag or exclude content that looks like rumor/advertorial to maintain quality. 

- **Named Entity Recognition (NER):** Apply NER on cleaned text to extract entities (persons, organizations, locations, events). We will use a Tamil-capable NER model (for example, a fine-tuned BERT for Tamil from HuggingFace). Extracted entities help cluster articles by event. Research shows NER and clustering are effective for deduplicating and categorizing news events. InfoCore’s example uses transformer-based NER to group related content by entity. We will tag each sentence with entities and store them in Postgres (array or linked table). 

- **Event Clustering:** Group articles that discuss the same real-world event. Possible approaches: cluster article embeddings using DBSCAN or Agglomerative Clustering, or link by common named entities. We might first compute a representative embedding per article (from Sentence-BERT) and then cluster all recent articles by cosine similarity. As an example, InfoCore used clustering on news to identify duplicates and events. We can similarly use pgvector’s nearest-neighbor search to find related articles and form a cluster. Each cluster gets a `topic_id`. We will also associate topic labels (keywords from prominent entities) and ensure each cluster contains articles from multiple sources if available. 

- **Bias Category Tagging:** For each article, we already know its source’s bias label (from Phase 1). After clustering, we can see the distribution of biases in each event. This allows features like highlighting if a cluster has, say, mostly *Pro-Dravidian* coverage and little *Opposition* coverage (a “blindspot”). 

## Phase 4: AI/ML Pipeline (NER, Summarization, Clustering)

 *Figure: Example of an AI model pipeline (conceptual). We will use multilingual NLP models for Tamil and English tasks.* 

- **NER Model:** Choose or train an NER model for Tamil. Options include fine-tuning a transformer (e.g. XLM-R or IndicBART) on Tamil NER datasets, or using community models (e.g. “sathishmahi/tamil-ner-model”). The model will label entities in Tamil text, which aids clustering. We will evaluate NER with precision, recall, and F1 score (the harmonic mean of precision and recall). For NER, F1 is critical: it ensures we balance not missing entities and not hallucinating extras.  

- **Summarization Model:** Generate multi-article summaries of each cluster, segmented by bias. For example, for a given event cluster, we might run two summaries: one summarizing the content from *Pro-Dravidian* sources and one from *Opposition* sources. This shows readers how different sides “frame” the event. For Tamil, we can use a model like **IndicBART** (a seq2seq model supporting Tamil), fine-tuned on news summaries. IndicBART is explicitly designed for Indic languages (including Tamil) and can handle summarization. We may also use mT5 or MBart-based models. The models will output concise Tamil summaries (and possibly an English translation). For English portions, we could use a multilingual summarizer as well. 

- **Evaluation:** We will evaluate summarization quality using ROUGE scores, which measure overlap of generated summaries with reference summaries. ROUGE is standard for summarization (it measures how much important information from reference is captured). We may also do human evaluation on a sample. For NER, we evaluate entity extraction using F1. For clustering, metrics like Adjusted Rand Index or Silhouette score (on embeddings) can guide our algorithm tuning. 

- **Scalability Considerations:** We will use lightweight or quantized models to fit local resource constraints. For instance, smaller variants of IndicBART or quantized transformer models (e.g. GGUF format) can run efficiently on CPU/GPU. Each model is containerized (with possibly separate GPU support if needed). 

## Phase 5: Application Features and Frontend

- **Event Pages:** The frontend will list “stories” (event clusters). Each story page shows: the event title (in Tamil and English), date, and a timeline of coverage. For each outlet in that story, we show its headline and an excerpt. We highlight the outlet’s bias label (e.g. a color-coded tag). This lets users compare different narratives. Ground News’s approach was to merge all coverage of an event into a single page, and we will do similarly. 

- **Blindspot Section:** Implement a “Blindspot” feed like Ground News. A blindspot is when one bias side has high coverage of an event but others have little or none. For example, if only *Opposition*-aligned media cover an issue and *Pro-Dravidian* outlets ignore it, we flag this as a blindspot. The front-end will show a list of such events with a brief description. As Ground News puts it, blindspots “highlight what news topics are being covered by only one side of the political spectrum”. This feature helps readers notice gaps in cross-media coverage. 

- **Search and Filtering:** Users can filter stories by bias categories or search by keywords. We leverage pgvector for semantic search on headlines or embeddings. The “Sort & Filter” tool in Ground News inspired us to allow filtering by bias, date, or popularity. 

- **Localization:** UI text and navigation will be in Tamil (with English UI option). Article summaries may be displayed in Tamil and/or English. We’ll use a Tamil-language web font and support right-to-left text if needed (Tamil is left-to-right, but careful with unicode). 

## Phase 6: Deployment and Operations

- **Container Orchestration:** We will use **Docker Compose** (or Kubernetes) to deploy all services. Each component (ingester, worker, API, frontend) runs in a container built from a Dockerfile. For example, the API container might be Python/Gunicorn on Ubuntu base, the frontend container Nginx+React, etc. Docker Compose will define inter-service networks and environment variables. This setup makes the system reproducible on any machine. 

- **Hosting:** For production, we might host on a cloud VM or Kubernetes cluster. PostgreSQL can be a managed instance or a container; Redis likewise. We’ll expose the frontend via HTTPS (using Let’s Encrypt SSL), and possibly put Nginx as a reverse proxy. 

- **Code Management:** We will keep code in Git (GitHub) with branches for each component. CI pipelines will build Docker images and run tests (e.g. lint, small integration tests). 

- **Monitoring:** Use Prometheus and Grafana or similar for system monitoring (Docker/container health, task queues, error logs). Logging should capture failures (e.g. if an RSS feed is down). Alerts can be configured to notify us if ingestion fails for a source repeatedly. 

- **Resource Constraints:** Since we aim to run locally or on a single VM, we will optimize image sizes (use Python slim) and choose compact ML models. If GPU is unavailable, models will run on CPU, so we may restrict batch size or use CPU-optimized libraries. 

## Evaluation and Future Work

- **Model Evaluation:** As noted, summarizers will be evaluated with ROUGE and possibly BLEU for English summaries. NER will be evaluated via precision/recall/F1 on a held-out annotated set (if available) or via manual checks. Clustering quality will be evaluated by manually inspecting event coherence. 

- **Feature Extensions:** Additional product features could include user accounts (personalized topic filters), trending topic alerts, or a daily newsletter. We could integrate fact-checking APIs or sentiment analysis to tag content. Voice-reading or mobile app interfaces are future possibilities. The core system, however, is designed to be robust and extensible, with no single point of failure and automated recovery (thanks to Celery scheduling). 

- **No Room for Errors:** By automating the pipeline (container health checks, retries on failure, input validation, unit tests for NLP components) we minimize partial outputs. For example, Celery workers will log and retry broken feeds rather than dropping them silently. Database constraints (e.g. unique article URLs) prevent duplication. 

In summary, this phased plan covers **data collection** (RSS feeds, filtering), **system design** (microservices with Docker, Celery/Redis scheduling, Postgres+pgvector storage), **NLP processing** (NER and clustering per InfoCore, summarization with IndicBART), and **UI features** (bias comparison, blindspots) with evaluation metrics (ROUGE, F1). All components will be built with open-source tools and containerized for ease of deployment. This comprehensive design mirrors the approach of Ground News while focusing on Tamil-language media. 

**Sources:** Design ideas are informed by Ground News documentation, the PGVector extension description, and AI/NLP model capabilities. Evaluation metric references are from standard NLP guides.
