"""Configuration: provider key registry, model registry, embedding profile.

Keys are read from the environment (`.env` at the repo root or `backend/.env`) and
can be overridden per-request via `X-OpenAI-Key` / `X-Gemini-Key` / `X-ElevenLabs-Key`
headers sent from the frontend. Per-request headers take precedence over env keys.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Load env from a few likely locations without overriding already-set vars.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_BACKEND_DIR)  # voice-agents/
for _p in (os.path.join(_BACKEND_DIR, ".env"), os.path.join(_REPO_ROOT, ".env")):
    load_dotenv(_p, override=False)

# Providers we support in this project (Anthropic is intentionally out of scope).
PROVIDERS: tuple[str, ...] = ("openai", "gemini", "elevenlabs")

# Env var and per-request header name for each provider's key.
ENV_KEYS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
}
HEADER_KEYS: dict[str, str] = {
    "openai": "x-openai-key",
    "gemini": "x-gemini-key",
    "elevenlabs": "x-elevenlabs-key",
}

# LLM model registry: friendly id -> provider + model. (R8)
LLM_MODELS: dict[str, dict[str, str]] = {
    "openai-lite": {"provider": "openai", "model": "gpt-4o-mini"},
    "openai-heavy": {"provider": "openai", "model": "gpt-4o"},
    "gemini-flash": {"provider": "gemini", "model": "gemini-2.5-flash"},
    "gemini-pro": {"provider": "gemini", "model": "gemini-2.5-pro"},
}

# RAG embedding/rerank profile (R5): "light" (OpenAI embed + LLM rerank, Railway-friendly)
# or "rich" (local sentence-transformers + cross-encoder). One env var switches them.
EMBEDDING_PROFILE: str = os.getenv("EMBEDDING_PROFILE", "light").strip().lower() or "light"

# Public-deploy safety (CC1): when true, the server NEVER uses its own .env keys — every request
# must carry the user's own X-*-Key header. Set REQUIRE_USER_KEYS=true on Railway/Vercel so the
# owner's key is never spent by the public; leave it off locally to use .env for convenience.
REQUIRE_USER_KEYS: bool = os.getenv("REQUIRE_USER_KEYS", "").strip().lower() in ("1", "true", "yes")


def env_key(provider: str) -> str:
    """The provider's key from the environment, or empty string."""
    return (os.getenv(ENV_KEYS[provider]) or "").strip()


def resolve_key(provider: str, headers: dict[str, str] | None = None) -> str:
    """Resolve a provider key: per-request header first, then env — unless REQUIRE_USER_KEYS is
    set, in which case only the header key is honored (no fallback to the server's own key)."""
    header_val = ""
    if headers:
        header_val = (headers.get(HEADER_KEYS[provider]) or "").strip()
    if REQUIRE_USER_KEYS:
        return header_val
    return header_val or env_key(provider)


def provider_availability(headers: dict[str, str] | None = None) -> dict[str, bool]:
    """Which providers currently have a usable key (via header or env)."""
    return {p: bool(resolve_key(p, headers)) for p in PROVIDERS}
