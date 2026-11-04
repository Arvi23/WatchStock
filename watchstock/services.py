"""Stock snapshot orchestration: fetch -> score -> cache, with a freshness TTL.

A snapshot is everything the dashboard shows for one ticker except the AI report,
which is stored separately (see store.save_analysis) because it's slow and costs money.
"""

import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from watchstock import config, scoring, store
from watchstock.providers import yahoo
from watchstock.providers.yahoo import MarketDataError

log = logging.getLogger(__name__)


def normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()


def _age_seconds(fetched_at: str) -> float:
    return (datetime.now(UTC) - store.parse_iso(fetched_at)).total_seconds()


def _domain(website: str | None) -> str | None:
    if not website:
        return None
    netloc = urlparse(website if "://" in website else f"https://{website}").netloc
    return netloc.removeprefix("www.") or None


def build_snapshot(ticker: str, fallback_name: str = "") -> dict[str, Any]:
    """Fetch everything live. Raises MarketDataError if the core data is unavailable."""
    profile = yahoo.fetch_profile(ticker)
    warnings: list[str] = []
    try:
        news = yahoo.fetch_news(ticker)
    except MarketDataError as exc:
        log.warning("news fetch failed for %s: %s", ticker, exc)
        news, warnings = [], ["News could not be loaded."]

    metrics = profile["metrics"]
    return {
        "ticker": ticker,
        "company_name": profile.get("name") or fallback_name or ticker,
        "company_domain": _domain(metrics.get("website")),
        "as_of": store.utcnow_iso(),
        "financial_data": {
            "metrics": metrics,
            "analyst_data": profile["analyst_data"],
            "key_officers": profile["key_officers"],
            "upgrades_downgrades": profile["upgrades_downgrades"],
            "insider_transactions": profile["insider_transactions"],
        },
        "news": news,
        "warnings": warnings,
        **scoring.compute_all(metrics, profile["analyst_data"]),
    }


def get_stock(ticker: str, *, name: str = "", refresh: bool = False) -> dict[str, Any]:
    """Serve a fresh-enough snapshot, fetching live when needed.

    If a live fetch fails but an older snapshot exists, the old one is returned
    with `stale=True` and a warning instead of failing outright.
    """
    ticker = normalize_ticker(ticker)
    cached = store.get_snapshot(ticker)
    fresh_enough = cached and _age_seconds(cached["fetched_at"]) < config.SNAPSHOT_TTL_SECONDS

    if cached and fresh_enough and not refresh:
        stock = {**cached["data"], "source": "cache", "stale": False}
    else:
        try:
            stock = build_snapshot(ticker, name)
        except MarketDataError as exc:
            if not cached:
                raise
            log.warning("live fetch failed for %s, serving stale snapshot: %s", ticker, exc)
            stock = {
                **cached["data"],
                "source": "cache",
                "stale": True,
                "warnings": [f"Live data unavailable ({exc}). Showing the last saved data."],
            }
        else:
            store.save_snapshot(ticker, stock["company_name"], stock, stock["as_of"])
            stock = {**stock, "source": "live", "stale": False}

    stock["ai_analysis"] = store.latest_analysis(ticker)
    return stock
