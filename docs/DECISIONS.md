# Decisions

Short records of choices that shape the codebase. Newest last. If you reverse one,
add a new entry rather than editing the old one.

## D1 — Keep Python + FastAPI for the backend (2026-11-04)
yfinance is the best free market-data source and it is Python-only, so the backend
stays Python. FastAPI is small, typed and widely known, so future agents can work on
it easily. Rejected: a Streamlit/NiceGUI rewrite (throws away a working UI, and the
rerun model is awkward for a portfolio app) and Node (no comparable free data library).

## D2 — Personal, single-user app: no accounts (2026-11-04)
The hackathon required multi-user login. Real use is one person on one PC. The old
login was cosmetic anyway (plain-text passwords, no server-side checks). Removed.
The server binds to `127.0.0.1` only, so nothing on the LAN can reach it.

## D3 — Drop sentence-transformers and NewsAPI; news comes from Yahoo (2026-11-04)
The embedding model pulled in PyTorch (~2 GB on Windows) to compute a "risk" score
that compared articles to a sentence mixing good and bad news, so it measured
"financial-sounding" rather than risk. NewsAPI's free tier is development-only and
delayed. `yfinance` `Ticker.get_news()` is free, keyless and already ticker-scoped.
Judging news materiality is done by the LLM in the analysis call (batch 2).

## D4 — Packaging with uv; one-click `start.bat` (2026-11-04)
`pyproject.toml` + `uv.lock` replace `requirements.txt` + `setup.bat`. `start.bat`
installs uv (official installer) if missing, then `uv run` downloads the pinned Python
and dependencies on first launch. The user doesn't need Python installed or on PATH.
Rejected for now: PyInstaller `.exe` (antivirus false positives, harder updates,
curl_cffi bundling issues). Revisit if uv is a problem on the target PC.

## D5 — OpenRouter is the only LLM gateway, and the LLM is optional (2026-11-04)
One key gives access to any model. Everything except AI analysis/chat works without a key.

## D6 — Frontend stays plain HTML/JS with no build step (2026-11-04)
A React/Vite rewrite would add a Node toolchain to every change, for little gain.
Third-party libraries get vendored + pinned (unpinned CDN `marked` already broke the
report's links). The single 2,400-line `index.html` will be split into ES modules
in batch 3. Tailwind's Play CDN is not meant for production; batch 3 decides between
a committed, pre-built CSS file and plain CSS.

## D7 — Cached snapshots with a freshness TTL; failures never cached (2026-11-04)
The old "DB-first" design served data from the DB forever (a May price was shown as
current in November) and also stored failed fetches. Now each ticker has one snapshot
with `fetched_at`; it's served only while younger than `SNAPSHOT_TTL`, and the UI shows
its age. AI analyses are stored separately with their own timestamp and model.

## D8 — Two scoring lenses, no double counting (2026-11-04)
The hackathon had "health" (ST/LT) and "opportunity" scores that both used current
ratio, margins and debt/equity. Now:
- **Opportunity** = Quality 30% (margins, growth, FCF yield) + Valuation 30% +
  Analyst 25% + Smart money 15%.
- **Safety** (sidebar) = Liquidity (current/quick ratio) and Solvency & volatility
  (debt/equity, beta).
Each metric feeds exactly one score. Missing inputs are skipped and the weights
renormalised; no inputs gives a neutral 50. Geographic risk is a flag, not a penalty
(HQ country says little about exposure). Analyst consensus with few analysts is shrunk
toward 50 instead of multiplied down. Loss-makers get a low valuation score instead of
the P/E being silently skipped. Debt/equity is skipped for financial companies. FCF yield
is skipped when statements and price are in different currencies. P/E bands are still
industry-agnostic, to be fixed by peer comparison (batch 5).

## D9 — Snapshot schema version (2026-11-04)
Snapshots carry `schema`. When the shape changes, bump `services.SNAPSHOT_SCHEMA` and
cached snapshots in the old shape are refetched instead of breaking the UI.

## D10 — Logs to a file, browser opens when the server is up (2026-11-04)
Windows console QuickEdit mode blocks any process writing to a console the user has
clicked into, which looks like a freeze. Logs go to `data/watchstock.log`; the console only
shows the startup banner. The browser opens after `/api/health` answers.

## D11 — Frontend: split classic scripts, vendored libs, precompiled Tailwind (2026-11-04)
The 2,400-line `index.html` is now `index.html` + `css/app.css` + ten files in `js/`.
They're classic scripts sharing one global scope, not ES modules: the markup uses inline
`onclick` handlers that need globals, and modules would mean rewriting every handler
for no user-visible gain. Converting to modules later is mechanical if it's ever needed.
Chart.js, marked, DOMPurify and the Inter font are vendored at pinned versions
(`package.json`, `scripts/vendor.mjs`): the app no longer depends on CDNs, and an
unpinned CDN update can't break it again (that's how the report links broke). Tailwind's
Play CDN (a runtime compiler, not meant for production) is replaced by a precompiled
`static/css/tailwind.css`, which CI checks is up to date. Node is a developer-only tool.
All LLM markdown goes through DOMPurify, with images forbidden.

