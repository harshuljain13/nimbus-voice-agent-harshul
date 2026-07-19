"""ASR (speech-to-text) adapters. Providers implemented in Phase 7 (R7)."""

from __future__ import annotations

from ..adapters import Adapter, Capabilities


class ASRAdapter(Adapter):
    """Speech-to-text. ``run(audio_bytes, **cfg) -> {'text': str}``.

    Providers (browser is client-side; OpenAI/Gemini/ElevenLabs server-side) land in Phase 7.
    """

    capabilities = Capabilities(streaming=True)
