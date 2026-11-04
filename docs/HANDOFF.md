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

### Batch 4 — Portfolio  *(branch `batch-4-portfolio`, PR #4, stacked on #3)* ✅
- [x] `holdings` table (migration 2), one row per position (D12)
- [x] `watchstock/portfolio.py`: value, P/L, day change, weights, sector allocation, per-currency totals
      (no FX), concentration flags (position > 20%, sector > 40%, only with ≥ 3 positions),
      projected annual dividends + yield on cost, missing-price handling
- [x] `/api/portfolio` GET/PUT/DELETE; PUT validates the ticker via `services.get_stock`
- [x] Home: "My Portfolio" with summary cards, holdings table (click → stock view), position and
      sector doughnuts, flags; add/edit modal with autocomplete, decimal-comma input, two-click remove
- [x] Stock sidebar: "You own N @ cost, P/L" line (`holding` field on the snapshot response)
- [x] Owner feedback: long-term safety renamed "Stability (debt & volatility)" and its breakdown says
      which half drags it down; scores round half up
- [x] 76 backend tests; UI smoke covers the portfolio flow

### Batch 5 — Staying on top of it  *(branch `batch-5-today`, PR #5, stacked on #4)* ✅
- [x] "Your stocks · next 2 weeks" panel (home, right column): earnings and ex-dividend dates within
      14 days, |day move| ≥ 3%, analyst rating changes in the last 7 days, insider purchases in the
      last 30 days; held stocks first (`today.py`, `/api/today`, D13)
- [x] `yahoo.fetch_events` (calendar + ratings + insider), cached 6 h per ticker, max 4 parallel
- [x] Thesis check per position (`/api/portfolio/{t}/thesis`, migration 3 `thesis_checks`): status
      intact / weakening / broken / unclear + evidence for/against + what to watch; badge in the
      portfolio table; previous check passed to the next one
- [x] 88 backend tests; UI smoke covers the Today panel and thesis flow

### Batch 6 — Peers + polish  *(branch `batch-6-peers`, PR #6, stacked on #5)* ✅
- [x] Industry peer comparison (D14): `peers.py`, `yahoo.fetch_industry_peers` / `fetch_key_metrics`,
      `services.load_peers` (US-listed only, 24 h cache, 4 parallel); Finance tab "Industry peers" table
      with the stock highlighted vs the median; P/E and forward P/E scored relative to the peer median
