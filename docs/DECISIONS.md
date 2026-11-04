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
