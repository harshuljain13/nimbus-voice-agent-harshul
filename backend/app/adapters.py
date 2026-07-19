"""Uniform adapter interface for ASR / LLM / TTS providers.

Concrete provider adapters (implemented in later phases) subclass these and are
selected at runtime from the frontend. Keeping one shape means the orchestrator and
the latency trace are provider-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator


@dataclass(frozen=True)
class Capabilities:
    streaming: bool = False


class Adapter:
    """Base for all provider adapters."""

    name: str = "base"
    provider: str = "base"
    capabilities: Capabilities = Capabilities()

    def run(self, *args: Any, **kwargs: Any) -> Any:
        """Batch call. Returns provider output (implemented per phase)."""
        raise NotImplementedError

    async def stream(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        """Streaming call. Yields chunks (implemented per phase)."""
        raise NotImplementedError
        yield  # pragma: no cover  (makes this an async generator)
