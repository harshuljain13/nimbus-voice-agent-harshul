# Phase 10 — Voice loop + barge-in + endpointing (Report / Design Doc)

> Status: ◻ awaiting manual test · Requirement: R11 · Tests: 5 passing (backend) · Playground: new `voice.html`
> Design target: [`../reference.md`](../reference.md).

## 1. Concept — what this phase teaches

Phases 8 (ASR) and 9 (TTS) built the two *halves* of voice as separate, button-driven steps.
Phase 10 stitches them into a **continuous, hands-free conversation**:

```
🎤 mic → VAD endpointing → /asr → /chat(/stream) → sentence TTS → 🔊 playback
   ▲                                                                      │
   └──────────────────── back to listening (loop) ───────────────────────┘
```

Three teaching points:

- **The loop is a browser state machine, not a WebSocket.** The whole cycle is orchestrated
  client-side in `voice.js`, reusing the REST endpoints we already have (`/asr`, `/chat/stream`,
  `/tts`). This mirrors the reference exactly and means every building block was already tested.
- **Endpointing = "how do we know you stopped talking?"** We measure the mic's **RMS energy**
  every frame, learn the room's **noise floor** at startup, and end your turn after a
  configurable **silence timeout**. No ML, no library — energy + a timer.
- **Barge-in = letting you interrupt.** While speaking, the mic also hears the agent's own voice
  (echo). We subtract a *predicted echo* from the mic signal and treat the **residual** as your
  voice; when it persists, we stop playback and yield the floor.

## 2. What we built

```
backend/app/llm/history.py   annotate_last_assistant(session_id, note) → bool
                             appends "[cancelled by the user]" to the last assistant turn
backend/app/main.py          POST /session/cancel_last {session_id} → {ok, annotated}
playground/voice.html        dark control panel (ASR/TTS/voice, endpoint, pre-buffer, mode,
                             barge-in sensitivity, model, knowledge, tools) + mic orb + pie
playground/voice.css         voice-only styles (mic orb, level meter, transcript, pill, legend)
playground/voice.js          the loop: mic → VAD → ASR → chat → sentence-TTS → playback + barge-in
playground/playground.html   header link → voice.html; phase chip → Phase 10
```

Everything else — ASR, streaming chat, TTS, the 8-key latency trace — is **reused unchanged**.
The only backend change is the one-line-idea cancel endpoint.

## 3. Design decisions

| Decision | Choice | Why |
|---|---|---|
| Transport | Client-side loop over existing REST (no WebSocket) | Mirrors the reference; reuses tested `/asr` `/chat/stream` `/tts`; nothing new to deploy. |
| Endpointing | RMS energy + adaptive noise floor + silence timeout | Simple, fast, no dependency; user tunes the timeout (200–1500 ms). |
| Barge-in | Echo-aware residual (`mic − echoGain·ttsOut`) + hysteresis + 350 ms grace | The mic hears our own audio; subtracting predicted echo isolates the user. Frames + grace kill false triggers. |
| `echoGain` | Learned only while the user is silent (0.97 old + 0.03 new) | During user silence, mic energy *is* echo — so that ratio estimates the coupling. |
| Barge sensitivity | Preset select (off/low/med/high) | It depends on mic/speaker/room — expose it rather than hardcode. |
| Cancel on backend | Annotate history, don't kill the LLM task | Matches reference; the generation is cheap and already streaming — we just record that the turn was cut off so context stays honest. |
| Don't re-listen mid-answer | Re-arm the mic only when playback drains **and** the whole answer is spoken (`answerComplete`) + a 400 ms echo-tail guard | With slow TTS the audio queue empties *between* streamed sentences; re-arming then makes the agent hear (and answer) its own next sentence. The guard also sheds the speaker's echo tail. |
| Answer length | `response_length: "low"` | Short replies feel snappier spoken. |
| Two pipeline modes | Batch (full answer → speak) vs Streaming (speak per sentence) | Streaming lowers time-to-first-audio; the pie/TTFA table lets you compare. |

## 4. How it works

```
loop() @ ~60fps:
  listening → level > threshold?           → beginRecording()            [MediaRecorder]
  recording → silence > endpoint ms?       → endRecording() → /asr → text
  text → runPipeline():
     stream: /chat/stream → on each sentence → /tts → decode → queue → play
     batch:  /chat → full text → /tts → decode → queue → play
  speaking → residual = mic − echoGain·ttsOut;  residual sustained? → bargeIn()
     bargeIn(): stopPlayback() + POST /session/cancel_last + resumeListening()
  queue drains with no barge-in            → resumeListening()
```

Playback uses a **Web-Audio queue** (`decodeAudioData` → `BufferSource`) so sentences play
back-to-back, and so we can measure the TTS output envelope for the echo model. Time-to-first-audio
is measured from turn start to the first audio sample and broken down into the latency pie
(ASR · RAG · LLM · TTS · buffer · other).

## 5. How to test it

**Serve the frontend + backend** (two terminals, from repo root):
```
make api      # backend on :8100
make web      # static server on :8092   → open http://localhost:8092/playground/voice.html
```

**In the voice page:**
1. Open **API keys**, confirm your OpenAI key (and ElevenLabs/Gemini if you want those providers).
2. Pick **ASR = OpenAI** (or **Browser** for on-device), **TTS = OpenAI**, a voice.
3. Click the **mic orb** → it calibrates (~0.5 s) then shows **listening…**.
4. Say *"What's the refund policy?"* → after you pause it transcribes, thinks, and **speaks back**.
   The transcript shows both turns; the right rail shows the **time-to-first-audio** pie + total.
5. **Barge-in:** while it's speaking a long answer, talk over it — playback should stop, the bubble
   marks **⏹ interrupted**, and it returns to listening. Tune the **Barge-in** select if it triggers
   too easily / not at all (headphones make it far more reliable).
6. Toggle **Batch vs Streaming** and compare the two TTFA rows — streaming should be lower.
7. Try **RAG** vs **RAGless**, and **Tools** on (batch) e.g. *"add the CRM Pro plan to my cart."*

**Automated:** `make test` → Phase 10 adds 5 backend tests (history annotation + `/session/cancel_last`).
The loop itself (mic VAD, endpointing, echo-aware barge-in) is browser-side and verified manually here.

## 6. Key takeaways

- **A voice "loop" is a state machine** (listening → recording → thinking → speaking → listening),
  not a special transport — plain REST calls in a cycle.
- **Endpointing is energy + a silence timer** over an adaptive noise floor.
- **Barge-in is echo subtraction:** predict how much of our own audio the mic hears, and react only
  to the residual — with grace + hysteresis so a cough doesn't cut the agent off.

## 7. What's next

**Phase 11 — Latency dashboard:** promote the per-turn pie into a persistent dashboard (per-stage
% and totals across turns, batch vs streaming), so the full `asr → rag → llm → tts → buffer → total`
trace is visible at a glance. Then **Phase 12** — finalize the website widget + deploy.
