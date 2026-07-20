# Harshul · Nimbus Voice Agent

A configurable, end-to-end **voice agent** built on top of the fictional Nimbus SaaS catalog,
for the Vizuara Voice Agents bootcamp. Every stage of the pipeline (ASR, RAG, LLM, tools, TTS)
is swappable from the frontend, and every stage reports its latency.

Built **phase by phase** — each phase is independently testable in the playground before the
next one starts. Target/reference: [`VizuaraAI/nimbus-voice-agent`](https://github.com/VizuaraAI/nimbus-voice-agent)
(see [`.spec-dev/reference.md`](.spec-dev/reference.md)).

> Nimbus is a made-up company; all names, prices, and policies are invented for teaching.

## Status

| Phase | | |
|---|---|---|
| 0 · Foundation | ✅ | backend scaffold, key management, latency trace |
| 1 · Web scraping | ✅ | `catalog.json` → 31 docs + `context.md` |
| 2 · RAGless chat | ✅ | grounded chat, reference-style playground, context inspector |
| 3 · RAG retrieval | ▶ next | FAISS, top-k |
| 4–12 | ◻ planned | RAG viz · LLM controls · streaming · tools · ASR · TTS · voice loop · dashboard · widget+deploy |

Full plan: [`.spec-dev/`](.spec-dev/) (requirements → spec → tasks → per-phase design docs).

## What it does (today)

- **Web scraping**: `catalog.json` → clean per-topic markdown docs + one `context.md`.
- **RAGless chat**: the whole `context.md` is grounded into the prompt; OpenAI (lite/heavy),
  response length (low/med/high), temperature, editable system prompt.
- **Context inspector**: see the exact prompt sent to the LLM + token counts.
- **Latency**: every turn returns a per-stage trace; the playground shows it.

## Architecture

```
backend/                 FastAPI — REST, per-stage latency. One process.
  app/
    scraping/            catalog.json -> docs/*.md + context.md
    llm/                 providers (openai) · orchestrator · prompts · tokens
    asr/ tts/ rag/       adapters (filled in as phases land)
    latency.py config.py main.py
  data/                  generated docs + context.md
playground/              the control panel (config · chat · latency)
frontend/                the Nimbus catalog site
.spec-dev/               the living plan (requirements, spec, tasks, phases, reference)
```

## Run locally

```bash
make install     # one-time: create backend venv + install deps
cp .env.example .env   # then add your OpenAI key (OPENAI_API_KEY=sk-...)
make scrape      # build docs/*.md + context.md from the catalog
make dev         # backend :8100 + no-cache static server :8092
```

- Playground: http://localhost:8092/playground/playground.html
- Nimbus site: http://localhost:8092/frontend/index.html

Keys are read from `.env`, or entered in the playground's **API keys** dialog and sent
per-request as `X-OpenAI-Key` headers. Nothing is ever committed (`.env` is git-ignored).

## Test

```bash
make test        # pytest (Phases 0–2: 23 tests)
```

## Deploy (later — Phase 12)

Backend → Railway; frontend + playground → Vercel. `EMBEDDING_PROFILE=light` on Railway.

**Public deploy — don't expose your own key.** Set **`REQUIRE_USER_KEYS=true`** on the backend
(Railway). Then the server *ignores* its own `.env` keys and every visitor must enter their own
key (playground **API keys** dialog / widget key prompt), sent per-request as `X-OpenAI-Key`. Leave
it unset locally to use your `.env` for convenience. (Improves on the reference, which always falls
back to the server key.)
