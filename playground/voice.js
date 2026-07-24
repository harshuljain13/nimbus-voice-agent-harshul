// Nimbus voice loop — Phase 10.
// A hands-free turn: mic → VAD endpointing → ASR → /chat(/stream) → sentence-by-sentence
// TTS → buffered Web-Audio playback → back to listening. Barge-in lets you talk over the
// agent to stop it. Reuses the Phase 8 (/asr), 6 (/chat/stream) and 9 (/tts) endpoints —
// the whole loop is orchestrated here in the browser (no WebSocket).

const LS_KEYS = "nimbus_pg_keys";
const LS_BASE = "nimbus_backend_url"; // shared with runtime-config.js + playground
const CFG_KEY = "nimbus_agent_config"; // shared config the landing widget reads (Phase 12)
const DEFAULT_BASE = (window.NIMBUS_CONFIG && window.NIMBUS_CONFIG.defaultBackendUrl) || "http://localhost:8100";
const $ = (id) => document.getElementById(id);

// latency pie slices: key → [label, colour]
const PIE = {
  asr_ms: ["ASR", "#3fb0c9"], rag_ms: ["RAG", "#a78bfa"], llm_total_ms: ["LLM", "#7c8cff"],
  tool_ms: ["Tools", "#34d399"], tts_ms: ["TTS", "#fbbf24"], buffer_ms: ["Buffer", "#e06aa8"],
  other_ms: ["Other/net", "#8a94a6"],
};

const state = {
  base: localStorage.getItem(LS_BASE) || DEFAULT_BASE,
  keys: load(LS_KEYS),
  session: "voice-" + Math.random().toString(36).slice(2),
  on: false, phase: "idle", mode: "stream",   // phase: idle|listening|recording|thinking|speaking
  // mic + analysers
  stream: null, ac: null, analyser: null, buf: null, noiseFloor: 0.01,
  recorder: null, chunks: [], lastVoice: 0, rec: null, speechEndTs: 0,
  // Web-Audio TTS playback + barge-in
  ttsAnalyser: null, ttsBuf: null, queue: [], source: null, playing: false, cancelled: false,
  playStartTs: 0, echoGain: 0.4, bargeFrames: 0, turnStart: 0, firstAudioAt: 0,
  lastBubble: null, voices: {},
  answerComplete: false, listenGuardUntil: 0,   // gate re-listening until the answer is fully spoken
  pendingAudio: 0,                              // sentences synthesized but not yet decoded+played
  lastReply: "",                               // the agent's last spoken answer (for echo filtering)
};

// Content-based echo guard: if a transcript is mostly the words of the agent's own last reply,
// it's the mic hearing the speaker — drop it. Works even without headphones / echo cancellation.
function normWords(s) { return (s || "").toLowerCase().replace(/[^a-z0-9\s]/g, " ").split(/\s+/).filter(Boolean); }
function isSelfEcho(text) {
  const inW = normWords(text);
  const ref = new Set(normWords(state.lastReply));
  if (inW.length < 4 || ref.size === 0) return false;
  const hit = inW.filter((w) => ref.has(w)).length;
  return hit / inW.length >= 0.7;
}

// After playback ends we wait this long before re-arming the mic, so the speaker's audio tail /
// room echo doesn't get picked up as a new user turn (headphones make this a non-issue).
const LISTEN_GUARD_MS = 400;

// Barge-in is a double-talk detector: we play TTS through Web Audio so we can measure the
// output envelope, estimate how much of it echoes into the mic (echoGain), and flag user
// speech only when mic energy exceeds that predicted echo, sustained for `frames` frames.
const BARGE_GRACE_MS = 350;   // let echoGain settle before we trust the trigger
const BARGE_PRESETS = {
  off:    { enabled: false, threshold: 1,    frames: 999 },
  low:    { enabled: true,  threshold: 0.09, frames: 11 },   // least sensitive (default)
  medium: { enabled: true,  threshold: 0.06, frames: 8 },
  high:   { enabled: true,  threshold: 0.04, frames: 5 },    // most sensitive
};
function bargeCfg() { return BARGE_PRESETS[$("barge").value] || BARGE_PRESETS.low; }

