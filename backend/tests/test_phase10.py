"""Phase 10 (voice loop) tests: barge-in cancel marker on conversation history.

The loop itself (mic VAD, endpointing, echo-aware barge-in, TTS playback) lives in the
browser and is verified manually. The one server-side change is /session/cancel_last, which
annotates the last assistant turn so the stored context reflects an interrupted answer.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.llm import history as history_mod
from app.llm import orchestrator as chat_orch

client = TestClient(app)


def test_annotate_last_assistant_marks_most_recent():
    store = history_mod.HistoryStore()
    store.append("s1", "user", "hi")
    store.append("s1", "assistant", "Hello, how can I help?")
    store.append("s1", "user", "tell me a long story")
    store.append("s1", "assistant", "Once upon a time")

    assert store.annotate_last_assistant("s1", "[cancelled by the user]") is True
    turns = store.get("s1")["turns"]
    # Only the most recent assistant turn is annotated; earlier ones untouched.
    assert turns[-1]["content"] == "Once upon a time [cancelled by the user]"
    assert turns[1]["content"] == "Hello, how can I help?"


def test_annotate_last_assistant_no_assistant_turn():
    store = history_mod.HistoryStore()
    store.append("s2", "user", "only a user turn")
    assert store.annotate_last_assistant("s2", "[cancelled by the user]") is False


def test_annotate_unknown_session_is_false():
    store = history_mod.HistoryStore()
    assert store.annotate_last_assistant("nope", "[cancelled by the user]") is False


def test_cancel_last_endpoint_annotates(monkeypatch):
    store = history_mod.HistoryStore()
    store.append("sid", "user", "hi")
    store.append("sid", "assistant", "Sure, here is a very long answer")
    monkeypatch.setattr(chat_orch, "HISTORY", store)

    r = client.post("/session/cancel_last", json={"session_id": "sid"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "annotated": True}
    assert store.get("sid")["turns"][-1]["content"].endswith("[cancelled by the user]")


def test_cancel_last_endpoint_no_session():
    r = client.post("/session/cancel_last", json={})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "annotated": False}
