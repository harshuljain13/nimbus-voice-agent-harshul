"""Chat orchestration — reference API contract (see .spec-dev/reference.md §3).

Phases 2-7: batch + streaming, multi-turn, OpenAI + Gemini, knowledge RAGless/RAG/none,
conversation history (verbatim + rolling summary), and a tool-call loop (batch mode). Returns
reference-shaped {text, latency, meta}; chat_stream yields SSE-style events.
"""

from __future__ import annotations

import os
from typing import Any, AsyncIterator

from .. import config
from ..latency import Timer, empty_trace
from ..rag import service as rag_service
from ..scraping import paths
from ..tools import registry as tool_registry
from . import history, prompts, tokens
from .providers import gemini as gemini_provider
from .providers import openai as openai_provider
from .providers.base import ProviderError

_PROVIDERS = {"openai": openai_provider, "gemini": gemini_provider}
_SUMMARY_MODEL = "gpt-4o-mini"

HISTORY = history.HistoryStore()


class ChatError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


_context_cache: dict[str, Any] = {"mtime": None, "text": ""}


def load_context() -> str:
    path = paths.CONTEXT_PATH
    if not os.path.exists(path):
        raise ChatError(409, "context.md not built — run Scrape → Build context.md first.")
    mtime = os.path.getmtime(path)
    if _context_cache["mtime"] != mtime:
        with open(path, encoding="utf-8") as f:
            _context_cache["text"] = f.read()
        _context_cache["mtime"] = mtime
    return _context_cache["text"]


def _resolve_model(model_key: str) -> dict[str, str]:
    if model_key not in config.LLM_MODELS:
        raise ChatError(400, f"Unknown model_key {model_key!r}. Options: {list(config.LLM_MODELS)}.")
    return config.LLM_MODELS[model_key]


