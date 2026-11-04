"""The "Today" panel: what's worth knowing about the owner's stocks right now.

Pure functions (routes fetch the inputs). Covered by tests/test_today.py.
"""

from datetime import date, timedelta
from typing import Any

LOOKAHEAD_DAYS = 14  # upcoming earnings / ex-dividend dates
RATINGS_DAYS = 7  # analyst rating changes this recent
INSIDER_DAYS = 30  # insider purchases this recent (sales are routine and skipped)
BIG_MOVE_PCT = 3.0  # |day change| at or above this is worth a line

# Lower sorts first.
_PRIORITY = {"big_move": 0, "earnings": 1, "ex_dividend": 2, "rating": 3, "insider_buy": 4}


def _parse(d: str | None) -> date | None:
    try:
        return date.fromisoformat(d[:10]) if d else None
    except ValueError:
        return None


def _days_label(delta: int) -> str:
    return "today" if delta == 0 else "tomorrow" if delta == 1 else f"in {delta} days"


def build_events(
    tickers: dict[str, dict],
    quotes: dict[str, dict],
    events: dict[str, dict],
    today: date,
) -> list[dict[str, Any]]:
    """tickers: {ticker: {"name", "held": bool}}; quotes/events: per ticker, may be missing."""
    out: list[dict[str, Any]] = []

    def add(ticker: str, kind: str, when: date | None, text: str) -> None:
        meta = tickers.get(ticker, {})
        out.append({
            "ticker": ticker,
            "name": meta.get("name") or ticker,
            "held": bool(meta.get("held")),
            "kind": kind,
            "date": when.isoformat() if when else None,
            "text": text,
        })  # fmt: skip

    horizon = today + timedelta(days=LOOKAHEAD_DAYS)
    for ticker in tickers:
        q = quotes.get(ticker) or {}
        chg = q.get("change_pct")
        if chg is not None and abs(chg) >= BIG_MOVE_PCT:
            add(ticker, "big_move", today, f"{'Up' if chg > 0 else 'Down'} {abs(chg):.1f}% today")

        ev = events.get(ticker) or {}
        upcoming = [
            d for d in map(_parse, ev.get("earnings_dates") or []) if d and today <= d <= horizon
        ]
        if upcoming:
            d = min(upcoming)
            add(ticker, "earnings", d, f"Earnings {_days_label((d - today).days)} ({d:%a %d %b})")

        exd = _parse(ev.get("ex_dividend_date"))
        if exd and today <= exd <= horizon:
            when = _days_label((exd - today).days)
            text = f"Ex-dividend {when}: own it before {exd:%d %b} to get the next dividend"
            add(ticker, "ex_dividend", exd, text)

        for r in ev.get("upgrades_downgrades") or []:
            d = _parse(r.get("date"))
            if not d or (today - d).days > RATINGS_DAYS or d > today:
                continue
            action = (r.get("action") or "").lower()
            verb = {"up": "upgraded", "down": "downgraded", "init": "started coverage at",
                    "main": "kept", "reit": "reiterated"}.get(action, "rated")  # fmt: skip
            frm = r.get("from_grade") or ""
            to = r.get("to_grade") or "?"
            detail = f"{frm} → {to}" if frm and verb in ("upgraded", "downgraded") else to
            add(ticker, "rating", d, f"{r.get('firm') or 'An analyst'} {verb} {detail}")

        for t in ev.get("insider_transactions") or []:
            d = _parse(t.get("date"))
            text = f"{t.get('transaction', '')} {t.get('text', '')}".lower()
            if (
                not d
                or (today - d).days > INSIDER_DAYS
                or "purchase" not in text
                and "buy" not in text
            ):
                continue
            value = t.get("value")
            amount = f" (${value / 1e6:.1f}M)" if value and value >= 1e5 else ""
            who = t.get("insider") or "An insider"
            add(ticker, "insider_buy", d, f"Insider buy: {who.title()}{amount}")

    # Held positions first, then by importance, then soonest/most recent.
    def key(e: dict) -> tuple:
        d = _parse(e["date"]) or today
        return (not e["held"], _PRIORITY[e["kind"]], abs((d - today).days), e["ticker"])

    return sorted(out, key=key)
