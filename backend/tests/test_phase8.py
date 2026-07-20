"""Phase 8 (ASR) tests: transcribe dispatch + /asr endpoint. Transcode + provider HTTP mocked."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import audio
from app.asr import service as asr
from app.main import app

client = TestClient(app)


class _Resp:
    status_code = 200

    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def test_transcribe_openai(monkeypatch):
    monkeypatch.setattr(audio, "to_wav", lambda data, sample_rate=16000: b"WAV")
    monkeypatch.setattr(asr.httpx, "post", lambda *a, **k: _Resp({"text": "hello nimbus"}))
    out = asr.transcribe(b"audio-bytes", "openai", api_key="sk-x")
    assert out["text"] == "hello nimbus" and out["provider"] == "openai" and out["asr_ms"] >= 0


def test_transcribe_gemini(monkeypatch):
    monkeypatch.setattr(audio, "to_wav", lambda data, sample_rate=16000: b"WAV")
    monkeypatch.setattr(asr.httpx, "post", lambda *a, **k: _Resp({"candidates": [{"content": {"parts": [{"text": "hi"}]}}]}))
    assert asr.transcribe(b"a", "gemini", api_key="k")["text"] == "hi"


def test_transcribe_guards():
    with pytest.raises(asr.ASRError):
        asr.transcribe(b"a", "unknown", api_key="k")        # bad provider
    with pytest.raises(asr.ASRError):
        asr.transcribe(b"a", "openai", api_key="")           # missing key
    with pytest.raises(asr.ASRError):
        asr.transcribe(b"", "openai", api_key="k")           # empty audio


def test_asr_endpoint(monkeypatch):
    monkeypatch.setattr(asr, "transcribe", lambda raw, provider, api_key: {"text": "spoken words", "asr_ms": 12.0, "provider": provider})
    r = client.post("/asr", data={"provider": "openai"}, files={"file": ("a.webm", b"audiobytes", "audio/webm")})
    assert r.status_code == 200
    assert r.json()["text"] == "spoken words" and r.json()["asr_ms"] == 12.0


def test_asr_endpoint_unknown_provider():
    r = client.post("/asr", data={"provider": "nope"}, files={"file": ("a.webm", b"x", "audio/webm")})
    assert r.status_code == 400
