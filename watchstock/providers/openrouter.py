"""OpenRouter chat-completions client. The ONLY module that talks to an LLM."""

from typing import Any

import httpx

from watchstock import config

URL = "https://openrouter.ai/api/v1/chat/completions"


class LLMError(Exception):
    """The LLM call failed or no API key is configured."""


def complete(
    messages: list[dict[str, str]], *, api_key: str, model: str, json_mode: bool = True
) -> str:
    """Send a chat completion and return the assistant's text."""
    if not api_key:
        raise LLMError("No OpenRouter API key configured. Add one in Settings.")
    payload: dict[str, Any] = {"model": model, "messages": messages}
    # response_format is an OpenAI-style option; Anthropic models misbehave with it.
    if json_mode and not model.startswith("anthropic/"):
        payload["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost",
        "X-Title": "WatchStock",
    }
    try:
        resp = httpx.post(URL, json=payload, headers=headers, timeout=config.LLM_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:300]
        raise LLMError(f"OpenRouter returned {exc.response.status_code}: {body}") from exc
    except Exception as exc:
        raise LLMError(f"OpenRouter request failed: {exc}") from exc
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Unexpected OpenRouter response: {str(data)[:300]}") from exc
