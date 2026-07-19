"""Filesystem locations for the corpus pipeline."""

from __future__ import annotations

import os

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO_ROOT = os.path.dirname(_BACKEND_DIR)  # voice-agents/

# Source of truth: the frontend site's catalog (override with NIMBUS_CATALOG).
CATALOG_PATH = os.getenv(
    "NIMBUS_CATALOG",
    os.path.join(REPO_ROOT, "frontend", "data", "catalog.json"),
)

DATA_DIR = os.path.join(_BACKEND_DIR, "data")
DOCS_DIR = os.path.join(DATA_DIR, "docs")
PRODUCTS_DIR = os.path.join(DOCS_DIR, "products")
CONTEXT_PATH = os.path.join(DATA_DIR, "context.md")
RAG_DIR = os.path.join(DATA_DIR, "rag")  # FAISS index + chunks + embeddings (Phase 3)
