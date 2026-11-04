"""Single-user state: watchlist and settings."""

import asyncio
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from watchstock import config, services, store
from watchstock.providers import yahoo

router = APIRouter(prefix="/api", tags=["personal"])


# ---------------------------------------------------------------- watchlist


class WatchlistAdd(BaseModel):
    ticker: str
    company_name: str = ""


@router.get("/watchlist")
async def watchlist() -> list[dict[str, Any]]:
    items = store.watchlist_items()
    if not items:
        return []
    quotes = await asyncio.to_thread(yahoo.fetch_quotes, [i["ticker"] for i in items])
    for item in items:
        quote = quotes.get(item["ticker"], {})
        item["price"] = quote.get("price")
        item["change_pct"] = quote.get("change_pct")
    return items


@router.post("/watchlist")
async def watchlist_add(body: WatchlistAdd) -> dict[str, bool]:
    store.watchlist_add(services.normalize_ticker(body.ticker), body.company_name.strip())
    return {"ok": True}


@router.delete("/watchlist/{ticker}")
async def watchlist_remove(ticker: str) -> dict[str, bool]:
    store.watchlist_remove(services.normalize_ticker(ticker))
    return {"ok": True}


# ----------------------------------------------------------------- settings


class SettingsUpdate(BaseModel):
    """Omitted fields are left unchanged. An empty string clears the setting."""

    llm_api_key: str | None = None
    llm_model: str | None = None


def _settings_view() -> dict[str, Any]:
    return {
        "llm_api_key_set": bool(store.get_setting("llm_api_key")),
        "llm_model": store.get_setting("llm_model", config.DEFAULT_LLM_MODEL),
        "default_llm_model": config.DEFAULT_LLM_MODEL,
    }


@router.get("/settings")
async def settings_get() -> dict[str, Any]:
    return _settings_view()


@router.put("/settings")
async def settings_put(body: SettingsUpdate) -> dict[str, Any]:
    for key, value in body.model_dump(exclude_none=True).items():
        store.set_setting(key, value.strip())
    return _settings_view()
