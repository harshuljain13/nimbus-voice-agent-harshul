"""Phase 4 (RAG vs RAGless + rerank + 2D viz) tests: PCA/kmeans, projection, rerank, endpoints.

Embeddings faked (deterministic bag-of-words), LLM + rerank HTTP mocked, index in a tmp dir.
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.llm.providers import openai as openai_provider
from app.main import app
from app.rag import embed as rag_embed
from app.rag import index as rag_index
from app.rag import rerank as rag_rerank
from app.rag import service as rag_service
from app.rag import viz_math
from app.scraping import build_context as bc_mod
from app.scraping import paths, scrape

client = TestClient(app)
_DIM = 16


def _bow(texts):
    arr = np.zeros((len(texts), _DIM), dtype="float32")
    for i, t in enumerate(texts):
        for tok in t.lower().split():
            arr[i, hash(tok) % _DIM] += 1.0
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (arr / norms).astype("float32")


@pytest.fixture(scope="module", autouse=True)
def _corpus():
    scrape.scrape_all()
    bc_mod.build_context()


@pytest.fixture
def rag_env(tmp_path, monkeypatch):
    rag_dir = tmp_path / "rag"
    monkeypatch.setattr(paths, "RAG_DIR", str(rag_dir))
    monkeypatch.setattr(rag_index, "_FAISS", str(rag_dir / "faiss.index"))
    monkeypatch.setattr(rag_index, "_EMB", str(rag_dir / "embeddings.npy"))
    monkeypatch.setattr(rag_index, "_CHUNKS", str(rag_dir / "chunks.json"))
    monkeypatch.setattr(rag_index, "_PROJ", str(rag_dir / "projection.json"))
    monkeypatch.setattr(rag_embed, "embed_texts", lambda texts, api_key=None: _bow(texts))
    monkeypatch.setattr(rag_embed, "embed_query", lambda t, api_key=None: _bow([t])[0])
    rag_index._state.clear()
    yield
    rag_index._state.clear()


@pytest.fixture
def fake_llm(monkeypatch):
    async def _fake(*, messages, model, api_key, max_tokens, temperature=0.3, timeout=60.0):
        return {"text": "ok", "usage": {"prompt_tokens": 300, "completion_tokens": 5}, "model": model}
    monkeypatch.setattr(openai_provider, "complete", _fake)


# --- PCA / KMeans -----------------------------------------------------------

def test_viz_math_pca_and_kmeans():
    rng = np.random.default_rng(0)
    v = rng.standard_normal((50, 12)).astype("float32")
    mean, comps = viz_math.fit_pca(v)
    assert mean.shape == (12,) and comps.shape == (2, 12)
    coords = viz_math.project(v, mean, comps)
    assert coords.shape == (50, 2)
    labels = viz_math.kmeans(coords, 5)
    assert labels.shape == (50,) and set(labels.tolist()) <= set(range(5))


# --- projection built into the index ----------------------------------------

def test_index_builds_2d_projection(rag_env):
    info = rag_index.build(clusters=8)
    proj = rag_index.projection()
    assert len(proj["points"]) == info["chunks"]
    p0 = proj["points"][0]
    assert {"x", "y", "cluster", "doc", "heading"} <= set(p0)
    assert len(proj["cluster_labels"]) == 8
    q = rag_index.project_query(rag_embed.embed_query("refund"))
    assert "x" in q and "y" in q


# --- rerank -----------------------------------------------------------------

def test_llm_rerank_reorders_and_falls_back(monkeypatch):
    cands = [{"doc": "a", "heading": "h", "text": "alpha"},
             {"doc": "b", "heading": "h", "text": "beta"},
             {"doc": "c", "heading": "h", "text": "gamma"}]

    class FakeResp:
        status_code = 200
        def json(self): return {"choices": [{"message": {"content": "[2,0,1]"}}]}

    monkeypatch.setattr(rag_rerank.httpx, "post", lambda *a, **k: FakeResp())
    assert [c["doc"] for c in rag_rerank.rerank("q", cands, 2, api_key="sk-test")] == ["c", "a"]
    # no key → graceful fallback to the original vector order
    monkeypatch.setattr(rag_rerank.config, "env_key", lambda p: "")
    assert [c["doc"] for c in rag_rerank.rerank("q", cands, 2, api_key=None)] == ["a", "b"]


def test_service_rerank_records_latency(rag_env, monkeypatch):
    rag_index.build(clusters=8)
    monkeypatch.setattr(rag_rerank, "rerank", lambda q, c, k, api_key=None: list(reversed(c))[:k])
    res = rag_service.query("refund policy", k=3, do_rerank=True)
    assert res["reranked"] is True and "rerank_ms" in res["latency"] and len(res["results"]) == 3


# --- endpoints + chat -------------------------------------------------------

def test_viz_and_query_endpoints(rag_env):
    client.post("/rag/build").raise_for_status()
    viz = client.get("/rag/visualization").json()
    assert len(viz["points"]) > 40 and len(viz["cluster_labels"]) == viz["clusters"]
    q = client.post("/rag/query", json={"query": "how do refunds work", "k": 4}).json()
    assert "query_point" in q and len(q["retrieved_ids"]) == 4 and "rag_ms" in q["latency"]


def test_chat_rerank_flag(rag_env, fake_llm, monkeypatch):
    monkeypatch.setattr(rag_rerank, "rerank", lambda q, c, k, api_key=None: c[:k])
    r = client.post("/chat", json={"message": "refund?", "use_context": False, "use_rag": True,
                                   "top_k": 3, "rerank": True})
    assert r.status_code == 200 and r.json()["meta"]["rag"]["reranked"] is True
