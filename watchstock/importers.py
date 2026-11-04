"""Portfolio file import: Tradeville export, plus a simple generic CSV. Pure parsing.

Tradeville "Portofoliu" export (observed 2026-11-04):
- first line `SEP=<tab>` (an Excel hint), then a tab-separated header
- `simbol`: market prefix + symbol + optional lowercase venue/class letter,
  e.g. `US.APLD`, `US.COHRn`, `US.OUSTc`; cash rows are e.g. `USD`
- `sold` = shares, `costm` = average cost per share, `ppiata` = market price,
  `valuta` = currency, `nume` = name, `isin`, `market`, `tsim` = `actiuni` (shares) / `bani` (cash)
- decimal point is `.`

Generic CSV: a header with ticker/symbol, shares/quantity and avg_cost/cost columns,
comma or semicolon separated. Resolving tickers against Yahoo happens in the route.
"""

import csv
import io
import re
from typing import Any


class ImportError_(ValueError):  # noqa: N801 (avoid shadowing the builtin ImportError)
    """The file couldn't be understood."""


def decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1250"):  # cp1250: older Romanian Windows exports
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def parse_number(text: Any) -> float | None:
    """'1234.56', '1.234,56', '1,234.56', '182,50' -> float."""
    s = str(text or "").strip().replace(" ", "").replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        s = (
            s.replace(".", "").replace(",", ".")
            if s.rfind(",") > s.rfind(".")
            else s.replace(",", "")
        )
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


# Tradeville market prefix -> Yahoo suffix ("" = US, no suffix).
_MARKET_SUFFIX = {"US": "", "RO": ".RO", "BVB": ".RO"}


def tradeville_to_yahoo(symbol: str, market: str | None = None) -> str:
    """`US.COHRn` -> `COHR`, `US.BRK.B` -> `BRK-B`, `TLV` (market RO) -> `TLV.RO`."""
    symbol = symbol.strip()
    prefix, dot, rest = symbol.partition(".")
    if dot and prefix.isupper() and 1 < len(prefix) <= 3 and rest:
        code, base = prefix, rest
    else:
        code, base = (market or "").strip().upper(), symbol
    base = re.sub(r"[a-z]+$", "", base)  # venue/class letter: COHRn -> COHR
    suffix = _MARKET_SUFFIX.get(code)
    if suffix is None:
        return base.upper()  # unknown market: the ISIN fallback will have to resolve it
    if suffix == "":
        return base.upper().replace(".", "-")  # Yahoo writes share classes with '-'
    return base.upper() + suffix


def _rows(text: str) -> tuple[list[dict[str, str]], str]:
    lines = text.lstrip("﻿").splitlines()
    sep = None
    if lines and lines[0].upper().startswith("SEP="):
        sep = lines[0][4:5] or "\t"
        lines = lines[1:]
    body = "\n".join(lines)
    if sep is None:
        first = lines[0] if lines else ""
        sep = max(("\t", ";", ","), key=first.count)
    reader = csv.DictReader(io.StringIO(body), delimiter=sep)
    rows = [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in reader]
    return rows, sep


def _pick(row: dict[str, str], *names: str) -> str:
    for n in names:
        if row.get(n):
            return row[n]
    return ""


def parse(text: str) -> dict[str, Any]:
    """-> {"format", "rows": [position], "skipped": [{"symbol", "reason"}]}."""
    rows, _ = _rows(text)
    if not rows:
        raise ImportError_("The file is empty or not a table.")
    headers = set(rows[0])
    positions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    if {"simbol", "sold", "costm"} <= headers:
        fmt = "tradeville"
        for r in rows:
            symbol = r.get("simbol", "")
            if not symbol:
                continue
            kind = r.get("tsim", "").lower()
            if kind and kind != "actiuni":
                reason = "cash" if kind == "bani" else kind
                amount = parse_number(r.get("sold"))
                skipped.append({"symbol": symbol, "reason": reason, "amount": amount,
                                "currency": r.get("valuta")})  # fmt: skip
                continue
            positions.append({
                "source_symbol": symbol,
                "ticker": tradeville_to_yahoo(symbol, r.get("market")),
                "name": r.get("nume", ""),
                "isin": r.get("isin", ""),
                "shares": parse_number(r.get("sold")),
                "avg_cost": parse_number(r.get("costm")),
                "currency": r.get("valuta") or None,
                "broker_price": parse_number(r.get("ppiata")),
            })  # fmt: skip
    else:

        def column(*names: str) -> str | None:
            return next((c for c in names if c in headers), None)

        ticker_col = column("ticker", "symbol", "simbol")
        shares_col = column("shares", "quantity", "qty", "sold", "cantitate")
        cost_col = column("avg_cost", "average_cost", "cost", "avg price", "costm", "pret mediu")
        if not (ticker_col and shares_col and cost_col):
            raise ImportError_(
                "Unrecognised file. Use a Tradeville portfolio export, or a CSV with "
                "ticker, shares and avg_cost columns."
            )
        fmt = "generic"
        for r in rows:
            if not r.get(ticker_col):
                continue
            positions.append({
                "source_symbol": r[ticker_col],
                "ticker": r[ticker_col].strip().upper(),
                "name": _pick(r, "name", "nume", "company"),
                "isin": _pick(r, "isin"),
                "shares": parse_number(r.get(shares_col)),
                "avg_cost": parse_number(r.get(cost_col)),
                "currency": _pick(r, "currency", "valuta") or None,
                "broker_price": None,
            })  # fmt: skip

    valid = []
    for p in positions:
        if not p["shares"] or p["shares"] <= 0 or p["avg_cost"] is None or p["avg_cost"] < 0:
            skipped.append({"symbol": p["source_symbol"], "reason": "no shares or cost"})
        else:
            valid.append(p)
    return {"format": fmt, "rows": valid, "skipped": skipped}
