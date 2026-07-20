# Tasks: Nimbus Voice Agent

> **North star: [`reference.md`](reference.md)** — every phase builds toward the instructor's
> shipped playground + API contract. Playground work matches the reference's dark 3-column
> control-panel design; future-phase controls are shown-but-disabled and light up per phase.

## Status
[ ] Not started  [~] In progress  [x] Done

## How this is organized
- **Each phase = one small, working capability you can test on its own.** No "plumbing-only"
  phases. Every phase ends with a **🧪 You test:** line — a concrete thing to try in the playground.
- Each phase maps to the ordered requirements (R1–R14) it delivers; nothing is dropped.
- Build inside `nimbus-voice-agent-starter/`: `backend/` (FastAPI) + `playground/` static pages.
- Every stage emits `latency_ms`. Trace = `{asr_ms, rag_ms, llm_ttft_ms, llm_total_ms, tool_ms, tts_ms, buffer_ms, total_ms}`.

## Requirement → phase map
R1 scrape→P1 · R6 RAGless→P2 · R8 LLM→P2+P5 · R5 RAG→P3+P4 · R3 RAG/RAGless toggle→P4 ·
R4 streaming/batch→P6 · R2 tools toggle→P7 · R9 tools→P7 · R7 ASR→P8 · R10 TTS→P9 ·
R11 interrupt→P10 · R12 endpoint→P10 · R13 latency dashboard→P11 · R14 playground+widget+deploy→P12

---

## Phase 0 — Foundation ✅ DONE  (scaffold)
Backend `/health` + `/config/providers`, key registry (env + `X-*-Key` headers), latency helper,
adapter stubs; playground shell with keys dialog + backend health check.
🧪 You test: open playground → **Check backend** goes green; add a key → provider chip flips on. (5 tests)

## Phase 1 — Web scraping ✅ DONE  (R1)
`catalog.json` → 24 product docs + 7 topic docs (FAQ/Pricing/Families/Refund/T&C/Monthly-vs-Annual/Company)
→ one `context.md`. Endpoints `/scrape`, `/build-context`, `/corpus`, `/corpus/file`.
🧪 You test: playground **Scrape → docs** (31 docs), **Build context.md**, click a doc to preview. (5 tests)

## Phase 2 — RAGless text chat  (R6 + core of R8)  ✅ DONE
First real answer. Minimal LLM adapter (OpenAI) + inject `context.md`; a text chatbox in the playground.
- [x] `llm/providers/openai.py` `complete()` (httpx, no SDK); `POST /chat {text}` → answer + `llm_total_ms`.
- [x] Inject `context.md` as grounding (RAGless) + ungrounded "None"; response length low/med/high.
- [x] **Playground rebuilt to the reference design** (dark 3-column control panel; see `reference.md`);
      future-phase controls locked with a "Phase N" tag.
- [x] **Contract converged on the reference**: `/chat` `{message,model_key,use_context,…}` → `{text,latency,meta}`;
      `/inspect` (context inspector), `/models`, `/health` corpus; Phase 7/5/3-4 stubs.
🧪 You test: reference-style playground — ask "What's the refund policy?" / "How much is Nimbus CRM Professional?" → grounded answer + latency + inspector. (13 tests; live-verified)

## Phase 3 — RAG retrieval  (R5 part 1)  ✅ DONE
Chunk + embed the docs into FAISS; retrieve top-k and ground the answer on it.
- [x] `rag/chunk.py` (heading split + window) + `rag/embed.py` (profile `light`, OpenAI 1536-d) + `rag/index.py` (FAISS IndexFlatIP) + `service.query(text,k)`.
- [x] `POST /rag/retrieve {query,k}` + `/rag/build` + `/rag/status`; `/chat` honors `use_rag`+`top_k` and returns `meta.rag.chunks` + `rag_ms`.
- [x] Playground: RAG un-locked in Knowledge source + top-k slider + index status; "This turn" shows rag_ms + retrieved chunks with scores.
🧪 You test: Knowledge source → RAG, ask "What's the refund policy?" → tiny context (~500 tok vs 23.5k), retrieved chunks + rag_ms; move top-k. (5 tests; live: 265 chunks, 98% smaller prompt)

## Phase 4 — RAG vs RAGless toggle + rerank + viz  (R3 + R5 part 2)  ✅ DONE
Make retrieval drive the answer, compare against RAGless, add rerank + the vector picture.
- [x] **Compare RAG vs RAGless** button → context/prompt tokens + RAG/LLM/total ms side by side.
- [x] `rag/rerank.py` (LLM rerank, graceful fallback) + rerank toggle (chat + viz); `rerank_ms` surfaced.
- [x] `rag/viz_math.py` (numpy PCA + KMeans); `projection.json` at build; `/rag/visualization` + `/rag/query`.
- [x] `rag.html`: 265-point cluster scatter + query diamond + ranked connectors + hover + rebuild.
🧪 You test: **Compare RAG vs RAGless** (tokens vs latency); toggle rerank; **Vector map ↗** → run a query, see the nearest chunks light up. (6 tests; live-verified)

