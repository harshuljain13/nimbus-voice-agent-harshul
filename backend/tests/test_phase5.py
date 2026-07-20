"""Phase 5 (LLM controls) tests: conversation history (verbatim + summary), Gemini, reset.

LLM calls mocked (a recorder that captures the messages each call receives), so we can assert
history is actually threaded into the prompt. Offline.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.llm import history
from app.llm.providers import gemini as gemini_provider
from app.llm.providers import openai as openai_provider
from app.main import app

client = TestClient(app)


@pytest.fixture
def rec_llm(monkeypatch):
    """Record the messages each LLM call receives; return canned replies."""
    calls = []

    async def _fake(*, messages, model, api_key, max_tokens, temperature=0.3, timeout=60.0):
        calls.append(messages)
        return {"text": f"reply-{len(calls)}", "usage": {"prompt_tokens": 10, "completion_tokens": 3}, "model": model}

    monkeypatch.setattr(openai_provider, "complete", _fake)
    return calls


def _none(**extra):
    return {"use_context": False, "use_rag": False, **extra}


# --- history split (unit) ---------------------------------------------------

def test_split_for_context():
    turns = [{"role": "user", "content": str(i)} for i in range(5)]
    older, recent = history.split_for_context(turns, 2)
    assert [m["content"] for m in recent] == ["3", "4"] and len(older) == 3
    assert history.split_for_context(turns, 0) == (turns, [])
    assert history.split_for_context(turns, 10) == ([], turns)


# --- multi-turn memory ------------------------------------------------------

def test_multi_turn_history_threaded_into_prompt(rec_llm):
    sid = "s-mem"
    client.post("/chat", json={"message": "My name is Aditya.", "session_id": sid, **_none()})
    client.post("/chat", json={"message": "What is my name?", "session_id": sid, **_none()})
    second = " ".join(m["content"] for m in rec_llm[-1])
    assert "My name is Aditya." in second     # prior user turn carried forward
    assert "reply-1" in second                # prior assistant turn too


def test_history_isolated_per_session(rec_llm):
    client.post("/chat", json={"message": "secret A", "session_id": "s-a", **_none()})
    client.post("/chat", json={"message": "hello", "session_id": "s-b", **_none()})
    assert "secret A" not in " ".join(m["content"] for m in rec_llm[-1])


# --- rolling summary --------------------------------------------------------

def test_summary_kicks_in_beyond_verbatim(rec_llm):
    sid = "s-sum"
    r = None
    for i in range(4):
        r = client.post("/chat", json={"message": f"msg {i}", "session_id": sid, "verbatim_turns": 2, **_none()})
    meta = r.json()["meta"]
    assert meta["summary_used"] is True and meta["summarized_messages"] > 0
    assert meta["verbatim_messages"] <= 2


# --- session reset ----------------------------------------------------------

def test_session_reset_clears_history(rec_llm):
    sid = "s-reset"
    client.post("/chat", json={"message": "remember XYZ", "session_id": sid, **_none()})
    assert client.post("/session/reset", json={"session_id": sid}).json()["ok"] is True
    client.post("/chat", json={"message": "again", "session_id": sid, **_none()})
    assert "remember XYZ" not in " ".join(m["content"] for m in rec_llm[-1])


# --- Gemini provider --------------------------------------------------------

def test_gemini_message_mapping():
    body = gemini_provider._to_gemini(
        [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}])
    assert body["systemInstruction"]["parts"][0]["text"] == "SYS"
    assert [c["role"] for c in body["contents"]] == ["user", "model"]


def test_chat_routes_to_gemini(monkeypatch):
    async def _fake(*, messages, model, api_key, max_tokens, temperature=0.3, timeout=60.0):
        assert api_key == "g-key"                       # Gemini key routed from the header
        return {"text": "gemini hi", "usage": {"prompt_tokens": 5, "completion_tokens": 2}, "model": model}

    monkeypatch.setattr(gemini_provider, "complete", _fake)
    r = client.post("/chat", json={"message": "hi", "model_key": "gemini-flash", **_none()},
                    headers={"X-Gemini-Key": "g-key"})
    assert r.status_code == 200
    assert r.json()["meta"]["provider"] == "gemini" and r.json()["text"] == "gemini hi"
