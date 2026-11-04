# Architecture

```
Browser (static/index.html + static/js/*.js, plain scripts, no build step)
   │  JSON over /api/*
   ▼
watchstock/app.py            FastAPI app factory, error → 502 mapping, static files
   ├── routes/stocks.py      /api/search, /api/stocks/{t}, /api/stocks/{t}/analysis, /api/chat
   ├── routes/market.py      /api/market/{indices,news,movers}   (TTL-cached, degrade to empty)
   ├── routes/personal.py    /api/watchlist, /api/settings
   ├── routes/portfolio.py   /api/portfolio (GET overview, PUT/DELETE position, GET/POST {t}/thesis,
   │                         POST import/preview, import/commit)
   └── routes/today.py       /api/today (events for held + watched stocks)
        │
        ├── services.py      snapshot freshness: cache hit / live fetch / stale fallback
        ├── scoring.py       pure scoring functions → opportunity pillars + safety, with breakdowns
        ├── i18n.py          English/Romanian: tr(), num(), request language (cookie → ContextVar)
        ├── symbols.py       Yahoo ↔ TradingView ticker translation
        ├── importers.py     pure file parsing: Tradeville export, generic CSV → positions
        ├── portfolio.py     pure portfolio math: value, P/L, weights, allocation, flags, dividends
        ├── today.py         pure "Today" event builder (earnings, ex-div, moves, ratings, insider buys)
        ├── peers.py         pure industry-peer comparison (medians, relative %, table rows)
        ├── analysis.py      LLM prompts: report, chat, thesis check (compact context)
        ├── store.py         every SQL query
        ├── db.py            connection + migrations (PRAGMA user_version)
        ├── ttl_cache.py     in-memory TTL cache for widgets
        └── providers/       the only code that touches the network
             ├── yahoo.py       yfinance: profile, news, quotes, events, industry peers, search, screeners
             └── openrouter.py  chat completions
```

## Frontend (`static/`)

| file | role |
|---|---|
| `index.html` | markup only; loads CSS, vendored libs, then `js/*.js` in order |
| `css/tailwind.css` | precompiled Tailwind (generated from `tailwind.config.js`; `npm run build:css`) |
| `css/app.css` | fonts, theme variables, component styles, markdown (`.prose`) styles |
| `vendor/` | pinned Chart.js, marked, DOMPurify, Inter font (`npm run vendor`) |
| `js/i18n.js` | language (cookie `ws_lang`), Romanian dictionary, `t()`, `fmtN()`, auto-translation |
| `js/core.js` | `api()`, `esc()`, `renderMarkdown()`, money formatting, DOM handles, toast |
| `js/charts.js` | Chart.js helpers |
| `js/scores.js` | breakdown popover + safety modal |
| `js/settings.js` | settings modal |
| `js/home.js` | indices, market news, movers, watchlist, search history |
| `js/portfolio.js` | portfolio totals/table/doughnuts, add/edit modal, thesis check, "you own" line |
| `js/import.js` | import modal: read file, preview table, ticker fixes, replace/merge, commit |
| `js/today.js` | "Your stocks · next 2 weeks" panel |
| `js/dashboard.js` | sidebar, finance tab, metric cards, news tab |
| `js/analysis.js` | AI report rendering/requesting, JSON export |
| `js/chat.js` | chat panel and the UI actions the model may request |
| `js/search.js` | layout, autocomplete, `executeSearch`/`loadStock`, refresh, overlay |
| `js/main.js` | startup calls (runs last) |

Classic scripts share one global scope (see D11). `scripts/ui_smoke.js` drives the real
UI against `scripts/fake_server.py` in CI.

## Request flow: opening a stock

1. UI calls `GET /api/stocks/MSFT?name=...` (`refresh=true` from the REFRESH button).
2. `services.get_stock` loads the snapshot from SQLite. If it's younger than
   `config.SNAPSHOT_TTL_SECONDS` it's returned (`source: "cache"`).
3. Otherwise `build_snapshot` calls `yahoo.fetch_profile` + `yahoo.fetch_news`, runs
   `scoring.compute_all`, and saves the result (`source: "live"`).
   - Profile failure with no saved snapshot → `MarketDataError` → HTTP 502 with a message.
   - Profile failure with an old snapshot → old one returned with `stale: true` + warning.
   - News failure → empty news + warning; the rest still works.
4. Scores are computed from the snapshot at serve time (`services.with_scores`) in the request's
   language, and the latest stored AI report (if any) is attached as `ai_analysis`.
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
  "schema": 3,                       // services.SNAPSHOT_SCHEMA
  "peers": null | {"industry", "rows": [{"ticker","name","is_self", P/E...}], "medians", "relative", "peer_count"},
  "tradingview_symbol": "MSFT",      // e.g. "BVB:TLV" for TLV.RO
  "scores": {
    "quality" | "valuation" | "analyst" | "smart_money": {"score", "breakdown": [item]},
    "opportunity": {"score", "label", "color", "components": [{"key","label","score","weight"}]}
  },
  "safety": {"short_term": {"score","breakdown"}, "long_term": {...}, "flags": [str]},
  "risk_analysis": {...},            // plain-language red flags for the LLM
  // breakdown item: {"item": str, "score": 0-100|null, "weight": "25%"|null, "note": str|null}
  "ai_analysis": null | {"executive_summary", "verdict", ..., "changes_since_last", "model", "created_at"}
}
```

## Logging and startup

`python -m watchstock` logs to `data/watchstock.log` (rotating, 1 MB × 3), opens the
browser only once `/api/health` answers, and if an instance is already running just
opens the browser. See D10.

## Database (`data/watchstock.db`)

| table | purpose |
|---|---|
| `settings` | key/value: `llm_api_key`, `llm_model` |
| `watchlist` | tickers the user starred |
| `snapshots` | latest successful fetch per ticker (JSON) + `fetched_at` |
| `analyses` | every successful AI report (JSON) + model + `created_at` |
| `holdings` | one row per position: shares, avg cost, currency, notes ("why I own it") |
| `thesis_checks` | every thesis check (JSON: status, summary, supporting, against, watch) + the thesis text |
| `company_info` | light facts (name, sector, country, currency, dividend rate) for positions never opened; snapshots win |

## Testing

`tests/conftest.py` replaces provider functions with `FakeYahoo` / `FakeLLM` and points
the DB at a temp dir. `scripts/fake_server.py` runs the real app on the same fakes for
manual UI work and Playwright screenshots.
