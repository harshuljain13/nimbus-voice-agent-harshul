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
  session: "pg-" + Math.random().toString(36).slice(2),
  busy: false,
};
function load(k) { try { return JSON.parse(localStorage.getItem(k) || "{}"); } catch { return {}; } }
function authHeaders() {
  const h = { "Content-Type": "application/json" };
  if (state.keys.openai) h["X-OpenAI-Key"] = state.keys.openai;
  return h;
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
    use_context: state.knowledge === "ragless", use_rag: false,
    temperature: Number($("temp").value) / 10,
    system_prompt: $("sysPrompt").value.trim() || null,
  };
}
async function send(message) {
  addMsg("user", message);
  const pending = addMsg("bot pending", "…");
  setBusy(true);
  try {
    const r = await fetch(state.base + "/chat", { method: "POST", headers: authHeaders(), body: JSON.stringify(payload(message)) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) { pending.className = "msg err"; pending.textContent = data.detail || `Request failed (${r.status})`; return; }
    pending.className = "msg bot";
    pending.textContent = data.text;
    renderTurn(data);
  } catch (e) {
    pending.className = "msg err";
    pending.textContent = `Can't reach the backend at ${state.base}. Is it running? (${e.message})`;
  } finally {
    setBusy(false);
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
  $("turn").innerHTML =
    `<div class="total"><span class="n grad">${Math.round(lat.total_ms)}</span><small>ms total</small></div>` +
    stages +
    `<div style="margin-top:14px"></div>` +
    kv("Knowledge", meta.knowledge) +
    kv("Context tokens", meta.knowledge === "ragless" ? n(meta.context_tokens) : "0") +
    kv("Prompt tokens", n(meta.prompt_tokens)) +
    kv("Output tokens", n(meta.completion_tokens)) +
    kv("Model", meta.model);
}

// ---- backend status ----
async function refreshHealth() {
  try {
    const d = await (await fetch(state.base + "/health")).json();
    $("health").className = "health ok";
    $("healthText").textContent = "backend online";
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
    const d = await (await fetch(state.base + "/models")).json();
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
  $("keysBtn").addEventListener("click", () => {
    $("k_openai").value = state.keys.openai || "";
    $("apiBase").value = state.base;
    dlg.showModal();
  });
  dlg.addEventListener("close", () => {
    if (dlg.returnValue !== "save") return;
    state.keys = { openai: $("k_openai").value.trim() };
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
    $("ctxHint").textContent = v === "ragless"
      ? "RAGless injects the full context.md into the prompt (no retrieval yet)."
      : "None: no Nimbus facts injected — the model answers from general knowledge only.";
  });
  $("temp").addEventListener("input", (e) => { $("tempVal").textContent = (e.target.value / 10).toFixed(1); persist(); });
  $("sysPrompt").addEventListener("input", persist);
  $("model").addEventListener("change", persist);
  $("inspectBtn").addEventListener("click", inspect);
  $("ctxClose").addEventListener("click", () => $("ctxDlg").close());
  $("resetBtn").addEventListener("click", () => {
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
  refreshHealth(); loadModels(); persist();
}
init();
