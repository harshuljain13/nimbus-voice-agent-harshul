"""TTS (text-to-speech) adapters. Providers implemented in Phase 10 (R10)."""

from __future__ import annotations

from ..adapters import Adapter, Capabilities


class TTSAdapter(Adapter):
    """Text-to-speech. ``run(text, **cfg) -> audio_bytes`` / ``stream(...) -> audio chunks``.

    OpenAI / Gemini / ElevenLabs with playback buffering land in Phase 10.
    """

    capabilities = Capabilities(streaming=True)
