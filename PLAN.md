# Nimbus Voice Agent — Plan

Built **phase by phase**; each phase is independently testable in the playground before the next.
This is the short version — the living plan (requirements → spec → tasks → per-phase design docs)
is in [`.spec-dev/`](.spec-dev/). North star: [`.spec-dev/reference.md`](.spec-dev/reference.md).

## Scope (locked)
- **LLM**: OpenAI (lite `gpt-4o-mini` + heavy `gpt-4o`) + Gemini (flash/pro). Anthropic out.
- **Voice**: web/browser only. Public phone / Twilio out.
- **Embedding profiles**: `light` (OpenAI embed + LLM rerank, Railway) / `rich` (local MiniLM + cross-encoder).
- Deploy: backend → Railway, frontend + playground → Vercel.

## Phases
| # | Phase | Delivers | Status |
|---|-------|----------|--------|
| 0 | Foundation | backend, keys, latency trace | ✅ |
| 1 | Web scraping | `catalog.json` → docs + `context.md` | ✅ |
| 2 | RAGless chat | grounded chat, playground, context inspector | ✅ |
| 3 | RAG retrieval | chunk · embed · FAISS · top-k | ✅ |
| 4 | RAG vs RAGless | toggle + rerank + 2D vector/query viz + citations | ✅ |
| 5 | LLM controls | Gemini, history (verbatim-N + summary), RAG routing | ✅ |
| 6 | Streaming vs batch | TTFT vs total + comparison | ✅ |
| 7 | Tools | 11 cart/pricing tools + on/off selection + live cart | ✅ |
| 8 | ASR | browser / OpenAI / Gemini / ElevenLabs | ◻ next |
| 9 | TTS | OpenAI / Gemini / ElevenLabs + buffering | ◻ |
| 10 | Voice loop | WS mic loop + barge-in + endpointing | ◻ |
| 11 | Latency dashboard | per-stage % + total | ◻ |
| 12 | Widget + deploy | landing chatbox (✅ + cart bridge) + Vercel/Railway (deploy pending) | ◧ |

## Per-turn latency trace (every stage, always)
`{ asr_ms, rag_ms, llm_ttft_ms, llm_total_ms, tool_ms, tts_ms, buffer_ms, total_ms }`
