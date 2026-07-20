# Phase 7 — Tools (Report / Design Doc)

> Status: ✅ Done · Requirements: R9 + R2 (tools on/off) · Tests: 6 passing · Playground: Tools panel + live cart
> Design target: [`../reference.md`](../reference.md).

## 1. Concept — what this phase teaches

Grounding lets the agent *talk* about Nimbus; **tools** let it *act* and compute **exactly**.
Phase 5 showed the LLM fumbling arithmetic ("save $540/year"); a **tool** computes it precisely
and mutates real state (the cart). This is **function calling**: we advertise a set of functions
(with JSON schemas) to the model; it decides to call one, we run it, feed the result back, and it
continues — a loop — until it produces a final answer.

Teaching point: **let the model orchestrate, but let code compute.** The model is great at deciding
*which* tool and *what* args; it's unreliable at math and state. Tools split those responsibilities.

Live proof: "add 3 seats of CRM Professional, then the annual savings" → the model called
`add_to_cart` then `savings_annual_vs_monthly` → **exactly $324/year (20%)**, cart updated.

## 2. What we built

```
backend/app/tools/
  catalog_data.py   read-only catalog access + product/tier resolution ("crm" → Nimbus CRM)
  cart_store.py     in-memory per-session cart (site nimbus_cart shape)
  handlers.py       the 11 handlers (JSON-safe dicts; pricing from catalog tiers)
  registry.py       ToolSpec schemas + enable/disable map + make_dispatch(session, enabled)
providers/openai.py + complete_with_tools(): the function-call loop (call → dispatch → feed back)
llm/orchestrator.py  wires tools into chat(); prompts.py gains a tool-awareness note when tools on
main.py              real /tools (the 11) + /cart (session cart); /chat takes tools_enabled + enabled_tools
```
**The 11 tools:** add_to_cart, cart_total, checkout, annual_pricing, savings_annual_vs_monthly,
sort_products, top_k_expensive, remove_item, checkout_item, clear_cart, product_info.

Playground: a **Tools** on/off toggle + a per-tool checklist with **All / None** (R2); the "This
turn" panel shows **Tools called** (name · args · ms) and a live **Cart** (items + monthly total).

## 3. Design decisions

| Decision | Choice | Why |
|---|---|---|
| Loop location | `complete_with_tools()` in the OpenAI provider | Keeps the multi-round call/dispatch loop next to the API details; the orchestrator just supplies the schema + a dispatch. |
| On/off (R2) | `enabled_tools` list → `make_dispatch` refuses disabled tools **and** they're never advertised | Two layers: the model can't see disabled tools, and even a hallucinated call is refused. |
| `tools_enabled` + no subset | defaults to **all** tools | Turning tools on with no explicit selection means "use them all"; a subset narrows it. |
| Session cart | in-memory, keyed by session_id; item shape mirrors the site's `nimbus_cart` | Bridges to the site cart later; `session_id` is injected by the orchestrator, never by the model. |
| Prompt | a tool-awareness note lists the tools and says "CALL them instead of guessing" | Without it the model computes in its head (and errs); with it, it calls the exact tool. |
| Tools + streaming | tools run in **batch** only | Mid-stream tool calls complicate token delivery; use batch for actions. |
| Errors | every handler + dispatch returns a safe dict; failures never crash the turn | Tool robustness — a bad arg becomes a message the model can recover from. |

## 4. How it works

Batch turn with tools on:
```
build messages (+ a tool note) + advertise the enabled tools' JSON schemas
loop (≤6):
  model → either a final answer (done) or tool_calls
  for each call: dispatch(name, args) → run handler → append result as a "tool" message
model's final answer → {text, meta.tool_calls:[{name,args,result,ms}], latency.tool_ms}
```
The cart lives server-side; `/cart?session_id=` returns it, and the playground refreshes it after
each turn.

## 5. How to test it

1. Tick **Tools** (Batch mode). Ask *"Add 3 seats of Nimbus CRM Professional and give me the
   monthly total."* → **$135**; "This turn" shows **add_to_cart + cart_total**; the **Cart** fills.
2. *"How much would I save per year paying annually?"* → `savings_annual_vs_monthly` → **$324 (20%)**
   — exact, where the plain LLM guessed wrong in Phase 5.
3. *"What are the 3 most expensive products?"* → `top_k_expensive`. *"Sort products cheapest first"*
   → `sort_products`. *"Clear my cart"* → `clear_cart`.
4. **On/off (R2):** untick a tool (or **None**) → the model can no longer use it (it'll say so or
   answer without it). Toggle **Tools** off entirely → pure conversation, no actions.

**Automated:** `make test` (Phase 7 = 6 tests; handlers' math, catalog tools, registry enable/dispatch,
/tools + /cart, and a `/chat` tool-loop with the LLM mocked).
**Live-verified:** add-to-cart + savings via real OpenAI function calling; cart reflects state.

## 6. Key takeaways

- **Function calling = the model picks tools + args; code does the math + state.**
- **On/off is enforced twice** — hidden from the model *and* refused at dispatch.
- **Deterministic tools fix the arithmetic** the LLM guessed at earlier — accuracy you can trust.

## 7. What's next

**Phase 8 — ASR (speech-to-text):** browser / OpenAI / Gemini / ElevenLabs, with the transcript in
the chatbox — the first half of turning this into a *voice* agent.
