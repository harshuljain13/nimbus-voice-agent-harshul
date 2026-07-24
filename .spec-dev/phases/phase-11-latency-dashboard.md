# Phase 11 — Latency dashboard (Report / Design Doc)

> Status: ◻ awaiting manual test · Requirement: R13 · Tests: reuses Phase 10 backend suite · Playground: voice page pie + new `#latBiggest` callout
> Design target: [`../reference.md`](../reference.md).

## 1. Concept — what this phase teaches

Every voice turn is a chain of stages — **ASR → RAG → LLM → tools → TTS → buffer** — and
each one costs milliseconds. R13 asks for *one combined view* that answers three questions:

- **How long did the turn take?** — total ms to first audio.
- **Where did the time go?** — each stage's ms and its **% contribution**.
- **What should I optimize first?** — the single **biggest contributor**.

The teaching point: latency is not one number, it's a *budget*. You optimize the biggest
line item, not a random one. The dashboard makes that line item obvious.

## 2. What we built (and what already existed)

Most of R13 was already delivered by the voice page's per-turn **latency pie** — this phase
closes the one gap in the success criteria.

```
playground/voice.js   renderPie(lat)  — donut of per-stage ms + %, total in the hole (existing)
                      finishTurn()    — computes the TTFA breakdown, batch vs streaming (existing)
                      renderPie()     — NEW: computes the biggest slice and fills #latBiggest
playground/voice.html #latBiggest     — NEW callout row between the total and the legend
playground/voice.css  .lat-biggest    — NEW style (matches the legend look)
```

The **batch-vs-streaming TTFA table** (`#ttfaBatch` / `#ttfaStream`) already lets you compare
the two pipeline modes turn over turn — so "combine every stage into one view" and
"compare pipelines" were both already in place.

## 3. Design decisions

| Decision | Choice | Why |
|---|---|---|
| Scope | Keep the existing per-turn pie; add only the biggest-contributor callout | The reference satisfies R13 with the per-turn pie — no separate persistent dashboard. We match it and fill the one gap the written criteria names. |
| Where "biggest" is computed | Client-side, from the slices already drawn | The pie already has every stage's ms; the biggest is a one-pass `reduce` over the same data — no new backend, no second source of truth. |
| No persistent cross-turn aggregate | Deferred | Would go beyond the reference. The batch-vs-streaming rows already give the cross-turn comparison that matters for the assignment. |
| Backend `stage_shares()` | Left as-is (unused by this UI) | Already present in `latency.py` for anyone who wants per-stage % server-side; the frontend computes its own from the displayed slices. |

## 4. How it works

```
finishTurn(lat, mode)
  → renderPie(lat)
      entries = [asr, rag, llm, tool, tts, buffer] with ms
      total   = Σ ms                     → #latTotal
      draw donut slices                  → #pie
      biggest = entries.reduce(max by ms) → #latBiggest  "Biggest stage: <label> — <ms>ms (<pct>%)"
      legend  = per-stage ms + %          → #pieLegend
```

The callout hides itself when the total is 0 (no turn yet), and colour-matches the slice.

## 5. How to test it

```
make api            # backend :8100
make web            # static server :8092 → http://localhost:8092/playground/voice.html
```

1. Click the mic orb and ask a question (e.g. *"What's the refund policy?"*).
2. When it speaks back, look at the **Time-to-first-audio** panel:
   - donut + total ms in the centre,
   - a **"Biggest stage: … — …ms (…%)"** row above the legend,
   - per-stage ms + % in the legend.
3. Switch **Batch ↔ Streaming** and do another turn — the biggest stage typically shifts
   (batch is usually **TTS**-dominated; streaming often shifts weight toward **LLM**/first token).
4. Sanity check: the biggest-stage ms should equal the largest legend row.

## 6. Key takeaways

- **Latency is a budget, not a number** — the dashboard shows per-stage % so you optimize the
  line item that actually dominates.
- **Reuse over rebuild** — R13 was ~90% covered by the existing pie; the phase is a small,
  honest gap-fill, not a new subsystem.

## 7. What's next

**Phase 12 — Playground finalize + landing widget + deploy (R14):** finalize the full-setup
playground, embed the finished voice widget on the Nimbus landing page (sharing config +
bridged to the site cart), and deploy (Vercel frontend + Railway/Render backend).
