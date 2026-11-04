"""Yahoo Finance access, via yfinance. The ONLY module that talks to Yahoo.

All functions are synchronous and may be slow (network). Call them from async
code with `asyncio.to_thread`. They raise `MarketDataError` when the data
can't be had, and return plain dicts/lists, never pandas objects.

Yahoo quirks handled here (keep this list current):
- `info` for an unknown ticker returns an almost-empty dict instead of an error.
- News comes in two shapes: `{"content": {...}}` (Ticker.get_news, 2025+) and the
  older flat shape (Search.news). `normalize_news_item` accepts both.
- Insider-transaction "Transaction" is often NaN; infer buy/sell from "Text".
- `dividendYield` switched from a fraction to a percent in 2025 (0.88 means 0.88%).
  We expose it as a fraction like every other ratio: dividendRate / price when
  both exist, else dividendYield / 100.
- For foreign companies listed in the US, statement values (freeCashflow,
  totalRevenue...) are in `financialCurrency` while price/marketCap are in
  `currency`. Both are exposed; scoring skips ratios that would mix them.
"""

import math
from datetime import UTC, datetime
from typing import Any

import yfinance as yf


class MarketDataError(Exception):
    """Market data could not be fetched (network, rate limit, unknown ticker)."""


INDEX_SYMBOLS = {"^GSPC": "S&P 500", "^IXIC": "NASDAQ", "^DJI": "DOW", "^VIX": "VIX"}

_METRIC_FIELDS = [
    # Liquidity
    "currentRatio", "quickRatio",
    # Profitability / growth
    "revenueGrowth", "profitMargins", "operatingMargins", "grossMargins",
    "earningsGrowth", "trailingEps", "forwardEps",
    # Solvency / cash
    "debtToEquity", "freeCashflow", "totalRevenue", "netIncomeToCommon",
    # Valuation
    "trailingPE", "forwardPE", "pegRatio", "priceToBook",
    "priceToSalesTrailingTwelveMonths", "enterpriseToEbitda",
    # Price / range
    "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "fiftyDayAverage", "twoHundredDayAverage",
    "marketCap", "beta",
    # Dividends
    "dividendYield", "dividendRate", "payoutRatio",
    # Ownership / short interest
    "shortPercentOfFloat", "shortRatio", "heldPercentInstitutions", "heldPercentInsiders",
    # Meta
    "country", "website", "sector", "industry", "industryKey", "currency", "financialCurrency",
    "exchange",
]  # fmt: skip

_ANALYST_FIELDS = [
    "recommendationMean", "recommendationKey", "numberOfAnalystOpinions",
    "targetMeanPrice", "targetHighPrice", "targetLowPrice", "targetMedianPrice",
]  # fmt: skip


def _clean(value: Any) -> Any:
    """NaN/inf -> None so the result is JSON-safe."""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip().lower() in ("", "nan", "none", "nat")


# ------------------------------------------------------------------ profile


def _dividend_yield(info: dict[str, Any], price: float | None) -> float | None:
    """Dividend yield as a fraction (0.0088 = 0.88%). See module docstring."""
    rate = _clean(info.get("dividendRate"))
    if rate and price:
        return round(rate / price, 6)
    raw = _clean(info.get("dividendYield"))
    return None if raw is None else round(raw / 100, 6)


