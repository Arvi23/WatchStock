"""Portfolio: holdings CRUD and the computed overview."""

import asyncio
import logging
import threading
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from watchstock import analysis, importers, portfolio, services, store
from watchstock.i18n import tr
from watchstock.providers import yahoo
from watchstock.providers.yahoo import MarketDataError

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])
log = logging.getLogger(__name__)


class HoldingIn(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)
    shares: float = Field(gt=0)
    avg_cost: float = Field(ge=0)
    notes: str = Field(default="", max_length=2000)


@router.get("")
async def get_portfolio(background: BackgroundTasks) -> dict[str, Any]:
    holdings = store.holdings_list()
    if not holdings:
        return portfolio.build_portfolio([], {}, {})
    tickers = [h["ticker"] for h in holdings]
    quotes = await asyncio.to_thread(yahoo.fetch_quotes, tickers)
    info, missing = {}, []
    for t in tickers:
        # Full snapshot when the stock was opened; else light facts saved after an import.
        if snap := store.get_snapshot(t):
            info[t] = portfolio.info_from_snapshot(snap["data"])
        elif basics := store.get_company_info(t):
            info[t] = basics
        else:
            info[t] = {}
            missing.append(t)
    if missing:  # e.g. the app was closed before the post-import fetch finished
        background.add_task(_warm_company_info, missing)
    result = portfolio.build_portfolio(holdings, quotes, info)
    result["info_pending"] = len(missing)  # the UI re-polls while sector info is loading
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


# ------------------------------------------------------------------- import


class ImportPreviewIn(BaseModel):
    content: str = Field(min_length=1, max_length=2_000_000)
    # The user's corrections from the preview: file symbol -> ticker to use instead.
    overrides: dict[str, str] = Field(default_factory=dict, max_length=500)


def _resolve(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Check each ticker with one cheap quote lookup; fall back to the ISIN via Yahoo search."""
    quotes = yahoo.fetch_quotes(sorted({r["ticker"] for r in rows}))
    taken = {r["ticker"] for r in rows}
    for r in rows:
        if q := quotes.get(r["ticker"]):
            r.update(status="ok", price=q["price"])
            continue
        r.update(status="not_found", price=None)
        if not r.get("isin"):
            continue
        try:
            hits = yahoo.search(r["isin"], limit=3)
        except MarketDataError:
            hits = []
        for hit in hits:
            if hit["ticker"] in taken:  # never turn one position into a duplicate of another
                continue
            if q := yahoo.fetch_quotes([hit["ticker"]]).get(hit["ticker"]):
                r.update(
                    status="isin",
                    original_ticker=r["ticker"],
                    ticker=hit["ticker"],
                    price=q["price"],
                )
                taken.add(hit["ticker"])
                break
    return rows


@router.post("/import/preview")
async def import_preview(body: ImportPreviewIn) -> dict[str, Any]:
    """Parse an uploaded file and check every ticker. Nothing is saved."""
    try:
        parsed = importers.parse(body.content)
    except importers.ImportError_ as exc:
        raise HTTPException(422, tr(str(exc))) from exc
    for r in parsed["rows"]:
        if fixed := body.overrides.get(r["source_symbol"], "").strip():
            r["ticker"] = services.normalize_ticker(fixed)
            r["isin"] = ""  # the user chose the ticker; don't second-guess it via the ISIN
    rows = await asyncio.to_thread(_resolve, parsed["rows"])
    held = {h["ticker"] for h in store.holdings_list()}
    for r in rows:
        r["in_portfolio"] = r["ticker"] in held
    return {
        "format": parsed["format"],
        "rows": rows,
        "skipped": parsed["skipped"],
        "currently_held": len(held),
    }


class ImportRow(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)
    shares: float = Field(gt=0)
    avg_cost: float = Field(ge=0)
    currency: str | None = None


class ImportCommitIn(BaseModel):
    rows: list[ImportRow] = Field(min_length=1, max_length=500)
    mode: Literal["replace", "merge"]


_warming = threading.Lock()


def _warm_company_info(tickers: list[str]) -> None:
    """Fetch sector/country/dividend for positions that were never opened, one ticker at a
    time (kind to Yahoo). Only one warm-up runs at once; failures are retried on a later
    portfolio load and never saved."""
    if not _warming.acquire(blocking=False):
        return
    try:
        for t in tickers:
            if store.get_snapshot(t) or store.get_company_info(t):
                continue
            try:
                store.save_company_info(t, yahoo.fetch_company_basics(t))
            except MarketDataError as exc:
                log.warning("company info unavailable for %s: %s", t, exc)
    finally:
        _warming.release()


@router.post("/import/commit")
async def import_commit(body: ImportCommitIn, background: BackgroundTasks) -> dict[str, Any]:
    """Save imported positions. "replace" makes the file the whole portfolio; "merge" adds
    and updates. "Why I own it" notes of positions that stay are kept either way."""
    existing = {h["ticker"]: h for h in store.holdings_list()}
    rows = {}
    for r in body.rows:
        t = services.normalize_ticker(r.ticker)
        notes = existing.get(t, {}).get("notes", "")
        rows[t] = {"ticker": t, "shares": r.shares, "avg_cost": r.avg_cost,
                   "currency": r.currency, "notes": notes}  # fmt: skip
    if body.mode == "replace":
        store.replace_holdings(list(rows.values()))
    else:
        for r in rows.values():
            store.holding_upsert(r["ticker"], r["shares"], r["avg_cost"], r["currency"], r["notes"])
    background.add_task(_warm_company_info, list(rows))
    return {"ok": True, "imported": len(rows), "mode": body.mode}
