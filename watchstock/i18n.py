"""Backend translations (English / Romanian), gettext style: the English text is the key.

The language comes from the `ws_lang` cookie (set by the UI's EN/RO switch). Middleware in
app.py stores it in a ContextVar for the request; `asyncio.to_thread` copies the context,
so code running in worker threads sees it too. Code that runs outside a request (tests,
scripts) gets English.

    tr("Net margin {pct}", pct=num(36.04, 1) + "%")  ->  "Marjă netă 36,0%" in Romanian

A missing translation falls back to English. tests/test_i18n.py checks that every
template passed to tr() has a Romanian entry.
"""

from contextvars import ContextVar

LANGUAGES = ("en", "ro")
_lang: ContextVar[str] = ContextVar("lang", default="en")


def set_lang(lang: str | None):
    return _lang.set(lang if lang in LANGUAGES else "en")


def reset_lang(token) -> None:
    _lang.reset(token)


def get_lang() -> str:
    return _lang.get()


def tr(text: str, **params) -> str:
    template = RO.get(text, text) if get_lang() == "ro" else text
    return template.format(**params) if params else template


def num(value: float, digits: int = 1, sign: bool = False) -> str:
    """Format a number with the current language's decimal separator."""
    s = f"{value:+.{digits}f}" if sign else f"{value:.{digits}f}"
    return s.replace(".", ",") if get_lang() == "ro" else s


def llm_language_instruction() -> str:
    """Appended to LLM system prompts. JSON keys and enum values stay English."""
    if get_lang() == "ro":
        return (
            "\n\nLANGUAGE: write every human-readable text value in Romanian (proper diacritics: "
            "ă, â, î, ș, ț). Keep JSON keys and enum values (e.g. BUY, intact) exactly as specified "
            "in English."
        )
    return ""


