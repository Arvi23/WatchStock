"""Scoring: pure functions from Yahoo metrics to explainable 0-100 scores.

No I/O here. Every score returns a `breakdown` list the UI shows on click, so
any formula change must keep the breakdown honest. Covered by tests/test_scoring.py.

NOTE (batch 1): formulas are ported unchanged from the hackathon version except
that the news penalty in the health scores is gone (it depended on the removed
embedding model). Known formula problems are listed in docs/HANDOFF.md, batch 2.
"""


def calculate_financial_risk(metrics: dict):
    """
    Compute a simple risk score based on key financial ratios.
    Each missing or unhealthy metric adds risk points.
    """
    risk_points = 0
    flags = []

    cr = metrics.get("currentRatio")
    if cr is None:
        risk_points += 1
        flags.append("currentRatio missing (1 pt)")
    elif cr < 1.0:
        risk_points += 2
        flags.append(f"currentRatio < 1.0 ({cr}) (2 pts)")
    elif 1.0 <= cr <= 1.2:
        risk_points += 1
        flags.append(f"currentRatio between 1.0 and 1.2 ({cr}) (1 pt)")

    rg = metrics.get("revenueGrowth")
    if rg is None:
        risk_points += 1
        flags.append("revenueGrowth missing (1 pt)")
    elif rg < -0.05:
        risk_points += 2
        flags.append(f"revenueGrowth < -0.05 ({rg}) (2 pts)")
    elif -0.05 <= rg <= 0:
        risk_points += 1
        flags.append(f"revenueGrowth between -0.05 and 0 ({rg}) (1 pt)")

    pm = metrics.get("profitMargins")
    if pm is None:
        risk_points += 1
        flags.append("profitMargins missing (1 pt)")
    elif pm < 0:
        risk_points += 2
        flags.append(f"profitMargins < 0 ({pm}) (2 pts)")
    elif 0 <= pm <= 0.05:
        risk_points += 1
        flags.append(f"profitMargins between 0 and 0.05 ({pm}) (1 pt)")

    if risk_points <= 1:
        severity = "Low"
    elif risk_points <= 3:
        severity = "Medium"
    else:
        severity = "High"

    return {
        "total_risk_points": risk_points,
        "severity_level": severity,
        "flags": flags,
    }


def norm_cr(val):
    return max(0, min(100, (val / 2.0) * 100))


def norm_qr(val):
    return max(0, min(100, (val / 1.5) * 100))


def norm_margin(val):
    return max(0, min(100, (val / 0.25) * 100))


def norm_de(val):
    return max(0, min(100, 100 - (val / 2.0)))


def norm_beta(val):
    return max(0, min(100, 100 - ((val - 0.5) * 50)))


def _weighted(components: list) -> float:
    total_w = sum(w for _, _, w in components)
    return sum(s * (w / total_w) for _, s, w in components) if total_w > 0 else 50.0


def score_fundamental(metrics: dict) -> dict:
    """Liquidity, profitability, and solvency — 0-100."""
    comps = []
    cr = metrics.get("currentRatio")
    if cr is not None:
        comps.append(("Current Ratio", norm_cr(cr), 0.20))
    qr = metrics.get("quickRatio")
    if qr is not None:
        comps.append(("Quick Ratio", norm_qr(qr), 0.15))
    pm = metrics.get("profitMargins")
    if pm is not None:
        comps.append(("Profit Margins", norm_margin(pm), 0.20))
    rg = metrics.get("revenueGrowth")
    if rg is not None:
        comps.append(("Revenue Growth", max(0, min(100, (rg + 0.2) / 0.5 * 100)), 0.15))
    de = metrics.get("debtToEquity")
    if de is not None:
        comps.append(("Debt/Equity", norm_de(de), 0.15))
    fcf = metrics.get("freeCashflow")
    mc = metrics.get("marketCap") or 1
    if fcf is not None:
        fcf_s = max(0, min(100, 50 + (fcf / mc) * 1000)) if mc > 0 else (60 if fcf > 0 else 30)
        comps.append(("Free Cash Flow", fcf_s, 0.15))
    eg = metrics.get("earningsGrowth")
    if eg is not None:
        comps.append(("Earnings Growth", max(0, min(100, 50 + eg * 150)), 0.10))
    if not comps:
        return {"score": 50, "breakdown": []}
    score = round(_weighted(comps))
    return {
        "score": score,
        "breakdown": [
            {"item": n, "score": round(s), "weight": f"{w * 100:.0f}%"} for n, s, w in comps
        ],
    }


