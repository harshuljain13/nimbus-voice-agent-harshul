# Test Cases: Nimbus Voice Agent

Test cases documented per phase as it completes. **Automated** = pytest in
`backend/tests/`. **Manual** = do it in the playground / browser.

Run automated tests:
```bash
cd backend && . .venv/bin/activate && python -m pytest -q
```

---

## Phase 0 — Foundation ✅

### Automated (`backend/tests/test_phase0.py`) — 5 passing
| # | Test | Verifies |
|---|------|----------|
| 0.1 | `test_health_ok` | `GET /health` → 200; `status=ok`, version present; all 3 providers reported as booleans; `llm_models` list correct; `embedding_profile` ∈ {light,rich}; `latency_demo` has the full 8-key canonical trace |
| 0.2 | `test_per_request_key_override` | ElevenLabs absent in env → `false`; sending `X-ElevenLabs-Key` header flips it → `true` (per-request keys override env) |
| 0.3 | `test_config_providers` | `GET /config/providers` → model registry maps ids→provider+model (`openai-lite`=gpt-4o-mini, `gemini-pro`=gemini); embedding profile surfaced |
| 0.4 | `test_latency_trace_shape_and_shares` | `empty_trace()` has exactly the 8 canonical keys; `timed()` records ≥0 ms; `stage_shares()` percentages sum to 100 |
| 0.5 | `test_cors_allows_frontend_origin` | CORS allows the Vercel frontend origin (`access-control-allow-origin: *`) |

### Manual (playground) — checklist
- [ ] `uvicorn app.main:app --port 8100` up; serve repo root (`python3 -m http.server`) and open `playground/playground.html`.
- [ ] Page renders with the Nimbus design (reused `styles.css`); header + two cards + phase roadmap.
- [ ] **Check backend** → status pill turns **online**; metrics show status/version/profile/round-trip.
- [ ] Provider chips reflect keys: providers with a key show green "on", others red "no key".
- [ ] **API keys** dialog: entering a key + Save persists to `localStorage`; re-checking backend flips that provider's chip to on.
- [ ] Change **Backend** URL to a bad value → status pill turns **offline** with a helpful message (no crash).
- [ ] Phase roadmap lists Phase 0 as active and Phases 1–14 pending.

### Edge cases covered
- Missing provider key → reported as unavailable (not an error).
- Per-request header key takes precedence over `.env`.
- Backend unreachable → frontend degrades gracefully with guidance.

### Notes
- Env in this machine currently exposes **OpenAI** (Gemini/ElevenLabs keys not detected under the
  expected env-var names — confirm names if those providers show "no key" unexpectedly). [OQ]

---

## Phase 1 — Web scraping ✅

### Automated (`backend/tests/test_phase1.py`) — 5 passing
| # | Test | Verifies |
|---|------|----------|
| 1.1 | `test_scrape_covers_every_product_and_topic` | scrape writes 1 doc per product (24) + 7 topic docs = 31; all required topics present (FAQ, Pricing, Families, Refund, T&C, Monthly-vs-Annual, Company); every product name has its own doc |
| 1.2 | `test_annual_savings_math_in_doc` | monthly-vs-annual table math correct (e.g. Nimbus CRM Pro $45→$36 = $9, 20%) |
| 1.3 | `test_build_context_concatenates_all` | `context.md` >50k chars; every product name present; refund policy + "30-day money-back" present |
| 1.4 | `test_endpoints_scrape_build_corpus_preview` | `POST /scrape` ≥24 docs; `POST /build-context` chars>0; `GET /corpus` doc_count≥31 + context bytes>0; `GET /corpus/file?name=refund.md` returns the doc |
| 1.5 | `test_corpus_file_rejects_traversal` | `GET /corpus/file?name=../../config.py` → 400 (path-traversal guarded) |

### Live evaluation (curl, server on :8100)
- `POST /scrape` → 31 docs, 24 products, 103,609 bytes, **4.1 ms**
- `POST /build-context` → context.md 103,787 chars, 31 docs, **2.4 ms**
- `GET /corpus` → doc_count 31, context 103,789 bytes
- `GET /corpus/file?name=faq.md` → returns markdown
- traversal `?name=../../config.py` → **400**

### Manual (playground) — checklist
- [ ] Open `playground.html` → **Phase 1 · Web scraping** card visible.
- [ ] **Scrape → docs** → pill shows "31 docs · N ms"; doc list renders (grouped topic + product docs).
- [ ] **Build context.md** → pill shows "context X KB · N ms".
- [ ] Click any doc (e.g. `products/nimbus-crm.md`) → preview pane shows its markdown.
- [ ] **Refresh** re-reads current corpus status without rescraping.
- [ ] Phase roadmap: Phase 0 = done (green), Phase 1 = active.

