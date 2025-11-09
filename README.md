# SentimentFlow-V2

## Overview

**SentimentFlow-V2** is an end-to-end **Data Engineering + NLP pipeline** that autonomously gathers and analyzes news sentiment for a curated list of startups.

It performs a **daily “sync”** by fetching global articles, identifying startups mentioned, performing **zero-shot sentiment analysis** per startup, and storing results in a PostgreSQL database.  
A **Streamlit-based Admin Dashboard** allows easy management of tracked startups and sectors.

This repository demonstrates a real-world, production-grade application of **Data Science, NLP, and CI/CD automation**.

---

## Tech Stack

| Layer | Technology | Purpose |
| :-- | :-- | :-- |
| **Language** | Python 3.11 | Core logic & scripting |
| **Database** | PostgreSQL | Relational data storage (via Prisma Proxy) |
| **Data Fetching** | NewsAPI | Source for global news articles |
| **ML Model** | [Soumil24/zero-shot-startup-sentiment-v2](https://huggingface.co/Soumil24/zero-shot-startup-sentiment-v2) | Zero-Shot NLI model for startup sentiment |
| **NLP Libraries** | `transformers`, `torch` | Model inference |
| **Core Libraries** | `psycopg2`, `pyahocorasick` | DB connection & high-speed text matching |
| **Admin UI** | Streamlit | Web-based admin dashboard |
| **Automation** | GitHub Actions | Scheduled ETL runs (3× daily) |

---

##  Core Features

**Automated 3×/Day Pipeline** — runs automatically via GitHub Actions.  
**Dynamic Fetch Logic** — 30-day *backfill* for new startups, 1-day *maintenance* fetch for existing ones.  
**Keyword-Driven Queries** — auto-builds NewsAPI queries using `findingKeywords` (e.g., “food delivery”).  
**High-Performance Search** — Aho-Corasick automaton detects 30+ startups in a single text pass.  
**Bulk AI Analysis** — Zero-Shot sentiment inference in mini-batches for GPU efficiency.  
**Streamlit Admin Dashboard** — add/update startups directly through the browser.  
**Transactional Integrity** — all DB operations occur in atomic transactions.

---

## Project Structure

```
/
├── .github/workflows/
│ └── main_pipeline.yml # CI/CD pipeline (GitHub Actions)
├── scripts/
│ ├── clear_data.py # Clears Articles & Sentiment tables
│ └── seed_sectors.py # Seeds 'Sector' table with 30 sectors
├── src/
│ ├── core/
│ │ ├── config.py # Loads environment (.env)
│ │ └── logger.py # Project-wide logging setup
│ ├── constants.py # Global constants (batch size, etc.)
│ ├── pipeline/
│ │ └── init.py # Main ETL pipeline orchestrator
│ └── utils/
│ ├── api_utils.py # NewsAPI calls, key rotation, dedup
│ ├── db_utils.py # DB connections, inserts, queries
│ ├── sentiment_utils.py # Zero-shot model & batch predictions
│ └── text_utils.py # Aho-Corasick search engine & IDs
├── .env.example # Template for environment variables
├── main.py # Entry point for the pipeline
├── requirements.txt # Python dependencies
└── streamlit_admin.py # Streamlit admin dashboard
```

---

## Database Design

A **4-table relational model** efficiently links startups to articles and sentiments.

### Sector Table

| Column | Type | Description |
| :-- | :-- | :-- |
| `id` | INT (PK) | Unique sector ID (e.g., 1, 2) |
| `name` | TEXT | Sector name (e.g., “Fintech”) |

### Startups Table

| Column | Type | Description |
| :-- | :-- | :-- |
| `id` | TEXT (PK) | Deterministic ID (e.g., `swiggy-a1b2c3-d4e5`) |
| `name` | TEXT | Startup’s official name |
| `sectorId` | INT (FK) | Links to `Sector.id` |
| `description` | TEXT | Startup description |
| `imageUrl` | TEXT | Logo URL |
| `findingKeywords` | TEXT | JSON string of keywords (e.g., `["food delivery"]`) |

### Articles Table

| Column | Type | Description |
| :-- | :-- | :-- |
| `id` | UUID (PK) | Unique article ID |
| `title` | TEXT | Article title |
| `content` | TEXT | Truncated content (≤ 300 chars) |
| `url` | TEXT (UNIQUE) | Article URL |
| `publishedAt` | TIMESTAMP | Original publication time |

### ArticlesSentiment Table (Many-to-Many)

| Column | Type | Description |
| :-- | :-- | :-- |
| `id` | UUID (PK) | Unique entry ID |
| `articleId` | UUID (FK) | Links to `Articles.id` |
| `startupId` | TEXT (FK) | Links to `Startups.id` |
| `positiveScore` | FLOAT | Probability of positive sentiment |
| `negativeScore` | FLOAT | Probability of negative sentiment |
| `neutralScore` | FLOAT | Probability of neutral sentiment |
| `sentiment` | TEXT | Final label (`positive` / `neutral` / `negative`) |

---

## Sentiment Analysis Logic

The project uses a **Zero-Shot Natural Language Inference (NLI)** model — not a conventional sentiment classifier — allowing startup-specific sentiment detection even in multi-company articles.

**Model:** [`Soumil24/zero-shot-startup-sentiment-v2`](https://huggingface.co/Soumil24/zero-shot-startup-sentiment-v2)

**Premise:**  
> “Swiggy’s revenue jumps, but Zomato’s losses widen…”

**Hypotheses per startup:**  
1. The news for Swiggy is **positive**.  
2. The news for Swiggy is **neutral**.  
3. The news for Swiggy is **negative**.

The model outputs **entailment probabilities** for each hypothesis:  
→ `positiveScore`, `neutralScore`, `negativeScore`  
→ the label with the highest score becomes the **final sentiment**.

---

## Getting Started

### 1 Clone the Repository
```bash
git clone https://github.com/SoumilMalik24/SentimentFlow-V2.git
cd SentimentFlow-V2
```

### 2 Create Virtual Environment
```bash
python -m venv venv
# Linux/Mac
source venv/bin/activate
# Windows
.\venv\Scripts\activate
```

### 3 Install Dependencies
```bash
pip install -r requirements.txt
```

### 4 Configure Environment

Copy .env.example → .env, then fill in:
```bash
DB_URL=postgresql://user:pass@host:port/dbname
NEWS_API_KEYS=["key1","key2"]
HF_TOKEN=your_huggingface_token
MODEL_PATH=Soumil24/zero-shot-startup-sentiment-v2
```

---

## Running the Project

### 1. Admin Dashboard (setup first)

Used to manage sectors & startups.

**Seed sectors:**
```bash
python scripts/seed_sectors.py
```

**Launch the Streamlit app:**
```bash
streamlit run streamlit_admin.py
```
streamlit run streamlit_admin.py

---

### 2. Main Pipeline

Runs the automated ETL workflow (fetch → analyze → store).

**Manual run:**
```bash
python main.py
```
**To force a full reset (clear all data):**
```bash
python scripts/clear_data.py
```

---

# CI/CD Automation

Configured to run automatically via **GitHub Actions**.

| Setting | Description |
| :-- | :-- |
| **Workflow File** | `.github/workflows/main_pipeline.yml` |
| **Schedule** | Runs 3× per day — 7 AM, 1 PM, and 7 PM (IST) |
| **Secrets Required** | `DB_URL`, `NEWS_API_KEYS`, `HF_TOKEN`, `MODEL_PATH` |

---

## Contributors

**Soumil Malik** — Developer  
🔗 [GitHub @SoumilMalik24](https://github.com/SoumilMalik24)  

Creator of the [Zero-Shot Startup Sentiment Model](https://huggingface.co/Soumil24/zero-shot-startup-sentiment-v2)

---

## License

This project is released under the **MIT License**.  
Feel free to **fork**, **adapt**, and **build upon it** — credit is appreciated!

---

## Inspiration

**SentimentFlow-V2** was built to bridge the gap between **real-time news analysis** and **startup intelligence**, providing **automated**, **explainable**, and **scalable sentiment insights** for **investors**, **analysts**, and **researchers**.