function load(k) { try { return JSON.parse(localStorage.getItem(k) || "{}"); } catch { return {}; } }
function keyHeaders() {
  const h = {};
  if (state.keys.openai) h["X-OpenAI-Key"] = state.keys.openai;
  if (state.keys.gemini) h["X-Gemini-Key"] = state.keys.gemini;
  if (state.keys.elevenlabs) h["X-ElevenLabs-Key"] = state.keys.elevenlabs;
  return h;
}
function authHeaders() { return { "Content-Type": "application/json", ...keyHeaders() }; }

// ---- UI helpers ----
function setPhase(p, text) {
  state.phase = p;
  $("status").textContent = p;
  $("status").className = "pill " + (p === "idle" ? "pill-muted" : "pill-ok");
  const cls = p === "recording" ? " recording" : p === "speaking" ? " speaking" : state.on ? " listening" : "";
  $("mic").className = "mic-orb" + cls;
  if (text != null) $("phase").textContent = text;
}
function addMsg(role, text) {
  const d = document.createElement("div");
  d.className = "t-msg t-" + role;
  d.textContent = text;
  $("transcript").append(d);
  $("transcript").scrollTop = $("transcript").scrollHeight;
  return d;
}
function addMetaLine(text) {
  const d = document.createElement("div");
  d.className = "t-meta"; d.textContent = text;
  $("transcript").append(d); $("transcript").scrollTop = $("transcript").scrollHeight;
}

// ---- latency pie ----
function renderPie(lat) {
  const cv = $("pie"), ctx = cv.getContext("2d");
  const W = cv.width, cx = W / 2, cy = W / 2, r = W / 2 - 6;
  ctx.clearRect(0, 0, W, W);
  const entries = Object.keys(PIE).map((k) => [k, lat[k] || 0]);
  const total = entries.reduce((s, [, v]) => s + v, 0) || 1;
  let a = -Math.PI / 2;
  for (const [k, v] of entries) {
    if (v <= 0) continue;
    const slice = (v / total) * Math.PI * 2;
    ctx.beginPath(); ctx.moveTo(cx, cy); ctx.arc(cx, cy, r, a, a + slice);
    ctx.closePath(); ctx.fillStyle = PIE[k][1]; ctx.fill();
    a += slice;
  }
  ctx.beginPath(); ctx.arc(cx, cy, r * 0.55, 0, Math.PI * 2); ctx.fillStyle = "#12161f"; ctx.fill();
  $("latTotal").textContent = Math.round(total);
  // Biggest contributor (R13): call out the slowest stage of this turn.
  const bc = $("latBiggest");
  const [topK, topV] = entries.reduce((m, e) => (e[1] > m[1] ? e : m), ["", 0]);
  if (topV > 0) {
    bc.hidden = false;
    bc.innerHTML = `<span class="dot" style="background:${PIE[topK][1]}"></span>` +
      `Biggest stage: <b>${PIE[topK][0]}</b> — ${Math.round(topV)}ms (${Math.round(topV / total * 100)}%)`;
  } else {
    bc.hidden = true;
  }
  $("pieLegend").innerHTML = entries.map(([k, v]) =>
    `<div class="pl"><span class="dot" style="background:${PIE[k][1]}"></span><span>${PIE[k][0]}</span><span>${Math.round(v)}ms (${Math.round(v / total * 100)}%)</span></div>`
  ).join("");
}

// ---- mic + analysers ----
async function ensureMic() {
  if (state.stream) return;
  state.stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  state.ac = new (window.AudioContext || window.webkitAudioContext)();
  const src = state.ac.createMediaStreamSource(state.stream);
  state.analyser = state.ac.createAnalyser();
  state.analyser.fftSize = 1024;
  state.buf = new Float32Array(state.analyser.fftSize);
  src.connect(state.analyser);
  // analyser on the TTS output path — our echo reference (what we're playing right now)
  state.ttsAnalyser = state.ac.createAnalyser();
  state.ttsAnalyser.fftSize = 1024;
  state.ttsBuf = new Float32Array(state.ttsAnalyser.fftSize);
  state.ttsAnalyser.connect(state.ac.destination);
}
function rmsOf(analyser, buf) {
  analyser.getFloatTimeDomainData(buf);
  let s = 0;
  for (const x of buf) s += x * x;
  return Math.sqrt(s / buf.length);
}
function rms() { return rmsOf(state.analyser, state.buf); }
function ttsLevel() { return state.playing ? rmsOf(state.ttsAnalyser, state.ttsBuf) : 0; }
function speechThreshold() { return Math.max(0.012, state.noiseFloor * 2 + 0.01); }

