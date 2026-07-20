// "Talk to Nimbus" — the finalized agent embedded on the site (Phase 12 / R14).
// Chats with the backend (tools on) and keeps the site cart (nimbus_cart) in sync both ways:
//   before a turn: push the site cart → agent (so it sees what you clicked on the site)
//   after a turn:  pull the agent cart → site + repaint the drawer (so you WATCH it change)

const BASE = (localStorage.getItem("nimbus_backend_url") || "http://localhost:8100").replace(/\/$/, "");
const CART_KEY = "nimbus_cart";
const SID_KEY = "nimbus_agent_session";

function sessionId() {
  let s = localStorage.getItem(SID_KEY);
  if (!s) { s = "site-" + Math.random().toString(36).slice(2); localStorage.setItem(SID_KEY, s); }
  return s;
}
function siteCart() { try { return JSON.parse(localStorage.getItem(CART_KEY) || "[]"); } catch { return []; } }

const STYLE = `
.nbw-btn{position:fixed;right:22px;bottom:22px;z-index:9998;width:58px;height:58px;border:0;border-radius:50%;
  background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;font-size:24px;cursor:pointer;box-shadow:0 8px 24px rgba(99,102,241,.45);transition:transform .15s}
.nbw-btn:hover{transform:scale(1.06)}
.nbw-panel{position:fixed;right:22px;bottom:92px;z-index:9999;width:370px;max-width:calc(100vw - 32px);height:540px;max-height:calc(100vh - 130px);
  background:#fff;border:1px solid #e6e8ef;border-radius:16px;box-shadow:0 24px 60px rgba(20,20,50,.22);display:none;flex-direction:column;overflow:hidden;font:14px/1.5 -apple-system,system-ui,Segoe UI,Roboto,sans-serif}
.nbw-panel.open{display:flex}
.nbw-head{background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;padding:14px 16px;display:flex;align-items:center;justify-content:space-between}
.nbw-head b{font-size:15px}.nbw-head small{opacity:.85;font-size:11.5px;display:block}
.nbw-x{background:transparent;border:0;color:#fff;font-size:20px;cursor:pointer;line-height:1}
.nbw-msgs{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px;background:#f7f8fb}
.nbw-msg{max-width:85%;padding:9px 12px;border-radius:13px;white-space:pre-wrap;word-break:break-word}
.nbw-user{align-self:flex-end;background:#6366f1;color:#fff;border-bottom-right-radius:4px}
.nbw-bot{align-self:flex-start;background:#fff;border:1px solid #e6e8ef;color:#1e2233;border-bottom-left-radius:4px}
.nbw-tool{align-self:flex-start;font-size:11px;color:#8b5cf6;background:#f2effe;border:1px solid #e6ddfb;border-radius:8px;padding:4px 9px}
.nbw-form{display:flex;gap:8px;padding:12px;border-top:1px solid #eceef4;background:#fff}
.nbw-form input{flex:1;border:1px solid #d9dce6;border-radius:9px;padding:9px 11px;font:inherit;outline:none}
.nbw-form input:focus{border-color:#6366f1}
.nbw-form button{border:0;border-radius:9px;padding:9px 15px;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;font-weight:600;cursor:pointer}
.nbw-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:2px}
.nbw-chip{border:1px solid #d9dce6;background:#fff;border-radius:999px;padding:5px 10px;font-size:12px;cursor:pointer;color:#4b5168}
.nbw-chip:hover{border-color:#6366f1;color:#6366f1}`;

export function mountWidget() {
  if (document.querySelector(".nbw-btn")) return;
  const style = document.createElement("style"); style.textContent = STYLE; document.head.append(style);

  const btn = document.createElement("button");
  btn.className = "nbw-btn"; btn.title = "Talk to Nimbus"; btn.textContent = "💬";
  const panel = document.createElement("div");
  panel.className = "nbw-panel";
  panel.innerHTML = `
    <div class="nbw-head"><div><b>Talk to Nimbus</b><small>Ask about products, pricing — or manage your cart</small></div><button class="nbw-x" aria-label="Close">×</button></div>
    <div class="nbw-msgs" id="nbwMsgs">
      <div class="nbw-bot">Hi! I can answer questions and manage your cart. Try one:</div>
      <div class="nbw-chips">
        <button class="nbw-chip">Add Nimbus CRM Professional to my cart</button>
        <button class="nbw-chip">What's my cart total?</button>
        <button class="nbw-chip">How much do I save paying annually?</button>
      </div>
    </div>
    <form class="nbw-form" id="nbwForm"><input id="nbwInput" placeholder="Type a message…" autocomplete="off" /><button type="submit">Send</button></form>`;
  document.body.append(btn, panel);

  const msgs = panel.querySelector("#nbwMsgs");
  btn.addEventListener("click", () => { panel.classList.toggle("open"); if (panel.classList.contains("open")) panel.querySelector("#nbwInput").focus(); });
  panel.querySelector(".nbw-x").addEventListener("click", () => panel.classList.remove("open"));
  panel.querySelectorAll(".nbw-chip").forEach((c) => c.addEventListener("click", () => send(c.textContent)));
  panel.querySelector("#nbwForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const v = panel.querySelector("#nbwInput").value.trim();
    if (!v) return; panel.querySelector("#nbwInput").value = ""; send(v);
  });

  function add(kind, text) {
    const d = document.createElement("div"); d.className = "nbw-msg nbw-" + kind; d.textContent = text;
    msgs.append(d); msgs.scrollTop = msgs.scrollHeight; return d;
  }

  async function syncSiteToAgent() {
    const items = siteCart().map((i) => ({ product_id: i.product_id, product_name: i.product_name, tier: i.tier, seats: i.seats }));
    try { await fetch(BASE + "/cart/set", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: sessionId(), items }) }); } catch {}
  }
  async function syncAgentToSite() {
    try {
      const d = await (await fetch(BASE + "/cart?session_id=" + encodeURIComponent(sessionId()))).json();
      const items = d.items.map((i) => ({ product_id: i.product_id, product_name: i.product_name, tier: i.tier, seats: i.seats, price: i.price_monthly }));
      localStorage.setItem(CART_KEY, JSON.stringify(items));
      if (window.__nimbusCart) { window.__nimbusCart.refresh(); if (items.length) window.__nimbusCart.open(); }
    } catch {}
  }

  async function send(message) {
    add("user", message);
    const pending = add("bot", "…");
    try {
      await syncSiteToAgent();
      const r = await fetch(BASE + "/chat", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId(), message, use_context: true, use_rag: false,
          tools_enabled: true, response_length: "low", verbatim_turns: 8 }) });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) { pending.textContent = data.detail || "Something went wrong."; return; }
      pending.textContent = data.text;
      (data.meta && data.meta.tool_calls || []).forEach((t) => add("tool", "🔧 " + t.name));
      await syncAgentToSite();
    } catch (e) {
      pending.textContent = "Can't reach the Nimbus agent. Is the backend running?";
    }
  }
}
