"""Build / load the FAISS index + the 2D projection for the viz (Phase 3-4, R5).

Artifacts (under data/rag/):
  faiss.index      - FAISS IndexFlatIP over normalized vectors (inner product == cosine)
  embeddings.npy   - the same vectors (kept for the query-nearest viz)
  chunks.json      - chunk metadata aligned to vector rows
  projection.json  - {points:[{x,y,cluster,...}], cluster_labels, pca, profile, model, dim}  (Phase 4)
"""

from __future__ import annotations

import json
import os
from collections import Counter

import faiss
import numpy as np

from ..scraping import paths
from . import chunk as chunker
from . import embed, viz_math

_FAISS = os.path.join(paths.RAG_DIR, "faiss.index")
_EMB = os.path.join(paths.RAG_DIR, "embeddings.npy")
_CHUNKS = os.path.join(paths.RAG_DIR, "chunks.json")
_PROJ = os.path.join(paths.RAG_DIR, "projection.json")

_state: dict = {}  # loaded index + metadata, kept in memory after first load

# Friendly names for the non-product topic docs (for the viz legend).
_TOPIC_NAMES = {
    "faq": "FAQ", "refund": "Refund", "terms": "Terms & policies", "pricing": "Pricing",
    "monthly-vs-annual": "Monthly vs annual", "families": "Families", "company": "Company",
}


def is_built() -> bool:
    return os.path.exists(_FAISS) and os.path.exists(_CHUNKS)


def _topic_map() -> dict[str, str]:
    """doc stem → topic label. Product docs map to their catalog category."""
    with open(paths.CATALOG_PATH, encoding="utf-8") as f:
        cat = json.load(f)
    m = {p["id"]: p.get("category", "Products") for p in cat.get("products", [])}
    m.update(_TOPIC_NAMES)
    return m


def _topic_of(doc: str, topics: dict[str, str]) -> str:
    return topics.get(doc) or doc.replace("-", " ").title()


def _cluster_labels(points: list[dict], k: int) -> list[str]:
    """Name each cluster by the most common topic among its chunks (+ a close runner-up)."""
    topics = _topic_map()
    labels: list[str] = []
    for c in range(k):
        members = [_topic_of(p["doc"], topics) for p in points if p["cluster"] == c]
        if not members:
            labels.append(f"cluster {c}")
            continue
        ranked = Counter(members).most_common()
        name = ranked[0][0]
        if len(ranked) > 1 and ranked[1][1] >= ranked[0][1] * 0.6:
            name += " + " + ranked[1][0]
        labels.append(name)
    return labels


def build(api_key: str | None = None, clusters: int = 8) -> dict:
    """Chunk the docs, embed, write the FAISS index + metadata + 2D projection."""
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

    # 2D projection for the visualization (Phase 4).
    mean, comps = viz_math.fit_pca(vectors)
    coords = viz_math.project(vectors, mean, comps)
    labels = viz_math.kmeans(coords, clusters)
    points = [
        {"id": chunks[i].id, "x": float(coords[i, 0]), "y": float(coords[i, 1]),
         "cluster": int(labels[i]), "doc": chunks[i].doc, "heading": chunks[i].heading,
         "text": chunks[i].text}
        for i in range(len(chunks))
    ]
    with open(_PROJ, "w", encoding="utf-8") as f:
        json.dump({"points": points, "cluster_labels": _cluster_labels(points, clusters),
                   "pca": {"mean": mean.tolist(), "components": comps.tolist()},
                   "profile": embed.profile(), "model": embed.model_label(),
                   "dim": dim, "clusters": clusters}, f)

    _state.clear()
    return {"chunks": len(chunks), "dim": dim, "profile": embed.profile(),
            "model": embed.model_label(), "clusters": clusters}


def _load() -> dict:
    if _state:
        return _state
    if not is_built():
        raise RuntimeError("RAG index not built. POST /rag/build first.")
    _state["index"] = faiss.read_index(_FAISS)
    with open(_CHUNKS, encoding="utf-8") as f:
        _state["chunks"] = json.load(f)
    if os.path.exists(_PROJ):
        with open(_PROJ, encoding="utf-8") as f:
            _state["projection"] = json.load(f)
    return _state


def status() -> dict:
    if not is_built():
        return {"built": False, "profile": embed.profile(), "model": embed.model_label()}
    with open(_CHUNKS, encoding="utf-8") as f:
        chunks = json.load(f)
    ix = faiss.read_index(_FAISS)
    st = {"built": True, "chunks": len(chunks), "dim": ix.d,
          "profile": embed.profile(), "model": embed.model_label()}
    if os.path.exists(_PROJ):
        with open(_PROJ, encoding="utf-8") as f:
            st["clusters"] = json.load(f).get("clusters")
    return st


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


def projection() -> dict:
    """The precomputed 2D scatter (points + cluster labels) for the viz page."""
    proj = _load().get("projection")
    if proj is None:
        raise RuntimeError("Projection not built. POST /rag/build to (re)generate it.")
    return proj


def project_query(query_vec: np.ndarray) -> dict:
    """Project a query vector into the same 2D space as the chunk scatter."""
    proj = projection()
    mean = np.array(proj["pca"]["mean"], dtype="float32")
    comps = np.array(proj["pca"]["components"], dtype="float32")
    xy = viz_math.project(query_vec, mean, comps)[0]
    return {"x": float(xy[0]), "y": float(xy[1])}
