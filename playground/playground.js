// Nimbus playground — Phase 2 (batch RAGless/None chat). Kept intentionally small;
// new controls are added as each phase lands.

const LS_KEYS = "nimbus_pg_keys";
const LS_BASE = "nimbus_backend_url"; // shared with runtime-config.js
const CFG_KEY = "nimbus_agent_config"; // shared config the landing widget will read (Phase 12)
const DEFAULT_BASE = (window.NIMBUS_CONFIG && window.NIMBUS_CONFIG.defaultBackendUrl) || "http://localhost:8100";

const $ = (id) => document.getElementById(id);
const state = {
  base: localStorage.getItem(LS_BASE) || DEFAULT_BASE,
  keys: load(LS_KEYS),
  length: "medium",
  knowledge: "ragless",
  mode: "stream",
  session: "pg-" + Math.random().toString(36).slice(2),
  busy: false,
};
function load(k) { try { return JSON.parse(localStorage.getItem(k) || "{}"); } catch { return {}; } }
function keyHeaders() {
  const h = {};
  if (state.keys.openai) h["X-OpenAI-Key"] = state.keys.openai;
  if (state.keys.gemini) h["X-Gemini-Key"] = state.keys.gemini;
  if (state.keys.elevenlabs) h["X-ElevenLabs-Key"] = state.keys.elevenlabs;
  return h;
}
function authHeaders() {
  return { "Content-Type": "application/json", ...keyHeaders() };
}

// ---- ASR (voice input, Phase 8) ----
let asrRec = false, asrMedia = null, asrChunks = [], asrRecognizer = null, asrT0 = 0;
function setMic(on) {
  asrRec = on;
  const b = $("micBtn");
  b.classList.toggle("rec", on);
  b.textContent = on ? "⏹" : "🎤";
}
function asrHint(msg) { const el = $("asrHint"); el.hidden = false; el.textContent = msg; }
async function toggleMic() {
  if (asrRec) { stopMic(); return; }
  asrT0 = performance.now();
  const p = $("asrProvider").value;
  if (p === "browser") return browserASR();
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    asrMedia = new MediaRecorder(stream);
    asrChunks = [];
    asrMedia.ondataavailable = (e) => e.data.size && asrChunks.push(e.data);
    asrMedia.onstop = () => { stream.getTracks().forEach((t) => t.stop()); sendAudio(new Blob(asrChunks, { type: asrMedia.mimeType })); };
    asrMedia.start();
    setMic(true); asrHint("🎤 recording… click again to stop");
  } catch { asrHint("🎤 mic blocked — allow microphone access"); }
}
function stopMic() {
  setMic(false);
  if (asrRecognizer) { asrRecognizer.stop(); asrRecognizer = null; return; }
  if (asrMedia && asrMedia.state !== "inactive") asrMedia.stop();
}
async function sendAudio(blob) {
  $("micBtn").textContent = "…"; asrHint("transcribing…");
  const fd = new FormData();
  fd.append("file", blob, "audio.webm");
  fd.append("provider", $("asrProvider").value);
  try {
    const r = await fetch(state.base + "/asr", { method: "POST", headers: keyHeaders(), body: fd });
    const d = await r.json();
    if (!r.ok) { asrHint("ASR failed: " + (d.detail || r.status)); return; }
    $("input").value = d.text; $("input").focus();
    asrHint(`🎤 ${d.provider} · ${Math.round(d.asr_ms)} ms`);
  } catch (e) { asrHint("ASR failed: " + e.message); }
  finally { $("micBtn").textContent = "🎤"; }
}
function browserASR() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { asrHint("Web Speech not supported in this browser (try Chrome)"); return; }
  asrRecognizer = new SR();
  asrRecognizer.lang = "en-US"; asrRecognizer.interimResults = false; asrRecognizer.maxAlternatives = 1;
  asrRecognizer.onresult = (e) => { $("input").value = e.results[0][0].transcript; $("input").focus(); asrHint(`🎤 browser · ${Math.round(performance.now() - asrT0)} ms`); };
  asrRecognizer.onerror = (e) => asrHint("speech error: " + e.error);
  asrRecognizer.onend = () => setMic(false);
  asrRecognizer.start(); setMic(true); asrHint("🎤 listening… speak now");
}

