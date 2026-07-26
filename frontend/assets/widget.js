// "Talk to Nimbus" — the finalized voice agent embedded on the site (Phase 12 / R14).
// Text OR voice, streaming, RAG-grounded, with tools (cart) and barge-in.
//
// Production config is HARDCODED in AGENT below (the Playground is only a dev/tuning tool — a real
// visitor's browser has no playground config). Every turn hits /chat/stream: pure Q&A streams
// token-by-token; tool turns run the loop then emit one delta (cart still updates). In voice mode
// the reply is split into sentences and each is synthesized as soon as it's complete, so the first
// audio starts after sentence 1, not the whole answer. Barge-in lets you talk over the agent.
//
// Visitors bring their own API keys (public deploy runs REQUIRE_USER_KEYS=true): the 🔑 dialog
// stores them in localStorage and every call (chat/asr/tts) carries them; the server never uses its own.

const _isLocal = location.hostname === "localhost" || location.hostname === "127.0.0.1";
const BASE = (localStorage.getItem("nimbus_backend_url") ||
  (_isLocal ? "http://localhost:8100" : "https://nimbus-voice-agent-harshul.onrender.com")).replace(/\/$/, "");
const CART_KEY = "nimbus_cart";
const CART_TOOLS = new Set(["add_to_cart", "remove_item", "checkout", "checkout_item", "clear_cart"]);
const SID_KEY = "nimbus_agent_session";
const KEYS_KEY = "nimbus_pg_keys";

// ---- the tuned production agent (edit here to retune; every visitor gets this) ----
const AGENT = {
  model_key: "openai-heavy",   // gpt-4o — best quality (swap to "openai-lite" for lower latency/cost)
  knowledge: "rag",            // retrieve from the catalog index (grounded answers + citations)
  response_length: "medium",
  tools_enabled: true,         // cart / pricing / sorting tools
  enabled_tools: [],           // [] = all tools (backend does `enabled_tools or None`)
  top_k: 4,
  asr: "openai",               // server ASR (MediaRecorder → /asr). Recording is gated to the LISTENING
                               // phase, so the mic is never captured while TTS plays — the reference
                               // widget's guard against the agent hearing its own voice.
  asr_fallback: "openai",
  tts: "openai", voice: "alloy",
  barge: "medium",             // interrupt sensitivity (high self-triggers on speaker echo)
  endpoint: 700, buffer: 120,  // ms: end-of-turn silence, TTS pre-roll
};
const BARGE_PRESETS = { off: { en: false, th: 1, fr: 999 }, low: { en: true, th: 0.09, fr: 11 }, medium: { en: true, th: 0.06, fr: 8 }, high: { en: true, th: 0.04, fr: 5 } };

function sessionId() {
  let s = localStorage.getItem(SID_KEY);
  if (!s) { s = "site-" + Math.random().toString(36).slice(2); localStorage.setItem(SID_KEY, s); }
  return s;
}
function siteCart() { try { return JSON.parse(localStorage.getItem(CART_KEY) || "[]"); } catch { return []; } }
function agentKeys() { try { return JSON.parse(localStorage.getItem(KEYS_KEY) || "{}"); } catch { return {}; } }
function saveKeys(k) { localStorage.setItem(KEYS_KEY, JSON.stringify(k)); }
function hasKey() { return !!agentKeys().openai; }

function keyHeaders() {
  const h = {}; const k = agentKeys();
  if (k.openai) h["X-OpenAI-Key"] = k.openai;
  if (k.gemini) h["X-Gemini-Key"] = k.gemini;
  if (k.elevenlabs) h["X-ElevenLabs-Key"] = k.elevenlabs;
  return h;
}
function jsonHeaders() { return { "Content-Type": "application/json", ...keyHeaders() }; }
function chatBody(message) {
  return JSON.stringify({
    session_id: sessionId(), message, mode: "stream",
    model_key: AGENT.model_key, response_length: AGENT.response_length,
    use_context: AGENT.knowledge === "ragless", use_rag: AGENT.knowledge === "rag", top_k: AGENT.top_k,
    tools_enabled: AGENT.tools_enabled, enabled_tools: AGENT.enabled_tools, verbatim_turns: 8,
  });
}