async function calibrate() {
  const samples = [];
  const t0 = performance.now();
  while (performance.now() - t0 < 500) {
    samples.push(rms());
    await new Promise((r) => setTimeout(r, 30));
  }
  state.noiseFloor = samples.reduce((a, b) => a + b, 0) / samples.length;
}

// ---- the loop: one requestAnimationFrame tick (~60/s) ----
function loop() {
  if (!state.on) return;
  const level = rms();
  $("levelBar").style.width = Math.min(100, level * 600) + "%";
  const th = speechThreshold();
  const now = performance.now();
  const serverMode = $("asr").value !== "browser";

  if (state.phase === "speaking") {
    // barge-in: subtract predicted echo from the mic; the residual is (roughly) the user's voice
    const bc = bargeCfg();
    const out = ttsLevel();
    const residual = level - state.echoGain * out;
    const since = now - state.playStartTs;
    const speaking = residual > bc.threshold;
    if (!speaking && out > 0.005) {
      // learn echo coupling ONLY while the user is silent (mic energy is then pure echo)
      state.echoGain = Math.min(4, Math.max(0, state.echoGain * 0.97 + (level / out) * 0.03));
    }
    if (bc.enabled && since > BARGE_GRACE_MS) {
      state.bargeFrames = speaking ? state.bargeFrames + 1 : Math.max(0, state.bargeFrames - 1);
      if (state.bargeFrames >= bc.frames) bargeIn();
    }
  } else if (serverMode && state.phase === "listening" && level > th && now > state.listenGuardUntil) {
    beginRecording();                                    // your turn started
  } else if (serverMode && state.phase === "recording") {
    if (level > th) state.lastVoice = now;               // still talking → reset silence timer
    if (now - state.lastVoice > Number($("endpoint").value)) endRecording();  // silence → your turn ended
  }
  requestAnimationFrame(loop);
}

// ---- server-ASR capture (MediaRecorder → /asr) ----
function beginRecording() {
  state.chunks = [];
  state.recorder = new MediaRecorder(state.stream, { mimeType: pickMime() });
  state.recorder.ondataavailable = (e) => { if (e.data.size) state.chunks.push(e.data); };
  state.recorder.onstop = onRecordingStop;
  state.recorder.start();
  state.lastVoice = performance.now();
  setPhase("recording", "listening to you… (press Space or tap the mic when done)");
}
function endRecording() {
  if (state.recorder && state.recorder.state !== "inactive") state.recorder.stop();
}
async function onRecordingStop() {
  const blob = new Blob(state.chunks, { type: state.recorder.mimeType });
  if (blob.size < 1200) { setPhase("listening", "(too short, ignored)"); return; }
  setPhase("thinking", "transcribing…");
  const fd = new FormData();
  fd.append("provider", $("asr").value);
  fd.append("file", blob, "utt.webm");
  try {
    const r = await fetch(state.base + "/asr", { method: "POST", headers: keyHeaders(), body: fd });
    const d = await r.json();
    if (d.error) { setPhase("listening", "ASR error: " + d.error); return; }
    if (!d.text) { setPhase("listening", "(no speech detected)"); return; }
    if (isSelfEcho(d.text)) { setPhase("listening", "(ignored my own voice)"); return; }
    addMsg("user", d.text);
    await runPipeline(d.text, d.asr_ms || 0);
  } catch (e) { setPhase("listening", "ASR failed: " + e.message); }
}
function pickMime() {
  for (const m of ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"])
    if (MediaRecorder.isTypeSupported(m)) return m;
  return "";
}

// ---- browser ASR (Web Speech API — endpointing handled on-device) ----
function startBrowserASR() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { setPhase("listening", "Browser ASR unsupported here; pick another ASR."); return; }
  const rec = new SR();
  rec.continuous = true; rec.interimResults = false; rec.lang = "en-US";
  rec.onspeechend = () => { state.speechEndTs = performance.now(); };
  rec.onresult = async (ev) => {
    const text = ev.results[ev.results.length - 1][0].transcript.trim();
    if (!text || state.phase === "thinking" || state.phase === "speaking") return;
    if (isSelfEcho(text)) return;   // mic heard the agent's own reply
    addMsg("user", text);
    // Browser Web Speech is on-device: asr_ms = recognition latency since speech ended.
    // Consume speechEndTs (reset to 0) so a later result can't reuse a stale timestamp, and
    // clamp implausible deltas — a large gap is idle wall-clock, not ASR compute, and would
    // otherwise dominate the TTFA breakdown with a bogus 20s+ "ASR" slice.
    const delta = state.speechEndTs ? performance.now() - state.speechEndTs : 0;
    state.speechEndTs = 0;
    const asrMs = delta > 0 && delta < 4000 ? Math.round(delta) : 0;
    await runPipeline(text, asrMs);
  };
  rec.onerror = () => {};
  rec.onend = () => { if (state.on && $("asr").value === "browser") { try { rec.start(); } catch {} } };
  state.rec = rec;
  try { rec.start(); } catch {}
}
function stopBrowserASR() { if (state.rec) { state.rec.onend = null; try { state.rec.stop(); } catch {} state.rec = null; } }

