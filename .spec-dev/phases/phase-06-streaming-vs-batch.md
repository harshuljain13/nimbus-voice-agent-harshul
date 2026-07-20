# Phase 6 — Streaming vs Batch (Report / Design Doc)

> Status: ✅ Done · Requirement: R4 · Tests: 2 passing · Playground: Mode = Batch / Streaming
> Design target: [`../reference.md`](../reference.md).

## 1. Concept — what this phase teaches

Batch waits for the *entire* answer, then shows it. **Streaming** shows tokens **as they generate**.
The user-visible metric that changes is **time-to-first-token (TTFT)** — how long until *something*
appears. A smaller prompt (RAG) reaches the first token sooner, so this is where RAG's latency
advantage finally shows up (Phase 3's point: RAG's win is cost *and*, in streaming, perceived speed).

Teaching point: **total time ≈ same, but perceived latency is very different.** Streaming feels
instant because TTFT is a fraction of the total; batch feels slow because you wait for all of it.

## 2. What we built

```
providers/openai.py   + stream() — SSE deltas over httpx (stream: true)
providers/gemini.py   + stream() — streamGenerateContent?alt=sse
llm/orchestrator.py    + chat_stream(): shared _prepare() then yield delta/done/error events;
                         records llm_ttft_ms on the first token
main.py                + POST /chat/stream (text/event-stream)
```
Playground: a **Mode** toggle (Batch / Streaming) + a **⚖ Compare batch vs stream** button that
runs the same question both ways and shows **TTFT / LLM ms / Total ms** side by side (R4). Streaming
renders tokens live; the "This turn" panel shows a consistent metric set across modes (TTFT is
`— (batch)` in batch), and **streaming reports token counts too** (counted locally with tiktoken,
since streaming APIs omit usage) so the panel doesn't change shape when you switch modes.
`chat()` (batch) and `chat_stream()` share `_prepare()` (grounding + history).

## 3. Design decisions

| Decision | Choice | Why |
|---|---|---|
| Transport | Server-Sent Events (`data: {json}\n\n`) | Simple, one-way, native `EventSource`/`fetch` reader; no WebSocket needed for text. |
| Event shape | `{type: delta\|done\|error}`; `done` carries latency + meta | The client renders deltas, then gets the full trace once — same `meta` as batch. |
| TTFT | timestamp the first delta → `llm_ttft_ms` | The metric that makes streaming's win measurable; the streaming-vs-batch comparison is TTFT vs total. |
| Tools + streaming | **tools run in batch only**; streaming is text-only | Mid-stream tool calls complicate the token stream; the reference does the same. Pick batch for cart actions. |
| Shared prep | `_prepare()` used by both paths | One place for grounding + history; streaming can't drift from batch. |

## 4. How it works

`POST /chat/stream` runs `chat_stream()`, which `_prepare()`s (grounding + history) then iterates
the provider's `stream()`, yielding `{"type":"delta","text":…}` per token. On the first token it
records `llm_ttft_ms`. When the stream ends it appends the turn to history and yields
`{"type":"done", text, latency, meta}`. The browser reads the response body reader, splits on
`\n\n`, and appends deltas to the message bubble in real time.

## 5. How to test it

1. **Mode → Streaming**, ask anything → the answer **types out live** instead of appearing at once.
2. The "This turn" panel shows **TTFT** (time to first token) alongside total ms.
3. Compare **Batch vs Streaming** on the same question — total is similar, but streaming *feels*
   faster because TTFT ≪ total. In **RAG** mode, TTFT is lower (smaller prompt).

**Automated:** `make test` (Phase 6 = 2 tests; provider stream mocked — asserts delta events, a
done event with `llm_ttft_ms`, and an error event on bad input).
**Live-verified:** `/chat/stream` yields tokens (`Nimbus`, ` CRM`, ` is`, …).

## 6. Key takeaways

- **Streaming changes *perceived* latency, not total** — TTFT is the number that matters.
- **SSE is enough for text**; keep WebSocket for the full voice loop (Phase 10).
- **Batch and streaming must share setup** — one `_prepare()` keeps them consistent.

## 7. What's next

**Phase 7 — Tools** (built alongside this): the 11 cart/pricing tools with a function-call loop,
an on/off panel, and a live cart.
