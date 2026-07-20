"""Phase 7 (tools) tests: the 11 handlers, registry enable/dispatch, /tools + /cart, /chat loop."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.llm.providers import openai as openai_provider
from app.main import app
from app.tools import cart_store
from app.tools import handlers as H
from app.tools import registry

client = TestClient(app)


# --- handlers ---------------------------------------------------------------

def test_cart_add_total_and_savings():
    sid = "t-cart"
    cart_store.clear(sid)
    assert "added" in H.add_to_cart(sid, "Nimbus CRM", "Professional", 2)
    total = H.cart_total(sid)
    assert total["monthly_total"] == 90                       # $45 × 2 seats
    savings = H.savings_annual_vs_monthly(sid)
    assert savings["savings_percent"] == 20.0                 # $45 → $36 annual = 20%
    assert H.clear_cart(sid)["cleared"] == 1
    assert H.cart_total(sid).get("empty") is True


def test_catalog_tools():
    top = H.top_k_expensive(3)
    assert top["k"] == 3 and len(top["products"]) == 3
    asc = H.sort_products("asc")["products"]
    assert asc[0]["starting_price_monthly"] <= asc[-1]["starting_price_monthly"]
    assert H.product_info("crm")["name"] == "Nimbus CRM"
    assert "error" in H.product_info("nonexistent-xyz")


def test_remove_and_checkout_item():
    sid = "t-ci"
    cart_store.clear(sid)
    H.add_to_cart(sid, "Nimbus Projects", "Starter", 1)
    out = H.checkout_item(sid, "Nimbus Projects")
    assert out["order_id"].startswith("NB-") and H.cart_total(sid).get("empty")


# --- registry: enable list + dispatch ---------------------------------------

def test_dispatch_respects_enable_list():
    d = registry.make_dispatch("t-en", ["cart_total"])       # only cart_total allowed
    assert "error" in d("add_to_cart", {"product": "crm"})   # disabled → refused
    assert d("cart_total", {}).get("empty") is True          # allowed
    assert len(registry.enabled_specs(None)) == 11 and registry.enabled_specs([]) == []


def test_tools_and_cart_endpoints():
    assert len(client.get("/tools").json()["tools"]) == 11
    sid = "t-ep"
    cart_store.clear(sid)
    H.add_to_cart(sid, "Nimbus CRM", "Professional", 1)
    d = client.get("/cart", params={"session_id": sid}).json()
    assert d["monthly_total"] == 45 and d["items"][0]["product_name"] == "Nimbus CRM"


# --- /chat tool loop --------------------------------------------------------

def test_chat_runs_tool_loop(monkeypatch):
    async def _fake_cwt(*, messages, model, api_key, tool_schema, dispatch, max_tokens,
                        temperature=0.3, max_iters=6, timeout=60.0):
        result = dispatch("top_k_expensive", {"k": 2})       # exercise the dispatch wiring
        return {"text": "Here are the priciest apps.", "usage": {"prompt_tokens": 20, "completion_tokens": 6},
                "tool_ms": 1.0, "tool_calls": [{"name": "top_k_expensive", "args": {"k": 2}, "result": result, "ms": 1.0}]}

    monkeypatch.setattr(openai_provider, "complete_with_tools", _fake_cwt)
    r = client.post("/chat", json={"message": "top 2 priciest", "use_context": False, "use_rag": False,
                                   "tools_enabled": True, "enabled_tools": ["top_k_expensive"], "session_id": "s7"})
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["tool_calls"][0]["name"] == "top_k_expensive"
    assert body["latency"]["tool_ms"] >= 0
