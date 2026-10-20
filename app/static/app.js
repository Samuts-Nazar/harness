"use strict";
const $ = (id) => document.getElementById(id);
const feed = $("feed");
let tag = "", lastSeq = 0, es = null, turnEls = [], cur = null, busy = false, turnNpc = [];

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
function npcBlock(who, name, text, cut, event) {
  const b = el("p", "npc"); b.dataset.who = who;
  b.appendChild(el("span", "who", name));
  if (text) b.appendChild(el("span", "w", text));
  if (cut) b.classList.add("cut");
  if (event != null) addAsk(b, event);
  return b;
}

// "Звідки він це знає?": the player marks a line as impossible; the engine checks the channels
function addAsk(block, event) {
  block.dataset.event = event;
  const old = block.querySelector(".ask"); if (old) old.remove();
  const btn = el("button", "ask", "звідки він це знає?");
  btn.type = "button";
  btn.addEventListener("click", () => openAsk(block));
  block.appendChild(btn);
}
function openAsk(block) {
  if (block.querySelector(".askbox")) return;
  const box = el("span", "askbox");
  const note = el("textarea"); note.rows = 2; note.placeholder = "Що саме він не міг знати? (можна лишити порожнім)";
  const go = el("button", "btn primary", "Перевірити"); go.type = "button";
  const cancel = el("button", "btn ghost", "Скасувати"); cancel.type = "button";
  cancel.addEventListener("click", () => box.remove());
  go.addEventListener("click", async () => {
    go.disabled = true; go.textContent = "Перевіряю…";
    let r, d;
    try {
      r = await fetch("/api/challenge", { method: "POST", body: JSON.stringify({ event: Number(block.dataset.event), explanation: note.value }) });
      d = await r.json();
    } catch (e) { d = { error: "Немає зв'язку." }; r = { ok: false }; }
    box.remove();
    showAnswer(block, r.ok, d);
  });
  box.append(note, go, cancel);
  block.appendChild(box);
  note.focus({ preventScroll: true });
}
function showAnswer(block, ok, d) {
  const prev = block.querySelector(".askres"); if (prev) prev.remove();
  const res = el("span", "askres");
  if (!ok) res.textContent = d.error || "Не вдалося перевірити.";
  else if (d.verdict === "channel") {
    res.appendChild(document.createTextNode("Може знати: " + d.public + ". "));
    const spoil = el("button", "linkbtn", "показати (спойлер)"); spoil.type = "button";
    const detail = el("span", "spoiler", d.detail); detail.hidden = true;
    spoil.addEventListener("click", () => { detail.hidden = !detail.hidden; });
    res.append(spoil, detail);
  } else if (d.verdict === "no_channel") {
    if (d.regenerated) {
      const w = block.querySelector(".w"); if (w) w.textContent = d.text;
      block.classList.remove("cut");
      block.dataset.event = d.new_event;
      res.textContent = "Він не міг цього знати: репліку переписано з твоїм поясненням.";
    } else res.textContent = "Він не міг цього знати. Пояснення збережено для наступних реплік.";
  } else res.textContent = "Не вдалося перевірити (суддя недоступний).";
  block.appendChild(res);
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
    else add(npcBlock(t.who, t.name, t.text, t.cut, t.event), false);
  }
  setPanel(state.panel);
  feed.scrollTop = feed.scrollHeight;
  if (state.ended) showFinale(state.chronicle); else $("finale").hidden = true;
}