const STYLE = `
.nbw-btn{position:fixed;right:22px;bottom:22px;z-index:9998;width:58px;height:58px;border:0;border-radius:50%;
  background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;font-size:24px;cursor:pointer;box-shadow:0 8px 24px rgba(99,102,241,.45);transition:transform .15s}
.nbw-btn:hover{transform:scale(1.06)}
.nbw-panel{position:fixed;right:22px;bottom:92px;z-index:9999;width:372px;max-width:calc(100vw - 32px);height:566px;max-height:calc(100vh - 130px);
  background:#fff;border:1px solid #e6e8ef;border-radius:16px;box-shadow:0 24px 60px rgba(20,20,50,.22);display:none;flex-direction:column;overflow:hidden;font:14px/1.5 -apple-system,system-ui,Segoe UI,Roboto,sans-serif}
.nbw-panel.open{display:flex}
.nbw-head{background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;padding:14px 16px;display:flex;align-items:center;justify-content:space-between}
.nbw-head b{font-size:15px}.nbw-head small{opacity:.85;font-size:11.5px;display:block}
.nbw-hbtns{display:flex;align-items:center;gap:2px}
.nbw-gear,.nbw-key,.nbw-x{background:transparent;border:0;color:#fff;font-size:18px;cursor:pointer;line-height:1;padding:2px 6px}
.nbw-set{position:absolute;inset:56px 0 0 0;background:#fff;z-index:2;padding:16px;overflow-y:auto;display:none;flex-direction:column;gap:11px}
.nbw-set.open{display:flex}
.nbw-set h4{margin:0;font-size:14px;color:#1e2233}
.nbw-set label{display:flex;flex-direction:column;gap:4px;font-size:12px;color:#5b6475}
.nbw-set select{border:1px solid #d8dce6;border-radius:8px;padding:8px 10px;font:inherit;font-size:13px;color:#1a1f2b}
.nbw-set .nbw-row{display:flex;gap:8px}.nbw-set .nbw-row label{flex:1}
.nbw-set .nbw-tg{flex-direction:row;align-items:center;justify-content:space-between}
.nbw-set .nbw-save{border:0;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;border-radius:9px;padding:9px;cursor:pointer;font-weight:600;margin-top:2px}
.nbw-set .nbw-note{font-size:11px;color:#8b93a7}.nbw-set .nbw-note a{color:#6366f1}
.nbw-keys{position:absolute;inset:56px 0 0 0;background:#fff;z-index:2;padding:16px;overflow-y:auto;display:none;flex-direction:column;gap:12px}
.nbw-keys.open{display:flex}
.nbw-keys h4{margin:0;font-size:14px;color:#1e2233}
.nbw-keys p{margin:0;font-size:12px;color:#5b6475}
.nbw-keys label{display:flex;flex-direction:column;gap:4px;font-size:12px;color:#5b6475}
.nbw-keys input{border:1px solid #d8dce6;border-radius:8px;padding:8px 10px;font:inherit;font-size:13px}
.nbw-keys .nbw-save{border:0;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;border-radius:9px;padding:9px;cursor:pointer;font-weight:600;margin-top:2px}
.nbw-keys .nbw-note{font-size:11px;color:#8b93a7}.nbw-keys .nbw-note a{color:#6366f1}
.nbw-msgs{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px;background:#f7f8fb}
.nbw-msg{max-width:85%;padding:9px 12px;border-radius:13px;white-space:pre-wrap;word-break:break-word}
.nbw-user{align-self:flex-end;background:#6366f1;color:#fff;border-bottom-right-radius:4px}
.nbw-bot{align-self:flex-start;background:#fff;border:1px solid #e6e8ef;color:#1e2233;border-bottom-left-radius:4px}
.nbw-bot.cancelled{opacity:.55}
.nbw-bot.nbw-speaking{box-shadow:0 0 0 2px #c7d0ff}
.nbw-tool{align-self:flex-start;font-size:11px;color:#8b5cf6;background:#f2effe;border:1px solid #e6ddfb;border-radius:8px;padding:4px 9px}
.nbw-status{font-size:11px;color:#8b93a7;padding:3px 14px;background:#f7f8fb;min-height:15px}
.nbw-form{display:flex;gap:8px;padding:12px;border-top:1px solid #eceef4;background:#fff;align-items:center}
.nbw-mic{border:1px solid #d8dce6;background:#fff;color:#6366f1;border-radius:10px;width:40px;height:38px;cursor:pointer;display:grid;place-items:center;flex:0 0 auto}
.nbw-mic.on{background:#6366f1;color:#fff;border-color:#6366f1}
.nbw-mic.spk{background:#d29922;color:#fff;border-color:#d29922}
.nbw-form input{flex:1;min-width:0;border:1px solid #d9dce6;border-radius:9px;padding:9px 11px;font:inherit;outline:none}
.nbw-form input:focus{border-color:#6366f1}
.nbw-send{border:0;border-radius:9px;padding:9px 15px;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;font-weight:600;cursor:pointer}
.nbw-chips{display:flex;flex-wrap:wrap;gap:6px}
.nbw-chip{border:1px solid #d9dce6;background:#fff;border-radius:999px;padding:5px 10px;font-size:12px;cursor:pointer;color:#4b5168}
.nbw-chip:hover{border-color:#6366f1;color:#6366f1}`;