- [x] Snapshot schema 3 (old cached snapshots refetch); LLM context includes peer medians
- [x] `start.bat` creates a Desktop shortcut on first run (once; marker `data\.shortcut-created`)
- [x] Debt/Equity card shows "0.30x" like the breakdown (Yahoo's raw value is percent)
- [x] 96 backend tests; UI smoke checks the peer table and relative P/E

### Batch 7 — English / Romanian  *(branch `batch-7-language`, PR #7, stacked on #6)* ✅
- [x] EN/RO switch in the home top bar and in Settings (`ws_lang` cookie, page reload) (D15)
- [x] Frontend: `static/js/i18n.js` dictionary (~300 strings), automatic translation of static and
      inserted text, `t()` for strings with variables, `fmtN()` + locale-aware money/dates
- [x] Backend: `watchstock/i18n.py` (`tr`, `num`), middleware sets the request language; score
      breakdowns, labels, flags, Today events (Romanian dates), portfolio flags, warnings and errors
      localised; scores computed at serve time; LLM writes reports/thesis checks/chat in Romanian
- [x] `tests/test_i18n.py` enforces complete dictionaries; UI smoke audits Romanian pages for
      leftover English. Caught: a MutationObserver infinite loop on identical translations, and
      the logo turning into "WatchAcțiune"

### Batch 8 — History, Tradeville import, highlights, model presets (next)
- **Tradeville import** (owner sent a real export 2026-11-04; NOT in the repo, keep it that way;
  build a synthetic fixture). Format: first line `SEP=\t`, then a tab-separated header. Columns:
  `simbol` (e.g. `US.APLD`, `US.COHRn`, `US.OUSTc`: strip the `US.` prefix and trailing lowercase
  class letters; BVB symbols presumably have no prefix → `.RO`), `sold` = shares,
  `costm` = average cost, `ppiata` = market price, `valuta` = currency, `nume` = name,
  `isin`, `tsim` = `actiuni` (shares) or `bani` (cash row; skip, maybe show cash). Decimal point
  is `.`. Use the ISIN (`yf.Search(isin)`) as a fallback when a ticker doesn't resolve. Preview
  before saving; replace vs merge choice. The owner's dad has ~36 US positions.
- **Today panel with ~36 holdings**: currently fetches calendar + ratings + insider per ticker
  (3 Yahoo requests each, cached 6 h, 4 in parallel): fine but slow on first load. Consider
  calendar-only for the first pass and loading ratings/insider lazily.
- **Portfolio history**: 1-year chart of the current holdings' value (from `Ticker.history`)
  vs the S&P 500, plus a daily recorded total going forward.
- **Price highlights**: optional "below X / above Y" per position → highlighted row + a line in
  the "Your stocks" panel. No notifications (the owner said no alerts; app isn't open 24/7).
- **Model presets** in Settings (free nemotron default + one or two good paid options).

### Ideas for later (not planned)
- Own price chart (`Ticker.history`) if TradingView ever fails for a market the owner uses
  (owner confirmed TradingView works, including BVB, on 2026-11-04).
- Scheduled morning digest (email / Windows toast) if the "Your stocks" panel proves useful.
- Peer comparison for non-US stocks (would need a different peer source).
- Portfolio history (value over time) — needs a daily snapshot job.

## Status
Batches 1-7 done. PR #1 merged by the owner; #2-#7 stacked, CI-green. **Owner action:** on PR #2
change the base to `main` (Edit next to the title), merge, click "Delete branch"; GitHub then
retargets #3 to `main`, and so on. (Agents may not merge or retarget PRs here.)
The owner's folder `E:\WatchStock\WatchStock` has everything through batch 7. Next: batch 8.

Notes for the next agent:
- The sidebar "you own" P/L uses the snapshot price (up to 4 h old); the portfolio table
  uses live quotes. Fine for now; unify if the owner notices.
- For screenshots/tests: `scripts/fake_server.py` + `node scripts/ui_smoke.js` (needs
  `PLAYWRIGHT_BROWSERS_PATH` pointing at a Chromium matching playwright 1.63.0).

## Needs live testing (owner, on Windows)
Owner reported 2026-11-04 evening: batches 1-5 tested, "it all seems to work" (incl. TradingView on BVB).

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

Batch 4:
- [ ] Add a few real positions (+ ADD POSITION): value, P/L and "Today" look right vs the broker
- [ ] Expected dividends per year look plausible (shares × annual dividend per share)
- [ ] Click a row → opens the stock; sidebar shows "You own ..."
- [ ] Edit a position, then remove it (click REMOVE twice)
- [ ] Sidebar "Stability" circle; its breakdown explains a low score from high beta

Batch 5:
- [ ] "Your stocks · next 2 weeks" shows real earnings / ex-dividend dates for held + starred stocks
      (dates come from Yahoo's calendar; spot-check one against the company's IR page)
- [ ] Add a "why I own it" note to a position → CHECK → verdict with evidence appears; badge in table
- [ ] The free model returns valid JSON for the thesis check (if not: note the error text)

Batch 6:
- [ ] Finance tab "Industry peers" table appears for a US stock (e.g. MSFT, JPM) with sensible peers
- [ ] Valuation breakdown shows "P/E ... vs industry median ..."
- [ ] First start after the update creates a "WatchStock" shortcut on the Desktop, and it launches the app
- [ ] Opening a stock for the first time is still reasonably fast (peers add up to 5 Yahoo calls, cached a day)

Owner reported 2026-11-04 evening: batch 6 OK (peers make sense, Desktop shortcut works).

Batch 7:
- [ ] RO button (top right) switches everything to Romanian; EN switches back
- [ ] A new AI report / thesis check / chat answer comes back in Romanian (free model quality varies)
- [ ] Romanian wording reads naturally to the dad (send any odd phrases; they're in static/js/i18n.js)

## Open questions for the owner
- (answered) Dad holds mostly US stocks → currency formatting stays in batch 3, no rush.
- (answered) Default model: `nvidia/nemotron-3.5-super-vl:free` for now.
