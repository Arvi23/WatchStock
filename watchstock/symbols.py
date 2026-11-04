"""Ticker symbol translation between Yahoo Finance and other services."""

# Yahoo suffix -> TradingView exchange prefix. Yahoo: "TLV.RO", TradingView: "BVB:TLV".
_TRADINGVIEW_EXCHANGES = {
    "RO": "BVB",  # Bucharest
    "DE": "XETR",  # Xetra
    "F": "FWB",  # Frankfurt
    "L": "LSE",
    "PA": "EURONEXT",
    "AS": "EURONEXT",
    "BR": "EURONEXT",
    "LS": "EURONEXT",
    "MI": "MIL",
    "MC": "BME",
    "SW": "SIX",
    "VI": "VIE",
    "WA": "GPW",
    "ST": "OMXSTO",
    "CO": "OMXCOP",
    "HE": "OMXHEX",
    "OL": "OSL",
    "TO": "TSX",
    "V": "TSXV",
    "HK": "HKEX",
    "T": "TSE",
    "AX": "ASX",
    "NS": "NSE",
    "BO": "BSE",
    "KS": "KRX",
    "SA": "BMFBOVESPA",
}


def tradingview_symbol(yahoo_ticker: str) -> str:
    """Best-effort TradingView symbol for a Yahoo ticker. Unknown suffixes pass through."""
    ticker = yahoo_ticker.strip().upper()
    base, dot, suffix = ticker.rpartition(".")
    if not dot or suffix not in _TRADINGVIEW_EXCHANGES:
        # US share classes: Yahoo "BRK-B" is TradingView "BRK.B".
        return ticker.replace("-", ".")
    if suffix == "HK":
        base = base.lstrip("0") or "0"  # Yahoo "0700.HK" -> "HKEX:700"
    return f"{_TRADINGVIEW_EXCHANGES[suffix]}:{base}"
