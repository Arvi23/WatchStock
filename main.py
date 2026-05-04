"""
WatchStock — Backend Server
============================
FastAPI application serving a stock analysis terminal.

Core capabilities:
- Fetches live financial data from Yahoo Finance (yfinance)
- Fetches and semantically scores news articles from NewsAPI
- Computes short-term and long-term health/safety scores
- Generates AI-powered analysis reports via configurable LLM
- Persists all data to SQLite (companies, signals, analysis, users)
- Provides a multi-turn agentic chat with UI control actions
- User authentication (login/register) with local SQLite user store
"""

import asyncio
import json
import os
import sqlite3
import time
from datetime import datetime
from urllib.parse import urlparse

import httpx
import uvicorn
import yfinance as yf
from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sentence_transformers import SentenceTransformer, util

# =========================================================================
# INITIALIZATION
# =========================================================================

load_dotenv()

print("Loading semantic embeddings model... Please wait.")
try:
    model = SentenceTransformer("all-MiniLM-L6-v2")
except Exception as e:
    print(f"WARNING: Failed to load all-MiniLM-L6-v2: {e}")
    model = None

app = FastAPI(title="WatchStock API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================================
# DATABASE (SQLite)
# =========================================================================

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchstock.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            full_name TEXT,
            role TEXT DEFAULT 'user'
        );
        CREATE TABLE IF NOT EXISTS companies (
            ticker TEXT PRIMARY KEY,
            company_name TEXT,
            financial_data TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            title TEXT,
            author TEXT,
            published_at TEXT,
            description TEXT,
            url TEXT UNIQUE,
            semantic_score REAL
        );
        CREATE TABLE IF NOT EXISTS analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            report_date TEXT,
            content TEXT,
            summary TEXT
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.commit()
    conn.close()


init_db()


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_setting(key: str, default: str = "") -> str:
    """Read a value from the settings table, falling back to the provided default."""
    conn = get_db()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row and row["value"] else default
    except Exception:
        return default
    finally:
        conn.close()


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
    """
    news_key = get_setting("news_api_key", NEWS_API_KEY)
    if not news_key:
        return {"error": "News API key is not configured. Add it in Settings."}

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
        "pageSize": 100,
        "apiKey": news_key,
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
                    art_embedding = model.encode(text)
                    embedding_list = art_embedding.tolist()
                    cos_score = util.cos_sim(art_embedding, reference_embedding).item()
                    semantic_signal_score = float(cos_score)

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
                            "embedding": embedding_list[:5],
                        }
                    )

            relevant_signals.sort(
                key=lambda x: x["semantic_signal_score"], reverse=True
            )

            return {
                "relevant_signals": relevant_signals,
                "total_fetched": total_fetched,
            }
        except Exception as e:
            return {"error": f"NewsAPI call failed: {str(e)}"}


def db_get_signals(ticker: str):
    """Load previously saved news signals from the local database."""
    if not ticker:
        return []
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM signals WHERE ticker = ? ORDER BY published_at DESC LIMIT 50",
            (ticker.upper(),),
        ).fetchall()
        signals = []
        for row in rows:
            signals.append({
                "title": row["title"] or "",
                "url": row["url"] or "",
                "source": row["author"] or "",
                "description": row["description"] or "",
                "publishedAt": row["published_at"],
                "semantic_signal_score": row["semantic_score"] or 0.25,
            })
        if signals:
            print(f"[DB] Loaded {len(signals)} cached signals for {ticker}")
        return signals
    except Exception:
        return []
    finally:
        conn.close()


def db_save_signals(ticker: str, signals: list):
    """Save news signals to the database, deduplicating by URL."""
    if not signals:
        return
    conn = get_db()
    try:
        for sig in signals:
            if isinstance(sig, dict) and "error" not in sig:
                url = sig.get("url", "")
                if not url:
                    continue
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO signals
                           (ticker, title, author, published_at, description, url, semantic_score)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            ticker.upper(),
                            sig.get("title", ""),
                            sig.get("author"),
                            sig.get("publishedAt"),
                            sig.get("description", ""),
                            url,
                            sig.get("semantic_signal_score", 0.0),
                        ),
                    )
                except Exception:
                    pass
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


# =========================================================================
# FINANCIAL RISK CALCULATION
# =========================================================================


def calculate_financial_risk(metrics: dict):
    """
    Compute a simple risk score based on key financial ratios.
    Each missing or unhealthy metric adds risk points.
    """
    risk_points = 0
    flags = []

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
    Also extracts top executives for branching news search and display.
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

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

        risk_analysis = calculate_financial_risk(metrics)

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


def norm_cr(val):
    return max(0, min(100, (val / 2.0) * 100))


def norm_qr(val):
    return max(0, min(100, (val / 1.5) * 100))


def norm_margin(val):
    return max(0, min(100, (val / 0.25) * 100))


def norm_de(val):
    return max(0, min(100, 100 - (val / 2.0)))


def norm_beta(val):
    return max(0, min(100, 100 - ((val - 0.5) * 50)))


def get_geo_risk_penalty(country: str):
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
    """
    cr = metrics.get("currentRatio")
    qr = metrics.get("quickRatio")
    pm = metrics.get("profitMargins")
    de = metrics.get("debtToEquity")
    beta = metrics.get("beta")
    country = metrics.get("country", "")

    # --- Short-Term Score ---
    st_components = []
    if cr is not None:
        st_components.append(("Current Ratio", norm_cr(cr), 0.4))
    if qr is not None:
        st_components.append(("Quick Ratio", norm_qr(qr), 0.3))
    if pm is not None:
        st_components.append(("Profit Margins", norm_margin(pm), 0.3))

    total_st_weight = sum([w for _, _, w in st_components])
    if total_st_weight > 0:
        st_base = sum([s * (w / total_st_weight) for _, s, w in st_components])
    else:
        st_base = 50.0

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

    news_signals_count = 0
    for sig in relevant_signals:
        if isinstance(sig, dict) and "error" not in sig:
            if sig.get("semantic_signal_score", 0) > 0.3:
                news_signals_count += 1

    news_pen = min(30, news_signals_count * 10)

    # --- Final Scores ---
    st_final = max(0, st_base - news_pen)
    lt_final = max(0, lt_base - geo_pen - (news_pen / 2))

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
    return FileResponse("login.html")


