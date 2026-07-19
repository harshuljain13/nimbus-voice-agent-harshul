"""Scrape the Nimbus catalog into clean per-topic markdown docs (R1).

Reads ``catalog.json`` (the starter site's source of truth) and writes
``backend/data/docs/*.md`` — one doc per required topic plus one per product.

Run: ``python -m app.scraping.scrape``
"""

from __future__ import annotations

import json
import os
from typing import Any

from . import paths, render


def load_catalog(catalog_path: str | None = None) -> dict:
    path = catalog_path or paths.CATALOG_PATH
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(path: str, text: str) -> dict[str, Any]:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return {"path": os.path.relpath(path, paths.DATA_DIR), "bytes": len(text.encode("utf-8"))}


def scrape_all(catalog_path: str | None = None) -> dict[str, Any]:
    """Generate every topic doc. Returns a manifest of what was written."""
    catalog = load_catalog(catalog_path)
    company = catalog.get("company", {})
    policies = catalog.get("policies", {})
    categories = catalog.get("categories", [])
    products = catalog.get("products", [])

    docs: list[dict[str, Any]] = []

    # Topic docs (the instruction's list).
    docs.append({"topic": "Company", **_write(os.path.join(paths.DOCS_DIR, "company.md"), render.company_md(company))})
    docs.append({"topic": "Families", **_write(os.path.join(paths.DOCS_DIR, "families.md"), render.families_md(categories, products))})
    docs.append({"topic": "Pricing", **_write(os.path.join(paths.DOCS_DIR, "pricing.md"), render.pricing_md(products))})
    docs.append({"topic": "Monthly-vs-Annual", **_write(os.path.join(paths.DOCS_DIR, "monthly-vs-annual.md"), render.monthly_vs_annual_md(products, policies))})
    docs.append({"topic": "Refund", **_write(os.path.join(paths.DOCS_DIR, "refund.md"), render.refund_md(policies))})
    docs.append({"topic": "T&C", **_write(os.path.join(paths.DOCS_DIR, "terms.md"), render.terms_md(policies))})
    docs.append({"topic": "FAQ", **_write(os.path.join(paths.DOCS_DIR, "faq.md"), render.faq_md(products))})

    # One doc per product.
    for p in products:
        info = _write(os.path.join(paths.PRODUCTS_DIR, f"{p['id']}.md"), render.product_md(p))
        docs.append({"topic": f"Product:{p['name']}", **info})

    manifest = {
        "catalog": os.path.relpath(catalog_path or paths.CATALOG_PATH, paths.REPO_ROOT),
        "docs_dir": os.path.relpath(paths.DOCS_DIR, paths.REPO_ROOT),
        "count": len(docs),
        "product_count": len(products),
        "docs": docs,
        "total_bytes": sum(d["bytes"] for d in docs),
    }
    return manifest


if __name__ == "__main__":  # pragma: no cover
    m = scrape_all()
    print(f"Wrote {m['count']} docs ({m['product_count']} products) to {m['docs_dir']} "
          f"— {m['total_bytes']:,} bytes")
    for d in m["docs"]:
        print(f"  {d['bytes']:>6,}  {d['path']}")
