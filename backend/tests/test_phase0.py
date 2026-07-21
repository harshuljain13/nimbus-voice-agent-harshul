"""Phase 0 (foundation) tests: health, config, key override, latency trace, CORS."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.latency import TRACE_KEYS, empty_trace, stage_shares, timed
from app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["version"]
    # all three providers reported (bool each)
    assert set(data["providers"]) == {"openai", "gemini", "elevenlabs"}
    assert all(isinstance(v, bool) for v in data["providers"].values())
    # model registry + embedding profile surfaced
    assert data["llm_models"] == ["openai-lite", "openai-heavy", "gemini-flash", "gemini-pro"]
    assert data["embedding_profile"] in {"light", "rich"}
    # latency demo carries the full canonical trace shape
    assert set(data["latency_demo"]) == set(TRACE_KEYS)


def test_per_request_key_override(monkeypatch):
    # Independent of the developer's .env: ensure no ElevenLabs env key, then a per-request
    # header must flip availability on.
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    base = client.get("/health").json()["providers"]
    assert base["elevenlabs"] is False
    over = client.get("/health", headers={"X-ElevenLabs-Key": "el_test"}).json()["providers"]
    assert over["elevenlabs"] is True


def test_config_providers():
    data = client.get("/config/providers").json()
    assert data["llm_models"]["openai-lite"] == {"provider": "openai", "model": "gpt-4o-mini"}
    assert data["llm_models"]["gemini-pro"]["provider"] == "gemini"
    assert data["embedding_profile"] in {"light", "rich"}


def test_latency_trace_shape_and_shares():
    trace = empty_trace()
    assert set(trace) == set(TRACE_KEYS)
    with timed(trace, "asr_ms"):
        sum(range(1000))
    assert trace["asr_ms"] >= 0.0
    trace["asr_ms"], trace["llm_total_ms"], trace["tts_ms"] = 40.0, 40.0, 20.0
    shares = stage_shares(trace)
    assert round(sum(s["pct"] for s in shares), 1) == 100.0


def test_cors_allows_frontend_origin():
    r = client.get("/health", headers={"Origin": "https://nimbus-harshul.vercel.app"})
    assert r.headers.get("access-control-allow-origin") == "*"