// ---- chat ----
function addMsg(kind, text) {
  const empty = $("empty");
  if (empty) empty.remove();
  const div = document.createElement("div");
  div.className = "msg " + kind;
  div.textContent = text;
  $("messages").append(div);
  $("messages").scrollTop = $("messages").scrollHeight;
  return div;
}
function setBusy(b) {
  state.busy = b;
  $("input").disabled = b;
  $("composer").querySelector("button").disabled = b;
  if (!b) $("input").focus();
}
function payload(message) {
  return {
    session_id: state.session, message, mode: "batch",
    model_key: $("model").value, response_length: state.length,
    use_context: state.knowledge === "ragless", use_rag: state.knowledge === "rag",
    top_k: Number($("topk").value), rerank: $("rerank").checked,
    verbatim_turns: Number($("verbatim").value),
    tools_enabled: $("toolsOn").checked, enabled_tools: enabledToolNames(),
    temperature: Number($("temp").value) / 10,
    system_prompt: $("sysPrompt").value.trim() || null,
  };
}
function enabledToolNames() {
  return [...document.querySelectorAll("#toolList input:checked")].map((c) => c.value);
}

async function compare() {
  const q = $("input").value.trim() || "What is the refund policy?";
  $("cmpTitle").textContent = "RAG vs RAGless";
  $("cmpQ").textContent = `“${q}”`;
  $("cmpBody").innerHTML = "<p class='stat-empty'>running both…</p>";
  $("cmpDlg").showModal();
  const base = { session_id: null, message: q, mode: "batch", model_key: $("model").value,
    response_length: state.length, temperature: Number($("temp").value) / 10, system_prompt: null,
    top_k: Number($("topk").value) };  // session_id null → compare doesn't pollute the conversation
  const run = async (cfg) => {
    const r = await fetch(state.base + "/chat", { method: "POST", headers: authHeaders(), body: JSON.stringify({ ...base, ...cfg }) });
    const d = await r.json(); if (!r.ok) throw new Error(d.detail || "failed"); return d;
  };
  try {
    const [rag, rl] = await Promise.all([
      run({ use_rag: true, use_context: false, rerank: $("rerank").checked }),
      run({ use_rag: false, use_context: true }),
    ]);
    const m = (d, k) => d.meta[k] != null ? d.meta[k].toLocaleString() : "—";
    const L = (d, k) => Math.round(d.latency[k] || 0);
    const row = (label, a, b) => `<tr><td>${label}</td><td>${a}</td><td>${b}</td></tr>`;
    $("cmpBody").innerHTML =
      `<table class="cmp"><thead><tr><th></th><th>RAG</th><th>RAGless</th></tr></thead><tbody>` +
      row("Context tokens", m(rag, "context_tokens"), m(rl, "context_tokens")) +
      row("Prompt tokens", m(rag, "prompt_tokens"), m(rl, "prompt_tokens")) +
      row("RAG ms", L(rag, "rag_ms"), "—") +
      row("LLM ms", L(rag, "llm_total_ms"), L(rl, "llm_total_ms")) +
      row("Total ms", L(rag, "total_ms"), L(rl, "total_ms")) +
      `</tbody></table>` +
      `<p class="hint" style="margin-top:12px">RAG sends a fraction of the tokens (cheaper, scales past the context window). Total latency is similar here because RAG's query-embed offsets the smaller-prompt LLM win — and OpenAI caches the big RAGless prompt.</p>`;
  } catch (e) { $("cmpBody").innerHTML = `<p style="color:var(--bad)">${e.message}</p>`; }
}

async function compareModes() {
  const q = $("input").value.trim() || "What is the refund policy?";
  $("cmpTitle").textContent = "Batch vs Streaming";
  $("cmpQ").textContent = `“${q}”`;
  $("cmpBody").innerHTML = "<p class='stat-empty'>running both…</p>";
  $("cmpDlg").showModal();
  const body = { ...payload(q), session_id: null, tools_enabled: false };  // isolate; streaming is text-only
  try {
    const bd = await (await fetch(state.base + "/chat", { method: "POST", headers: authHeaders(), body: JSON.stringify(body) })).json();
    const stext = await (await fetch(state.base + "/chat/stream", { method: "POST", headers: authHeaders(), body: JSON.stringify(body) })).text();
    const done = stext.split("\n\n").map((p) => p.split("\n").find((l) => l.startsWith("data: "))).filter(Boolean)
      .map((l) => { try { return JSON.parse(l.slice(6)); } catch { return null; } }).filter(Boolean).find((e) => e.type === "done");
    const L = (o, k) => (o && o.latency && o.latency[k]) ? Math.round(o.latency[k]) + " ms" : "—";
    const row = (label, a, b) => `<tr><td>${label}</td><td>${a}</td><td>${b}</td></tr>`;
    $("cmpBody").innerHTML =
      `<table class="cmp"><thead><tr><th></th><th>Batch</th><th>Stream</th></tr></thead><tbody>` +
      row("Time to first token", "— (waits for all)", L(done, "llm_ttft_ms")) +
      row("LLM ms", L(bd, "llm_total_ms"), L(done, "llm_total_ms")) +
      row("Total ms", L(bd, "total_ms"), L(done, "total_ms")) +
      `</tbody></table>` +
      `<p class="hint" style="margin-top:12px">Total time is similar, but streaming shows the first token after ~TTFT ms — so it <b>feels</b> far faster. Batch makes you wait for the whole answer.</p>`;
  } catch (e) { $("cmpBody").innerHTML = `<p style="color:var(--bad)">${e.message}</p>`; }
}
function renderSources(pending, data) {
  if (data.meta && data.meta.rag && data.meta.rag.chunks && data.meta.rag.chunks.length) {
    const srcs = [...new Set(data.meta.rag.chunks.map((c) => c.doc))];
    const f = document.createElement("div");
    f.className = "msg-src";
    f.textContent = "Sources: " + srcs.join(" · ");
    pending.appendChild(f);
  }
}

