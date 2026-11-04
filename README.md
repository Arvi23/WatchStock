# WatchStock

A personal stock-analysis terminal that runs on your own PC. Search a company and get
live metrics from Yahoo Finance, explainable 0–100 scores, recent news, and (optionally)
an AI-written research report you can question in a chat.

> WatchStock is a research aid, not financial advice. Scores are simple heuristics on
> Yahoo Finance data, and AI reports can be wrong. Check anything you act on.

## Install and run (Windows)

1. Download this repository: **Code → Download ZIP** on GitHub, then unzip it somewhere
   permanent (e.g. `Documents\WatchStock`). Or `git clone` it.
2. Double-click **`start.bat`**.
   - The first start installs a small tool called `uv`, which downloads Python and the
     libraries WatchStock needs. This takes a few minutes, once. Nothing else needs to be installed.
   - Your browser opens at `http://127.0.0.1:8000`.
3. To stop WatchStock, close the black window.

Optional: for AI reports and chat, open **Settings** (gear icon) and paste an
[OpenRouter](https://openrouter.ai) API key. Everything else works without one.

Your data (watchlist, settings, saved reports) is stored in the `data` folder next to
`start.bat`. Keep that folder when updating.

## Updating

Download the new ZIP and copy your old `data` folder into it (or `git pull`).

## What it shows

- **Home:** major indices, market news, today's biggest movers, your watchlist.
- **Finance tab:** opportunity score (fundamentals, analyst view, valuation, smart money,
  each with a click-for-breakdown), valuation multiples, analyst targets and rating
  changes, insider transactions, key metrics.
- **AI Analysis tab:** verdict, deep dive, news impact, bull/base/bear scenarios, charts.
  Reports are saved with their date and model.
- **News tab:** recent headlines for the stock.
- **Chat:** ask follow-up questions about the loaded company.

Data is cached for a few hours; the **REFRESH** button next to the ticker fetches it
again, and the label beside it shows how old the data is.

## For developers

See [`CLAUDE.md`](CLAUDE.md) (conventions and commands), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
[`docs/DECISIONS.md`](docs/DECISIONS.md) and [`docs/HANDOFF.md`](docs/HANDOFF.md) (status and plan).

```bash
uv sync
uv run python -m watchstock          # run
uv run pytest                        # tests, no network needed
uv run python scripts/fake_server.py # UI with fake data on :8001
npm ci && node scripts/ui_smoke.js   # browser test against the fake server
npm run build                        # after changing vendored libs or Tailwind classes
```

## License

MIT
