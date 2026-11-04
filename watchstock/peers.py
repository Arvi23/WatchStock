"""Industry peer comparison: pure functions. Covered by tests/test_peers.py.

Peers are the largest US companies in the stock's Yahoo industry. Medians are taken over
the peers only (not the stock itself) and only when at least MIN_PEERS have a usable value.
"""

from statistics import median
from typing import Any

MIN_PEERS = 3

# field -> (label, valid range); values outside the range (e.g. negative or absurd P/E)
# are ignored for medians.
COMPARE_FIELDS: dict[str, tuple[str, tuple[float, float] | None]] = {
    "trailingPE": ("P/E", (0, 500)),
    "forwardPE": ("Fwd P/E", (0, 500)),
    "pegRatio": ("PEG", (0, 20)),
    "profitMargins": ("Net margin", None),
    "revenueGrowth": ("Revenue growth", None),
}


def _valid(field: str, value: Any) -> bool:
    if not isinstance(value, int | float):
        return False
    bounds = COMPARE_FIELDS[field][1]
    return bounds is None or bounds[0] < value < bounds[1]


def peer_medians(peers: list[dict]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for field in COMPARE_FIELDS:
        values = [p[field] for p in peers if _valid(field, p.get(field))]
        out[field] = round(median(values), 4) if len(values) >= MIN_PEERS else None
    return out


def build_comparison(
    ticker: str, name: str, metrics: dict, peers: list[dict], industry: str | None
) -> dict[str, Any]:
    peers = [p for p in peers if p.get("ticker") != ticker]
    medians = peer_medians(peers)
    relative = {}
    for field, med in medians.items():
        value = metrics.get(field)
        if med and _valid(field, value):
            relative[field] = round((value / med - 1) * 100, 1)
    self_row = {"ticker": ticker, "name": name, "is_self": True,
                **{f: metrics.get(f) for f in (*COMPARE_FIELDS, "marketCap")}}  # fmt: skip
    rows = [self_row] + [{**p, "is_self": False} for p in peers]
    return {
        "industry": industry,
        "rows": rows,
        "medians": medians,
        "relative": relative,
        "peer_count": len(peers),
    }
