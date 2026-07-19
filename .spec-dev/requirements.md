# Requirements: Nimbus Voice Agent

> **North star: [`reference.md`](reference.md)** — the instructor's completed build
> (github.com/VizuaraAI/nimbus-voice-agent). The playground design, module layout, and API
> contract come from there. Our requirements/phases are re-targeted at that reference.

## Problem Statement
The Nimbus starter site is a static SaaS catalog (products, pricing, policies, FAQs) with no
way to *talk* to it. We need a configurable, end-to-end **voice agent** built on top of the
starter site, plus a **playground** that exposes every pipeline knob (ASR/RAG/LLM/tools/TTS,
RAG vs RAGless, streaming vs batch, endpoint timing, latency breakdown) and reports latency at
every stage. Audience: the builder (Harshul) learning/benchmarking voice-agent design for the
Vizuara bootcamp, plus end users on the Nimbus landing page using a finalized chat widget.

## Ordered Requirements
Requirements are numbered in the order of the instruction file
(`nimbus-voice-agent-instruction.txt`). **The implementation plan builds them in this exact
order — Requirement N is delivered by Phase N.**

- **R1 — Web scraping**: Scrape/normalize the Nimbus catalog (`data/catalog.json`, optional
  GitHub) into clean per-topic docs (FAQ, Products, Families/categories, Pricing, Refund,
  T&C, Monthly-vs-Annual) as `docs/*.md`, plus one combined `context.md`.
- **R2 — Tools on/off + manual selection**: A master tools on/off switch and manual per-tool
  selection (all / none / any subset); disabled tools are never advertised to the LLM.
- **R3 — RAG vs RAGless toggle**: Runtime switch between RAG and RAGless, with the retrieval
  latency of each measured and displayed. RAGless injects `context.md` directly.
- **R4 — Streaming vs batch**: Selectable streaming or batch mode with a total-latency
  comparison (time-to-first-token vs total).
- **R5 — RAG**: FAISS vector index; top-k retrieval (k set from frontend); reranking; chosen
  embedding model; 2-D vector-cluster visualization; query visualization (query point +
  nearest-k chunks) with top-k sliders; retrieval latency in ms. Hostable locally (Railway later).
- **R6 — RAGless**: One clean `context.md` passed directly into the LLM; latency in ms;
  comparable side-by-side with RAG.
- **R7 — ASR**: Providers browser (Web Speech) / OpenAI / Gemini / ElevenLabs; transcript
  shown as text in the chatbox; per-provider latency in ms.
- **R8 — LLM reasoning layer**: Providers OpenAI (lite `gpt-4o-mini` + heavy `gpt-4o`) /
  Gemini (flash + pro); editable system prompt; response length (low/med/high); conversation
  history (last-N verbatim + rolling summary of older turns); access to allowed tools; RAG
  routing rules in the system prompt; interrupt handling (`[cancelled by user]`); a **context
  inspector** (exact prompt + token count); latency in ms. **Anthropic out of scope (no key).**
- **R9 — Tools**: The 11-tool cart/pricing/product suite (see Success Criteria), each timed,
  with cart state bridged to the site's existing `nimbus_cart`.
- **R10 — TTS**: Providers OpenAI / Gemini / ElevenLabs; playback buffering with the buffer
  latency (`buffer_ms`) surfaced (and why no buffer risks choppy audio); latency in ms.
- **R11 — Interrupt-driven conversations**: Barge-in — user speech during TTS stops playback
  immediately (echo-aware, Off/Low/Medium/High sensitivity), tied to `[cancelled by user]`.
- **R12 — Endpoint detection**: Manual silence-duration slider (e.g. 500 / 700 ms) controlling
  turn finalization.
- **R13 — Latency dashboard**: Combine every stage into one view; each stage's % contribution
  as a pie/bar chart; total ms; highlight the biggest contributor.
- **R14 — Playground + landing widget**: A full-setup playground (all options, keys, sliders,
  viz, dashboard) and a finalized voice-agent chat widget embedded on the landing page,
  sharing config and bridged to the site cart. Deployed (Vercel frontend + Railway backend).

### Cross-cutting requirements (present from the start, not a phase)
- **CC1 — Frontend-settable keys**: Provider keys enterable in the browser and sent per-request
  (`X-OpenAI-Key` / `X-Gemini-Key` / `X-ElevenLabs-Key`), stored in `localStorage`, precedence
  over `.env`. Single-user local dev tool — do not ship key entry on a public deploy ungated.
- **CC2 — Latency everywhere**: Every stage emits `latency_ms` from the phase it first appears.
- **CC3 — Build the backend fresh**: implement ASR/LLM/TTS/history/latency directly against
  provider SDKs/APIs (the course Colab notebooks are not reused).
