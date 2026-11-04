"""Scoring: pure functions from Yahoo metrics to explainable 0-100 scores.

No I/O here. Covered by tests/test_scoring.py.

Two separate lenses, so no metric is counted twice:

* **Opportunity** (is it worth buying?) = weighted mix of four pillars:
  Quality (profitability, growth, cash), Valuation, Analyst view, Smart money.
* **Safety** (how fragile is it?) = Liquidity (short-term) and Solvency &
  volatility (long-term). Shown in the sidebar.

Every score returns a `breakdown`: a list of
`{"item": label, "score": 0-100 | None, "weight": "25%" | None, "note": str | None}`.
Items with `score: None` are explanations (skipped inputs, flags) and don't count.
Missing data is skipped, never guessed. With no usable inputs a score is a neutral 50.

Units: Yahoo reports debtToEquity in percent (150 = 1.5x). Ratios like margins and
growth are fractions (0.25 = 25%). dividendYield is normalised to a fraction in
providers/yahoo.py.
"""

from typing import Any

Breakdown = list[dict[str, Any]]


def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))


def _item(label: str, score: float | None = None, weight: float | None = None,
          note: str | None = None) -> dict[str, Any]:  # fmt: skip
    return {
        "item": label,
        "score": None if score is None else round(score),
        "weight": None if weight is None else f"{weight * 100:.0f}%",
        "note": note,
    }


def _combine(components: list[tuple[str, float, float]], extra: Breakdown | None = None) -> dict:
    """Weighted average of (label, score, weight); weights renormalised over present inputs."""
    breakdown = [_item(label, s, w) for label, s, w in components] + (extra or [])
    total = sum(w for _, _, w in components)
    if total == 0:
        return {"score": 50, "breakdown": breakdown + [_item("Not enough data: neutral 50")]}
    score = sum(s * w for _, s, w in components) / total
    return {"score": round(score), "breakdown": breakdown}


def _bucket(value: float, thresholds: list[tuple[float, float]], otherwise: float) -> float:
    """First score whose upper bound exceeds `value`."""
    for upper, score in thresholds:
        if value < upper:
            return score
    return otherwise


# --------------------------------------------------------------------- quality


def currency_mismatch(metrics: dict) -> str | None:
    """Return a note if financial statements and the share price use different currencies.

    Happens for foreign companies listed in the US (e.g. TSM: statements in TWD,
    price and market cap in USD). Ratios we compute by mixing the two are skipped.
    """
    fin, px = metrics.get("financialCurrency"), metrics.get("currency")
    if fin and px and fin != px:
        return f"statements in {fin}, price in {px}"
    return None


def score_quality(metrics: dict) -> dict:
    """Profitability, growth and cash generation."""
    comps: list[tuple[str, float, float]] = []
    extra: Breakdown = []

    if (pm := metrics.get("profitMargins")) is not None:
        comps.append((f"Net margin {pm * 100:.1f}%", _clamp(pm / 0.25 * 100), 0.25))
    if (om := metrics.get("operatingMargins")) is not None:
        comps.append((f"Operating margin {om * 100:.1f}%", _clamp(om / 0.30 * 100), 0.15))
    if (rg := metrics.get("revenueGrowth")) is not None:
        # -20% -> 0, +30% -> 100
        comps.append((f"Revenue growth {rg * 100:+.1f}%", _clamp((rg + 0.2) / 0.5 * 100), 0.25))
    if (eg := metrics.get("earningsGrowth")) is not None:
        comps.append((f"Earnings growth {eg * 100:+.1f}%", _clamp(50 + eg * 150), 0.15))

    fcf, mcap = metrics.get("freeCashflow"), metrics.get("marketCap")
    if fcf is not None and mcap:
        if note := currency_mismatch(metrics):
            extra.append(_item("Free-cash-flow yield skipped", note=note))
        else:
            fcf_yield = fcf / mcap
            # 0% -> 50, +5% -> 100, -5% -> 0
            comps.append((f"FCF yield {fcf_yield * 100:.1f}%", _clamp(50 + fcf_yield * 1000), 0.20))
    return _combine(comps, extra)


# ------------------------------------------------------------------- valuation


