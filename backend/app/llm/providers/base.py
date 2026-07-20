"""Shared provider error so the orchestrator can catch OpenAI and Gemini uniformly."""

from __future__ import annotations


class ProviderError(RuntimeError):
    """A failed provider call, carrying an HTTP-ish status for the API layer to surface."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