const handlers = {
  turn_start(e) { turnEls = []; turnNpc = []; cur = null; add(el("p", "me", e.text)); },
  narr_start() { cur = add(el("p", "narr")); setBusy(true, "narrating"); },
  narr_word(e) { addWord(cur, e.w); },
  narr_end() { setBusy(true, "thinking"); },
  speaker(e) { cur = add(npcBlock(e.who, e.name, "")); turnNpc.push(cur); setBusy(true, "speaking"); },
  word(e) { addWord(cur, e.w); },
  turn_done(e) {
    if (e.interrupted && cur && cur.classList.contains("npc")) cur.classList.add("cut");
    $("clock").textContent = e.clock + tag;
    (e.lines || []).forEach((id, i) => { if (turnNpc[i]) addAsk(turnNpc[i], id); });
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
  settled(e) {            // the slow lane is done: the panel now shows what the turn changed
    $("clock").textContent = e.clock + tag;
    setPanel(e.panel);
    if (!$("debugPanel").hidden) loadDebug();
  },
  retract(e) {            // the bookkeeping of the turn failed after the player had read it
    for (const n of turnEls) n.remove();
    turnEls = []; cur = null;
    $("input").value = e.text; syncSend();
    setBusy(false); showError(e.message);
  },
  ended(e) { showFinale(e.chronicle); },
  reset() {},
};

// the player character died: a final chronicle, the campaign is read-only
function showFinale(lines) {
  const box = $("finaleBody"); box.textContent = "";
  for (const l of lines || []) {
    const cls = l.kind === "death" ? "death" : l.kind === "outcome" ? "outcome" : l.kind === "line" ? "npc" : "narr";
    const p = el("p", cls);
    if (l.kind === "line") p.append(el("span", "who", l.who), el("span", "w", l.text));
    else p.textContent = l.text;
    box.appendChild(p);
  }
  $("finale").hidden = false;
  $("composer").hidden = true;
  $("dockBusy").hidden = true;
}

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
  if (!r.ok) { setBusy(false); const d = await r.json(); showError(d.error || "Помилка."); if (d.ended) load(); }
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
    ["весь хід (до кінця тексту)", tm.total_s + " с"],
    ["повільна смуга (поки читаєш)", (tm.slow_s || 0) + " с"],
    ["очікування попередньої смуги", (tm.waited_s || 0) + " с"],
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
  if (d.world) appendWorld(body, d.world);
  body.appendChild(section("Виклики моделей", d.calls.map((c) =>
    [c.role, `${c.model} · ${c.seconds} с · $${c.cost.toFixed(5)} · ${c.chars_in}→${c.chars_out} симв.`])));
  body.appendChild(section("Судження", d.judgments.map((j) =>
    [j.tag, `${j.answer} · p=${j.probability} · ${j.backend}${j.escalated ? " · ескалація" : ""}`])));
  body.appendChild(section("Журнал подій", d.events.map((e) =>
    ["#" + e.id + " " + e.type, JSON.stringify(e.payload).slice(0, 140)])));
  body.appendChild(section("Нотатки рушія", d.notes.map((n) =>
    [n.kind, JSON.stringify(n).slice(0, 160)])));
  if (d.challenge) body.appendChild(section("Остання перевірка «звідки він це знає»", [
    [d.challenge.verdict, JSON.stringify(d.challenge).slice(0, 300)]]));
  await loadKnowledge(body);
}

// "Світ": what happened beyond the scene, which news reached whom, in which version
function appendWorld(body, w) {
  body.appendChild(section("Світ: час і місце", [["зараз", `${w.clock.now} хв · ${w.clock.place}`],
    ...w.moves.map((m) => [m.kind, `${m.from} → ${m.to} · ${m.minutes} хв`])]));
  body.appendChild(section("Світ: поза сценою", w.offscreen.map((o) =>
    [o.character, `${o.what} · ${o.place} · з ${o.arrives} хв`])));
  body.appendChild(section("Світ: влада", [...w.reactions.map((r) => [r.authority, r.text]),
    ...w.arrivals.map((a) => ["прибули", a.text])]));
  body.appendChild(section("Світ: канонічні події", w.canon.map((c) => [c.outcome, c.summary])));
  for (const n of w.news) {
    const det = el("details");
    det.appendChild(el("summary", "", `${n.new ? "● " : ""}${n.text.slice(0, 80)} · гучність ${n.notability}`));
    det.appendChild(section("версії", n.versions.map((v) =>
      [v.holder, `${v.text} · ${v.operator} · ${v.hops} пер. · від ${v.source || "—"} · ${v.at} хв${v.stance ? " · " + v.stance : ""}`])));
    det.appendChild(section("почули", n.heard_by.map((h) => [h.person, `від ${h.via} · ${h.at} хв`])));
    body.appendChild(det);
  }
}

// who knows what and from where (per character), so the user can check knowledge directly
async function loadKnowledge(body) {
  const r = await fetch("/api/knowledge");
  if (!r.ok) { body.appendChild(section("Хто що знає", [["", "недоступно під час ходу"]])); return; }
  const k = await r.json();
  body.appendChild(el("h4", "", "Хто що знає"));
  for (const [id, c] of Object.entries(k)) {
    const det = el("details");
    det.appendChild(el("summary", "", `${c.name} (${c.label}) · ${c.items.length}`));
    const t = el("table");
    for (const i of c.items) {
      const tr = el("tr");
      tr.appendChild(el("td", "dim", i.kind));
      tr.appendChild(el("td", "", i.text));
      tr.appendChild(el("td", "dim", [i.how, i.source_name ? "від " + i.source_name : "", i.when_text || "", i.event != null ? "#" + i.event : ""].filter(Boolean).join(" · ")));
      t.appendChild(tr);
    }
    det.appendChild(t);
    body.appendChild(det);
  }
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

$("btnNewFinale").addEventListener("click", async () => {
  const r = await fetch("/api/campaign/new", { method: "POST" });
  if (r.ok) { $("finale").hidden = true; load(); }
});
