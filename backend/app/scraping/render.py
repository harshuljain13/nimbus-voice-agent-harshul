"""Render catalog.json data into clean per-topic markdown documents (R1).

Topics required by the instruction: FAQ, Products (one per product), Families/
categories, Pricing, Refund, T&C, Monthly-vs-Annual (+ Company for grounding).
"""

from __future__ import annotations

from typing import Any

# Human labels for the policy blocks that make up the Terms doc.
_TERMS_SECTIONS = [
    ("freeTrial", "Free trial"),
    ("billing", "Billing"),
    ("cancellation", "Cancellation"),
    ("sla", "Service level agreement (SLA)"),
    ("security", "Security & compliance"),
    ("dataResidency", "Data residency"),
    ("support", "Support"),
]


def _price(v: Any) -> str:
    return "Custom" if v is None else f"${v}"


def company_md(company: dict) -> str:
    c = company
    lines = [f"# {c.get('name', 'Nimbus')} — Company", ""]
    if c.get("legalName"):
        lines.append(f"**Legal name:** {c['legalName']}")
    if c.get("tagline"):
        lines.append(f"**Tagline:** {c['tagline']}")
    for k in ("founded", "hq"):
        if c.get(k):
            lines.append(f"**{k.capitalize()}:** {c[k]}")
    lines += ["", c.get("about", ""), ""]
    if c.get("mission"):
        lines += [f"**Mission:** {c['mission']}", ""]
    if c.get("stats"):
        lines.append("## Company stats")
        lines += [f"- {k}: {v}" for k, v in c["stats"].items()]
        lines.append("")
    if c.get("contact"):
        lines.append("## Contact")
        lines += [f"- {k}: {v}" for k, v in c["contact"].items()]
    return "\n".join(lines).strip() + "\n"


def refund_md(policies: dict) -> str:
    return f"# Refund Policy\n\n{policies.get('refund', '').strip()}\n"


def terms_md(policies: dict) -> str:
    out = ["# Terms & Policies", ""]
    for key, label in _TERMS_SECTIONS:
        if policies.get(key):
            out += [f"## {label}", "", policies[key].strip(), ""]
    return "\n".join(out).strip() + "\n"


def families_md(categories: list[dict], products: list[dict]) -> str:
    out = ["# Product Families (Categories)", "",
           "Nimbus groups its products into the following families:", ""]
    for cat in categories:
        members = [p["name"] for p in products if p.get("categoryId") == cat["id"]]
        out.append(f"## {cat['name']}")
        out.append(", ".join(members) if members else "_(no products)_")
        out.append("")
    return "\n".join(out).strip() + "\n"


def pricing_md(products: list[dict]) -> str:
    out = ["# Pricing Overview", "",
           "Per-product plan pricing. Prices are per user / month unless noted; "
           "annual plans are billed at the lower annual monthly rate.", ""]
    for p in products:
        out.append(f"## {p['name']}")
        out.append("| Plan | Monthly | Annual (per mo) | Unit |")
        out.append("| --- | --- | --- | --- |")
        for t in p.get("tiers", []):
            out.append(
                f"| {t['name']} | {_price(t.get('priceMonthly'))} | "
                f"{_price(t.get('priceAnnualMonthly'))} | {t.get('unit', '')} |"
            )
        out.append("")
    return "\n".join(out).strip() + "\n"


def monthly_vs_annual_md(products: list[dict], policies: dict) -> str:
    out = ["# Monthly vs Annual Billing", ""]
    if policies.get("billing"):
        out += [policies["billing"].strip(), ""]
    out += ["Choosing annual billing lowers the effective monthly rate on every paid plan. "
            "The table below shows the savings per paid plan.", "",
            "| Product | Plan | Monthly | Annual/mo | Save/mo | Save % |",
            "| --- | --- | --- | --- | --- | --- |"]
    for p in products:
        for t in p.get("tiers", []):
            m, a = t.get("priceMonthly"), t.get("priceAnnualMonthly")
            if not m or a is None:  # skip free (0) and custom (None)
                continue
            save = m - a
            pct = round(100 * save / m) if m else 0
            out.append(f"| {p['name']} | {t['name']} | ${m} | ${a} | ${save} | {pct}% |")
    return "\n".join(out).strip() + "\n"


def faq_md(products: list[dict]) -> str:
    out = ["# Frequently Asked Questions", ""]
    for p in products:
        faqs = p.get("faqs", [])
        if not faqs:
            continue
        out.append(f"## {p['name']}")
        for f in faqs:
            out += [f"**Q: {f['q']}**", "", f"A: {f['a']}", ""]
    return "\n".join(out).strip() + "\n"


def product_md(p: dict) -> str:
    out = [f"# {p['name']}", ""]
    if p.get("tagline"):
        out.append(f"*{p['tagline']}*")
    out += ["", f"**Category:** {p.get('category', '')}", ""]
    if p.get("summary"):
        out += [p["summary"].strip(), ""]
    if p.get("description"):
        out += ["## Overview", "", p["description"].strip(), ""]
    if p.get("keyFeatures"):
        out += ["## Key features"] + [f"- {f}" for f in p["keyFeatures"]] + [""]
    if p.get("specs"):
        out.append("## Specs")
        out += [f"- {k}: {v}" for k, v in p["specs"].items()]
        out.append("")
    if p.get("integrations"):
        out += ["## Integrations", ", ".join(p["integrations"]), ""]
    if p.get("tiers"):
        out += ["## Plans & pricing",
                "| Plan | Monthly | Annual/mo | Unit | Highlights |",
                "| --- | --- | --- | --- | --- |"]
        for t in p["tiers"]:
            hl = "; ".join(t.get("highlights", []))
            out.append(
                f"| {t['name']} | {_price(t.get('priceMonthly'))} | "
                f"{_price(t.get('priceAnnualMonthly'))} | {t.get('unit', '')} | {hl} |"
            )
        out.append("")
    if p.get("addOns"):
        out.append("## Add-ons")
        for a in p["addOns"]:
            out.append(f"- **{a['name']}** ({a.get('price', '')}): {a.get('desc', '')}")
        out.append("")
    if p.get("faqs"):
        out.append("## FAQ")
        for f in p["faqs"]:
            out += [f"**Q: {f['q']}**", "", f"A: {f['a']}", ""]
    return "\n".join(out).strip() + "\n"
