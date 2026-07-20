"""Filesystem locations for the corpus pipeline."""

from __future__ import annotations

import os

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO_ROOT = os.path.dirname(_BACKEND_DIR)  # voice-agents/

DATA_DIR = os.path.join(_BACKEND_DIR, "data")

# Catalog source: NIMBUS_CATALOG override → the bundled backend copy (so a backend-only deploy is
# self-contained) → the frontend site's copy (local dev before bundling).
_BUNDLED_CATALOG = os.path.join(DATA_DIR, "catalog.json")
CATALOG_PATH = os.getenv("NIMBUS_CATALOG") or (
    _BUNDLED_CATALOG if os.path.exists(_BUNDLED_CATALOG)
    else os.path.join(REPO_ROOT, "frontend", "data", "catalog.json")
)

DOCS_DIR = os.path.join(DATA_DIR, "docs")
PRODUCTS_DIR = os.path.join(DOCS_DIR, "products")
CONTEXT_PATH = os.path.join(DATA_DIR, "context.md")
RAG_DIR = os.path.join(DATA_DIR, "rag")  # FAISS index + chunks + embeddings (Phase 3)
