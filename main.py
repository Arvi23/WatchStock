"""
Sourcing Buyer Terminal — Backend Server
=========================================
FastAPI application that serves as the backend for a supplier risk analysis platform.

Core capabilities:
- Fetches live financial data from Yahoo Finance (yfinance)
- Fetches and semantically scores news articles from NewsAPI
- Computes short-term and long-term health/safety scores
- Generates AI-powered due diligence reports via OpenRouter (GPT-4o-mini)
- Persists all data to Elasticsearch (company, sources, analyses)
- Provides a multi-turn agentic chat with UI control actions
- User authentication (login/register) with ES-backed user store
"""

import json
import os
from datetime import datetime
from urllib.parse import urlparse

import httpx
import uvicorn
import yfinance as yf
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sentence_transformers import SentenceTransformer, util

# =========================================================================
# INITIALIZATION
# =========================================================================

# Load environment variables from .env file
load_dotenv()

# Load the sentence-transformer model globally (used for semantic news scoring)
# This model encodes text into 384-dimensional vectors for cosine similarity
print("Loading semantic embeddings model... Please wait.")
try:
    model = SentenceTransformer("all-MiniLM-L6-v2")
except Exception as e:
    print(f"WARNING: Failed to load all-MiniLM-L6-v2: {e}")
    model = None

app = FastAPI(title="Supplier Data Ingestion API")

# Allow cross-origin requests from the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================================
# ELASTICSEARCH CONNECTION
# =========================================================================

ES_URL = os.getenv("ES_URL", "https://localhost:9200")
ES_USER = os.getenv("ES_USER", "elastic")
ES_PASS = os.getenv("ES_PASS", "")

# Index names matching the ES mappings defined in cipri.py
COMPANY_INDEX = "company_index"   # Flat company profile + financial metrics
SOURCE_INDEX = "source_index"     # News articles / signals per company
ANALYSIS_INDEX = "analysis_index" # AI-generated analysis reports
USER_INDEX = "user_index"         # User accounts for login/register

# Attempt to connect; fall back to in-memory cache if ES is unavailable
es = None
try:
    es_kwargs = {"verify_certs": False}
    if ES_USER and ES_PASS:
        es_kwargs["basic_auth"] = (ES_USER, ES_PASS)
    es = Elasticsearch(ES_URL, **es_kwargs)
    if es.ping():
        print(f"[ES] Connected to Elasticsearch at {ES_URL}")
    else:
        print(f"[ES] WARNING: Elasticsearch at {ES_URL} not reachable. Falling back to in-memory cache.")
        es = None
except Exception as e:
    print(f"[ES] WARNING: Could not connect to Elasticsearch: {e}. Falling back to in-memory cache.")
    es = None


@app.on_event("shutdown")
def app_shutdown():
    """Close the ES connection gracefully when the server shuts down."""
    if es:
        es.close()


# =========================================================================
# SEMANTIC SCORING SETUP
# =========================================================================

# Reference text representing high-risk/high-signal financial events.
# News articles are compared against this embedding via cosine similarity
# to produce a 0-1 "semantic signal score" indicating relevance.
REFERENCE_SIGNAL_TEXT = (
    "Major financial risk, bankruptcy, credit rating downgrade, operational disruption, "
    "supply chain failure, factory closure, legal lawsuit, regulatory fine, executive "
    "resignation, positive market dividend, stock upgrade."
)
reference_embedding = model.encode(REFERENCE_SIGNAL_TEXT) if model else None

# API keys loaded from environment
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")


# =========================================================================
# NEWS FETCHING & SEMANTIC ANALYSIS
# =========================================================================


async def fetch_news(company_name: str, officers: list, dynamic_threshold: float):
    """
    Fetch news articles from NewsAPI and score them semantically.

    Uses "branching search": queries by company name OR top executive names
    to catch leadership-related news. Each article is encoded with the
    sentence-transformer model and compared to the reference risk embedding
    via cosine similarity. Only articles above the dynamic_threshold are kept.

    Args:
        company_name: The company to search news for
        officers: List of executive names for branching search
        dynamic_threshold: Minimum cosine similarity score to keep an article
            (0.20 for mega-cap, 0.15 for regular companies)

    Returns:
        dict with "relevant_signals" list and "total_fetched" count, or "error"
    """
    if not NEWS_API_KEY:
        return {"error": "NEWS_API_KEY is not set in environment variables."}

    # Build branching search query: "Company Name" OR "CEO Name" OR ...
    query_parts = [f'"{company_name}"']
    for off in officers or []:
        if off:
            query_parts.append(f'"{off}"')

    q_param = " OR ".join(query_parts)

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": q_param,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 100,  # Max allowed on free tier
        "apiKey": NEWS_API_KEY,
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            articles = data.get("articles", [])
            total_fetched = len(articles)

            relevant_signals = []

            for art in articles:
                text = f"{art.get('title', '')} {art.get('description', '')}"

                semantic_signal_score = 0.0
                embedding_list = []

                if model and text.strip():
                    # Generate embedding for this article
                    art_embedding = model.encode(text)
                    embedding_list = art_embedding.tolist()

                    # Compute cosine similarity against the risk reference
                    cos_score = util.cos_sim(art_embedding, reference_embedding).item()
                    semantic_signal_score = float(cos_score)

                # Dynamic thresholding: only keep articles above the relevance threshold
                if semantic_signal_score >= dynamic_threshold:
                    relevant_signals.append(
                        {
                            "title": art.get("title"),
                            "url": art.get("url"),
                            "source": art.get("source", {}).get("name"),
                            "author": art.get("author"),
                            "publishedAt": art.get("publishedAt"),
                            "description": art.get("description"),
                            "semantic_signal_score": round(semantic_signal_score, 4),
                            "embedding": embedding_list[:5],  # First 5 dims for visual demo
                        }
                    )

            # Sort by relevance score (highest first)
            relevant_signals.sort(
                key=lambda x: x["semantic_signal_score"], reverse=True
            )

            return {
                "relevant_signals": relevant_signals,
                "total_fetched": total_fetched,
            }
        except Exception as e:
            return {"error": f"NewsAPI call failed: {str(e)}"}


def fetch_cached_news(ticker: str):
    """
    Fallback: load previously saved news from ES source_index.
    Used when NewsAPI is rate-limited or unavailable.
    """
    if not es or not ticker:
        return []
    try:
        result = es.search(
            index=SOURCE_INDEX,
            body={
                "query": {"term": {"related_ticker": ticker.upper()}},
                "sort": [{"source_date": {"order": "desc"}}],
                "size": 50,
            },
        )
        signals = []
        for hit in result["hits"]["hits"]:
            s = hit["_source"]
            signals.append({
                "title": s.get("source_title", ""),
                "url": s.get("source_url", ""),
                "source": s.get("source_author", ""),
                "description": s.get("source_body", ""),
                "publishedAt": s.get("source_date"),
                "semantic_signal_score": 0.25,  # Default score for cached articles
            })
        if signals:
            print(f"[ES] Loaded {len(signals)} cached news for {ticker}")
        return signals
    except Exception:
        return []


