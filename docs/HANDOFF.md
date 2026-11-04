# Handoff / progress log

Read this first. Update it at the end of every batch or before your context runs out.

## Context
- Owner: Spartacus (GitHub `Arvi23`). End user: his dad, on Windows, non-technical,
  manages a small portfolio, **mostly US stocks**. Owner delegated the project ("be in
  charge") and wants progress reported in batches.
- **Delivery:** the owner wants every batch copied straight into his local folder
  `E:\WatchStock\WatchStock` (device file tools, `device_commit_files`) so he never has to run
  git. Copy tracked files only; never touch its `data\`, `.venv\` or `.git\`. Don't use his
  computer for anything else; ask him to test.
- **Merging:** the environment blocks agents from merging their own PRs. Open the PR, get
  CI green, and the owner merges (or stack the next batch on the open branch).
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

### Batch 2 — Correct numbers + owner feedback  *(branch `batch-2-numbers`, PR #2, stacked on #1)* ✅
- [x] Analyst score shrinks toward 50 with few analysts (was multiplied down)
- [x] Currency mismatch guard: FCF yield skipped when `financialCurrency` ≠ `currency`
- [x] Dividend yield normalised to a fraction in the provider (Yahoo now sends percent)
- [x] Scores restructured (D8): Opportunity = Quality/Valuation/Analyst/Smart money; Safety = Liquidity + Solvency;
      no metric counted twice; geo-risk is a flag; D/E skipped for financials; uniform breakdown items
- [x] Valuation: loss-makers scored low instead of skipped; 52-week position labelled "contrarian", weight 15%
- [x] Report prompt gets the previous report and returns `changes_since_last` (new "Since the Last Report" section)
- [x] Chat: compact context, no duplicated question (done in batch 1)
- [x] Owner feedback: browser opened before the server was up on first run ("lost connection"), so it now waits
      for `/api/health`; logs moved to `data/watchstock.log` (Windows QuickEdit freeze risk);
      second launch just opens the browser; no API key → no auto-request, hint shown instead
- [x] TradingView symbol mapping (`symbols.py`): `TLV.RO` → `BVB:TLV` etc. ("symbol doesn't exist" for BVB)
- [x] Default model `nvidia/nemotron-3.5-super-vl:free` (owner's choice for trials); LLM timeout 150 s
- [x] Snapshot `schema` version (D9): old cached snapshots are refetched, not rendered broken

### Batch 3 — Frontend cleanup  *(branch `batch-3-frontend`, PR #3, stacked on #2)* ✅
- [x] `static/index.html` split into `css/app.css` + 10 classic scripts in `js/` (D11)
- [x] Chart.js 4.6.1, marked 18.1.3, DOMPurify 3.4.17, Inter 5.3.0 vendored + pinned; no CDNs left
      except TradingView and logos
- [x] Tailwind Play CDN → precompiled `css/tailwind.css` (Tailwind 3.4.19); CI checks it's fresh
- [x] All LLM markdown sanitised (`renderMarkdown`, images forbidden); chat's raw-HTML
      `update_tab_content` action removed
- [x] Currency-aware money (`fmtMoney`/`fmtBig`): prices in `currency`, FCF in `financialCurrency`,
      GBp/ZAc/ILA minor units, compact $3.08T style; watchlist quotes carry currency
- [x] Plain-language wording (Analyze, New AI report, Ask about this stock, disclaimer line)
- [x] Markdown styles for AI text (headings, lists, quotes)
- [x] `scripts/ui_smoke.js` is now a pass/fail browser test (sanitising, currencies, breakdowns,
      watchlist, refresh, chat, no-key hint, failure toast) and runs in CI

### Batch 4 — Portfolio
- Holdings (ticker, shares, cost basis, currency), P/L, allocation by sector/country,
  concentration warnings, projected dividend income

### Batch 5 — Staying on top of it
- Morning digest of holdings (earnings / ex-dividend dates, big moves, insider buys, rating changes)
- Industry peer comparison; thesis tracking ("why I bought" checked against new data)

## Status
Batches 1-3 done. PRs #1, #2, #3 (stacked) wait for the owner to merge; files are copied
to the owner's folder after each batch. Next: batch 4 (portfolio).

Notes for the next agent:
- Batch 4 plan: `holdings` table (ticker, shares, avg cost, currency, opened_at, notes) via a new
  migration; `/api/portfolio` returning positions with live quotes, P/L, weights, sector/country
  allocation (sector from the cached snapshot, else a light `fetch_profile`), concentration flags
  (single position > 20%, sector > 40%), projected annual dividends. UI: a "Portfolio" view on the
  home screen next to the watchlist; keep it to one table + two small allocation charts.
  Multi-currency totals: show per-currency subtotals rather than inventing FX conversion; dad is
  mostly USD.
- For screenshots/tests: `scripts/fake_server.py` + `node scripts/ui_smoke.js` (needs
  `PLAYWRIGHT_BROWSERS_PATH` pointing at a Chromium matching playwright 1.63.0).
- The old hackathon DB (`watchstock.db` at repo root) is not migrated; the new DB is
  `data/watchstock.db`.

## Needs live testing (owner, on Windows)
Batch 1 (owner tested 2026-11-04: works; BVB chart said "symbol doesn't exist" → fixed in batch 2;
first run without key "froze / lost connection" → likely browser opened too early, fixed in batch 2):
- [x] start.bat first run, search, news, AI report with the free nemotron model

Batch 2:
- [ ] First start after update: browser opens by itself once ready (no "can't connect" page)
- [ ] Double-click start.bat again while running → just opens a tab
- [ ] `TLV.RO` / `SNP.RO`: TradingView chart shows (if it says "only available on TradingView",
      the free widget lacks BVB data and we'll need our own chart)
- [ ] Remove the API key → search a stock → AI tab shows the "add a key" hint, nothing freezes
- [ ] MSFT dividend yield shows ~0.8%, not 80%
- [ ] Request a second report on the same stock → "Since the Last Report" section appears
- [ ] If anything misbehaves: send `data\watchstock.log`

Batch 3:
- [ ] Looks the same as before (fonts, layout, colours), with nothing loaded from CDNs
- [ ] AI report: headings/bullets readable, links clickable
- [ ] `TLV.RO` shows prices in RON (e.g. "RON 29.50"), MSFT in $
- [ ] Market cap shows compact (e.g. "$3.08T")

## Open questions for the owner
- (answered) Dad holds mostly US stocks → currency formatting stays in batch 3, no rush.
- (answered) Default model: `nvidia/nemotron-3.5-super-vl:free` for now.
