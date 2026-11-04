"""Portfolio: holdings CRUD and the computed overview."""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from watchstock import analysis, portfolio, services, store
from watchstock.i18n import tr
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
    result = portfolio.build_portfolio(holdings, quotes, info)
    for pos in result["positions"]:
        check = store.latest_thesis_check(pos["ticker"])
        pos["thesis_check"] = (
            {"status": check["status"], "created_at": check["created_at"]} if check else None
        )
    return result


@router.put("")
async def put_holding(body: HoldingIn) -> dict[str, Any]:
    """Add or replace a position. The ticker is validated (and its data cached) via Yahoo."""
    ticker = services.normalize_ticker(body.ticker)
    stock = await asyncio.to_thread(services.get_stock, ticker)  # MarketDataError -> 502
    currency = stock["financial_data"]["metrics"].get("currency")
    store.holding_upsert(ticker, body.shares, body.avg_cost, currency, body.notes.strip())
    return {"ok": True, "ticker": ticker, "company_name": stock["company_name"]}


@router.get("/{ticker}/thesis")
async def get_thesis_check(ticker: str) -> dict[str, Any] | None:
    return store.latest_thesis_check(services.normalize_ticker(ticker))


@router.post("/{ticker}/thesis")
async def run_thesis_check(ticker: str) -> dict[str, Any]:
    """LLM check of the position's "why I own it" note against current data."""
    ticker = services.normalize_ticker(ticker)
    holding = store.get_holding(ticker)
    if not holding:
        raise HTTPException(404, tr("{ticker} isn't in the portfolio.", ticker=ticker))
    if not holding["notes"].strip():
        raise HTTPException(422, tr("Add a 'why I own it' note to this position first (Edit)."))
    stock = await asyncio.to_thread(services.get_stock, ticker)
    return await asyncio.to_thread(analysis.run_thesis_check, stock, holding["notes"])


@router.delete("/{ticker}")
async def delete_holding(ticker: str) -> dict[str, bool]:
    store.holding_delete(services.normalize_ticker(ticker))
    return {"ok": True}
