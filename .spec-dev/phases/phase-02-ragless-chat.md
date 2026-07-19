# Phase 2 — RAGless Text Chat (Report / Design Doc)

> Status: ✅ Done · Requirements: R6 + core of R8 · Tests: 13 passing · Playground: reference-aligned control panel
> Design target: [`../reference.md`](../reference.md) (matched 1:1 — dark 3-column control panel, reference API contract).

## 1. Concept — what this phase teaches

Phase 1 gave the agent clean facts (`context.md`). This phase makes it **actually answer** —
the first end-to-end turn where a question becomes a grounded reply.

The grounding method here is the simplest one, **RAGless**: paste the *entire* `context.md`
into the system prompt every turn, then ask. No retrieval, no vector DB. Two lessons fall out:

- **Grounding works.** The model has never heard of Nimbus, yet with the facts in the prompt it
  lists the real product families and says "$45/user/month" correctly. Knowledge comes from the
  prompt, not training.
- **RAGless has a price, and it's visible.** Every turn ships **~23.5k tokens** of context —
  shown in the latency panel + context inspector. That number is the whole motivation for RAG
  (Phase 3–4): retrieve a few relevant chunks instead of the whole corpus.

## 2. What we built

**Backend** (`backend/app/llm/`), on the **reference API contract** (`reference.md` §3):
```
providers/openai.py   async complete() over httpx (no SDK)
prompts.py            grounded (RAGless) + ungrounded (None) system prompts; length control
tokens.py             exact token counts via tiktoken
orchestrator.py       assemble → LLM → {text, latency, meta}; plus inspect() (no LLM call)
```
Endpoints (reference-shaped): `POST /chat` `{message, model_key, response_length, use_context,
use_rag, temperature, system_prompt, …}` → `{text, latency, meta}`; `POST /inspect` (context
inspector); `GET /models`; `GET /health` (now reports `corpus.doc_count`); plus stubs that light
up later — `GET /tools` (Phase 7), `GET /cart` (Phase 7), `POST /session/reset` (Phase 5),
`GET /rag/status` (Phase 3–4).

**Playground** — a clean, focused **dark 3-column tool** (config · chat · latency) in the
reference's aesthetic, showing **only what's live**: knowledge-base status, model picker,
response length, knowledge source (RAGless / None), temperature, editable system prompt, an
empty-state with clickable example questions, a **context inspector** (exact prompt + per-message
tokens), and a "This turn" latency/token panel. Future controls are **not shown yet** — the
playground grows one control per phase (no cluttered disabled stubs).

> Scraping is no longer a playground button — like the reference, it's a CLI step
> (`make scrape`); the health pill shows `corpus N docs`. The `/scrape`, `/build-context`,
> `/corpus` endpoints still exist for tooling.

## 3. Design decisions

| Decision | Choice | Why |
|---|---|---|
| Playground design | **Match the reference**: dark, standalone 3-column control panel | It's the target the user is matching; a dedicated instrument (all knobs at a glance) beats a marketing-styled page. Supersedes the light per-phase-cards approach. |
| API contract | Converge on the reference now (`message`/`model_key`/`use_context`, `{text, latency, meta}`) | Avoids double rework; the widget + later phases speak one contract. |
| Grounding method | RAGless — whole `context.md` in the system prompt | Simplest thing that works; the baseline RAG must beat. `use_context=false` = "None" (no grounding). |
| Provider client | Direct HTTP via `httpx`, no `openai` SDK | CC3; one less dependency; extends cleanly to Gemini in Phase 5. |
| Response length | low/med/high → guidance text **and** a `max_tokens` ceiling | R8 length control; makes latency/cost differences observable. |
| Context inspector | `/inspect` returns the exact messages + token counts, no LLM call | Makes the RAGless cost honest and seeds the Phase 5 inspector. |
| History | **None yet** (single system+user turn) | Memory (verbatim-N + summary) is a Phase 5 sub-feature; kept out so this phase stays testable. |
| Future controls | **Not shown** until their phase | Only live controls appear; the playground grows one control per phase. Disabled "Phase N" stubs were tried and dropped (cluttered). |

## 4. How it works

One turn:
```
POST /chat {message, model_key, response_length, use_context, temperature, system_prompt}
  → orchestrator.assemble()   # context.md (cached) + prompt rules → [system, user]
  → openai.complete() httpx   # timed → llm_total_ms
  → { text, latency{…}, meta{model, knowledge, context_tokens, prompt_tokens, system_chars, …} }
```
The system prompt tells the model to answer **only** from the Nimbus reference block, to admit
when it doesn't know, and (curation) never to reveal Nimbus is fictional. `/inspect` runs the
same assembly but returns the messages + token counts instead of calling the LLM. Latency uses
the Phase 0 `Timer`/trace; only `llm_total_ms` + `total_ms` are non-zero until later stages exist.

## 5. How to test it

**In the playground:**
1. `make dev` → open `http://localhost:8092/playground/playground.html`. Health pill shows
   `backend ok · corpus 31 docs`. Set your OpenAI key via **API keys** if not in `.env`.
2. Ask *"What's the refund policy?"* → grounded answer; the **Latency** panel shows LLM/total ms;
   **meta** shows model · knowledge · ~23.5k context tokens · prompt tokens.
3. Ask *"How much is Nimbus CRM Professional?"* → **$45/user/month**.
4. **Response length** Low↔High → shorter/longer answers. **Model** lite↔heavy → compare.
5. **Knowledge source → None**, ask a Nimbus specific → it should say it lacks the details.
6. **Inspect context** → the exact system+user prompt with token counts.
7. Use the empty-state **example-question chips** to fire a query in one click.

**Automated:** `make test` (Phase 2 = 13 tests; OpenAI mocked, offline).
**Live-verified:** families/refund/CRM-pricing answers correct via real OpenAI; ~23.5k ctx tokens/turn.

## 6. Key takeaways

- **Grounding is what makes an LLM useful about your data** — the facts came from the prompt.
- **RAGless is the honest baseline**: simple, correct, but ~23.5k tokens *every* turn — the cost RAG cuts.
- **One contract, matched to the reference** — the playground, widget, and later phases all speak it.
- **Progressive reveal** keeps the finished-product UI visible while we build toward it phase by phase.

## 7. What's next

**Phase 3 — RAG retrieval:** chunk the docs, embed into a FAISS index, retrieve top-k chunks —
the first step toward replacing the 23.5k-token dump with a few hundred relevant tokens, and the
first control (RAG) to un-lock in the panel.
