"""RAG query service (Phase 3, R5): embed → FAISS search → context, with latency.

Reranking (Phase 4) and the visualization data are added later; this delivers the core
retrieve-top-k-and-ground path.
"""

from __future__ import annotations

from ..latency import Timer
from . import embed, index


def ensure_built(api_key: str | None = None) -> dict:
    """Build the index on first use if it's missing; else report status."""
    if not index.is_built():
        return index.build(api_key)
    return index.status()


def format_context(results: list[dict]) -> str:
    """Join retrieved chunks into a grounding block (labeled by doc + heading)."""
    return "\n\n".join(f"[{r['doc']} - {r['heading']}]\n{r['text']}" for r in results)


def query(text: str, k: int = 4, api_key: str | None = None) -> dict:
    """Retrieve top-k chunks for `text`. Returns results + context + latency breakdown."""
    timing: dict[str, float] = {}

    t = Timer()
    qvec = embed.embed_query(text, api_key)
    timing["embed_ms"] = t.ms()

    t = Timer()
    results = index.search(qvec, k)
    timing["search_ms"] = t.ms()

    timing["rag_ms"] = round(timing["embed_ms"] + timing["search_ms"], 2)
    return {
        "results": results,
        "context": format_context(results),
        "latency": timing,
        "k": k,
        "reranked": False,  # Phase 4
    }
