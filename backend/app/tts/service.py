"""Text-to-speech across providers (Phase 9, R10).

The mirror image of ASR: given the agent's answer text, return spoken audio. Three providers —
OpenAI (`gpt-4o-mini-tts`, returns MP3), ElevenLabs (`eleven_turbo_v2_5`, returns MP3), and Gemini
(`gemini-2.5-flash-preview-tts`, returns raw 24 kHz PCM which we wrap into a WAV). Each call returns
the audio bytes + the mime type + `tts_ms` (server-side synth time). Keys are passed in (resolved by
the API layer, honoring REQUIRE_USER_KEYS).
"""

from __future__ import annotations

import base64
import time

import httpx

from .. import audio

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)

PROVIDERS = ("openai", "gemini", "elevenlabs")
_OPENAI_MODEL = "gpt-4o-mini-tts"
_GEMINI_MODEL = "gemini-2.5-flash-preview-tts"
_ELEVEN_MODEL = "eleven_turbo_v2_5"
_GEMINI_PCM_RATE = 24000  # Gemini TTS returns 24 kHz mono 16-bit PCM

# Friendly voice lists per provider (first entry = default). ElevenLabs values are public voice IDs.
VOICES: dict[str, list[dict[str, str]]] = {
    "openai": [{"id": v, "label": v.title()} for v in
               ("alloy", "echo", "fable", "onyx", "nova", "shimmer")],
    "gemini": [{"id": v, "label": v} for v in
               ("Kore", "Puck", "Charon", "Fenrir", "Aoede")],
    "elevenlabs": [
        {"id": "21m00Tcm4TlvDq8ikWAM", "label": "Rachel"},
        {"id": "AZnzlk1XvdvUeBnXmlld", "label": "Domi"},
        {"id": "EXAVITQu4vr4xnSDxMaL", "label": "Bella"},
        {"id": "ErXwobaYiN019PkySvjV", "label": "Antoni"},
        {"id": "pNInz6obpgDQGcFmaJgB", "label": "Adam"},
    ],
}


class TTSError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _default_voice(provider: str) -> str:
    return VOICES[provider][0]["id"]


def _openai(text: str, voice: str, key: str) -> tuple[bytes, str]:
    r = httpx.post(
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": _OPENAI_MODEL, "input": text, "voice": voice, "response_format": "mp3"},
        timeout=_TIMEOUT,
    )
    if r.status_code != 200:
        raise TTSError(r.status_code, f"OpenAI TTS error {r.status_code}: {r.text[:200]}")
    return r.content, "audio/mpeg"


def _elevenlabs(text: str, voice: str, key: str) -> tuple[bytes, str]:
    r = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
        headers={"xi-api-key": key, "accept": "audio/mpeg"},
        json={"text": text, "model_id": _ELEVEN_MODEL},
        timeout=_TIMEOUT,
    )
    if r.status_code != 200:
        raise TTSError(r.status_code, f"ElevenLabs TTS error {r.status_code}: {r.text[:200]}")
    return r.content, "audio/mpeg"


def _gemini(text: str, voice: str, key: str) -> tuple[bytes, str]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}:generateContent?key={key}"
    body = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }
    r = httpx.post(url, json=body, timeout=_TIMEOUT)
    if r.status_code != 200:
        raise TTSError(r.status_code, f"Gemini TTS error {r.status_code}: {r.text[:200]}")
    cand = (r.json().get("candidates") or [{}])[0]
    parts = cand.get("content", {}).get("parts", [])
    b64 = next((p["inlineData"]["data"] for p in parts if "inlineData" in p), None)
    if not b64:
        raise TTSError(502, "Gemini TTS returned no audio.")
    return audio.pcm_to_wav(base64.b64decode(b64), _GEMINI_PCM_RATE), "audio/wav"


_DISPATCH = {"openai": _openai, "gemini": _gemini, "elevenlabs": _elevenlabs}


def synthesize(text: str, provider: str, voice: str | None = None,
               api_key: str | None = None) -> dict:
    """Synthesize speech. Returns {audio: bytes, mime, tts_ms, provider, voice}."""
    if provider not in PROVIDERS:
        raise TTSError(400, f"Unknown TTS provider '{provider}'. Use one of {PROVIDERS}.")
    if not api_key:
        raise TTSError(400, f"Missing {provider} API key for TTS.")
    text = (text or "").strip()
    if not text:
        raise TTSError(400, "Empty text.")
    voice = voice or _default_voice(provider)
    t0 = time.perf_counter()
    data, mime = _DISPATCH[provider](text, voice, api_key)
    return {"audio": data, "mime": mime, "provider": provider, "voice": voice,
            "tts_ms": round((time.perf_counter() - t0) * 1000.0, 2)}
