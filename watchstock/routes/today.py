"""GET /api/today: earnings, ex-dividend dates, big moves, rating changes, insider buys
for the stocks the owner holds or watches."""

import asyncio
import logging
from datetime import date
from typing import Any

from fastapi import APIRouter

from watchstock import config, store, today, ttl_cache
from watchstock.providers import yahoo
from watchstock.providers.yahoo import MarketDataError

router = APIRouter(prefix="/api", tags=["today"])
log = logging.getLogger(__name__)

_MAX_PARALLEL = 4  # be gentle with Yahoo


def _tracked_tickers() -> dict[str, dict]:
    tickers: dict[str, dict] = {}
    for w in store.watchlist_items():
        tickers[w["ticker"]] = {"name": w["company_name"], "held": False}
    for h in store.holdings_list():
        snap = store.get_snapshot(h["ticker"])
        name = snap["data"].get("company_name") if snap else None
        tickers[h["ticker"]] = {
            "name": name or tickers.get(h["ticker"], {}).get("name"),
            "held": True,
        }
    return tickers


async def _events_for(ticker: str, gate: asyncio.Semaphore) -> dict:
    async with gate:
        try:
            return await asyncio.to_thread(
                ttl_cache.get_or_set,
                f"events:{ticker}",
                config.EVENTS_TTL_SECONDS,
                lambda: yahoo.fetch_events(ticker),
            )
        except MarketDataError as exc:
            log.warning("events unavailable for %s: %s", ticker, exc)
            return {}


@router.get("/today")
async def get_today() -> dict[str, Any]:
    tickers = _tracked_tickers()
    if not tickers:
        return {"events": [], "tracked": 0}
    gate = asyncio.Semaphore(_MAX_PARALLEL)
    quotes_task = asyncio.to_thread(yahoo.fetch_quotes, list(tickers))
    event_lists = await asyncio.gather(*(_events_for(t, gate) for t in tickers))
    quotes = await quotes_task
    events = dict(zip(tickers, event_lists, strict=True))
    return {
        "events": today.build_events(tickers, quotes, events, date.today()),
        "tracked": len(tickers),
    }
