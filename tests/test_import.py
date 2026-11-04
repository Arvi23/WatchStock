"""Portfolio import: Tradeville parsing (synthetic fixture), ticker resolution, commit."""

from pathlib import Path

import pytest

from watchstock import importers

SAMPLE = (Path(__file__).parent / "fixtures" / "tradeville_sample.csv").read_bytes()


@pytest.mark.parametrize(
    ("symbol", "market", "expected"),
    [("US.APLD", "US", "APLD"), ("US.COHRn", "US", "COHR"), ("US.OUSTc", "US", "OUST"),
     ("US.BRK.B", "US", "BRK-B"), ("TLV", "RO", "TLV.RO"), ("SNP", "BVB", "SNP.RO")],
)  # fmt: skip
def test_tradeville_symbol_mapping(symbol, market, expected):
    assert importers.tradeville_to_yahoo(symbol, market) == expected


@pytest.mark.parametrize(("text", "value"), [("1234.56", 1234.56), ("1.234,56", 1234.56),
                                             ("1,234.56", 1234.56), ("182,50", 182.5), ("", None)])  # fmt: skip
def test_parse_number(text, value):
    assert importers.parse_number(text) == value


def test_parse_tradeville_export():
    out = importers.parse(importers.decode(SAMPLE))
    assert out["format"] == "tradeville"
    assert [r["ticker"] for r in out["rows"]] == ["MSFT", "COHR", "BRK-B", "TLV.RO", "OLDNAME"]
    msft = out["rows"][0]
    assert msft["shares"] == 10 and msft["avg_cost"] == pytest.approx(300.123456)
    assert msft["currency"] == "USD" and msft["isin"] == "US5949181045"
    reasons = {s["symbol"]: s["reason"] for s in out["skipped"]}
    assert reasons == {"USD": "cash", "US.ZERO": "no shares or cost"}


def test_parse_generic_csv_with_semicolons_and_decimal_commas():
    out = importers.parse("Ticker;Shares;Avg_Cost\nAAPL;10;182,50\nmsft;2;300\n")
    assert out["format"] == "generic"
    assert [(r["ticker"], r["shares"], r["avg_cost"]) for r in out["rows"]] == [
        ("AAPL", 10, 182.5),
        ("MSFT", 2, 300),
    ]


def test_unrecognised_file_is_rejected():
    with pytest.raises(importers.ImportError_):
        importers.parse("foo,bar\n1,2\n")


# ---------------------------------------------------------------------- API


def test_preview_resolves_tickers_with_isin_fallback(client, fake_yahoo):
    fake_yahoo.unknown_tickers = {"OLDNAME"}
    fake_yahoo.isin_map = {"US0000000001": "NEWNAME"}
    body = client.post("/api/portfolio/import/preview", json={"content": SAMPLE.decode()}).json()
    status = {r["ticker"]: r["status"] for r in body["rows"]}
    assert status == {"MSFT": "ok", "COHR": "ok", "BRK-B": "ok", "TLV.RO": "ok", "NEWNAME": "isin"}
    assert next(r for r in body["rows"] if r["ticker"] == "NEWNAME")["original_ticker"] == "OLDNAME"
    assert client.get("/api/portfolio").json()["positions"] == []  # preview saves nothing


def test_preview_marks_unresolvable_rows(client, fake_yahoo):
    fake_yahoo.unknown_tickers = {"OLDNAME"}
    rows = client.post("/api/portfolio/import/preview", json={"content": SAMPLE.decode()}).json()[
        "rows"
    ]
    assert next(r for r in rows if r["ticker"] == "OLDNAME")["status"] == "not_found"


def test_preview_applies_user_corrections(client, fake_yahoo):
    fake_yahoo.unknown_tickers = {"OLDNAME"}
    body = {"content": SAMPLE.decode(), "overrides": {"US.OLDNAME": " newname "}}
    rows = client.post("/api/portfolio/import/preview", json=body).json()["rows"]
    fixed = next(r for r in rows if r["source_symbol"] == "US.OLDNAME")
    assert fixed["ticker"] == "NEWNAME" and fixed["status"] == "ok"


def test_preview_rejects_garbage(client):
    r = client.post("/api/portfolio/import/preview", json={"content": "hello"})
    assert r.status_code == 422


def test_commit_replace_keeps_notes_and_fills_company_info(client, fake_yahoo):
    client.put(
        "/api/portfolio", json={"ticker": "MSFT", "shares": 1, "avg_cost": 1, "notes": "Cloud"}
    )
    client.put("/api/portfolio", json={"ticker": "OLD", "shares": 1, "avg_cost": 1})
    rows = [{"ticker": "MSFT", "shares": 10, "avg_cost": 300, "currency": "USD"},
            {"ticker": "COHR", "shares": 2, "avg_cost": 207.27, "currency": "USD"}]  # fmt: skip
    r = client.post("/api/portfolio/import/commit", json={"rows": rows, "mode": "replace"})
    assert r.json() == {"ok": True, "imported": 2, "mode": "replace"}
    positions = {p["ticker"]: p for p in client.get("/api/portfolio").json()["positions"]}
    assert set(positions) == {"MSFT", "COHR"}  # OLD removed by "replace"
    assert positions["MSFT"]["shares"] == 10 and positions["MSFT"]["notes"] == "Cloud"
    # COHR was never opened: sector comes from the light company-info fetch after import
    assert positions["COHR"]["sector"] == "Technology"
    assert ("basics", "COHR") in fake_yahoo.calls
    assert ("basics", "MSFT") not in fake_yahoo.calls  # had a snapshot already


def test_commit_merge_adds_and_updates(client):
    client.put("/api/portfolio", json={"ticker": "MSFT", "shares": 1, "avg_cost": 1})
    client.put("/api/portfolio", json={"ticker": "AAPL", "shares": 3, "avg_cost": 100})
    rows = [
        {"ticker": "MSFT", "shares": 10, "avg_cost": 300},
        {"ticker": "COHR", "shares": 2, "avg_cost": 200},
    ]
    client.post("/api/portfolio/import/commit", json={"rows": rows, "mode": "merge"})
    shares = {p["ticker"]: p["shares"] for p in client.get("/api/portfolio").json()["positions"]}
    assert shares == {"MSFT": 10, "AAPL": 3, "COHR": 2}


def test_commit_validation(client):
    bad = {"rows": [{"ticker": "MSFT", "shares": 0, "avg_cost": 1}], "mode": "replace"}
    assert client.post("/api/portfolio/import/commit", json=bad).status_code == 422
    assert (
        client.post(
            "/api/portfolio/import/commit", json={"rows": [], "mode": "replace"}
        ).status_code
        == 422
    )


def test_portfolio_load_fills_missing_company_info(client, fake_yahoo):
    from watchstock import store

    store.holding_upsert("COHR", 2, 200, "USD", "")  # e.g. app closed mid warm-up
    first = client.get("/api/portfolio").json()
    assert first["info_pending"] == 1
    second = client.get("/api/portfolio").json()  # background task ran after the first
    assert second["info_pending"] == 0 and second["positions"][0]["sector"] == "Technology"


def test_failed_company_info_is_not_saved(client, fake_yahoo, monkeypatch):
    from watchstock import store
    from watchstock.providers import yahoo
    from watchstock.providers.yahoo import MarketDataError

    def boom(ticker):
        raise MarketDataError("offline")

    monkeypatch.setattr(yahoo, "fetch_company_basics", boom)
    store.holding_upsert("COHR", 2, 200, "USD", "")
    client.get("/api/portfolio")
    assert store.get_company_info("COHR") is None