def score_valuation(metrics: dict) -> dict:
    """How cheap the stock is vs earnings, book value and its own 52-week range.

    Higher = cheaper. P/E bands are the same for every industry (a known
    simplification until peer comparison exists).
    """
    comps: list[tuple[str, float, float]] = []
    extra: Breakdown = []
    pos_pct = None

    pe, eps = metrics.get("trailingPE"), metrics.get("trailingEps")
    if pe is not None and 0 < pe < 500:
        bands = [(10, 90), (15, 80), (20, 68), (25, 55), (35, 40), (50, 25)]
        comps.append((f"Trailing P/E {pe:.1f}", _bucket(pe, bands, 12), 0.25))
    elif eps is not None and eps <= 0:
        comps.append(("Trailing P/E: losses over last 12 months", 10, 0.25))

    fpe, feps = metrics.get("forwardPE"), metrics.get("forwardEps")
    if fpe is not None and 0 < fpe < 500:
        bands = [(10, 90), (15, 80), (20, 68), (25, 55), (35, 38)]
        comps.append((f"Forward P/E {fpe:.1f}", _bucket(fpe, bands, 18), 0.20))
    elif feps is not None and feps <= 0:
        comps.append(("Forward P/E: losses expected", 10, 0.20))

    peg = metrics.get("pegRatio")
    if peg is not None and 0 < peg < 20:
        bands = [(0.5, 95), (1.0, 82), (1.5, 65), (2.0, 50), (3.0, 32)]
        comps.append((f"PEG {peg:.2f}", _bucket(peg, bands, 15), 0.25))

    pb = metrics.get("priceToBook")
    if pb is not None and pb > 0:
        comps.append(
            (f"Price/Book {pb:.2f}", _bucket(pb, [(1, 88), (2, 72), (3, 58), (5, 42)], 22), 0.15)
        )

    high, low, cur = (
        metrics.get(k) for k in ("fiftyTwoWeekHigh", "fiftyTwoWeekLow", "currentPrice")
    )
    if high and low and cur and high > low:
        pos_pct = round((cur - low) / (high - low) * 100, 1)
        bands = [(20, 85), (40, 72), (60, 55), (80, 38)]
        comps.append(
            (f"52-week position {pos_pct:.0f}% (contrarian: lower = cheaper)",
             _bucket(pos_pct, bands, 20), 0.15)
        )  # fmt: skip

    result = _combine(comps, extra)
    result["position_pct"] = pos_pct
    return result


# --------------------------------------------------------------------- analyst


def score_analyst(metrics: dict, analyst_data: dict) -> dict:
    """Wall Street consensus and price-target upside.

    With few analysts the consensus is pulled toward neutral (50) rather than
    scaled down, so a thinly covered Strong Buy isn't scored like a Sell.
    """
    rec = analyst_data.get("recommendationMean")  # 1 = strong buy ... 5 = strong sell
    n = analyst_data.get("numberOfAnalystOpinions") or 0
    target, cur = analyst_data.get("targetMeanPrice"), metrics.get("currentPrice")

    if rec is None:
        return {
            "score": 50,
            "breakdown": [_item("No analyst coverage: neutral 50")],
            "upside_pct": None,
        }

    raw = _clamp((5 - rec) / 4 * 100)
    confidence = 1.0 if n >= 8 else 0.75 if n >= 3 else 0.5
    score = 50 + (raw - 50) * confidence
    consensus = (analyst_data.get("recommendationKey") or "n/a").replace("_", " ").title()
    breakdown = [
        _item(f"Consensus: {consensus} ({rec:.1f} on a 1-5 scale)", raw),
        _item(f"{n} analyst{'s' if n != 1 else ''}: {confidence * 100:.0f}% trust in consensus",
              note="few analysts pull the score toward 50"),
    ]  # fmt: skip

    upside = None
    if target and cur and cur > 0:
        upside = round((target - cur) / cur * 100, 1)
        delta = 10 if upside > 30 else 5 if upside > 10 else -10 if upside < 0 else 0
        score += delta
        breakdown.append(_item(f"Price-target upside {upside:+.1f}%", note=f"{delta:+d} points"))
    return {"score": round(_clamp(score)), "breakdown": breakdown, "upside_pct": upside}


# ----------------------------------------------------------------- smart money


def score_smart_money(metrics: dict) -> dict:
    """Insider ownership, institutional positioning, short interest."""
    comps: list[tuple[str, float, float]] = []
    flags: list[str] = []

    if (ins := metrics.get("heldPercentInsiders")) is not None:
        bands = [(0.01, 30), (0.05, 44), (0.10, 58), (0.20, 72)]
        comps.append((f"Insider ownership {ins * 100:.1f}%", _bucket(ins, bands, 85), 0.35))

    if (inst := metrics.get("heldPercentInstitutions")) is not None:
        if inst > 0.90:
            s = 40
            flags.append("Heavily institutionally owned: crowded-trade risk")
        else:
            s = _bucket(inst, [(0.20, 52), (0.50, 60), (0.80, 72)], 55)
        comps.append((f"Institutional ownership {inst * 100:.1f}%", s, 0.30))

    if (short := metrics.get("shortPercentOfFloat")) is not None:
        if short > 0.20:
            s = 22
            flags.append(
                f"Very high short interest ({short * 100:.1f}%): "
                "strong bearish bets or squeeze risk"
            )
        elif short > 0.10:
            s = 35
            flags.append(f"High short interest ({short * 100:.1f}%)")
        else:
            s = _bucket(short, [(0.02, 72), (0.05, 62)], 52)
        comps.append((f"Short interest {short * 100:.1f}% of float", s, 0.35))

    result = _combine(comps)
    result["flags"] = flags
    return result


# ----------------------------------------------------------------- opportunity

