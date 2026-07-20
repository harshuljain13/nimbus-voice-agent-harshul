"""Phase 2 (RAGless text chat) tests: prompt assembly, tokens, /chat endpoint + guards.

The OpenAI call is mocked, so these run offline (no key, no network).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.latency import TRACE_KEYS
from app.llm import orchestrator, prompts, tokens
from app.llm.providers import openai as openai_provider
from app.main import app
from app.scraping import build_context as bc_mod
from app.scraping import scrape

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def _corpus():
    """Ensure docs + context.md exist so RAGless grounding has a payload."""
    scrape.scrape_all()
    bc_mod.build_context()
    orchestrator._context_cache["mtime"] = None  # force reload of the freshly written file


@pytest.fixture
def fake_openai(monkeypatch):
    """Replace the OpenAI HTTP call with a canned answer; record what it was sent."""
    calls = {}

    async def _fake(*, messages, model, api_key, max_tokens, temperature=0.3, timeout=60.0):
        calls.update(messages=messages, model=model, max_tokens=max_tokens)
        return {"text": "Our refund policy is 30-day money-back.",
                "usage": {"completion_tokens": 9, "prompt_tokens": 100},
                "model": model}

    monkeypatch.setattr(openai_provider, "complete", _fake)
    return calls


# --- prompt assembly (pure) -------------------------------------------------

def test_system_prompt_grounds_and_guards():
    sp = prompts.build_system_prompt("NIMBUS FACTS HERE", "medium")
    assert "NIMBUS FACTS HERE" in sp                      # context injected
    assert "ONLY the Nimbus reference information" in sp  # anti-hallucination rule
    assert "fictional" in sp                              # curation: don't reveal it's a demo


def test_response_length_controls_tokens_and_guidance():
    assert prompts.max_tokens_for("low") < prompts.max_tokens_for("high")
    assert "ONE sentence" in prompts.build_system_prompt("x", "low")
    # length directive is placed last (after the grounding block) so the model obeys it
    p = prompts.build_system_prompt("FACTS", "low")
    assert p.index("LENGTH REQUIREMENT") > p.index("END REFERENCE INFORMATION")


def test_system_prompt_override_still_appends_grounding():
    sp = prompts.build_system_prompt("FACTS", "medium", override="Be a pirate.")
    assert "Be a pirate." in sp and "FACTS" in sp


def test_token_count_exact_with_tiktoken():
    out = tokens.count_tokens("hello world", "gpt-4o-mini")
    assert out["tokens"] > 0 and out["exact"] is True


# --- /chat endpoint (mocked LLM), on the reference contract -------------------

def test_chat_returns_text_meta_and_latency(fake_openai):
    r = client.post("/chat", json={"message": "What is the refund policy?"})
    assert r.status_code == 200
    data = r.json()
    assert "30-day money-back" in data["text"]                 # reference shape: {text, ...}
    meta = data["meta"]
    assert meta["model_key"] == "openai-lite" and meta["mode"] == "batch"
    assert meta["knowledge"] == "ragless"
    assert meta["context_chars"] > 50_000 and meta["context_tokens"] > 0
    # full canonical latency trace, with the LLM stage timed
    assert set(data["latency"]) == set(TRACE_KEYS)


def test_chat_injects_context_into_the_prompt(fake_openai):
    client.post("/chat", json={"message": "hi", "response_length": "high"})
    system_msg = fake_openai["messages"][0]["content"]
    assert "Refund Policy" in system_msg                       # real catalog content reached the LLM
    assert fake_openai["max_tokens"] == prompts.max_tokens_for("high")


def test_chat_knowledge_none_skips_grounding(fake_openai):
    client.post("/chat", json={"message": "hi", "use_context": False, "use_rag": False})
    system_msg = fake_openai["messages"][0]["content"]
    assert "NIMBUS REFERENCE INFORMATION" not in system_msg    # None mode: no grounding block


def test_chat_rejects_empty_and_bad_model(fake_openai):
    assert client.post("/chat", json={"message": "   "}).status_code == 400
    assert client.post("/chat", json={"message": "hi", "model_key": "nope"}).status_code == 400


def test_chat_gemini_needs_key(fake_openai):
    # Gemini is a real provider (Phase 5) but errors 400 without a key (none in the test env).
    assert client.post("/chat", json={"message": "hi", "model_key": "gemini-flash"}).status_code == 400


def test_chat_missing_key_is_a_clear_400(monkeypatch):
    # No mock: real provider short-circuits on an empty key without any network call.
    monkeypatch.setattr("app.config.resolve_key", lambda provider, headers=None: "")
    r = client.post("/chat", json={"message": "hi"})
    assert r.status_code == 400
    assert "key" in r.json()["detail"].lower()


# --- new reference endpoints -------------------------------------------------

def test_inspect_returns_messages_and_token_totals(fake_openai):
    r = client.post("/inspect", json={"message": "hi there"})
    assert r.status_code == 200
    d = r.json()
    assert d["total_tokens"] > 0 and d["total_chars"] > 0
    roles = [m["role"] for m in d["messages"]]
    assert roles == ["system", "user"]
    assert d["messages"][1]["content"] == "hi there"


def test_models_lists_availability_by_key():
    d = client.get("/models").json()
    by_key = {m["key"]: m for m in d["models"]}
    assert by_key["openai-lite"]["available"] is True          # OpenAI key present in env
    assert by_key["gemini-flash"]["provider"] == "gemini"      # Gemini is a real provider now (Phase 5)
    # gemini availability just reflects whether a key is present (no hard-coded "deferred")


def test_health_reports_corpus_and_stubs_load():
    h = client.get("/health").json()
    assert h["corpus"]["doc_count"] >= 31 and h["corpus"]["context_built"] is True
    assert len(client.get("/tools").json()["tools"]) == 11     # the 11-tool suite (Phase 7)
    assert client.get("/cart").json()["monthly_total"] == 0    # empty session
    assert "built" in client.get("/rag/status").json()         # real in Phase 3
    assert client.post("/session/reset", json={"session_id": "x"}).json()["ok"] is True