### Coverage note
- 24 products across 8 families all covered; 7 topic docs (Company, Families, Pricing,
  Monthly-vs-Annual, Refund, T&C, FAQ). No separate GitHub scraper: `catalog.json` (in the
  repo's `data/`) is the complete source and satisfies R1's "[website/github]" (OQ2 resolved).
- **UI update (Phase 2 redesign):** the "Web scraping" playground card was removed when the
  playground was rebuilt to the reference design. Scraping is now a CLI step (`make scrape`); the
  health pill shows `corpus N docs`. The `/scrape`, `/build-context`, `/corpus` endpoints
  (tests 1.4/1.5) are unchanged.

---

## Phase 2 — RAGless text chat ✅

Playground rebuilt to the **reference design** (dark 3-column control panel; see `reference.md`).
Contract converged on the reference (`message`/`model_key`/`use_context`, `{text, latency, meta}`).

### Automated (`backend/tests/test_phase2.py`) — 13 passing (OpenAI mocked, offline)
| # | Test | Verifies |
|---|------|----------|
| 2.1 | `test_system_prompt_grounds_and_guards` | system prompt injects the context + "answer ONLY from reference" + "don't reveal it's fictional" curation rule |
| 2.2 | `test_response_length_controls_tokens_and_guidance` | low `max_tokens` < high; low adds "1-2 short sentences" |
| 2.3 | `test_system_prompt_override_still_appends_grounding` | a custom prompt still gets the grounding block appended |
| 2.4 | `test_token_count_exact_with_tiktoken` | `tokens.count_tokens` returns an exact tiktoken count |
| 2.5 | `test_chat_returns_text_meta_and_latency` | `POST /chat` → `{text}`; meta `model_key`/`mode`/`knowledge=ragless`, `context_chars>50k`; full 8-key latency trace |
| 2.6 | `test_chat_injects_context_into_the_prompt` | real catalog content ("Refund Policy") reaches the system message; `max_tokens` follows length |
| 2.7 | `test_chat_knowledge_none_skips_grounding` | `use_context=false` → no grounding block in the system message |
| 2.8 | `test_chat_rejects_empty_and_bad_model` | empty message → 400; unknown `model_key` → 400 |
| 2.9 | `test_chat_gemini_stream_and_rag_deferred` | Gemini → 400 (Phase 5); `use_rag` → 400 (Phase 3-4); `mode=stream` → 400 (Phase 6) |
| 2.10 | `test_chat_missing_key_is_a_clear_400` | no OpenAI key → 400 with a "key" message, no network call |
| 2.11 | `test_inspect_returns_messages_and_token_totals` | `POST /inspect` → `{total_tokens, total_chars, messages:[system,user]}` |
| 2.12 | `test_models_lists_openai_available_gemini_deferred` | `GET /models` → openai available; gemini `available=false` + "Phase 5" label |
| 2.13 | `test_health_reports_corpus_and_stubs_load` | `/health` has `corpus.doc_count≥31`; `/tools`,`/cart`,`/rag/status`,`/session/reset` stubs load |

### Live evaluation (real OpenAI, key from `.env`)
- "What is the refund policy?" → "30-day money-back guarantee…" ✅
- "How much is Nimbus CRM Professional per month?" → "$45 per user per month" ✅
- "What families does Nimbus offer?" → lists Sales & CRM, Marketing, Finance, HR, … ✅
- RAGless payload = **23,482 context tokens per turn** (the cost RAG will cut in Phase 3-4).

### Manual (playground) — checklist
- [ ] `make dev` → open the playground; clean **dark 3-column** layout renders; header shows **backend online** (green dot); left **Knowledge base** card reads `31 docs · context.md ready`.
- [ ] OpenAI key set (env or **API keys** dialog); Model picker shows OpenAI models.
- [ ] Ask "What's the refund policy?" → grounded answer; **Latency** shows LLM/total ms; **meta** shows knowledge · ~23.5k ctx tokens · prompt tokens.
- [ ] Ask "How much is Nimbus CRM Professional?" → **$45/user/month**.
- [ ] **Response length** Low↔High → shorter/longer. **Model** lite↔heavy → compare.
- [ ] **Knowledge source → None** → the model admits it lacks Nimbus specifics.
- [ ] **Inspect context** → shows exact system+user prompt + token counts.
- [ ] Empty-state **example-question chips** fire a query in one click.
- [ ] Only live controls are shown (no disabled future-phase stubs); **Reset** clears the chat.

### Edge cases covered
- Empty message / unknown model / RAG-Gemini-stream-too-early → clear 400s.
- Missing key → 400 with guidance, no network call.
- context.md not built → 409 ("run Scrape → Build context.md first" / `make scrape`).
- Knowledge = None → ungrounded prompt; the model admits it lacks Nimbus specifics.

### Notes
- Single-turn only in Phase 2 (no conversation memory); verbatim-N + summary history is Phase 5.
- Scraping moved to a CLI step (`make scrape`) to match the reference; the health pill shows corpus status.
- context.md cached by mtime; rebuilding the corpus auto-invalidates it.