def fetch_profile(ticker: str) -> dict[str, Any]:
    """Fundamentals, analyst consensus, officers, rating changes, insider trades."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
    except Exception as exc:  # yfinance raises many exception types
        raise MarketDataError(f"Yahoo Finance request failed for {ticker}: {exc}") from exc

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    name = info.get("longName") or info.get("shortName")
    if price is None and not name:
        raise MarketDataError(f"No data found for ticker {ticker!r}")

    metrics = {k: _clean(info.get(k)) for k in _METRIC_FIELDS}
    metrics["currentPrice"] = _clean(price)
    metrics["dividendYield"] = _dividend_yield(info, metrics["currentPrice"])
    analyst = {k: _clean(info.get(k)) for k in _ANALYST_FIELDS}

    officers = [
        {"name": o.get("name"), "title": o.get("title") or "N/A"}
        for o in (info.get("companyOfficers") or [])
        if o.get("name")
    ][:5]

    return {
        "name": name,
        "metrics": metrics,
        "analyst_data": analyst,
        "key_officers": officers,
        "upgrades_downgrades": _upgrades(stock),
        "insider_transactions": _insider_transactions(stock),
    }


def _upgrades(stock: "yf.Ticker", limit: int = 10) -> list[dict[str, Any]]:
    try:
        df = stock.upgrades_downgrades
    except Exception:
        return []
    if df is None or df.empty:
        return []
    out = []
    for date_idx, row in df.head(limit).iterrows():
        out.append(
            {
                "date": str(date_idx)[:10],
                "firm": str(row.get("Firm", "")),
                "from_grade": str(row.get("FromGrade", "")),
                "to_grade": str(row.get("ToGrade", "")),
                "action": str(row.get("Action", "")),
            }
        )
    return out


def _insider_transactions(stock: "yf.Ticker", limit: int = 10) -> list[dict[str, Any]]:
    try:
        df = stock.insider_transactions
    except Exception:
        return []
    if df is None or df.empty:
        return []
    out = []
    for _, row in df.head(limit).iterrows():
        text = "" if _is_blank(row.get("Text")) else str(row.get("Text")).strip()
        txn = row.get("Transaction")
        if _is_blank(txn):
            lower = text.lower()
            if any(k in lower for k in ("purchase", "acquired", "bought")):
                txn = "Purchase"
            elif any(k in lower for k in ("sale", "sold", "disposed", "disposition")):
                txn = "Sale"
            else:
                txn = ""
        shares, value = _clean(row.get("Shares")), _clean(row.get("Value"))
        out.append(
            {
                "date": str(row.get("Start Date", row.get("Date", "")))[:10],
                "insider": str(row.get("Insider", "")),
                "title": str(row.get("Position", row.get("Title", ""))),
                "transaction": str(txn),
                "text": text,
                "shares": int(shares) if shares is not None else None,
                "value": int(value) if value is not None else None,
            }
        )
    return out


# --------------------------------------------------------------------- news


def normalize_news_item(item: dict[str, Any]) -> dict[str, Any] | None:
    content = item.get("content") if isinstance(item.get("content"), dict) else item
    title = content.get("title")
    url = (
        (content.get("canonicalUrl") or {}).get("url")
        or (content.get("clickThroughUrl") or {}).get("url")
        or content.get("link")
    )
    if not title or not url:
        return None
    published = content.get("pubDate") or content.get("displayTime")
    if not published and content.get("providerPublishTime") is not None:
        published = datetime.fromtimestamp(content["providerPublishTime"], UTC).isoformat()
    return {
        "title": title,
        "url": url,
        "publisher": (content.get("provider") or {}).get("displayName")
        or content.get("publisher")
        or "",
        "published_at": published,
        "summary": content.get("summary") or content.get("description") or "",
    }


def fetch_news(ticker: str, count: int = 20) -> list[dict[str, Any]]:
    try:
        raw = yf.Ticker(ticker).get_news(count=count) or []
    except Exception as exc:
        raise MarketDataError(f"Could not fetch news for {ticker}: {exc}") from exc
    return [n for n in (normalize_news_item(i) for i in raw) if n]


def fetch_market_news(count: int = 10) -> list[dict[str, Any]]:
    try:
        raw = yf.Search("stock market earnings Wall Street", news_count=count).news
    except Exception as exc:
        raise MarketDataError(f"Could not fetch market news: {exc}") from exc
    return [n for n in (normalize_news_item(i) for i in raw or []) if n]


# -------------------------------------------------------------------- peers

# The few fields the peer table and relative valuation need.
PEER_FIELDS = [
    "trailingPE", "forwardPE", "pegRatio", "priceToBook", "profitMargins",
    "revenueGrowth", "marketCap", "currency",
]  # fmt: skip


def fetch_industry_peers(industry_key: str, limit: int = 8) -> list[dict[str, Any]]:
    """Largest US companies in a Yahoo industry (e.g. "software-infrastructure")."""
    try:
        df = yf.Industry(industry_key).top_companies
    except Exception as exc:
        raise MarketDataError(f"Could not load industry {industry_key!r}: {exc}") from exc
    if df is None or df.empty:
        return []
    return [
        {"ticker": str(symbol), "name": str(row.get("name") or symbol)}
        for symbol, row in df.head(limit).iterrows()
    ]


def fetch_key_metrics(ticker: str) -> dict[str, Any]:
    """Only `info` (one request), not the full profile: used for each peer."""
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as exc:
        raise MarketDataError(f"Yahoo Finance request failed for {ticker}: {exc}") from exc
    if not info.get("longName") and not info.get("shortName"):
        raise MarketDataError(f"No data found for ticker {ticker!r}")
    out = {k: _clean(info.get(k)) for k in PEER_FIELDS}
    out["name"] = info.get("shortName") or info.get("longName")
    return out


def fetch_company_basics(ticker: str) -> dict[str, Any]:
    """Name, sector, country, currency and dividend rate: one `info` request.

    Used to fill in portfolio allocation for imported positions without fetching the
    full stock profile (news, ratings, insiders, peers) for every holding.
    """
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as exc:
        raise MarketDataError(f"Yahoo Finance request failed for {ticker}: {exc}") from exc
    name = info.get("longName") or info.get("shortName")
    if not name:
        raise MarketDataError(f"No data found for ticker {ticker!r}")
    return {
        "name": name,
        "sector": info.get("sector"),
        "country": info.get("country"),
        "currency": info.get("currency"),
        "dividend_rate": _clean(info.get("dividendRate")),
    }


# ------------------------------------------------------------------- events


def _iso_date(value: Any) -> str | None:
    if value is None or _is_blank(value):
        return None
    try:
        return value.isoformat()[:10]
    except AttributeError:
        return str(value)[:10]


def fetch_events(ticker: str) -> dict[str, Any]:
    """Upcoming calendar dates plus recent rating changes and insider trades.

    `calendar` is a dict of `date` objects; "Earnings Date" is a list (a range when
    the date isn't confirmed yet). Missing pieces come back empty rather than failing.
    """
    try:
        stock = yf.Ticker(ticker)
    except Exception as exc:
        raise MarketDataError(f"Yahoo Finance request failed for {ticker}: {exc}") from exc
    try:
        cal = stock.calendar or {}
    except Exception:
        cal = {}
    earnings = cal.get("Earnings Date") or []
    if not isinstance(earnings, list | tuple):
        earnings = [earnings]
    return {
        "earnings_dates": [d for d in (_iso_date(e) for e in earnings) if d],
        "ex_dividend_date": _iso_date(cal.get("Ex-Dividend Date")),
        "dividend_date": _iso_date(cal.get("Dividend Date")),
        "upgrades_downgrades": _upgrades(stock),
        "insider_transactions": _insider_transactions(stock),
    }


# ------------------------------------------------------------------- quotes


def fetch_quotes(tickers: list[str]) -> dict[str, dict[str, Any]]:
    """Latest price and day change per ticker. Tickers that fail are omitted."""
    out = {}
    for ticker in tickers:
        try:
            fi = yf.Ticker(ticker).fast_info
            price = float(fi.last_price)
            prev = float(fi.previous_close)
        except Exception:
            continue
        if math.isnan(price):
            continue
        change = round((price - prev) / prev * 100, 2) if prev else 0.0
        try:
            currency = fi.currency
        except Exception:
            currency = None
        out[ticker] = {"price": round(price, 2), "change_pct": change, "currency": currency}
    return out


def fetch_indices() -> list[dict[str, Any]]:
    quotes = fetch_quotes(list(INDEX_SYMBOLS))
    return [
        {
            "name": name,
            "ticker": sym,
            "value": quotes[sym]["price"],
            "change_pct": quotes[sym]["change_pct"],
        }
        for sym, name in INDEX_SYMBOLS.items()
        if sym in quotes
    ]


# ------------------------------------------------------------ search/movers


def search(query: str, limit: int = 6) -> list[dict[str, Any]]:
    try:
        quotes = yf.Search(query, max_results=10, news_count=0).quotes
    except Exception as exc:
        raise MarketDataError(f"Yahoo search failed: {exc}") from exc
    results = []
    for q in quotes or []:
        name = q.get("longname") or q.get("shortname")
        if name and q.get("symbol"):
            results.append(
                {
                    "name": name,
                    "ticker": q["symbol"],
                    "exchange": q.get("exchDisp") or q.get("exchange"),
                    "type": q.get("quoteType"),
                }
            )
        if len(results) >= limit:
            break
    return results


def _screen(name: str, count: int) -> list[dict[str, Any]]:
    try:
        result = yf.screen(name, count=count)
    except Exception as exc:
        raise MarketDataError(f"Yahoo screener {name!r} failed: {exc}") from exc
    return [
        {
            "ticker": q.get("symbol", ""),
            "name": (q.get("shortName") or q.get("longName") or "")[:28],
            "price": round(float(q.get("regularMarketPrice") or 0), 2),
            "change_pct": round(float(q.get("regularMarketChangePercent") or 0), 2),
            "market_cap": q.get("marketCap"),
        }
        for q in (result or {}).get("quotes", [])[:count]
    ]


def fetch_movers(count: int = 20) -> dict[str, list[dict[str, Any]]]:
    return {"gainers": _screen("day_gainers", count), "losers": _screen("day_losers", count)}
