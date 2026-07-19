"""Build / load the FAISS index over the chunk embeddings (Phase 3, R5).

Artifacts (under data/rag/):
  faiss.index    - FAISS IndexFlatIP over normalized vectors (inner product == cosine)
  embeddings.npy - the same vectors (kept for the Phase 4 PCA / query-nearest viz)
  chunks.json    - chunk metadata aligned to vector rows

The 2D projection + clustering for the visualization is added in Phase 4.
"""

from __future__ import annotations

import json
import os

import faiss
import numpy as np

from ..scraping import paths
from . import chunk as chunker
from . import embed

_FAISS = os.path.join(paths.RAG_DIR, "faiss.index")
_EMB = os.path.join(paths.RAG_DIR, "embeddings.npy")
_CHUNKS = os.path.join(paths.RAG_DIR, "chunks.json")

_state: dict = {}  # loaded index + metadata, kept in memory after first load


def is_built() -> bool:
    return os.path.exists(_FAISS) and os.path.exists(_CHUNKS)


def build(api_key: str | None = None) -> dict:
    """Chunk the docs, embed them, and write the FAISS index + metadata."""
    os.makedirs(paths.RAG_DIR, exist_ok=True)
    chunks = chunker.build_chunks()
    if not chunks:
        raise RuntimeError("No chunks — run the scraper (make scrape) first.")
    vectors = embed.embed_texts([c.embed_text() for c in chunks], api_key)
    dim = int(vectors.shape[1])

    ix = faiss.IndexFlatIP(dim)
    ix.add(vectors)
    faiss.write_index(ix, _FAISS)
    np.save(_EMB, vectors)
    with open(_CHUNKS, "w", encoding="utf-8") as f:
        json.dump([c.as_dict() for c in chunks], f)

    _state.clear()
    return {"chunks": len(chunks), "dim": dim, "profile": embed.profile(), "model": embed.model_label()}


def _load() -> dict:
    if _state:
        return _state
    if not is_built():
        raise RuntimeError("RAG index not built. POST /rag/build first.")
    _state["index"] = faiss.read_index(_FAISS)
    with open(_CHUNKS, encoding="utf-8") as f:
        _state["chunks"] = json.load(f)
    return _state


def status() -> dict:
    if not is_built():
        return {"built": False, "profile": embed.profile(), "model": embed.model_label()}
    with open(_CHUNKS, encoding="utf-8") as f:
        chunks = json.load(f)
    ix = faiss.read_index(_FAISS)
    return {"built": True, "chunks": len(chunks), "dim": ix.d,
            "profile": embed.profile(), "model": embed.model_label()}


def search(query_vec: np.ndarray, k: int) -> list[dict]:
    """Top-k chunks for a query vector, each with its cosine score + rank."""
    st = _load()
    scores, idx = st["index"].search(query_vec.reshape(1, -1).astype("float32"), k)
    out = []
    for rank, (i, s) in enumerate(zip(idx[0], scores[0])):
        if i < 0:
            continue
        out.append({**st["chunks"][i], "score": round(float(s), 4), "rank": rank})
    return out
