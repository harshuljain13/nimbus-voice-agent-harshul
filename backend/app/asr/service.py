"""Speech-to-text across providers (Phase 8, R7).

The **browser** provider is handled client-side (Web Speech API); here we serve OpenAI, Gemini,
and ElevenLabs. Input audio is transcoded to 16 kHz mono WAV first so every provider gets a format
it accepts. Returns transcript + asr_ms. Keys are passed in (resolved by the API layer, honoring
REQUIRE_USER_KEYS).
"""

from __future__ import annotations

import base64
import time

import httpx

from .. import audio

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)

PROVIDERS = ("openai", "gemini", "elevenlabs")   # browser is client-side
_OPENAI_MODEL = "gpt-4o-transcribe"
_GEMINI_MODEL = "gemini-2.5-flash"
_ELEVEN_MODEL = "scribe_v1"


class ASRError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _openai(wav: bytes, key: str) -> str:
    r = httpx.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {key}"},
        files={"file": ("audio.wav", wav, "audio/wav")},
        data={"model": _OPENAI_MODEL, "response_format": "json"}, timeout=_TIMEOUT,
    )
    if r.status_code != 200:
        raise ASRError(r.status_code, f"OpenAI ASR error {r.status_code}: {r.text[:200]}")
    return r.json().get("text", "").strip()


def _elevenlabs(wav: bytes, key: str) -> str:
    r = httpx.post(
        "https://api.elevenlabs.io/v1/speech-to-text",
        headers={"xi-api-key": key},
        files={"file": ("audio.wav", wav, "audio/wav")},
        data={"model_id": _ELEVEN_MODEL}, timeout=_TIMEOUT,
    )
    if r.status_code != 200:
        raise ASRError(r.status_code, f"ElevenLabs ASR error {r.status_code}: {r.text[:200]}")
    return r.json().get("text", "").strip()


def _gemini(wav: bytes, key: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}:generateContent?key={key}"
    body = {"contents": [{"role": "user", "parts": [
        {"text": "Transcribe this audio verbatim. Return only the transcript text."},
        {"inline_data": {"mime_type": "audio/wav", "data": base64.b64encode(wav).decode()}},
    ]}]}
    r = httpx.post(url, json=body, timeout=_TIMEOUT)
    if r.status_code != 200:
        raise ASRError(r.status_code, f"Gemini ASR error {r.status_code}: {r.text[:200]}")
    cand = (r.json().get("candidates") or [{}])[0]
    return "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", [])).strip()


_DISPATCH = {"openai": _openai, "gemini": _gemini, "elevenlabs": _elevenlabs}


def transcribe(raw_audio: bytes, provider: str, api_key: str | None = None) -> dict:
    """Transcode → transcribe with the given provider. Returns {text, asr_ms, provider}."""
    if provider not in PROVIDERS:
        raise ASRError(400, f"Unknown ASR provider '{provider}'. Use one of {PROVIDERS}.")
    if not api_key:
        raise ASRError(400, f"Missing {provider} API key for ASR.")
    if not raw_audio:
        raise ASRError(400, "Empty audio.")
    t0 = time.perf_counter()
    try:
        wav = audio.to_wav(raw_audio)
    except RuntimeError as e:
        raise ASRError(400, str(e)) from e
    text = _DISPATCH[provider](wav, api_key)
    return {"text": text, "asr_ms": round((time.perf_counter() - t0) * 1000.0, 2), "provider": provider}
