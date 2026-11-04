"""Run WatchStock with fake Yahoo + LLM providers (no network needed).

For UI work and screenshots in sandboxes that can't reach Yahoo/OpenRouter:

    uv run python scripts/fake_server.py            # http://127.0.0.1:8001

Uses a throwaway data dir, so it never touches the real DB.
"""

import copy
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["WATCHSTOCK_DATA_DIR"] = tempfile.mkdtemp(prefix="watchstock-fake-")

import uvicorn  # noqa: E402

from tests.conftest import SAMPLE_NEWS, SAMPLE_PROFILE  # noqa: E402
from watchstock import store  # noqa: E402
from watchstock.providers import openrouter, yahoo  # noqa: E402


def fetch_profile(ticker):
    if ticker == "FAIL":
        raise yahoo.MarketDataError("429 Too Many Requests (fake)")
    p = copy.deepcopy(SAMPLE_PROFILE)
    m = p["metrics"]
    m["industryKey"] = "software-infrastructure"
    if ticker.endswith(".RO"):  # Bucharest: everything in RON
        p["name"] = "Banca Transilvania S.A."
        m.update(currency="RON", financialCurrency="RON", currentPrice=29.5, marketCap=2.4e10)
    elif ticker == "TSM":  # US-listed, statements in TWD
        p["name"] = "Taiwan Semiconductor Manufacturing"
        m.update(currency="USD", financialCurrency="TWD", freeCashflow=9e11, marketCap=1.1e12)
    p["upgrades_downgrades"] = [
        {"date": "2026-10-2" + str(i), "firm": f"Firm {i}", "from_grade": "Hold",
         "to_grade": "Buy", "action": "up"} for i in range(7)
    ]  # fmt: skip
    p["insider_transactions"] = [
        {"date": "2026-10-15", "insider": "Jane Doe", "title": "CFO", "transaction": "Sale",
         "text": "Sale at price 410.00 per share.", "shares": 5000, "value": 2_050_000}
    ]  # fmt: skip
    return p


def fetch_news(ticker, count=20):
    return copy.deepcopy(SAMPLE_NEWS) * 3


def fetch_quotes(tickers):
    def cur(t):
        return "RON" if t.endswith(".RO") else "USD"

    def chg(t):
        return -6.5 if t == "NVDA" else 1.2  # NVDA: a "big move" for the Today panel

    return {t: {"price": 100.0, "change_pct": chg(t), "currency": cur(t)} for t in tickers}


def fetch_industry_peers(industry_key, limit=8):
    return [
        {"ticker": t, "name": n}
        for t, n in [
            ("MSFT", "Microsoft"),
            ("ORCL", "Oracle"),
            ("ADBE", "Adobe"),
            ("CRM", "Salesforce"),
        ]
    ][:limit]


def fetch_key_metrics(ticker):
    pe = {"ORCL": 40.0, "ADBE": 45.0, "CRM": 50.0}.get(ticker, 30.0)
    return {
        "name": ticker,
        "trailingPE": pe,
        "forwardPE": pe * 0.8,
        "pegRatio": 2.0,
        "profitMargins": 0.2,
        "revenueGrowth": 0.1,
        "marketCap": 2e11,
        "currency": "USD",
    }


def fetch_events(ticker):
    from datetime import date, timedelta

    def d(n):
        return (date.today() + timedelta(days=n)).isoformat()

    if ticker == "MSFT":
        return {
            "earnings_dates": [d(3)],
            "ex_dividend_date": d(5),
            "upgrades_downgrades": [{"date": d(-1), "firm": "Example Securities", "action": "up",
                                     "from_grade": "Hold", "to_grade": "Buy"}],
            "insider_transactions": [],
        }  # fmt: skip
    if ticker == "NVDA":
        return {"insider_transactions": [{"date": d(-2), "insider": "JANE DOE", "transaction": "Purchase",
                                          "text": "", "value": 1_200_000}]}  # fmt: skip
    return {}


def fetch_indices():
    return [
        {"name": n, "ticker": t, "value": v, "change_pct": c}
        for n, t, v, c in [("S&P 500", "^GSPC", 6012.3, 0.42), ("NASDAQ", "^IXIC", 19876.1, -0.31),
                           ("DOW", "^DJI", 44210.0, 0.12), ("VIX", "^VIX", 15.2, -2.1)]
    ]  # fmt: skip


def fetch_market_news(count=10):
    return copy.deepcopy(SAMPLE_NEWS) * 4


def fetch_movers(count=20):
    def row(t, chg, cap):
        return {
            "ticker": t,
            "name": f"{t} Inc",
            "price": 42.0,
            "change_pct": chg,
            "market_cap": cap,
        }

    return {
        "gainers": [row(f"GA{i}", 5.0 + i, 5e10) for i in range(6)],
        "losers": [row(f"LO{i}", -4.0 - i, 5e10) for i in range(6)],
    }


def search(query, limit=6):
    return [
        {"name": "Microsoft Corporation", "ticker": "MSFT", "exchange": "NASDAQ", "type": "EQUITY"}
    ]


REPORT = {
    "executive_summary": "Fake report: strong franchise, fair-to-rich valuation.",
    "verdict": {"action": "BUY", "confidence": 68, "horizon": "12 months"},
    "recommended_action": "Accumulate on pullbacks.",
    # The <img onerror> is a deliberate XSS probe: the UI must sanitise it away.
    "financial_deep_dive": "## Margins\n**Operating margin 45%**. See [source](https://example.com)."
    '\n\n<img src="https://probe.invalid/x.png" onerror="window.__xss=1">'
    "<script>window.__xss=1</script>",
    "news_impact_analysis": "## News\n- Cloud growth beat.",
    "risk_scenarios": "## Bull Case\nUp.\n## Base Case\nFlat.\n## Bear Case\nDown.",
    "charts": [{"chart_type": "bar", "labels": ["P/E", "Fwd P/E"], "values": [33.4, 29.3],
                "title": "Valuation Multiples"}],
}  # fmt: skip


def complete(messages, *, api_key, model, json_mode=True):
    if "investor_thesis" in messages[-1]["content"]:
        return json.dumps({
            "status": "intact",
            "summary": "Fake check: cloud growth is still visible in the numbers.",
            "supporting": ["Revenue growth +12%"], "against": ["Valuation is rich"],
            "watch": ["Next earnings"],
        })  # fmt: skip
    if "COMPANY CONTEXT" in messages[0]["content"]:
        return json.dumps({"reply_text": "Fake chat answer.", "ui_action": None})
    report = dict(REPORT)
    if "previous_report" in messages[-1]["content"]:
        report["changes_since_last"] = "- Nothing material changed (fake)."
    return json.dumps(report)


def install_fakes():
    for fn in (fetch_profile, fetch_news, fetch_quotes, fetch_indices, fetch_market_news,
               fetch_movers, search, fetch_events, fetch_industry_peers, fetch_key_metrics):  # fmt: skip
        setattr(yahoo, fn.__name__, fn)
    openrouter.complete = complete


if __name__ == "__main__":
    install_fakes()
    from watchstock import db

    db.init_db()
    store.set_setting("llm_api_key", "fake-key")
    uvicorn.run("watchstock.app:app", host="127.0.0.1", port=8001, log_level="warning")
