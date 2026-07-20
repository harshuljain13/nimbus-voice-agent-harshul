"""Nimbus Voice Agent backend — FastAPI app (Phase 0 scaffold).

Phase 0 provides:
  * GET /health            — liveness + provider key availability + a demo latency trace
  * GET /config/providers  — provider availability + LLM model registry + embedding profile

Later phases add /scrape, /rag/*, /chat, /asr, /tts, /context/preview and the /ws voice loop.
"""

from __future__ import annotations

import glob
import os

import json

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import __version__, config
from .latency import Timer, empty_trace
from .llm import orchestrator as chat_orch
from .rag import index as rag_index
from .rag import service as rag_service
from .scraping import build_context as bc_mod
from .scraping import paths as corpus_paths
from .scraping import scrape as scrape_mod
from .tools import cart_store
from .tools import registry as tool_registry

app = FastAPI(title="Nimbus Voice Agent Backend", version=__version__)

# Course-scale: allow the static frontend (Vercel / localhost) to call the API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _headers_lower(request: Request) -> dict[str, str]:
    """Request headers with lowercased names (for X-*-Key lookup)."""
    return {k.lower(): v for k, v in request.headers.items()}


def _corpus_doc_count() -> int:
    """How many docs are on disk (drives the health pill; reference.md §3)."""
    return len(glob.glob(os.path.join(corpus_paths.DOCS_DIR, "**", "*.md"), recursive=True))


@app.get("/health")
def health(request: Request) -> dict:
    """Liveness + which providers have a usable key + corpus status + a demo latency trace."""
    t = Timer()
    headers = _headers_lower(request)
    trace = empty_trace()
    trace["total_ms"] = t.ms()
    return {
        "status": "ok",
        "version": __version__,
        "embedding_profile": config.EMBEDDING_PROFILE,
        "require_user_keys": config.REQUIRE_USER_KEYS,
        "providers": config.provider_availability(headers),
        "llm_models": list(config.LLM_MODELS.keys()),
        "corpus": {"doc_count": _corpus_doc_count(),
                   "context_built": os.path.exists(corpus_paths.CONTEXT_PATH)},
        "latency_demo": trace,
    }


@app.get("/config/providers")
def providers(request: Request) -> dict:
    """Provider availability + the LLM model registry + the active embedding profile."""
    headers = _headers_lower(request)
    return {
        "providers": config.provider_availability(headers),
        "llm_models": config.LLM_MODELS,
        "embedding_profile": config.EMBEDDING_PROFILE,
    }


# --------------------------------------------------------------------------- #
# Phase 1 — Web scraping / corpus (R1)                                         #
# --------------------------------------------------------------------------- #

@app.post("/scrape")
def scrape() -> dict:
    """Scrape catalog.json into docs/*.md. Returns the manifest + latency."""
    t = Timer()
    manifest = scrape_mod.scrape_all()
    manifest["latency_ms"] = t.ms()
    return manifest


@app.post("/build-context")
def build_context() -> dict:
    """Concatenate docs/*.md into one context.md (RAGless payload). Returns latency."""
    t = Timer()
    try:
        info = bc_mod.build_context()
    except FileNotFoundError as e:
        raise HTTPException(status_code=409, detail=str(e))
    info["latency_ms"] = t.ms()
    return info


@app.get("/corpus")
def corpus() -> dict:
    """Current corpus status: the docs on disk + whether context.md exists."""
    docs = []
    for p in sorted(glob.glob(os.path.join(corpus_paths.DOCS_DIR, "**", "*.md"), recursive=True)):
        docs.append({
            "name": os.path.relpath(p, corpus_paths.DOCS_DIR),
            "bytes": os.path.getsize(p),
        })
    ctx = None
    if os.path.exists(corpus_paths.CONTEXT_PATH):
        ctx = {"bytes": os.path.getsize(corpus_paths.CONTEXT_PATH)}
    return {"doc_count": len(docs), "docs": docs, "context": ctx}


@app.get("/corpus/file")
def corpus_file(name: str = Query(..., description="doc path relative to docs/, or 'context.md'")) -> dict:
    """Return one doc's raw markdown for preview (path-traversal guarded)."""
    if name == "context.md":
        target = corpus_paths.CONTEXT_PATH
    else:
        target = os.path.normpath(os.path.join(corpus_paths.DOCS_DIR, name))
        if not target.startswith(corpus_paths.DOCS_DIR) or not target.endswith(".md"):
            raise HTTPException(status_code=400, detail="invalid file")
    if not os.path.exists(target):
        raise HTTPException(status_code=404, detail="not found — run /scrape first")
    with open(target, encoding="utf-8") as f:
        return {"name": name, "text": f.read()}


