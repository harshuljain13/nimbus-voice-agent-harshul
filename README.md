# Harshul · Nimbus Voice Agent

A configurable, end-to-end agent built on top of the fictional **Nimbus** SaaS catalog, for the
Vizuara Voice Agents bootcamp. Every stage of the pipeline (RAG, LLM, tools; ASR/TTS next) is
swappable from the frontend, and every stage reports its latency.

Built **phase by phase** — each phase is independently testable in the playground before the next.
Repo: **github.com/harshuljain13/nimbus-voice-agent-harshul** ·
Target/reference: [`VizuaraAI/nimbus-voice-agent`](https://github.com/VizuaraAI/nimbus-voice-agent)
(see [`.spec-dev/reference.md`](.spec-dev/reference.md)).

## 🚀 Live

- **Site + agent widget:** https://nimbus-harshul.vercel.app
- **Playground:** https://nimbus-harshul.vercel.app/playground/playground.html
- **RAG vector viz:** https://nimbus-harshul.vercel.app/playground/rag.html
- **Backend API:** https://nimbus-voice-agent-harshul.onrender.com (Render free tier — the first
  request after idle wakes it, ~50s)

Public deploy uses `REQUIRE_USER_KEYS=true`, so enter your own OpenAI key in the playground's
**API keys** dialog / the widget's key prompt (stored only in your browser; the server never uses
its own key).

> Nimbus is a made-up company; all names, prices, and policies are invented for teaching.

## Status (7 of 13 phases done · 48 tests passing)

| Phase | | |
|---|---|---|
| 0 · Foundation | ✅ | backend, key management (env + per-request headers), latency trace |
| 1 · Web scraping | ✅ | `catalog.json` → 31 docs + `context.md` |
| 2 · RAGless chat | ✅ | grounded chat; OpenAI lite/heavy, response length, temperature, system prompt; context inspector |
| 3 · RAG retrieval | ✅ | chunk · embed (OpenAI) · FAISS · top-k (98% smaller prompt) |
| 4 · RAG vs RAGless + viz | ✅ | compare, reranking, 2D vector-cluster map (`rag.html`), source citations |
| 5 · LLM controls | ✅ | Gemini provider, conversation memory (verbatim-N + rolling summary), RAG-routing |
| 6 · Streaming vs batch | ✅ | SSE streaming, TTFT, batch-vs-stream comparison |
| 7 · Tools | ✅ | 11 cart/pricing tools + on/off selection; function-call loop; live cart |
| 12 · Landing widget | ◧ | "Talk to Nimbus" widget on the site + two-way cart bridge (deploy remaining) |
| 8–11 | ◻ planned | ASR · TTS · voice loop (barge-in/endpointing) · latency dashboard |

Full plan: [`.spec-dev/`](.spec-dev/) and [`PLAN.md`](PLAN.md).

## What it does (today)

- **Scrape** the catalog → clean docs + one `context.md`.
- **RAGless vs RAG** — inject the whole catalog, or retrieve top-k FAISS chunks; **compare** token
  cost + latency; **rerank**; **2D vector visualization** with a query overlay; **source citations**.
- **LLM layer** — OpenAI (lite/heavy) + Gemini; editable system prompt; response length;
  **conversation memory** (last-N verbatim + rolling summary); **streaming or batch** (with TTFT).
- **Tools** — 11 cart/pricing functions (add/remove/checkout/clear, cart total, annual pricing,
  annual-vs-monthly savings, sort, top-k, product lookup) with an **on/off panel**; a **live cart**.
- **Context inspector** — the exact prompt + token counts. **Latency** on every stage.
- **"Talk to Nimbus" widget** on the actual site, bridged to the site cart (watch add/remove live).

## Architecture

```
backend/                 FastAPI (one process; REST + SSE; per-stage latency)
  app/
    scraping/            catalog.json -> docs/*.md + context.md
    rag/                 chunk · embed · FAISS index · rerank · 2D viz
    llm/                 providers (openai, gemini) · orchestrator · history · prompts · tokens
    tools/               11 cart/pricing tools + registry + session cart
    config.py latency.py main.py
  data/                  bundled catalog.json + generated docs + context.md
playground/              control panel (config · chat · latency) + rag.html vector viz
frontend/                the Nimbus catalog site + assets/widget.js (the embedded agent)
.spec-dev/               the living plan (requirements · spec · tasks · phases · reference)
vercel.json              one Vercel app serves site (/) + playground + rag viz
```

## Run locally

```bash
make install                 # one-time: backend venv + deps
cp .env.example .env          # add OPENAI_API_KEY=sk-...
make scrape                   # build docs/*.md + context.md
make dev                      # backend :8100 + no-cache static server :8092
```

- Playground: http://localhost:8092/playground/playground.html
- Nimbus site (+ widget): http://localhost:8092/frontend/index.html

Keys come from `.env`, or the playground **API keys** dialog / widget prompt (sent per-request as
`X-OpenAI-Key`; `.env` is git-ignored, never committed).

## Test

```bash
make test    # pytest — 48 tests across Phases 0–7
```

## Deploy

**One Vercel app for all frontends** (`vercel.json` — like the reference):
`/` → site · `/playground/playground.html` · `/playground/rag.html`.

- **Frontend → Vercel (static):** import the repo at vercel.com/new (Framework preset **Other**,
  no build). Then point it at the backend by editing `playground/runtime-config.js`
  (`defaultBackendUrl`) and the widget default.
- **Backend → Railway** (`Procfile` + `railway.json`, Nixpacks) *or any FastAPI host* (Render's
  free web-service tier works too). Set `EMBEDDING_PROFILE=light`.

**Public deploy — don't expose your own key.** Set **`REQUIRE_USER_KEYS=true`** on the backend →
the server ignores its own `.env` keys, so every visitor must bring their own (playground dialog /
widget prompt), sent per-request. Off locally. (Improves on the reference, which always falls back
to the server key.)
