# Phase 8 — ASR / Voice Input (Report / Design Doc)

> Status: ✅ Done · Requirement: R7 · Tests: 5 passing · Playground: 🎤 mic + ASR provider selector
> Design target: [`../reference.md`](../reference.md).

## 1. Concept — what this phase teaches

The first half of turning a *text* agent into a *voice* agent: **speech-to-text (ASR)**. The
browser captures your microphone, and either the browser itself (Web Speech API) or a cloud
provider (OpenAI / Gemini / ElevenLabs) turns the audio into text — which becomes the chat input.

Two teaching points:
- **Where the audio goes decides the trade-off.** Browser ASR is free + instant but Chrome-only
  and less accurate; cloud ASR is accurate + consistent but costs a round-trip (upload + transcribe).
- **One audio format for many providers.** Browsers record WebM/Opus; each ASR API wants something
  specific. So we transcode to **16 kHz mono WAV** once, up front, and every provider is happy.

## 2. What we built

```
backend/app/audio.py       ffmpeg transcode (webm → 16kHz mono WAV) via the pip-bundled ffmpeg
backend/app/asr/service.py transcribe(audio, provider) → OpenAI (gpt-4o-transcribe) / Gemini /
                           ElevenLabs (scribe); returns {text, asr_ms}
backend/app/main.py        POST /asr (multipart audio + provider); key resolved per-request
```
Playground: a **Voice input (ASR)** selector (Browser / OpenAI / Gemini / ElevenLabs) + a **🎤 mic
button** in the composer. Click → record → click to stop → the transcript fills the input (with a
`provider · Nms` readout). The **browser** provider uses the Web Speech API entirely client-side
(no upload, no key); the others record with `MediaRecorder` and POST the audio to `/asr`.

## 3. Design decisions

| Decision | Choice | Why |
|---|---|---|
| Browser provider | client-side Web Speech API — no backend, no key | Free, instant, zero setup; the easy default to try. |
| Cloud transcode | ffmpeg → 16 kHz mono WAV once, server-side | One format every provider accepts; browsers emit WebM/Opus. |
| ffmpeg source | `imageio-ffmpeg` (pip-bundled binary) | Works on Render/Railway with no apt install. |
| Transcript → input | fills the chat input (not auto-send) | Lets you review/edit before sending — safer than firing on a mishearing. |
| Keys | resolved per-request (honors `REQUIRE_USER_KEYS`) | Same key model as chat; ElevenLabs added to the keys dialog. |
| Scope | ASR only (mic → text). | The full mic→ASR→LLM→TTS **loop** with barge-in is Phase 10; TTS is Phase 9. |

## 4. How it works

```
🎤 click → MediaRecorder captures mic (WebM)           [browser: Web Speech, no upload]
click again → POST /asr (audio + provider)
  → audio.to_wav (ffmpeg → 16kHz mono WAV)             timed →
  → provider transcribe (OpenAI/Gemini/ElevenLabs)     → asr_ms
  → { text } fills the chat input
```

## 5. How to test it

**In the playground:**
1. **Browser** provider (default, no key): click **🎤**, allow the mic, say *"What's the refund
   policy?"*, click 🎤 again → the words appear in the input → **Send**. (Chrome/Edge.)
2. **OpenAI** provider (needs your OpenAI key): same flow → the audio uploads and comes back as
   text with a `openai · Nms` timing.
3. Gemini / ElevenLabs work the same with their keys (add ElevenLabs in **API keys**).

**Automated:** `make test` (Phase 8 = 5 tests; transcode + provider HTTP mocked, offline).
**Live-verified:** a macOS `say`-generated clip "Add Nimbus CRM Professional to my cart" → OpenAI
ASR returned exactly that (transcode + transcribe, ~3s).

## 6. Key takeaways

- **ASR = mic → text**; the transcript is just another way to fill the chat box.
- **Browser vs cloud** is a real trade: free/instant/Chrome-only vs accurate/consistent/costs-a-hop.
- **Normalize the audio once** (16 kHz mono WAV) and every provider "just works."

## 7. What's next

**Phase 9 — TTS (speech out):** OpenAI / Gemini / ElevenLabs voices with a playback buffer — the
agent talks back. Then **Phase 10** wires mic → ASR → LLM → TTS into a real, interruptible voice loop.
