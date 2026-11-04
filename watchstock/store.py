"""All SQL queries. Routes and services call these; nothing else writes SQL."""

import json
import os
from datetime import UTC, datetime
from typing import Any

from watchstock import db


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


# ---------------------------------------------------------------- settings

# Settings that may be read from the environment / .env when not set in the UI.
_ENV_FALLBACKS = {"llm_api_key": "OPENROUTER_API_KEY"}


def get_setting(key: str, default: str = "") -> str:
    with db.session() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row and row["value"]:
        return row["value"]
    env_name = _ENV_FALLBACKS.get(key)
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]
    return default


def set_setting(key: str, value: str) -> None:
    with db.session() as conn:
        if value:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
        else:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))


# --------------------------------------------------------------- watchlist


def watchlist_items() -> list[dict[str, Any]]:
    with db.session() as conn:
        rows = conn.execute(
            "SELECT ticker, company_name, added_at FROM watchlist ORDER BY added_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def watchlist_add(ticker: str, company_name: str) -> None:
    with db.session() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO watchlist (ticker, company_name, added_at) VALUES (?, ?, ?)",
            (ticker, company_name, utcnow_iso()),
        )


def watchlist_remove(ticker: str) -> None:
    with db.session() as conn:
        conn.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker,))


# --------------------------------------------------------------- snapshots


def get_snapshot(ticker: str) -> dict[str, Any] | None:
    """Return {"data": ..., "fetched_at": iso} or None."""
    with db.session() as conn:
        row = conn.execute(
            "SELECT data, fetched_at FROM snapshots WHERE ticker = ?", (ticker,)
        ).fetchone()
    if not row:
        return None
    return {"data": json.loads(row["data"]), "fetched_at": row["fetched_at"]}


def save_snapshot(ticker: str, company_name: str, data: dict[str, Any], fetched_at: str) -> None:
    with db.session() as conn:
        conn.execute(
            "INSERT INTO snapshots (ticker, company_name, data, fetched_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(ticker) DO UPDATE SET company_name = excluded.company_name, "
            "data = excluded.data, fetched_at = excluded.fetched_at",
            (ticker, company_name, json.dumps(data, default=str), fetched_at),
        )


# ---------------------------------------------------------------- analyses


def save_analysis(ticker: str, model: str, content: dict[str, Any]) -> dict[str, Any]:
    created_at = utcnow_iso()
    with db.session() as conn:
        conn.execute(
            "INSERT INTO analyses (ticker, created_at, model, content) VALUES (?, ?, ?, ?)",
            (ticker, created_at, model, json.dumps(content, default=str)),
        )
    return {**content, "created_at": created_at, "model": model}


def latest_analysis(ticker: str) -> dict[str, Any] | None:
    with db.session() as conn:
        row = conn.execute(
            "SELECT created_at, model, content FROM analyses WHERE ticker = ? "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (ticker,),
        ).fetchone()
    if not row:
        return None
    return {**json.loads(row["content"]), "created_at": row["created_at"], "model": row["model"]}
