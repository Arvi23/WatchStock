"""The Today panel (pure event building + /api/today) and thesis checks."""

import json
from datetime import date, timedelta

import pytest

from watchstock import today
from watchstock.providers import yahoo

TODAY = date(2026, 11, 4)


def d(days):
    return (TODAY + timedelta(days=days)).isoformat()


def build(events=None, quotes=None, held=True):
    tickers = {"MSFT": {"name": "Microsoft", "held": held}}
    return today.build_events(tickers, quotes or {}, {"MSFT": events or {}}, TODAY)


def test_upcoming_earnings_and_ex_dividend():
    out = build({"earnings_dates": [d(3), d(5)], "ex_dividend_date": d(1)})
    texts = [e["text"] for e in out]
    assert texts[0].startswith("Earnings in 3 days")
    assert texts[1].startswith("Ex-dividend tomorrow")


def test_dates_outside_window_are_ignored():
    assert build({"earnings_dates": [d(-1), d(30)], "ex_dividend_date": d(15)}) == []


def test_big_move_only_above_threshold():
    assert build(quotes={"MSFT": {"change_pct": -4.2}})[0]["text"] == "Down 4.2% today"
    assert build(quotes={"MSFT": {"change_pct": 2.9}}) == []


def test_recent_rating_changes_only():
    ev = {"upgrades_downgrades": [
        {"date": d(-2), "firm": "Morgan Stanley", "action": "up", "from_grade": "Hold", "to_grade": "Buy"},
        {"date": d(-20), "firm": "Old Firm", "action": "down", "from_grade": "Buy", "to_grade": "Sell"},
    ]}  # fmt: skip
    out = build(ev)
    assert [e["text"] for e in out] == ["Morgan Stanley upgraded Hold → Buy"]


def test_insider_purchases_only():
    ev = {"insider_transactions": [
        {"date": d(-3), "insider": "JANE DOE", "transaction": "Purchase", "text": "", "value": 2_500_000},
        {"date": d(-3), "insider": "JOHN ROE", "transaction": "Sale", "text": "Sale at price", "value": 9e6},
    ]}  # fmt: skip
    assert [e["text"] for e in build(ev)] == ["Insider buy: Jane Doe ($2.5M)"]


def test_held_positions_sort_before_watchlist():
    tickers = {"WATCH": {"held": False}, "HELD": {"held": True}}
    events = {t: {"earnings_dates": [d(2)]} for t in tickers}
    out = today.build_events(tickers, {}, events, TODAY)
    assert [e["ticker"] for e in out] == ["HELD", "WATCH"]


# --------------------------------------------------------------------- API


def test_today_endpoint_combines_watchlist_and_holdings(client, fake_yahoo):
    assert client.get("/api/today").json() == {"events": [], "tracked": 0}
    soon = (date.today() + timedelta(days=2)).isoformat()
    fake_yahoo.events = {"MSFT": {"earnings_dates": [soon]}, "AAPL": {"ex_dividend_date": soon}}
    client.post("/api/watchlist", json={"ticker": "AAPL", "company_name": "Apple"})
    client.put("/api/portfolio", json={"ticker": "MSFT", "shares": 1, "avg_cost": 1})
    body = client.get("/api/today").json()
    assert body["tracked"] == 2
    assert [(e["ticker"], e["kind"], e["held"]) for e in body["events"]] == [
        ("MSFT", "earnings", True),
        ("AAPL", "ex_dividend", False),
    ]
    # cached: a second call doesn't refetch events
    client.get("/api/today")
    assert fake_yahoo.calls.count(("events", "MSFT")) == 1


def test_thesis_check_flow(client, fake_llm):
    client.put("/api/settings", json={"llm_api_key": "sk-test"})
    assert client.post("/api/portfolio/MSFT/thesis").status_code == 404
    client.put("/api/portfolio", json={"ticker": "MSFT", "shares": 1, "avg_cost": 1})
    r = client.post("/api/portfolio/MSFT/thesis")
    assert r.status_code == 422 and "why I own it" in r.json()["detail"]

    client.put(
        "/api/portfolio",
        json={"ticker": "MSFT", "shares": 1, "avg_cost": 1, "notes": "Cloud growth"},
    )
    fake_llm.reply = json.dumps({"status": "Intact", "summary": "Azure still growing.",
                                 "supporting": ["Revenue +12%"], "against": [], "watch": ["Capex"]})  # fmt: skip
    result = client.post("/api/portfolio/MSFT/thesis").json()
    assert result["status"] == "intact"
    assert result["thesis"] == "Cloud growth"
    ctx = json.loads(fake_llm.requests[-1]["messages"][1]["content"])
    assert ctx["investor_thesis"] == "Cloud growth"

    pos = client.get("/api/portfolio").json()["positions"][0]
    assert pos["thesis_check"]["status"] == "intact"
    assert client.get("/api/portfolio/MSFT/thesis").json()["summary"] == "Azure still growing."


@pytest.mark.parametrize(
    "reply", ['{"status": "great", "summary": "x"}', '{"status": "intact"}', "nope"]
)
def test_thesis_check_rejects_bad_replies(client, fake_llm, reply):
    client.put("/api/settings", json={"llm_api_key": "sk-test"})
    client.put("/api/portfolio", json={"ticker": "MSFT", "shares": 1, "avg_cost": 1, "notes": "x"})
    fake_llm.reply = reply
    assert client.post("/api/portfolio/MSFT/thesis").status_code == 502
    assert client.get("/api/portfolio/MSFT/thesis").json() is None


# ---------------------------------------------------------------- provider


def test_fetch_events_parses_calendar(monkeypatch):
    class Stub:
        calendar = {"Earnings Date": [date(2026, 11, 20), date(2026, 11, 24)],
                    "Ex-Dividend Date": date(2026, 11, 12)}  # fmt: skip
        upgrades_downgrades = None
        insider_transactions = None

    monkeypatch.setattr(yahoo.yf, "Ticker", lambda t: Stub())
    ev = yahoo.fetch_events("MSFT")
    assert ev["earnings_dates"] == ["2026-11-20", "2026-11-24"]
    assert ev["ex_dividend_date"] == "2026-11-12"
    assert ev["dividend_date"] is None