const MIC_SVG = '<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z"/></svg>';

export function mountWidget() {
  if (document.querySelector(".nbw-btn")) return;
  // apply any per-browser overrides saved from the ⚙ settings on top of the hardcoded AGENT defaults
  try {
    const o = JSON.parse(localStorage.getItem("nimbus_widget_cfg") || "{}");
    ["model_key", "asr", "tts", "voice", "barge", "knowledge", "tools_enabled"].forEach((k) => { if (o[k] != null) AGENT[k] = o[k]; });
  } catch {}
  const style = document.createElement("style"); style.textContent = STYLE; document.head.append(style);

  const btn = document.createElement("button");
  btn.className = "nbw-btn"; btn.title = "Talk to Nimbus"; btn.textContent = "💬";
  const panel = document.createElement("div");
  panel.className = "nbw-panel";
  panel.innerHTML = `
    <div class="nbw-head">
      <div><b>Talk to Nimbus</b><small>Type or tap the mic · streaming · full tools</small></div>
      <div class="nbw-hbtns"><button class="nbw-gear" title="Settings" aria-label="Settings">⚙</button><button class="nbw-key" title="API keys" aria-label="API keys">🔑</button><button class="nbw-x" aria-label="Close">×</button></div>
    </div>
    <div class="nbw-keys" id="nbwKeys"></div>
    <div class="nbw-set" id="nbwSet"></div>
    <div class="nbw-msgs" id="nbwMsgs">
      <div class="nbw-bot">Hi! I can answer questions and manage your cart — by text or voice. Try one:</div>
      <div class="nbw-chips">
        <button class="nbw-chip">Add Nimbus CRM Professional to my cart</button>
        <button class="nbw-chip">What's my cart total?</button>
        <button class="nbw-chip">How much do I save paying annually?</button>
      </div>
    </div>
    <div class="nbw-status" id="nbwStatus"></div>
    <form class="nbw-form" id="nbwForm">
      <button class="nbw-mic" id="nbwMic" type="button" title="Voice">${MIC_SVG}</button>
      <input id="nbwInput" placeholder="Type a message…" autocomplete="off" />
      <button type="submit" class="nbw-send">Send</button>
    </form>`;
  document.body.append(btn, panel);

  const msgs = panel.querySelector("#nbwMsgs");
  const statusEl = panel.querySelector("#nbwStatus");
  const micBtn = panel.querySelector("#nbwMic");
  const keysEl = panel.querySelector("#nbwKeys");
  const setEl = panel.querySelector("#nbwSet");
  const input = panel.querySelector("#nbwInput");
  const status = (t) => { statusEl.textContent = t || ""; };

  btn.addEventListener("click", () => {
    panel.classList.toggle("open");
    if (panel.classList.contains("open")) { if (!hasKey() && !_isLocal) openKeys(); else input.focus(); }
  });
  panel.querySelector(".nbw-x").addEventListener("click", () => panel.classList.remove("open"));
  panel.querySelectorAll(".nbw-chip").forEach((c) => c.addEventListener("click", () => sendText(c.textContent)));
  panel.querySelector("#nbwForm").addEventListener("submit", (e) => {
    e.preventDefault(); const v = input.value.trim(); if (!v) return; input.value = ""; sendText(v);
  });

  function add(kind, text) {
    const d = document.createElement("div"); d.className = "nbw-msg nbw-" + kind; d.textContent = text || "";
    msgs.append(d); msgs.scrollTop = msgs.scrollHeight; return d;
  }
  const scroll = () => { msgs.scrollTop = msgs.scrollHeight; };

  // ---- cart bridge (two-way) ----
  async function syncSiteToAgent() {
    const items = siteCart().map((i) => ({ product_id: i.product_id, product_name: i.product_name, tier: i.tier, seats: i.seats }));
    try { await fetch(BASE + "/cart/set", { method: "POST", headers: jsonHeaders(), body: JSON.stringify({ session_id: sessionId(), items }) }); } catch {}
  }
  // openDrawer = true only when a cart tool actually ran this turn; otherwise just repaint so the
  // drawer never pops open on its own (e.g. a spurious voice turn that finds leftover cart items).
  async function syncAgentToSite(openDrawer) {
    try {
      const d = await (await fetch(BASE + "/cart?session_id=" + encodeURIComponent(sessionId()))).json();
      const items = d.items.map((i) => ({ product_id: i.product_id, product_name: i.product_name, tier: i.tier, seats: i.seats, price: i.price_monthly }));
      localStorage.setItem(CART_KEY, JSON.stringify(items));
      if (window.__nimbusCart) { window.__nimbusCart.refresh(); if (openDrawer && items.length) window.__nimbusCart.open(); }
    } catch {}
  }

  // ---- streaming turn, shared by text + voice ----
  // Consumes /chat/stream SSE. In voice mode, each complete sentence is synthesized as it arrives
  // (onSentence). Returns { text, meta, ok }. On a key error, opens the keys dialog.
  async function streamTurn(message, bubble, onSentence) {
    await syncSiteToAgent();
    let r;
    try {
      r = await fetch(BASE + "/chat/stream", { method: "POST", headers: jsonHeaders(), body: chatBody(message) });
    } catch { bubble.textContent = "Can't reach the Nimbus agent. Is the backend running?"; return { ok: false }; }
    if (!r.ok) {
      const data = await r.json().catch(() => ({}));
      if (r.status === 400 && /key/i.test(data.detail || "")) { bubble.textContent = "Add your API key to chat →"; openKeys(); return { ok: false, keyNeeded: true }; }
      bubble.textContent = data.detail || "Something went wrong."; return { ok: false };
    }
    // Render the full text verbatim as it arrives — no DOM fragmentation, so structured replies
    // (numbered lists, prices like $10.00) display exactly as written. For voice we separately pull
    // off speakable chunks (a whole line, or a sentence — but never a list-number "1." or a decimal).
    bubble.textContent = "";
    const reader = r.body.getReader(), dec = new TextDecoder();
    let sseBuf = "", acc = "", pending = "", meta = null;
    const nextCut = () => {
      const nl = pending.indexOf("\n");
      const sm = pending.match(/(?<![0-9])[.!?](\s|$)/);   // sentence end, ignoring list markers & decimals
      let cut = nl >= 0 ? nl + 1 : -1;
      if (sm && (cut < 0 || sm.index + 1 < cut)) cut = sm.index + 1;
      return cut;
    };
    const commit = async (final) => {
      if (!onSentence) { pending = ""; return; }   // text mode: no TTS chunking needed
      for (let cut = nextCut(); cut > 0; cut = nextCut()) {
        const chunk = pending.slice(0, cut); pending = pending.slice(cut);
        if (chunk.trim().length >= 2) await onSentence(chunk);
      }
      if (final && pending.trim()) { await onSentence(pending); pending = ""; }
    };
    try {
      while (true) {
        const { done, value } = await reader.read(); if (done) break;
        sseBuf += dec.decode(value, { stream: true });
        const parts = sseBuf.split("\n\n"); sseBuf = parts.pop();
        for (const p of parts) {
          const line = p.split("\n").find((l) => l.startsWith("data: ")); if (!line) continue;
          const ev = JSON.parse(line.slice(6));
          if (ev.type === "delta") { acc += ev.text; pending += ev.text; bubble.textContent = acc; scroll(); await commit(false); }
          else if (ev.type === "done") { meta = ev.meta; }
          else if (ev.type === "error") { bubble.textContent = "Error: " + ev.error; return { ok: false }; }
        }
      }
      await commit(true);
    } catch (e) { bubble.textContent = "Stream failed: " + e.message; return { ok: false }; }
    const toolCalls = (meta && meta.tool_calls) || [];
    toolCalls.forEach((t) => add("tool", "🔧 " + t.name));
    await syncAgentToSite(toolCalls.some((t) => CART_TOOLS.has(t.name)));   // open the drawer only if the cart changed
    return { ok: true, text: acc, meta };
  }

  // text turn (renders tokens live; no speech)
  async function sendText(message) {
    add("user", message);
    const bubble = add("bot", "…");
    await streamTurn(message, bubble, null);
  }

  // ================= VOICE =================
  const V = {
    on: false, phase: "idle", stream: null, ac: null, an: null, buf: null, noise: 0.01,
    ttsAn: null, ttsBuf: null, rec: null, sr: null, chunks: [], lastVoice: 0, voicedFrames: 0,
    queue: [], src: null, playing: false, cancelled: false, echoGain: 0.4, bargeFrames: 0, playTs: 0,
    answerComplete: false, pendingAudio: 0, lastBubble: null, lastReply: "",
  };
  const BARGE_GRACE = 500, LISTEN_GUARD_MS = 400;
  const bargeP = () => BARGE_PRESETS[AGENT.barge] || BARGE_PRESETS.low;
  const serverAsr = () => AGENT.asr !== "browser";   // browser = on-device Web Speech; else MediaRecorder→/asr

  // ---- browser Web Speech ASR (on-device, English, no key, no hallucination) ----
  function startBrowserASR() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { AGENT.asr = AGENT.asr_fallback; status("Browser voice unsupported here; using server ASR."); return; }
    const rec = new SR();
    rec.continuous = true; rec.interimResults = false; rec.lang = "en-US";
    rec.onresult = async (ev) => {
      const text = ev.results[ev.results.length - 1][0].transcript.trim();
      if (!text || V.phase === "thinking" || V.phase === "speaking") return;
      if (isSelfEcho(text)) return;   // mic heard the agent's own reply
      add("user", text);
      await runVoicePipeline(text);
    };
    rec.onerror = () => {};
    // keep it alive across the browser's periodic auto-stops (it ignores results while thinking/speaking)
    rec.onend = () => { if (V.on && AGENT.asr === "browser" && V.sr === rec) { try { rec.start(); } catch {} } };
    V.sr = rec;
    try { rec.start(); } catch {}
  }
  function stopBrowserASR() { if (V.sr) { V.sr.onend = null; try { V.sr.stop(); } catch {} V.sr = null; } }
  const rmsOf = (an, b) => { an.getFloatTimeDomainData(b); let s = 0; for (const x of b) s += x * x; return Math.sqrt(s / b.length); };
  const micLevel = () => rmsOf(V.an, V.buf);
  const ttsLevel = () => (V.playing ? rmsOf(V.ttsAn, V.ttsBuf) : 0);
  const speechThreshold = () => Math.max(0.012, V.noise * 2 + 0.01);
  const setMic = (cls) => { micBtn.className = "nbw-mic" + (cls ? " " + cls : ""); };

  // drop a transcript that's really the agent's own last reply echoing back into the mic
  const normWords = (s) => (s || "").toLowerCase().replace(/[^a-z0-9\s]/g, "").split(/\s+/).filter(Boolean);
  function isSelfEcho(text) {
    const inW = normWords(text), ref = new Set(normWords(V.lastReply));
    if (inW.length < 4 || ref.size === 0) return false;
    return inW.filter((w) => ref.has(w)).length / inW.length >= 0.7;
  }

  async function ensureMic() {
    if (V.stream) return;
    V.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    V.ac = new (window.AudioContext || window.webkitAudioContext)();
    const s = V.ac.createMediaStreamSource(V.stream);
    V.an = V.ac.createAnalyser(); V.an.fftSize = 1024; V.buf = new Float32Array(V.an.fftSize); s.connect(V.an);
    V.ttsAn = V.ac.createAnalyser(); V.ttsAn.fftSize = 1024; V.ttsBuf = new Float32Array(V.ttsAn.fftSize); V.ttsAn.connect(V.ac.destination);
  }
  async function calibrate() {
    const a = []; const t = performance.now();
    while (performance.now() - t < 450) { a.push(micLevel()); await new Promise((r) => setTimeout(r, 30)); }
    V.noise = a.reduce((x, y) => x + y, 0) / a.length;
  }

  function loop() {
    if (!V.on) return;
    const lvl = micLevel(), now = performance.now(), th = speechThreshold();
    if (V.phase === "speaking") {
      const bp = bargeP(), out = ttsLevel(), residual = lvl - V.echoGain * out;
      const withinGrace = !V.playTs || now - V.playTs < BARGE_GRACE;
      const speaking = residual > bp.th;
      // Calibrate the echo-coupling estimate from our own playback. During the grace window we
      // adapt UNCONDITIONALLY so a speaker user's echo can't self-trigger before the estimator
      // has learned — otherwise residual stays high, "speaking" stays true, it never converges,
      // and the agent cuts itself off after a few words. After grace, only adapt while silent.
      if (out > 0.005 && (withinGrace || !speaking)) V.echoGain = Math.min(3, Math.max(0, V.echoGain * 0.9 + (lvl / out) * 0.1));
      if (bp.en && !withinGrace) { V.bargeFrames = speaking ? V.bargeFrames + 1 : Math.max(0, V.bargeFrames - 1); if (V.bargeFrames >= bp.fr) bargeIn(); }
    } else if (serverAsr() && V.phase === "listening" && now > (V.listenGuardUntil || 0) && lvl > th) {
      beginRec();
    } else if (serverAsr() && V.phase === "recording") {
      if (lvl > th) { V.lastVoice = now; V.voicedFrames++; }
      if (now - V.lastVoice > AGENT.endpoint) endRec();
    }
    requestAnimationFrame(loop);
  }

  function pickMime() {
    for (const m of ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"]) if (MediaRecorder.isTypeSupported(m)) return m;
    return "";
  }
  function beginRec() {
    V.chunks = []; V.voicedFrames = 0; V.rec = new MediaRecorder(V.stream, { mimeType: pickMime() });
    V.rec.ondataavailable = (e) => { if (e.data.size) V.chunks.push(e.data); };
    V.rec.onstop = onRec; V.rec.start(); V.lastVoice = performance.now();
    V.phase = "recording"; setMic("on"); status("listening…");
  }
  function endRec() { if (V.rec && V.rec.state !== "inactive") V.rec.stop(); }
  async function onRec() {
    const blob = new Blob(V.chunks, { type: V.rec.mimeType });
    if (blob.size < 1200) { V.phase = "listening"; status("listening…"); return; }
    // Guard against Whisper-family hallucination: a tap/noise blip with too little actual voice
    // gets dropped rather than sent (server ASR will otherwise invent text, sometimes non-English).
    if (V.voicedFrames < 10) { V.phase = "listening"; status("listening…"); return; }
    V.phase = "thinking"; setMic("on"); status("transcribing…");
    const fd = new FormData(); fd.append("provider", AGENT.asr); fd.append("file", blob, "utt.webm");
    let d;
    try {
      const r = await fetch(BASE + "/asr", { method: "POST", headers: keyHeaders(), body: fd });
      d = await r.json().catch(() => ({}));
      if (!r.ok && r.status === 400 && /key/i.test(d.detail || "")) { status("Add your API key (🔑)."); openKeys(); resume(); return; }
    } catch (e) { V.phase = "listening"; status("ASR error: " + e.message); return; }
    if (d.error || !d.text) { V.phase = "listening"; status(d.error ? "ASR: " + d.error : "listening…"); return; }
    if (isSelfEcho(d.text)) { V.phase = "listening"; status("(ignored echo)"); return; }
    add("user", d.text);
    await runVoicePipeline(d.text);
  }

  // voice turn: stream reply, synth each sentence as it lands, play in order, resume when drained
  async function runVoicePipeline(userText) {
    V.cancelled = false; V.answerComplete = false; V.pendingAudio = 0;
    if (!serverAsr()) stopBrowserASR();   // don't let speech recognition hear our own TTS (resume restarts it)
    V.phase = "thinking"; status("thinking…");
    const bubble = add("bot", ""); V.lastBubble = bubble;
    let spoke = false;
    const onSentence = async (sentence) => {
      if (V.cancelled) return;
      const audio = await synth(sentence.trim());
      if (!audio || V.cancelled) return;
      if (!spoke) { spoke = true; beginSpeaking(); await new Promise((r) => setTimeout(r, AGENT.buffer)); }  // pre-buffer
      enqueue(audio);
    };
    const res = await streamTurn(userText, bubble, onSentence);
    V.lastReply = res.text || "";
    if (!res.ok) { resume(); return; }
    V.answerComplete = true;
    if (!spoke) { resume(); return; }   // nothing synthesized (e.g. empty reply)
    endSpeakingIfDone();
  }

  async function synth(text) {
    try {
      const r = await fetch(BASE + "/tts", { method: "POST", headers: jsonHeaders(), body: JSON.stringify({ text, provider: AGENT.tts, voice: AGENT.voice }) });
      if (!r.ok) return null;
      return await r.arrayBuffer();
    } catch { return null; }
  }
  function beginSpeaking() {
    // playTs is set when the FIRST audio buffer actually starts (in playNext), so the grace
    // window measures real playback, not synth/decode time.
    V.phase = "speaking"; V.playTs = 0; V.bargeFrames = 0;
    highlight(V.lastBubble, true);   // light the whole reply bubble while it's being spoken
    setMic("spk"); status("speaking… (talk to interrupt)");
  }
  const highlight = (el, on) => { if (el && el.classList) el.classList.toggle("nbw-speaking", on); };
  async function enqueue(ab) {
    if (V.cancelled) return;
    V.pendingAudio++;
    let b; try { b = await V.ac.decodeAudioData(ab.slice(0)); } catch { V.pendingAudio--; return; }
    V.pendingAudio--;
    if (V.cancelled) return;
    V.queue.push(b); if (!V.playing) playNext();
  }
  function playNext() {
    if (V.cancelled) { V.queue = []; V.playing = false; return; }
    const b = V.queue.shift();
    if (!b) { V.playing = false; endSpeakingIfDone(); return; }
    V.playing = true;
    const s = V.ac.createBufferSource(); s.buffer = b; s.connect(V.ttsAn);
    s.onended = () => { V.src = null; playNext(); }; V.src = s;
    if (!V.playTs) V.playTs = performance.now();
    s.start();
  }
  // resume listening only once the whole answer is synthesized AND all audio has drained
  function endSpeakingIfDone() {
    if (V.phase === "speaking" && V.answerComplete && !V.playing && V.queue.length === 0 && V.pendingAudio === 0) resume();
  }
  function stopAudio() {
    V.cancelled = true; V.queue = []; V.pendingAudio = 0;
    document.querySelectorAll(".nbw-speaking").forEach((e) => e.classList.remove("nbw-speaking"));
    if (V.src) { try { V.src.onended = null; V.src.stop(); } catch {} V.src = null; }
    V.playing = false;
  }
  function bargeIn() {
    stopAudio();
    if (V.lastBubble) V.lastBubble.classList.add("cancelled");
    fetch(BASE + "/session/cancel_last", { method: "POST", headers: jsonHeaders(), body: JSON.stringify({ session_id: sessionId() }) }).catch(() => {});
    status("— interrupted —");
    resume();
  }
  function resume() {
    highlight(V.lastBubble, false);
    if (!V.on) { setMic(""); status(""); return; }
    V.playing = false; V.answerComplete = false; V.phase = "listening";
    V.listenGuardUntil = performance.now() + LISTEN_GUARD_MS;   // ignore the speaker's echo tail
    setMic("on"); status("listening…");
    // browser ASR was stopped during the turn; restart it once the echo tail has passed
    if (!serverAsr()) setTimeout(() => { if (V.on && V.phase === "listening") startBrowserASR(); }, LISTEN_GUARD_MS);
  }

  async function startVoice() {
    if (!hasKey() && !_isLocal) { openKeys(); return; }
    try { await ensureMic(); } catch { status("mic permission denied"); return; }
    if (V.ac.state === "suspended") await V.ac.resume();
    V.on = true; V.phase = "listening"; setMic("on"); status("calibrating mic…");
    await calibrate();
    if (!serverAsr()) startBrowserASR();   // on-device Web Speech handles transcription + endpointing
    status("listening…"); requestAnimationFrame(loop);
  }
  function stopVoice() {
    V.on = false; stopAudio(); stopBrowserASR();
    if (V.rec && V.rec.state !== "inactive") try { V.rec.stop(); } catch {}
    V.phase = "idle"; setMic(""); status("");
  }
  micBtn.addEventListener("click", () => { V.on ? stopVoice() : startVoice(); });

  // ================= API KEYS =================
  function buildKeys() {
    const k = agentKeys();
    keysEl.innerHTML = `
      <h4>Your API keys</h4>
      <p>This demo runs on your own keys — stored only in this browser, sent per-request; the server never keeps them. OpenAI is enough for the default setup.</p>
      <label>OpenAI key (required)<input id="nbwkOpenai" type="password" placeholder="sk-…" value="${k.openai || ""}"></label>
      <label>Gemini key (optional)<input id="nbwkGemini" type="password" placeholder="AIza…" value="${k.gemini || ""}"></label>
      <label>ElevenLabs key (optional)<input id="nbwkEleven" type="password" placeholder="…" value="${k.elevenlabs || ""}"></label>
      <button class="nbw-save" id="nbwkSave">Save keys</button>
      <div class="nbw-note">Get an OpenAI key at <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener">platform.openai.com ↗</a></div>`;
    keysEl.querySelector("#nbwkSave").addEventListener("click", () => {
      saveKeys({
        openai: keysEl.querySelector("#nbwkOpenai").value.trim(),
        gemini: keysEl.querySelector("#nbwkGemini").value.trim(),
        elevenlabs: keysEl.querySelector("#nbwkEleven").value.trim(),
      });
      keysEl.classList.remove("open");
      status(hasKey() ? "Keys saved." : "OpenAI key still needed.");
      if (hasKey()) input.focus();
    });
  }
  function openKeys() { setEl.classList.remove("open"); buildKeys(); keysEl.classList.add("open"); }
  panel.querySelector(".nbw-key").addEventListener("click", () => { keysEl.classList.contains("open") ? keysEl.classList.remove("open") : openKeys(); });

  // ================= SETTINGS (⚙) — pick model / ASR / TTS / voice / barge; overrides AGENT =========
  let VOICEMAP = {};
  const opt = (vals, sel, labels) => vals.map((v) => `<option value="${v}"${v === sel ? " selected" : ""}>${(labels && labels[v]) || v}</option>`).join("");
  function syncVoiceSel(want) {
    const prov = setEl.querySelector("#nbwsTts").value;
    const list = VOICEMAP[prov] || [];
    setEl.querySelector("#nbwsVoice").innerHTML = list.map((v) => `<option value="${v.id}"${v.id === want ? " selected" : ""}>${v.label}</option>`).join("");
  }
  function buildSettings() {
    setEl.innerHTML = `
      <h4>Model & voice settings</h4>
      <label>Chat model<select id="nbwsModel"></select></label>
      <div class="nbw-row">
        <label>Knowledge<select id="nbwsKnow">${opt(["rag", "ragless", "none"], AGENT.knowledge, { rag: "RAG (retrieve)", ragless: "Full context", none: "None" })}</select></label>
        <label class="nbw-tg">Tools (cart)<input type="checkbox" id="nbwsTools"${AGENT.tools_enabled ? " checked" : ""}></label>
      </div>
      <div class="nbw-row">
        <label>Speech-in (ASR)<select id="nbwsAsr">${opt(["openai", "gemini", "elevenlabs", "browser"], AGENT.asr, { openai: "OpenAI · gpt-4o-transcribe", gemini: "Gemini", elevenlabs: "ElevenLabs · scribe", browser: "Browser (on-device)" })}</select></label>
        <label>Speech-out (TTS)<select id="nbwsTts">${opt(["openai", "gemini", "elevenlabs"], AGENT.tts, { openai: "OpenAI · gpt-4o-mini-tts", gemini: "Gemini", elevenlabs: "ElevenLabs · turbo" })}</select></label>
      </div>
      <label>Voice<select id="nbwsVoice"></select></label>
      <label>Barge-in (interrupt)<select id="nbwsBarge">${opt(["off", "low", "medium", "high"], AGENT.barge, { off: "Off", low: "Low sensitivity", medium: "Medium sensitivity", high: "High sensitivity" })}</select></label>
      <button class="nbw-save" id="nbwsSave">Save settings</button>
      <div class="nbw-note">Full controls (latency, RAG viz, system prompt) live in the <a href="playground/playground.html" target="_blank" rel="noopener">Playground ↗</a></div>`;
    fetch(BASE + "/models", { headers: keyHeaders() }).then((r) => r.json()).then((d) => {
      setEl.querySelector("#nbwsModel").innerHTML = d.models.map((m) => `<option value="${m.key}"${m.key === AGENT.model_key ? " selected" : ""}>${m.label}</option>`).join("");
    }).catch(() => {});
    fetch(BASE + "/tts/voices").then((r) => r.json()).then((d) => { VOICEMAP = d.voices || {}; syncVoiceSel(AGENT.voice); }).catch(() => {});
    setEl.querySelector("#nbwsTts").addEventListener("change", () => syncVoiceSel());
    setEl.querySelector("#nbwsSave").addEventListener("click", saveSettings);
  }
  function saveSettings() {
    const val = (id) => setEl.querySelector(id).value;
    AGENT.model_key = val("#nbwsModel"); AGENT.asr = val("#nbwsAsr"); AGENT.tts = val("#nbwsTts");
    AGENT.voice = val("#nbwsVoice"); AGENT.barge = val("#nbwsBarge");
    AGENT.knowledge = val("#nbwsKnow"); AGENT.tools_enabled = setEl.querySelector("#nbwsTools").checked;
    localStorage.setItem("nimbus_widget_cfg", JSON.stringify({
      model_key: AGENT.model_key, asr: AGENT.asr, tts: AGENT.tts, voice: AGENT.voice, barge: AGENT.barge,
      knowledge: AGENT.knowledge, tools_enabled: AGENT.tools_enabled,
    }));
    setEl.classList.remove("open"); status("Settings saved.");
    if (V.on) { if (serverAsr()) stopBrowserASR(); else if (!V.sr && V.phase === "listening") startBrowserASR(); }  // apply ASR-mode switch live
  }
  function openSettings() { keysEl.classList.remove("open"); buildSettings(); setEl.classList.add("open"); }
  panel.querySelector(".nbw-gear").addEventListener("click", () => { setEl.classList.contains("open") ? setEl.classList.remove("open") : openSettings(); });
}
