"""OpenAI chat-completions adapter (Phase 2, R8).

Implemented directly against the HTTP API with ``httpx`` — no vendor SDK (CC3) — so the
same shape extends to Gemini later. Batch ``complete()`` only for now; token streaming
(``llm_ttft_ms``) arrives in Phase 6.
"""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

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


async def stream(
    *,
    messages: list[dict[str, str]],
    model: str,
    api_key: str,
    max_tokens: int,
    temperature: float = 0.3,
    timeout: float = 60.0,
) -> AsyncIterator[str]:
    """Yield assistant text deltas as they arrive (Phase 6)."""
    if not api_key:
        raise OpenAIError(400, "No OpenAI API key — set OPENAI_API_KEY or send an X-OpenAI-Key header.")
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens,
               "temperature": temperature, "stream": True}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", API_URL, headers=headers, json=payload) as resp:
            if resp.status_code != 200:
                body = (await resp.aread()).decode("utf-8", "replace")
                raise OpenAIError(resp.status_code, body[:300])
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                chunk = line[6:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    delta = json.loads(chunk)["choices"][0]["delta"].get("content")
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if delta:
                    yield delta


async def complete_with_tools(
    *,
    messages: list[dict[str, str]],
    model: str,
    api_key: str,
    tool_schema: list[dict],
    dispatch,
    max_tokens: int,
    temperature: float = 0.3,
    max_iters: int = 6,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Function-calling loop (Phase 7): let the model call tools until it answers.

    Returns {text, usage, tool_ms, tool_calls:[{name,args,result,ms}]}. `dispatch(name, args)`
    runs a tool and returns a JSON-safe dict.
    """
    if not api_key:
        raise OpenAIError(400, "No OpenAI API key — set OPENAI_API_KEY or send an X-OpenAI-Key header.")
    native = [dict(m) for m in messages]
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    tool_ms = 0.0
    trace: list[dict] = []
    usage: dict = {}
    async with httpx.AsyncClient(timeout=timeout) as client:
        for _ in range(max_iters):
            payload = {"model": model, "messages": native, "max_tokens": max_tokens,
                       "temperature": temperature, "tools": tool_schema, "tool_choice": "auto"}
            resp = await client.post(API_URL, headers=headers, json=payload)
            if resp.status_code != 200:
                raise OpenAIError(resp.status_code, _error_message(resp))
            data = resp.json()
            usage = data.get("usage") or usage
            msg = data["choices"][0]["message"]
            calls = msg.get("tool_calls") or []
            if not calls:
                return {"text": (msg.get("content") or "").strip(), "usage": usage,
                        "tool_ms": round(tool_ms, 2), "tool_calls": trace}
            native.append({"role": "assistant", "content": msg.get("content"), "tool_calls": calls})
            for tc in calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                t0 = time.perf_counter()
                result = dispatch(name, args)
                ms = (time.perf_counter() - t0) * 1000.0
                tool_ms += ms
                trace.append({"name": name, "args": args, "result": result, "ms": round(ms, 2)})
                native.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(result)})
    return {"text": "I wasn't able to finish that action.", "usage": usage,
            "tool_ms": round(tool_ms, 2), "tool_calls": trace}


def _error_message(resp: httpx.Response) -> str:
    """Pull the human-readable error out of an OpenAI error response."""
    try:
        return resp.json().get("error", {}).get("message") or resp.text
    except Exception:  # noqa: BLE001 — any parse failure falls back to raw text
        return resp.text
