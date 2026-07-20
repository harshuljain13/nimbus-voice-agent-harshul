"""Gemini chat provider over httpx (Phase 5, R8), matching openai.complete()'s shape.

Normalized messages map to Gemini's format: system messages → a single systemInstruction;
assistant → "model", user → "user". Returns {text, usage, model}.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from .base import ProviderError

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class GeminiError(ProviderError):
    """A failed Gemini call (subclass of ProviderError)."""


def _to_gemini(messages: list[dict[str, str]]) -> dict[str, Any]:
    system_txt = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    contents = [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
        for m in messages if m["role"] != "system"
    ]
    body: dict[str, Any] = {"contents": contents}
    if system_txt:
        body["systemInstruction"] = {"parts": [{"text": system_txt}]}
    return body


async def complete(
    *,
    messages: list[dict[str, str]],
    model: str,
    api_key: str,
    max_tokens: int,
    temperature: float = 0.3,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Call Gemini generateContent → ``{text, usage, model}``. Raises GeminiError on failure."""
    if not api_key:
        raise GeminiError(400, "No Gemini API key — set GEMINI_API_KEY or send an X-Gemini-Key header.")
    body = _to_gemini(messages)
    body["generationConfig"] = {"maxOutputTokens": max_tokens, "temperature": temperature}
    url = f"{_BASE}/{model}:generateContent?key={api_key}"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=body)
    except httpx.HTTPError as e:
        raise GeminiError(502, f"Gemini request failed: {e}") from e
    if resp.status_code != 200:
        raise GeminiError(resp.status_code, _error_message(resp))

    data = resp.json()
    text = "".join(
        part["text"]
        for cand in data.get("candidates", [])
        for part in cand.get("content", {}).get("parts", [])
        if "text" in part
    ).strip()
    usage = data.get("usageMetadata") or {}
    return {
        "text": text,
        "usage": {"prompt_tokens": usage.get("promptTokenCount"),
                  "completion_tokens": usage.get("candidatesTokenCount")},
        "model": model,
    }


async def stream(
    *,
    messages: list[dict[str, str]],
    model: str,
    api_key: str,
    max_tokens: int,
    temperature: float = 0.3,
    timeout: float = 60.0,
) -> AsyncIterator[str]:
    """Yield Gemini text deltas as they arrive (Phase 6)."""
    if not api_key:
        raise GeminiError(400, "No Gemini API key — set GEMINI_API_KEY or send an X-Gemini-Key header.")
    body = _to_gemini(messages)
    body["generationConfig"] = {"maxOutputTokens": max_tokens, "temperature": temperature}
    url = f"{_BASE}/{model}:streamGenerateContent?alt=sse&key={api_key}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, json=body) as resp:
            if resp.status_code != 200:
                raw = (await resp.aread()).decode("utf-8", "replace")
                raise GeminiError(resp.status_code, raw[:300])
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                piece = "".join(
                    part["text"]
                    for cand in data.get("candidates", [])
                    for part in cand.get("content", {}).get("parts", [])
                    if "text" in part
                )
                if piece:
                    yield piece


def _error_message(resp: httpx.Response) -> str:
    try:
        return resp.json().get("error", {}).get("message") or resp.text
    except Exception:  # noqa: BLE001
        return resp.text
