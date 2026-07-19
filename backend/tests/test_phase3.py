"""Phase 3 (RAG retrieval) tests: chunking, FAISS index build/search, /chat with RAG, endpoints.

Embeddings are faked with a deterministic bag-of-words vector (so retrieval is meaningful without
OpenAI), the LLM is mocked, and the index is built into a tmp dir — all offline.
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.llm.providers import openai as openai_provider
from app.main import app
from app.rag import chunk as rag_chunk
from app.rag import embed as rag_embed
from app.rag import index as rag_index
from app.scraping import build_context as bc_mod
from app.scraping import paths, scrape

client = TestClient(app)

_DIM = 64


def _bow(texts: list[str]) -> np.ndarray:
    """Deterministic bag-of-words embedding: similar text -> similar (normalized) vector."""
    arr = np.zeros((len(texts), _DIM), dtype="float32")
    for i, t in enumerate(texts):
        for tok in t.lower().split():
            arr[i, hash(tok) % _DIM] += 1.0
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (arr / norms).astype("float32")


@pytest.fixture(scope="module", autouse=True)
def _corpus():
    """Docs must exist for chunking/retrieval."""
    scrape.scrape_all()
    bc_mod.build_context()


@pytest.fixture
def rag_env(tmp_path, monkeypatch):
    """Isolated FAISS dir + faked embeddings, so tests are offline and don't touch real artifacts."""
    rag_dir = tmp_path / "rag"
    monkeypatch.setattr(paths, "RAG_DIR", str(rag_dir))
    monkeypatch.setattr(rag_index, "_FAISS", str(rag_dir / "faiss.index"))
    monkeypatch.setattr(rag_index, "_EMB", str(rag_dir / "embeddings.npy"))
    monkeypatch.setattr(rag_index, "_CHUNKS", str(rag_dir / "chunks.json"))
    monkeypatch.setattr(rag_embed, "embed_texts", lambda texts, api_key=None: _bow(texts))
    monkeypatch.setattr(rag_embed, "embed_query", lambda t, api_key=None: _bow([t])[0])
    rag_index._state.clear()
    yield
    rag_index._state.clear()


@pytest.fixture
def fake_llm(monkeypatch):
    async def _fake(*, messages, model, api_key, max_tokens, temperature=0.3, timeout=60.0):
        return {"text": "Grounded answer.", "usage": {"prompt_tokens": 350, "completion_tokens": 8}, "model": model}
    monkeypatch.setattr(openai_provider, "complete", _fake)


# --- chunking ---------------------------------------------------------------

def test_chunking_splits_docs_with_doc_and_heading():
    chunks = rag_chunk.build_chunks()
    assert len(chunks) > 40                          # many more chunks than the 31 docs
    assert all(c.text.strip() for c in chunks)       # no empty chunks
    assert all(len(c.text) <= rag_chunk.MAX_CHARS for c in chunks)  # windowed
    c = chunks[0]
    assert c.doc and c.heading and c.doc in c.embed_text() and c.heading in c.embed_text()


# --- index build + search ---------------------------------------------------

def test_index_build_and_exact_retrieval(rag_env):
    info = rag_index.build(api_key=None)
    assert info["chunks"] > 40 and info["dim"] == _DIM
    assert rag_index.status()["built"] is True

    chunks = rag_chunk.build_chunks()
    target = next(c for c in chunks if "refund" in c.doc.lower())
    qvec = rag_embed.embed_query(target.embed_text())
    results = rag_index.search(qvec, k=3)
    assert len(results) == 3
    assert results[0]["id"] == target.id             # a chunk retrieves itself first
    assert results[0]["score"] >= results[1]["score"]  # scores descending
    assert {"doc", "heading", "score", "rank"} <= set(results[0])


# --- /chat with RAG ---------------------------------------------------------

def test_chat_rag_uses_small_context_and_reports_chunks(rag_env, fake_llm):
    r = client.post("/chat", json={"message": "What is the refund policy?", "use_context": False,
                                   "use_rag": True, "top_k": 3})
    assert r.status_code == 200
    meta = r.json()["meta"]
    assert meta["knowledge"] == "rag"
    assert meta["rag"]["k"] == 3 and len(meta["rag"]["chunks"]) == 3
    assert all({"doc", "heading", "score"} <= set(c) for c in meta["rag"]["chunks"])
    # RAG prompt is a tiny fraction of the ~23.5k-token RAGless dump
    assert 0 < meta["context_tokens"] < 3000
    assert "rag_ms" in r.json()["latency"]


# --- endpoints --------------------------------------------------------------

def test_rag_status_build_and_retrieve_endpoints(rag_env):
    assert client.get("/rag/status").json()["built"] is False
    built = client.post("/rag/build").json()
    assert built["chunks"] > 40
    st = client.get("/rag/status").json()
    assert st["built"] is True and st["chunks"] == built["chunks"]

    res = client.post("/rag/retrieve", json={"query": "how much does CRM cost", "k": 4}).json()
    assert len(res["results"]) == 4 and res["k"] == 4
    assert "rag_ms" in res["latency"]
