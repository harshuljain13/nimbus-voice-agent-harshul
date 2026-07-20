"""System prompt + message assembly for the grounded RAGless agent (R6 + core R8).

Phase 2 injects the *entire* ``context.md`` into the system prompt (RAGless). The base
prompt seeds the grounding/anti-hallucination rules; the length directive is placed **last**
(after the context block) so the model actually obeys it, and is backed by a hard max-tokens
cap. Editable prompt / RAG-routing / history come in Phase 5 — here every turn is a single
system+user exchange.
"""

from __future__ import annotations

# Response-length control (R8): a concrete directive per level + a hard max-tokens cap.
# The directive is concrete (sentence/word counts) because vague hints ("be concise") get
# ignored under a huge context; the cap enforces it even if the model over-writes.
LENGTH_GUIDANCE: dict[str, str] = {
    "low": "Reply in ONE sentence only (about 15-25 words). No lists, no preamble, no follow-up question.",
    "medium": "Reply in 2-4 sentences (about 40-90 words). Cover the key points, then stop.",
    "high": "Reply in depth (about 150-300 words): cover the relevant specifics and use short bullet points where they help.",
}
MAX_TOKENS: dict[str, int] = {"low": 80, "medium": 320, "high": 1100}

_GROUNDING_BLOCK = (
    "===== NIMBUS REFERENCE INFORMATION =====\n{context}\n"
    "===== END REFERENCE INFORMATION =====")

_BASE_INSTRUCTIONS = (
    "You are the Nimbus assistant, a helpful support and sales agent for Nimbus — an "
    "all-in-one business software suite.\n\n"
    "Ground rules:\n"
    "- Answer using ONLY the Nimbus reference information below. It is the source of truth "
    "for products, families, pricing, and policies.\n"
    "- If the answer is not in the reference information, say you don't have that detail and "
    "offer to help with something else. Never invent products, prices, or policies.\n"
    "- Speak naturally as Nimbus's own assistant. Do not mention that this is a demo, that "
    "Nimbus is fictional, or that you were handed a 'context' document.\n"
    "- Routing: use the reference information for product, family, pricing, and policy questions. "
    "If earlier conversation is summarized above, use it to resolve follow-ups like \"that one\" "
    "or \"the same plan\".")

_UNGROUNDED_INSTRUCTIONS = (
    "You are the Nimbus assistant for Nimbus, an all-in-one business software suite.\n\n"
    "No reference document is attached this turn; answer from general knowledge, and if tools are "
    "available use them to look up real product/pricing details rather than guessing.")

_TOOLS_NOTE = (
    "You can take actions and do exact pricing math with tools: add_to_cart, cart_total, checkout, "
    "remove_item, checkout_item, clear_cart, annual_pricing, savings_annual_vs_monthly, "
    "sort_products, top_k_expensive, product_info. When the user asks for a cart action, a total, "
    "annual savings, a ranking, or a specific product's price, CALL the appropriate tool instead of "
    "guessing — the tools read the real catalog and the live cart.")


def build_system_prompt(
    context: str,
    response_length: str = "medium",
    override: str | None = None,
    grounded: bool = True,
    tools_available: bool = False,
) -> str:
    """Assemble the system prompt: instructions (+ grounding block) then the length directive last.

    ``override`` (Phase 5) replaces the base instructions but, when grounded, still keeps the
    grounding block and the length directive. ``grounded=False`` is the "None" knowledge mode.
    Putting the length directive at the very end is deliberate — it's the instruction the model
    weights most, so low/medium/high produce clearly different answers.
    """
    length = LENGTH_GUIDANCE.get(response_length, LENGTH_GUIDANCE["medium"])
    base = override.strip() if override else (_BASE_INSTRUCTIONS if grounded else _UNGROUNDED_INSTRUCTIONS)
    parts = [base]
    if grounded:
        parts.append(_GROUNDING_BLOCK.format(context=context))
    if tools_available:
        parts.append(_TOOLS_NOTE)
    parts.append(f"LENGTH REQUIREMENT (obey exactly): {length}")
    return "\n\n".join(parts)


def build_messages(
    text: str,
    context: str,
    response_length: str = "medium",
    system_prompt: str | None = None,
    grounded: bool = True,
    tools_available: bool = False,
) -> list[dict[str, str]]:
    """The single-turn message list for a chat call (grounded RAGless, or ungrounded 'None')."""
    return [
        {"role": "system",
         "content": build_system_prompt(context, response_length, system_prompt, grounded, tools_available)},
        {"role": "user", "content": text},
    ]


def max_tokens_for(response_length: str) -> int:
    """Hard output-token cap for a response-length level."""
    return MAX_TOKENS.get(response_length, MAX_TOKENS["medium"])
