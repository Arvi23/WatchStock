"""Translations stay complete: backend tr() templates, frontend t() strings, index.html text."""

import ast
import json
import re
import string
from html.parser import HTMLParser
from pathlib import Path

import pytest

from watchstock import i18n, scoring

ROOT = Path(__file__).resolve().parent.parent

# Templates passed to tr() through a variable (not a literal), so the AST scan can't see them.
DYNAMIC_TEMPLATES = [
    "{firm} upgraded {detail}", "{firm} downgraded {detail}", "{firm} started coverage at {detail}",
    "{firm} kept {detail}", "{firm} reiterated {detail}", "{firm} rated {detail}",
    "Up {pct} today", "Down {pct} today", "News could not be loaded.",
    "Held down by volatility; debt looks healthy", "Held down by debt; volatility looks healthy",
    "Trailing P/E", "Forward P/E", "Strong Buy", "Buy", "Hold", "Underperform", "Sell",
    *scoring.PILLAR_LABELS.values(), "Strong Opportunity", "Moderate Opportunity", "Neutral", "Weak", "Avoid",
    "conflict-exposed region", "emerging market",
]  # fmt: skip


def _tr_literals() -> set[str]:
    found = set()
    for path in (ROOT / "watchstock").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr" and node.args:
                arg = node.args[0]
                for c in [arg.body, arg.orelse] if isinstance(arg, ast.IfExp) else [arg]:
                    if isinstance(c, ast.Constant) and isinstance(c.value, str):
                        found.add(c.value)
    return found


def _fields(template: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(template) if f}


def test_every_backend_template_has_romanian():
    missing = sorted(t for t in _tr_literals() | set(DYNAMIC_TEMPLATES) if t not in i18n.RO)
    assert not missing, f"add to watchstock/i18n.py RO: {missing}"


def test_backend_placeholders_match():
    bad = {k: v for k, v in i18n.RO.items() if _fields(k) != _fields(v)}
    assert not bad


# ------------------------------------------------------------------ frontend


def _js_dictionary() -> dict[str, str]:
    src = (ROOT / "static/js/i18n.js").read_text(encoding="utf-8")
    body = src[src.index("const RO = {") : src.index("\n};", src.index("const RO = {"))]
    pairs = re.findall(
        r"^\s*(['\"])((?:\\.|(?!\1).)*)\1:\s*(['\"])((?:\\.|(?!\3).)*)\3,", body, re.M
    )
    return {k.replace("\\'", "'"): v.replace("\\'", "'") for _, k, _, v in pairs}


def test_js_dictionary_parses_and_placeholders_match():
    d = _js_dictionary()
    assert len(d) > 200
    bad = {
        k: v
        for k, v in d.items()
        if set(re.findall(r"\{(\w+)\}", k)) != set(re.findall(r"\{(\w+)\}", v))
    }
    assert not bad


def test_every_js_t_call_has_romanian():
    d = _js_dictionary()
    calls = set()
    for path in (ROOT / "static/js").glob("*.js"):
        code = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                         if not line.lstrip().startswith("//"))  # fmt: skip
        for m in re.finditer(r"\bt\(\s*(['\"])((?:\\.|(?!\1).)*)\1", code):
            calls.add(m.group(2).replace("\\'", "'").replace('\\"', '"'))
    # role labels passed through t(role)
    calls |= {"USER", "SYSTEM"}
    missing = sorted(c for c in calls if c not in d)
    assert not missing, f"add to static/js/i18n.js RO: {missing}"


# Visible strings in index.html that are deliberately not translated.
_HTML_KEEP = {"WatchStock", "Watch", "Stock", "TICKER", "Enter", "Esc", ":free", "EN", "RO",
              "English", "Română", "nvidia/nemotron-3.5-super-vl:free", "sk-or-..."}  # fmt: skip


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found: set[str] = set()
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "svg", "title"):
            self._skip += 1
        for k, v in attrs:
            if k in ("placeholder", "title") and v and re.search("[A-Za-z]{2}", v):
                self.found.add(v.strip())

    def handle_endtag(self, tag):
        if tag in ("script", "style", "svg", "title"):
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and re.search("[A-Za-z]{2}", data):
            self.found.add(data.strip())


def test_every_index_html_string_has_romanian():
    p = _Text()
    p.feed((ROOT / "static/index.html").read_text(encoding="utf-8"))
    d = _js_dictionary()
    missing = sorted(s for s in p.found - _HTML_KEEP if s not in d)
    assert not missing, f"add to static/js/i18n.js RO: {missing}"


# ----------------------------------------------------------------------- API


def test_romanian_scores_and_decimal_comma(client):
    client.cookies.set("ws_lang", "ro")
    body = client.get("/api/stocks/MSFT").json()
    items = [b["item"] for b in body["scores"]["quality"]["breakdown"]]
    assert "Marjă netă 36,0%" in items
    assert body["scores"]["opportunity"]["label"] == "Oportunitate moderată"
    assert [c["label"] for c in body["scores"]["opportunity"]["components"]][0] == "Calitate"


def test_same_cached_snapshot_switches_language(client, fake_yahoo):
    en = client.get("/api/stocks/MSFT").json()
    client.cookies.set("ws_lang", "ro")
    ro = client.get("/api/stocks/MSFT").json()
    assert ro["source"] == "cache"  # no refetch, scores computed at serve time
    assert en["scores"]["quality"]["breakdown"][0]["item"] == "Net margin 36.0%"
    assert ro["scores"]["quality"]["breakdown"][0]["item"] == "Marjă netă 36,0%"


def test_llm_is_asked_for_romanian(client, fake_llm):
    client.cookies.set("ws_lang", "ro")
    client.put("/api/settings", json={"llm_api_key": "sk-test"})
    client.post("/api/stocks/MSFT/analysis")
    assert "Romanian" in fake_llm.requests[-1]["messages"][0]["content"]
    client.cookies.set("ws_lang", "en")
    client.post("/api/stocks/MSFT/analysis")
    assert "Romanian" not in fake_llm.requests[-1]["messages"][0]["content"]


def test_romanian_error_messages(client):
    client.cookies.set("ws_lang", "ro")
    r = client.post("/api/stocks/MSFT/analysis")  # no key configured
    assert "cheie OpenRouter" in r.json()["detail"]


@pytest.mark.parametrize("cookie", ["de", "", "<script>"])
def test_unknown_language_falls_back_to_english(client, cookie):
    client.cookies.set("ws_lang", cookie)
    body = client.get("/api/stocks/MSFT").json()
    assert body["scores"]["quality"]["breakdown"][0]["item"] == "Net margin 36.0%"


def test_default_is_english_outside_requests():
    assert i18n.get_lang() == "en"
    assert i18n.tr("Net margin {pct}", pct="1%") == "Net margin 1%"
    assert json.dumps(i18n.num(1.5)) == '"1.5"'