// ---- pipeline: chat → tts ----
function chatBody(message, mode) {
  const know = document.querySelector("#knowledge .active").dataset.v;
  return JSON.stringify({
    session_id: state.session, message, mode,
    model_key: $("model").value, response_length: "medium",   // "low" makes the model punt on broad Qs
    use_context: know === "ragless", use_rag: know === "rag", top_k: 4,
    tools_enabled: $("toolsEnabled").checked,
    enabled_tools: [],   // our backend: [] = "all enabled tools" (orchestrator does `enabled_tools or None`)
  });
}

async function runPipeline(userText, asrMs) {
  state.cancelled = false;
  state.answerComplete = false;
  state.pendingAudio = 0;
  state.turnStart = performance.now();
  state.firstAudioAt = 0;
  if ($("asr").value === "browser") stopBrowserASR();  // don't let ASR hear our own audio
  if (state.mode === "stream") await pipelineStream(userText, asrMs);
  else await pipelineBatch(userText, asrMs);
}

// batch: wait for the full answer, then synthesize + speak it
async function pipelineBatch(userText, asrMs) {
  setPhase("thinking", "thinking…");
  let chat;
  try {
    const r = await fetch(state.base + "/chat", { method: "POST", headers: authHeaders(), body: chatBody(userText, "batch") });
    if (!r.ok) { addMsg("assistant", `chat error (HTTP ${r.status}): ${(await r.text()).slice(0, 200)}`).classList.add("cancelled"); resumeListening(); return; }
    chat = await r.json();
  } catch (e) { setPhase("listening", "chat failed: " + e.message); return; }
  if (chat.error) { setPhase("listening", "chat error: " + chat.error); return; }
  state.lastBubble = addMsg("assistant", chat.text);
  state.lastReply = chat.text;
  setPhase("thinking", "synthesizing voice…");
  const tts = await synth(chat.text);
  if (!tts) { resumeListening(); return; }
  const lat = { ...chat.latency, asr_ms: asrMs, tts_ms: tts.ms, buffer_ms: Number($("buffer").value) };
  beginSpeaking();
  await new Promise((r) => setTimeout(r, lat.buffer_ms));   // pre-buffer
  enqueue(tts.audio, state.lastBubble);   // highlight the whole bubble while spoken
  state.answerComplete = true;   // batch has only this one utterance
  finishTurn(lat, "batch");
}

