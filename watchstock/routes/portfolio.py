"""Portfolio: holdings CRUD and the computed overview."""

import asyncio
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from watchstock import portfolio, services, store
from watchstock.providers import yahoo

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class HoldingIn(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)
    shares: float = Field(gt=0)
    avg_cost: float = Field(ge=0)
    notes: str = Field(default="", max_length=2000)


@router.get("")
async def get_portfolio() -> dict[str, Any]:
    holdings = store.holdings_list()
    if not holdings:
        return portfolio.build_portfolio([], {}, {})
    tickers = [h["ticker"] for h in holdings]
    quotes = await asyncio.to_thread(yahoo.fetch_quotes, tickers)
    info = {}
    for t in tickers:
        snap = store.get_snapshot(t)
        info[t] = portfolio.info_from_snapshot(snap["data"] if snap else None)
    return portfolio.build_portfolio(holdings, quotes, info)


@router.put("")
async def put_holding(body: HoldingIn) -> dict[str, Any]:
    """Add or replace a position. The ticker is validated (and its data cached) via Yahoo."""
    ticker = services.normalize_ticker(body.ticker)
    stock = await asyncio.to_thread(services.get_stock, ticker)  # MarketDataError -> 502
    currency = stock["financial_data"]["metrics"].get("currency")
    store.holding_upsert(ticker, body.shares, body.avg_cost, currency, body.notes.strip())
    return {"ok": True, "ticker": ticker, "company_name": stock["company_name"]}


@router.delete("/{ticker}")
async def delete_holding(ticker: str) -> dict[str, bool]:
    store.holding_delete(services.normalize_ticker(ticker))
    return {"ok": True}
