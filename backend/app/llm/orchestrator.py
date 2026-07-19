"""Chat orchestration — converging on the reference API contract (see .spec-dev/reference.md §3).

Phases 2-3: batch, single-turn. Knowledge = RAGless (whole context.md), RAG (top-k retrieved
chunks, Phase 3), or none. Returns the reference-shaped `{text, latency, meta}`. Gemini,
streaming, history, and tools are guarded off until their phases.
"""

from __future__ import annotations

import os
from typing import Any

from .. import config
from ..latency import Timer, empty_trace
from ..rag import service as rag_service
from ..scraping import paths
from . import prompts, tokens
from .providers import openai as openai_provider


class ChatError(RuntimeError):
    """A chat turn that couldn't complete, carrying a status for the API layer."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


# context.md is large (~100k chars); cache it and reload only when the file changes.
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
    """Validate the model key and ensure its provider is supported this phase (OpenAI only)."""
    if model_key not in config.LLM_MODELS:
        raise ChatError(400, f"Unknown model_key {model_key!r}. Options: {list(config.LLM_MODELS)}.")
    spec = config.LLM_MODELS[model_key]
    if spec["provider"] != "openai":
        raise ChatError(400, f"Provider {spec['provider']!r} arrives in Phase 5 — Phase 2-3 is OpenAI only.")
    return spec


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
    """Build the message list + grounding metadata. RAG retrieves top-k chunks (optionally
    reranked); RAGless uses the whole context.md; None injects nothing. Shared by chat()/inspect()."""
    rag_info: dict[str, Any] | None = None
    if use_rag:
        knowledge = "rag"
        try:
            rag_service.ensure_built(api_key)
            res = rag_service.query(message, k=top_k, do_rerank=rerank, api_key=api_key)
        except RuntimeError as e:
            raise ChatError(400, f"RAG error: {e}") from e
        context = res["context"]
        rag_info = {
            "k": res["k"],
            "reranked": res["reranked"],
            "rag_ms": res["latency"]["rag_ms"],
            "latency": res["latency"],
            "chunks": [{"doc": r["doc"], "heading": r["heading"], "score": r["score"]} for r in res["results"]],
        }
    elif use_context:
        knowledge = "ragless"
        context = load_context()
    else:
        knowledge = "none"
        context = ""

    grounded = knowledge in ("rag", "ragless")
    messages = prompts.build_messages(message, context, response_length, system_prompt, grounded=grounded)
    info = {
        "knowledge": knowledge,
        "context_chars": len(context),
        "context_tokens": tokens.count_tokens(context)["tokens"] if context else 0,
        "rag": rag_info,
    }
    return messages, info


async def chat(
    *,
    message: str,
    model_key: str = "openai-lite",
    response_length: str = "medium",
    use_context: bool = True,
    use_rag: bool = False,
    top_k: int = 4,
    rerank: bool = False,
    system_prompt: str | None = None,
    temperature: float = 0.3,
    mode: str = "batch",
    session_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run one batch chat turn → reference-shaped ``{text, latency, meta}``."""
    message = (message or "").strip()
    if not message:
        raise ChatError(400, "Empty message.")
    if mode == "stream":
        raise ChatError(400, "Streaming arrives in Phase 6 — use batch for now.")
    spec = _resolve_model(model_key)
    api_key = config.resolve_key("openai", headers)

    trace = empty_trace()
    total = Timer()
    messages, info = assemble(
        message, response_length=response_length, use_context=use_context, use_rag=use_rag,
        system_prompt=system_prompt, top_k=top_k, rerank=rerank, api_key=api_key,
    )
    if info["rag"]:
        trace["rag_ms"] = info["rag"]["rag_ms"]

    llm_timer = Timer()
    try:
        out = await openai_provider.complete(
            messages=messages, model=spec["model"], api_key=api_key,
            max_tokens=prompts.max_tokens_for(response_length), temperature=temperature,
        )
    except openai_provider.OpenAIError as e:
        status = e.status if e.status in (400, 401, 403, 429) else 502
        raise ChatError(status, e.message) from e
    trace["llm_total_ms"] = llm_timer.ms()
    trace["total_ms"] = total.ms()

    usage = out.get("usage", {})
    rag_meta = None
    if info["rag"]:
        rag_meta = {"k": info["rag"]["k"], "reranked": info["rag"]["reranked"],
                    "latency": info["rag"]["latency"], "chunks": info["rag"]["chunks"]}
    meta = {
        "model": out.get("model", spec["model"]),
        "model_key": model_key,
        "mode": "batch",
        "knowledge": info["knowledge"],
        "context_chars": info["context_chars"],
        "context_tokens": info["context_tokens"],
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "system_chars": len(messages[0]["content"]),
        "verbatim_messages": 0,      # history → Phase 5
        "summarized_messages": 0,
        "summary_used": False,
        "tool_calls": [],            # tools → Phase 7
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
    system_prompt: str | None = None,
    model_key: str = "openai-lite",
    api_key: str | None = None,
    **_ignore: Any,
) -> dict[str, Any]:
    """Context inspector — the exact messages that would be sent + per-message token counts."""
    spec = _resolve_model(model_key)
    messages, info = assemble(
        message or "(preview)", response_length=response_length, use_context=use_context,
        use_rag=use_rag, system_prompt=system_prompt, top_k=top_k, rerank=rerank, api_key=api_key,
    )
    rows = []
    total_tokens = total_chars = 0
    for m in messages:
        t = tokens.count_tokens(m["content"], spec["model"])["tokens"]
        rows.append({"role": m["role"], "content": m["content"], "tokens": t, "chars": len(m["content"])})
        total_tokens += t
        total_chars += len(m["content"])
    return {"total_tokens": total_tokens, "total_chars": total_chars, "messages": rows,
            "knowledge": info["knowledge"], "rag": info["rag"]}
