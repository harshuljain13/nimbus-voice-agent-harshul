// RAG vector visualization: scatter of all chunk embeddings (PCA→2D, KMeans colors),
// with a query overlay highlighting the retrieved chunks. Matches playground.css tokens.

const LS_KEYS = "nimbus_pg_keys";
const LS_BASE = "nimbus_backend_url";
const BASE = localStorage.getItem(LS_BASE) || (window.NIMBUS_CONFIG && window.NIMBUS_CONFIG.defaultBackendUrl) || "http://localhost:8100";

const PALETTE = ["#7c8cff", "#a78bfa", "#34d399", "#fbbf24", "#f87171", "#22d3ee", "#f472b6", "#a3e635"];
const QCOLOR = "#fbbf24";
const $ = (id) => document.getElementById(id);
const view = { points: [], bounds: null, retrieved: new Set(), queryPoint: null, dpr: 1, labels: [] };

function authHeaders() {
  const h = { "Content-Type": "application/json" };
  let keys = {};
  try { keys = JSON.parse(localStorage.getItem(LS_KEYS) || "{}"); } catch {}
  if (keys.openai) h["X-OpenAI-Key"] = keys.openai;
  return h;
}
function escapeHtml(s) { return s.replace(/[<>&]/g, (m) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[m])); }

function computeBounds(pts) {
  const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y), pad = 0.08;
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const dx = (maxX - minX) || 1, dy = (maxY - minY) || 1;
  return { minX: minX - dx * pad, maxX: maxX + dx * pad, minY: minY - dy * pad, maxY: maxY + dy * pad };
}
function sizeCanvas() {
  const c = $("plot");
  view.dpr = window.devicePixelRatio || 1;
  c.width = c.clientWidth * view.dpr; c.height = c.clientHeight * view.dpr;
}
function toPx(p) {
  const c = $("plot"), b = view.bounds;
  return [((p.x - b.minX) / (b.maxX - b.minX)) * c.width, (1 - (p.y - b.minY) / (b.maxY - b.minY)) * c.height];
}

