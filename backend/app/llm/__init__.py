"""LLM adapters + orchestration. Providers implemented in Phase 8 (R8)."""

from __future__ import annotations

from ..adapters import Adapter, Capabilities


class LLMAdapter(Adapter):
    """Text generation. ``run(messages, tools=None, **cfg)`` / ``stream(...)``.

    OpenAI (lite/heavy) + Gemini (flash/pro) land in Phase 8. Anthropic is out of scope.
    """

    capabilities = Capabilities(streaming=True)
