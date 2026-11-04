"""Portfolio math: pure functions from holdings + quotes + cached company info.

No I/O here (routes gather the inputs). Covered by tests/test_portfolio.py.

Currencies: positions are grouped by currency and totals are per currency. We don't
convert with FX rates: a guessed rate would make every total quietly wrong, and the
owner's portfolio is mostly USD anyway. Weights and concentration are measured within
each currency group.
"""

from collections import defaultdict
from typing import Any

POSITION_LIMIT = 0.20  # one position above 20% of its currency group gets flagged
SECTOR_LIMIT = 0.40  # one sector above 40% gets flagged
MIN_POSITIONS_FOR_FLAGS = 3  # with 1-2 positions, "concentrated" is obvious and just noise


def _round(x: float | None, digits: int = 2) -> float | None:
    return None if x is None else round(x, digits)


def build_position(holding: dict, quote: dict | None, info: dict | None) -> dict[str, Any]:
    """One holding with live value, P/L, day change and expected dividends."""
    quote, info = quote or {}, info or {}
    shares, avg_cost = holding["shares"], holding["avg_cost"]
    price = quote.get("price")
    change_pct = quote.get("change_pct")
    currency = holding.get("currency") or quote.get("currency") or info.get("currency") or "USD"

    cost = shares * avg_cost
    value = shares * price if price is not None else None
    pl = value - cost if value is not None else None
    pl_pct = pl / cost * 100 if pl is not None and cost > 0 else None
    # value today vs yesterday's close: v - v / (1 + c)
    day_change = (
        value * change_pct / (100 + change_pct)
        if value is not None and change_pct is not None and change_pct > -100
        else None
    )
    rate = info.get("dividend_rate")  # annual dividend per share, price currency
    dividends = shares * rate if rate else 0.0
    yield_on_cost = rate / avg_cost * 100 if rate and avg_cost > 0 else None

    return {
        "ticker": holding["ticker"],
        "name": info.get("name") or holding["ticker"],
        "sector": info.get("sector") or "Unknown",
        "country": info.get("country") or "Unknown",
        "currency": currency,
        "shares": shares,
        "avg_cost": avg_cost,
        "notes": holding.get("notes") or "",
        "price": price,
        "change_pct": change_pct,
        "cost": _round(cost),
        "value": _round(value),
        "pl": _round(pl),
        "pl_pct": _round(pl_pct),
        "day_change": _round(day_change),
        "annual_dividends": _round(dividends),
        "yield_on_cost": _round(yield_on_cost),
        "weight": None,  # filled in by build_portfolio
    }


def build_portfolio(
    holdings: list[dict], quotes: dict[str, dict], info: dict[str, dict]
) -> dict[str, Any]:
    positions = [
        build_position(h, quotes.get(h["ticker"]), info.get(h["ticker"])) for h in holdings
    ]
    groups: dict[str, list[dict]] = defaultdict(list)
    for p in positions:
        groups[p["currency"]].append(p)

    totals: dict[str, dict] = {}
    allocation: dict[str, dict] = {}
    flags: list[str] = []

    # Biggest currency group first (for the owner: USD), then alphabetical.
    order = sorted(groups, key=lambda c: (-len(groups[c]), c))
    for currency in order:
        group = groups[currency]
        priced = [p for p in group if p["value"] is not None]
        value = sum(p["value"] for p in priced)
        cost = sum(p["cost"] for p in priced)
        day = sum(p["day_change"] or 0 for p in priced)
        pl = value - cost
        totals[currency] = {
            "value": _round(value),
            "cost": _round(cost),
            "pl": _round(pl),
            "pl_pct": _round(pl / cost * 100) if cost > 0 else None,
            "day_change": _round(day),
            "day_change_pct": _round(day / (value - day) * 100) if value - day > 0 else None,
            "annual_dividends": _round(sum(p["annual_dividends"] for p in group)),
            "positions": len(group),
        }

        sectors: dict[str, float] = defaultdict(float)
        for p in priced:
            p["weight"] = _round(p["value"] / value * 100, 1) if value > 0 else None
            sectors[p["sector"]] += p["value"]
        allocation[currency] = {
            "positions": [{"label": p["ticker"], "weight": p["weight"]} for p in
                          sorted(priced, key=lambda p: -p["value"])],
            "sectors": [{"label": s, "weight": _round(v / value * 100, 1)} for s, v in
                        sorted(sectors.items(), key=lambda kv: -kv[1])] if value > 0 else [],
        }  # fmt: skip

        if len(priced) >= MIN_POSITIONS_FOR_FLAGS and value > 0:
            for p in priced:
                if p["value"] / value > POSITION_LIMIT:
                    flags.append(
                        f"{p['ticker']} is {p['weight']:.0f}% of your {currency} holdings "
                        f"(above {POSITION_LIMIT:.0%})."
                    )
            for sector, v in sectors.items():
                if sector != "Unknown" and v / value > SECTOR_LIMIT:
                    flags.append(
                        f"{sector} is {v / value:.0%} of your {currency} holdings "
                        f"(above {SECTOR_LIMIT:.0%})."
                    )

    for p in positions:
        if p["value"] is None:
            flags.append(f"No live price for {p['ticker']}; it's left out of the totals.")

    positions.sort(key=lambda p: (order.index(p["currency"]), -(p["value"] or 0)))
    return {"positions": positions, "totals": totals, "allocation": allocation, "flags": flags}


def info_from_snapshot(snapshot: dict | None) -> dict[str, Any]:
    """The static-ish company facts the portfolio needs, from a cached stock snapshot.

    Sector, country and dividend rate change rarely, so any snapshot age is fine.
    """
    if not snapshot:
        return {}
    m = snapshot.get("financial_data", {}).get("metrics", {})
    return {
        "name": snapshot.get("company_name"),
        "sector": m.get("sector"),
        "country": m.get("country"),
        "currency": m.get("currency"),
        "dividend_rate": m.get("dividendRate"),
    }
