# Architecture

```
Browser (static/index.html, vanilla JS)
   │  JSON over /api/*
   ▼
watchstock/app.py            FastAPI app factory, error → 502 mapping, static files
   ├── routes/stocks.py      /api/search, /api/stocks/{t}, /api/stocks/{t}/analysis, /api/chat
   ├── routes/market.py      /api/market/{indices,news,movers}   (TTL-cached, degrade to empty)
   └── routes/personal.py    /api/watchlist, /api/settings
        │
        ├── services.py      snapshot freshness: cache hit / live fetch / stale fallback
        ├── scoring.py       pure scoring functions → scores + breakdowns
        ├── analysis.py      LLM prompts: report + chat (compact context)
        ├── store.py         every SQL query
        ├── db.py            connection + migrations (PRAGMA user_version)
        ├── ttl_cache.py     in-memory TTL cache for widgets
        └── providers/       the only code that touches the network
             ├── yahoo.py       yfinance: profile, news, quotes, search, screeners
             └── openrouter.py  chat completions
```

## Request flow: opening a stock

1. UI calls `GET /api/stocks/MSFT?name=...` (`refresh=true` from the REFRESH button).
2. `services.get_stock` loads the snapshot from SQLite. If it's younger than
   `config.SNAPSHOT_TTL_SECONDS` it's returned (`source: "cache"`).
3. Otherwise `build_snapshot` calls `yahoo.fetch_profile` + `yahoo.fetch_news`, runs
   `scoring.compute_all`, and saves the result (`source: "live"`).
   - Profile failure with no saved snapshot → `MarketDataError` → HTTP 502 with a message.
   - Profile failure with an old snapshot → old one returned with `stale: true` + warning.
   - News failure → empty news + warning; the rest still works.
4. The latest stored AI report (if any) is attached as `ai_analysis`.
5. If there is none, the UI immediately calls `POST /api/stocks/MSFT/analysis`, which
   runs the LLM on the snapshot and stores the report only if it parsed correctly.

All provider calls run in worker threads (`asyncio.to_thread`), so a slow Yahoo or LLM
call never blocks other requests.

## Snapshot shape (`GET /api/stocks/{ticker}`)

```jsonc
{
  "ticker": "MSFT", "company_name": "...", "company_domain": "microsoft.com",
  "as_of": "2026-11-04T01:02:35+00:00", "source": "live|cache", "stale": false,
  "warnings": [],
  "financial_data": {
    "metrics": { ... Yahoo fields, see providers/yahoo._METRIC_FIELDS ... },
    "analyst_data": { ... }, "key_officers": [...],
    "upgrades_downgrades": [...], "insider_transactions": [...]
  },
  "news": [{"title", "url", "publisher", "published_at", "summary"}],
  "health_scores": {"short_term": {...}, "long_term": {...}},
  "scores": {"fundamental", "analyst", "valuation", "smart_money", "opportunity"},
  "risk_analysis": {...},
  "ai_analysis": null | {"executive_summary", "verdict", ..., "model", "created_at"}
}
```

## Database (`data/watchstock.db`)

| table | purpose |
|---|---|
| `settings` | key/value: `llm_api_key`, `llm_model` |
| `watchlist` | tickers the user starred |
| `snapshots` | latest successful fetch per ticker (JSON) + `fetched_at` |
| `analyses` | every successful AI report (JSON) + model + `created_at` |

## Testing

`tests/conftest.py` replaces provider functions with `FakeYahoo` / `FakeLLM` and points
the DB at a temp dir. `scripts/fake_server.py` runs the real app on the same fakes for
manual UI work and Playwright screenshots.