async function batchTurn(message, pending) {
  const r = await fetch(state.base + "/chat", { method: "POST", headers: authHeaders(), body: JSON.stringify(payload(message)) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) { pending.className = "msg err"; pending.textContent = data.detail || `Request failed (${r.status})`; return; }
  pending.className = "msg bot";
  pending.textContent = data.text;
  renderSources(pending, data);
  renderTurn(data);
}

async function streamTurn(message, pending) {
  pending.className = "msg bot";
  pending.textContent = "";
  const r = await fetch(state.base + "/chat/stream", { method: "POST", headers: authHeaders(), body: JSON.stringify(payload(message)) });
  if (!r.ok || !r.body) { pending.className = "msg err"; pending.textContent = "Stream failed (" + r.status + ")"; return; }
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "", acc = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop();
    for (const part of parts) {
      const line = part.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      let ev; try { ev = JSON.parse(line.slice(6)); } catch { continue; }
      if (ev.type === "delta") { acc += ev.text; pending.textContent = acc; $("messages").scrollTop = $("messages").scrollHeight; }
      else if (ev.type === "error") { pending.className = "msg err"; pending.textContent = ev.error; }
      else if (ev.type === "done") { renderSources(pending, ev); renderTurn(ev); }
    }
  }
}

async function send(message) {
  addMsg("user", message);
  const pending = addMsg("bot pending", "…");
  setBusy(true);
  try {
    // tools run in batch only, so a tools-on turn falls back to batch even in streaming mode
    if (state.mode === "stream" && !$("toolsOn").checked) await streamTurn(message, pending);
    else await batchTurn(message, pending);
  } catch (e) {
    pending.className = "msg err";
    pending.textContent = `Can't reach the backend at ${state.base}. Is it running? (${e.message})`;
  } finally {
    setBusy(false);
    refreshCart();
  }
}

// ---- right rail: this turn ----
const STAGES = { asr_ms: "ASR", rag_ms: "RAG", llm_total_ms: "LLM", tool_ms: "Tools", tts_ms: "TTS", buffer_ms: "Buffer" };
function renderTurn(data) {
  const lat = data.latency || {}, meta = data.meta || {};
  const present = Object.entries(STAGES).filter(([k]) => (lat[k] || 0) > 0);
  const max = Math.max(1, ...present.map(([k]) => lat[k]));
  const stages = present.map(([k, label]) =>
    `<div class="stage"><span class="lbl">${label}</span><div class="bar"><i style="width:${(lat[k] / max) * 100}%"></i></div><span class="v">${Math.round(lat[k])}ms</span></div>`).join("");
  const kv = (k, v) => v == null ? "" : `<div class="kv"><span class="k">${k}</span><span class="v">${v}</span></div>`;
  const n = (x) => x == null ? null : x.toLocaleString();
  let chunks = "";
  if (meta.rag && meta.rag.chunks) {
    const rows = meta.rag.chunks.map((c) =>
      `<div class="chunk"><span class="chunk-doc">${c.doc}</span><span class="chunk-score">${c.score.toFixed(3)}</span><div class="chunk-head">${c.heading}</div></div>`).join("");
    chunks = `<div class="chunks-head">Retrieved ${meta.rag.chunks.length} chunks (top-${meta.rag.k})</div>${rows}`;
  }
  let toolsHtml = "";
  if (meta.tool_calls && meta.tool_calls.length) {
    const rows = meta.tool_calls.map((t) =>
      `<div class="chunk"><span class="chunk-doc">${t.name}</span><span class="chunk-score">${Math.round(t.ms)}ms</span><div class="chunk-head">${esc(JSON.stringify(t.args || {}))}</div></div>`).join("");
    toolsHtml = `<div class="chunks-head">Tools called (${meta.tool_calls.length})</div>${rows}`;
  }
  $("turn").innerHTML =
    `<div class="total"><span class="n grad">${Math.round(lat.total_ms)}</span><small>ms total</small></div>` +
    stages +
    `<div style="margin-top:14px"></div>` +
    kv("Knowledge", meta.knowledge) +
    kv("Mode", meta.mode) +
    kv("TTFT", meta.mode === "stream" ? Math.round(lat.llm_ttft_ms || 0) + " ms" : "— (batch)") +
    kv("LLM ms", Math.round(lat.llm_total_ms || 0)) +
    kv("Context tokens", meta.knowledge === "none" ? "0" : n(meta.context_tokens)) +
    kv("Prompt tokens", n(meta.prompt_tokens)) +
    kv("Output tokens", n(meta.completion_tokens)) +
    kv("Model", meta.model) +
    kv("Memory", (meta.verbatim_messages || 0) + " verbatim" + (meta.summary_used ? " + summary" : "")) +
    toolsHtml + chunks;
}
function esc(s) { return String(s).replace(/[<>&]/g, (m) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[m])); }