@app.get("/app")
async def app_page():
    return FileResponse("index.html")


@app.post("/login")
async def login(request: Request):
    try:
        body = await request.json()
    except Exception:
        return {"success": False, "message": "Invalid JSON"}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        return {"success": False, "message": "Username and password required"}
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row and row["password"] == password:
            return {
                "success": True,
                "user": {
                    "username": row["username"],
                    "full_name": row["full_name"] or "",
                    "role": row["role"] or "user",
                },
            }
        return {"success": False, "message": "Invalid username or password"}
    except Exception:
        return {"success": False, "message": "Invalid username or password"}
    finally:
        conn.close()


@app.post("/register")
async def register(request: Request):
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
    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT username FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing:
            return {"success": False, "message": "Username already taken"}
        conn.execute(
            "INSERT INTO users (username, password, full_name, role) VALUES (?, ?, ?, ?)",
            (username, password, full_name or username, "user"),
        )
        conn.commit()
        return {"success": True, "message": "Account created successfully"}
    except Exception as e:
        return {"success": False, "message": f"Registration error: {str(e)}"}
    finally:
        conn.close()


# =========================================================================
# COMPANY AUTOCOMPLETE
# =========================================================================


@app.get("/search_company")
async def search_company(
    q: str = Query(..., description="Search term for company autocomplete"),
):
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
# DATA PERSISTENCE
# =========================================================================


def db_get_company(ticker: str):
    """Check if a company exists in the local database. Returns the stored doc or None."""
    if not ticker:
        return None
    tk = ticker.upper()
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM companies WHERE ticker = ?", (tk,)
        ).fetchone()
        if row:
            result = dict(row)
            result["financial_data"] = json.loads(result.get("financial_data") or "{}")
            print(f"[DB] Found {tk} in database")
            return result
        return None
    except Exception:
        return None
    finally:
        conn.close()


