"""SQLite connection handling and schema migrations.

Schema changes are appended to MIGRATIONS. The DB's `PRAGMA user_version` records
how many have been applied. Never edit a migration that has shipped; add a new one.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from watchstock import config

MIGRATIONS: list[str] = [
    # 1 — initial personal-use schema (replaces the hackathon multi-user schema)
    """
    CREATE TABLE settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE watchlist (
        ticker       TEXT PRIMARY KEY,
        company_name TEXT,
        added_at     TEXT NOT NULL
    );
    -- Latest successful data fetch per ticker (JSON). Served while fresh.
    CREATE TABLE snapshots (
        ticker       TEXT PRIMARY KEY,
        company_name TEXT,
        data         TEXT NOT NULL,
        fetched_at   TEXT NOT NULL
    );
    -- Every successful AI analysis, kept for history / "what changed".
    CREATE TABLE analyses (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker     TEXT NOT NULL,
        created_at TEXT NOT NULL,
        model      TEXT,
        content    TEXT NOT NULL
    );
    CREATE INDEX idx_analyses_ticker ON analyses (ticker, created_at);
    """,
    # 2 — portfolio: one row per position (the user maintains shares + average cost)
    """
    CREATE TABLE holdings (
        ticker     TEXT PRIMARY KEY,
        shares     REAL NOT NULL CHECK (shares > 0),
        avg_cost   REAL NOT NULL CHECK (avg_cost >= 0),
        currency   TEXT,
        notes      TEXT NOT NULL DEFAULT '',   -- "why I own it"; used for thesis checks later
        added_at   TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    # 3 — thesis checks: the LLM's verdict on whether "why I own it" still holds
    """
    CREATE TABLE thesis_checks (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker     TEXT NOT NULL,
        created_at TEXT NOT NULL,
        model      TEXT,
        thesis     TEXT NOT NULL,   -- the notes as they were when checked
        content    TEXT NOT NULL    -- JSON: status, summary, supporting, against, watch
    );
    CREATE INDEX idx_thesis_ticker ON thesis_checks (ticker, created_at);
    """,
]


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session() -> Iterator[sqlite3.Connection]:
    """Open a connection, commit on success, always close."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with session() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        for version, script in enumerate(MIGRATIONS, start=1):
            if version <= current:
                continue
            conn.executescript(script)
            conn.execute(f"PRAGMA user_version = {version}")