// streaming: speak sentence-by-sentence as the LLM writes — lowers time-to-first-audio
async function pipelineStream(userText, asrMs) {
  setPhase("thinking", "thinking…");
  const bubble = addMsg("assistant", "");
  state.lastBubble = bubble;
  let tail = document.createElement("span");   // holds tokens not yet forming a full sentence
  bubble.appendChild(tail);
  let acc = "", pending = "", spoke = false, lat0 = null;
  let firstSentenceTs = 0, firstSynthMs = 0;   // only the FIRST sentence gates first-audio
  const flush = async (text, el) => {
    const t = text.trim();
    if (!t || state.cancelled) return;
    const fs = performance.now();
    const tts = await synth(t);
    if (!tts || state.cancelled) return;
    if (!firstSentenceTs) { firstSentenceTs = fs; firstSynthMs = performance.now() - fs; }
    if (!spoke) { spoke = true; beginSpeaking(); await new Promise((r) => setTimeout(r, Number($("buffer").value))); }
    enqueue(tts.audio, el);   // el lights up while this sentence is spoken
  };
  try {
    const r = await fetch(state.base + "/chat/stream", { method: "POST", headers: authHeaders(), body: chatBody(userText, "stream") });
    if (!r.ok) { bubble.textContent = `chat error (HTTP ${r.status}): ${(await r.text()).slice(0, 200)}`; bubble.classList.add("cancelled"); resumeListening(); return; }
    const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done || state.cancelled) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split("\n\n"); buf = parts.pop();
      for (const p of parts) {
        const line = p.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        const ev = JSON.parse(line.slice(6));
        if (ev.type === "delta") {
          acc += ev.text; pending += ev.text; tail.textContent = pending;
          let m;
          // commit + flush every complete sentence to TTS as soon as it lands
          while ((m = pending.match(/[^.!?]*[.!?]+(\s|$)/)) && m[0].trim().length > 2) {
            const sentText = m[0];
            const span = document.createElement("span");
            span.className = "t-sent"; span.textContent = sentText;
            bubble.insertBefore(span, tail);          // committed sentence, tail keeps the rest
            pending = pending.slice(sentText.length); tail.textContent = pending;
            $("transcript").scrollTop = $("transcript").scrollHeight;
            await flush(sentText, span);
          }
        } else if (ev.type === "done") { lat0 = ev.latency; }
        else if (ev.type === "error") { bubble.textContent = "error: " + ev.error; }
      }
    }
    if (pending.trim()) { tail.className = "t-sent"; await flush(pending, tail); }
  } catch (e) { bubble.textContent = "stream failed: " + e.message; resumeListening(); return; }
  if (state.cancelled) return;
  state.answerComplete = true;                 // no more sentences will be enqueued
  state.lastReply = acc;
  if (!spoke) { resumeListening(); return; }
  endSpeakingIfDone();                          // resume now if the last sentence already finished playing
  // TTFA breakdown: only the first sentence's RAG + LLM + TTS gate first audio
  const ragMs = (lat0 && lat0.rag_ms) || 0;
  const llmToFirst = firstSentenceTs ? firstSentenceTs - state.turnStart : 0;
  const lat = {
    asr_ms: asrMs, rag_ms: ragMs,
    llm_total_ms: Math.max(0, llmToFirst - ragMs),
    tool_ms: 0, tts_ms: firstSynthMs, buffer_ms: Number($("buffer").value),
  };
  finishTurn(lat, "stream");
}

function finishTurn(lat, mode) {
  // Measured TTFA = ASR (before turnStart) + time from turnStart to first audio sample.
  const measured = state.firstAudioAt ? state.firstAudioAt - state.turnStart : 0;
  const ttfa = Math.round((lat.asr_ms || 0) + measured);
  const sum = ["asr_ms", "rag_ms", "llm_total_ms", "tool_ms", "tts_ms", "buffer_ms"]
    .reduce((s, k) => s + (lat[k] || 0), 0);
  lat = { ...lat, other_ms: Math.max(0, ttfa - sum) };   // network/decode remainder
  $(mode === "stream" ? "ttfaStream" : "ttfaBatch").textContent = ttfa + "ms";
  renderPie(lat);
  addMetaLine(`[${mode}] TTFA ${ttfa}ms = ASR ${Math.round(lat.asr_ms || 0)} + RAG ${Math.round(lat.rag_ms || 0)} + LLM ${Math.round(lat.llm_total_ms || 0)} + TTS ${Math.round(lat.tts_ms || 0)} + buffer ${Math.round(lat.buffer_ms || 0)} + other ${Math.round(lat.other_ms)}`);
}

