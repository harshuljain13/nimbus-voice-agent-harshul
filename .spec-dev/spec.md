# Spec: Nimbus Voice Agent

Status: Draft
Last updated: 2026-07-18

> **North star: [`reference.md`](reference.md)** — the instructor's shipped build
> (github.com/VizuaraAI/nimbus-voice-agent) is the target for playground design, module
> architecture, and API contract. Match it; this spec re-targets our phases at it.

## Summary
A configurable, end-to-end voice agent built **on top of the `nimbus-voice-agent-starter`
site**: one **FastAPI backend** (ASR · RAG · LLM · tools · TTS, every stage timed) plus static
**playground pages** added to the site, deployed on **Vercel (frontend) + Railway (backend)**.
Every pipeline stage is swappable from the frontend and reports latency. The design mirrors the
instructor's shipped reference architecture (grounding only — our own implementation), and the
build is phased **1:1 with the ordered requirements** (Requirement N → Phase N).

## Design Decisions

### D1: Build inside the starter repo — single backend + static pages
**Chosen**: `nimbus-voice-agent-starter/` is the app. Add a `backend/` FastAPI process and a
`playground/` folder of static pages; vendor/keep the starter site as-is.
**Why**: The starter README's "typical path" says exactly this; it's the least code and no
duplication. One process (not a microservice fleet) is enough at course scale and deploys to
Railway cleanly. Rejected: Next.js app, 3-service monorepo, docker-compose.

### D2: Stack + transport
**Chosen**: Python + FastAPI. **WebSocket** carries the streaming voice loop; **REST** for
everything else (scrape, rag, single-stage calls, profiles). Static HTML/CSS/JS frontend
reusing the site's `styles.css`. FAISS local file index.
**Why**: Python is the home for FAISS/embeddings and the provider SDKs; WS maps to the
real-time loop; static pages keep the frontend trivial and Vercel-hostable.

### D3: RAG is a module, not a service
**Chosen**: RAG lives in `backend/app/rag/` (chunk · embed · index · rerank · viz), same
process as the orchestrator. Railway hosts the whole backend.
**Why**: The instructor ships it this way; a separate service adds ops with no course benefit.

### D4: Embedding + rerank as pluggable profiles
**Chosen**: `EMBEDDING_PROFILE` env var switches one shared retrieve/rerank interface:
- `light` (Railway default): OpenAI `text-embedding-3-small` + **LLM rerank** (`gpt-4o-mini`).
  No `torch`, small image, low RAM.
- `rich` (local default): `sentence-transformers` MiniLM + **cross-encoder** rerank; best for
  the clustering visualization.
**Why**: Lets the same code run free/rich locally and lean on Railway. Rejected: hardcoding one
embedding model. Changing profile rebuilds the index.

### D5: LLM providers (Anthropic out)
**Chosen**: OpenAI lite `gpt-4o-mini` + heavy `gpt-4o`; Gemini `flash` + `pro`. Unified
`complete()` / `stream()` adapter. **Anthropic not built (no key).**

### D6: ASR / TTS providers
**Chosen**: ASR = browser Web Speech (client-side) + OpenAI + Gemini + ElevenLabs (server).
TTS = OpenAI + Gemini + ElevenLabs with a playback **buffer**. Audio transcode via bundled
ffmpeg (`imageio-ffmpeg`). Default agent config: ElevenLabs ASR+TTS.

### D7: Streaming vs batch + latency model
**Chosen**: A `mode` flag. Batch awaits each stage; streaming pipelines LLM tokens into TTS
chunks. Every turn returns a fixed trace:
`{asr_ms, rag_ms, llm_ttft_ms, llm_total_ms, tool_ms, tts_ms, buffer_ms, total_ms}`.
The streaming-vs-batch comparison is `llm_ttft_ms` vs `llm_total_ms`; the dashboard renders
per-stage % (pie/bar) + total.

