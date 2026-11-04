"""Portfolio math (pure) and the /api/portfolio routes."""

import pytest

from watchstock import portfolio
from watchstock.providers.yahoo import MarketDataError


def h(ticker, shares, avg_cost, currency="USD"):
    return {
        "ticker": ticker,
        "shares": shares,
        "avg_cost": avg_cost,
        "currency": currency,
        "notes": "",
    }


def test_position_value_pl_day_change_and_dividends():
    p = portfolio.build_position(
        h("MSFT", 10, 300.0),
        {"price": 400.0, "change_pct": 2.0},
        {"name": "Microsoft", "sector": "Technology", "dividend_rate": 3.6},
    )
    assert p["value"] == 4000.0
    assert p["cost"] == 3000.0
    assert p["pl"] == 1000.0
    assert p["pl_pct"] == pytest.approx(33.33, abs=0.01)
    assert p["day_change"] == pytest.approx(4000 * 2 / 102, abs=0.01)  # vs yesterday's close
    assert p["annual_dividends"] == 36.0
    assert p["yield_on_cost"] == 1.2


def test_totals_weights_and_allocation():
    holdings = [h("A", 10, 10), h("B", 10, 10), h("C", 20, 10)]
    quotes = {t: {"price": 10.0, "change_pct": 0.0} for t in "ABC"}
    info = {"A": {"sector": "Tech"}, "B": {"sector": "Energy"}, "C": {"sector": "Tech"}}
    out = portfolio.build_portfolio(holdings, quotes, info)
    t = out["totals"]["USD"]
    assert t["value"] == 400.0 and t["pl"] == 0.0 and t["positions"] == 3
    weights = {p["ticker"]: p["weight"] for p in out["positions"]}
    assert weights == {"A": 25.0, "B": 25.0, "C": 50.0}
    sectors = {s["label"]: s["weight"] for s in out["allocation"]["USD"]["sectors"]}
    assert sectors == {"Tech": 75.0, "Energy": 25.0}


def test_concentration_flags():
    holdings = [h("A", 10, 10), h("B", 10, 10), h("C", 20, 10)]
    quotes = {t: {"price": 10.0, "change_pct": 0.0} for t in "ABC"}
    info = {"A": {"sector": "Tech"}, "B": {"sector": "Energy"}, "C": {"sector": "Tech"}}
    flags = portfolio.build_portfolio(holdings, quotes, info)["flags"]
    assert any(f.startswith("C is 50%") for f in flags)
    assert any(f.startswith("Tech is 75%") for f in flags)


def test_no_concentration_flags_for_tiny_portfolios():
    out = portfolio.build_portfolio([h("A", 1, 1)], {"A": {"price": 2.0, "change_pct": 0}}, {})
    assert out["flags"] == []


def test_missing_price_is_excluded_and_flagged():
    out = portfolio.build_portfolio(
        [h("A", 1, 10), h("B", 1, 10)], {"A": {"price": 12.0, "change_pct": 0}}, {}
    )
    assert out["totals"]["USD"]["value"] == 12.0
    assert out["totals"]["USD"]["cost"] == 10.0  # only priced positions
    assert any("No live price for B" in f for f in out["flags"])


def test_currencies_are_not_mixed():
    holdings = [h("MSFT", 1, 100), h("TLV.RO", 100, 20, currency="RON")]
    quotes = {"MSFT": {"price": 110.0, "change_pct": 0}, "TLV.RO": {"price": 30.0, "change_pct": 0}}
    out = portfolio.build_portfolio(holdings, quotes, {})
    assert out["totals"]["USD"]["value"] == 110.0
    assert out["totals"]["RON"]["value"] == 3000.0
    assert all(p["weight"] == 100.0 for p in out["positions"])  # each is 100% of its group


def test_empty_portfolio():
    assert portfolio.build_portfolio([], {}, {}) == {
        "positions": [],
        "totals": {},
        "allocation": {},
        "flags": [],
    }


# ---------------------------------------------------------------------- API


def test_portfolio_roundtrip(client):
    assert client.get("/api/portfolio").json()["positions"] == []
    r = client.put(
        "/api/portfolio", json={"ticker": "msft", "shares": 10, "avg_cost": 300, "notes": "cloud"}
    )
    assert r.status_code == 200
    assert r.json()["ticker"] == "MSFT"

    body = client.get("/api/portfolio").json()
    pos = body["positions"][0]
    assert pos["ticker"] == "MSFT"
    assert pos["name"] == "Microsoft Corporation"  # from the snapshot cached on add
    assert pos["sector"] == "Technology"
    assert pos["value"] == 1000.0  # fake quote: 100.0
    assert pos["pl"] == -2000.0
    assert pos["notes"] == "cloud"
    assert pos["annual_dividends"] == pytest.approx(36.4)

    # editing replaces the position
    client.put("/api/portfolio", json={"ticker": "MSFT", "shares": 5, "avg_cost": 90})
    assert client.get("/api/portfolio").json()["positions"][0]["shares"] == 5

    # the stock view knows it's held
    assert client.get("/api/stocks/MSFT").json()["holding"]["shares"] == 5

    client.delete("/api/portfolio/MSFT")
    assert client.get("/api/portfolio").json()["positions"] == []
    assert client.get("/api/stocks/MSFT").json()["holding"] is None


def test_portfolio_rejects_unknown_ticker(client, fake_yahoo):
    fake_yahoo.profile_error = MarketDataError("No data found for ticker 'NOPE'")
    r = client.put("/api/portfolio", json={"ticker": "NOPE", "shares": 1, "avg_cost": 1})
    assert r.status_code == 502
    assert "No data" in r.json()["detail"]
    assert client.get("/api/portfolio").json()["positions"] == []


@pytest.mark.parametrize(
    "bad", [{"shares": 0, "avg_cost": 1}, {"shares": 1, "avg_cost": -1}, {"shares": 1}]
)
def test_portfolio_validation(client, bad):
    assert client.put("/api/portfolio", json={"ticker": "MSFT", **bad}).status_code == 422


def test_biggest_currency_group_comes_first():
    holdings = [h("TLV.RO", 1, 1, currency="RON"), h("A", 1, 1), h("B", 1, 1)]
    quotes = {t: {"price": 2.0, "change_pct": 0} for t in ("TLV.RO", "A", "B")}
    out = portfolio.build_portfolio(holdings, quotes, {})
    assert list(out["totals"]) == ["USD", "RON"]
    assert [p["ticker"] for p in out["positions"]][-1] == "TLV.RO"
