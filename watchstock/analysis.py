"""LLM-backed analysis report and chat. Prompts live here; transport is providers/openrouter."""

import json
import re
from typing import Any

from watchstock import config, store
from watchstock.providers import openrouter
from watchstock.providers.openrouter import LLMError

VERDICTS = ("STRONG BUY", "BUY", "HOLD", "REDUCE", "SELL", "STRONG SELL")


def llm_settings() -> tuple[str, str]:
    return store.get_setting("llm_api_key"), store.get_setting(
        "llm_model", config.DEFAULT_LLM_MODEL
    )


def parse_llm_json(text: str) -> dict[str, Any]:
    """Parse an LLM reply as a JSON object, tolerating code fences and chatter around it."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    raise ValueError("No valid JSON object found in LLM reply")


def compact_context(stock: dict[str, Any]) -> dict[str, Any]:
    """The subset of a stock snapshot worth sending to the LLM."""
    return {
        "company_name": stock.get("company_name"),
        "ticker": stock.get("ticker"),
        "as_of": stock.get("as_of"),
        "metrics": stock.get("financial_data", {}).get("metrics", {}),
        "analyst_data": stock.get("financial_data", {}).get("analyst_data", {}),
        "key_officers": (stock.get("financial_data", {}).get("key_officers") or [])[:3],
        "risk_analysis": stock.get("risk_analysis", {}),
        "safety": stock.get("safety"),
        "industry_peers": (
            {k: stock["peers"][k] for k in ("industry", "medians", "relative", "peer_count")}
            if stock.get("peers")
            else None
        ),
        "scores": stock.get("scores"),
        "news": [
            {k: n.get(k) for k in ("title", "publisher", "published_at", "summary")}
            for n in (stock.get("news") or [])[:15]
        ],
    }


ANALYSIS_SYSTEM_PROMPT = (
    "You are a Senior Investment Research Analyst. "
    "You have been handed a company profile: live financial metrics, valuation data, "
    "analyst consensus, computed scores and recent news headlines. "
    "Produce a deep, actionable investment research report for a private investor.\n\n"
    "DATA AVAILABLE TO YOU:\n"
    "- `metrics`: ratios and valuation multiples (P/E, PEG, P/B, margins, debt/equity "
    "(Yahoo reports it in percent, 150 = 1.5x), beta, marketCap, EPS, revenue growth)\n"
    "- `analyst_data`: Wall Street consensus, price targets, recommendation rating\n"
    "- `scores`: opportunity (0-100) built from quality, valuation, analyst and smart-money "
    "pillars, each with a breakdown of what drove it\n"
    "- `safety`: short_term (liquidity) and long_term (solvency & volatility) 0-100, plus flags\n"
    "- `industry_peers` (may be null): industry peer medians and this stock's % difference\n"
    "- `previous_report` (may be absent): your last report on this stock and its date\n"
    "- `news`: recent headlines. Decide yourself which ones are material.\n\n"
    "INSTRUCTIONS:\n"
    "1. Interpret the numbers, don't just list them.\n"
    "2. Connect material news to price catalysts and risks; ignore noise.\n"
    "3. Be specific: cite metrics and headlines.\n"
    "4. Consider valuation honestly relative to growth.\n"
    "5. Markdown fields use rich markdown (##, **bold**, bullet lists, > for key warnings).\n\n"
    "Return ONLY valid JSON, no preamble, with exactly this structure:\n"
    "{\n"
    '  "executive_summary": "3-5 sentence investment verdict.",\n'
    '  "verdict": {"action": "BUY", "confidence": 72, "horizon": "12 months"},\n'
    '  "recommended_action": "Full sentence elaborating the verdict.",\n'
    '  "financial_deep_dive": "Rich markdown analysis, min 200 words.",\n'
    '  "news_impact_analysis": "Rich markdown analysis, min 150 words.",\n'
    '  "risk_scenarios": "Rich markdown with ## Bull Case, ## Base Case, ## Bear Case.",\n'
    '  "changes_since_last": "If previous_report exists: short markdown on what changed '
    'since then and whether the verdict changed and why. Otherwise null.",\n'
    '  "charts": [\n'
    '    {"chart_type": "bar", "labels": ["P/E", "P/B", "EV/EBITDA"], '
    '"values": [28.5, 4.2, 18.1], "title": "Valuation Multiples"}\n'
    "  ]\n"
    "}\n\n"
    "Charts: use ACTUAL numbers from the data, values must be numbers, 1-3 charts, "
    "skip any chart lacking data. verdict.action must be one of: "
    + ", ".join(VERDICTS)
    + ". verdict.confidence is an integer 0-100."
)


def run_analysis(stock: dict[str, Any]) -> dict[str, Any]:
    """Generate, validate and store an analysis report. Raises LLMError."""
    api_key, model = llm_settings()
    context = compact_context(stock)
    if previous := store.latest_analysis(stock["ticker"]):
        context["previous_report"] = {
            k: previous.get(k) for k in ("created_at", "verdict", "executive_summary")
        }
    reply = openrouter.complete(
        [
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(context, default=str)},
        ],
        api_key=api_key,
        model=model,
    )
    try:
        report = parse_llm_json(reply)
    except ValueError as exc:
        raise LLMError(
            "The model's reply wasn't valid JSON. Try again or pick another model."
        ) from exc
    if not report.get("executive_summary"):
        raise LLMError("The model's reply was missing the executive summary.")
    return store.save_analysis(stock["ticker"], model, report)


CHAT_SYSTEM_PROMPT = (
    "You are a Senior Investment Research Analyst inside a stock analysis terminal. "
    "The user has loaded the company below. You are the same analyst who wrote the "
    "AI analysis shown on screen.\n\n"
    "COMPANY CONTEXT:\n{context}\n\n"
    "Return a JSON object with:\n"
    '  "reply_text": your markdown answer (concise, professional)\n'
    '  "ui_action": null, or one of:\n'
    '    {{"action": "update_chart", "chart_type": "bar|pie|line|doughnut|radar", '
    '"labels": [...], "values": [...], "title": "..."}}\n'
    '    {{"action": "append_new_chart", "target_tab": "tab-ai", "chart_config": '
    '{{"type": "...", "labels": [...], "values": [...], "title": "..."}}}}\n'
    '    {{"action": "switch_tab", "tab": "tab-finance|tab-ai|tab-news"}}\n'
    '    {{"action": "search_company", "company_name": "...", "ticker": "..."}}\n'
    '    {{"action": "highlight_risk"}}\n'
    'For several actions return "ui_actions" (array) instead of "ui_action".\n'
    "Use update_chart to change the existing chart, append_new_chart to add one. "
    "When asked about a different company, use search_company with the correct ticker.\n"
    "CHARTS ALREADY ON SCREEN: {charts}. Don't duplicate them unless asked."
)


def chat(
    question: str,
    stock: dict[str, Any] | None,
    history: list[dict[str, str]],
    existing_charts: list[str],
) -> dict[str, Any]:
    api_key, model = llm_settings()
    context = {"stock": compact_context(stock) if stock else None}
    if stock and stock.get("ai_analysis"):
        analysis = stock["ai_analysis"]
        context["current_analysis"] = {
            k: analysis.get(k) for k in ("executive_summary", "verdict", "recommended_action")
        }
    system = CHAT_SYSTEM_PROMPT.format(
        context=json.dumps(context, default=str), charts=json.dumps(existing_charts)
    )
    messages = [{"role": "system", "content": system}]
    for msg in history[-20:]:
        role = "user" if msg.get("role") == "user" else "assistant"
        messages.append({"role": role, "content": str(msg.get("content", ""))})
    # The UI may already have appended the question to history; don't send it twice.
    if not (messages[-1]["role"] == "user" and messages[-1]["content"] == question):
        messages.append({"role": "user", "content": question})

    reply = openrouter.complete(messages, api_key=api_key, model=model)
    try:
        parsed = parse_llm_json(reply)
    except ValueError:
        return {"reply_text": reply, "ui_action": None, "ui_actions": None}
    return {
        "reply_text": parsed.get("reply_text") or reply,
        "ui_action": parsed.get("ui_action"),
        "ui_actions": parsed.get("ui_actions"),
    }


THESIS_STATUSES = ("intact", "weakening", "broken", "unclear")

THESIS_SYSTEM_PROMPT = (
    "You check whether a private investor's reason for owning a stock still holds. "
    "You get their thesis in their own words and the current company data: metrics, "
    "scores, analyst view and recent headlines (some may be noise).\n\n"
    "Judge only what the thesis claims. Be concrete: cite numbers and headlines. If the "
    "data can't confirm or refute a claim, say so instead of guessing. Not financial advice.\n\n"
    "Return ONLY valid JSON:\n"
    "{\n"
    '  "status": "intact" | "weakening" | "broken" | "unclear",\n'
    '  "summary": "2-3 sentences in plain language.",\n'
    '  "supporting": ["evidence that the thesis still holds", ...],\n'
    '  "against": ["evidence that it is weakening or wrong", ...],\n'
    '  "watch": ["what to keep an eye on next", ...]\n'
    "}"
)


def run_thesis_check(stock: dict[str, Any], thesis: str) -> dict[str, Any]:
    """Ask the LLM whether `thesis` still holds for this stock; store and return it."""
    api_key, model = llm_settings()
    context = {"investor_thesis": thesis, "company": compact_context(stock)}
    if previous := store.latest_thesis_check(stock["ticker"]):
        context["previous_check"] = {
            k: previous.get(k) for k in ("created_at", "status", "summary")
        }
    reply = openrouter.complete(
        [
            {"role": "system", "content": THESIS_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(context, default=str)},
        ],
        api_key=api_key,
        model=model,
    )
    try:
        result = parse_llm_json(reply)
    except ValueError as exc:
        raise LLMError(
            "The model's reply wasn't valid JSON. Try again or pick another model."
        ) from exc
    status = str(result.get("status", "")).strip().lower()
    if status not in THESIS_STATUSES or not result.get("summary"):
        raise LLMError("The model's reply was missing a valid status or summary.")
    clean = {
        "status": status,
        "summary": str(result["summary"]),
        **{
            k: [str(x) for x in result.get(k) or []][:8] for k in ("supporting", "against", "watch")
        },
    }
    return store.save_thesis_check(stock["ticker"], model, thesis, clean)
