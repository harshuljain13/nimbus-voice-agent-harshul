"""Phase 1 (web scraping) tests: corpus generation + endpoints + coverage."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app
from app.scraping import build_context as bc_mod
from app.scraping import paths, scrape

client = TestClient(app)


def _catalog() -> dict:
    with open(paths.CATALOG_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_scrape_covers_every_product_and_topic():
    manifest = scrape.scrape_all()
    catalog = _catalog()
    # one doc per product + the 7 topic docs
    assert manifest["product_count"] == len(catalog["products"])
    assert manifest["count"] == len(catalog["products"]) + 7
    topics = {d["topic"] for d in manifest["docs"]}
    for required in ("FAQ", "Pricing", "Families", "Refund", "T&C", "Monthly-vs-Annual", "Company"):
        assert required in topics
    # every product name appears as its own doc
    product_topics = {d["topic"] for d in manifest["docs"] if d["topic"].startswith("Product:")}
    for p in catalog["products"]:
        assert f"Product:{p['name']}" in product_topics


def test_annual_savings_math_in_doc():
    scrape.scrape_all()
    with open(paths.DOCS_DIR + "/monthly-vs-annual.md", encoding="utf-8") as f:
        text = f.read()
    # Nimbus CRM Professional: $45 -> $36 = $9 (20%)
    assert "| Nimbus CRM | Professional | $45 | $36 | $9 | 20% |" in text


def test_build_context_concatenates_all():
    scrape.scrape_all()
    info = bc_mod.build_context()
    assert info["chars"] > 50_000
    with open(paths.CONTEXT_PATH, encoding="utf-8") as f:
        ctx = f.read()
    catalog = _catalog()
    # every product represented, plus policy content
    for p in catalog["products"]:
        assert p["name"] in ctx
    assert "Refund Policy" in ctx and "30-day money-back" in ctx


def test_endpoints_scrape_build_corpus_preview():
    assert client.post("/scrape").json()["count"] >= 24
    assert client.post("/build-context").json()["chars"] > 0
    corpus = client.get("/corpus").json()
    assert corpus["doc_count"] >= 31 and corpus["context"]["bytes"] > 0
    # preview a specific doc
    doc = client.get("/corpus/file", params={"name": "refund.md"}).json()
    assert "Refund Policy" in doc["text"]


def test_corpus_file_rejects_traversal():
    r = client.get("/corpus/file", params={"name": "../../config.py"})
    assert r.status_code == 400