OPPORTUNITY_WEIGHTS = {"quality": 0.30, "valuation": 0.30, "analyst": 0.25, "smart_money": 0.15}
PILLAR_LABELS = {
    "quality": "Quality",
    "valuation": "Valuation",
    "analyst": "Analyst",
    "smart_money": "Smart Money",
}


def calculate_opportunity_score(pillars: dict[str, dict]) -> dict:
    score = round(sum(pillars[k]["score"] * w for k, w in OPPORTUNITY_WEIGHTS.items()))
    label, color = (
        ("Strong Opportunity", "#4caf50") if score >= 75 else
        ("Moderate Opportunity", "#8bc34a") if score >= 60 else
        ("Neutral", "#ffc107") if score >= 45 else
        ("Weak", "#ff9800") if score >= 30 else
        ("Avoid", "#f44336")
    )  # fmt: skip
    components = [
        {
            "key": k,
            "label": PILLAR_LABELS[k],
            "score": pillars[k]["score"],
            "weight": f"{w * 100:.0f}%",
        }
        for k, w in OPPORTUNITY_WEIGHTS.items()
    ]
    return {"score": score, "label": label, "color": color, "components": components}


# ---------------------------------------------------------------------- safety

_GEO_FLAGS = {
    **dict.fromkeys(
        ["Israel", "Ukraine", "Russia", "Iran", "Yemen", "Syria"], "conflict-exposed region"
    ),
    **dict.fromkeys(
        ["Brazil", "India", "Mexico", "South Africa", "China", "Turkey"], "emerging market"
    ),
}


def calculate_safety(metrics: dict) -> dict:
    """Liquidity (short term) and solvency & volatility (long term)."""
    financial = (metrics.get("sector") or "") == "Financial Services"

    st: list[tuple[str, float, float]] = []
    st_extra: Breakdown = []
    if (cr := metrics.get("currentRatio")) is not None:
        st.append((f"Current ratio {cr:.2f}", _clamp(cr / 2.0 * 100), 0.55))
    if (qr := metrics.get("quickRatio")) is not None:
        st.append((f"Quick ratio {qr:.2f}", _clamp(qr / 1.5 * 100), 0.45))
    if financial and not st:
        st_extra.append(_item("Liquidity ratios aren't reported for banks/insurers"))

    lt: list[tuple[str, float, float]] = []
    lt_extra: Breakdown = []
    flags: list[str] = []
    de = metrics.get("debtToEquity")
    if de is not None and not financial:
        # Yahoo: percent. 0% -> 100, 200% (2x) -> 0
        lt.append((f"Debt/Equity {de / 100:.2f}x", _clamp(100 - de / 2.0), 0.5))
    elif de is not None:
        lt_extra.append(_item("Debt/Equity skipped", note="not meaningful for financial companies"))
    if (beta := metrics.get("beta")) is not None:
        # beta 0.5 -> 100, 1.5 -> 50, 2.5 -> 0
        lt.append((f"Beta {beta:.2f}", _clamp(100 - (beta - 0.5) * 50), 0.5))

    country = metrics.get("country")
    if country in _GEO_FLAGS:
        flag = f"Headquartered in {country} ({_GEO_FLAGS[country]})"
        flags.append(flag)
        lt_extra.append(_item(flag, note="informational, not scored"))

    return {
        "short_term": _combine(st, st_extra),
        "long_term": _combine(lt, lt_extra),
        "flags": flags,
    }


# ------------------------------------------------------------------- red flags


def calculate_financial_risk(metrics: dict) -> dict:
    """Plain-language red flags, fed to the LLM as hints."""
    points, flags = 0, []

    def check(key: str, label: str, bad: float, weak: float, fmt: str) -> None:
        nonlocal points
        v = metrics.get(key)
        if v is None:
            return
        if v < bad:
            points += 2
            flags.append(f"{label} {fmt.format(v)} (bad)")
        elif v <= weak:
            points += 1
            flags.append(f"{label} {fmt.format(v)} (weak)")

    check("currentRatio", "Current ratio", 1.0, 1.2, "{:.2f}")
    check("revenueGrowth", "Revenue growth", -0.05, 0.0, "{:+.1%}")
    check("profitMargins", "Net margin", 0.0, 0.05, "{:.1%}")
    severity = "Low" if points <= 1 else "Medium" if points <= 3 else "High"
    return {"total_risk_points": points, "severity_level": severity, "flags": flags}


# ------------------------------------------------------------------------ all


def compute_all(metrics: dict, analyst_data: dict) -> dict:
    """Every score for one stock, in the shape the UI expects."""
    pillars = {
        "quality": score_quality(metrics),
        "valuation": score_valuation(metrics),
        "analyst": score_analyst(metrics, analyst_data),
        "smart_money": score_smart_money(metrics),
    }
    return {
        "scores": {**pillars, "opportunity": calculate_opportunity_score(pillars)},
        "safety": calculate_safety(metrics),
        "risk_analysis": calculate_financial_risk(metrics),
    }
