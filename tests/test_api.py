"""End-to-end API behaviour against fake providers."""

from watchstock import config
from watchstock.providers.openrouter import LLMError
from watchstock.providers.yahoo import MarketDataError


def profile_calls(fake):
    return [c for c in fake.calls if c[0] == "profile"]


# ------------------------------------------------------------ stock snapshots


def test_first_fetch_is_live_then_served_from_cache(client, fake_yahoo):
    r = client.get("/api/stocks/msft")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "MSFT"
    assert body["source"] == "live"
    assert body["company_name"] == "Microsoft Corporation"
    assert body["company_domain"] == "microsoft.com"
    assert body["as_of"]
    assert body["news"][0]["title"] == "Microsoft beats estimates"
    assert body["scores"]["opportunity"]["score"] >= 0
    assert body["ai_analysis"] is None

    again = client.get("/api/stocks/MSFT").json()
    assert again["source"] == "cache"
    assert len(profile_calls(fake_yahoo)) == 1


def test_refresh_forces_live_fetch(client, fake_yahoo):
    client.get("/api/stocks/MSFT")
    assert client.get("/api/stocks/MSFT?refresh=true").json()["source"] == "live"
    assert len(profile_calls(fake_yahoo)) == 2


def test_snapshot_expires_after_ttl(client, fake_yahoo, monkeypatch):
    client.get("/api/stocks/MSFT")
    monkeypatch.setattr(config, "SNAPSHOT_TTL_SECONDS", 0)
    assert client.get("/api/stocks/MSFT").json()["source"] == "live"
    assert len(profile_calls(fake_yahoo)) == 2


def test_failed_fetch_returns_502_and_is_not_cached(client, fake_yahoo):
    fake_yahoo.profile_error = MarketDataError("429 Too Many Requests")
    r = client.get("/api/stocks/MSFT")
    assert r.status_code == 502
    assert "429" in r.json()["detail"]

    fake_yahoo.profile_error = None
    assert client.get("/api/stocks/MSFT").json()["source"] == "live"


def test_failed_refresh_falls_back_to_stale_snapshot(client, fake_yahoo, monkeypatch):
    client.get("/api/stocks/MSFT")
    monkeypatch.setattr(config, "SNAPSHOT_TTL_SECONDS", 0)
    fake_yahoo.profile_error = MarketDataError("timeout")
    body = client.get("/api/stocks/MSFT").json()
    assert body["stale"] is True
    assert body["source"] == "cache"
    assert "timeout" in body["warnings"][0]


def test_news_failure_still_returns_stock(client, fake_yahoo):
    fake_yahoo.news_error = MarketDataError("news down")
    body = client.get("/api/stocks/MSFT").json()
    assert body["news"] == []
    assert body["warnings"] == ["News could not be loaded."]


def test_search(client):
    assert client.get("/api/search?q=micro").json()[0]["ticker"] == "MSFT"


# ------------------------------------------------------------------ analysis


def test_analysis_requires_api_key(client):
    r = client.post("/api/stocks/MSFT/analysis")
    assert r.status_code == 502
    assert "API key" in r.json()["detail"]


def test_analysis_is_stored_and_returned_with_stock(client, fake_llm):
    client.put("/api/settings", json={"llm_api_key": "sk-test", "llm_model": "test/model"})
    r = client.post("/api/stocks/MSFT/analysis")
    assert r.status_code == 200
    report = r.json()
    assert report["executive_summary"] == "Solid."
    assert report["model"] == "test/model"
    assert report["created_at"]
    assert fake_llm.requests[0]["api_key"] == "sk-test"

    stock = client.get("/api/stocks/MSFT").json()
    assert stock["ai_analysis"]["executive_summary"] == "Solid."


