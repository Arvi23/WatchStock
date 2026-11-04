"""Industry peer comparison: pure math, relative P/E scoring, snapshot integration."""

import pytest

from watchstock import peers, scoring
from watchstock.providers.yahoo import MarketDataError


def peer(t, pe, fpe=None, margin=0.2, growth=0.1):
    return {
        "ticker": t,
        "name": t,
        "trailingPE": pe,
        "forwardPE": fpe,
        "pegRatio": None,
        "profitMargins": margin,
        "revenueGrowth": growth,
        "marketCap": 1e11,
    }


def test_medians_need_three_valid_peers_and_ignore_bad_values():
    rows = [peer("A", 20), peer("B", 30), peer("C", -5), peer("D", 900)]
    med = peers.peer_medians(rows)
    assert med["trailingPE"] is None  # only 2 valid P/Es
    assert med["profitMargins"] == 0.2
    med = peers.peer_medians([peer("A", 20), peer("B", 30), peer("C", 40)])
    assert med["trailingPE"] == 30


def test_comparison_excludes_self_and_computes_relative():
    rows = [peer("MSFT", 99), peer("A", 20), peer("B", 30), peer("C", 40)]
    out = peers.build_comparison("MSFT", "Microsoft", {"trailingPE": 36.0}, rows, "Software")
    assert out["peer_count"] == 3
    assert [r["ticker"] for r in out["rows"]] == ["MSFT", "A", "B", "C"]
    assert out["rows"][0]["is_self"] is True
    assert out["relative"]["trailingPE"] == 20.0  # 36 vs median 30


def test_valuation_uses_peer_median_when_available():
    absolute = scoring.score_valuation({"trailingPE": 33.4})
    cheap_vs_peers = scoring.score_valuation({"trailingPE": 33.4}, {"trailingPE": 60.0})
    pricey_vs_peers = scoring.score_valuation({"trailingPE": 33.4}, {"trailingPE": 15.0})
    assert absolute["breakdown"][0]["item"] == "Trailing P/E 33.4"
    assert "vs industry median 60.0 (-44%)" in cheap_vs_peers["breakdown"][0]["item"]
    assert cheap_vs_peers["score"] > absolute["score"] > pricey_vs_peers["score"]


# --------------------------------------------------------------- snapshots


@pytest.fixture
def with_peers(fake_yahoo, monkeypatch):
    from tests.conftest import SAMPLE_PROFILE

    monkeypatch.setitem(SAMPLE_PROFILE["metrics"], "industryKey", "software-infrastructure")
    fake_yahoo.industries = {"software-infrastructure": [
        {"ticker": "MSFT", "name": "Microsoft"}, {"ticker": "ORCL", "name": "Oracle"},
        {"ticker": "ADBE", "name": "Adobe"}, {"ticker": "CRM", "name": "Salesforce"},
        {"ticker": "GONE", "name": "Delisted"},
    ]}  # fmt: skip
    fake_yahoo.peer_metrics = {
        "ORCL": peer("ORCL", 40, 30),
        "ADBE": peer("ADBE", 45, 28),
        "CRM": peer("CRM", 50, 32),
    }
    return fake_yahoo


def test_snapshot_includes_peers_and_relative_valuation(client, with_peers):
    body = client.get("/api/stocks/MSFT").json()
    p = body["peers"]
    assert p["industry"] == "Software"
    assert [r["ticker"] for r in p["rows"]] == [
        "MSFT",
        "ORCL",
        "ADBE",
        "CRM",
    ]  # GONE failed, skipped
    assert p["medians"]["trailingPE"] == 45
    pe_item = body["scores"]["valuation"]["breakdown"][0]["item"]
    assert "vs industry median 45.0" in pe_item


def test_peer_data_is_cached_across_stocks(client, with_peers):
    client.get("/api/stocks/MSFT")
    client.get("/api/stocks/MSFT?refresh=true")
    assert with_peers.calls.count(("industry", "software-infrastructure")) == 1
    assert with_peers.calls.count(("peer", "ORCL")) == 1


def test_no_peers_for_non_usd_stocks(client, with_peers, monkeypatch):
    from tests.conftest import SAMPLE_PROFILE

    monkeypatch.setitem(SAMPLE_PROFILE["metrics"], "currency", "RON")
    assert client.get("/api/stocks/TLV.RO").json()["peers"] is None
    assert ("industry", "software-infrastructure") not in with_peers.calls


def test_peer_failure_falls_back_to_absolute_bands(client, with_peers):
    with_peers.peers_error = MarketDataError("blocked")
    body = client.get("/api/stocks/MSFT").json()
    assert body["peers"] is None
    assert body["scores"]["valuation"]["breakdown"][0]["item"] == "Trailing P/E 33.4"
