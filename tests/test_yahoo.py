"""Provider normalisation, with yfinance replaced by stubs."""

import pytest

from watchstock.providers import yahoo


def test_normalize_news_new_shape():
    item = {
        "id": "x",
        "content": {
            "title": "T",
            "summary": "S",
            "pubDate": "2026-11-01T10:00:00Z",
            "provider": {"displayName": "Reuters"},
            "canonicalUrl": {"url": "https://r.com/a"},
        },
    }
    assert yahoo.normalize_news_item(item) == {
        "title": "T",
        "url": "https://r.com/a",
        "publisher": "Reuters",
        "published_at": "2026-11-01T10:00:00Z",
        "summary": "S",
    }


def test_normalize_news_old_shape():
    item = {"title": "T", "link": "https://y.com/b", "publisher": "Yahoo", "providerPublishTime": 0}
    out = yahoo.normalize_news_item(item)
    assert out["url"] == "https://y.com/b"
    assert out["publisher"] == "Yahoo"
    assert out["published_at"].startswith("1970-01-01")


def test_normalize_news_skips_items_without_url():
    assert yahoo.normalize_news_item({"content": {"title": "no link"}}) is None


class _StubTicker:
    def __init__(self, info):
        self.info = info
        self.upgrades_downgrades = None
        self.insider_transactions = None


def test_unknown_ticker_raises(monkeypatch):
    monkeypatch.setattr(yahoo.yf, "Ticker", lambda t: _StubTicker({"trailingPegRatio": None}))
    with pytest.raises(yahoo.MarketDataError, match="No data"):
        yahoo.fetch_profile("NOPE")


def test_profile_cleans_nan(monkeypatch):
    info = {"longName": "X Corp", "currentPrice": 10.0, "beta": float("nan")}
    monkeypatch.setattr(yahoo.yf, "Ticker", lambda t: _StubTicker(info))
    profile = yahoo.fetch_profile("X")
    assert profile["name"] == "X Corp"
    assert profile["metrics"]["currentPrice"] == 10.0
    assert profile["metrics"]["beta"] is None


def test_network_error_becomes_market_data_error(monkeypatch):
    def boom(_t):
        raise ConnectionError("blocked")

    monkeypatch.setattr(yahoo.yf, "Ticker", boom)
    with pytest.raises(yahoo.MarketDataError):
        yahoo.fetch_profile("MSFT")
