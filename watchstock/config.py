"""Paths and tunables. Everything configurable lives here."""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"

HOST = "127.0.0.1"  # personal app: never listen on the LAN
PORT = int(os.environ.get("WATCHSTOCK_PORT", "8000"))

# A stock snapshot (fundamentals, analyst data, news, scores) is reused for this
# long before it is fetched again. Prices inside it age too; the UI shows `as_of`.
SNAPSHOT_TTL_SECONDS = 4 * 60 * 60

# Short-lived caches for the home screen widgets.
INDICES_TTL_SECONDS = 60
MARKET_NEWS_TTL_SECONDS = 5 * 60
MOVERS_TTL_SECONDS = 10 * 60

DEFAULT_LLM_MODEL = "anthropic/claude-haiku-4-5"
LLM_TIMEOUT_SECONDS = 90.0


def data_dir() -> Path:
    """Where the SQLite DB lives. Overridable for tests."""
    path = Path(os.environ.get("WATCHSTOCK_DATA_DIR", ROOT_DIR / "data"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "watchstock.db"
