"""Phase 9 (TTS) tests: synthesize dispatch + /tts endpoint. Provider HTTP mocked."""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.tts import service as tts

client = TestClient(app)


class _Resp:
    def __init__(self, *, content=b"", payload=None, status=200):
        self.content = content
        self._p = payload
        self.status_code = status
        self.text = ""

    def json(self):
        return self._p


def test_synthesize_openai(monkeypatch):
    monkeypatch.setattr(tts.httpx, "post", lambda *a, **k: _Resp(content=b"MP3DATA"))
    out = tts.synthesize("hello", "openai", voice="nova", api_key="sk-x")
    assert out["audio"] == b"MP3DATA" and out["mime"] == "audio/mpeg"
    assert out["provider"] == "openai" and out["voice"] == "nova" and out["tts_ms"] >= 0


def test_synthesize_default_voice(monkeypatch):
    monkeypatch.setattr(tts.httpx, "post", lambda *a, **k: _Resp(content=b"MP3"))
    assert tts.synthesize("hi", "openai", api_key="k")["voice"] == "alloy"  # first in VOICES


def test_synthesize_gemini_wraps_pcm(monkeypatch):
    b64 = base64.b64encode(b"\x00\x01" * 8).decode()
    payload = {"candidates": [{"content": {"parts": [{"inlineData": {"data": b64}}]}}]}
    monkeypatch.setattr(tts.httpx, "post", lambda *a, **k: _Resp(payload=payload))
    out = tts.synthesize("hi", "gemini", api_key="k")
    assert out["mime"] == "audio/wav" and out["audio"].startswith(b"RIFF")


def test_synthesize_guards():
    with pytest.raises(tts.TTSError):
        tts.synthesize("hi", "unknown", api_key="k")   # bad provider
    with pytest.raises(tts.TTSError):
        tts.synthesize("hi", "openai", api_key="")      # missing key
    with pytest.raises(tts.TTSError):
        tts.synthesize("", "openai", api_key="k")       # empty text


def test_tts_endpoint(monkeypatch):
    monkeypatch.setattr(tts, "synthesize",
                        lambda text, provider, voice, api_key: {
                            "audio": b"AUDIO", "mime": "audio/mpeg", "provider": provider,
                            "voice": voice or "alloy", "tts_ms": 42.0})
    r = client.post("/tts", json={"text": "hello", "provider": "openai"})
    assert r.status_code == 200 and r.content == b"AUDIO"
    assert r.headers["X-TTS-Ms"] == "42.0" and r.headers["content-type"] == "audio/mpeg"


def test_tts_voices():
    d = client.get("/tts/voices").json()
    assert "openai" in d["voices"] and d["voices"]["openai"][0]["id"] == "alloy"


def test_tts_endpoint_unknown_provider():
    r = client.post("/tts", json={"text": "hi", "provider": "nope"})
    assert r.status_code == 400
