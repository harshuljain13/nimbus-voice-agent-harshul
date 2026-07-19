# Phase 0 — Foundation (Report / Design Doc)

> Status: ✅ Done · Requirements: scaffolding for all · Tests: 5 passing

## 1. Concept — what this phase teaches

A voice agent is a **pipeline of stages**: microphone → speech-to-text (ASR) → retrieval →
LLM → tools → text-to-speech (TTS) → speaker. Before building any stage, you need three
foundations that *every* stage will lean on:

1. **A backend** — the stages (RAG, LLM calls, TTS) need Python and secret API keys, so they
   can't live in the browser. We use **FastAPI** (a Python web framework) as the one process
   that runs the pipeline and answers HTTP requests from the web page.
2. **A way to manage API keys** — every provider (OpenAI, Gemini, ElevenLabs) needs a key.
   We let you type them into the web page; they're sent with each request. Keys never get
   hard-coded.
3. **Latency measurement** — the whole point of this project is comparing options by *speed*.
   So from day one, every response carries a **latency trace**: a fixed set of numbers
   (`asr_ms`, `llm_total_ms`, …) that later becomes the latency dashboard.

Teaching point: **instrument first.** If you bolt on timing later, you retrofit every stage.
We baked the trace shape in before writing a single pipeline stage.

## 2. What we built

```
backend/
  app/
    main.py       FastAPI app. Endpoints: GET /health, GET /config/providers. CORS enabled.
    config.py     Which providers have keys (from .env OR X-*-Key headers). LLM model list. EMBEDDING_PROFILE.
    latency.py    The 8-number latency trace + a Timer + timed() context manager + stage_shares().
    adapters.py   The uniform "Adapter" shape all ASR/LLM/TTS providers will implement (run/stream).
    asr/ llm/ tts/  empty adapter stubs — filled in later phases.
  tests/test_phase0.py   5 tests
playground/
  playground.html/.css/.js   the web page: enter keys, check backend, see provider status
  runtime-config.js          where the backend URL lives
Makefile + scripts/dev.sh    one command to run everything
```

## 3. Design decisions

| Decision | Choice | Why |
|---|---|---|
| Backend framework | FastAPI | Async, tiny, auto-JSON; standard for Python AI services |
| Keys | env **or** per-request `X-*-Key` header (header wins) | You can tune keys live from the browser without restarting; still works from `.env` on a server |
| Latency shape | one fixed dict of 8 keys, everywhere | The dashboard can render any turn the same way; no per-stage special-casing |
| Provider adapters | one `Adapter` interface (`run` + `stream`) | Swapping OpenAI↔Gemini↔ElevenLabs later is just picking a different object |
| Frontend | plain HTML/CSS/JS on the existing site | No build step; reuses the Nimbus design; deployable as static files |

## 4. How it works

The web page (`playground.js`) reads your keys from the browser's `localStorage`, then calls
`GET /health` with headers like `X-OpenAI-Key: sk-...`. The backend's `config.py` checks, for
each provider, "do I have a key — from this header, or failing that from `.env`?" and returns
a `{openai: true, gemini: false, ...}` map. The page paints a green/red chip per provider.

`latency.py` is the reusable stopwatch. Example of the pattern every future stage uses:
```python
trace = empty_trace()
with timed(trace, "llm_total_ms"):
    answer = call_the_llm(...)
# trace["llm_total_ms"] now holds the milliseconds
```

## 5. How to test it

**One-time setup:** `cd voice-agents && make install`
**Run it:** `make dev` → open http://localhost:8092/playground/playground.html
**Automated:** `make test` → expect part of the `10 passed`.

Manual checklist:
- Click **Check backend** → status pill turns green **online**; `openai` chip green.
- **API keys** dialog → paste anything into Gemini → Save → Check backend → `gemini` chip flips green.
- Bad backend URL → pill turns **offline** with guidance (no crash).

## 6. Key takeaways

- A voice agent is a **pipeline**; the backend is where the secret-key stages live.
- **Per-request keys** let you experiment without redeploying.
- **Instrument latency before building features** — it's the backbone of every comparison later.
- A **uniform adapter interface** is what makes "swap the provider" a one-line change.

## 7. What's next

**Phase 1 — Web scraping:** give the agent something to know (the Nimbus catalog as clean docs).
