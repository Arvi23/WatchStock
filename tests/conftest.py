"""Shared fixtures. Tests never touch the network: providers are replaced by fakes."""

import copy

import pytest
from fastapi.testclient import TestClient

from watchstock import ttl_cache
from watchstock.providers import openrouter, yahoo

SAMPLE_METRICS = {
    "currentRatio": 1.35, "quickRatio": 1.1, "revenueGrowth": 0.12, "profitMargins": 0.36,
    "operatingMargins": 0.45, "grossMargins": 0.69, "earningsGrowth": 0.1, "trailingEps": 12.4,
    "forwardEps": 14.1, "debtToEquity": 30.3, "freeCashflow": 70e9, "totalRevenue": 280e9,
    "netIncomeToCommon": 100e9, "trailingPE": 33.4, "forwardPE": 29.3, "pegRatio": 2.1,
    "priceToBook": 10.2, "priceToSalesTrailingTwelveMonths": 12.0, "enterpriseToEbitda": 22.0,
    "currentPrice": 414.0, "fiftyTwoWeekHigh": 468.0, "fiftyTwoWeekLow": 344.0,
    "fiftyDayAverage": 420.0, "twoHundredDayAverage": 410.0, "marketCap": 3.08e12, "beta": 0.9,
    "dividendYield": 0.0088, "dividendRate": 3.64, "payoutRatio": 0.25,
    "shortPercentOfFloat": 0.008, "shortRatio": 1.9, "heldPercentInstitutions": 0.74,
    "heldPercentInsiders": 0.015, "country": "United States", "website": "https://www.microsoft.com",
    "sector": "Technology", "industry": "Software", "currency": "USD", "financialCurrency": "USD",
    "exchange": "NMS",
}  # fmt: skip

SAMPLE_PROFILE = {
    "name": "Microsoft Corporation",
    "metrics": SAMPLE_METRICS,
    "analyst_data": {
        "recommendationMean": 1.4,
        "recommendationKey": "strong_buy",
        "numberOfAnalystOpinions": 45,
        "targetMeanPrice": 500.0,
        "targetHighPrice": 600.0,
        "targetLowPrice": 420.0,
        "targetMedianPrice": 505.0,
    },  # fmt: skip
    "key_officers": [{"name": "Satya Nadella", "title": "Chairman & CEO"}],
    "upgrades_downgrades": [],
    "insider_transactions": [],
}

SAMPLE_NEWS = [
    {
        "title": "Microsoft beats estimates",
        "url": "https://example.com/msft",
        "publisher": "Example News",
        "published_at": "2026-11-03T12:00:00Z",
        "summary": "Cloud revenue up.",
    }
]


class FakeYahoo:
    """Records calls; behaviour is configurable per test."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.profile_error: Exception | None = None
        self.news_error: Exception | None = None
        self.market_error: Exception | None = None

    def fetch_profile(self, ticker):
        self.calls.append(("profile", ticker))
        if self.profile_error:
            raise self.profile_error
        return copy.deepcopy(SAMPLE_PROFILE)

    def fetch_news(self, ticker, count=20):
        self.calls.append(("news", ticker))
        if self.news_error:
            raise self.news_error
        return copy.deepcopy(SAMPLE_NEWS)

    def fetch_quotes(self, tickers):
        self.calls.append(("quotes", tuple(tickers)))
        return {t: {"price": 100.0, "change_pct": 1.5} for t in tickers}

    def _market(self, name, value):
        self.calls.append((name,))
        if self.market_error:
            raise self.market_error
        return value

    def fetch_indices(self):
        return self._market(
            "indices", [{"name": "S&P 500", "ticker": "^GSPC", "value": 6000.0, "change_pct": 0.4}]
        )

    def fetch_market_news(self, count=10):
        return self._market("market_news", copy.deepcopy(SAMPLE_NEWS))

    def fetch_movers(self, count=20):
        return self._market("movers", {"gainers": [], "losers": []})

    events: dict = {}
    # industry key -> list of peers; peer ticker -> key metrics. Empty = no peers.
    industries: dict = {}
    peer_metrics: dict = {}
    peers_error: Exception | None = None

    def fetch_industry_peers(self, industry_key, limit=8):
        self.calls.append(("industry", industry_key))
        if self.peers_error:
            raise self.peers_error
        return copy.deepcopy(self.industries.get(industry_key, []))[:limit]

    def fetch_key_metrics(self, ticker):
        self.calls.append(("peer", ticker))
        if ticker not in self.peer_metrics:
            raise yahoo.MarketDataError(f"No data found for ticker {ticker!r}")
        return copy.deepcopy(self.peer_metrics[ticker])

    def fetch_events(self, ticker):
        self.calls.append(("events", ticker))
        return copy.deepcopy(self.events.get(ticker, {}))

    def search(self, query, limit=6):
        self.calls.append(("search", query))
        return [
            {
                "name": "Microsoft Corporation",
                "ticker": "MSFT",
                "exchange": "NASDAQ",
                "type": "EQUITY",
            }
        ]


class FakeLLM:
    def __init__(self):
        self.reply = (
            '{"executive_summary": "Solid.", "verdict": {"action": "BUY", "confidence": 70}}'
        )
        self.error: Exception | None = None
        self.requests: list[dict] = []

    def complete(self, messages, *, api_key, model, json_mode=True):
        self.requests.append({"messages": messages, "api_key": api_key, "model": model})
        if not api_key:
            raise openrouter.LLMError("No OpenRouter API key configured. Add one in Settings.")
        if self.error:
            raise self.error
        return self.reply


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHSTOCK_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    ttl_cache.clear()
    yield
    ttl_cache.clear()


@pytest.fixture
def fake_yahoo(monkeypatch):
    fake = FakeYahoo()
    for name in ("fetch_profile", "fetch_news", "fetch_quotes", "fetch_indices",
                 "fetch_market_news", "fetch_movers", "search", "fetch_events",
                 "fetch_industry_peers", "fetch_key_metrics"):  # fmt: skip
        monkeypatch.setattr(yahoo, name, getattr(fake, name))
    return fake


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(openrouter, "complete", fake.complete)
    return fake


@pytest.fixture
def client(fake_yahoo, fake_llm, monkeypatch):
    monkeypatch.setattr("watchstock.app.load_dotenv", lambda *a, **k: None)
    from watchstock.app import create_app

    with TestClient(create_app()) as c:
        yield c
