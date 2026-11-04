"""Scoring formulas. These pin current behaviour; change them deliberately."""

import math

from tests.conftest import SAMPLE_METRICS, SAMPLE_PROFILE
from watchstock import scoring


def _all_scores_in_range(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "score":
                assert 0 <= v <= 100, obj
            else:
                _all_scores_in_range(v)
    elif isinstance(obj, list):
        for v in obj:
            _all_scores_in_range(v)


def test_compute_all_shape_and_ranges():
    out = scoring.compute_all(SAMPLE_METRICS, SAMPLE_PROFILE["analyst_data"])
    assert set(out) == {"health_scores", "scores", "risk_analysis"}
    assert set(out["scores"]) == {
        "fundamental",
        "analyst",
        "valuation",
        "smart_money",
        "opportunity",
    }
    _all_scores_in_range(out)


def test_compute_all_with_no_data_is_neutral():
    out = scoring.compute_all({}, {})
    assert out["scores"]["fundamental"]["score"] == 50
    assert out["scores"]["analyst"]["score"] == 50
    assert out["health_scores"]["short_term"]["score"] == 50
    assert out["health_scores"]["long_term"]["score"] == 50


def test_health_scores_known_values():
    h = scoring.calculate_health_scores(
        {"currentRatio": 2.0, "quickRatio": 1.5, "profitMargins": 0.25}
    )
    assert h["short_term"]["score"] == 100
    h = scoring.calculate_health_scores({"debtToEquity": 100, "beta": 1.5})
    # D/E 100% -> 50, beta 1.5 -> 50
    assert h["long_term"]["score"] == 50


def test_geo_penalty_applies_to_long_term_only():
    base = scoring.calculate_health_scores(
        {"debtToEquity": 0, "beta": 0.5, "country": "United States"}
    )
    risky = scoring.calculate_health_scores({"debtToEquity": 0, "beta": 0.5, "country": "Russia"})
    assert base["long_term"]["score"] - risky["long_term"]["score"] == 40
    assert base["short_term"] == risky["short_term"]


def test_valuation_position_in_52w_range():
    v = scoring.score_valuation(
        {"currentPrice": 150, "fiftyTwoWeekLow": 100, "fiftyTwoWeekHigh": 200}
    )
    assert v["position_pct"] == 50.0


def test_analyst_upside():
    a = scoring.score_analyst(
        {"currentPrice": 100},
        {"recommendationMean": 2.0, "numberOfAnalystOpinions": 10, "targetMeanPrice": 120},
    )
    assert a["upside_pct"] == 20.0


def test_opportunity_label_thresholds():
    s = lambda v: {"score": v}  # noqa: E731
    assert (
        scoring.calculate_opportunity_score(s(80), s(80), s(80), s(80))["label"]
        == "Strong Opportunity"
    )
    assert scoring.calculate_opportunity_score(s(10), s(10), s(10), s(10))["label"] == "Avoid"


def test_risk_flags_for_missing_metrics():
    r = scoring.calculate_financial_risk({})
    assert r["total_risk_points"] == 3
    assert r["severity_level"] == "Medium"


def test_no_nan_leaks():
    out = scoring.compute_all({"marketCap": 0, "freeCashflow": 1e9}, {})
    fcf = [b for b in out["scores"]["fundamental"]["breakdown"] if b["item"] == "Free Cash Flow"]
    assert fcf and not math.isnan(fcf[0]["score"])
