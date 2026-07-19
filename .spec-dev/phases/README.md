# Nimbus Voice Agent — Design Docs Index

Detailed design doc (report) for every phase. Each follows the same structure:
**Concept → What we built → Design decisions → How it works → How to test → Key takeaways → What's next.**

| Phase | Design doc | Requirement | Status |
|-------|-----------|-------------|--------|
| 0 | [phase-00-foundation.md](phase-00-foundation.md) | scaffold | ✅ Done |
| 1 | [phase-01-web-scraping.md](phase-01-web-scraping.md) | R1 | ✅ Done |
| 2 | [phase-02-ragless-chat.md](phase-02-ragless-chat.md) | R6 + R8 core | ✅ Done |
| 3 | [phase-03-rag-retrieval.md](phase-03-rag-retrieval.md) | R5 (retrieval) | ✅ Done |
| 4 | [phase-04-rag-vs-ragless.md](phase-04-rag-vs-ragless.md) | R3 + R5 (rerank/viz) | ✅ Done |
| 5 | phase-05-llm-controls.md | R8 | ▶ Next |
| 6 | phase-06-streaming-vs-batch.md | R4 | ◻ Planned |
| 7 | phase-07-tools.md | R2 + R9 | ◻ Planned |
| 8 | phase-08-asr.md | R7 | ◻ Planned |
| 9 | phase-09-tts.md | R10 | ◻ Planned |
| 10 | phase-10-voice-loop.md | R11 + R12 | ◻ Planned |
| 11 | phase-11-latency-dashboard.md | R13 | ◻ Planned |
| 12 | phase-12-widget-deploy.md | R14 | ◻ Planned |

## Companion docs (the big picture)
- [`../requirements.md`](../requirements.md) — problem, ordered requirements R1–R14, success criteria
- [`../spec.md`](../spec.md) — architecture + all design decisions
- [`../tasks.md`](../tasks.md) — the phase plan + requirement→phase map + working agreement
- [`../test-cases.md`](../test-cases.md) — automated + manual test cases per phase

## Final submission bundle (planned)
1. **Code** — `backend/` (FastAPI) + `playground/` + `nimbus-voice-agent-starter/`
2. **Deployed** — frontend on Vercel (`nimbus-harshul.vercel.app`) + backend on Railway
3. **Design doc** — this `phases/` set + `requirements.md` + `spec.md` (optionally assembled into
   a single `DESIGN.md` at the end for a clean submission artifact)
