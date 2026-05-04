# WatchStock

A self-hosted stock analysis terminal. Search any publicly traded company and get live financial metrics, semantically scored news, AI-generated analysis, and an agentic chat that can control the UI — all running locally on your machine.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-async-green)
![SQLite](https://img.shields.io/badge/SQLite-built--in-lightblue)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

---

## Features

- **Live financial data** — current price, market cap, P/E, debt/equity, beta, profit margins, revenue growth and more, pulled directly from Yahoo Finance
- **Health scores (0–100)** — short-term (liquidity & shock resistance) and long-term (solvency & geopolitical) composite scores with explainable breakdowns
- **Semantic news scoring** — articles are encoded into 384-dimensional vectors and ranked by cosine similarity against a risk reference embedding, not just keyword matches
- **AI analysis reports** — 5-section deep-dive: executive summary, recommended action, financial analysis, news impact, and risk scenarios (optimistic / base / pessimistic)
- **Agentic chat** — ask questions in natural language; the AI can generate charts, switch tabs, append analysis, and load different companies directly from the chat panel
- **Market movers** — home screen shows today's top 5 gainers and losers, pulled live from Yahoo Finance screener
- **Bring your own API key** — configure your LLM provider (OpenRouter, Gemini, Anthropic) and model from the Settings panel inside the app, no terminal required
- **Zero external services** — SQLite for persistence, no Elasticsearch, no Docker, no Java

---

## Quick Start

### 1. Prerequisites

- **Python 3.10+** — [python.org/downloads](https://www.python.org/downloads/) — check *"Add Python to PATH"* during install

### 2. Setup (once)

```
setup.bat
```

This will:
- Verify Python is installed
- Create a virtual environment
- Install all dependencies
- Pre-download the NLP model (~90 MB, one-time)

### 3. Launch

```
start.bat
```

Opens the app at `http://localhost:8000` automatically.

### 4. Configure API keys

Click your username in the bottom-left (or the gear icon on the home screen) to open **Settings** and enter your keys:

| Key | Where to get it | Required |
|-----|----------------|----------|
| LLM API Key | [openrouter.ai](https://openrouter.ai) · [ai.google.dev](https://ai.google.dev) · [console.anthropic.com](https://console.anthropic.com) | Yes (for AI analysis) |
| News API Key | [newsapi.org](https://newsapi.org) — free tier | Optional |

---

## How It Works

### Search pipeline

```
Search "NVIDIA"
    │
    ├─ Memory cache hit  ──────────────────────> instant return
    │
    ├─ SQLite hit  ────────────────────────────> rebuild from DB (no API calls)
    │
    └─ Cache miss
           │
           ├─ yfinance        → financial metrics
           ├─ NewsAPI         → articles → NLP semantic scoring
           ├─ Health scores   → calculated from metrics + news penalties
           └─ LLM             → 5-section analysis report
                    │
                    └─ Save to SQLite + memory cache → return
```

### Semantic news scoring

Each article is encoded with `sentence-transformers/all-MiniLM-L6-v2` (384-dim vectors) and compared via cosine similarity against a reference risk embedding. A dynamic threshold filters noise: stricter for mega-caps (>$100B market cap), looser for smaller companies.

Score ranges:
- `< 0.15` — filtered out
- `0.15–0.20` — low relevance
- `0.20–0.30` — moderate risk signal
- `> 0.30` — high risk signal (penalises health scores)

### Health scores

| Score | Components | Penalties |
|-------|-----------|-----------|
| Short-Term (0–100) | Current Ratio, Quick Ratio, Profit Margins | High-risk news signals (up to −30) |
| Long-Term (0–100) | Debt/Equity, Beta | Geopolitical risk + residual news |

### Agentic chat

The chat LLM receives full company context and can execute structured UI actions: `update_chart`, `append_new_chart`, `switch_tab`, `search_company`, `update_tab_content`, `highlight_risk`. Multi-turn context is maintained for up to 20 messages.

---

## Project Structure

```
WatchStock/
├── main.py                    # FastAPI backend — all endpoints, NLP, AI, DB
├── index.html                 # Terminal dashboard (single-page app)
├── login.html                 # Login / register page
├── setup.bat                  # One-time setup script
├── start.bat                  # Launch script (activates venv, opens browser)
├── requirements.txt           # Python dependencies
└── TECHNICAL_DOCUMENTATION.md # In-depth technical reference
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + uvicorn (async Python) |
| Database | SQLite (built-in, zero config) |
| NLP | sentence-transformers `all-MiniLM-L6-v2` |
| Financial data | yfinance (Yahoo Finance) |
| News | NewsAPI (optional) |
| AI / LLM | OpenRouter · Gemini · Anthropic (bring your own key) |
| Frontend | Vanilla JS + Tailwind CSS |
| Charts | Chart.js |

---

## License

MIT
