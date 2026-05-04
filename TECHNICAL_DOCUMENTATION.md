# Sourcing Buyer Terminal - Technical Documentation

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Data Pipeline: How a Search Works](#data-pipeline-how-a-search-works)
3. [Semantic News Scoring - The NLP Engine](#semantic-news-scoring---the-nlp-engine)
4. [Dynamic Thresholding](#dynamic-thresholding)
5. [Health Score Mathematics](#health-score-mathematics)
6. [Elasticsearch: Why We Use It & How Data is Stored](#elasticsearch-why-we-use-it--how-data-is-stored)
7. [DB-First Architecture: Shared Intelligence](#db-first-architecture-shared-intelligence)
8. [News Resilience: The Fallback Chain](#news-resilience-the-fallback-chain)
9. [AI Analysis Pipeline](#ai-analysis-pipeline)
10. [Agentic Chat: LLM-Controlled UI](#agentic-chat-llm-controlled-ui)
11. [Authentication & Per-User History](#authentication--per-user-history)
12. [Frontend Architecture](#frontend-architecture)
13. [API Reference](#api-reference)

---

## Architecture Overview

The Sourcing Buyer Terminal is a **full-stack supplier risk intelligence platform** built for procurement teams. It combines live financial data, NLP-scored news signals, and AI-generated analysis into a single dark-themed terminal interface.

```
+------------------+     +------------------+     +-------------------+
|   login.html     | --> |    index.html     | <-> |    main.py        |
|   (Auth Gate)    |     |  (Terminal UI)    |     |   (FastAPI)       |
+------------------+     +------------------+     +-------------------+
                                                     |    |    |    |
                                          +----------+    |    |    +----------+
                                          |               |    |               |
                                   +------v----+  +------v----v--+  +---------v--------+
                                   |  yfinance  |  |   NewsAPI    |  | OpenRouter (LLM) |
                                   | (Financials)|  | (News + NLP) |  | (AI Analysis)    |
                                   +------+-----+  +------+-------+  +---------+--------+
                                          |               |                     |
                                          +-------+-------+---------------------+
                                                  |
                                          +-------v--------+
                                          | Elasticsearch  |
                                          | (Persistence)  |
                                          +----------------+
                                          | company_index  |
                                          | source_index   |
                                          | analysis_index |
                                          | user_index     |
                                          +----------------+
```

**Tech Stack:**
- **Backend:** Python 3.x, FastAPI, uvicorn (async)
- **Database:** Elasticsearch 8.17
- **NLP:** sentence-transformers (`all-MiniLM-L6-v2`) for semantic scoring
- **Financial Data:** yfinance (Yahoo Finance API)
- **News:** NewsAPI.org (100 articles/query, free tier)
- **AI:** OpenRouter API routing to GPT-4o-mini
- **Frontend:** Vanilla HTML/JS, Tailwind CSS, Chart.js, marked.js

---

## Data Pipeline: How a Search Works

When a user searches for a company, the system follows a **three-tier lookup strategy**:

```
User searches "Microsoft"
        |
        v
+-- 1. Memory Cache (instant) --------> HIT? --> Return cached response
|                                                  (flag: source=database)
|       MISS
|        |
+-- 2. Elasticsearch (fast) ----------> HIT? --> Rebuild response from 3 indices
|                                                  (company + news + analysis)
|       MISS
|        |
+-- 3. Live API Pipeline (slow) ------> Fetch yfinance + NewsAPI + AI
                                         Save to ES + memory cache
                                         Return fresh response
```

The key code for this lives in `get_supplier_data()`:

```python
@app.get("/fetch_supplier_data")
async def get_supplier_data(company_name, ticker):
    # Step 1: Check in-memory cache
    cached = cache_get(ticker)
    if cached:
        response = dict(cached)
        response["source"] = "database"
        return response

    # Step 2: Check Elasticsearch
    es_doc = es_get_company(ticker)
    if es_doc:
        # Rebuild full response from all 3 ES indices...
        return final_response

    # Step 3: Complete cache miss — fetch everything live
    final_response = await _fetch_live_supplier_data(company_name, ticker)
    ai_result = await _run_ai_analysis(final_response)
    final_response["ai_analysis"] = ai_result

    # Save to ES + memory cache for future lookups
    cache_set(ticker, final_response)
    await save_to_databases(final_response)
    return final_response
```

When a company comes from the database, the frontend shows an **"UPDATE DATA"** button so the user can force-refresh with live data if needed.

---

## Semantic News Scoring - The NLP Engine

This is the core intelligence layer. Instead of just showing "news about Microsoft", we **quantify how risky each article is** using cosine similarity against a reference risk embedding.

### How It Works

1. **Reference embedding:** At startup, we encode a risk-signal reference text into a 384-dimensional vector:

```python
REFERENCE_SIGNAL_TEXT = (
    "Major financial risk, bankruptcy, credit rating downgrade, operational disruption, "
    "supply chain failure, factory closure, legal lawsuit, regulatory fine, executive "
    "resignation, positive market dividend, stock upgrade."
)
reference_embedding = model.encode(REFERENCE_SIGNAL_TEXT)
```

2. **Article encoding:** Each news article's title + description is encoded into the same vector space:

```python
art_embedding = model.encode(f"{article['title']} {article['description']}")
```

3. **Cosine similarity:** We compute the similarity between the article and the reference:

```python
cos_score = util.cos_sim(art_embedding, reference_embedding).item()
```

This produces a score between 0 and 1:
- **0.00 - 0.15:** Irrelevant noise (filtered out)
- **0.15 - 0.20:** Low relevance (kept for smaller companies)
- **0.20 - 0.30:** Moderate risk signal (amber)
- **0.30+:** High risk signal (red) — these penalize health scores

### Branching Search

We don't just search for the company name — we also search for **top executives by name**. This catches leadership news (resignations, lawsuits, statements) that might not mention the company:

```python
# Build: "Microsoft" OR "Satya Nadella" OR "Brad Smith"
query_parts = [f'"{company_name}"']
for officer in top_executives:
    query_parts.append(f'"{officer}"')
q_param = " OR ".join(query_parts)
```

The executive names come from yfinance's `companyOfficers` field — we extract the top 2 executives specifically for this branching search.

---

## Dynamic Thresholding

Mega-cap companies ($100B+) generate **enormous amounts of news noise** — routine earnings reports, analyst commentary, minor product announcements. A fixed threshold would either:
- Miss important signals for small companies (too strict), or
- Flood the screen with noise for Apple/Microsoft (too loose)

Our solution: **market-cap-adaptive thresholds**:

```python
market_cap = financial_data.get("metrics", {}).get("marketCap")
if market_cap and market_cap > 100_000_000_000:
    dynamic_threshold = 0.20   # Stricter for mega-caps
else:
    dynamic_threshold = 0.15   # More permissive for smaller companies
```

This means a score of 0.17 would be filtered OUT for Microsoft but kept IN for a mid-cap supplier — because for a smaller company, that signal is proportionally more significant.

---

## Health Score Mathematics

We compute two composite scores (0-100): **Short-Term Safety** (liquidity & shock resistance) and **Long-Term Safety** (solvency & geopolitical risk).

### Normalization Functions

Each raw financial metric is mapped to a 0-100 "health" value:

```python
def norm_cr(val):
    """Current Ratio: 0 -> 0, 1.0 -> 50, 2.0+ -> 100"""
    return max(0, min(100, (val / 2.0) * 100))

def norm_de(val):
    """Debt/Equity (yfinance returns as %): 0 -> 100, 100 -> 50, 200+ -> 0"""
    return max(0, min(100, 100 - (val / 2.0)))

def norm_beta(val):
    """Beta: 0.5 -> 100 (defensive), 1.5 -> 50, 2.5+ -> 0 (volatile)"""
    return max(0, min(100, 100 - ((val - 0.5) * 50)))
```

> **Important note on `norm_de`:** yfinance returns Debt-to-Equity as a **percentage** (e.g., 42.0 means 42%), not a ratio (0.42). An earlier version used `100 - (val * 50)` which meant any D/E above 2% scored zero — this was caught and fixed.

### Weighted Composite

```
Short-Term = weighted_avg(Current Ratio × 0.4, Quick Ratio × 0.4, Profit Margins × 0.2)
             - news_penalty (up to -30)

Long-Term  = weighted_avg(Debt/Equity × 0.5, Beta × 0.5)
             - geo_risk_penalty (up to -40)
             - news_penalty / 2 (residual impact)
```

If a metric is missing (some companies don't report quick ratio), the weights are **re-normalized** among available metrics rather than defaulting to zero.

### News Impact Penalty

Articles with semantic scores above 0.3 are counted as "high-risk signals":

```python
news_signals_count = sum(1 for sig in signals if sig.get("semantic_signal_score", 0) > 0.3)
news_pen = min(30, news_signals_count * 10)  # Cap at 30 points
```

This means 3+ high-risk articles will shave up to **30 points** off the short-term score and **15 points** off the long-term score.

### Geopolitical Risk Tiers

Long-term scores are penalized based on the company's headquarter country:

| Tier | Countries | Penalty |
|------|-----------|---------|
| Tier 1 (Safe) | US, EU, Japan, etc. | 0 |
| Tier 2 (Emerging) | Brazil, India, China, Mexico, South Africa | -10 |
| Tier 3 (Tax Haven) | Bermuda, Cayman Islands, Cyprus, etc. | -20 |
| Tier 4 (Conflict) | Russia, Iran, Syria, Ukraine, Yemen, Israel | -40 |

---

## Elasticsearch: Why We Use It & How Data is Stored

### Why Elasticsearch?

We chose Elasticsearch over a traditional SQL database for several reasons:

1. **Schema flexibility:** Financial data varies wildly between companies. ES handles sparse/missing fields naturally without NULL columns.
2. **Full-text search:** News articles benefit from ES's built-in text analysis (tokenization, relevance scoring) for future search features.
3. **Fast reads:** Document-oriented storage means we can retrieve a full company profile in a single GET — no JOINs across tables.
4. **Horizontal scaling:** If this grew beyond a hackathon, ES clusters scale without schema migrations.
5. **Kibana integration:** Free, built-in dashboarding for monitoring indexed data.

### Index Architecture

We use **4 separate indices**, each with a specific responsibility:

#### `company_index` — Financial Profile
Stores one document per company, keyed by ticker symbol.

```json
{
  "company_name": "Microsoft Corporation",
  "financial_data": {
    "currentRatio": 1.28,
    "quickRatio": 1.14,
    "profitMargins": 0.359,
    "debtToEquity": 42.15,
    "beta": 0.89,
    "country": "United States",
    "marketCap": 3145000000000,
    "shortRisk": 72,
    "longRisk": 85,
    "stockPrice": 420.50,
    "ceo": "Satya Nadella"
  }
}
```

#### `source_index` — News Articles
Stores individual news articles, linked to companies by ticker. Deduplicated by URL.

```json
{
  "related_ticker": "MSFT",
  "source_title": "Microsoft announces major Azure expansion",
  "source_author": "Reuters",
  "source_date": "2026-04-03T14:30:00Z",
  "source_body": "Microsoft Corp said on Thursday...",
  "source_url": "https://reuters.com/..."
}
```

#### `analysis_index` — AI Reports
Stores the full JSON output from the LLM analysis, with a timestamp.

```json
{
  "related_ticker": "MSFT",
  "report_date": "2026-04-04T10:15:00Z",
  "content": "{\"executive_summary\": \"...\", \"recommended_action\": \"...\", ...}",
  "summary": "Microsoft presents a strong supplier profile...",
  "sentiment_score": null
}
```

#### `user_index` — User Accounts
Stores login credentials and roles, keyed by username.

```json
{
  "username": "john",
  "password": "hashed_password",
  "full_name": "John Smith",
  "role": "buyer"
}
```

### Data Flow: How Documents Are Saved

When a company is fetched live, `save_to_databases()` writes to all 3 data indices:

```python
async def save_to_databases(final_json_data):
    # 1. Company profile -> company_index (flat format, keyed by ticker)
    es_save_company(ticker, company_name, financial_data, health_scores)

    # 2. News articles -> source_index (deduplicated by URL)
    await save_signals_to_es(ticker, relevant_signals)

    # 3. AI analysis -> analysis_index (full JSON as string)
    es.index(index=ANALYSIS_INDEX, document={
        "related_ticker": ticker.upper(),
        "report_date": datetime.utcnow().isoformat(),
        "content": json.dumps(ai_analysis),
        "summary": ai_analysis.get("executive_summary", ""),
    })
```

---

## DB-First Architecture: Shared Intelligence

A critical design decision: **any company analyzed by any user becomes instantly available to all users.**

When User A searches for "NVIDIA":
1. Live data is fetched from yfinance + NewsAPI
2. AI analysis is generated
3. Everything is saved to Elasticsearch

When User B searches for "NVIDIA" 5 minutes later:
1. ES lookup finds the data immediately
2. Full response is rebuilt from the 3 indices
3. **No API calls are made** — instant response

This creates a **collaborative intelligence pool** where the database grows richer over time. The "UPDATE DATA" button on the frontend bypasses the cache for users who want fresh data.

---

## News Resilience: The Fallback Chain

NewsAPI's free tier is limited to **100 requests per 24 hours**. When we hit the rate limit, we don't show an empty news tab — we fall back to cached articles:

```python
news_result = await fetch_news(company_name, top_executives, dynamic_threshold)

if "error" in news_result:
    # NewsAPI failed — try cached news from Elasticsearch
    cached_news = fetch_cached_news(ticker)
    if cached_news:
        relevant_signals = cached_news  # Seamless fallback
```

The `fetch_cached_news()` function loads from `source_index`:

```python
def fetch_cached_news(ticker):
    result = es.search(
        index=SOURCE_INDEX,
        body={
            "query": {"term": {"related_ticker": ticker.upper()}},
            "sort": [{"source_date": {"order": "desc"}}],
            "size": 50,
        },
    )
    # Each cached article gets a default semantic score of 0.25
    return [{"title": s["source_title"], ...} for s in hits]
```

This means the **first search** for a company populates the news cache, and all subsequent searches (even when rate-limited) will still have articles to display and analyze.

---

## AI Analysis Pipeline

### Initial Analysis

When a company is first loaded, the system automatically generates a comprehensive risk report by sending the **entire supplier dossier** to GPT-4o-mini via OpenRouter:

```python
system_prompt = (
    "You are a Senior Sourcing Buyer Risk Analyst at a Fortune 500 procurement department. "
    "You have been handed a full supplier dossier including live financial metrics "
    "and recent news signals..."
)
```

The LLM returns a structured JSON with 6 fields:

| Field | Purpose |
|-------|---------|
| `executive_summary` | 3-5 sentence verdict for busy executives |
| `recommended_action` | Single-line: Proceed / Proceed with conditions / Escalate / Avoid |
| `financial_deep_dive` | Metric-by-metric interpretation in rich markdown |
| `news_impact_analysis` | Each headline tied to specific financial risks |
| `risk_scenarios` | Optimistic / Base Case / Pessimistic scenarios |
| `dynamic_ui_config` | Chart configuration that the frontend renders automatically |

### Force Update (Diff-Aware)

When a user clicks "UPDATE DATA", the system fetches fresh data and runs a **comparison analysis**:

```python
system_prompt = (
    "Compare the NEW data with the PREVIOUS data and highlight all changes. "
    "Mention specific metric changes (e.g. 'Short-term score changed from X to Y')."
)
user_content = json.dumps({
    "previous_data": { "health_scores": old_data["health_scores"], ... },
    "new_data": fresh_data,
})
```

This produces a delta-focused report instead of a full re-analysis.

---

## Agentic Chat: LLM-Controlled UI

The chat panel isn't just a Q&A bot — it's an **agentic system** where the LLM can control the frontend UI through structured action objects.

### Available UI Actions

The LLM can return a `ui_action` (or `ui_actions` array) alongside its text response:

```json
{
  "reply_text": "Here's a comparison of the key liquidity metrics...",
  "ui_action": {
    "action": "append_new_chart",
    "target_tab": "tab-ai",
    "chart_config": {
      "type": "bar",
      "labels": ["Current Ratio", "Quick Ratio", "D/E Ratio"],
      "values": [1.28, 1.14, 42.15],
      "title": "Liquidity Snapshot"
    }
  }
}
```

| Action | What It Does |
|--------|-------------|
| `update_chart` | Replaces the main dynamic chart |
| `append_new_chart` | Adds a new chart to the AI tab |
| `switch_tab` | Changes the active tab (finance/news/AI) |
| `search_company` | Loads a different company entirely |
| `update_tab_content` | Appends HTML analysis to any tab |
| `highlight_risk` | Flashes the safety score indicators |

### Anti-Duplication

The frontend sends the titles of all currently visible charts to the LLM:

```javascript
body: JSON.stringify({
    question: question,
    context: currentRawData,
    existing_chart_titles: getExistingChartTitles()
})
```

The system prompt includes:
```
CHARTS ALREADY ON SCREEN: ["Liquidity Snapshot", "Risk Breakdown"]
Do NOT duplicate charts that already exist unless the user explicitly asks.
```

### Multi-Turn Context

The chat maintains conversation history for multi-turn context. The last 20 messages are sent with each request to keep the LLM aware of what's already been discussed:

```python
messages = [{"role": "system", "content": system_prompt}]
for msg in conversation_history[-20:]:
    messages.append({"role": msg["role"], "content": msg["content"]})
messages.append({"role": "user", "content": user_question})
```

---

## Authentication & Per-User History

### Login/Register Flow

Authentication uses Elasticsearch as the user store (no external auth service needed):

```
login.html --> POST /login --> ES user_index lookup
                               |
                         sessionStorage.setItem('user', {...})
                               |
                         redirect to /app (index.html)
```

### Per-User Search History

Search history is stored in **localStorage**, keyed by username, so it persists across sessions:

```javascript
function getUserHistoryKey() {
    return currentUser ? `history_${currentUser.username}` : 'history_guest';
}

function saveUserHistory() {
    localStorage.setItem(getUserHistoryKey(), JSON.stringify(searchHistory));
}
```

Each history entry stores the company name, ticker, timestamp, and average safety score (used for the colored indicator dot on the sidebar):

```javascript
searchHistory.unshift({
    company: "Microsoft",
    ticker: "MSFT",
    time: new Date(),
    score: 78  // Average of ST + LT safety scores
});
```

---

## Frontend Architecture

### Layout Structure

```
+------+---------------------------+----------------+
|      |     HEADER (Tabs)         |                |
| SIDE |---------------------------| RIGHT CHAT     |
| BAR  |     CONTENT AREA          | PANEL          |
|      |  (Finance/News/AI tabs)   | (Resizable)    |
|      |                           |                |
|      |---------------------------+                |
| USER |     BOTTOM CHAT BAR       |                |
+------+---------------------------+----------------+
```

### Score Visualization

Safety scores are color-coded using HSL:

```javascript
// score * 1.2 maps: 0 -> red (0deg), 50 -> yellow (60deg), 83+ -> green (100deg)
sbStCircle.style.color = `hsl(${score * 1.2}, 100%, 50%)`;
```

The company logo box gets a colored glow based on the average safety score:

```javascript
const avg = (shortTerm + longTerm) / 2;
const glowHue = avg * 1.2;
companyLogoBox.style.boxShadow = `0 0 12px hsla(${glowHue}, 100%, 45%, 0.4)`;
```

### Terminal Color Palette (Chart.js)

LLM-suggested chart colors are **ignored** — we enforce a strict terminal palette:

```javascript
const TERMINAL_COLORS = ['#0078D4', '#00CC6A', '#D13438', '#FFB900', '#8A2BE2', '#00BFFF', '#FF8C00'];

function getChartColors(labels) {
    return labels.map((label, i) => {
        const l = label.toLowerCase();
        if (l.includes('debt') || l.includes('risk')) return '#D13438';  // red
        if (l.includes('profit') || l.includes('cash')) return '#00CC6A'; // green
        return TERMINAL_COLORS[i % TERMINAL_COLORS.length];
    });
}
```

This ensures semantic color meaning: red for danger/debt metrics, green for healthy/profit metrics.

---

## API Reference

### Core Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Login page |
| `GET` | `/app` | Main terminal (requires session) |
| `POST` | `/login` | Authenticate user |
| `POST` | `/register` | Create new account |
| `GET` | `/fetch_supplier_data?company_name=X&ticker=Y` | **Main endpoint** — DB-first supplier lookup |
| `POST` | `/analyze_supplier_ai` | Trigger AI analysis manually |
| `POST` | `/force_update_supplier` | Bypass cache, fetch fresh data |
| `POST` | `/chat_ai` | Multi-turn agentic chat |
| `GET` | `/search_company?q=X` | Company autocomplete (Yahoo Finance) |

### CRUD / Admin Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/company/all` | List all companies |
| `GET` | `/source/all` | List all news articles |
| `GET` | `/analysis/all` | List all AI reports |
| `GET` | `/analysis/{ticker}` | AI reports for a ticker |
| `GET` | `/source/{ticker}` | News for a ticker |
| `POST` | `/company/add` | Add company manually |
| `DELETE` | `/company/delete-ticker?ticker=X` | Delete a company |
| `PUT` | `/company/update_financial_data/{ticker}` | Update financial data |
| `POST` | `/source/add?ticker=X` | Add a news source |
