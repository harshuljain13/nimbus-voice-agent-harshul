"""Concatenate the topic docs into one ``context.md`` — the RAGless payload (R1/R6).

Run: ``python -m app.scraping.build_context``  (run ``scrape`` first).
"""

from __future__ import annotations

import glob
import os
from typing import Any

from . import paths

# Order topic docs read best for a single grounding document.
_ORDER = ["company.md", "families.md", "pricing.md", "monthly-vs-annual.md",
          "refund.md", "terms.md", "faq.md"]


def _ordered_doc_paths() -> list[str]:
    files = []
    for name in _ORDER:
        p = os.path.join(paths.DOCS_DIR, name)
        if os.path.exists(p):
            files.append(p)
    files += sorted(glob.glob(os.path.join(paths.PRODUCTS_DIR, "*.md")))
    return files


def build_context() -> dict[str, Any]:
    """Build ``context.md`` from the docs. Returns size + preview info."""
    files = _ordered_doc_paths()
    if not files:
        raise FileNotFoundError("No docs found — run `python -m app.scraping.scrape` first.")

    parts = []
    for p in files:
        with open(p, encoding="utf-8") as f:
            parts.append(f.read().strip())
    text = ("\n\n---\n\n".join(parts)).strip() + "\n"

    os.makedirs(os.path.dirname(paths.CONTEXT_PATH), exist_ok=True)
    with open(paths.CONTEXT_PATH, "w", encoding="utf-8") as f:
        f.write(text)

    return {
        "path": os.path.relpath(paths.CONTEXT_PATH, paths.REPO_ROOT),
        "docs_used": len(files),
        "bytes": len(text.encode("utf-8")),
        "chars": len(text),
        "preview": text[:800],
    }


if __name__ == "__main__":  # pragma: no cover
    info = build_context()
    print(f"Wrote {info['path']} from {info['docs_used']} docs — {info['chars']:,} chars")
