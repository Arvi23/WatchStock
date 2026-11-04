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
- Frontend: plain HTML/CSS/JS, **no build step required to run**. Third-party JS is
  vendored and pinned under `static/vendor/` (see HANDOFF for status).
- Keep the UI simple. Every new panel must earn its place for a portfolio owner.

## Workflow

- One branch + PR per batch (`batch-N-short-name`), CI must be green before merge.
- At the end of each batch (or when context is getting full), update
  `docs/HANDOFF.md`: what changed, what's next, what the owner must test.
- The owner tests on Windows; the dev sandbox usually cannot reach Yahoo or
  OpenRouter. Anything unverifiable against live data goes in HANDOFF's
  "Needs live testing" list.
