# Sourcing Buyer Terminal

A real-time supplier risk intelligence platform built for procurement teams. Combines live financial data, NLP-scored news signals, and AI-generated analysis into a dark-themed terminal interface.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-async-green)
![Elasticsearch](https://img.shields.io/badge/Elasticsearch-8.17-yellow)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

## What It Does

Search any publicly traded company and instantly get:

- **Financial health scores** (0-100) computed from live Yahoo Finance data
- **Semantically scored news** — each article rated by NLP for risk relevance, not just keyword matches
- **AI-generated due diligence reports** — 5-section analysis covering executive summary, financial deep dive, news impact, and risk scenarios
- **Agentic chat** — ask the AI questions and it can generate charts, switch tabs, and append analysis directly into the UI
- **Shared intelligence** — any company analyzed by one user is instantly available to all users from Elasticsearch

## Quick Start

### Prerequisites

- Python 3.10+
- [Elasticsearch 8.17](https://www.elastic.co/downloads/elasticsearch) (local install)
- API keys: [NewsAPI](https://newsapi.org/) (free tier) and [OpenRouter](https://openrouter.ai/)

### Setup

1. **Clone and install dependencies:**
   ```bash
   git clone <repo-url>
   cd HackAthon
   pip install -r requirements.txt
   ```

2. **Configure environment variables** — create a `.env` file:
   ```env
   NEWS_API_KEY=your_newsapi_key
   ES_URL=http://localhost:9200
   ES_USER=elastic
   ES_PASS=your_es_password
   OPENROUTER_API_KEY=your_openrouter_key
   ```

3. **Configure Elasticsearch** for local development — in `elasticsearch.yml`:
   ```yaml
   xpack.security.enabled: false
   discovery.type: single-node
   http.port: 9200
   ```

4. **Launch everything** (Windows):
   ```bash
   start.bat
   ```
   This starts Elasticsearch, Kibana, waits for ES to be ready, then launches the FastAPI server.

   **Or manually:**
   ```bash
   python main.py
   ```
   Server runs at `http://localhost:8000`

5. **Open the app** — navigate to `http://localhost:8000`, register an account, and search for a company.

## How It Works

### The Search Pipeline

```
User searches "NVIDIA"
     |
     v
Memory Cache ──HIT──> instant return
     |
    MISS
     |
     v
Elasticsearch ──HIT──> rebuild from 3 indices (no API calls)
     |
    MISS
     |
     v
Live Pipeline: yfinance + NewsAPI + NLP scoring + AI analysis
     |
     v
Save to ES + cache --> return to user
```

### Semantic News Scoring

We don't just show "news about company X". Each article is **encoded into a 384-dimensional vector** using `all-MiniLM-L6-v2` and compared via cosine similarity against a reference risk embedding. Articles below a **dynamic threshold** (stricter for mega-caps, looser for mid-caps) are filtered out.

### Health Scores

Two composite scores (0-100):
- **Short-Term Safety:** Current Ratio, Quick Ratio, Profit Margins — penalized by high-risk news
- **Long-Term Safety:** Debt/Equity, Beta — penalized by geopolitical risk and residual news impact

### Agentic AI Chat

The chat panel's LLM can control the UI through structured action objects — generating charts, switching tabs, appending analysis, and even loading different companies. All within a multi-turn conversation context.

## Project Structure

```
HackAthon/
  main.py                      # FastAPI backend (all endpoints, NLP, AI, ES)
  index.html                   # Main terminal dashboard (single-page app)
  login.html                   # Authentication page
  start.bat                    # One-click launcher (ES + Kibana + FastAPI)
  requirements.txt             # Python dependencies
  TECHNICAL_DOCUMENTATION.md   # In-depth technical docs
  .env                         # API keys (not committed)
```

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Backend | FastAPI + uvicorn | Async Python web server |
| Database | Elasticsearch 8.17 | Document store (4 indices) |
| NLP | sentence-transformers | Semantic news scoring |
| Financial Data | yfinance | Live metrics from Yahoo Finance |
| News | NewsAPI | Article fetching (with ES fallback) |
| AI | OpenRouter (GPT-4o-mini) | Analysis generation + agentic chat |
| Frontend | Vanilla JS + Tailwind | Dark terminal UI |
| Charts | Chart.js | Dynamic metric visualizations |

## Documentation

See [TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md) for in-depth coverage of:
- Semantic scoring algorithm and branching search
- Dynamic thresholding by market cap
- Health score mathematics and normalization functions
- Elasticsearch index architecture and data flow
- DB-first shared intelligence pattern
- News resilience fallback chain
- Agentic chat UI action system
- Full API reference

## License

MIT
