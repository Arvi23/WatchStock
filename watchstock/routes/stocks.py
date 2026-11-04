"""Search, stock snapshots, AI analysis and chat."""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from watchstock import analysis, services
from watchstock.providers import yahoo

router = APIRouter(prefix="/api", tags=["stocks"])


@router.get("/search")
async def search(q: str = Query(..., min_length=1)) -> list[dict[str, Any]]:
    return await asyncio.to_thread(yahoo.search, q)


@router.get("/stocks/{ticker}")
async def get_stock(ticker: str, name: str = "", refresh: bool = False) -> dict[str, Any]:
    return await asyncio.to_thread(services.get_stock, ticker, name=name, refresh=refresh)


@router.post("/stocks/{ticker}/analysis")
async def create_analysis(ticker: str) -> dict[str, Any]:
    """Run a new AI report on the current (cached or fresh) snapshot and store it."""
    stock = await asyncio.to_thread(services.get_stock, ticker)
    return await asyncio.to_thread(analysis.run_analysis, stock)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    stock: dict[str, Any] | None = None
    history: list[ChatMessage] = []
    existing_chart_titles: list[str] = []


@router.post("/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    if not req.question.strip():
        raise HTTPException(422, "Empty question")
    return await asyncio.to_thread(
        analysis.chat,
        req.question,
        req.stock,
        [m.model_dump() for m in req.history],
        req.existing_chart_titles,
    )