// ---- TTS synth + Web-Audio queue playback ----
async function synth(text) {
  try {
    const r = await fetch(state.base + "/tts", {
      method: "POST", headers: authHeaders(),
      body: JSON.stringify({ text, provider: $("tts").value, voice: $("voice").value }),
    });
    if (!r.ok) return null;
    const ms = Number(r.headers.get("X-TTS-Ms") || 0);
    return { audio: await r.arrayBuffer(), ms };
  } catch { return null; }
}

function beginSpeaking() {
  state.playStartTs = performance.now();
  state.bargeFrames = 0;
  setPhase("speaking", "speaking (talk to interrupt)");
}

function highlight(el, on) { if (el && el.classList) el.classList.toggle("speaking", on); }

// `el` is the transcript element to light up while this chunk plays (the sentence span, or the
// whole bubble in batch mode) — makes the text-vs-audio lead visible.
async function enqueue(arrayBuffer, el) {
  if (state.cancelled) return;
  state.pendingAudio++;   // synchronous — reserves this sentence before its async decode
  let audioBuf;
  try { audioBuf = await state.ac.decodeAudioData(arrayBuffer.slice(0)); }
  catch { state.pendingAudio--; return; }
  state.pendingAudio--;
  if (state.cancelled) return;
  state.queue.push({ buf: audioBuf, el });
  if (!state.playing) playNext();
}

// Resume listening only when playback has drained AND the whole answer is in — otherwise the
// gap between streamed sentences would re-arm the mic mid-answer and the agent hears itself.
function endSpeakingIfDone() {
  if (state.phase === "speaking" && state.answerComplete && !state.playing
      && state.queue.length === 0 && state.pendingAudio === 0)
    resumeListening();
}

function playNext() {
  if (state.cancelled) { state.queue = []; state.playing = false; return; }
  const item = state.queue.shift();
  if (!item) { state.playing = false; endSpeakingIfDone(); return; }
  state.playing = true;
  const src = state.ac.createBufferSource();
  src.buffer = item.buf;
  src.connect(state.ttsAnalyser);
  highlight(item.el, true);
  src.onended = () => { highlight(item.el, false); state.source = null; playNext(); };
  state.source = src;
  if (!state.firstAudioAt) { state.firstAudioAt = performance.now(); state.playStartTs = performance.now(); }
  src.start();
}

function stopPlayback() {
  state.cancelled = true;
  state.queue = [];
  state.pendingAudio = 0;
  document.querySelectorAll(".speaking").forEach((e) => e.classList.remove("speaking"));
  if (state.source) { try { state.source.onended = null; state.source.stop(); } catch {} state.source = null; }
  state.playing = false;
}

function bargeIn() {
  stopPlayback();
  if (state.lastBubble) state.lastBubble.classList.add("cancelled");
  // tell the server the answer was cut off so its stored history reflects the interruption
  fetch(state.base + "/session/cancel_last", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: state.session }),
  }).catch(() => {});
  addMetaLine("— barge-in: response cancelled —");
  resumeListening();
}

function resumeListening() {
  if (!state.on) return;
  state.playing = false;
  state.answerComplete = false;
  state.listenGuardUntil = performance.now() + LISTEN_GUARD_MS;   // ignore the speaker's echo tail
  setPhase("listening", "listening…");
  // browser ASR has no echo model, so hold it off through the guard window too
  if ($("asr").value === "browser")
    setTimeout(() => { if (state.on && state.phase === "listening") startBrowserASR(); }, LISTEN_GUARD_MS);
}

// ---- master toggle ----
async function start() {
  try { await ensureMic(); } catch { setPhase("idle", "mic permission denied"); return; }
  if (state.ac.state === "suspended") await state.ac.resume();
  state.on = true;
  setPhase("listening", "calibrating mic…");
  await calibrate();
  setPhase("listening", "listening…");
  if ($("asr").value === "browser") startBrowserASR();
  requestAnimationFrame(loop);
}
function stop() {
  state.on = false;
  stopBrowserASR();
  stopPlayback();
  if (state.recorder && state.recorder.state !== "inactive") try { state.recorder.stop(); } catch {}
  setPhase("idle", "stopped");
}

