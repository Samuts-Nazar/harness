"use strict";
const $ = (id) => document.getElementById(id);
const feed = $("feed");
let tag = "", lastSeq = 0, es = null, turnEls = [], cur = null, busy = false;

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function add(node, tracked = true) {
  const atBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 80;
  feed.appendChild(node);
  if (tracked) turnEls.push(node);
  if (atBottom) feed.scrollTop = feed.scrollHeight;
  return node;
}
function addWord(block, w) {
  const atBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 80;
  const s = el("span", "w", (block.querySelector(".w") ? " " : "") + w);
  block.appendChild(s);
  if (atBottom) feed.scrollTop = feed.scrollHeight;
}
function npcBlock(who, name, text, cut) {
  const b = el("p", "npc"); b.dataset.who = who;
  b.appendChild(el("span", "who", name));
  if (text) b.appendChild(el("span", "w", text));
  if (cut) b.classList.add("cut");
  return b;
}

function setBusy(on, phase) {
  busy = on;
  $("dockBusy").hidden = !on;
  $("composer").hidden = on;
  const talk = phase === "narrating" || phase === "speaking";
  $("btnInterrupt").hidden = !talk;
  $("busyText").textContent = talk ? "" : "Світ думає…";
  $("busyText").hidden = talk;
}
function setPanel(p) {
  $("charName").textContent = p.name;
  const chips = $("chips"); chips.textContent = "";
  if (!p.chips.length) chips.appendChild(el("span", "legend", "Нічого особливого."));
  for (const c of p.chips) {
    const chip = el("span", "chip");
    const d = el("i", "dot" + (c.observable ? " on" : ""));
    chip.append(d, c.text, el("small", "", c.label));
    chips.appendChild(chip);
  }
  $("prose").textContent = p.prose.join(" ");
}
function showError(msg) { const e = $("errbar"); e.textContent = msg; e.hidden = !msg; }

function render(state) {
  feed.textContent = "";
  $("sceneTitle").textContent = state.title;
  tag = state.live ? " · live" : " · офлайн";
  $("clock").textContent = state.clock + tag;
  for (const t of state.transcript) {
    if (t.kind === "intro") add(el("p", "intro", t.text), false);
    else if (t.kind === "player") add(el("p", "me", t.text), false);
    else if (t.kind === "narr") add(el("p", "narr", t.text), false);
    else add(npcBlock(t.who, t.name, t.text, t.cut), false);
  }
  setPanel(state.panel);
  feed.scrollTop = feed.scrollHeight;
}

const handlers = {
  turn_start(e) { turnEls = []; cur = null; add(el("p", "me", e.text)); },
  narr_start() { cur = add(el("p", "narr")); setBusy(true, "narrating"); },
  narr_word(e) { addWord(cur, e.w); },
  narr_end() { setBusy(true, "thinking"); },
  speaker(e) { cur = add(npcBlock(e.who, e.name, "")); setBusy(true, "speaking"); },
  word(e) { addWord(cur, e.w); },
  turn_done(e) {
    if (e.interrupted && cur && cur.classList.contains("npc")) cur.classList.add("cut");
    $("clock").textContent = e.clock + tag;
    setPanel(e.panel);
    $("input").value = ""; syncSend();
    setBusy(false); showError("");
    if (!$("debugPanel").hidden) loadDebug();
    $("input").focus({ preventScroll: true });
  },
  error(e) {
    for (const n of turnEls) n.remove();
    turnEls = []; cur = null;
    $("input").value = e.text; syncSend();
    setBusy(false); showError(e.message);
    if (!$("debugPanel").hidden) loadDebug();
  },
  reset() {},
};

function connect(after) {
  if (es) es.close();
  lastSeq = after;
  es = new EventSource("/api/events?after=" + after);
  for (const type of Object.keys(handlers)) {
    es.addEventListener(type, (m) => {
      const e = JSON.parse(m.data);
      if (e.seq <= lastSeq) return;      // replay after a reconnect: already shown
      lastSeq = e.seq;
      handlers[type](e);
    });
  }
}

async function load() {
  const state = await (await fetch("/api/state")).json();
  render(state);
  setBusy(state.running, state.phase);
  showError("");
  connect(state.resume_after);
}