async function loadTools() {
  try {
    const d = await (await fetch(state.base + "/tools")).json();
    $("toolList").innerHTML = d.tools.map((t) =>
      `<label class="tool-item"><input type="checkbox" value="${t.name}" checked /><span><b>${t.name}</b> — ${t.description}</span></label>`).join("");
  } catch { /* ignore */ }
}
async function refreshCart() {
  try {
    const d = await (await fetch(state.base + "/cart?session_id=" + encodeURIComponent(state.session))).json();
    if (!d.items.length) { $("cart") && ($("cart").innerHTML = ""); return; }
    const el = $("cart"); if (!el) return;
    el.innerHTML = `<div class="chunks-head">Cart · $${d.monthly_total}/mo</div>` +
      d.items.map((i) => `<div class="chunk"><span class="chunk-doc">${i.product_name}</span><span class="chunk-score">$${i.price_monthly * i.seats}/mo</span><div class="chunk-head">${i.tier} × ${i.seats}</div></div>`).join("");
  } catch { /* ignore */ }
}

// ---- backend status ----
async function refreshHealth() {
  try {
    const d = await (await fetch(state.base + "/health", { headers: authHeaders() })).json();
    state.requireKeys = !!d.require_user_keys;
    const needKey = d.require_user_keys && !state.keys.openai;
    $("health").className = needKey ? "health bad" : "health ok";
    $("healthText").textContent = needKey ? "add your OpenAI key →" : "backend online";
    $("kbSub").textContent = d.corpus.context_built
      ? `${d.corpus.doc_count} docs · context.md ready`
      : "not built — run `make scrape`";
  } catch {
    $("health").className = "health bad";
    $("healthText").textContent = "backend offline";
    $("kbSub").textContent = "backend unreachable";
  }
}
async function loadModels() {
  try {
    const d = await (await fetch(state.base + "/models", { headers: authHeaders() })).json();
    $("model").innerHTML = "";
    for (const m of d.models) {
      const o = document.createElement("option");
      o.value = m.key; o.textContent = m.label + (m.available ? "" : " (no key)"); o.disabled = !m.available;
      $("model").append(o);
    }
    const first = d.models.find((m) => m.available);
    if (first) $("model").value = first.key;
  } catch { /* health already shows the problem */ }
}
async function refreshRagStatus() {
  const el = $("ragStatus");
  try {
    const d = await (await fetch(state.base + "/rag/status")).json();
    el.textContent = d.built
      ? `index: ${d.chunks} chunks · ${d.model}`
      : "index not built — builds automatically on first RAG query";
  } catch { el.textContent = "index status unavailable"; }
}

// ---- context inspector ----
async function inspect() {
  $("ctxTot").textContent = "counting…";
  $("ctxBody").innerHTML = "";
  $("ctxDlg").showModal();
  try {
    const r = await fetch(state.base + "/inspect", { method: "POST", headers: authHeaders(), body: JSON.stringify(payload($("input").value.trim() || "(preview)")) });
    const d = await r.json();
    if (!r.ok) { $("ctxTot").textContent = d.detail || "failed"; return; }
    $("ctxTot").innerHTML = `<b>${d.total_tokens.toLocaleString()}</b> tokens · ${d.total_chars.toLocaleString()} chars`;
    for (const m of d.messages) {
      const el = document.createElement("div");
      el.className = "ctx-msg";
      el.innerHTML = `<div class="h"><span class="role">${m.role}</span><span>${m.tokens} tokens · ${m.chars} chars</span></div>`;
      const pre = document.createElement("pre"); pre.textContent = m.content; el.append(pre);
      $("ctxBody").append(el);
    }
  } catch (e) { $("ctxTot").textContent = "failed: " + e.message; }
}