# --------------------------------------------------------------------------- #
# Phase 2 — text chat, on the reference API contract (see .spec-dev/reference.md §3)  #
# Fields for later-phase controls are accepted now but only the Phase 2 subset acts. #
# --------------------------------------------------------------------------- #

_MODEL_LABELS = {
    "openai-lite": "OpenAI · gpt-4o-mini (lite)",
    "openai-heavy": "OpenAI · gpt-4o (heavy)",
    "gemini-flash": "Gemini · 2.5 Flash",
    "gemini-pro": "Gemini · 2.5 Pro",
}


class ChatRequest(BaseModel):
    """One chat turn from the playground (reference payload; Phase 2 honors a subset)."""

    session_id: str | None = None
    message: str
    mode: str = "batch"                    # stream arrives in Phase 6
    model_key: str = "openai-lite"         # config.LLM_MODELS key (OpenAI only until Phase 5)
    response_length: str = "medium"        # low | medium | high
    use_context: bool = True               # RAGless: inject context.md
    use_rag: bool = False                  # RAG arrives in Phase 3-4
    top_k: int = 4                         # (RAG) Phase 3-4
    rerank: bool = False                   # (RAG) Phase 3-4
    verbatim_turns: int = 6                # (history) Phase 5
    temperature: float = 0.3
    system_prompt: str | None = None
    tools_enabled: bool = False            # tools opt-in (Phase 7); the playground checkbox sets it
    enabled_tools: list[str] = Field(default_factory=list)


class SessionRef(BaseModel):
    session_id: str | None = None


@app.post("/chat")
async def chat(req: ChatRequest, request: Request) -> dict:
    """Batch chat grounded in context.md (RAGless) or ungrounded. Returns {text, latency, meta}."""
    headers = _headers_lower(request)
    try:
        return await chat_orch.chat(
            message=req.message, model_key=req.model_key, response_length=req.response_length,
            use_context=req.use_context, use_rag=req.use_rag, top_k=req.top_k, rerank=req.rerank,
            verbatim_turns=req.verbatim_turns, tools_enabled=req.tools_enabled,
            enabled_tools=req.enabled_tools, system_prompt=req.system_prompt,
            temperature=req.temperature, mode="batch", session_id=req.session_id, headers=headers,
        )
    except chat_orch.ChatError as e:
        raise HTTPException(status_code=e.status, detail=e.message)


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request) -> StreamingResponse:
    """Server-sent-events stream of the answer (Phase 6). Tools run in batch mode only."""
    headers = _headers_lower(request)

    async def gen():
        async for ev in chat_orch.chat_stream(
                message=req.message, model_key=req.model_key, response_length=req.response_length,
                use_context=req.use_context, use_rag=req.use_rag, top_k=req.top_k, rerank=req.rerank,
                verbatim_turns=req.verbatim_turns, system_prompt=req.system_prompt,
                temperature=req.temperature, session_id=req.session_id, headers=headers):
            yield f"data: {json.dumps(ev)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/inspect")
def inspect(req: ChatRequest, request: Request) -> dict:
    """Context inspector: the exact messages that would be sent + per-message token counts."""
    api_key = config.resolve_key("openai", _headers_lower(request))
    try:
        return chat_orch.inspect(
            message=req.message, response_length=req.response_length, use_context=req.use_context,
            use_rag=req.use_rag, top_k=req.top_k, rerank=req.rerank, verbatim_turns=req.verbatim_turns,
            system_prompt=req.system_prompt, model_key=req.model_key, session_id=req.session_id,
            api_key=api_key,
        )
    except chat_orch.ChatError as e:
        raise HTTPException(status_code=e.status, detail=e.message)


@app.get("/models")
def models(request: Request) -> dict:
    """Model registry for the picker: which model keys exist and which have a usable key."""
    avail = config.provider_availability(_headers_lower(request))
    return {"models": [
        {"key": key, "label": _MODEL_LABELS.get(key, key), "provider": spec["provider"],
         "available": avail.get(spec["provider"], False)}
        for key, spec in config.LLM_MODELS.items()
    ]}


