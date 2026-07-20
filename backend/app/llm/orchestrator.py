"""Chat orchestration — converging on the reference API contract (see .spec-dev/reference.md §3).

Phases 2-5: batch, multi-turn. Providers OpenAI + Gemini; knowledge RAGless / RAG / none;
conversation history (last-N verbatim + rolling summary). Returns reference-shaped
{text, latency, meta}. Streaming and tools are guarded off until their phases.
"""

from __future__ import annotations

import os
from typing import Any

from .. import config
from ..latency import Timer, empty_trace
from ..rag import service as rag_service
from ..scraping import paths
from . import history, prompts, tokens
from .providers import gemini as gemini_provider
from .providers import openai as openai_provider
from .providers.base import ProviderError

_PROVIDERS = {"openai": openai_provider, "gemini": gemini_provider}
_SUMMARY_MODEL = "gpt-4o-mini"  # cheap OpenAI model used to summarize aged-out history

HISTORY = history.HistoryStore()


class ChatError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


_context_cache: dict[str, Any] = {"mtime": None, "text": ""}


def load_context() -> str:
    """Return the RAGless grounding payload (``context.md``), cached by mtime."""
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


def assemble(
    message: str,
    *,
    response_length: str,
    use_context: bool,
    use_rag: bool,
    system_prompt: str | None,
    top_k: int = 4,
    rerank: bool = False,
    api_key: str | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
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
        knowledge = "ragless"
        context = load_context()
    else:
        knowledge = "none"
        context = ""

    grounded = knowledge in ("rag", "ragless")
    messages = prompts.build_messages(message, context, response_length, system_prompt, grounded=grounded)
    info = {"knowledge": knowledge, "context_chars": len(context),
            "context_tokens": tokens.count_tokens(context)["tokens"] if context else 0, "rag": rag_info}
    return messages, info


def _build_final(base: list[dict[str, str]], summary: str, recent: list[dict[str, str]]) -> list[dict[str, str]]:
    """system(grounding) + optional summary + recent verbatim turns + current user turn."""
    final = [base[0]]
    if summary:
        final.append({"role": "system", "content": "Summary of earlier conversation:\n" + summary})
    final += recent
    final.append(base[1])
    return final


async def _summarize_if_needed(session_id: str, sess: dict[str, Any], older: list[dict[str, str]],
                               openai_key: str) -> dict[str, Any]:
    if not history.needs_summary(sess, older):
        return sess
    try:
        out = await openai_provider.complete(
            messages=history.summary_prompt(sess["summary"], older),
            model=_SUMMARY_MODEL, api_key=openai_key, max_tokens=220, temperature=0.2)
        sess = {**sess, "summary": out["text"], "summarized_count": len(older)}
        HISTORY.set(session_id, sess)
    except ProviderError:
        pass  # summarization is best-effort; keep the previous summary
    return sess


async def chat(
    *,
    message: str,
    model_key: str = "openai-lite",
    response_length: str = "medium",
    use_context: bool = True,
    use_rag: bool = False,
    top_k: int = 4,
    rerank: bool = False,
    verbatim_turns: int = 6,
    system_prompt: str | None = None,
    temperature: float = 0.3,
    mode: str = "batch",
    session_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run one batch chat turn (with history) → reference-shaped ``{text, latency, meta}``."""
    message = (message or "").strip()
    if not message:
        raise ChatError(400, "Empty message.")
    if mode == "stream":
        raise ChatError(400, "Streaming arrives in Phase 6 — use batch for now.")
    spec = _resolve_model(model_key)
    provider = spec["provider"]
    openai_key = config.resolve_key("openai", headers)                       # RAG embed / rerank / summary
    llm_key = openai_key if provider == "openai" else config.resolve_key(provider, headers)

    trace = empty_trace()
    total = Timer()
    messages, info = assemble(message, response_length=response_length, use_context=use_context,
                              use_rag=use_rag, system_prompt=system_prompt, top_k=top_k,
                              rerank=rerank, api_key=openai_key)
    if info["rag"]:
        trace["rag_ms"] = info["rag"]["rag_ms"]

    # conversation history: keep the last N verbatim, summarize the rest
    recent: list[dict[str, str]] = []
    summary = ""
    summarized = 0
    if session_id:
        sess = HISTORY.get(session_id)
        older, recent = history.split_for_context(sess["turns"], verbatim_turns)
        sess = await _summarize_if_needed(session_id, sess, older, openai_key)
        summary, summarized = sess["summary"], sess["summarized_count"]
    final = _build_final(messages, summary, recent)

    llm_timer = Timer()
    try:
        out = await _PROVIDERS[provider].complete(
            messages=final, model=spec["model"], api_key=llm_key,
            max_tokens=prompts.max_tokens_for(response_length), temperature=temperature)
    except ProviderError as e:
        raise ChatError(e.status if e.status in (400, 401, 403, 429) else 502, e.message) from e
    trace["llm_total_ms"] = llm_timer.ms()
    trace["total_ms"] = total.ms()

    if session_id:  # persist this turn for the next one
        HISTORY.append(session_id, "user", message)
        HISTORY.append(session_id, "assistant", out["text"])

    usage = out.get("usage", {})
    rag_meta = None
    if info["rag"]:
        rag_meta = {"k": info["rag"]["k"], "reranked": info["rag"]["reranked"],
                    "latency": info["rag"]["latency"], "chunks": info["rag"]["chunks"]}
    meta = {
        "model": out.get("model", spec["model"]),
        "model_key": model_key,
        "provider": provider,
        "mode": "batch",
        "knowledge": info["knowledge"],
        "context_chars": info["context_chars"],
        "context_tokens": info["context_tokens"],
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "system_chars": len(final[0]["content"]),
        "verbatim_messages": len(recent),
        "summarized_messages": summarized,
        "summary_used": bool(summary),
        "tool_calls": [],
        "rag": rag_meta,
    }
    return {"text": out["text"], "latency": trace, "meta": meta}


def inspect(
    *,
    message: str,
    response_length: str = "medium",
    use_context: bool = True,
    use_rag: bool = False,
    top_k: int = 4,
    rerank: bool = False,
    verbatim_turns: int = 6,
    system_prompt: str | None = None,
    model_key: str = "openai-lite",
    session_id: str | None = None,
    api_key: str | None = None,
    **_ignore: Any,
) -> dict[str, Any]:
    """Context inspector — the exact messages that would be sent + per-message token counts.
    Shows the stored summary + recent turns (does not trigger a new summarization)."""
    spec = _resolve_model(model_key)
    messages, info = assemble(message or "(preview)", response_length=response_length,
                              use_context=use_context, use_rag=use_rag, system_prompt=system_prompt,
                              top_k=top_k, rerank=rerank, api_key=api_key)
    summary, recent = "", []
    if session_id:
        sess = HISTORY.get(session_id)
        _, recent = history.split_for_context(sess["turns"], verbatim_turns)
        summary = sess["summary"]
    final = _build_final(messages, summary, recent)

    rows, total_tokens, total_chars = [], 0, 0
    for m in final:
        t = tokens.count_tokens(m["content"], spec["model"])["tokens"]
        rows.append({"role": m["role"], "content": m["content"], "tokens": t, "chars": len(m["content"])})
        total_tokens += t
        total_chars += len(m["content"])
    return {"total_tokens": total_tokens, "total_chars": total_chars, "messages": rows,
            "knowledge": info["knowledge"], "rag": info["rag"]}