// ---- config persistence (for the Phase 12 widget) ----
function persist() {
  localStorage.setItem(CFG_KEY, JSON.stringify({
    model_key: $("model").value, response_length: state.length, knowledge: state.knowledge,
    temperature: Number($("temp").value) / 10, system_prompt: $("sysPrompt").value.trim() || null,
  }));
}

// ---- wiring ----
function seg(id, onPick) {
  $(id).querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    if (b.disabled) return;
    $(id).querySelectorAll("button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active"); onPick(b.dataset.v); persist();
  }));
}
function initKeys() {
  const dlg = $("keysDlg");
  $("health").style.cursor = "pointer";
  $("health").addEventListener("click", () => $("keysBtn").click());
  $("keysBtn").addEventListener("click", () => {
    $("k_openai").value = state.keys.openai || "";
    $("k_gemini").value = state.keys.gemini || "";
    $("k_elevenlabs").value = state.keys.elevenlabs || "";
    $("apiBase").value = state.base;
    dlg.showModal();
  });
  dlg.addEventListener("close", () => {
    if (dlg.returnValue !== "save") return;
    state.keys = { openai: $("k_openai").value.trim(), gemini: $("k_gemini").value.trim(), elevenlabs: $("k_elevenlabs").value.trim() };
    localStorage.setItem(LS_KEYS, JSON.stringify(state.keys));
    state.base = $("apiBase").value.trim() || DEFAULT_BASE;
    localStorage.setItem(LS_BASE, state.base);
    refreshHealth(); loadModels();
  });
}
function init() {
  seg("length", (v) => { state.length = v; });
  seg("knowledge", (v) => {
    state.knowledge = v;
    $("ragOpts").hidden = v !== "rag";
    $("ctxHint").textContent = {
      ragless: "RAGless injects the full context.md into the prompt (no retrieval).",
      rag: "RAG retrieves only the top-k relevant chunks — smaller prompt + retrieval latency.",
      none: "None: no Nimbus facts injected — the model answers from general knowledge only.",
    }[v];
    if (v === "rag") refreshRagStatus();
  });
  $("topk").addEventListener("input", (e) => { $("topkVal").textContent = e.target.value; persist(); });
  $("temp").addEventListener("input", (e) => { $("tempVal").textContent = (e.target.value / 10).toFixed(1); persist(); });
  $("verbatim").addEventListener("input", (e) => { $("verbatimVal").textContent = e.target.value; persist(); });
  seg("mode", (v) => { state.mode = v; });
  $("toolsOn").addEventListener("change", (e) => { $("toolsBox").hidden = !e.target.checked; persist(); });
  $("toolAll").addEventListener("click", () => document.querySelectorAll("#toolList input").forEach((c) => (c.checked = true)));
  $("toolNone").addEventListener("click", () => document.querySelectorAll("#toolList input").forEach((c) => (c.checked = false)));
  $("sysPrompt").addEventListener("input", persist);
  $("model").addEventListener("change", persist);
  $("inspectBtn").addEventListener("click", inspect);
  $("ctxClose").addEventListener("click", () => $("ctxDlg").close());
  $("compareBtn").addEventListener("click", compare);
  $("cmpModesBtn").addEventListener("click", compareModes);
  $("micBtn").addEventListener("click", toggleMic);
  $("cmpClose").addEventListener("click", () => $("cmpDlg").close());
  $("topk").addEventListener("input", persist);
  $("resetBtn").addEventListener("click", async () => {
    try { await fetch(state.base + "/session/reset", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: state.session }) }); } catch {}
    state.session = "pg-" + Math.random().toString(36).slice(2);
    $("messages").innerHTML = '<div class="empty" id="empty"><h3>Conversation reset</h3><p>Ask another question.</p></div>';
    $("turn").innerHTML = '<p class="stat-empty">Send a message to see latency &amp; tokens.</p>';
  });
  $("composer").addEventListener("submit", (e) => {
    e.preventDefault();
    const v = $("input").value.trim();
    if (!v || state.busy) return;
    $("input").value = ""; send(v);
  });
  document.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => {
    if (state.busy) return;
    send(c.textContent);
  }));
  initKeys();
  refreshHealth(); loadModels(); loadTools(); persist();
}
init();
