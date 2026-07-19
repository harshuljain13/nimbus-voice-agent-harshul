"""Token counting for the context inspector / RAGless cost readout (R8).

Uses ``tiktoken`` when available (exact for OpenAI models), else a chars/4 estimate.
Kept tiny here; the full context inspector (exact assembled prompt) lands in Phase 5.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any


@lru_cache(maxsize=4)
def _encoding(model: str):
    """Cached tiktoken encoding for a model, or ``None`` if tiktoken is unavailable."""
    try:
        import tiktoken
    except Exception:  # noqa: BLE001 — tiktoken optional; fall back to estimate
        return None
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, model: str = "gpt-4o-mini") -> dict[str, Any]:
    """Return ``{tokens, exact}`` — exact via tiktoken, else a rough chars/4 estimate."""
    enc = _encoding(model)
    if enc is None:
        return {"tokens": max(1, len(text) // 4), "exact": False}
    return {"tokens": len(enc.encode(text)), "exact": True}