## D12 — Portfolio: one row per position, per-currency totals, no FX (2026-11-04)
The user enters each position as shares + average cost (not individual lots): that's
how a small-portfolio owner thinks about it, and it's easy to keep current. Totals,
weights and concentration are computed per currency; there is no FX conversion,
because a guessed or stale rate would make every total quietly wrong (the owner is
mostly USD). Adding a position validates the ticker by fetching and caching its
snapshot, which also gives sector/country/dividend rate for allocation. A position's
`notes` ("why I own it") is stored now so batch 5 can check the thesis against new data.
Scores are rounded half up (49, not Python's banker's 48) so people can check them by hand.

## D13 — "Today" panel computed on page load; thesis checks on demand (2026-11-04)
The morning-digest idea starts as a panel computed when the home screen opens (calendar,
big moves, rating changes, insider buys for held + watched stocks). That needs no scheduler,
email setup or background process on the dad's PC. Per-ticker event data is cached for 6 h
and fetched at most 4 tickers at a time, to stay gentle with Yahoo. Thesis checks are an
explicit button per position (one LLM call each) and are stored with the thesis text as it
was, so a later check can say what changed. Insider sales are skipped (routine diversification);
purchases are signal.

## D14 — Industry peers make P/E relative; US-listed stocks only (2026-11-04)
Fixed P/E bands judged a software company and a bank by the same yardstick (D8). The
snapshot now includes up to 5 of the largest companies in the stock's Yahoo industry
(`yf.Industry(key).top_companies`). When at least 3 have a usable value, trailing and
forward P/E are scored against the peer median (ratio bands), and the breakdown says
e.g. "33.4 vs industry median 45.0 (-26%)". Otherwise the fixed bands still apply. Yahoo's
industry lists are US companies, so non-USD stocks get no peers rather than a misleading
comparison. Peer lists and peer metrics (one `info` call each) are cached in memory for
24 h and fetched 4 at a time; a failed peer is skipped. Snapshot schema 3.

## D15 — English/Romanian: English strings are the keys; language in a cookie (2026-11-04)
gettext-style dictionaries (`static/js/i18n.js`, `watchstock/i18n.py`) keyed by the English
text, so the code stays readable and a missing translation shows English instead of breaking.
The frontend translates static and dynamically inserted text automatically (a
MutationObserver matches exact strings; only text with variables needs `t()`). Containers
of external text (news, LLM output, chat) are marked `no-i18n` so a headline like "Hold"
isn't "translated". The language is a `ws_lang` cookie: known synchronously at page load,
and sent with every request, so the backend localises score breakdowns, panel events and
errors and tells the LLM to write in Romanian (JSON keys/enums stay English). Scores are
now computed at serve time from the cached snapshot (cheap, language-aware, and formula
changes apply without refetching). Switching language reloads the page. Numbers and dates
follow the locale (1.234,56 in Romanian). Stored AI reports stay in the language they were
written in. Tests enforce dictionary completeness.

## D16 — Portfolio import: preview first, verify every ticker, light background info (2026-11-04)
The owner's dad keeps his positions in Tradeville, so typing ~36 positions by hand was the
real obstacle. Import is two calls: `preview` parses the file and checks every ticker (one
batch quote call; an ISIN search for the ones that fail; an ISIN hit that would duplicate
another row is rejected) and saves nothing; `commit` writes the rows the user kept. Rows that
can't be verified can't be imported until the user types a ticker that verifies, so the
portfolio never holds an unpriced typo. "Replace" is the default because a broker export is
the full portfolio; "why I own it" notes survive either mode. Opening all 36 stocks just to get
sectors would cost ~10 Yahoo calls each, so the import fetches one light `info` call per new
ticker in the background (`company_info` table, migration 4) and the portfolio re-polls while
`info_pending > 0`; if the app was closed mid-way, the next portfolio load resumes it. Failed
fetches are not saved. Parsing is pure (`importers.py`) and tested on a synthetic fixture: the
real export contains the family's holdings and stays out of the repo.