## Phase 5 — LLM controls  (rest of R8)  ✅ DONE
Make the brain configurable + conversational.
- [x] **Gemini provider** (flash/pro) behind one `complete()` shape; provider dispatch; `/models` lists it (key-gated). (system-prompt editor + length were done in Phase 2.)
- [x] **Conversation history**: last-N verbatim (slider) + rolling summary of older turns; `verbatim_turns`; `meta.verbatim_messages/summarized_messages/summary_used`.
- [x] **RAG-routing** rule in the system prompt; `/session/reset` clears history; inspector shows summary + recent turns.
🧪 You test: (None mode) "My name is Harshul, I love Nimbus CRM" → "what's my name + product?" recalls both; lower the memory slider to see a summary form; Gemini appears in the picker.
Note: interrupt `[cancelled by user]` moves to Phase 10 (voice loop, where barge-in lives).

## Phase 6 — Streaming vs batch  (R4)  ← NEXT
- [ ] Streaming path (`stream()`, `llm_ttft_ms`) + batch (`llm_total_ms`); mode toggle + side-by-side comparison.
🧪 You test: flip streaming/batch → see time-to-first-token vs total latency compared.

## Phase 7 — Tools + on/off selection  (R2 + R9)
- [ ] 11 tools (add_to_cart, cart_total, checkout, annual_price, annual_savings_pct, sort_by_price, top_k_expensive, remove_item, checkout_item, clear_cart, product_lookup) each timed; cart bridged to the site's `nimbus_cart`.
- [ ] Master on/off + per-tool allowlist (all/none/subset) in the playground.
🧪 You test: "add CRM Professional to my cart", "what's my annual total?", "clear cart" → cart updates (and matches the site cart); turn a tool off → the agent stops using it.

## Phase 8 — ASR (speech in)  (R7)
- [ ] Adapters: browser Web Speech (client) + OpenAI + Gemini + ElevenLabs (server); transcript in chatbox; `asr_ms`; live waveform + mel-spectrogram.
🧪 You test: pick a provider, speak → your words appear as text in the chatbox; see the waveform move.

## Phase 9 — TTS (speech out)  (R10)
- [ ] Adapters: OpenAI + Gemini + ElevenLabs with playback buffer; `tts_ms` + `buffer_ms`.
🧪 You test: agent's answer is spoken aloud; change provider/voice; see the buffer's latency cost.

## Phase 10 — Full voice loop + interrupt + endpointing  (R11 + R12)
- [ ] WebSocket loop mic→ASR→(RAG)→LLM→tools→TTS→playback; barge-in (Off/Low/Med/High) stops TTS; endpoint silence slider (500/700 ms).
🧪 You test: have a spoken back-and-forth; talk over it to interrupt; move the endpoint slider and feel it end turns sooner/later.

## Phase 11 — Latency dashboard  (R13)
- [ ] Combine every stage into a pie/bar of % contribution + total ms; highlight the biggest stage.
🧪 You test: after a turn, see the breakdown chart — which stage cost the most.

## Phase 12 — Playground finalize + landing widget + deploy  (R14)
- [ ] Polish the playground; `assets/widget.js` "Talk to Nimbus" chatbox on the landing page bridged to the cart; deploy backend → Railway, frontend already on Vercel.
🧪 You test: use the finalized widget on the Nimbus landing page; everything works against the deployed backend.

## Out of scope
- Public phone number / Twilio (no key); Anthropic (no key); real payments.

## Working agreement (how we run each phase)
1. I build the phase (backend + a **playground panel** — the playground is the one place you
   interact with every phase's functionality).
2. I write a **teaching Report / design doc** at `.spec-dev/phases/phase-NN-*.md` (concept →
   what we built → decisions → how it works → how to test → takeaways → next).
3. I add automated tests + a manual checklist in `.spec-dev/test-cases.md`.
4. **You test it in the playground** and sign off before we start the next phase.

## Notes
- Reorder vs raw instruction order is deliberate: RAGless answer (P2) before the RAG/RAGless toggle
  (P4), and ASR/TTS (P8/P9) before the full voice loop (P10), so **every phase is independently testable**.
  All 14 requirements are still covered (see the map above).
- After each phase: automated tests in `backend/tests/` + a manual checklist in `.spec-dev/test-cases.md`.