@app.get("/tools")
def tools() -> dict:
    """The 11 cart/pricing/product tools (name + description) for the on/off panel (Phase 7)."""
    return {"tools": tool_registry.list_tools()}


@app.get("/cart")
def cart(session_id: str = Query("")) -> dict:
    """The session's cart (Phase 7) — item shape mirrors the site's nimbus_cart."""
    items = cart_store.get(session_id)
    return {"items": [{"product_id": i["product_id"], "product_name": i["product_name"], "tier": i["tier"],
                       "seats": i["seats"], "price_monthly": i["price_monthly"]} for i in items],
            "monthly_total": sum(i["price_monthly"] * i["seats"] for i in items)}


class CartSetItem(BaseModel):
    product_id: str | None = None
    product_name: str | None = None
    tier: str | None = None
    seats: int = 1


class CartSetRequest(BaseModel):
    session_id: str
    items: list[CartSetItem] = Field(default_factory=list)


@app.post("/cart/set")
def cart_set(req: CartSetRequest) -> dict:
    """Replace a session's cart from the browser's nimbus_cart (site → agent sync, Phase 12).

    Prices are re-resolved from the catalog so monthly/annual stay correct regardless of what the
    site stored.
    """
    from .tools import catalog_data as cat
    cart_store.clear(req.session_id)
    for it in req.items:
        p = cat.resolve_product(it.product_id or it.product_name or "")
        if not p:
            continue
        t = cat.resolve_tier(p, it.tier)
        if not t:
            continue
        item = {"product_id": p["id"], "product_name": p["name"], "tier": t["name"],
                "price_monthly": float(t.get("priceMonthly") or 0),
                "price_annual_monthly": float(t.get("priceAnnualMonthly") or t.get("priceMonthly") or 0)}
        cart_store.add(req.session_id, item, max(1, int(it.seats or 1)))
    return {"ok": True, "count": len(cart_store.get(req.session_id))}


@app.post("/session/reset")
def session_reset(req: SessionRef) -> dict:
    """Clear a session's conversation history (Phase 5)."""
    if req.session_id:
        chat_orch.HISTORY.reset(req.session_id)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Phase 3 — RAG retrieval (R5): chunk · embed · FAISS · top-k                  #
# --------------------------------------------------------------------------- #

class RetrieveRequest(BaseModel):
    query: str
    k: int = 4
    rerank: bool = False


@app.get("/rag/status")
def rag_status() -> dict:
    """Whether the FAISS index is built + its chunk count / embedding model."""
    return rag_index.status()


@app.post("/rag/build")
def rag_build(request: Request) -> dict:
    """(Re)build the FAISS index from the scraped docs. Uses the OpenAI key for embeddings."""
    api_key = config.resolve_key("openai", _headers_lower(request))
    try:
        return rag_index.build(api_key)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/rag/retrieve")
def rag_retrieve(req: RetrieveRequest, request: Request) -> dict:
    """Top-k chunks for a query (for testing + programmatic use)."""
    api_key = config.resolve_key("openai", _headers_lower(request))
    try:
        rag_service.ensure_built(api_key)
        res = rag_service.query(req.query, k=req.k, do_rerank=req.rerank, api_key=api_key)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"results": res["results"], "latency": res["latency"], "k": res["k"], "reranked": res["reranked"]}


@app.get("/rag/visualization")
def rag_visualization() -> dict:
    """The precomputed 2D scatter of all chunk vectors (PCA) + cluster labels — for rag.html."""
    if not rag_index.is_built():
        raise HTTPException(status_code=409, detail="RAG index not built. POST /rag/build first.")
    proj = rag_index.projection()
    return {"points": proj["points"], "cluster_labels": proj["cluster_labels"],
            "clusters": proj["clusters"], "model": proj["model"], "dim": proj["dim"],
            "profile": proj["profile"]}


@app.post("/rag/query")
def rag_query(req: RetrieveRequest, request: Request) -> dict:
    """Retrieve + project the query into 2D (query point + retrieved ids) for the viz overlay."""
    api_key = config.resolve_key("openai", _headers_lower(request))
    try:
        rag_service.ensure_built(api_key)
        return rag_service.query_with_viz(req.query, k=req.k, do_rerank=req.rerank, api_key=api_key)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
