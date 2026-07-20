# Tasks: Nimbus Voice Agent

> **North star: [`reference.md`](reference.md)** — every phase builds toward the instructor's
> shipped playground + API contract. Playground work matches the reference's dark control-panel
> design; controls are added incrementally per phase (no disabled stubs).

## Status
**Phases 0–7 ✅ done (48 tests). Phase 12 widget + two-way cart bridge ✅ (deploy pending).
Phases 8–11 (voice + dashboard) planned.** Pushed to `github.com/harshuljain13/nimbus-voice-agent-harshul`.

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

## Phase 6 — Streaming vs batch  (R4)  ✅ DONE
- [x] Streaming path (`stream()` on both providers, `llm_ttft_ms`) + batch; `POST /chat/stream` (SSE); Mode toggle; TTFT in "This turn".
🧪 You test: Mode → Streaming → the answer types out live; TTFT vs total shown. (2 tests; live-verified)

## Phase 7 — Tools + on/off selection  (R2 + R9)  ✅ DONE
- [x] **11 tools** (add_to_cart, cart_total, checkout, annual_pricing, savings_annual_vs_monthly, sort_products, top_k_expensive, remove_item, checkout_item, clear_cart, product_info), each timed; function-call loop; session cart (nimbus_cart shape).
- [x] Master on/off + per-tool All/None/subset (R2 — enforced at dispatch **and** never advertised); tool trace + live cart in the UI.
🧪 You test: tools on → "add 3 seats of CRM Professional + total" → $135, cart fills; "annual savings?" → $324 (20%); untick a tool → agent stops using it. (6 tests; live via real function-calling)

## Phase 8 — ASR (speech in)  (R7)  ✅ DONE
- [x] browser Web Speech (client-side, no key) + OpenAI (gpt-4o-transcribe) / Gemini / ElevenLabs (server, via `/asr`); `audio.py` ffmpeg transcode → 16kHz WAV; transcript fills the chat input; `asr_ms`.
- [x] Playground: **Voice input (ASR)** selector + **🎤 mic** button (MediaRecorder / Web Speech).
🧪 You test: pick a provider, click 🎤, speak → your words fill the input. (5 tests; live-verified via a `say` clip → OpenAI returned it exactly)
Note: live waveform/spectrogram deferred; the full mic→ASR→LLM→TTS loop is Phase 10.

## Phase 9 — TTS (speech out)  (R10)  ← NEXT
- [ ] Adapters: OpenAI + Gemini + ElevenLabs with playback buffer; `tts_ms` + `buffer_ms`.
🧪 You test: agent's answer is spoken aloud; change provider/voice; see the buffer's latency cost.

## Phase 10 — Full voice loop + interrupt + endpointing  (R11 + R12)
- [ ] WebSocket loop mic→ASR→(RAG)→LLM→tools→TTS→playback; barge-in (Off/Low/Med/High) stops TTS; endpoint silence slider (500/700 ms).
🧪 You test: have a spoken back-and-forth; talk over it to interrupt; move the endpoint slider and feel it end turns sooner/later.

## Phase 11 — Latency dashboard  (R13)
- [ ] Combine every stage into a pie/bar of % contribution + total ms; highlight the biggest stage.
🧪 You test: after a turn, see the breakdown chart — which stage cost the most.

## Phase 12 — Playground finalize + landing widget + deploy  (R14)  ◧ PARTIAL (brought forward)
- [x] **`assets/widget.js` "Talk to Nimbus" chatbox on the site** (all pages), tool-enabled, **bridged to the site cart both ways**: pushes `nimbus_cart` → agent before a turn, syncs agent cart → `nimbus_cart` + repaints the drawer after. `POST /cart/set` seeds the session cart; `/cart` returns `product_id`.
- [ ] Polish the playground further; deploy backend → Railway, frontend → Vercel (against the deployed backend).
🧪 You test: on the Nimbus site, open **💬 Talk to Nimbus**, say "add Nimbus CRM Professional" → watch the site's **cart drawer** update live; "remove it" → it disappears. (widget + cart bridge done; deploy remains)

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
