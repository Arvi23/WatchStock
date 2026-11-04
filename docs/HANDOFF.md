# Handoff / progress log

Read this first. Update it at the end of every batch or before your context runs out.

## Context
- Owner: Spartacus (GitHub `Arvi23`). End user: his dad, on Windows, non-technical,
  manages a small portfolio. Owner delegated the project ("be in charge") and wants
  progress reported in batches. **Don't touch the owner's computer**. Ask him to test.
- Dev sandbox can't reach Yahoo, OpenRouter or CDNs (PyPI + npm work). Verify against
  fakes and Playwright screenshots. Live behaviour goes in "Needs live testing" below.
- The original review that motivated this plan: bugs list in the batch plan below.

## Batch plan

### Batch 1 — Foundation  *(branch `batch-1-foundation`, PR #1)* ✅
- [x] Split `main.py` (2,100 lines) into the `watchstock/` package
- [x] Remove accounts/login, admin CRUD endpoints, sentence-transformers, NewsAPI, Elasticsearch leftovers
- [x] Yahoo news via yfinance; all Yahoo access through `providers/yahoo.py` (search + screeners too)
- [x] Snapshot cache with TTL + `as_of`; never persist failures; stale fallback; provider calls off the event loop
- [x] AI analysis stored separately and requested by the UI after the data loads (search no longer blocks on the LLM)
- [x] uv packaging, one-click `start.bat`, bind 127.0.0.1, no auto-reload
- [x] pytest suite (40 tests) with fake providers, ruff, GitHub Actions CI (Ubuntu + Windows)
- [x] Frontend updated to the new API: no login, `api()` helper, REFRESH + "data Xm ago" label,
      errors shown as toasts, news cards escaped, marked link renderer fixed (pulled forward from batch 3)
- [x] `scripts/fake_server.py` for UI work without network

### Batch 2 — Correct numbers
- Analyst score: shrink toward 50 with few analysts instead of multiplying the score down
- Currency mismatch (`financialCurrency` ≠ `currency`, e.g. TSM) in FCF yield and similar ratios
- Dividend yield unit (Yahoo now returns percent): normalise in the provider
- Merge the overlapping "health" and "opportunity" scores into one explained system; geo-risk becomes a flag, not a penalty
- Valuation: loss-makers shouldn't skip P/E penalties; label the 52-week-low = "value" assumption
- One analysis prompt (the old "force update" used a shallower one); LLM judges news materiality; "what changed since last analysis"
- Chat: compact context, no duplicated question

### Batch 3 — Frontend cleanup
- Split `static/index.html` into `index.html` + `css/` + `js/` ES modules
- Vendor + pin Chart.js, marked, DOMPurify; sanitise LLM HTML; fix marked link renderer (broken in marked ≥13)
- Tailwind Play CDN → decide (D6)
- Show data age ("as of"), currency-aware formatting, simpler settings
- Drop the chat's HTML-injection UI action

### Batch 4 — Portfolio
- Holdings (ticker, shares, cost basis, currency), P/L, allocation by sector/country,
  concentration warnings, projected dividend income

### Batch 5 — Staying on top of it
- Morning digest of holdings (earnings / ex-dividend dates, big moves, insider buys, rating changes)
- Industry peer comparison; thesis tracking ("why I bought" checked against new data)

## Status
Batch 1 done. Next: batch 2. Start with the analyst score + dividend unit + currency
mismatch in `scoring.py`/`providers/yahoo.py`, updating `tests/test_scoring.py` as formulas change.

Batch 1 notes for the next agent:
- Scoring formulas are deliberately unchanged from the hackathon (except: no news penalty).
  `tests/test_scoring.py` pins current behaviour; batch 2 changes it on purpose.
- The chat still supports `update_tab_content` on the frontend (raw HTML). The backend
  prompt no longer offers it; remove the frontend handler in batch 3 with DOMPurify.
- The Tailwind Play CDN, Chart.js and marked still load from CDNs (unpinned). Batch 3.
  For screenshots in the sandbox: run `scripts/fake_server.py`, then `scripts/ui_smoke.js`
  (header explains how it serves CDN scripts from npm copies).
- The old hackathon DB (`watchstock.db` at repo root) is not migrated; the new DB is
  `data/watchstock.db`. Nothing in the old one is worth keeping.

## Needs live testing (owner, on Windows)
Batch 1:
- [ ] Fresh folder → double-click `start.bat`: uv installs, Python downloads, browser opens
- [ ] Home: indices, market news, movers populate (they use yfinance `Search`/`screen` now)
- [ ] Search "Microsoft" → dashboard loads; News tab shows real headlines with dates
- [ ] AI report generates automatically once a key is set; links inside it are clickable
- [ ] REFRESH works; "data Xm ago" label updates
- [ ] Watchlist star add/remove, prices show
- [ ] A European/BVB ticker (e.g. `SAP.DE`, `TLV.RO`) loads without errors (currency still shows `$`; known)

## Open questions for the owner
- Does dad hold only US stocks, or also BVB (.RO) / European ones? Decides how early
  currency support lands.
- Default LLM model id on OpenRouter: code uses `anthropic/claude-haiku-4-5`
  (worked during the hackathon); confirm or pick a newer one.