- **CC4 — Playground quality**: The playground should be genuinely polished (clean UI, smooth
  real-time signal/latency rendering, clear agent state), **matching the reference's standalone
  dark control-panel design** (see `reference.md` §1 — dark 3-column control panel; *not* the
  light marketing-site look). The playground grows **incrementally** — only live controls are
  shown; new controls are added as each phase lands (no cluttered disabled "Phase N" stubs).

## Non-Goals (explicitly out of scope)
- **R15 / Public phone number / Twilio telephony** — web + browser voice only (no Twilio key).
- **Anthropic LLM provider** — no key; not built.
- Real payment processing — checkout is a simulated tool action.
- Real user accounts / persistent identity beyond a session.
- Multi-tenant / production auth, rate limiting, or agent billing.
- Model training/fine-tuning; mobile-native apps.
- Rebuilding catalog content — consume `data/catalog.json`.

## Success Criteria
- **R1**: `docs/*.md` + `context.md` generated, covering every product + policy topic.
- **R2**: tool selection (all/none/subset) changes which tools the LLM can call.
- **R3**: RAG and RAGless both selectable and answer correctly; retrieval latencies shown.
- **R4**: streaming and batch both run; TTFT-vs-total latency compared side by side.
- **R5**: catalog/policy query returns correct chunks; top-k slider + rerank work; vector
  cluster + query-overlay viz render; `rag_ms` shown.
- **R6**: RAGless answers from `context.md`; latency shown alongside RAG.
- **R7**: each ASR provider transcribes; transcript appears in the chatbox; `asr_ms` shown.
- **R8**: each LLM provider answers; system prompt / length / history-N controls work; RAG
  routing behaves; interrupt appends `[cancelled by user]`; context inspector shows prompt + tokens.
- **R9**: all 11 tools work when invoked — **add to cart, cart total, checkout (whole cart),
  annual pricing, annual-vs-monthly savings %, sort products by price (asc/desc), top-k most
  expensive, remove item, checkout single item, clear cart, product/tier lookup** — and cart
  stays in sync with the site's `nimbus_cart`.
- **R10**: each TTS provider speaks; buffering works; `buffer_ms` + `tts_ms` shown.
- **R11**: speaking over TTS stops playback promptly (per sensitivity mode).
- **R12**: endpoint slider changes turn boundaries.
- **R13**: combined latency dashboard shows per-stage %, total ms, biggest contributor.
- **R14**: full playground live; landing-page widget answers + drives the cart; deployed on Vercel+Railway.

## Constraints
- **Build inside the starter repo** `nimbus-voice-agent-starter/` (README's "typical path"):
  a `backend/` FastAPI app + static `playground/` pages added to the site. **One backend
  process**, not a microservice fleet. No Next.js, no docker-compose.
- **Content source**: `data/catalog.json` is the source of truth (optional GitHub supplements).
- **Stack**: Python + FastAPI backend (WebSocket for the streaming voice loop, REST otherwise);
  static HTML/CSS/JS frontend reusing the site's `styles.css`; FAISS local file index.
- **Providers/keys**: OpenAI, Gemini, ElevenLabs (+ Railway, Vercel for deploy). Anthropic/Twilio absent.
- **Embedding/rerank profiles** (`EMBEDDING_PROFILE`): `light` = OpenAI `text-embedding-3-small`
  + LLM rerank (no torch, Railway-friendly, default); `rich` = local MiniLM + cross-encoder
  (best for viz). One interface, one env var.
- **Deploy**: frontend → Vercel (`nimbus-harshul.vercel.app`, live); backend → Railway (later).
- **Latency is first-class**: every turn returns `{asr_ms, rag_ms, llm_ttft_ms, llm_total_ms,
  tool_ms, tts_ms, buffer_ms, total_ms}`.

## Open Questions
- **OQ1**: Exact OpenAI/Gemini model ids for "lite" vs "heavy" (default `gpt-4o-mini`/`gpt-4o`,
  `gemini-2.5-flash`/`pro`) — confirm availability on the keys.
- **OQ2** ✅ RESOLVED (2026-07-18): No separate GitHub scraper. `catalog.json` lives in the
  starter's GitHub repo and is its *complete* data (company, policies, 8 categories, 24 products
  with tiers + FAQs); the site HTML is JS-rendered shells and `README.md` is bootcamp-meta
  ("Nimbus is fictional") that must NOT enter agent grounding. So catalog.json satisfies R1's
  "[website/github]"; Phase 1 stands as-is.
- **OQ3**: ElevenLabs default voice id + default TTS provider (instructor default: ElevenLabs).
- **OQ4**: Fork `VizuaraAI/nimbus-voice-agent-starter` for write access, or work locally only?
- **OQ5**: Session/cart store — in-memory dict (course-scale) vs Redis? (Default: in-memory + `nimbus_cart` bridge.)