def assemble(message, *, response_length, use_context, use_rag, system_prompt, top_k=4,
             rerank=False, tools_available=False, api_key=None) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Build the [system, user] pair + grounding metadata (RAG / RAGless / none)."""
    rag_info: dict[str, Any] | None = None
    if use_rag:
        knowledge = "rag"
        try:
            rag_service.ensure_built(api_key)
            res = rag_service.query(message, k=top_k, do_rerank=rerank, api_key=api_key)
        except RuntimeError as e:
            raise ChatError(400, f"RAG error: {e}") from e
        context = res["context"]
        rag_info = {"k": res["k"], "reranked": res["reranked"], "rag_ms": res["latency"]["rag_ms"],
                    "latency": res["latency"],
                    "chunks": [{"doc": r["doc"], "heading": r["heading"], "score": r["score"]} for r in res["results"]]}
    elif use_context:
        knowledge, context = "ragless", load_context()
    else:
        knowledge, context = "none", ""

    grounded = knowledge in ("rag", "ragless")
    messages = prompts.build_messages(message, context, response_length, system_prompt,
                                      grounded=grounded, tools_available=tools_available)
    info = {"knowledge": knowledge, "context_chars": len(context),
            "context_tokens": tokens.count_tokens(context)["tokens"] if context else 0, "rag": rag_info}
    return messages, info


def _build_final(base, summary, recent):
    final = [base[0]]
    if summary:
        final.append({"role": "system", "content": "Summary of earlier conversation:\n" + summary})
    final += recent
    final.append(base[1])
    return final


async def _summarize_if_needed(session_id, sess, older, openai_key):
    if not history.needs_summary(sess, older):
        return sess
    try:
        out = await openai_provider.complete(messages=history.summary_prompt(sess["summary"], older),
                                             model=_SUMMARY_MODEL, api_key=openai_key, max_tokens=220, temperature=0.2)
        sess = {**sess, "summary": out["text"], "summarized_count": len(older)}
        HISTORY.set(session_id, sess)
    except ProviderError:
        pass
    return sess


async def _prepare(*, message, model_key, response_length, use_context, use_rag, top_k, rerank,
                   verbatim_turns, system_prompt, session_id, headers,
                   tools_enabled=False, enabled_tools=None) -> dict[str, Any]:
    """Shared setup for batch + stream: validate, assemble grounding, thread history."""
    message = (message or "").strip()
    if not message:
        raise ChatError(400, "Empty message.")
    spec = _resolve_model(model_key)
    provider = spec["provider"]
    openai_key = config.resolve_key("openai", headers)                    # RAG embed / rerank / summary / tools
    llm_key = openai_key if provider == "openai" else config.resolve_key(provider, headers)

    # tools_enabled with no explicit subset → all tools; a non-empty list → just that subset.
    specs = tool_registry.enabled_specs(enabled_tools or None) if tools_enabled else []
    tools_available = tools_enabled and provider == "openai" and bool(specs)

    trace = empty_trace()
    base, info = assemble(message, response_length=response_length, use_context=use_context,
                          use_rag=use_rag, system_prompt=system_prompt, top_k=top_k, rerank=rerank,
                          tools_available=tools_available, api_key=openai_key)
    if info["rag"]:
        trace["rag_ms"] = info["rag"]["rag_ms"]

    recent, summary, summarized = [], "", 0
    if session_id:
        sess = HISTORY.get(session_id)
        older, recent = history.split_for_context(sess["turns"], verbatim_turns)
        sess = await _summarize_if_needed(session_id, sess, older, openai_key)
        summary, summarized = sess["summary"], sess["summarized_count"]

    return {"message": message, "model_key": model_key, "spec": spec, "provider": provider,
            "openai_key": openai_key, "llm_key": llm_key, "trace": trace, "info": info,
            "final": _build_final(base, summary, recent), "recent": recent, "summary": summary,
            "summarized": summarized, "response_length": response_length,
            "specs": specs, "tools_available": tools_available}


def _build_meta(ctx, *, mode, model, usage, tool_calls):
    info = ctx["info"]
    rag_meta = None
    if info["rag"]:
        r = info["rag"]
        rag_meta = {"k": r["k"], "reranked": r["reranked"], "latency": r["latency"], "chunks": r["chunks"]}
    return {"model": model, "model_key": ctx["model_key"], "provider": ctx["provider"], "mode": mode,
            "knowledge": info["knowledge"], "context_chars": info["context_chars"],
            "context_tokens": info["context_tokens"], "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"), "system_chars": len(ctx["final"][0]["content"]),
            "verbatim_messages": len(ctx["recent"]), "summarized_messages": ctx["summarized"],
            "summary_used": bool(ctx["summary"]), "tool_calls": tool_calls, "rag": rag_meta}


async def chat(*, message, model_key="openai-lite", response_length="medium", use_context=True,
               use_rag=False, top_k=4, rerank=False, verbatim_turns=6, tools_enabled=False,
               enabled_tools=None, system_prompt=None, temperature=0.3, mode="batch",
               session_id=None, headers=None) -> dict[str, Any]:
    """One batch chat turn (history + optional tool-call loop) → {text, latency, meta}."""
    if mode == "stream":
        raise ChatError(400, "Use /chat/stream for streaming.")
    total = Timer()
    ctx = await _prepare(message=message, model_key=model_key, response_length=response_length,
                         use_context=use_context, use_rag=use_rag, top_k=top_k, rerank=rerank,
                         verbatim_turns=verbatim_turns, system_prompt=system_prompt,
                         session_id=session_id, headers=headers,
                         tools_enabled=tools_enabled, enabled_tools=enabled_tools)
    trace, spec, provider = ctx["trace"], ctx["spec"], ctx["provider"]
    max_tokens = prompts.max_tokens_for(response_length)

    specs = ctx["specs"]
    use_tools = ctx["tools_available"]
    tool_calls: list[dict] = []
    llm_timer = Timer()
    try:
        if use_tools:
            out = await openai_provider.complete_with_tools(
                messages=ctx["final"], model=spec["model"], api_key=ctx["llm_key"],
                tool_schema=tool_registry.openai_schema(specs),
                dispatch=tool_registry.make_dispatch(session_id or "anon", enabled_tools or None),
                max_tokens=max_tokens, temperature=temperature)
            tool_calls = out["tool_calls"]
            trace["tool_ms"] = out["tool_ms"]
        else:
            out = await _PROVIDERS[provider].complete(
                messages=ctx["final"], model=spec["model"], api_key=ctx["llm_key"],
                max_tokens=max_tokens, temperature=temperature)
    except ProviderError as e:
        raise ChatError(e.status if e.status in (400, 401, 403, 429) else 502, e.message) from e
    trace["llm_total_ms"] = llm_timer.ms()
    trace["total_ms"] = total.ms()

    if session_id:
        HISTORY.append(session_id, "user", ctx["message"])
        HISTORY.append(session_id, "assistant", out["text"])

    meta = _build_meta(ctx, mode="batch", model=out.get("model", spec["model"]),
                       usage=out.get("usage", {}), tool_calls=tool_calls)
    return {"text": out["text"], "latency": trace, "meta": meta}


async def chat_stream(*, message, model_key="openai-lite", response_length="medium", use_context=True,
                      use_rag=False, top_k=4, rerank=False, verbatim_turns=6, system_prompt=None,
                      temperature=0.3, session_id=None, headers=None) -> AsyncIterator[dict[str, Any]]:
    """Stream a chat turn (text-only; tools run in batch mode). Yields delta/done/error events."""
    total = Timer()
    try:
        ctx = await _prepare(message=message, model_key=model_key, response_length=response_length,
                             use_context=use_context, use_rag=use_rag, top_k=top_k, rerank=rerank,
                             verbatim_turns=verbatim_turns, system_prompt=system_prompt,
                             session_id=session_id, headers=headers)
    except ChatError as e:
        yield {"type": "error", "error": e.message}
        return
    trace, spec, provider = ctx["trace"], ctx["spec"], ctx["provider"]
    acc = ""
    llm_timer = Timer()
    try:
        async for delta in _PROVIDERS[provider].stream(
                messages=ctx["final"], model=spec["model"], api_key=ctx["llm_key"],
                max_tokens=prompts.max_tokens_for(response_length), temperature=temperature):
            if not acc:
                trace["llm_ttft_ms"] = llm_timer.ms()   # time to first token
            acc += delta
            yield {"type": "delta", "text": delta}
    except ProviderError as e:
        yield {"type": "error", "error": e.message}
        return
    trace["llm_total_ms"] = llm_timer.ms()
    trace["total_ms"] = total.ms()

    if session_id:
        HISTORY.append(session_id, "user", ctx["message"])
        HISTORY.append(session_id, "assistant", acc)

    # streaming APIs don't return usage by default — count locally so the metrics match batch mode
    usage = {"prompt_tokens": sum(tokens.count_tokens(m["content"], spec["model"])["tokens"] for m in ctx["final"]),
             "completion_tokens": tokens.count_tokens(acc, spec["model"])["tokens"]}
    meta = _build_meta(ctx, mode="stream", model=spec["model"], usage=usage, tool_calls=[])
    yield {"type": "done", "text": acc, "latency": trace, "meta": meta}


def inspect(*, message, response_length="medium", use_context=True, use_rag=False, top_k=4,
            rerank=False, verbatim_turns=6, system_prompt=None, model_key="openai-lite",
            session_id=None, api_key=None, **_ignore) -> dict[str, Any]:
    """Context inspector — exact messages + per-message token counts (uses stored history)."""
    spec = _resolve_model(model_key)
    base, info = assemble(message or "(preview)", response_length=response_length,
                          use_context=use_context, use_rag=use_rag, system_prompt=system_prompt,
                          top_k=top_k, rerank=rerank, api_key=api_key)
    summary, recent = "", []
    if session_id:
        sess = HISTORY.get(session_id)
        _, recent = history.split_for_context(sess["turns"], verbatim_turns)
        summary = sess["summary"]
    final = _build_final(base, summary, recent)
    rows, total_tokens, total_chars = [], 0, 0
    for m in final:
        t = tokens.count_tokens(m["content"], spec["model"])["tokens"]
        rows.append({"role": m["role"], "content": m["content"], "tokens": t, "chars": len(m["content"])})
        total_tokens += t
        total_chars += len(m["content"])
    return {"total_tokens": total_tokens, "total_chars": total_chars, "messages": rows,
            "knowledge": info["knowledge"], "rag": info["rag"]}
