# Phase 9 — TTS / Voice Output (Report / Design Doc)

> Status: ✅ Done · Requirement: R10 · Tests: 7 passing · Playground: TTS provider/voice + 🔊 speak
> Design target: [`../reference.md`](../reference.md).

## 1. Concept — what this phase teaches

The mirror image of Phase 8: **text-to-speech (TTS)** — the agent *speaks its answer back*. Given the
LLM's reply text, a provider synthesizes audio that the browser plays.

Two teaching points:
- **Two latencies, not one.** `tts_ms` is the **server-side synthesis** time (the provider generating
  the audio). `buffer_ms` is the **client-side playback buffer** — how long the browser needs to
  decode/buffer the returned audio before it can start playing. Both matter for how "instant" a voice
  feels; the playground shows them as separate stages.
- **Audio comes back in different shapes.** OpenAI and ElevenLabs return ready-to-play **MP3**; Gemini
  returns **raw 24 kHz PCM**, which we wrap into a WAV container server-side (`audio.pcm_to_wav`) so the
  browser gets one predictable, playable format.

## 2. What we built

```
backend/app/tts/service.py  synthesize(text, provider, voice) → {audio, mime, tts_ms, provider, voice}
                            OpenAI (gpt-4o-mini-tts, MP3) / ElevenLabs (eleven_turbo_v2_5, MP3) /
                            Gemini (gemini-2.5-flash-preview-tts, PCM → WAV)
backend/app/main.py         POST /tts  → audio bytes; tts_ms in the X-TTS-Ms header
                            GET  /tts/voices → voices per provider (first = default)
```
Playground: a **Voice output (TTS)** selector (provider + voice) and a **🔊 Speak replies aloud**
toggle. When on, each answer is auto-spoken; either way a small **🔊** button on every reply replays
it. After playback the **This turn** panel folds in **TTS** (synth) and **Buffer** (playback) bars
next to ASR / RAG / LLM.

## 3. Design decisions

| Decision | Choice | Why |
|---|---|---|
| Audio return | binary body + `X-TTS-Ms` header (not base64 JSON) | Smaller, native `<audio>` playback; timing rides along in a header. |
| CORS | `expose_headers=[X-TTS-Ms, …]` | So the browser can *read* the synth time cross-origin (Vercel → Render). |
| Gemini PCM | wrap to WAV with `audio.pcm_to_wav` | Gemini emits raw 24 kHz PCM; browsers need a container. |
| `buffer_ms` | measured client-side (bytes → `canplaythrough`) | The real "time to first audio" cost, distinct from server synth. |
| Auto-play vs button | both — toggle + per-reply 🔊 | Hands-free listening, or replay on demand without re-synthesizing the whole turn. |
| Keys | resolved per-request (honors `REQUIRE_USER_KEYS`) | Same key model as chat/ASR. |
| Scope | TTS only (text → speech, click/auto play). | The continuous mic→ASR→LLM→TTS **loop** with barge-in is Phase 10. |

## 4. How it works

```
answer text ─▶ POST /tts {text, provider, voice}
                 └▶ provider synthesize → audio bytes           timed → tts_ms  (X-TTS-Ms header)
             ◀── audio/mpeg | audio/wav
browser: decode/buffer the bytes                                timed → buffer_ms (client-side)
         play via <audio>; fold TTS + Buffer into "This turn"
```

## 5. How to test it

**In the playground:**
1. Set **Voice output (TTS) → OpenAI**, pick a voice (Alloy…). Tick **🔊 Speak replies aloud**.
2. Ask *"What's the refund policy?"* → the answer is **spoken**; the **This turn** panel now shows
   **TTS** (synth ms) and **Buffer** (playback ms) bars alongside LLM.
3. Untick auto-play and click the **🔊** on any past reply to replay it.
4. Switch voice/provider and hear the difference (ElevenLabs needs its key; Gemini needs a working key).

**Automated:** `make test` (Phase 9 = 7 tests; provider HTTP mocked, offline) → 60 total.
**Live-verified:** `POST /tts` (OpenAI, alloy) → a valid 24 kHz MP3 that plays *"Welcome to Nimbus.
How can I help you today?"*, `X-TTS-Ms` returned.

## 6. Key takeaways

- **TTS = text → speech**; it's the exact inverse of ASR and closes the "voice out" half.
- **Two costs, not one:** server **synth** (`tts_ms`) + client **playback buffer** (`buffer_ms`).
- **Normalize the output too:** MP3 passes through; Gemini's raw PCM gets wrapped to WAV so the browser
  always gets something playable.

## 7. What's next

**Phase 10 — full voice loop + interrupt + endpointing:** wire mic → ASR → (RAG) → LLM → tools → TTS
into a continuous, hands-free WebSocket loop with **barge-in** (talk over the agent to stop playback)
and silence **endpointing**. That's where `asr_ms → … → tts_ms → buffer_ms` finally becomes one
end-to-end trace per spoken turn.