# =========================================================================
# FINANCIAL RISK CALCULATION
# =========================================================================


def calculate_financial_risk(metrics: dict):
    """
    Compute a simple risk score based on key financial ratios.
    Each missing or unhealthy metric adds risk points.
    Used for the pre-computed risk_analysis in financial_data.
    """
    risk_points = 0
    flags = []

    # 1. Current Ratio — measures ability to pay short-term obligations
    cr = metrics.get("currentRatio")
    if cr is None:
        risk_points += 1
        flags.append("currentRatio missing (1 pt)")
    elif cr < 1.0:
        risk_points += 2
        flags.append(f"currentRatio < 1.0 ({cr}) (2 pts)")
    elif 1.0 <= cr <= 1.2:
        risk_points += 1
        flags.append(f"currentRatio between 1.0 and 1.2 ({cr}) (1 pt)")

    # 2. Revenue Growth — negative growth signals declining business
    rg = metrics.get("revenueGrowth")
    if rg is None:
        risk_points += 1
        flags.append("revenueGrowth missing (1 pt)")
    elif rg < -0.05:
        risk_points += 2
        flags.append(f"revenueGrowth < -0.05 ({rg}) (2 pts)")
    elif -0.05 <= rg <= 0:
        risk_points += 1
        flags.append(f"revenueGrowth between -0.05 and 0 ({rg}) (1 pt)")

    # 3. Profit Margins — negative margins mean the company is losing money
    pm = metrics.get("profitMargins")
    if pm is None:
        risk_points += 1
        flags.append("profitMargins missing (1 pt)")
    elif pm < 0:
        risk_points += 2
        flags.append(f"profitMargins < 0 ({pm}) (2 pts)")
    elif 0 <= pm <= 0.05:
        risk_points += 1
        flags.append(f"profitMargins between 0 and 0.05 ({pm}) (1 pt)")

    # Severity classification
    if risk_points <= 1:
        severity = "Low"
    elif risk_points <= 3:
        severity = "Medium"
    else:
        severity = "High"

    return {
        "total_risk_points": risk_points,
        "severity_level": severity,
        "flags": flags,
    }