RO: dict[str, str] = {
    # ---- scoring: generic
    "Not enough data: neutral 50": "Date insuficiente: neutru 50",
    "statements in {fin}, price in {px}": "situațiile financiare în {fin}, prețul în {px}",
    # quality
    "Net margin {pct}": "Marjă netă {pct}",
    "Operating margin {pct}": "Marjă operațională {pct}",
    "Revenue growth {pct}": "Creșterea veniturilor {pct}",
    "Earnings growth {pct}": "Creșterea profitului {pct}",
    "Free-cash-flow yield skipped": "Randamentul fluxului de numerar liber a fost omis",
    "FCF yield {pct}": "Randament flux de numerar liber {pct}",
    # valuation
    "Trailing P/E": "P/E (ultimele 12 luni)",
    "Forward P/E": "P/E estimat",
    "{label} {pe} vs industry median {median} ({diff})": "{label} {pe} față de mediana industriei {median} ({diff})",
    "{label} {pe}": "{label} {pe}",
    "Trailing P/E: losses over last 12 months": "P/E (12 luni): pierderi în ultimele 12 luni",
    "Forward P/E: losses expected": "P/E estimat: se estimează pierderi",
    "PEG {v}": "PEG {v}",
    "Price/Book {v}": "Preț/Valoare contabilă {v}",
    "52-week position {pct} (contrarian: lower = cheaper)": "Poziția în intervalul pe 52 de săptămâni {pct} (contrarian: mai jos = mai ieftin)",
    # analyst
    "No analyst coverage: neutral 50": "Nicio acoperire de la analiști: neutru 50",
    "Consensus: {consensus} ({rec} on a 1-5 scale)": "Consens: {consensus} ({rec} pe o scară de 1-5)",
    "{n} analyst: {conf} trust in consensus": "{n} analist: {conf} încredere în consens",
    "{n} analysts: {conf} trust in consensus": "{n} analiști: {conf} încredere în consens",
    "few analysts pull the score toward 50": "puțini analiști trag scorul spre 50",
    "Price-target upside {pct}": "Potențial până la prețul țintă {pct}",
    "{delta} points": "{delta} puncte",
    "Strong Buy": "Cumpărare puternică",
    "Buy": "Cumpărare",
    "Hold": "Păstrare",
    "Underperform": "Sub piață",
    "Sell": "Vânzare",
    "Strong Sell": "Vânzare puternică",
    "N/A": "N/A",
    # smart money
    "Insider ownership {pct}": "Deținuți de insideri {pct}",
    "Heavily institutionally owned: crowded-trade risk": "Deținută masiv de instituții: risc de poziție aglomerată",
    "Institutional ownership {pct}": "Deținuți de instituții {pct}",
    "Very high short interest ({pct}): strong bearish bets or squeeze risk": "Vânzări în lipsă foarte mari ({pct}): pariuri puternice pe scădere sau risc de short squeeze",
    "High short interest ({pct})": "Vânzări în lipsă mari ({pct})",
    "Short interest {pct} of float": "Vânzări în lipsă {pct} din flotant",
    # opportunity
    "Quality": "Calitate",
    "Valuation": "Evaluare",
    "Analyst": "Analiști",
    "Smart Money": "Insideri și instituții",
    "Strong Opportunity": "Oportunitate puternică",
    "Moderate Opportunity": "Oportunitate moderată",
    "Neutral": "Neutru",
    "Weak": "Slab",
    "Avoid": "De evitat",
    # safety
    "Current ratio {v}": "Lichiditate curentă {v}",
    "Quick ratio {v}": "Lichiditate imediată {v}",
    "Liquidity ratios aren't reported for banks/insurers": "Indicatorii de lichiditate nu se raportează pentru bănci/asigurători",
    "Debt/Equity {v}x (debt load)": "Datorii/Capital propriu {v}x (nivelul datoriilor)",
    "Debt/Equity skipped": "Datorii/Capital propriu omis",
    "not meaningful for financial companies": "nu e relevant pentru companiile financiare",
    "Beta {v} (volatility vs the market)": "Beta {v} (volatilitatea față de piață)",
    "Held down by volatility; debt looks healthy": "Scăzut din cauza volatilității; datoriile arată bine",
    "Held down by debt; volatility looks healthy": "Scăzut din cauza datoriilor; volatilitatea arată bine",
    "Headquartered in {country} ({kind})": "Sediul în {country} ({kind})",
    "conflict-exposed region": "regiune expusă la conflicte",
    "emerging market": "piață emergentă",
    "informational, not scored": "informativ, nu intră în scor",
    # ---- portfolio flags
    "{ticker} is {pct} of your {cur} holdings (above {limit}).": "{ticker} reprezintă {pct} din deținerile tale în {cur} (peste {limit}).",
    "{sector} is {pct} of your {cur} holdings (above {limit}).": "Sectorul {sector} reprezintă {pct} din deținerile tale în {cur} (peste {limit}).",
    "No live price for {ticker}; it's left out of the totals.": "Nu există preț live pentru {ticker}; nu e inclus în totaluri.",
    "Unknown": "Necunoscut",
    # ---- today panel
    "today": "azi",
    "tomorrow": "mâine",
    "in {n} days": "în {n} zile",
    "Up {pct} today": "Crește {pct} azi",
    "Down {pct} today": "Scade {pct} azi",
    "Earnings {when} ({date})": "Rezultate financiare {when} ({date})",
    "Ex-dividend {when}: own it before {date} to get the next dividend": "Ex-dividend {when}: trebuie deținută înainte de {date} pentru următorul dividend",
    "{firm} upgraded {detail}": "{firm} a îmbunătățit recomandarea: {detail}",
    "{firm} downgraded {detail}": "{firm} a coborât recomandarea: {detail}",
    "{firm} started coverage at {detail}": "{firm} a început acoperirea cu {detail}",
    "{firm} kept {detail}": "{firm} a menținut {detail}",
    "{firm} reiterated {detail}": "{firm} a reiterat {detail}",
    "{firm} rated {detail}": "{firm} a acordat {detail}",
    "An analyst": "Un analist",
    "Insider buy: {who}{amount}": "Cumpărare de insider: {who}{amount}",
    "An insider": "Un insider",
    # ---- services / routes / analysis
    "News could not be loaded.": "Știrile nu au putut fi încărcate.",
    "Live data unavailable ({err}). Showing the last saved data.": "Datele live nu sunt disponibile ({err}). Se afișează ultimele date salvate.",
    "{ticker} isn't in the portfolio.": "{ticker} nu este în portofoliu.",
    "Add a 'why I own it' note to this position first (Edit).": "Adaugă mai întâi motivul pentru care deții poziția (Editează).",
    "No OpenRouter API key configured. Add one in Settings.": "Nu e configurată nicio cheie OpenRouter. Adaug-o în Setări.",
    "The model's reply wasn't valid JSON. Try again or pick another model.": "Răspunsul modelului nu a fost JSON valid. Încearcă din nou sau alege alt model.",
    "The model's reply was missing the executive summary.": "Răspunsul modelului nu conține rezumatul.",
    "The model's reply was missing a valid status or summary.": "Răspunsului modelului îi lipsește un status sau un rezumat valid.",
}
