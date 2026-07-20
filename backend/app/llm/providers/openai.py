"""OpenAI chat-completions adapter (Phase 2, R8).

Implemented directly against the HTTP API with ``httpx`` — no vendor SDK (CC3) — so the
same shape extends to Gemini later. Batch ``complete()`` only for now; token streaming
(``llm_ttft_ms``) arrives in Phase 6.
"""

from __future__ import annotations

from typing import Any

import httpx

from .base import ProviderError

API_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIError(ProviderError):
    """A failed OpenAI call (subclass of ProviderError so the orchestrator catches it generically)."""


async def complete(
    *,
    messages: list[dict[str, str]],
    model: str,
    api_key: str,
    max_tokens: int,
    temperature: float = 0.3,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Call chat-completions and return ``{text, usage, model}``.

    Raises ``OpenAIError`` (with a status) on a missing key, network failure, or API error.
    """
    if not api_key:
        raise OpenAIError(400, "No OpenAI API key — set OPENAI_API_KEY or send an X-OpenAI-Key header.")

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(API_URL, headers=headers, json=payload)
    except httpx.HTTPError as e:
        raise OpenAIError(502, f"OpenAI request failed: {e}") from e

    if resp.status_code != 200:
        raise OpenAIError(resp.status_code, _error_message(resp))

    data = resp.json()
    try:
        text = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as e:
        raise OpenAIError(502, f"Unexpected OpenAI response shape: {e}") from e

    return {"text": text, "usage": data.get("usage", {}), "model": data.get("model", model)}


def _error_message(resp: httpx.Response) -> str:
    """Pull the human-readable error out of an OpenAI error response."""
    try:
        return resp.json().get("error", {}).get("message") or resp.text
    except Exception:  # noqa: BLE001 — any parse failure falls back to raw text
        return resp.text