function draw() {
  const c = $("plot"), ctx = c.getContext("2d");
  ctx.clearRect(0, 0, c.width, c.height);
  if (!view.bounds) return;
  const r = 3 * view.dpr;
  for (const p of view.points) {
    const [x, y] = toPx(p), hit = view.retrieved.has(p.id);
    ctx.beginPath(); ctx.arc(x, y, hit ? r * 2.2 : r, 0, Math.PI * 2);
    ctx.fillStyle = PALETTE[p.cluster % PALETTE.length];
    ctx.globalAlpha = hit ? 1 : (view.retrieved.size ? 0.25 : 0.75);
    ctx.fill();
    if (hit) { ctx.globalAlpha = 1; ctx.lineWidth = 2 * view.dpr; ctx.strokeStyle = "#fff"; ctx.stroke(); }
  }
  ctx.globalAlpha = 1;
  if (view.queryPoint) {
    const [qx, qy] = toPx(view.queryPoint);
    view.points.filter((p) => view.retrieved.has(p.id)).forEach((p, i) => {
      const [x, y] = toPx(p);
      ctx.beginPath(); ctx.moveTo(qx, qy); ctx.lineTo(x, y);
      ctx.strokeStyle = QCOLOR; ctx.globalAlpha = 0.85; ctx.lineWidth = 2 * view.dpr; ctx.stroke();
      ctx.globalAlpha = 1;
      const bx = qx + (x - qx) * 0.86, by = qy + (y - qy) * 0.86;
      ctx.fillStyle = QCOLOR; ctx.beginPath(); ctx.arc(bx, by, 8 * view.dpr, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "#0b0e14"; ctx.font = `${10 * view.dpr}px system-ui`;
      ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(String(i + 1), bx, by);
    });
    ctx.save(); ctx.translate(qx, qy); ctx.rotate(Math.PI / 4);
    const s = 8 * view.dpr;
    ctx.fillStyle = "#fff"; ctx.strokeStyle = QCOLOR; ctx.lineWidth = 2 * view.dpr;
    ctx.fillRect(-s, -s, s * 2, s * 2); ctx.strokeRect(-s, -s, s * 2, s * 2); ctx.restore();
  }
}

async function loadViz() {
  try {
    const r = await fetch(BASE + "/rag/visualization");
    const d = await r.json();
    if (!r.ok) { $("ragInfo").textContent = "index not built"; $("buildHint").textContent = d.detail || "POST /rag/build"; return; }
    view.points = d.points; view.labels = d.cluster_labels || []; view.bounds = computeBounds(d.points);
    $("ragInfo").textContent = `${d.points.length} chunks · ${d.model} (${d.dim}-d)`;
    sizeCanvas(); draw(); renderLegend(d.clusters);
  } catch (e) { $("ragInfo").textContent = "backend unreachable"; }
}

function renderLegend(k) {
  $("legend").innerHTML = "";
  for (let i = 0; i < k; i++) {
    const el = document.createElement("span"); el.className = "lg";
    el.innerHTML = `<span class="dot" style="background:${PALETTE[i % PALETTE.length]}"></span>${escapeHtml(view.labels[i] || "cluster " + i)}`;
    $("legend").append(el);
  }
  const q = document.createElement("span"); q.className = "lg";
  q.innerHTML = `<span class="dot" style="background:#fff;border-radius:2px"></span>query`;
  $("legend").append(q);
}

async function runQuery() {
  const q = $("q").value.trim();
  if (!q) return;
  $("run").disabled = true; $("results").innerHTML = "<em>retrieving…</em>";
  try {
    const r = await fetch(BASE + "/rag/query", { method: "POST", headers: authHeaders(),
      body: JSON.stringify({ query: q, k: Number($("topk").value), rerank: $("rerank").checked }) });
    const d = await r.json();
    if (!r.ok) { $("results").innerHTML = `<span style="color:var(--bad)">${d.detail || "query failed"}</span>`; return; }
    view.retrieved = new Set(d.retrieved_ids); view.queryPoint = d.query_point; draw();
    const L = d.latency;
    $("latency").innerHTML =
      `<div>embed <b>${Math.round(L.embed_ms)}ms</b></div><div>search <b>${Math.round(L.search_ms)}ms</b></div>` +
      `<div>rerank <b>${Math.round(L.rerank_ms)}ms</b></div><div>RAG total <b>${Math.round(L.rag_ms)}ms</b></div>`;
    $("results").innerHTML = d.results.map((c) =>
      `<div class="rc"><div class="rh"><span class="src">${c.doc} / ${c.heading}</span><span class="sc">${c.score.toFixed(3)}</span></div><div class="tx">${escapeHtml(c.text.slice(0, 220))}</div></div>`).join("");
  } catch (e) { $("results").innerHTML = `<span style="color:var(--bad)">query failed: ${e.message}</span>`; }
  finally { $("run").disabled = false; }
}

async function rebuild() {
  $("buildHint").textContent = "building index (embedding all chunks)…"; $("buildBtn").disabled = true;
  try {
    const r = await fetch(BASE + "/rag/build", { method: "POST", headers: authHeaders(), body: "{}" });
    const d = await r.json();
    $("buildHint").textContent = r.ok ? `built ${d.chunks} chunks · ${d.model} (${d.dim}-d)` : (d.detail || "build failed");
    view.retrieved = new Set(); view.queryPoint = null; await loadViz();
  } catch (e) { $("buildHint").textContent = "build failed: " + e.message; }
  finally { $("buildBtn").disabled = false; }
}

function nearestPoint(e) {
  const c = $("plot"), rect = c.getBoundingClientRect();
  const mx = (e.clientX - rect.left) * view.dpr, my = (e.clientY - rect.top) * view.dpr;
  let best = null, bd = 14 * view.dpr;
  for (const p of view.points) { const [x, y] = toPx(p); const dist = Math.hypot(x - mx, y - my); if (dist < bd) { bd = dist; best = p; } }
  return best;
}
function showHover(p) {
  const color = PALETTE[p.cluster % PALETTE.length], label = view.labels[p.cluster] || `cluster ${p.cluster}`;
  $("hover").innerHTML =
    `<div class="hh"><span class="src">${escapeHtml(p.doc)} / ${escapeHtml(p.heading)}</span><span class="clab" style="background:${color}">${escapeHtml(label)}</span></div>` +
    `<div class="body">${escapeHtml(p.text)}</div>`;
}

$("plot").addEventListener("mousemove", (e) => {
  if (!view.bounds) return;
  const p = nearestPoint(e); $("plot").style.cursor = p ? "pointer" : "crosshair"; if (p) showHover(p);
});
$("run").addEventListener("click", runQuery);
$("q").addEventListener("keydown", (e) => { if (e.key === "Enter") runQuery(); });
$("buildBtn").addEventListener("click", rebuild);
window.addEventListener("resize", () => { sizeCanvas(); draw(); });
loadViz();