function syncSend() { $("btnSend").disabled = !$("input").value.trim(); }
$("input").addEventListener("input", syncSend);
$("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("composer").requestSubmit(); }
});
$("composer").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const text = $("input").value.trim();
  if (!text || busy) return;
  showError("");
  setBusy(true, "thinking");
  const r = await fetch("/api/turn", { method: "POST", body: JSON.stringify({ text }) });
  if (!r.ok) { setBusy(false); showError((await r.json()).error || "Помилка."); }
});
$("btnInterrupt").addEventListener("click", () => fetch("/api/interrupt", { method: "POST" }));

// panels
$("btnChar").addEventListener("click", () => { $("charPanel").hidden = false; });
$("charClose").addEventListener("click", () => { $("charPanel").hidden = true; });
$("btnNew").addEventListener("click", async () => {
  if (!confirm("Почати гру спочатку? Поточна пригода буде втрачена.")) return;
  const r = await fetch("/api/campaign/new", { method: "POST" });
  if (r.ok) { $("charPanel").hidden = true; load(); }
});
$("btnDebug").addEventListener("click", () => {
  const on = $("debugPanel").hidden;
  $("debugPanel").hidden = !on;
  $("btnDebug").setAttribute("aria-pressed", String(on));
  if (on) loadDebug();
});

function section(title, rows) {
  const frag = document.createDocumentFragment();
  frag.appendChild(el("h4", "", title));
  if (!rows.length) { frag.appendChild(el("div", "dim", "—")); return frag; }
  const t = el("table");
  for (const r of rows) {
    const tr = el("tr");
    r.forEach((c, i) => tr.appendChild(el("td", i === 0 ? "dim" : "", String(c))));
    t.appendChild(tr);
  }
  frag.appendChild(t);
  return frag;
}
async function loadDebug() {
  const d = await (await fetch("/api/debug")).json();
  const body = $("debugBody"); body.textContent = "";
  if (!d.timing) { body.textContent = "Ходу ще не було."; return; }
  const tm = d.timing;
  body.appendChild(section("Хід", [
    ["до першого слова", tm.first_word_s == null ? "—" : tm.first_word_s + " с"],
    ["весь хід", tm.total_s + " с"],
    ["вартість", "$" + d.cost.toFixed(4)],
    ...(d.error ? [["помилка", d.error]] : []),
  ]));
  if (d.repetition) {
    const r = d.repetition;
    body.appendChild(section("Повторюваність", [
      ["оцінка / n-грами / початки / форма", `${r.score} / ${r.ngram} / ${r.opening} / ${r.shape}`],
      ...r.outputs.flatMap((o) => o.examples.length ? [[o.kind, o.examples.join(" · ")]] : []),
    ]));
  }
  if (d.names) {
    body.appendChild(section("Імена", [
      ["виправлено варіантів", String(d.names.fixed.length)],
      ["схожі на спотворені", d.names.near_misses.map((m) => m.join("→")).join(", ") || "—"],
      ...d.names.fixed.map((f) => [f.where, `${f.form} → ${f.canonical}`]),
    ]));
  }
  body.appendChild(section("Виклики моделей", d.calls.map((c) =>
    [c.role, `${c.model} · ${c.seconds} с · $${c.cost.toFixed(5)} · ${c.chars_in}→${c.chars_out} симв.`])));
  body.appendChild(section("Судження", d.judgments.map((j) =>
    [j.tag, `${j.answer} · p=${j.probability} · ${j.backend}${j.escalated ? " · ескалація" : ""}`])));
  body.appendChild(section("Журнал подій", d.events.map((e) =>
    ["#" + e.id + " " + e.type, JSON.stringify(e.payload).slice(0, 140)])));
  body.appendChild(section("Нотатки рушія", d.notes.map((n) =>
    [n.kind, JSON.stringify(n).slice(0, 160)])));
}

// the world pauses while the app is in the background; the server holds the stream
function presence(visible) {
  const body = JSON.stringify({ visible });
  if (!visible && navigator.sendBeacon) navigator.sendBeacon("/api/presence", body);
  else fetch("/api/presence", { method: "POST", body, keepalive: true }).catch(() => {});
}
document.addEventListener("visibilitychange", () => {
  const vis = document.visibilityState === "visible";
  presence(vis);
  if (vis && es && es.readyState === EventSource.CLOSED) load();   // connection died in the background
});
window.addEventListener("pagehide", () => presence(false));

load();