def score_analyst(metrics: dict, analyst_data: dict) -> dict:
    """Analyst consensus and price-target upside — 0-100."""
    rec = analyst_data.get("recommendationMean")
    n = analyst_data.get("numberOfAnalystOpinions") or 0
    tgt = analyst_data.get("targetMeanPrice")
    cur = metrics.get("currentPrice")

    if rec is None:
        return {"score": 50, "breakdown": [], "upside_pct": None}

    base = max(0, min(100, (5 - rec) / 4 * 100))
    confidence = 1.0 if n >= 8 else (0.75 if n >= 3 else 0.5)
    score = base * confidence

    upside_pct = None
    consensus = (analyst_data.get("recommendationKey") or "N/A").replace("_", " ").title()
    breakdown = [
        {
            "item": f"Consensus: {consensus}",
            "score": round(base),
        }
    ]
    if tgt and cur and cur > 0:
        upside_pct = round((tgt - cur) / cur * 100, 1)
        delta = (
            10 if upside_pct > 30 else (5 if upside_pct > 10 else (-10 if upside_pct < 0 else 0))
        )
        score = max(0, min(100, score + delta))
        breakdown.append({"item": f"Price-target upside: {upside_pct:+.1f}%", "impact": delta})
    if n > 0:
        breakdown.append({"item": f"{n} analysts · {confidence * 100:.0f}% confidence weight"})

    return {"score": round(score), "breakdown": breakdown, "upside_pct": upside_pct}


def score_valuation(metrics: dict) -> dict:
    """How cheap/expensive vs earnings and its own 52-week range. 0-100, higher = cheaper."""
    comps = []
    pos_pct = None

    pe = metrics.get("trailingPE")
    if pe is not None and 0 < pe < 500:
        pe_s = (
            90
            if pe < 10
            else 80
            if pe < 15
            else 68
            if pe < 20
            else 55
            if pe < 25
            else 40
            if pe < 35
            else 25
            if pe < 50
            else 12
        )
        comps.append(("Trailing P/E", pe_s, 0.25))
    fpe = metrics.get("forwardPE")
    if fpe is not None and 0 < fpe < 500:
        fpe_s = (
            90
            if fpe < 10
            else 80
            if fpe < 15
            else 68
            if fpe < 20
            else 55
            if fpe < 25
            else 38
            if fpe < 35
            else 18
        )
        comps.append(("Forward P/E", fpe_s, 0.20))
    peg = metrics.get("pegRatio")
    if peg is not None and 0 < peg < 20:
        peg_s = (
            95
            if peg < 0.5
            else 82
            if peg < 1.0
            else 65
            if peg < 1.5
            else 50
            if peg < 2.0
            else 32
            if peg < 3.0
            else 15
        )
        comps.append(("PEG Ratio", peg_s, 0.25))
    high52 = metrics.get("fiftyTwoWeekHigh")
    low52 = metrics.get("fiftyTwoWeekLow")
    cur = metrics.get("currentPrice")
    if high52 and low52 and cur and high52 > low52:
        pos_pct = round((cur - low52) / (high52 - low52) * 100, 1)
        pos_s = (
            85
            if pos_pct < 20
            else 72
            if pos_pct < 40
            else 55
            if pos_pct < 60
            else 38
            if pos_pct < 80
            else 20
        )
        comps.append(("52-Week Position", pos_s, 0.20))
    pb = metrics.get("priceToBook")
    if pb is not None and pb > 0:
        pb_s = 88 if pb < 1 else 72 if pb < 2 else 58 if pb < 3 else 42 if pb < 5 else 22
        comps.append(("Price/Book", pb_s, 0.10))

    if not comps:
        return {"score": 50, "breakdown": [], "position_pct": None}
    score = round(_weighted(comps))
    return {
        "score": score,
        "breakdown": [
            {"item": n, "score": round(s), "weight": f"{w * 100:.0f}%"} for n, s, w in comps
        ],
        "position_pct": pos_pct,
    }


def score_smart_money(metrics: dict) -> dict:
    """Insider ownership, institutional positioning, short interest — 0-100."""
    comps = []
    flags = []

    ins_pct = metrics.get("heldPercentInsiders")
    if ins_pct is not None:
        ins_s = (
            85
            if ins_pct > 0.20
            else 72
            if ins_pct > 0.10
            else 58
            if ins_pct > 0.05
            else 44
            if ins_pct > 0.01
            else 30
        )
        comps.append(("Insider Ownership", ins_s, 0.35))

    inst_pct = metrics.get("heldPercentInstitutions")
    if inst_pct is not None:
        if inst_pct > 0.90:
            inst_s = 40
            flags.append("Heavily institutionally owned — crowded trade risk")
        elif inst_pct > 0.80:
            inst_s = 55
        elif inst_pct >= 0.50:
            inst_s = 72
        elif inst_pct >= 0.20:
            inst_s = 60
        else:
            inst_s = 52
        comps.append(("Institutional Ownership", inst_s, 0.30))

    short_pct = metrics.get("shortPercentOfFloat")
    if short_pct is not None:
        if short_pct > 0.20:
            short_s = 22
            flags.append(
                f"Very high short interest ({short_pct * 100:.1f}%) — heavy bearish conviction "
                "or extreme squeeze candidate"
            )
        elif short_pct > 0.10:
            short_s = 35
            flags.append(
                f"High short interest ({short_pct * 100:.1f}%) — watch for squeeze "
                "or continued selling"
            )
        elif short_pct > 0.05:
            short_s = 52
        elif short_pct > 0.02:
            short_s = 62
        else:
            short_s = 72
        comps.append(("Short Interest", short_s, 0.35))

    if not comps:
        return {"score": 50, "breakdown": [], "flags": []}
    score = round(_weighted(comps))
    return {
        "score": score,
        "breakdown": [
            {"item": n, "score": round(s), "weight": f"{w * 100:.0f}%"} for n, s, w in comps
        ],
        "flags": flags,
    }


