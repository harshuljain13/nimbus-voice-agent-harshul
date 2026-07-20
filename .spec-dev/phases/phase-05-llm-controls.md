# Phase 5 — LLM Controls: Providers, History, RAG-routing (Report / Design Doc)

> Status: ✅ Done · Requirement: R8 (rest of it) · Tests: 7 passing · Playground: memory slider + Gemini in the picker
> Design target: [`../reference.md`](../reference.md).

## 1. Concept — what this phase teaches

Phase 2 gave the agent a *brain* (one LLM, single-turn). Phase 5 makes it a **real conversational
assistant**:

- **A second provider (Gemini):** the LLM is swappable. One `complete()` shape, two backends.
- **Conversation memory:** the agent remembers earlier turns, so *"what about annually?"* or
  *"which product did I pick?"* work. But you can't keep the *entire* history forever (the prompt
  would grow without bound) — so we keep the **last N messages verbatim** and fold everything
  older into a **rolling summary**. That's the classic verbatim + summary memory model.
- **RAG-routing:** the system prompt now tells the model *when* to lean on the reference vs. do
  pricing math — seeding the behavior tools will formalize in Phase 7.

The teaching point: **context is a budget.** Verbatim memory is precise but expensive; a summary
is cheap but lossy. Keeping recent turns verbatim and summarizing the rest spends the budget where
it matters (the recent thread) — exactly what this phase implements.

## 2. What we built

```
backend/app/llm/
  providers/base.py     shared ProviderError (so OpenAI + Gemini are caught uniformly)
  providers/gemini.py   Gemini generateContent over httpx; maps system→systemInstruction, assistant→model
  history.py            in-memory sessions; split_for_context (last-N verbatim) + rolling summary
  orchestrator.py       provider dispatch {openai, gemini}; history threading; summarize-when-aged-out
  prompts.py            + RAG-routing rule (reference for facts; compute for pricing math; use summary for follow-ups)
```
`/models` now lists Gemini (available iff a `GEMINI_API_KEY` is present); `/session/reset` clears a
session; `/chat` + `/inspect` take `verbatim_turns` and thread the stored history + summary.

Playground: a **Conversation memory** slider (last-N verbatim), a **Memory** readout in "This turn"
(`N verbatim (+ summary)`), Gemini in the model picker, and **Reset** now clears server history too.

## 3. Design decisions

| Decision | Choice | Why |
|---|---|---|
| Memory model | last-N **verbatim** + **rolling summary** of older turns | R8's exact spec; bounds prompt growth while keeping the recent thread exact. |
| Summary timing | regenerate only when the aged-out set changes (cheap `gpt-4o-mini` call) | Steady-state turns add no summarization latency. |
| Session store | in-memory dict, keyed by `session_id` | Single-process playground; no DB needed. `/session/reset` clears it. |
| Provider shape | one `complete(messages, model, api_key, max_tokens, temperature)` for both | Swapping OpenAI↔Gemini is a dispatch-table lookup; the orchestrator is provider-agnostic. |
| Key routing | LLM uses its provider's key; **RAG embed / rerank / summary always use OpenAI** | Embeddings + summarization stay on OpenAI even when the answer model is Gemini. |
| RAG-routing | a rule in the system prompt (facts→reference, pricing→compute, follow-ups→summary) | Seeds R8's routing; tools formalize the "actions" half in Phase 7. |

## 4. How it works

Each turn: build the `[system, user]` pair (Phase 2–4), then wrap history around it —
`[system] + (summary as a system note) + last-N verbatim turns + current user`. Call the chosen
provider. Append this turn's user + assistant messages to the session. If the number of aged-out
(older-than-N) messages changed, regenerate the summary in the background of the request (one cheap
call). `meta` reports `verbatim_messages`, `summarized_messages`, `summary_used`, and `provider`.

## 5. How to test it

**In the playground:**
1. **Memory** — set **Knowledge source → None** (to isolate). Say *"My name is Harshul and I love
   Nimbus CRM."* then *"What's my name and which product?"* → it recalls both. "This turn" shows
   **Memory: N verbatim**.
2. **Follow-ups** — RAGless/RAG: *"How much is Nimbus CRM Professional?"* then *"What about
   annually?"* → it resolves *"that"* from memory.
3. **Summary** — set the **Conversation memory** slider low (e.g. 2) and chat several turns → older
   turns fold into a summary; the readout shows **+ summary**.
4. **Reset** clears the conversation (server-side too).
5. **Gemini** — appears in the Model picker; usable once you add a `GEMINI_API_KEY` (in `.env` or the
   API-keys dialog). Without a key it's greyed.

**Automated:** `make test` (Phase 5 = 7 tests; LLM mocked, offline — asserts prior turns are
threaded into the prompt, summary triggers past the verbatim window, sessions isolate + reset,
Gemini routing/mapping).
**Live-verified:** 2-turn recall correct; `/models` lists Gemini.

## 6. Key takeaways

- **Memory = verbatim (recent, exact) + summary (old, compressed)** — bounded prompt, coherent thread.
- **Providers are pluggable** behind one `complete()` shape; the orchestrator doesn't care which.
- **Not all calls use the same key** — the answer model can be Gemini while embeddings/summary stay OpenAI.

## 7. What's next

**Phase 6 — Streaming vs batch:** stream tokens as they generate and compare **time-to-first-token**
vs total — where a smaller RAG prompt finally shows a *latency* win, not just a cost one.
