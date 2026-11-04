# WatchStock — notes for AI agents and contributors

Personal stock-analysis tool for **one non-technical user on Windows** (the
owner's dad, who manages a small portfolio). It started as a hackathon project.
Optimise for: simple UI, one-click install, correct numbers, easy to extend.

**Start every session by reading `docs/HANDOFF.md`.** It has the current state,
the batch plan, open questions, and what still needs testing on a real machine.
Architecture: `docs/ARCHITECTURE.md`. Why things are the way they are: `docs/DECISIONS.md`.

## Commands

```bash
uv sync                          # install deps (creates .venv)
uv run python -m watchstock      # run the app at http://127.0.0.1:8000 (opens browser)
uv run python -m watchstock --no-browser
uv run pytest                    # tests (no network needed)
uv run ruff check . && uv run ruff format --check .

# frontend tooling (developers only; outputs are committed, end users never need Node)
npm ci
npm run build                    # re-vendor pinned libs + recompile Tailwind CSS
uv run python scripts/fake_server.py &  node scripts/ui_smoke.js   # browser test, fake data
```

End users run `start.bat` (Windows). It installs `uv` if missing; `uv` fetches
the right Python and dependencies by itself. Nothing needs to be pre-installed.

## Rules of the road

- **All network access goes through `watchstock/providers/`** (`yahoo.py` for
  market data, `openrouter.py` for the LLM). Nothing else imports `yfinance` or
  calls `httpx`. Tests swap these modules for fakes; tests must never hit the network.
- Provider functions are **synchronous**; routes call them via `asyncio.to_thread`
  so a slow Yahoo call never freezes the server.
- **Never persist a failed fetch or a failed LLM call.** Errors are returned to the
  UI and logged, not cached.
- Scoring lives in `watchstock/scoring.py` as **pure functions** with unit tests.
  If you change a formula, update the test and the explanation in the UI breakdown.
- Yahoo field quirks (units, currencies) are normalised in `providers/yahoo.py`,
  not in the frontend. Document each quirk where it's handled.
- Single user, bound to `127.0.0.1`. No accounts, no auth. Don't add them back.
- SQLite via stdlib `sqlite3`, schema changes as new entries in
  `db.MIGRATIONS` (never edit an applied migration).
- Frontend: plain HTML/CSS/JS, **no build step required to run**. `static/js/*.js` are
  classic scripts sharing one global scope, loaded in the order listed in `index.html`;
  top-level code may only call functions from earlier files (startup lives in `main.js`).
  Third-party JS/fonts are vendored and pinned in `static/vendor/` via `npm run vendor`.
  Tailwind is precompiled to `static/css/tailwind.css`. After adding Tailwind classes,
  run `npm run build:css`; CI fails if the committed CSS is stale.
- LLM output is untrusted: render markdown only through `renderMarkdown()` (DOMPurify).
  Never assign model text to `innerHTML` directly. Escape external text with `esc()`.
- Money: use `fmtMoney`/`fmtBig` with `priceCurrency()` for prices and
  `statementCurrency()` for statement values. Never hardcode `$`. Other displayed numbers
  go through `fmtN()` (locale-aware); numbers used in CSS stay plain.
- **Every user-visible string is translatable (English / Romanian)**, English text = key:
  - Frontend: exact static strings are translated automatically. Just add the English →
    Romanian pair to `RO` in `static/js/i18n.js`. Strings with variables use
    `t('Saved {ticker}.', { ticker })`. Mark containers of external/LLM text `no-i18n`.
  - Backend: `tr("Net margin {pct}", pct=num(x) + "%")` with the pair in `watchstock/i18n.py`.
  - `tests/test_i18n.py` fails if a string is missing from either dictionary. Never name a
    local variable `t` in frontend code (it shadows the translator).
- Keep the UI simple. Every new panel must earn its place for a portfolio owner.

## Workflow

- One branch + PR per batch (`batch-N-short-name`), CI must be green before merge.
- At the end of each batch (or when context is getting full), update
  `docs/HANDOFF.md`: what changed, what's next, what the owner must test.
- The owner tests on Windows; the dev sandbox usually cannot reach Yahoo or
  OpenRouter. Anything unverifiable against live data goes in HANDOFF's
  "Needs live testing" list.
