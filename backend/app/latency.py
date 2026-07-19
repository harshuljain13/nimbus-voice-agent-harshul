"""Per-stage latency instrumentation (CC2).

Every turn returns the same fixed trace shape so the frontend dashboard (R13) can
render per-stage contribution consistently:

    {asr_ms, rag_ms, llm_ttft_ms, llm_total_ms, tool_ms, tts_ms, buffer_ms, total_ms}
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

TRACE_KEYS: tuple[str, ...] = (
    "asr_ms",
    "rag_ms",
    "llm_ttft_ms",
    "llm_total_ms",
    "tool_ms",
    "tts_ms",
    "buffer_ms",
    "total_ms",
)


def empty_trace() -> dict[str, float]:
    """A zeroed latency trace with every canonical key present."""
    return {k: 0.0 for k in TRACE_KEYS}


class Timer:
    """Monotonic stopwatch in milliseconds."""

    def __init__(self) -> None:
        self._start = time.perf_counter()

    def ms(self) -> float:
        return round((time.perf_counter() - self._start) * 1000, 2)

    def reset(self) -> None:
        self._start = time.perf_counter()


@contextmanager
def timed(trace: dict[str, float], key: str) -> Iterator[None]:
    """Time a block and record its duration (ms) into ``trace[key]``."""
    if key not in TRACE_KEYS:
        raise KeyError(f"{key!r} is not a canonical latency key: {TRACE_KEYS}")
    t = Timer()
    try:
        yield
    finally:
        trace[key] = t.ms()


def stage_shares(trace: dict[str, float]) -> list[dict[str, float]]:
    """Per-stage percentage contribution for the dashboard (R13).

    Uses the additive stage costs (excludes ``total_ms`` and the streaming-only
    ``llm_ttft_ms``, which is a marker within ``llm_total_ms``).
    """
    stages = ("asr_ms", "rag_ms", "llm_total_ms", "tool_ms", "tts_ms", "buffer_ms")
    total = sum(trace.get(s, 0.0) for s in stages) or 1.0
    return [
        {"stage": s, "ms": trace.get(s, 0.0), "pct": round(100 * trace.get(s, 0.0) / total, 1)}
        for s in stages
    ]