def calculate_opportunity_score(f: dict, a: dict, v: dict, s: dict) -> dict:
    """Composite opportunity score from all four dimensions."""
    score = round(f["score"] * 0.25 + a["score"] * 0.30 + v["score"] * 0.30 + s["score"] * 0.15)
    label, color = (
        ("Strong Opportunity", "#4caf50")
        if score >= 75
        else ("Moderate Opportunity", "#8bc34a")
        if score >= 60
        else ("Neutral", "#ffc107")
        if score >= 45
        else ("Weak", "#ff9800")
        if score >= 30
        else ("Avoid", "#f44336")
    )
    return {
        "score": score,
        "label": label,
        "color": color,
        "sub": {
            "fundamental": f["score"],
            "analyst": a["score"],
            "valuation": v["score"],
            "smart_money": s["score"],
        },
    }


def get_geo_risk_penalty(country: str):
    if not country:
        return 0, "No data"
    tier_3_tax_havens = [
        "Bermuda",
        "Cayman Islands",
        "British Virgin Islands",
        "Cyprus",
        "Bahamas",
    ]
    tier_4_conflict = ["Israel", "Ukraine", "Russia", "Iran", "Yemen", "Syria"]
    tier_2_emerging = ["Brazil", "India", "Mexico", "South Africa", "China"]

    if country in tier_4_conflict:
        return 40, "High geopolitical risk / Conflict"
    elif country in tier_3_tax_havens:
        return 20, "Tax Haven / Regulatory scrutiny"
    elif country in tier_2_emerging:
        return 10, "Emerging Market Volatility"
    return 0, "Safe/Tier 1"


def calculate_health_scores(metrics: dict):
    """
    Compute Short-Term (ST) and Long-Term (LT) health scores (0-100).

    Short-Term: weighted average of Current Ratio, Quick Ratio, Profit Margins.
    Long-Term: weighted average of Debt/Equity, Beta, minus a geo-risk penalty.
    """
    st_components = []
    if (cr := metrics.get("currentRatio")) is not None:
        st_components.append(("Current Ratio", norm_cr(cr), 0.4))
    if (qr := metrics.get("quickRatio")) is not None:
        st_components.append(("Quick Ratio", norm_qr(qr), 0.3))
    if (pm := metrics.get("profitMargins")) is not None:
        st_components.append(("Profit Margins", norm_margin(pm), 0.3))
    st_base = _weighted(st_components) if st_components else 50.0

    lt_components = []
    if (de := metrics.get("debtToEquity")) is not None:
        lt_components.append(("Debt to Equity", norm_de(de), 0.5))
    if (beta := metrics.get("beta")) is not None:
        lt_components.append(("Beta", norm_beta(beta), 0.5))
    lt_base = _weighted(lt_components) if lt_components else 50.0

    geo_pen, geo_reason = get_geo_risk_penalty(metrics.get("country") or "")
    lt_final = max(0, lt_base - geo_pen)

    st_breakdown = [{"item": "Short-Term Base (Liquidity & Margins)", "impact": round(st_base, 1)}]
    lt_breakdown = [{"item": "Long-Term Base (Solvency & Volatility)", "impact": round(lt_base, 1)}]
    if geo_pen > 0:
        lt_breakdown.append({"item": f"Geo-Risk Penalty ({geo_reason})", "impact": -geo_pen})

    return {
        "short_term": {"score": round(st_base), "breakdown": st_breakdown},
        "long_term": {"score": round(lt_final), "breakdown": lt_breakdown},
    }


def compute_all(metrics: dict, analyst_data: dict) -> dict:
    """Every score for one stock, in the shape the UI expects."""
    f = score_fundamental(metrics)
    a = score_analyst(metrics, analyst_data)
    v = score_valuation(metrics)
    s = score_smart_money(metrics)
    return {
        "health_scores": calculate_health_scores(metrics),
        "scores": {
            "fundamental": f,
            "analyst": a,
            "valuation": v,
            "smart_money": s,
            "opportunity": calculate_opportunity_score(f, a, v, s),
        },
        "risk_analysis": calculate_financial_risk(metrics),
    }
