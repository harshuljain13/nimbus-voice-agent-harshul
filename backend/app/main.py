"""Nimbus Voice Agent backend — FastAPI app (Phase 0 scaffold).

Phase 0 provides:
  * GET /health            — liveness + provider key availability + a demo latency trace
  * GET /config/providers  — provider availability + LLM model registry + embedding profile

Later phases add /scrape, /rag/*, /chat, /asr, /tts, /context/preview and the /ws voice loop.
"""

from __future__ import annotations

import glob
import os

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import __version__, config
from .latency import Timer, empty_trace
from .llm import orchestrator as chat_orch
from .rag import index as rag_index
from .rag import service as rag_service
from .scraping import build_context as bc_mod
from .scraping import paths as corpus_paths
from .scraping import scrape as scrape_mod

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
    tools_enabled: bool = True             # (tools) Phase 7
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
            use_context=req.use_context, use_rag=req.use_rag, top_k=req.top_k,
            system_prompt=req.system_prompt, temperature=req.temperature, mode=req.mode,
            session_id=req.session_id, headers=headers,
        )
    except chat_orch.ChatError as e:
        raise HTTPException(status_code=e.status, detail=e.message)


@app.post("/inspect")
def inspect(req: ChatRequest, request: Request) -> dict:
    """Context inspector: the exact messages that would be sent + per-message token counts."""
    api_key = config.resolve_key("openai", _headers_lower(request))
    try:
        return chat_orch.inspect(
            message=req.message, response_length=req.response_length, use_context=req.use_context,
            use_rag=req.use_rag, top_k=req.top_k, system_prompt=req.system_prompt,
            model_key=req.model_key, api_key=api_key,
        )
    except chat_orch.ChatError as e:
        raise HTTPException(status_code=e.status, detail=e.message)


@app.get("/models")
def models(request: Request) -> dict:
    """Model registry for the picker: which model keys exist and which are usable now."""
    avail = config.provider_availability(_headers_lower(request))
    out = []
    for key, spec in config.LLM_MODELS.items():
        supported = spec["provider"] == "openai"        # Gemini lands in Phase 5
        out.append({
            "key": key,
            "label": _MODEL_LABELS.get(key, key) + ("" if supported else " (Phase 5)"),
            "available": supported and avail.get(spec["provider"], False),
        })
    return {"models": out}


# Stubs so the reference playground loads cleanly; each lights up in its phase.
@app.get("/tools")
def tools() -> dict:
    return {"tools": []}                                # the 11-tool suite → Phase 7


@app.get("/cart")
def cart(session_id: str = Query("")) -> dict:
    return {"items": [], "monthly_total": 0}            # cart → Phase 7


@app.post("/session/reset")
def session_reset(req: SessionRef) -> dict:
    return {"ok": True}                                 # server session/history → Phase 5


# --------------------------------------------------------------------------- #
# Phase 3 — RAG retrieval (R5): chunk · embed · FAISS · top-k                  #
# --------------------------------------------------------------------------- #

class RetrieveRequest(BaseModel):
    query: str
    k: int = 4


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
    """Top-k chunks for a query (for testing + the Phase 4 visualization)."""
    api_key = config.resolve_key("openai", _headers_lower(request))
    try:
        rag_service.ensure_built(api_key)
        res = rag_service.query(req.query, k=req.k, api_key=api_key)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"results": res["results"], "latency": res["latency"], "k": res["k"]}