def fetch_financials(ticker: str):
    """
    Fetch live financial metrics from Yahoo Finance for a given ticker.
    Also extracts top executives for branching news search and key officers display.

    Returns a dict with: metrics, risk_analysis, top_executives, key_officers
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # Extract key financial health metrics (None if unavailable)
        metrics = {
            "currentRatio": info.get("currentRatio"),
            "quickRatio": info.get("quickRatio"),
            "revenueGrowth": info.get("revenueGrowth"),
            "profitMargins": info.get("profitMargins"),
            "debtToEquity": info.get("debtToEquity"),
            "freeCashflow": info.get("freeCashflow"),
            "marketCap": info.get("marketCap"),
            "beta": info.get("beta"),
            "country": info.get("country"),
            "website": info.get("website"),
            "currentPrice": info.get("currentPrice") or info.get("regularMarketPrice"),
        }

        # Calculate risk score from the metrics
        risk_analysis = calculate_financial_risk(metrics)

        # Extract executives: top 2 for news search, top 5 for display
        officers_data = info.get("companyOfficers", [])
        top_executives = []
        key_officers = []

        for index, officer in enumerate(officers_data):
            name = officer.get("name")
            title = officer.get("title")

            if name:
                if index < 2:
                    top_executives.append(name)
                if index < 5:
                    key_officers.append({"name": name, "title": title or "N/A"})

        return {
            "metrics": metrics,
            "risk_analysis": risk_analysis,
            "top_executives": top_executives,
            "key_officers": key_officers,
        }
    except Exception as e:
        return {
            "error": f"Could not fetch financial data for ticker {ticker}: {str(e)}"
        }


# Simple lookup map for common company names to tickers (fallback when no ticker provided)
COMPANY_TICKER_MAP = {
    "apple": "AAPL",
    "microsoft": "MSFT",
    "google": "GOOGL",
    "amazon": "AMZN",
    "tesla": "TSLA",
    "nvidia": "NVDA",
}


# =========================================================================
# HEALTH SCORE NORMALIZATION FUNCTIONS
# =========================================================================
# Each function maps a raw financial metric to a 0-100 "health" score.
# Higher = healthier. These are then combined into composite ST/LT scores.


def norm_cr(val):
    """Current Ratio: 0 → 0, 1.0 → 50, 2.0+ → 100"""
    return max(0, min(100, (val / 2.0) * 100))


def norm_qr(val):
    """Quick Ratio: 0 → 0, 0.75 → 50, 1.5+ → 100"""
    return max(0, min(100, (val / 1.5) * 100))


def norm_margin(val):
    """Profit Margins: 0 → 0, 0.125 → 50, 0.25+ → 100"""
    return max(0, min(100, (val / 0.25) * 100))


def norm_de(val):
    """Debt/Equity (yfinance returns as %): 0 → 100, 100 → 50, 200+ → 0"""
    return max(0, min(100, 100 - (val / 2.0)))


def norm_beta(val):
    """Beta (volatility): 0.5 → 100, 1.0 → 75, 1.5 → 50, 2.5+ → 0"""
    return max(0, min(100, 100 - ((val - 0.5) * 50)))


def get_geo_risk_penalty(country: str):
    """
    Apply a penalty to the long-term score based on geopolitical risk.
    Countries are grouped into risk tiers:
      Tier 1 (Safe): US, EU, Japan, etc. — no penalty
      Tier 2 (Emerging): Brazil, India, China — 10pt penalty
      Tier 3 (Tax Haven): Bermuda, Cayman Islands — 20pt penalty
      Tier 4 (Conflict): Russia, Iran, Syria — 40pt penalty
    """
    if not country:
        return 0, "No data"
    tier_3_tax_havens = [
        "Bermuda", "Cayman Islands", "British Virgin Islands", "Cyprus", "Bahamas",
    ]
    tier_4_conflict = ["Israel", "Ukraine", "Russia", "Iran", "Yemen", "Syria"]
    tier_2_emerging = ["Brazil", "India", "Mexico", "South Africa", "China"]

    if country in tier_4_conflict:
        return 40, "High geopolitical risk / Conflict"
    elif country in tier_3_tax_havens:
        return 20, "Tax Haven / Regulatory scrutiny"
    elif country in tier_2_emerging:
        return 10, "Emerging Market Volatility"
    return 0, "Safe/Tier 1"


def calculate_health_scores(metrics: dict, relevant_signals: list):
    """
    Compute Short-Term (ST) and Long-Term (LT) health scores (0-100).

    Short-Term: weighted average of Current Ratio, Quick Ratio, Profit Margins
      - Penalized by high-risk news signals (up to -30)

    Long-Term: weighted average of Debt/Equity, Beta
      - Penalized by geo-political risk and residual news impact

    Returns dict with "short_term" and "long_term", each containing
    a "score" and a "breakdown" list for the frontend modal.
    """
    cr = metrics.get("currentRatio")
    qr = metrics.get("quickRatio")
    pm = metrics.get("profitMargins")
    de = metrics.get("debtToEquity")
    beta = metrics.get("beta")
    country = metrics.get("country")

    # --- Short-Term Score ---
    st_components = []
    if cr is not None:
        st_components.append(("Current Ratio", norm_cr(cr), 0.4))
    if qr is not None:
        st_components.append(("Quick Ratio", norm_qr(qr), 0.4))
    if pm is not None:
        st_components.append(("Profit Margins", norm_margin(pm), 0.2))

    # Weighted average (re-normalize weights if some metrics are missing)
    total_st_weight = sum([w for _, _, w in st_components])
    if total_st_weight > 0:
        st_base = sum([s * (w / total_st_weight) for _, s, w in st_components])
    else:
        st_base = 50.0  # Default when no metrics available

    # --- Long-Term Score ---
    lt_components = []
    if de is not None:
        lt_components.append(("Debt to Equity", norm_de(de), 0.5))
    if beta is not None:
        lt_components.append(("Beta", norm_beta(beta), 0.5))

    total_lt_weight = sum([w for _, _, w in lt_components])
    if total_lt_weight > 0:
        lt_base = sum([s * (w / total_lt_weight) for _, s, w in lt_components])
    else:
        lt_base = 50.0

    # --- Penalties ---
    geo_pen, geo_reason = get_geo_risk_penalty(country)

    # Count high-risk news signals (score > 0.3 = strongly risk-correlated)
    news_signals_count = 0
    for sig in relevant_signals:
        if isinstance(sig, dict) and "error" not in sig:
            if sig.get("semantic_signal_score", 0) > 0.3:
                news_signals_count += 1

    # Cap news penalty at 30 points (3+ signals = max penalty)
    news_pen = min(30, news_signals_count * 10)

    # --- Final Scores ---
    st_final = max(0, st_base - news_pen)
    lt_final = max(0, lt_base - geo_pen - (news_pen / 2))

    # --- Build Breakdown (for the explainability modal in the frontend) ---
    st_breakdown = [
        {"item": "Short-Term Base (Liquidity & Margins)", "impact": round(st_base, 1)}
    ]
    if news_pen > 0:
        st_breakdown.append(
            {"item": f"News Penalty ({news_signals_count} high-risk signals)", "impact": -news_pen}
        )

    lt_breakdown = [
        {"item": "Long-Term Base (Solvency & Volatility)", "impact": round(lt_base, 1)}
    ]
    if geo_pen > 0:
        lt_breakdown.append(
            {"item": f"Geo-Risk Penalty ({geo_reason})", "impact": -geo_pen}
        )
    if news_pen > 0:
        lt_breakdown.append(
            {"item": "News Penalty (Residual Impact)", "impact": -(news_pen / 2)}
        )

    return {
        "short_term": {"score": round(st_final), "breakdown": st_breakdown},
        "long_term": {"score": round(lt_final), "breakdown": lt_breakdown},
    }


# =========================================================================
# AUTHENTICATION ENDPOINTS
# =========================================================================


@app.get("/")
async def root():
    """Serve the login page as the entry point."""
    return FileResponse("login.html")


@app.get("/app")
async def app_page():
    """Serve the main terminal dashboard (requires login via frontend session)."""
    return FileResponse("index.html")


@app.post("/login")
async def login(request: Request):
    """Authenticate a user against the ES user_index."""
    try:
        body = await request.json()
    except Exception:
        return {"success": False, "message": "Invalid JSON"}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        return {"success": False, "message": "Username and password required"}
    if not es:
        return {"success": False, "message": "Database not available"}
    try:
        result = es.get(index=USER_INDEX, id=username)
        if result["found"]:
            stored = result["_source"]
            if stored.get("password") == password:
                return {
                    "success": True,
                    "user": {
                        "username": stored["username"],
                        "full_name": stored.get("full_name", ""),
                        "role": stored.get("role", "user"),
                    },
                }
        return {"success": False, "message": "Invalid username or password"}
    except Exception:
        return {"success": False, "message": "Invalid username or password"}


@app.post("/register")
async def register(request: Request):
    """Register a new user account. Stores in ES user_index with 'buyer' role by default."""
    try:
        body = await request.json()
    except Exception:
        return {"success": False, "message": "Invalid JSON"}
    username = (body.get("username") or "").strip().lower()
    password = body.get("password") or ""
    full_name = (body.get("full_name") or "").strip()
    if not username or not password:
        return {"success": False, "message": "Username and password required"}
    if len(username) < 3:
        return {"success": False, "message": "Username must be at least 3 characters"}
    if len(password) < 4:
        return {"success": False, "message": "Password must be at least 4 characters"}
    if not es:
        return {"success": False, "message": "Database not available"}
    try:
        if es.exists(index=USER_INDEX, id=username):
            return {"success": False, "message": "Username already taken"}
        user_doc = {
            "username": username,
            "password": password,
            "full_name": full_name or username,
            "role": "buyer",
        }
        es.index(index=USER_INDEX, id=username, document=user_doc, refresh=True)
        return {"success": True, "message": "Account created successfully"}
    except Exception as e:
        return {"success": False, "message": f"Registration error: {str(e)}"}


# =========================================================================
# COMPANY AUTOCOMPLETE
# =========================================================================


@app.get("/search_company")
async def search_company(
    q: str = Query(..., description="Search term for company autocomplete (e.g. 'micro')"),
):
    """
    Autocomplete endpoint. Searches Yahoo Finance and returns the top 5 matching companies.
    Used by the frontend search input dropdown.
    """
    url = "https://query2.finance.yahoo.com/v1/finance/search"
    params = {"q": q}
    headers = {"User-Agent": "Mozilla/5.0"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            quotes = data.get("quotes", [])

            results = []
            for item in quotes:
                name = item.get("longname") or item.get("shortname")
                ticker = item.get("symbol")
                exchange = item.get("exchange")

                if name and ticker:
                    results.append({"name": name, "ticker": ticker, "exchange": exchange})
                if len(results) >= 5:
                    break

            return results
        except Exception as e:
            return {"error": f"Yahoo Finance Search failed: {str(e)}"}


# =========================================================================
# DATA PERSISTENCE: Elasticsearch + in-memory cache
# =========================================================================


async def save_to_databases(final_json_data: dict):
    """
    Save processed supplier data to all 3 Elasticsearch indices:
      1. company_index — flat financial profile
      2. source_index — news articles (deduplicated by URL)
      3. analysis_index — AI analysis report (full JSON)
    """
    company_name = final_json_data.get("company_name", "")
    ticker = final_json_data.get("ticker_used", "")
    relevant_signals = final_json_data.get("relevant_signals", [])
    financial_data = final_json_data.get("financial_data", {})
    health_scores = final_json_data.get("health_scores")
    ai_analysis = final_json_data.get("ai_analysis")

    # Save company profile to company_index
    es_save_company(ticker, company_name, financial_data, health_scores)

    # Save news articles to source_index
    await save_signals_to_es(ticker, relevant_signals)

    # Save AI analysis to analysis_index
    if es and ai_analysis and ticker:
        try:
            if isinstance(ai_analysis, dict):
                full_content = json.dumps(ai_analysis, default=str)
                summary = ai_analysis.get("executive_summary", "")
            else:
                full_content = str(ai_analysis)
                summary = ""
            analysis_doc = {
                "related_ticker": ticker.upper(),
                "report_date": datetime.utcnow().isoformat(),
                "content": full_content,
                "summary": summary,
                "sentiment_score": None,
            }
            es.index(index=ANALYSIS_INDEX, document=analysis_doc)
            print(f"[ES] Saved analysis for {ticker.upper()} to analysis_index")
        except Exception as e:
            print(f"[ES] Error saving analysis for {ticker}: {e}")


# In-memory cache: holds full supplier responses for fast serving within a session
supplier_cache = {}


def es_get_company(ticker: str):
    """Check if a company exists in Elasticsearch. Returns the flat ES document or None."""
    if not ticker or not es:
        return None
    tk = ticker.upper()
    try:
        result = es.get(index=COMPANY_INDEX, id=tk)
        if result.get("found"):
            print(f"[ES] Found {tk} in database")
            return result["_source"]
    except Exception:
        pass
    return None


def es_save_company(ticker: str, company_name: str, financial_data: dict, health_scores: dict):
    """
    Save company to ES in the flat format matching the company_index mapping.
    Extracts CEO name from key_officers list.
    """
    if not ticker or not es:
        return
    tk = ticker.upper()
    metrics = financial_data.get("metrics", {})
    key_officers = financial_data.get("key_officers", [])

    # Find the CEO from the officers list
    ceo = None
    for officer in key_officers:
        title = (officer.get("title") or "").lower()
        if "ceo" in title or "chief executive" in title:
            ceo = officer.get("name")
            break
    if not ceo and key_officers:
        ceo = key_officers[0].get("name")  # Fallback to first officer

    es_doc = {
        "company_name": company_name,
        "financial_data": {
            "currentRatio": metrics.get("currentRatio"),
            "quickRatio": metrics.get("quickRatio"),
            "profitMargins": metrics.get("profitMargins"),
            "debtToEquity": metrics.get("debtToEquity"),
            "beta": metrics.get("beta"),
            "country": metrics.get("country"),
            "marketCap": metrics.get("marketCap"),
            "shortRisk": health_scores.get("short_term", {}).get("score") if health_scores else None,
            "longRisk": health_scores.get("long_term", {}).get("score") if health_scores else None,
            "stockPrice": metrics.get("currentPrice"),
            "ceo": ceo,
        }
    }
    try:
        es.index(index=COMPANY_INDEX, id=tk, document=es_doc, refresh=True)
        print(f"[ES] Saved {tk} to company_index")
    except Exception as e:
        print(f"[ES] Error saving {tk}: {e}")


def cache_get(ticker: str):
    """Retrieve full supplier response from in-memory cache."""
    if not ticker:
        return None
    return supplier_cache.get(ticker.upper())


def cache_set(ticker: str, data: dict):
    """Store full supplier response in memory for fast serving."""
    if not ticker:
        return
    tk = ticker.upper()
    supplier_cache[tk] = data
    print(f"[Cache] Saved {tk} in memory ({len(supplier_cache)} entries)")


# =========================================================================
# CORE DATA PIPELINE
# =========================================================================


async def _fetch_live_supplier_data(company_name: str, ticker: str):
    """
    Internal: fetch fresh supplier data from live APIs.

    Pipeline:
      1. Fetch financial metrics from yfinance
      2. Determine dynamic threshold based on market cap (mega-cap = stricter)
      3. Fetch and score news from NewsAPI (with ES fallback if rate-limited)
      4. Calculate health scores from metrics + news penalties
      5. Build the final response object

    Returns the full supplier data dict (without AI analysis — that's added separately).
    """
    financial_data = {}
    top_executives = []

    if ticker:
        fin_data = fetch_financials(ticker)
        if "error" not in fin_data:
            top_executives = fin_data.pop("top_executives", [])
            financial_data = fin_data
        else:
            financial_data = fin_data
    else:
        financial_data = {
            "error": "Ticker was not provided and could not be resolved from the company name."
        }

    # Dynamic threshold: mega-cap companies (>$100B) get a stricter filter
    # because they generate more noise in news results
    market_cap = financial_data.get("metrics", {}).get("marketCap")
    if market_cap and market_cap > 100_000_000_000:
        dynamic_threshold = 0.20
        company_size_category = "Mega Cap (>100B)"
    else:
        dynamic_threshold = 0.15
        company_size_category = "Regular Cap (<100B)"

    # Fetch news articles and score them semantically
    news_result = await fetch_news(company_name, top_executives, dynamic_threshold)

    relevant_signals = []
    total_fetched = 0
    relevant_articles_found = 0

    if isinstance(news_result, dict) and "error" not in news_result:
        relevant_signals = news_result.get("relevant_signals", [])
        total_fetched = news_result.get("total_fetched", 0)
        relevant_articles_found = len(relevant_signals)
    elif isinstance(news_result, dict) and "error" in news_result:
        # NewsAPI failed (rate limit, etc.) — try cached news from ES
        cached_news = fetch_cached_news(ticker)
        if cached_news:
            relevant_signals = cached_news
            total_fetched = len(cached_news)
            relevant_articles_found = len(cached_news)
            print(f"[Fallback] Using {len(cached_news)} cached news articles for {ticker}")
        else:
            relevant_signals = [{"error": news_result["error"]}]

    # Calculate health scores (requires both metrics and news signals)
    health_scores = None
    company_domain = None
    if "error" not in financial_data:
        metrics = financial_data.get("metrics", {})
        health_scores = calculate_health_scores(metrics, relevant_signals)

        # Extract company domain from website URL for logo lookup
        raw_website = metrics.get("website")
        if raw_website:
            try:
                company_domain = urlparse(raw_website).netloc.replace("www.", "")
            except Exception:
                company_domain = None

    final_response = {
        "company_name": company_name,
        "ticker_used": ticker,
        "company_domain": company_domain,
        "health_scores": health_scores,
        "financial_data": financial_data,
        "signal_metadata": {
            "total_articles_fetched": total_fetched,
            "relevant_articles_found": relevant_articles_found,
            "dynamic_threshold_applied": dynamic_threshold,
            "company_size_category": company_size_category,
        },
        "relevant_signals": relevant_signals,
    }

    return final_response


# =========================================================================
# AI ANALYSIS (OpenRouter / GPT-4o-mini)
# =========================================================================


async def _run_ai_analysis(data: dict):
    """
    Send supplier data to OpenRouter LLM for a comprehensive risk analysis report.

    The LLM receives the full supplier dossier and returns a structured JSON with:
      - executive_summary: 3-5 sentence verdict
      - recommended_action: single-line procurement recommendation
      - financial_deep_dive: detailed metric-by-metric interpretation (markdown)
      - news_impact_analysis: each headline tied to financial risks (markdown)
      - risk_scenarios: optimistic / base / pessimistic scenarios (markdown)
      - dynamic_ui_config: chart configuration for frontend rendering
    """
    openrouter_api_key = OPENROUTER_API_KEY
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {openrouter_api_key}",
        "HTTP-Referer": "http://localhost:8000",
        "Content-Type": "application/json",
    }

    system_prompt = (
        "You are a Senior Sourcing Buyer Risk Analyst at a Fortune 500 procurement department. "
        "You have been handed a full supplier dossier including live financial metrics and recent news signals. "
        "Your job is to produce a DEEP, THOROUGH due diligence report that a procurement manager can act on.\n\n"

        "DATA AVAILABLE TO YOU:\n"
        "- `financial_data.metrics`: live ratios (currentRatio, quickRatio, profitMargins, debtToEquity, beta, marketCap, currentPrice, revenueGrowth)\n"
        "- `financial_data.key_officers`: leadership team\n"
        "- `financial_data.risk_analysis`: pre-computed risk flags\n"
        "- `health_scores`: short_term (liquidity & shock) and long_term (solvency & geo) scores 0-100\n"
        "- `relevant_signals`: news articles with semantic relevance scores — THESE ARE CRITICAL\n\n"

        "INSTRUCTIONS:\n"
        "1. DO NOT just list numbers. Interpret them. Explain what they MEAN for a buyer.\n"
        "2. Connect news headlines directly to financial vulnerabilities — this is the core of your value.\n"
        "3. Be specific: name metrics, cite headlines, quantify risks where possible.\n"
        "4. Write all markdown fields in rich markdown (use ##, **bold**, bullet lists, > blockquotes for key warnings).\n\n"

        "Return STRICT JSON with EXACTLY this structure (all fields required):\n"
        "{\n"
        '  "executive_summary": "3-5 sentence overview for a busy executive. Verdict on supplier health.",\n'
        '  "recommended_action": "Concrete single-sentence procurement recommendation (e.g. Proceed / Proceed with conditions / Escalate / Avoid).",\n'
        '  "financial_deep_dive": "Rich markdown. Analyse each available metric in context. Compare to industry norms. Explain what high/low values mean for supply continuity. Min 200 words.",\n'
        '  "news_impact_analysis": "Rich markdown. For each relevant news signal: cite the headline, explain the risk or opportunity it represents, and connect it to a specific financial metric. If no news, state why that itself may be a signal. Min 150 words.",\n'
        '  "risk_scenarios": "Rich markdown. Describe THREE scenarios: ## Optimistic, ## Base Case, ## Pessimistic. For each: 2-3 sentences on what drives it and the procurement implication.",\n'
        '  "dynamic_ui_config": {"chart_type": "bar", "labels": [...], "values": [...], "title": "..."}\n'
        "}\n\n"
        "For dynamic_ui_config: choose the 3-5 most telling metrics (use actual numeric values from the data). "
        "Prefer metrics that tell the most risk-relevant story together."
    )

    payload = {
        "model": "openai/gpt-4o-mini",
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(data, default=str)},
        ],
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            content_str = (
                result.get("choices", [{}])[0].get("message", {}).get("content", "")
            )
            try:
                return json.loads(content_str)
            except json.JSONDecodeError:
                return {
                    "error": "LLM response was not valid JSON.",
                    "raw": content_str,
                }
        except Exception as e:
            return {"error": f"OpenRouter API call failed: {str(e)}"}


# =========================================================================
# MAIN DATA ENDPOINT: DB-First Supplier Lookup
# =========================================================================


@app.get("/fetch_supplier_data")
async def get_supplier_data(
    company_name: str = Query(..., description="Company name to look up"),
    ticker: str = Query(None, description="Stock ticker (optional)"),
):
    """
    The primary endpoint for the frontend. Implements a DB-first strategy:

    1. Check in-memory cache → instant return if available
    2. Check Elasticsearch → rebuild response from all 3 indices (no API calls)
    3. Cache miss → fetch live from yfinance + NewsAPI, run AI analysis, save everything

    This means a company searched by ANY user is available to ALL users instantly
    from the database. The "UPDATE DATA" button triggers force_update_supplier instead.
    """
    if not ticker:
        ticker = COMPANY_TICKER_MAP.get(company_name.lower())

    # Step 1: Check in-memory cache (full response with AI, news, etc.)
    cached = cache_get(ticker)
    if cached:
        print(f"[Memory HIT] Returning cached data for {ticker}")
        response = dict(cached)
        response["source"] = "database"
        return response

    # Step 2: Check Elasticsearch — rebuild full response from all 3 indices
    es_doc = es_get_company(ticker)
    if es_doc:
        print(f"[ES HIT] Serving {ticker} entirely from database")
        fin = es_doc.get("financial_data", {})
        st_score = fin.get("shortRisk")
        lt_score = fin.get("longRisk")

        # Reconstruct health scores from stored values
        health_scores = None
        if st_score is not None and lt_score is not None:
            health_scores = {
                "short_term": {"score": round(st_score), "breakdown": [{"item": "From database", "impact": round(st_score)}]},
                "long_term": {"score": round(lt_score), "breakdown": [{"item": "From database", "impact": round(lt_score)}]},
            }

        # Load cached news from source_index
        cached_news = fetch_cached_news(ticker)

        # Load saved AI analysis from analysis_index (prefer full analysis over shallow updates)
        saved_analysis = None
        if es:
            try:
                ar = es.search(
                    index=ANALYSIS_INDEX,
                    body={
                        "query": {"term": {"related_ticker": ticker.upper()}},
                        "sort": [{"report_date": {"order": "desc"}}],
                        "size": 5,
                    },
                )
                for hit in ar["hits"]["hits"]:
                    content_raw = hit["_source"].get("content", "")
                    try:
                        parsed = json.loads(content_raw)
                        # Prefer the full analysis (has news_impact_analysis), not shallow "no changes" ones
                        if "news_impact_analysis" in parsed:
                            saved_analysis = parsed
                            break
                        # Keep as fallback if nothing better found
                        if saved_analysis is None:
                            saved_analysis = parsed
                    except (json.JSONDecodeError, TypeError):
                        if saved_analysis is None:
                            saved_analysis = {"executive_summary": hit["_source"].get("summary", content_raw)}
            except Exception:
                pass

        # Reconstruct key_officers from stored CEO name
        key_officers = []
        if fin.get("ceo"):
            key_officers = [{"name": fin["ceo"], "title": "CEO"}]

        # Build the full response matching the live pipeline's format
        final_response = {
            "company_name": es_doc.get("company_name", company_name),
            "ticker_used": ticker,
            "company_domain": None,
            "health_scores": health_scores,
            "financial_data": {
                "metrics": {
                    "currentRatio": fin.get("currentRatio"),
                    "quickRatio": fin.get("quickRatio"),
                    "profitMargins": fin.get("profitMargins"),
                    "debtToEquity": fin.get("debtToEquity"),
                    "beta": fin.get("beta"),
                    "country": fin.get("country"),
                    "marketCap": fin.get("marketCap"),
                    "currentPrice": fin.get("stockPrice"),
                },
                "key_officers": key_officers,
                "risk_analysis": {},
            },
            "signal_metadata": {
                "total_articles_fetched": len(cached_news),
                "relevant_articles_found": len(cached_news),
            },
            "relevant_signals": cached_news,
            "ai_analysis": saved_analysis,
            "source": "database",
        }
        cache_set(ticker, final_response)
        return final_response

    # Step 3: Complete cache miss — fetch everything live
    print(f"[MISS] Fetching live data for {ticker}")
    final_response = await _fetch_live_supplier_data(company_name, ticker)

    # Step 4: Run AI analysis
    ai_result = await _run_ai_analysis(final_response)
    final_response["ai_analysis"] = ai_result
    final_response["source"] = "live_api"

    # Step 5: Save to ES (all 3 indices) + memory cache
    cache_set(ticker, final_response)
    await save_to_databases(final_response)

    return final_response


# =========================================================================
# AI ANALYSIS ENDPOINTS
# =========================================================================


@app.post("/analyze_supplier_ai")
async def analyze_supplier_ai(request: Request):
    """Manually trigger AI analysis on supplier data (used by the Analyze button)."""
    try:
        data = await request.json()
    except Exception:
        return {"error": "Invalid JSON format."}

    return await _run_ai_analysis(data)


@app.post("/force_update_supplier")
async def force_update_supplier(request: Request):
    """
    Force bypass cache: fetch fresh live data, compare with previous data,
    and generate a diff-aware AI analysis highlighting what changed.
    """
    try:
        body = await request.json()
    except Exception:
        return {"error": "Invalid JSON format."}

    company_name = body.get("company_name", "")
    ticker = body.get("ticker", "")

    if not ticker:
        return {"error": "Ticker is required for force update."}

    # Get old data from cache for comparison
    old_data = cache_get(ticker)

    # Fetch fresh live data
    fresh_data = await _fetch_live_supplier_data(company_name, ticker)

    # Build diff-aware AI prompt
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "http://localhost:8000",
        "Content-Type": "application/json",
    }

    if old_data:
        # Comparison mode: highlight what changed since last analysis
        system_prompt = (
            "You are a Sourcing Buyer Risk Analyst performing a DATA UPDATE. "
            "Compare the NEW data with the PREVIOUS data and highlight all changes. "
            "Mention specific metric changes (e.g. 'Short-term score changed from X to Y because...'). "
            "If there are new news signals, highlight them. "
            "If no significant changes, say 'No significant changes since last analysis'. "
            'Return STRICT JSON: {"executive_summary": "text with diff highlights", '
            '"recommended_action": "updated action", "changes_detected": true/false, '
            '"dynamic_ui_config": {"chart_type": "bar", "labels": [...], "values": [...], "title": "..."}}'
        )
        user_content = json.dumps(
            {
                "previous_data": {
                    "health_scores": old_data.get("health_scores"),
                    "signal_metadata": old_data.get("signal_metadata"),
                    "ai_analysis": old_data.get("ai_analysis"),
                },
                "new_data": fresh_data,
            },
            default=str,
        )
    else:
        # No previous data — run a standard analysis
        system_prompt = (
            "You are an expert Sourcing Buyer Risk Analyst. Analyze the supplier data provided. "
            'Return STRICT JSON: {"executive_summary": "...", "recommended_action": "...", '
            '"dynamic_ui_config": {"chart_type": "bar", "labels": [...], "values": [...], "title": "..."}}'
        )
        user_content = json.dumps(fresh_data, default=str)

    payload = {
        "model": "openai/gpt-4o-mini",
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }

    ai_result = {}
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            content_str = (
                result.get("choices", [{}])[0].get("message", {}).get("content", "")
            )
            try:
                ai_result = json.loads(content_str)
            except json.JSONDecodeError:
                ai_result = {"error": "Invalid JSON from LLM", "raw": content_str}
        except Exception as e:
            ai_result = {"error": f"LLM API error: {str(e)}"}

    # Save updated data to cache + ES
    fresh_data["ai_analysis"] = ai_result
    fresh_data["source"] = "live_api"
    cache_set(ticker, fresh_data)
    await save_to_databases(fresh_data)

    return fresh_data


# =========================================================================
# AGENTIC CHAT: Multi-turn conversation with UI control
# =========================================================================


@app.post("/chat_ai")
async def chat_ai(request: Request):
    """
    Enhanced multi-turn chat with the AI analyst.

    The LLM has full context of the loaded company data and can:
      - Answer questions about the supplier
      - Generate/update charts (update_chart, append_new_chart)
      - Switch tabs (switch_tab)
      - Search for different companies (search_company)
      - Append additional analysis to tabs (update_tab_content)
      - Highlight risk indicators (highlight_risk)

    Supports conversation history for multi-turn context and
    anti-duplication rules (won't create charts that already exist on screen).
    """
    try:
        body = await request.json()
    except Exception:
        return {"error": "Invalid JSON format."}

    user_question = body.get("question", "")
    company_context = body.get("context", {})
    ai_analysis = body.get("ai_analysis", {})
    conversation_history = body.get("conversation_history", [])
    existing_chart_titles = body.get("existing_chart_titles", [])

    if not user_question:
        return {"error": "No question provided."}

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "http://localhost:8000",
        "Content-Type": "application/json",
    }

    # Build context string with full supplier data and current AI analysis
    context_str = json.dumps(
        {"supplier_data": company_context, "current_ai_analysis": ai_analysis},
        default=str,
    )

    system_prompt = (
        "You are an expert Sourcing Buyer Risk Analyst integrated into a live financial terminal. "
        "You have FULL control over the terminal UI. The user has loaded supplier data (financial metrics, risk scores, news). "
        "You are the SAME analyst who generated the AI Analysis visible on screen.\n\n"
        "CURRENT COMPANY CONTEXT:\n" + context_str + "\n\n"
        "INSTRUCTIONS:\n"
        "- Answer concisely and professionally using markdown.\n"
        "- You MUST return a JSON object with these fields:\n"
        '  1) "reply_text": your markdown answer\n'
        '  2) "ui_action": (null if not needed) one of these action objects:\n'
        '     - {"action": "update_chart", "chart_type": "bar|pie|line|doughnut|radar", "labels": [...], "values": [...], "title": "..."} — update the main chart\n'
        '     - {"action": "switch_tab", "tab": "tab-finance|tab-ai|tab-news"} — switch the active tab\n'
        '     - {"action": "search_company", "company_name": "...", "ticker": "..."} — load a different company\n'
        '     - {"action": "highlight_risk"} — flash the safety indicators\n'
        '     - {"action": "update_tab_content", "target_tab": "tab-ai|tab-finance|tab-news", "new_content": "<p>HTML</p>"} — append analysis to a tab\n'
        '     - {"action": "append_new_chart", "target_tab": "tab-ai", "chart_config": {"type": "...", "labels": [...], "values": [...], "title": "..."}} — add a new chart\n'
        "\nIMPORTANT RULES:\n"
        "- NEVER destroy or replace the initial AI analysis. Only APPEND new insights.\n"
        "- To UPDATE the existing chart, use update_chart. To ADD a new chart, use append_new_chart.\n"
        '- For multiple charts, return "ui_actions" (array) instead of "ui_action" (single).\n'
        "- For normal Q&A, set ui_action to null.\n"
        "- When asked about a different company, use search_company with the correct ticker.\n"
        "\nCHARTS ALREADY ON SCREEN: " + json.dumps(existing_chart_titles) + "\n"
        "Do NOT duplicate charts that already exist unless the user explicitly asks for a different visualization.\n"
    )

    # Build multi-turn message history (last 20 messages to stay within context limits)
    messages = [{"role": "system", "content": system_prompt}]
    for msg in conversation_history[-20:]:
        role = "user" if msg.get("role") == "user" else "assistant"
        messages.append({"role": role, "content": msg.get("content", "")})
    messages.append({"role": "user", "content": user_question})

    payload = {
        "model": "openai/gpt-4o-mini",
        "response_format": {"type": "json_object"},
        "messages": messages,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            content_str = (
                result.get("choices", [{}])[0].get("message", {}).get("content", "")
            )
            try:
                parsed = json.loads(content_str)
                # Support both singular ui_action and plural ui_actions (array of actions)
                return {
                    "reply_text": parsed.get("reply_text", content_str),
                    "ui_action": parsed.get("ui_action", None),
                    "ui_actions": parsed.get("ui_actions", None),
                }
            except json.JSONDecodeError:
                return {"reply_text": content_str, "ui_action": None}
        except Exception as e:
            return {"error": f"LLM API error: {str(e)}"}


# =========================================================================
# ELASTICSEARCH CRUD ENDPOINTS (merged from cipri.py)
# These provide direct CRUD access to the ES indices for admin/debug use.
# =========================================================================


@app.get("/analysis/all")
async def analysis_get_all():
    """List all AI analysis reports, sorted by date (newest first)."""
    if not es:
        return {"success": False, "message": "Elasticsearch not connected"}
    try:
        result = es.search(
            index=ANALYSIS_INDEX,
            body={"query": {"match_all": {}}, "sort": [{"report_date": {"order": "desc"}}], "size": 100},
        )
        return {
            "success": True,
            "total_found": result["hits"]["total"]["value"],
            "data": [hit["_source"] for hit in result["hits"]["hits"]],
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/analysis/{ticker}")
async def analysis_list_by_ticker(ticker: str):
    """List all AI analysis reports for a specific ticker."""
    if not es:
        return {"success": False, "message": "Elasticsearch not connected"}
    try:
        result = es.search(
            index=ANALYSIS_INDEX,
            body={
                "query": {"match": {"related_ticker": ticker.upper()}},
                "sort": [{"report_date": {"order": "desc"}}],
                "size": 100,
            },
        )
        return {
            "success": True,
            "ticker": ticker.upper(),
            "total_found": result["hits"]["total"]["value"],
            "data": [hit["_source"] for hit in result["hits"]["hits"]],
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/company/all")
async def company_get_all():
    """List all companies in the database."""
    if not es:
        return {
            "success": True,
            "count": len(supplier_cache),
            "data": list(supplier_cache.values()),
        }
    try:
        result = es.search(index=COMPANY_INDEX, size=1000)
        return {
            "success": True,
            "count": len(result["hits"]["hits"]),
            "data": [hit["_source"] for hit in result["hits"]["hits"]],
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/source/all")
async def source_get_all():
    """List all news sources/articles in the database."""
    if not es:
        return {"success": False, "message": "Elasticsearch not connected"}
    try:
        result = es.search(index=SOURCE_INDEX, size=1000)
        return {
            "success": True,
            "count": len(result["hits"]["hits"]),
            "data": [hit["_source"] for hit in result["hits"]["hits"]],
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/source/{ticker}")
async def source_list_by_ticker(ticker: str):
    """List all news sources for a specific ticker."""
    if not es:
        return {"success": False, "message": "Elasticsearch not connected"}
    try:
        result = es.search(
            index=SOURCE_INDEX,
            body={
                "query": {"match": {"related_ticker": ticker.upper()}},
                "sort": [{"source_date": {"order": "desc"}}],
                "size": 100,
            },
        )
        return {
            "success": True,
            "ticker": ticker.upper(),
            "total_found": result["hits"]["total"]["value"],
            "data": [hit["_source"] for hit in result["hits"]["hits"]],
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/company/ticker")
async def company_get_ticker(ticker: str = Query(...)):
    """Look up a specific company by ticker."""
    if not es:
        cached = supplier_cache.get(ticker.upper())
        return {"success": bool(cached), "message": str(cached) if cached else "Not found"}
    try:
        q = es.search(index=COMPANY_INDEX, body={"query": {"match": {"ticker": ticker.upper()}}})
        return {"success": True, "message": str(q)}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/company/get-financial-data")
async def company_get_financial_data(ticker: str = Query(...)):
    """Get only the financial_data field for a company."""
    if not es:
        cached = supplier_cache.get(ticker.upper())
        if cached:
            return {"success": True, "data": cached.get("financial_data", {})}
        return {"success": False, "message": "Not found in cache"}
    try:
        q = es.search(index=COMPANY_INDEX, body={"query": {"match": {"ticker": ticker.upper()}}})
        hits = q["hits"]["hits"]
        if hits:
            return {"success": True, "data": hits[0]["_source"].get("financial_data", {})}
        return {"success": False, "message": "Not found"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.delete("/company/delete-ticker")
async def company_delete_ticker(ticker: str = Query(...)):
    """Delete a company from the database by ticker."""
    if not es:
        removed = supplier_cache.pop(ticker.upper(), None)
        return {"success": bool(removed), "message": "Removed from cache" if removed else "Not found"}
    try:
        result = es.delete(index=COMPANY_INDEX, id=ticker.upper())
        return {"success": True, "message": str(result)}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.put("/company/update_financial_data/{ticker}")
async def company_update_financial_data(ticker: str, request: Request):
    """Update the financial_data field for an existing company."""
    try:
        metrics = await request.json()
    except Exception:
        return {"success": False, "message": "Invalid JSON"}
    tk = ticker.upper()
    if not es:
        if tk in supplier_cache:
            supplier_cache[tk]["financial_data"] = metrics
            return {"success": True, "ticker": tk, "result": "updated in cache"}
        return {"success": False, "message": "Not found in cache"}
    try:
        result = es.update(
            index=COMPANY_INDEX, id=tk,
            body={"doc": {"financial_data": metrics}},
            refresh=True,
        )
        return {"success": True, "ticker": tk, "result": result.get("result")}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/company/add")
async def company_add(request: Request):
    """Add a new company to the database (deduplicates by ticker)."""
    try:
        company_json = await request.json()
    except Exception:
        return {"success": False, "message": "Invalid JSON"}
    ticker = (company_json.get("ticker") or "").upper()
    if not ticker:
        return {"success": False, "message": "Field 'ticker' missing from JSON"}
    if not es:
        if ticker in supplier_cache:
            return {"success": True, "inserted": False, "message": "Duplicate entry detected. Entry skipped."}
        supplier_cache[ticker] = company_json
        return {"success": True, "inserted": True, "message": "Company added to cache.", "id": ticker}
    try:
        exists = es.exists(index=COMPANY_INDEX, id=ticker)
        if not exists:
            result = es.index(index=COMPANY_INDEX, id=ticker, document=company_json)
            return {"success": True, "inserted": True, "message": "Company indexed successfully.", "id": result["_id"]}
        return {"success": True, "inserted": False, "message": "Duplicate entry detected. Entry skipped."}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/source/add")
async def source_add(request: Request, ticker: str = Query(...)):
    """Add a news source/article to source_index (deduplicates by URL)."""
    try:
        source_json = await request.json()
    except Exception:
        return {"success": False, "message": "Invalid JSON"}
    if not es:
        return {"success": False, "message": "Elasticsearch not connected — sources require ES"}
    url = source_json.get("source_url")
    if not url:
        return {"success": False, "message": "Field 'source_url' missing from JSON"}
    try:
        result = es.search(
            index=SOURCE_INDEX,
            body={"query": {"match": {"source_url": url}}, "size": 1},
        )
        exists = result["hits"]["total"]["value"] > 0
        if not exists:
            source_json["related_ticker"] = ticker.upper()
            result = es.index(index=SOURCE_INDEX, document=source_json)
            return {"success": True, "inserted": True, "message": "Source indexed successfully.", "id": result["_id"]}
        return {"success": True, "inserted": False, "message": "Duplicate entry detected. Entry skipped."}
    except Exception as e:
        return {"success": False, "message": str(e)}


# =========================================================================
# STRATEGIC DUE DILIGENCE REPORT (standalone, from cipri.py)
# =========================================================================


async def generate_business_diligence(ticker: str, financial_data: dict, news_articles: list):
    """
    Generate a strategic due-diligence report via OpenRouter LLM.
    This is a standalone function (not exposed as endpoint) for generating
    deeper partner/acquirer-focused analysis. Produces a risk-opportunity matrix
    rather than a buy/sell recommendation.
    """
    financial_context = f"""
    CORPORATE STRUCTURE & STABILITY ({ticker.upper()}):
    - CEO: {financial_data.get("ceo")} | Country: {financial_data.get("country")}
    - Market Valuation: {financial_data.get("marketCap")}
    - Liquidity: Current Ratio: {financial_data.get("currentRatio")}, Quick Ratio: {financial_data.get("quickRatio")}
    - Profitability: {financial_data.get("profitMargins")}
    - Leverage: Debt-to-Equity: {financial_data.get("debtToEquity")}
    - Risk Profile: Short-term: {financial_data.get("shortRisk")}, Long-term: {financial_data.get("longRisk")}
    """
    news_context = "\n".join(
        [
            f"- [{a.get('source_date')}] {a.get('source_title')}: {str(a.get('content', ''))[:400]}"
            for a in news_articles[:12]
        ]
    )
    prompt = f"""
    Act as a Strategic Management Consultant. Analyze the provided data for {ticker.upper()}
    to assist a potential partner or acquirer in their due diligence process.
    DO NOT provide a Buy/Sell recommendation. Instead, provide a nuanced risk-opportunity matrix.

    {financial_context}

    OPERATIONAL NEWS & REPUTATION:
    {news_context}

    REPORT STRUCTURE:
    1. OPERATIONAL HEALTH: Interpret the liquidity and profit margins.
    2. STRATEGIC SYNERGY VS. FRICTION: Based on news, what are the benefits and headaches?
    3. RISK EXPOSURE: Contrast the numerical risk scores with news headlines.
    4. PROBABLE OUTCOMES: Three scenarios (Optimistic, Neutral, Pessimistic) for next 18 months.
    5. DATA VISUALIZATION: Suggest which financial metrics should be overlaid with news events.
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "http://localhost:8000",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            report = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {"success": True, "ticker": ticker.upper(), "diligence_report": report}
        except Exception as e:
            return {"success": False, "message": str(e)}


# =========================================================================
# NEWS SIGNAL PERSISTENCE
# =========================================================================


async def save_signals_to_es(ticker: str, signals: list):
    """
    Save news signals to ES source_index matching the mapping.
    Deduplicates by source_url to avoid storing the same article twice.
    """
    if not es:
        return
    for sig in signals:
        if isinstance(sig, dict) and "error" not in sig:
            try:
                source_url = sig.get("url", "")
                if not source_url:
                    continue
                # Check for duplicate by URL
                existing = es.search(
                    index=SOURCE_INDEX,
                    body={"query": {"term": {"source_url": source_url}}, "size": 1},
                )
                if existing["hits"]["total"]["value"] == 0:
                    doc = {
                        "related_ticker": ticker.upper(),
                        "source_title": sig.get("title", ""),
                        "source_author": sig.get("author"),
                        "source_date": sig.get("publishedAt"),
                        "source_body": sig.get("description", ""),
                        "source_url": source_url,
                    }
                    es.index(index=SOURCE_INDEX, document=doc)
            except Exception:
                pass  # Best effort — don't fail the whole pipeline for one article


# =========================================================================
# SERVER ENTRY POINT
# =========================================================================

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