### D8: Tools — 11 tools, allowlist, shared cart
**Chosen**: 11 tools with JSON schemas in a `registry.py` carrying an enable/disable map; only
allowed tools are advertised to the LLM. Tool-call loop in the orchestrator, each call timed
(`tool_ms`). Cart state matches the site's `nimbus_cart` (localStorage key, item shape
`{product_id, product_name, tier, seats, price}`) so site and agent stay in sync.
Tools: add_to_cart, cart_total, checkout (whole cart), annual_price, annual_savings_pct,
sort_products_by_price(order), top_k_expensive(k), remove_item, checkout_item, clear_cart,
product_lookup (get product/tier details for grounding).

### D9: LLM control — prompt, length, history, RAG routing, context inspector
**Chosen**: Editable system prompt; response length low/med/high (max-tokens + prompt guidance);
history = last-N verbatim (slider) + rolling summary of older turns; system prompt encodes RAG
routing (catalog/policy facts → RAG; cart math/actions → tools, no RAG). A **context inspector**
returns the exact assembled prompt + token count (`tiktoken`).

### D10: Interrupt + endpointing
**Chosen**: Client VAD endpointing with a silence-duration slider (500/700 ms…). Barge-in is an
echo-aware double-talk detector with Off/Low/Medium/High sensitivity; on interrupt, halt TTS and
append `[cancelled by user]` to history so context matches what was actually heard.

### D11: Frontend keys + config
**Chosen**: Keys entered in-page (dialog) → `localStorage` → sent as `X-*-Key` headers;
precedence over `.env`. `runtime-config.js` holds the default backend URL. No key logged/committed.

### D12: Playground surfaces — MATCH THE REFERENCE (see `reference.md`)
**Chosen**: Adopt the instructor's shipped design 1:1 (`.spec-dev/reference.md` §1, §3). The
playground is a **standalone dark control panel** (GitHub-dark tokens `--bg:#0d1117`,
`--brand:#6e8bff→#9d7bff`), NOT the light marketing-site look. `playground.html` is a
**3-column app**: left `controls` (model, mode, length, knowledge source, top-k, rerank,
verbatim history, temperature, system prompt, tools), center `chat`, right `latency` (per-stage
bars + streaming-vs-batch table + cart + tool trace), with `<dialog>` modals for **API keys**
and a **context inspector**. Separate `voice.html` (voice loop) + `rag.html` (vector viz);
landing widget = `assets/widget.js`. Component vocabulary is fixed: `.seg`, `.switch`, range
sliders, `.btn*`, `.pill*`, `.msg-*`, `.lat-*` (reference class names).
**Incremental, not all-at-once**: the playground shows **only the controls that are live today**
and grows one control at a time as each phase lands. We do NOT pre-render future controls as
disabled "Phase N" stubs — that made the UI cluttered and unclear (user feedback). The design
target/aesthetic is the reference's clean dark tool; the *scope* of what's shown tracks our
phases. **Why**: a small, focused, obviously-testable surface beats a wall of dead knobs.
**Supersedes** both the earlier "light per-phase cards" approach and the interim
"all-controls-disabled-with-tags" attempt.

## Architecture / Approach

```
nimbus-voice-agent-starter/            # the app (build here)
├── index.html …                        existing catalog pages (unchanged)
│    └─ assets/widget.js                 finalized agent chatbox (R14), bridged to nimbus_cart
├── playground/                          static frontend (Vercel)
│    ├── playground.(html|js|css)        control panel (R2–R8, R13)
│    ├── voice.(html|js|css)             full voice loop (R7,R10,R11,R12)
│    ├── rag.(html|js|css)               vector/query viz (R5)
│    └── runtime-config.js               default backend URL
└── backend/                             FastAPI (Railway) — one process, per-stage latency
     app/
       main.py        config.py  latency.py  audio.py
       scraping/      scrape.py  build_context.py  render.py           # R1
       rag/           chunk.py embed.py index.py rerank.py service.py viz_math.py  # R5
       llm/           providers/{openai,gemini}.py  orchestrator.py history.py prompts.py tokens.py  # R3,R4,R8
       tools/         registry.py handlers.py cart_store.py catalog_data.py         # R2,R9
       asr/ service.py     tts/ service.py                              # R7,R10
     data/  docs/*.md  context.md  faiss.index  chunks.json  catalog.json
```

