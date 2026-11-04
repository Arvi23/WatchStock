"""Home-screen widgets. These degrade to empty results instead of erroring."""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter

from watchstock import config, ttl_cache
from watchstock.providers import yahoo
from watchstock.providers.yahoo import MarketDataError

router = APIRouter(prefix="/api/market", tags=["market"])
log = logging.getLogger(__name__)


async def _cached(key: str, ttl: float, produce: Callable[[], Any], empty: Any) -> Any:
    try:
        return await asyncio.to_thread(ttl_cache.get_or_set, key, ttl, produce)
    except MarketDataError as exc:
        log.warning("%s unavailable: %s", key, exc)
        return empty


@router.get("/indices")
async def indices() -> list[dict[str, Any]]:
    return await _cached("indices", config.INDICES_TTL_SECONDS, yahoo.fetch_indices, [])


@router.get("/news")
async def market_news() -> list[dict[str, Any]]:
    return await _cached("market_news", config.MARKET_NEWS_TTL_SECONDS, yahoo.fetch_market_news, [])


@router.get("/movers")
async def movers() -> dict[str, Any]:
    return await _cached(
        "movers", config.MOVERS_TTL_SECONDS, yahoo.fetch_movers, {"gainers": [], "losers": []}
    )
