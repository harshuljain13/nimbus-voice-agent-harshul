# Reference Implementation — the North Star

> **This is the target.** The instructor (Sreedath, Vizuara) shipped a complete Nimbus voice
> agent. Our build must match its **playground design, module architecture, API contract, and
> behavior**. When in doubt, open the reference and copy its shape. Every phase doc, the spec,
> and the tasks list are re-targeted at this reference.

- **Repo:** https://github.com/VizuaraAI/nimbus-voice-agent  (the *completed* build; note our
  own working copy is the `-starter`, which is only the catalog site).
- **Live:** https://nimbus-sreedath.vercel.app · playground `/playground/playground.html` ·
  voice `/playground/voice.html` · RAG viz `/playground/rag.html`
- **Local clone (re-clone as needed, do not commit):**
  `git clone --depth 1 https://github.com/VizuaraAI/nimbus-voice-agent /tmp/nimbus-ref-1`
- Its own build plan lives in the repo's `PLAN.md` (6 phases 0–5).

## 1. Playground design system (ADOPT THIS — supersedes the old "light per-phase cards")

The reference playground is a **standalone dark control panel**, deliberately *not* the light
marketing-site look. Our playground should match it.

**Design tokens** (`playground.css` `:root`):
```
--bg:#0d1117  --panel:#161b22  --panel-2:#1c232d  --line:#2a3340
--ink:#e6edf3  --muted:#8b949e  --brand:#6e8bff  --brand-2:#9d7bff
--ok:#2ea043  --warn:#d29922  --bad:#f85149  --radius:12px
font: 15px/1.5 system-ui
```

**Layout:** `header.pg-top` (brand + health pill + Voice link + API-keys button) then
`main.pg-grid` = `grid-template-columns: 300px 1fr 300px` (collapses to 1 col < 1100px):
- **Left `aside.panel.controls`** — every config knob (see §3).
- **Center `section.panel.chat`** — `.messages` (`.msg-user`/`.msg-assistant`/`.msg-system`/
  `.msg-error`) + `.composer` (input + Send).
- **Right `aside.panel.latency`** — big total ms, per-stage `.lat-bars`, streaming-vs-batch
  `.cmp` table, `.cart-view`, `.tool-trace`, `.meta`.

**Component vocabulary** (reuse these class names):
- Segmented control `.seg > button(.active)` — for mode, length, knowledge source.
- Toggle `.switch > input + .slider` — for tools-enabled, rerank.
- `input[type=range]` sliders (top-k, verbatim history, temperature) with a live `<b>` value.
- `.btn` / `.btn-primary` / `.btn-ghost` / `.btn.mini` / `.btn-block`.
- `.pill` / `.pill-ok` / `.pill-bad` / `.pill-muted` for the health status.
- `<dialog class="settings">` for **API keys** and the **context inspector** (`.ctx-*`).

## 2. Module architecture (backend/app — we already mirror this)

```
scraping/  scrape.py build_context.py render.py
rag/       chunk.py embed.py index.py rerank.py service.py viz_math.py
llm/       providers/{base,openai,gemini}.py  orchestrator.py history.py prompts.py
           tokens.py registry.py
tools/     registry.py handlers.py cart_store.py catalog_data.py
asr/ service.py     tts/ service.py     audio.py  latency.py  config.py  main.py
```
Notably present that we haven't built yet: `llm/history.py`, `llm/registry.py`,
`llm/providers/base.py`, the whole `rag/` and `tools/` packages, `audio.py`.

## 3. API contract (ADOPT — our endpoints should converge on these)

**Session-based from early on.** Every chat call carries a `session_id`; the server holds that
session's **cart and conversation history**. Request payload (`/chat`, `/chat/stream`, `/inspect`):
```
{ session_id, message, mode: "batch"|"stream", model_key,
  response_length: "low"|"medium"|"high",
  use_context: bool,        # RAGless: inject context.md
  use_rag: bool,            # RAG: inject top-k chunks
  top_k, rerank,
  verbatim_turns,           # last-N verbatim; older turns summarized
  temperature,
  system_prompt|null,
  tools_enabled, enabled_tools[] }
```
Endpoints:
- `GET /health` → `{ corpus:{doc_count}, ... }`
- `GET /models` → `{ models:[{key,label,available}] }`  (drives the model `<select>`)
- `POST /chat` → `{ text, latency, meta }` (batch)
- `POST /chat/stream` → **SSE** events `{type:"delta",text}` … `{type:"done",latency,meta}` / `{type:"error",error}`
- `POST /inspect` → `{ total_tokens, total_chars, messages:[{role,content,tokens,chars}] }`
- `GET /tools` → `{ tools:[{name,description}] }`
- `GET /cart?session_id=` → `{ items:[{product_name,tier,seats,price_monthly}], monthly_total }`
- `POST /session/reset` `{session_id}`
- `GET /rag/status` → `{built, chunks, model, dim, profile}` · `POST /rag/build` · plus the `rag.html` viz endpoints.

`meta` (returned per turn) carries: `model, mode, prompt_tokens, system_chars,
verbatim_messages, summarized_messages, summary_used, tool_calls[], rag:{k,reranked,chunks[]}`.

**Model keys:** `openai-lite` (gpt-4o-mini), `openai-heavy` (gpt-4o), `gemini-flash`,
`gemini-pro`. **Defaults:** RAG on, tools on, batch mode, ElevenLabs ASR+TTS, Low barge-in.

**Shared config for the widget:** the playground writes `nimbus_agent_config` to `localStorage`;
the landing `widget.js` reads it. Cart bridges to the site's `nimbus_cart`.

## 4. Reference PLAN.md phases → our phases

| Reference (PLAN.md) | Our phases (.spec-dev) |
|---|---|
| 0 Scaffold + scraping | 0 Foundation, 1 Web scraping |
| 1 RAGless + LLM core + text chat (stream/batch, sys prompt, length, history) | 2 RAGless chat, 5 LLM controls, 6 Streaming/batch |
| 2 Tools | 7 Tools |
| 3 RAG (FAISS, rerank, viz) | 3 RAG retrieval, 4 RAG-vs-RAGless + viz |
| 4 Voice (ASR, TTS, loop, interrupt, endpoint, latency dashboard) | 8 ASR, 9 TTS, 10 Voice loop, 11 Latency dashboard |
| 5 Landing chatbox + deploy | 12 Widget + deploy |

We keep the finer phasing (better for incremental review), and each phase builds toward the
reference's design + contract. **Difference in delivery**: the reference ships the whole control
panel at once; we grow the playground **incrementally** — only the controls that are live today
are shown, and we add one as each phase lands. We do NOT pre-render future controls as disabled
"Phase N" stubs (that was tried and made the UI cluttered/unclear). Match the reference's *look*;
scope what's shown to our built phases.

## 5. How to use this doc

- Before building a phase, open the matching reference files and mirror their shape/behavior.
- Playground work: match §1 exactly (dark 3-col control panel, these class names).
- Backend work: converge endpoints/payloads on §3; keep the canonical 8-key latency trace.
- Divergences we keep: finer phasing; **playground grown incrementally (only live controls
  shown, added per phase — no disabled stubs)**; our own clean code (we implement, not copy
  verbatim — the reference is the spec, not the source to paste).