**Turn pipeline** (each stage timed → latency trace): ASR → (RAG | RAGless) → LLM (stream|batch,
tool loop, RAG routing) → Tools → TTS (buffered) → playback. History (N verbatim + summary) and
interrupt handling are cross-cutting.

## Data Model / Schema
- **Doc corpus** (R1): `docs/*.md` per topic + `context.md` (RAGless payload).
- **Chunk** (R5): `chunks.json` `{id, text, metadata:{product_id, product_name, category, section, tier?}}` + FAISS vectors.
- **Cart** (R9): the site's `nimbus_cart` — items `{product_id, product_name, tier, seats, price}`.
- **Turn config**: `{asr_provider, llm_provider, tts_provider, retrieval_mode, mode(streaming|batch),
  system_prompt, response_length, history_n, tools_enabled, tool_allowlist[], endpoint_ms,
  barge_in(off|low|med|high), rag:{profile, top_k, rerank, rerank_k}}`.
- **Latency trace**: `{asr_ms, rag_ms, llm_ttft_ms, llm_total_ms, tool_ms, tts_ms, buffer_ms, total_ms}`.

## API / Interface Design
> **Target contract = `reference.md` §3** (session-based `/chat` + `/chat/stream` SSE,
> `/models`, `/inspect`, `/tools`, `/cart`, `/session/reset`, `/rag/*`). Endpoints below are our
> incremental subset; converge field names on the reference (`message`, `model_key`,
> `use_context`/`use_rag`, `verbatim_turns`, response `{text, latency, meta}`) as phases land.

**REST**: `GET /health` · `POST /scrape` · `POST /build-context` · `GET /catalog` ·
`POST /rag/build` · `POST /rag/retrieve {query,k,rerank}` · `GET /rag/viz` · `POST /rag/viz/query {query,k}` ·
`POST /chat {text, config}` (batch text turn + latency) · `POST /asr` · `POST /tts` ·
`GET /context/preview` (inspector) · `GET /config/providers` · profiles/config as needed.
**WebSocket** `/ws`: client → `audio_frame|interrupt|end_turn|config`; server →
`asr_partial|asr_final|llm_token|tool_call|tts_chunk|latency|error`.
**Keys**: `X-OpenAI-Key` / `X-Gemini-Key` / `X-ElevenLabs-Key` headers (or `.env`).

## Edge Cases and Error Handling
- Missing key → `/config/providers` marks provider unavailable; UI disables it.
- Embedding profile switch → rebuild index (guarded).
- Barge-in mid-tool-call → cancel TTS only; append `[cancelled by user]`.
- Endpoint fires on noise → skip empty turn, no LLM call.
- Disabled tool called → orchestrator refuses; LLM re-plans.
- RAG finds nothing relevant → RAG-routing prompt falls back to "not in Nimbus docs" / RAGless.
- Non-streaming provider in streaming mode → fall back to batch, report it.
- Small buffer + long TTS → surface `buffer_ms` vs underruns.

## What's Explicitly Not in v1
Public phone / Twilio; Anthropic provider; real payments; durable accounts; Next.js/monorepo/docker.

## Dependencies
fastapi, uvicorn, python-dotenv, httpx, numpy, faiss-cpu, tiktoken, python-multipart,
imageio-ffmpeg; optional `sentence-transformers` for `rich`. Provider SDKs/HTTP: OpenAI, Gemini,
ElevenLabs. Frontend: vanilla JS + a small chart lib for latency/viz. Deploy: Vercel, Railway.

## Open Questions (resolved / tracked)
- Model ids (OQ1), GitHub scrape (OQ2), ElevenLabs voice (OQ3), fork vs local (OQ4), cart store
  (OQ5) — tracked in requirements; sensible defaults chosen, confirm as each phase is reached.
