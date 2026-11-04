"""FastAPI application factory."""

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from watchstock import __version__, config, db, i18n
from watchstock.providers.openrouter import LLMError
from watchstock.providers.yahoo import MarketDataError
from watchstock.routes import market, personal, portfolio, stocks, today

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    load_dotenv(config.ROOT_DIR / ".env")  # optional; dev convenience for OPENROUTER_API_KEY
    db.init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="WatchStock", version=__version__, lifespan=lifespan)

    # UI language (EN/RO switch) -> request-scoped language for backend text and the LLM.
    @app.middleware("http")
    async def _language(request: Request, call_next):
        token = i18n.set_lang(request.cookies.get("ws_lang"))
        try:
            return await call_next(request)
        finally:
            i18n.reset_lang(token)

    # Upstream failures become a clear 502 with a message the UI can show.
    @app.exception_handler(MarketDataError)
    async def _market_error(_req: Request, exc: MarketDataError) -> JSONResponse:
        log.warning("market data error: %s", exc)
        return JSONResponse({"detail": str(exc)}, status_code=502)

    @app.exception_handler(LLMError)
    async def _llm_error(_req: Request, exc: LLMError) -> JSONResponse:
        log.warning("llm error: %s", exc)
        return JSONResponse({"detail": str(exc)}, status_code=502)

    app.include_router(stocks.router)
    app.include_router(market.router)
    app.include_router(personal.router)
    app.include_router(portfolio.router)
    app.include_router(today.router)

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True, "version": __version__}

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(config.STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
    return app


app = create_app()