def db_save_company(ticker: str, company_name: str, financial_data: dict, health_scores: dict):
    """Save or update a company record in the local database."""
    if not ticker:
        return
    tk = ticker.upper()
    metrics = financial_data.get("metrics", {})
    key_officers = financial_data.get("key_officers", [])

    ceo = None
    for officer in key_officers:
        title = (officer.get("title") or "").lower()
        if "ceo" in title or "chief executive" in title:
            ceo = officer.get("name")
            break
    if not ceo and key_officers:
        ceo = key_officers[0].get("name")

    fin_doc = {
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

    conn = get_db()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO companies (ticker, company_name, financial_data, updated_at)
               VALUES (?, ?, ?, ?)""",
            (tk, company_name, json.dumps(fin_doc), datetime.utcnow().isoformat()),
        )
        conn.commit()
        print(f"[DB] Saved {tk} to companies")
    except Exception as e:
        print(f"[DB] Error saving {tk}: {e}")
    finally:
        conn.close()


async def save_to_databases(final_json_data: dict):
    """Save processed stock data to all tables: companies, signals, analysis."""
    company_name = final_json_data.get("company_name", "")
    ticker = final_json_data.get("ticker_used", "")
    relevant_signals = final_json_data.get("relevant_signals", [])
    financial_data = final_json_data.get("financial_data", {})
    health_scores = final_json_data.get("health_scores")
    ai_analysis = final_json_data.get("ai_analysis")

    db_save_company(ticker, company_name, financial_data, health_scores)
    db_save_signals(ticker, relevant_signals)

    if ai_analysis and ticker:
        if isinstance(ai_analysis, dict):
            full_content = json.dumps(ai_analysis, default=str)
            summary = ai_analysis.get("executive_summary", "")
        else:
            full_content = str(ai_analysis)
            summary = ""
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO analysis (ticker, report_date, content, summary) VALUES (?, ?, ?, ?)",
                (ticker.upper(), datetime.utcnow().isoformat(), full_content, summary),
            )
            conn.commit()
            print(f"[DB] Saved analysis for {ticker.upper()}")
        except Exception as e:
            print(f"[DB] Error saving analysis for {ticker}: {e}")
        finally:
            conn.close()


# In-memory cache: holds full responses for fast serving within a session
supplier_cache = {}


def cache_get(ticker: str):
    if not ticker:
        return None
    return supplier_cache.get(ticker.upper())


def cache_set(ticker: str, data: dict):
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
    Fetch fresh stock data from live APIs.

    Pipeline:
      1. Fetch financial metrics from yfinance
      2. Determine dynamic threshold based on market cap
      3. Fetch and score news from NewsAPI (with DB fallback if rate-limited)
      4. Calculate health scores
      5. Build the final response object
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

    market_cap = financial_data.get("metrics", {}).get("marketCap")
    if market_cap and market_cap > 100_000_000_000:
        dynamic_threshold = 0.20
        company_size_category = "Mega Cap (>100B)"
    else:
        dynamic_threshold = 0.15
        company_size_category = "Regular Cap (<100B)"

    news_result = await fetch_news(company_name, top_executives, dynamic_threshold)

    relevant_signals = []
    total_fetched = 0
    relevant_articles_found = 0

    if isinstance(news_result, dict) and "error" not in news_result:
        relevant_signals = news_result.get("relevant_signals", [])
        total_fetched = news_result.get("total_fetched", 0)
        relevant_articles_found = len(relevant_signals)
    elif isinstance(news_result, dict) and "error" in news_result:
        cached_signals = db_get_signals(ticker)
        if cached_signals:
            relevant_signals = cached_signals
            total_fetched = len(cached_signals)
            relevant_articles_found = len(cached_signals)
            print(f"[Fallback] Using {len(cached_signals)} cached signals for {ticker}")
        else:
            relevant_signals = [{"error": news_result["error"]}]

    health_scores = None
    company_domain = None
    if "error" not in financial_data:
        metrics = financial_data.get("metrics", {})
        health_scores = calculate_health_scores(metrics, relevant_signals)

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
# AI ANALYSIS (OpenRouter / configurable LLM)
# =========================================================================


async def _run_ai_analysis(data: dict):
    """
    Send stock data to the configured LLM for a comprehensive analysis report.

    Returns structured JSON with executive_summary, recommended_action,
    financial_deep_dive, news_impact_analysis, risk_scenarios, dynamic_ui_config.
    """
    api_key = get_setting("llm_api_key", OPENROUTER_API_KEY)
    llm_model = get_setting("llm_model", "openai/gpt-4o-mini")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
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
        "model": llm_model,
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
                return {"error": "LLM response was not valid JSON.", "raw": content_str}
        except Exception as e:
            return {"error": f"LLM API call failed: {str(e)}"}


# =========================================================================
# MAIN DATA ENDPOINT: DB-First Stock Lookup
# =========================================================================


@app.get("/fetch_supplier_data")
async def get_supplier_data(
    company_name: str = Query(..., description="Company name to look up"),
    ticker: str = Query(None, description="Stock ticker (optional)"),
):
    """
    Primary endpoint. Implements a DB-first strategy:
      1. Check in-memory cache → instant return if available
      2. Check local database → rebuild response (no API calls)
      3. Cache miss → fetch live from yfinance + NewsAPI, run AI analysis, save everything
    """
    if not ticker:
        ticker = COMPANY_TICKER_MAP.get(company_name.lower())

    # Step 1: In-memory cache
    cached = cache_get(ticker)
    if cached:
        print(f"[Memory HIT] Returning cached data for {ticker}")
        response = dict(cached)
        response["source"] = "database"
        return response

    # Step 2: Local database
    db_doc = db_get_company(ticker)
    if db_doc:
        print(f"[DB HIT] Serving {ticker} entirely from database")
        fin = db_doc.get("financial_data", {})
        st_score = fin.get("shortRisk")
        lt_score = fin.get("longRisk")

        health_scores = None
        if st_score is not None and lt_score is not None:
            health_scores = {
                "short_term": {"score": round(st_score), "breakdown": [{"item": "From database", "impact": round(st_score)}]},
                "long_term": {"score": round(lt_score), "breakdown": [{"item": "From database", "impact": round(lt_score)}]},
            }

        cached_signals = db_get_signals(ticker)

        # Load saved analysis (prefer full analysis over shallow updates)
        saved_analysis = None
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT content FROM analysis WHERE ticker = ? ORDER BY report_date DESC LIMIT 5",
                (ticker.upper(),),
            ).fetchall()
            for row in rows:
                try:
                    parsed = json.loads(row["content"])
                    if "news_impact_analysis" in parsed:
                        saved_analysis = parsed
                        break
                    if saved_analysis is None:
                        saved_analysis = parsed
                except (json.JSONDecodeError, TypeError):
                    if saved_analysis is None:
                        saved_analysis = {"executive_summary": row["content"]}
        except Exception:
            pass
        finally:
            conn.close()

        key_officers = []
        if fin.get("ceo"):
            key_officers = [{"name": fin["ceo"], "title": "CEO"}]

        final_response = {
            "company_name": db_doc.get("company_name", company_name),
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
                "total_articles_fetched": len(cached_signals),
                "relevant_articles_found": len(cached_signals),
            },
            "relevant_signals": cached_signals,
            "ai_analysis": saved_analysis,
            "source": "database",
        }
        cache_set(ticker, final_response)
        return final_response

    # Step 3: Complete miss — fetch everything live
    print(f"[MISS] Fetching live data for {ticker}")
    final_response = await _fetch_live_supplier_data(company_name, ticker)

    ai_result = await _run_ai_analysis(final_response)
    final_response["ai_analysis"] = ai_result
    final_response["source"] = "live_api"

    cache_set(ticker, final_response)
    await save_to_databases(final_response)

    return final_response


# =========================================================================
# AI ANALYSIS ENDPOINTS
# =========================================================================


@app.post("/analyze_supplier_ai")
async def analyze_supplier_ai(request: Request):
    """Manually trigger AI analysis on stock data."""
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

    old_data = cache_get(ticker)
    fresh_data = await _fetch_live_supplier_data(company_name, ticker)

    api_key = get_setting("llm_api_key", OPENROUTER_API_KEY)
    llm_model = get_setting("llm_model", "openai/gpt-4o-mini")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:8000",
        "Content-Type": "application/json",
    }

    if old_data:
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
        system_prompt = (
            "You are an expert Sourcing Buyer Risk Analyst. Analyze the supplier data provided. "
            'Return STRICT JSON: {"executive_summary": "...", "recommended_action": "...", '
            '"dynamic_ui_config": {"chart_type": "bar", "labels": [...], "values": [...], "title": "..."}}'
        )
        user_content = json.dumps(fresh_data, default=str)

    payload = {
        "model": llm_model,
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
    Multi-turn chat with the AI analyst.

    The LLM has full context of the loaded company data and can answer questions,
    generate/update charts, switch tabs, and load different companies.
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

    api_key = get_setting("llm_api_key", OPENROUTER_API_KEY)
    llm_model = get_setting("llm_model", "openai/gpt-4o-mini")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:8000",
        "Content-Type": "application/json",
    }

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
        '     - {"action": "update_chart", "chart_type": "bar|pie|line|doughnut|radar", "labels": [...], "values": [...], "title": "..."}\n'
        '     - {"action": "switch_tab", "tab": "tab-finance|tab-ai|tab-news"}\n'
        '     - {"action": "search_company", "company_name": "...", "ticker": "..."}\n'
        '     - {"action": "highlight_risk"}\n'
        '     - {"action": "update_tab_content", "target_tab": "tab-ai|tab-finance|tab-news", "new_content": "<p>HTML</p>"}\n'
        '     - {"action": "append_new_chart", "target_tab": "tab-ai", "chart_config": {"type": "...", "labels": [...], "values": [...], "title": "..."}}\n'
        "\nIMPORTANT RULES:\n"
        "- NEVER destroy or replace the initial AI analysis. Only APPEND new insights.\n"
        "- To UPDATE the existing chart, use update_chart. To ADD a new chart, use append_new_chart.\n"
        '- For multiple charts, return "ui_actions" (array) instead of "ui_action" (single).\n'
        "- For normal Q&A, set ui_action to null.\n"
        "- When asked about a different company, use search_company with the correct ticker.\n"
        "\nCHARTS ALREADY ON SCREEN: " + json.dumps(existing_chart_titles) + "\n"
        "Do NOT duplicate charts that already exist unless the user explicitly asks for a different visualization.\n"
    )

    messages = [{"role": "system", "content": system_prompt}]
    for msg in conversation_history[-20:]:
        role = "user" if msg.get("role") == "user" else "assistant"
        messages.append({"role": role, "content": msg.get("content", "")})
    messages.append({"role": "user", "content": user_question})

    payload = {
        "model": llm_model,
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
# SETTINGS ENDPOINTS
# =========================================================================


@app.get("/settings")
async def settings_get():
    """Return current settings. API key values are masked if set."""
    conn = get_db()
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        data = {row["key"]: row["value"] for row in rows}
        return {
            "llm_api_key": "***" if data.get("llm_api_key") else "",
            "llm_api_key_set": bool(data.get("llm_api_key")),
            "llm_model": data.get("llm_model") or "openai/gpt-4o-mini",
            "news_api_key": "***" if data.get("news_api_key") else "",
            "news_api_key_set": bool(data.get("news_api_key")),
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


@app.post("/settings")
async def settings_save(request: Request):
    """Persist settings. Ignores masked placeholder values ('***')."""
    try:
        body = await request.json()
    except Exception:
        return {"success": False, "message": "Invalid JSON"}
    allowed = {"llm_api_key", "llm_model", "news_api_key"}
    conn = get_db()
    try:
        for key, value in body.items():
            if key in allowed and value is not None and value != "***":
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (key, str(value)),
                )
        conn.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        conn.close()


# =========================================================================
# DATABASE CRUD ENDPOINTS (admin/debug)
# =========================================================================


@app.get("/analysis/all")
async def analysis_get_all():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM analysis ORDER BY report_date DESC LIMIT 100"
        ).fetchall()
        return {"success": True, "total_found": len(rows), "data": [dict(r) for r in rows]}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        conn.close()


@app.get("/analysis/{ticker}")
async def analysis_list_by_ticker(ticker: str):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM analysis WHERE ticker = ? ORDER BY report_date DESC LIMIT 100",
            (ticker.upper(),),
        ).fetchall()
        return {"success": True, "ticker": ticker.upper(), "total_found": len(rows), "data": [dict(r) for r in rows]}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        conn.close()


@app.get("/company/all")
async def company_get_all():
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM companies").fetchall()
        data = []
        for row in rows:
            r = dict(row)
            r["financial_data"] = json.loads(r.get("financial_data") or "{}")
            data.append(r)
        return {"success": True, "count": len(data), "data": data}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        conn.close()


@app.get("/source/all")
async def source_get_all():
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM signals LIMIT 1000").fetchall()
        return {"success": True, "count": len(rows), "data": [dict(r) for r in rows]}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        conn.close()


@app.get("/source/{ticker}")
async def source_list_by_ticker(ticker: str):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM signals WHERE ticker = ? ORDER BY published_at DESC LIMIT 100",
            (ticker.upper(),),
        ).fetchall()
        return {"success": True, "ticker": ticker.upper(), "total_found": len(rows), "data": [dict(r) for r in rows]}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        conn.close()


@app.get("/company/ticker")
async def company_get_ticker(ticker: str = Query(...)):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM companies WHERE ticker = ?", (ticker.upper(),)
        ).fetchone()
        if row:
            r = dict(row)
            r["financial_data"] = json.loads(r.get("financial_data") or "{}")
            return {"success": True, "message": str(r)}
        return {"success": False, "message": "Not found"}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        conn.close()


@app.get("/company/get-financial-data")
async def company_get_financial_data(ticker: str = Query(...)):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT financial_data FROM companies WHERE ticker = ?", (ticker.upper(),)
        ).fetchone()
        if row:
            return {"success": True, "data": json.loads(row["financial_data"] or "{}")}
        return {"success": False, "message": "Not found"}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        conn.close()


@app.delete("/company/delete-ticker")
async def company_delete_ticker(ticker: str = Query(...)):
    tk = ticker.upper()
    conn = get_db()
    try:
        conn.execute("DELETE FROM companies WHERE ticker = ?", (tk,))
        conn.commit()
        supplier_cache.pop(tk, None)
        return {"success": True, "message": f"Deleted {tk}"}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        conn.close()


@app.put("/company/update_financial_data/{ticker}")
async def company_update_financial_data(ticker: str, request: Request):
    try:
        metrics = await request.json()
    except Exception:
        return {"success": False, "message": "Invalid JSON"}
    tk = ticker.upper()
    conn = get_db()
    try:
        conn.execute(
            "UPDATE companies SET financial_data = ?, updated_at = ? WHERE ticker = ?",
            (json.dumps(metrics), datetime.utcnow().isoformat(), tk),
        )
        conn.commit()
        return {"success": True, "ticker": tk, "result": "updated"}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        conn.close()


@app.post("/company/add")
async def company_add(request: Request):
    try:
        company_json = await request.json()
    except Exception:
        return {"success": False, "message": "Invalid JSON"}
    ticker = (company_json.get("ticker") or "").upper()
    if not ticker:
        return {"success": False, "message": "Field 'ticker' missing from JSON"}
    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT ticker FROM companies WHERE ticker = ?", (ticker,)
        ).fetchone()
        if existing:
            return {"success": True, "inserted": False, "message": "Duplicate entry detected. Entry skipped."}
        conn.execute(
            "INSERT INTO companies (ticker, company_name, financial_data, updated_at) VALUES (?, ?, ?, ?)",
            (ticker, company_json.get("company_name", ""), json.dumps(company_json), datetime.utcnow().isoformat()),
        )
        conn.commit()
        return {"success": True, "inserted": True, "message": "Company added.", "id": ticker}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        conn.close()


@app.post("/source/add")
async def source_add(request: Request, ticker: str = Query(...)):
    try:
        source_json = await request.json()
    except Exception:
        return {"success": False, "message": "Invalid JSON"}
    url = source_json.get("source_url")
    if not url:
        return {"success": False, "message": "Field 'source_url' missing from JSON"}
    conn = get_db()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO signals (ticker, title, author, published_at, description, url, semantic_score)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                ticker.upper(),
                source_json.get("source_title", ""),
                source_json.get("source_author"),
                source_json.get("source_date"),
                source_json.get("source_body", ""),
                url,
                None,
            ),
        )
        conn.commit()
        return {"success": True, "inserted": True, "message": "Source added."}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        conn.close()


# =========================================================================
# MARKET MOVERS
# =========================================================================

_movers_cache: dict = {"data": None, "ts": 0.0}
MOVERS_TTL = 600  # seconds — refresh every 10 minutes


@app.get("/market_movers")
async def market_movers():
    """
    Return today's top 5 gainers and top 5 losers from Yahoo Finance screener.
    Result is cached for 10 minutes to avoid hammering the API.
    """
    now = time.time()
    if _movers_cache["data"] and (now - _movers_cache["ts"]) < MOVERS_TTL:
        return _movers_cache["data"]

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    def parse_quotes(resp) -> list:
        try:
            quotes = resp.json()["finance"]["result"][0]["quotes"]
            return [
                {
                    "ticker": q.get("symbol", ""),
                    "name": (q.get("shortName") or q.get("longName") or "")[:28],
                    "price": round(float(q.get("regularMarketPrice", 0)), 2),
                    "change_pct": round(float(q.get("regularMarketChangePercent", 0)), 2),
                }
                for q in quotes[:5]
            ]
        except Exception:
            return []

    async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
        try:
            base = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
            gr, lr = await asyncio.gather(
                client.get(base, params={"formatted": "false", "scrIds": "day_gainers", "count": 5}),
                client.get(base, params={"formatted": "false", "scrIds": "day_losers",  "count": 5}),
            )
            result = {"gainers": parse_quotes(gr), "losers": parse_quotes(lr)}
        except Exception as e:
            result = {"gainers": [], "losers": [], "error": str(e)}

    _movers_cache["data"] = result
    _movers_cache["ts"] = now
    return result


# =========================================================================
# SERVER ENTRY POINT
# =========================================================================

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