def test_api_key_can_come_from_environment(client, fake_llm, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-env")
    assert client.post("/api/stocks/MSFT/analysis").status_code == 200
    assert fake_llm.requests[0]["api_key"] == "sk-env"


def test_invalid_llm_reply_is_not_stored(client, fake_llm):
    client.put("/api/settings", json={"llm_api_key": "sk-test"})
    fake_llm.reply = "Sorry, I can't do that."
    r = client.post("/api/stocks/MSFT/analysis")
    assert r.status_code == 502
    assert client.get("/api/stocks/MSFT").json()["ai_analysis"] is None


def test_llm_transport_error_is_reported(client, fake_llm):
    client.put("/api/settings", json={"llm_api_key": "sk-test"})
    fake_llm.error = LLMError("OpenRouter returned 401: bad key")
    r = client.post("/api/stocks/MSFT/analysis")
    assert r.status_code == 502
    assert "401" in r.json()["detail"]


# ---------------------------------------------------------------------- chat


def test_chat_does_not_duplicate_the_question(client, fake_llm):
    client.put("/api/settings", json={"llm_api_key": "sk-test"})
    fake_llm.reply = '{"reply_text": "Hi", "ui_action": null}'
    stock = client.get("/api/stocks/MSFT").json()
    r = client.post(
        "/api/chat",
        json={
            "question": "Is it cheap?",
            "stock": stock,
            "history": [{"role": "user", "content": "Is it cheap?"}],
        },
    )
    assert r.json()["reply_text"] == "Hi"
    msgs = fake_llm.requests[-1]["messages"]
    assert [m["content"] for m in msgs[1:]] == ["Is it cheap?"]
    assert "Microsoft" in msgs[0]["content"]


def test_chat_non_json_reply_is_passed_through(client, fake_llm):
    client.put("/api/settings", json={"llm_api_key": "sk-test"})
    fake_llm.reply = "plain text"
    assert client.post("/api/chat", json={"question": "hi"}).json()["reply_text"] == "plain text"


# ------------------------------------------------------- watchlist / settings


def test_watchlist_roundtrip(client):
    client.post("/api/watchlist", json={"ticker": "msft", "company_name": "Microsoft"})
    items = client.get("/api/watchlist").json()
    assert items[0]["ticker"] == "MSFT"
    assert items[0]["price"] == 100.0
    client.delete("/api/watchlist/MSFT")
    assert client.get("/api/watchlist").json() == []


def test_settings_never_return_the_key(client):
    body = client.put("/api/settings", json={"llm_api_key": "sk-secret"}).json()
    assert body["llm_api_key_set"] is True
    assert "sk-secret" not in str(body)
    assert client.get("/api/settings").json()["llm_model"] == config.DEFAULT_LLM_MODEL
    client.put("/api/settings", json={"llm_api_key": ""})
    assert client.get("/api/settings").json()["llm_api_key_set"] is False


# -------------------------------------------------------------------- market


def test_market_widgets_are_cached(client, fake_yahoo):
    assert client.get("/api/market/indices").json()[0]["name"] == "S&P 500"
    client.get("/api/market/indices")
    assert fake_yahoo.calls.count(("indices",)) == 1


def test_market_widgets_degrade_to_empty(client, fake_yahoo):
    fake_yahoo.market_error = MarketDataError("blocked")
    assert client.get("/api/market/indices").json() == []
    assert client.get("/api/market/news").json() == []
    assert client.get("/api/market/movers").json() == {"gainers": [], "losers": []}


# -------------------------------------------------------------------- static


def test_index_and_health(client):
    assert "WatchStock" in client.get("/").text
    assert client.get("/api/health").json()["ok"] is True


# ------------------------------------------------------------------- batch 2


def test_snapshot_from_older_schema_is_refetched(client, fake_yahoo):
    from watchstock import store

    store.save_snapshot(
        "MSFT", "Microsoft", {"ticker": "MSFT", "health_scores": {}}, store.utcnow_iso()
    )
    body = client.get("/api/stocks/MSFT").json()
    assert body["source"] == "live"
    assert "safety" in body


def test_stock_includes_tradingview_symbol(client):
    assert client.get("/api/stocks/TLV.RO").json()["tradingview_symbol"] == "BVB:TLV"


def test_second_report_sees_the_previous_one(client, fake_llm):
    import json

    client.put("/api/settings", json={"llm_api_key": "sk-test"})
    client.post("/api/stocks/MSFT/analysis")
    client.post("/api/stocks/MSFT/analysis")
    first_ctx = json.loads(fake_llm.requests[0]["messages"][1]["content"])
    second_ctx = json.loads(fake_llm.requests[1]["messages"][1]["content"])
    assert "previous_report" not in first_ctx
    assert second_ctx["previous_report"]["executive_summary"] == "Solid."


def test_default_model_used_when_unset(client, fake_llm):
    from watchstock import config

    client.put("/api/settings", json={"llm_api_key": "sk-test"})
    client.post("/api/stocks/MSFT/analysis")
    assert fake_llm.requests[0]["model"] == config.DEFAULT_LLM_MODEL
