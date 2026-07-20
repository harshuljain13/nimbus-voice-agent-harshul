"""Phase 6 (streaming) tests: /chat/stream yields delta events + a done event with TTFT."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.llm.providers import openai as openai_provider
from app.main import app

client = TestClient(app)


def _events(text: str):
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


@pytest.fixture
def fake_stream(monkeypatch):
    async def _stream(*, messages, model, api_key, max_tokens, temperature=0.3, timeout=60.0):
        for tok in ["Hello", ", ", "Nimbus", "!"]:
            yield tok
    monkeypatch.setattr(openai_provider, "stream", _stream)


def test_stream_yields_deltas_then_done(fake_stream):
    r = client.post("/chat/stream", json={"message": "hi", "use_context": False, "use_rag": False})
    assert r.status_code == 200
    evs = _events(r.text)
    deltas = [e for e in evs if e["type"] == "delta"]
    done = next(e for e in evs if e["type"] == "done")
    assert "".join(d["text"] for d in deltas) == "Hello, Nimbus!"
    assert done["text"] == "Hello, Nimbus!"
    # time-to-first-token recorded; the streaming-vs-batch comparison is ttft vs total
    assert "llm_ttft_ms" in done["latency"] and done["latency"]["total_ms"] >= 0
    assert done["meta"]["mode"] == "stream"


def test_stream_error_event_on_empty_message(fake_stream):
    evs = _events(client.post("/chat/stream", json={"message": "  ", "use_context": False}).text)
    assert any(e["type"] == "error" for e in evs)
