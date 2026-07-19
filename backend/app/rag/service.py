"""RAG query service (Phase 3-4, R5): embed → FAISS search → optional rerank → context,
with a latency breakdown, plus the data the 2D visualization needs.
"""

from __future__ import annotations

from ..latency import Timer
from . import embed, index
from . import rerank as reranker

POOL_MULTIPLIER = 3  # candidates fetched before rerank = max(k * this, 12)


def ensure_built(api_key: str | None = None) -> dict:
    """Build the index on first use if it's missing; else report status."""
    if not index.is_built():
        return index.build(api_key)
    return index.status()


def format_context(results: list[dict]) -> str:
    """Join retrieved chunks into a grounding block (labeled by doc + heading)."""
    return "\n\n".join(f"[{r['doc']} - {r['heading']}]\n{r['text']}" for r in results)


def query(text: str, k: int = 4, do_rerank: bool = False, api_key: str | None = None) -> dict:
    """Retrieve top-k chunks for `text` (optionally reranked). Returns results + context + latency."""
    timing: dict[str, float] = {}

    t = Timer()
    qvec = embed.embed_query(text, api_key)
    timing["embed_ms"] = t.ms()

    pool = max(k * POOL_MULTIPLIER, 12) if do_rerank else k
    t = Timer()
    candidates = index.search(qvec, pool)
    timing["search_ms"] = t.ms()

    if do_rerank:
        t = Timer()
        results = reranker.rerank(text, candidates, k, api_key)
        timing["rerank_ms"] = t.ms()
    else:
        results = candidates[:k]
        timing["rerank_ms"] = 0.0

    timing["rag_ms"] = round(timing["embed_ms"] + timing["search_ms"] + timing["rerank_ms"], 2)
    return {"results": results, "context": format_context(results), "latency": timing,
            "qvec": qvec, "k": k, "reranked": do_rerank}


def query_with_viz(text: str, k: int = 4, do_rerank: bool = False, api_key: str | None = None) -> dict:
    """As query(), plus the query's 2D point + retrieved chunk ids for the visualization."""
    res = query(text, k, do_rerank, api_key)
    point = index.project_query(res["qvec"])
    res.pop("qvec", None)
    return {**res, "query_point": point, "retrieved_ids": [r["id"] for r in res["results"]]}
