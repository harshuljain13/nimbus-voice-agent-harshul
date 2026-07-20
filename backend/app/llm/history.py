"""Conversation history — verbatim-N + rolling summary (Phase 5, R8).

A session holds the full turn list (each turn = {"role", "content"}). When building context we
keep the most recent `verbatim` messages as-is and fold everything older into a rolling summary.
The summary is regenerated (one cheap LLM call) only when the aged-out set changes, so
steady-state turns add no summarization latency. In-memory store — fine for the single-process
playground; reset via /session/reset.
"""

from __future__ import annotations

from typing import Any

Turn = dict[str, str]


def _new_session() -> dict[str, Any]:
    return {"turns": [], "summary": "", "summarized_count": 0}


class HistoryStore:
    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}

    def get(self, session_id: str) -> dict[str, Any]:
        return self._sessions.get(session_id) or _new_session()

    def set(self, session_id: str, session: dict[str, Any]) -> None:
        self._sessions[session_id] = session

    def reset(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def append(self, session_id: str, role: str, content: str) -> dict[str, Any]:
        s = self.get(session_id)
        s = {**s, "turns": s["turns"] + [{"role": role, "content": content}]}
        self._sessions[session_id] = s
        return s


def split_for_context(turns: list[Turn], verbatim: int) -> tuple[list[Turn], list[Turn]]:
    """Return (older, recent) where `recent` is the last `verbatim` messages."""
    if verbatim <= 0:
        return turns, []
    if len(turns) <= verbatim:
        return [], turns
    return turns[:-verbatim], turns[-verbatim:]


def needs_summary(session: dict[str, Any], older: list[Turn]) -> bool:
    return bool(older) and len(older) != session["summarized_count"]


def summary_prompt(prev_summary: str, older: list[Turn]) -> list[Turn]:
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in older)
    body = (
        "Summarize the earlier part of this conversation into a compact paragraph that preserves "
        "user intents, facts established, and any product or cart decisions. This summary replaces "
        "the verbatim turns."
    )
    if prev_summary:
        body += f"\n\nExisting summary so far:\n{prev_summary}"
    body += f"\n\nConversation to summarize:\n{convo}"
    return [{"role": "user", "content": body}]
