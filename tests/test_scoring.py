"""Scoring formulas. Change these tests deliberately when a formula changes."""

import pytest

from tests.conftest import SAMPLE_METRICS, SAMPLE_PROFILE
from watchstock import scoring


def _walk_scores(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "score" and v is not None:
                yield v
            else:
                yield from _walk_scores(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_scores(v)


def test_compute_all_shape_and_ranges():
    out = scoring.compute_all(SAMPLE_METRICS, SAMPLE_PROFILE["analyst_data"])
    assert set(out) == {"scores", "safety", "risk_analysis"}
    assert set(out["scores"]) == {"quality", "valuation", "analyst", "smart_money", "opportunity"}
    assert set(out["safety"]) == {"short_term", "long_term", "flags"}
    assert all(0 <= s <= 100 for s in _walk_scores(out))


def test_no_data_is_neutral_and_explained():
    out = scoring.compute_all({}, {})
    for key in ("quality", "valuation", "analyst", "smart_money"):
        assert out["scores"][key]["score"] == 50
        assert out["scores"][key]["breakdown"], key
    assert out["safety"]["short_term"]["score"] == 50


def test_opportunity_components_and_weights():
    out = scoring.compute_all(SAMPLE_METRICS, SAMPLE_PROFILE["analyst_data"])
    comps = out["scores"]["opportunity"]["components"]
    assert [c["key"] for c in comps] == ["quality", "valuation", "analyst", "smart_money"]
    assert sum(scoring.OPPORTUNITY_WEIGHTS.values()) == pytest.approx(1.0)
    expected = sum(out["scores"][k]["score"] * w for k, w in scoring.OPPORTUNITY_WEIGHTS.items())
    assert out["scores"]["opportunity"]["score"] == round(expected)


def test_opportunity_labels():
    def pillars(v):
        return {k: {"score": v} for k in scoring.OPPORTUNITY_WEIGHTS}

    assert scoring.calculate_opportunity_score(pillars(80))["label"] == "Strong Opportunity"
    assert scoring.calculate_opportunity_score(pillars(50))["label"] == "Neutral"
    assert scoring.calculate_opportunity_score(pillars(10))["label"] == "Avoid"


# --------------------------------------------------------------------- analyst


def test_analyst_few_analysts_pull_toward_neutral_not_down():
    strong_buy_thin = scoring.score_analyst(
        {}, {"recommendationMean": 1.5, "numberOfAnalystOpinions": 2}
    )
    sell_wide = scoring.score_analyst(
        {}, {"recommendationMean": 4.0, "numberOfAnalystOpinions": 20}
    )
    assert strong_buy_thin["score"] > 50 > sell_wide["score"]
    # raw 87.5 -> 50 + 37.5 * 0.5
    assert strong_buy_thin["score"] == 69


def test_analyst_upside_adjustment():
    a = scoring.score_analyst(
        {"currentPrice": 100},
        {"recommendationMean": 3.0, "numberOfAnalystOpinions": 10, "targetMeanPrice": 140},
    )
    assert a["upside_pct"] == 40.0
    assert a["score"] == 60  # neutral 50 + 10 for >30% upside


def test_analyst_no_coverage():
    assert scoring.score_analyst({}, {})["score"] == 50


# --------------------------------------------------------------------- quality


def test_quality_skips_fcf_yield_on_currency_mismatch():
    metrics = {
        "freeCashflow": 900e9,
        "marketCap": 1e12,
        "financialCurrency": "TWD",
        "currency": "USD",
    }
    q = scoring.score_quality(metrics)
    assert q["score"] == 50  # nothing else to score
    assert any("skipped" in b["item"] for b in q["breakdown"])


def test_quality_fcf_yield_when_currencies_match():
    q = scoring.score_quality(
        {"freeCashflow": 50e9, "marketCap": 1e12, "currency": "USD", "financialCurrency": "USD"}
    )
    assert q["score"] == 100  # 5% yield


def test_quality_profitable_grower_beats_shrinking_loss_maker():
    good = scoring.score_quality(
        {"profitMargins": 0.3, "revenueGrowth": 0.2, "earningsGrowth": 0.2}
    )
    bad = scoring.score_quality(
        {"profitMargins": -0.1, "revenueGrowth": -0.15, "earningsGrowth": -0.3}
    )
    assert good["score"] > 80 and bad["score"] < 20


# ------------------------------------------------------------------- valuation


def test_valuation_penalises_loss_makers_instead_of_skipping():
    loss = scoring.score_valuation({"trailingEps": -1.2, "forwardEps": -0.5})
    assert loss["score"] == 10
    assert "losses" in loss["breakdown"][0]["item"]


def test_valuation_52w_position_is_labelled_contrarian():
    v = scoring.score_valuation(
        {"currentPrice": 150, "fiftyTwoWeekLow": 100, "fiftyTwoWeekHigh": 200}
    )
    assert v["position_pct"] == 50.0
    assert "contrarian" in v["breakdown"][0]["item"]


def test_valuation_cheap_beats_expensive():
    cheap = scoring.score_valuation(
        {"trailingPE": 9, "forwardPE": 8, "pegRatio": 0.8, "priceToBook": 0.9}
    )
    pricey = scoring.score_valuation(
        {"trailingPE": 80, "forwardPE": 60, "pegRatio": 4, "priceToBook": 12}
    )
    assert cheap["score"] > 80 and pricey["score"] < 25


# ---------------------------------------------------------------------- safety


def test_safety_known_values():
    s = scoring.calculate_safety(
        {"currentRatio": 2.0, "quickRatio": 1.5, "debtToEquity": 100, "beta": 1.5}
    )
    assert s["short_term"]["score"] == 100
    assert s["long_term"]["score"] == 50  # D/E 1.0x -> 50, beta 1.5 -> 50


def test_geo_is_a_flag_not_a_penalty():
    base = {"debtToEquity": 0, "beta": 0.5}
    us = scoring.calculate_safety({**base, "country": "United States"})
    ru = scoring.calculate_safety({**base, "country": "Russia"})
    assert us["long_term"]["score"] == ru["long_term"]["score"] == 100
    assert ru["flags"] and not us["flags"]


def test_debt_to_equity_skipped_for_financials():
    s = scoring.calculate_safety({"sector": "Financial Services", "debtToEquity": 900, "beta": 1.0})
    assert s["long_term"]["score"] == 75  # beta only
    assert any("skipped" in b["item"] for b in s["long_term"]["breakdown"])


def test_breakdown_items_have_uniform_shape():
    out = scoring.compute_all(SAMPLE_METRICS, SAMPLE_PROFILE["analyst_data"])
    pillars = [out["scores"][k] for k in scoring.OPPORTUNITY_WEIGHTS]
    for block in [*pillars, out["safety"]["short_term"], out["safety"]["long_term"]]:
        for item in block["breakdown"]:
            assert set(item) == {"item", "score", "weight", "note"}


def test_risk_flags():
    r = scoring.calculate_financial_risk(
        {"currentRatio": 0.8, "revenueGrowth": -0.1, "profitMargins": -0.02}
    )
    assert r["total_risk_points"] == 6
    assert r["severity_level"] == "High"
    assert scoring.calculate_financial_risk({})["total_risk_points"] == 0