// ---- load options ----
async function loadModels() {
  try {
    const d = await (await fetch(state.base + "/models", { headers: keyHeaders() })).json();
    $("model").innerHTML = d.models.map((m) => `<option value="${m.key}">${m.label}${m.available ? "" : " (no key)"}</option>`).join("");
  } catch {}
}
async function loadVoices() {
  try {
    const d = await (await fetch(state.base + "/tts/voices")).json();
    state.voices = d.voices || {};
    syncVoices();
  } catch {}
}
function syncVoices() {
  const list = state.voices[$("tts").value] || [];
  $("voice").innerHTML = list.map((v) => `<option value="${v.id}">${v.label}</option>`).join("");
}
function updateAsrHint() {
  $("asrHint").textContent = $("asr").value === "browser"
    ? "On-device Web Speech API. Endpointing handled by the browser."
    : "Server ASR. Your turn ends after the endpoint silence below.";
}

// Shared agent config consumed by the website widget (Phase 12) — merges with the playground's.
function persistConfig() {
  const know = document.querySelector("#knowledge .active")?.dataset.v || "rag";
  const toolsOn = $("toolsEnabled").checked;
  let prev = {};
  try { prev = JSON.parse(localStorage.getItem(CFG_KEY) || "{}"); } catch {}
  localStorage.setItem(CFG_KEY, JSON.stringify({
    ...prev,
    model_key: $("model").value, knowledge: know,
    tools_enabled: toolsOn, enabled_tools: [],
    asr: $("asr").value, tts: $("tts").value, voice: $("voice").value,
    endpoint: Number($("endpoint").value), buffer: Number($("buffer").value), barge: $("barge").value,
  }));
}

// ---- API keys dialog ----
function initKeys() {
  const dlg = $("keysDlg");
  $("keysBtn").addEventListener("click", () => {
    $("k_openai").value = state.keys.openai || ""; $("k_gemini").value = state.keys.gemini || "";
    $("k_elevenlabs").value = state.keys.elevenlabs || ""; $("apiBase").value = state.base;
    dlg.showModal();
  });
  dlg.addEventListener("close", () => {
    if (dlg.returnValue !== "save") return;
    state.keys = { openai: $("k_openai").value.trim(), gemini: $("k_gemini").value.trim(), elevenlabs: $("k_elevenlabs").value.trim() };
    localStorage.setItem(LS_KEYS, JSON.stringify(state.keys));
    state.base = $("apiBase").value.trim() || DEFAULT_BASE;
    localStorage.setItem(LS_BASE, state.base);
    loadModels(); loadVoices();
  });
}

// End the current turn immediately (skip the silence wait) — great for slow speakers. Server ASR only;
// browser ASR does its own endpointing.
function finishTurnNow() {
  if (state.on && state.phase === "recording" && $("asr").value !== "browser") { endRecording(); return true; }
  return false;
}

function init() {
  // While recording, a tap means "I'm done talking, send now"; otherwise it toggles the loop.
  $("mic").addEventListener("click", () => { if (!finishTurnNow()) state.on ? stop() : start(); });
  document.addEventListener("keydown", (e) => {
    if (e.code === "Space" && document.activeElement === document.body) { if (finishTurnNow()) e.preventDefault(); }
  });
  $("endpoint").addEventListener("input", (e) => $("epVal").textContent = e.target.value);
  $("buffer").addEventListener("input", (e) => $("bufVal").textContent = e.target.value);
  document.querySelectorAll("#mode button").forEach((b) =>
    b.addEventListener("click", () => {
      document.querySelectorAll("#mode button").forEach((x) => x.classList.remove("active"));
      b.classList.add("active"); state.mode = b.dataset.v;
    }));
  document.querySelectorAll("#knowledge button").forEach((b) =>
    b.addEventListener("click", () => {
      document.querySelectorAll("#knowledge button").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
    }));
  $("tts").addEventListener("change", syncVoices);
  $("asr").addEventListener("change", () => { updateAsrHint(); if (state.on) { stopBrowserASR(); resumeListening(); } });
  initKeys();
  loadModels();
  loadVoices().then(() => { updateAsrHint(); persistConfig(); });
  // keep the shared widget config in sync as controls change
  document.querySelector("main").addEventListener("change", persistConfig);
  document.querySelector("main").addEventListener("input", persistConfig);
  renderPie({});
}

init();
