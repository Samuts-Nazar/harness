"use strict";
// The book page: one continuous page of prose; each character's speech in their own ink.
const $ = (id) => document.getElementById(id);
const feed = $("feed");
const root = document.documentElement;
// The eight inks offered by the picker: the palette of app/inks.py (a test keeps them equal).
const PALETTE = ["#e8a87c", "#8fb8e8", "#a8d49a", "#e89ab8", "#c8a8f0", "#e8d27c", "#7cd4cc", "#e8887c"];
const PLACEHOLDER_IDLE = "Що скажете чи зробите…";
const PLACEHOLDER_TALK = "Можна писати й зараз — це переб'є…";

let tag = "", lastSeq = 0, es = null, cur = null, busy = false, phase = "idle", turnNpc = [], sending = 0;
// the feed elements of each turn, by the server's turn id: a late retract or error of an earlier
// turn (its slow lane failed after the player had cut in) removes only that turn's elements
let turnEls = {}, curTurn = null;
let cast = {};            // tok -> {tok, label, ink, present}: who the player character has met
let actions = [];         // optional line actions the server offers ("model_error", "cut")
let speakingTok = null;   // whose words stream now (tints ✋)
let sugg = { turn: null, items: [] };
// a reload during a turn's slow lane: that turn is already in the transcript, so its replayed feed
// events are skipped (only events of that turn id), and its rendered paragraphs are tracked under
// that id so a late retract still removes them
let replay = null, lastTurnNodes = [];

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function store(key, val) {   // per-viewer conveniences only; the page works without storage
  try { if (val === undefined) return localStorage.getItem(key); localStorage.setItem(key, val); }
  catch (e) { return null; }
  return null;
}

// -- inks ---------------------------------------------------------------------------------
const safeTok = (t) => String(t || "").replace(/[^A-Za-z0-9_-]/g, "");
const inkVar = (tok) => "var(--ink-" + safeTok(tok) + ", var(--ink-none))";
function setInk(tok, ink) {   // one custom property per character: every line of theirs follows
  if (!tok || !ink) return;
  root.style.setProperty("--ink-" + safeTok(tok), ink);
  if (cast[tok]) cast[tok].ink = ink;
}
async function loadCast() {
  let list;
  try { const r = await fetch("/api/cast"); if (!r.ok) return; list = await r.json(); }
  catch (e) { return; }
  cast = {};
  for (const c of list) { cast[c.tok] = c; setInk(c.tok, c.ink); }
  renderLegend();
}

// -- paragraphs ---------------------------------------------------------------------------
function add(node, tracked = true) {
  const atBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 80;
  feed.appendChild(node);
  if (tracked) (turnEls[curTurn] = turnEls[curTurn] || []).push(node);
  if (atBottom) feed.scrollTop = feed.scrollHeight;
  return node;
}
function follow(fn) {   // keep the newest words in view, unless the reader scrolled up
  const atBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 80;
  fn();
  if (atBottom) feed.scrollTop = feed.scrollHeight;
}

// NPC text: speech, with the speaker's own beats in *asterisks* (one may still be open while it
// streams). Speech is written with a dash and in the character's ink; beats in the base italic.
function segments(text) {
  const out = [];
  String(text || "").split("*").forEach((s, i) => {
    s = s.trim();
    if (i % 2 === 0) s = s.replace(/^[—–-]+\s*/, "");
    if (s) out.push({ beat: i % 2 === 1, text: s });
  });
  return out;
}
// a speech paragraph names its speaker (subtly) only when the speaker changed from the previous
// speech paragraph and no beat of the line names them; otherwise colour, dash and legend carry it
function needsTag(p, segs) {
  if (p._prevTok === p.dataset.tok) return false;
  const label = String(p.dataset.label || "").toLowerCase();
  return !segs.some((s) => s.beat && label && s.text.toLowerCase().includes(label));
}
function fillBody(p, text) {
  p._raw = text;
  const body = el("span", "body");
  const segs = segments(text);
  if (p.dataset.line === "say" && needsTag(p, segs)) body.append(el("span", "who", p.dataset.label + ":"), document.createTextNode(" "));
  segs.forEach((s, i) => {
    if (i) body.appendChild(document.createTextNode(" "));
    if (!s.beat) { body.appendChild(el("span", "q", "— " + s.text)); return; }
    let t = (i ? "— " : "") + s.text;
    if (i < segs.length - 1 && !/[.!?…,:;]$/.test(t)) t += ".";
    body.appendChild(el("span", "beat", t));
  });
  const old = p._body;
  p._body = body;
  if (old) old.replaceWith(body); else p.appendChild(body);   // keeps an open ask box after it
}
function who(p, tok, label) {   // no visible tag: gesture text names the actor itself
  p.dataset.tok = tok;
  p.dataset.label = label || "";
  p.style.setProperty("--c", inkVar(tok));
}
function prevSpeaker() {   // the speaker of the last speech paragraph on the page so far
  const ls = lines();
  for (let i = ls.length - 1; i >= 0; i--) if (ls[i].dataset.line === "say") return ls[i].dataset.tok;
  return null;
}
function sayBlock(tok, label, text, cut, event) {
  const p = el("p", "npc"); p.dataset.line = "say"; p.tabIndex = 0;
  who(p, tok, label);
  p._prevTok = prevSpeaker();
  fillBody(p, text || "");
  if (cut) p.classList.add("cut");
  if (event != null) p.dataset.event = event;
  return p;
}
function actBlock(tok, label, text) {
  const p = el("p", "npc act"); p.dataset.line = "act"; p.tabIndex = 0;
  who(p, tok, label);
  p.appendChild(el("span", "act-text", text));
  return p;
}
function narrBlock(text, cls = "narr") {
  const p = el("p", cls, text); p.dataset.line = cls === "intro" ? "intro" : "narr";
  if (cls === "narr") p.tabIndex = 0;   // the line menu (model error) is reachable by keyboard
  return p;
}
function meBlock(text) { const p = el("p", "me", text); p.dataset.line = "me"; return p; }
function streaming(p) {
  for (const n of Array.from(feed.children)) if (n !== p && n.classList) n.classList.remove("streaming");
  if (p) p.classList.add("streaming");
}

// -- the line menu (long press / right click / Enter on a line) ----------------------------
function lines() { return Array.from(feed.children).filter((n) => n.dataset && n.dataset.line); }
function lineInfo(p) {
  const all = lines(), i = all.indexOf(p);
  let lastMe = -1, lastW = -1;
  const isWorld = (n) => ["narr", "say", "act"].includes(n.dataset.line);
  all.forEach((n, k) => { if (n.dataset.line === "me") lastMe = k; if (isWorld(n)) lastW = k; });
  const kind = p.dataset.line;
  // "last world output": the very last narration, line or gesture of the story, after the player
  return { kind, tok: p.dataset.tok || "", event: p.dataset.event != null && p.dataset.event !== "",
    cut: p.classList.contains("cut"), lastWorld: isWorld(p) && lastMe >= 0 && i === lastW && i > lastMe,
    lastLine: i === all.length - 1, busy };
}
// which items apply to a line (spec: «Звідки він це знає?» on NPC speech only; model error only
// on the last world output; retroactive cut only on the last NPC line; ink on any line of a
// character). `offered`: the optional actions the server has endpoints for.
function sheetItems(x, offered) {
  const out = [];
  if (x.kind === "say" && x.event) out.push("challenge");
  if (offered.includes("model_error") && x.lastWorld && x.kind !== "act" && !x.busy) out.push("model_error");
  if (offered.includes("cut") && x.kind === "say" && x.lastWorld && x.lastLine && !x.busy && !x.cut)
    out.push("cut");
  if (x.tok && (x.kind === "say" || x.kind === "act")) out.push("ink");
  return out;
}
const ITEM_TEXT = {
  challenge: "🔎 Звідки він це знає?", model_error: "⚠ Помилка моделі — переписати",
  cut: "✂ Перебити тут (заднім числом)", ink: "🎨 Чорнило цього персонажа",
};
let sheetLine = null;
function labelOf(p) { return p.dataset.label || ""; }
function openSheet(p) {
  const sheet = $("sheet");
  if (sheet.open) return;
  const items = sheetItems(lineInfo(p), actions);
  if (!items.length) return;
  sheetLine = p;
  p.classList.add("sel");
  $("sheetHead").textContent = p.dataset.line === "narr" ? "Оповідь" :
    (p.dataset.line === "act" ? "Жест — " : "Ця репліка — ") + labelOf(p);
  const body = $("sheetBody"); body.textContent = "";
  for (const a of items) {
    const b = el("button", "opt", ITEM_TEXT[a]); b.type = "button"; b.dataset.act = a;
    b.addEventListener("click", () => act(a, p));
    body.appendChild(b);
  }
  sheet.showModal();
  $("sheetHead").focus();
  feed.classList.add("menu-open");
  p.scrollIntoView({ block: "start" });   // the line stays in sight above the sheet
}
function inkPicker(tok) {
  const c = cast[tok] || { label: "", ink: "" };
  const now = (c.ink || getComputedStyle(root).getPropertyValue("--ink-" + safeTok(tok))).trim().toLowerCase();
  $("sheetHead").textContent = "Чорнило: " + (c.label || labelOf(sheetLine || el("p")));
  const body = $("sheetBody"); body.textContent = "";
  const sw = el("div", "sw"); sw.setAttribute("role", "group"); sw.setAttribute("aria-label", "Кольори");
  PALETTE.forEach((ink, i) => {
    const b = el("button"); b.type = "button"; b.dataset.ink = ink;
    b.style.setProperty("--sw", ink);
    b.setAttribute("aria-label", "Колір " + (i + 1));
    b.setAttribute("aria-pressed", String(ink === now));
    b.addEventListener("click", () => pickInk(tok, ink, sw));
    sw.appendChild(b);
  });
  body.append(sw, el("p", "note", "Колір належить персонажу: зміниться в усіх його репліках, минулих і майбутніх, у всій кампанії."));
  const first = sw.querySelector("[aria-pressed=true]") || sw.firstChild;
  if (first && first.focus) first.focus();
}
function openInk(tok) {
  const sheet = $("sheet");
  if (!sheet.open) { sheetLine = null; sheet.showModal(); }
  inkPicker(tok);
}
async function pickInk(tok, ink, sw) {
  const before = cast[tok] ? cast[tok].ink : null;
  setInk(tok, ink); renderLegend();
  for (const b of sw.children) b.setAttribute("aria-pressed", String(b.dataset.ink === ink));
  let ok = false;
  try { ok = (await fetch("/api/ink", { method: "POST", body: JSON.stringify({ tok, ink }) })).ok; }
  catch (e) { ok = false; }
  if (!ok) {
    if (before) { setInk(tok, before); renderLegend(); }
    showError("Не вдалося зберегти колір.");
  }
}
function closeSheet() { const s = $("sheet"); if (s.open) s.close(); }
function act(a, p) {
  if (a === "ink") { inkPicker(p.dataset.tok); return; }
  closeSheet();
  if (a === "challenge") openAsk(p);
  else if (a === "model_error") openModelError(p);
  else if (a === "cut") openCut(p);
}
$("sheet").addEventListener("close", () => {
  if (sheetLine) sheetLine.classList.remove("sel");
  sheetLine = null;
  feed.classList.remove("menu-open");
});
$("sheet").addEventListener("click", (ev) => { if (ev.target === $("sheet")) closeSheet(); });

// long press on touch (and a long click with a mouse), right click on desktop, Enter by keyboard
let press = null, swallowClick = false;
const lineOf = (t) => (t && t.closest ? t.closest("#feed [data-line]") : null);
const onControl = (t) => t && t.closest && t.closest("button, textarea, a, .askbox, .askres");
function cancelPress() { if (press) { clearTimeout(press.t); press = null; } }
feed.addEventListener("pointerdown", (ev) => {
  swallowClick = false;
  const p = lineOf(ev.target);
  if (!p || ev.button > 0 || onControl(ev.target)) return;
  cancelPress();
  press = { x: ev.clientX, y: ev.clientY,
    t: setTimeout(() => { press = null; swallowClick = true; openSheet(p); }, 500) };
});
feed.addEventListener("pointermove", (ev) => {
  if (press && Math.hypot(ev.clientX - press.x, ev.clientY - press.y) > 10) cancelPress();
});
// a touch scroll ends in pointercancel; a programmatic scroll (the story following) is no reason
for (const t of ["pointerup", "pointercancel"]) feed.addEventListener(t, cancelPress);
feed.addEventListener("contextmenu", (ev) => {
  const p = lineOf(ev.target);
  if (!p || onControl(ev.target)) return;
  ev.preventDefault();
  cancelPress();
  openSheet(p);
});
feed.addEventListener("keydown", (ev) => {
  const p = ev.target && ev.target.dataset && ev.target.dataset.line ? ev.target : null;
  if (p && (ev.key === "Enter" || ev.key === "ContextMenu" || (ev.shiftKey && ev.key === "F10"))) {
    ev.preventDefault(); openSheet(p);
  }
});
feed.addEventListener("click", (ev) => {   // a tap on the story shows the rest at once
  if (swallowClick) { swallowClick = false; return; }
  if (!onControl(ev.target)) skipPace();
});

// "Звідки він це знає?": the player marks a line as impossible; the engine checks the channels
function addAsk(block, event) { block.dataset.event = event; }
function inlineBox(block, placeholder, goText, onGo) {
  if (block.querySelector(".askbox")) return;
  const box = el("span", "askbox");
  const note = el("textarea"); note.rows = 2; note.placeholder = placeholder;
  const go = el("button", "btn primary", goText); go.type = "button";
  const cancel = el("button", "btn ghost", "Скасувати"); cancel.type = "button";
  cancel.addEventListener("click", () => box.remove());
  go.addEventListener("click", () => onGo(note, go, box));
  box.append(note, go, cancel);
  block.appendChild(box);
  note.focus({ preventScroll: true });
}
function openAsk(block) {
  inlineBox(block, "Що саме він не міг знати? (можна лишити порожнім)", "Перевірити", async (note, go, box) => {
    go.disabled = true; go.textContent = "Перевіряю…";
    let r, d;
    try {
      r = await fetch("/api/challenge", { method: "POST", body: JSON.stringify({ event: Number(block.dataset.event), explanation: note.value }) });
      d = await r.json();
    } catch (e) { d = { error: "Немає зв'язку." }; r = { ok: false }; }
    box.remove();
    showAnswer(block, r.ok, d);
  });
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
    if (d.withdrawn) {
      block.remove();
      res.textContent = "Він не міг цього знати: репліку прибрано, він промовчав.";
      feed.appendChild(res);
      return;
    }
    if (d.regenerated) {
      fillBody(block, d.text);
      block.classList.remove("cut");
      block.dataset.event = d.new_event;
      res.textContent = "Він не міг цього знати: репліку переписано з твоїм поясненням.";
    } else res.textContent = "Він не міг цього знати. Пояснення збережено для наступних реплік.";
  } else res.textContent = "Не вдалося перевірити (суддя недоступний).";
  block.appendChild(res);
}
// «Помилка моделі» and «Перебити тут»: shown only when the server offers them (state.actions)
async function postAndReload(url, body) {
  let r, d = {};
  try { r = await fetch(url, { method: "POST", body: JSON.stringify(body) }); if (!r.ok) d = await r.json(); }
  catch (e) { r = { ok: false }; d = { error: "Немає зв'язку." }; }
  if (!r.ok) { showError(d.error || "Не вдалося."); return; }
  load();
}
function openModelError(block) {
  inlineBox(block, "Що саме не так? (обов'язково)", "Переписати", (note, go) => {
    if (!note.value.trim()) { note.focus(); return; }
    go.disabled = true;
    postAndReload("/api/model_error", { event: Number(block.dataset.event) || null, explanation: note.value.trim() });
  });
}
function openCut(block) {   // tap the word after which he is cut off
  const words = String(block._raw || "").split(/\s+/).filter(Boolean);
  const body = el("span", "body cutpick");
  body.appendChild(el("span", "note", "Торкніться слова, після якого перебити: "));
  words.forEach((w, i) => {
    const b = el("button", "cw", w); b.type = "button";
    b.addEventListener("click", () => postAndReload("/api/cut", { event: Number(block.dataset.event), after_words: i + 1 }));
    body.append(b, document.createTextNode(" "));
  });
  const cancel = el("button", "btn ghost", "Скасувати"); cancel.type = "button";
  cancel.addEventListener("click", () => fillBody(block, block._raw));
  body.appendChild(cancel);
  block._body.replaceWith(body); block._body = body;
}

// -- legend ------------------------------------------------------------------------------
function renderLegend() {
  const list = $("legendList"); list.textContent = "";
  const all = Object.values(cast);
  const shown = all.filter((c) => c.present).length ? all.filter((c) => c.present) : all;
  for (const c of shown) {
    const b = el("button", "lg"); b.type = "button"; b.dataset.tok = c.tok;
    b.style.setProperty("--c", inkVar(c.tok));
    b.append(el("i", "dot"), el("span", "nm", c.label));
    b.setAttribute("aria-label", c.label + ": змінити чорнило");
    b.tabIndex = $("legend").dataset.open === "true" ? 0 : -1;
    b.addEventListener("click", (ev) => {
      if ($("legend").dataset.open !== "true") return;   // collapsed: the whole row opens it
      ev.stopPropagation(); openInk(c.tok);
    });
    list.appendChild(b);
  }
  $("legend").hidden = !shown.length;
}
function setLegend(open) {
  $("legend").dataset.open = String(open);
  $("btnLegend").setAttribute("aria-expanded", String(open));
  for (const b of $("legendList").children) b.tabIndex = open ? 0 : -1;
  store("legendOpen", open ? "1" : "0");
}
$("btnLegend").addEventListener("click", (ev) => {
  ev.stopPropagation();
  setLegend($("legend").dataset.open !== "true");
});
$("legend").addEventListener("click", () => { if ($("legend").dataset.open !== "true") setLegend(true); });

// -- suggestions ---------------------------------------------------------------------------
function renderSugg() {
  const box = $("sugg"); box.textContent = "";
  for (const s of sugg.items.slice(0, 6)) {
    const b = el("button", "sg", s); b.type = "button"; b.title = s;
    b.addEventListener("click", () => {   // into the input for editing; nothing is sent
      const inp = $("input");
      inp.value = inp.value.trim() ? inp.value.replace(/\s*$/, " ") + s : s;
      syncSend();
      inp.focus();
      inp.setSelectionRange(inp.value.length, inp.value.length);
    });
    box.appendChild(b);
  }
  box.hidden = busy || !sugg.items.length;
}
async function moreSugg() {
  const btn = $("btnIdea");
  if (btn.disabled) return;
  btn.disabled = true; btn.classList.add("wait");
  try {
    const r = await fetch("/api/suggestions?more=1");
    const d = await r.json();
    if (!r.ok) showError(d.error || "Не вдалося підказати.");
    else if (d.items && d.items.length) {   // the new ones first, where the eye is
      sugg.items = d.items.concat(sugg.items.filter((s) => !d.items.includes(s)));
      renderSugg();
      $("sugg").scrollLeft = 0;
    }
  } catch (e) { showError("Немає зв'язку."); }
  btn.disabled = false; btn.classList.remove("wait");
}
async function loadSugg() {
  try {
    const r = await fetch("/api/suggestions");
    if (!r.ok) return;
    const d = await r.json();
    if (!busy) { sugg = { turn: d.turn, items: d.items || [] }; renderSugg(); }
  } catch (e) { /* suggestions are optional */ }
}

// -- phases --------------------------------------------------------------------------------
// the composer stays open during a turn: sending cuts in (the server interrupts, then runs it)
function setBusy(on, ph) {
  busy = on;
  phase = on ? (ph && ph !== "idle" ? ph : "thinking") : "idle";
  document.body.dataset.phase = phase;
  feed.classList.toggle("busy", on);
  const talk = phase === "narrating" || phase === "speaking";
  // screen readers wait while words stream in, then read the finished paragraphs once
  feed.setAttribute("aria-busy", String(talk));
  $("btnInterrupt").hidden = !talk;
  $("btnInterrupt").style.setProperty("--c", phase === "speaking" && speakingTok ? inkVar(speakingTok) : "var(--pen)");
  $("btnIdea").hidden = on;
  $("btnSkip").hidden = !talk;
  $("btnDrawerSkip").hidden = !talk;
  $("busyText").hidden = phase !== "thinking";
  $("input").placeholder = on ? PLACEHOLDER_TALK : PLACEHOLDER_IDLE;
  if (!on) streaming(null);
  renderSugg();
}
function skipPace() { if (busy) fetch("/api/skip", { method: "POST" }).catch(() => {}); }
function setPanel(p) {
  $("charName").textContent = p.name;
  const chips = $("chips"); chips.textContent = "";
  if (!p.chips.length) chips.appendChild(el("span", "note", "Нічого особливого."));
  for (const c of p.chips) {
    const chip = el("span", "chip");
    chip.append(el("i", "cdot" + (c.observable ? " on" : "")), c.text, el("small", "", c.label));
    chips.appendChild(chip);
  }
  $("prose").textContent = p.prose.join(" ");
}
function showError(msg) { const e = $("errbar"); e.textContent = msg; e.hidden = !msg; }

function render(state) {
  feed.textContent = "";
  $("sceneTitle").textContent = state.title;
  tag = state.live ? "" : " · офлайн";
  $("clock").textContent = state.clock + tag;
  actions = Array.isArray(state.actions) ? state.actions : [];
  lastTurnNodes = [];   // the paragraphs since the last player paragraph (the last turn)
  for (const t of state.transcript) {
    let n = null;
    if (t.kind === "intro") n = narrBlock(t.text, "intro");
    else if (t.kind === "player") { n = meBlock(t.text); lastTurnNodes = []; }
    else if (t.kind === "narr") { if (t.text && t.text.trim()) n = narrBlock(t.text); }
    else if (t.kind === "npc_act") n = actBlock(t.tok, t.label, t.text);
    else n = sayBlock(t.tok, t.label, t.text, t.cut, t.event);
    if (!n) continue;
    add(n, false);
    if (t.kind !== "intro") lastTurnNodes.push(n);
  }
  setPanel(state.panel);
  feed.scrollTop = feed.scrollHeight;
  if (document.fonts && document.fonts.ready)   // the web font changes the height once it arrives
    document.fonts.ready.then(() => { feed.scrollTop = feed.scrollHeight; });
  if (state.ended) showFinale(state.chronicle); else $("finale").hidden = true;
}

// remove the elements of the event's turn; true when it is the current turn
function dropTurn(e) {
  const t = e.turn != null ? e.turn : curTurn;
  for (const n of turnEls[t] || []) n.remove();
  delete turnEls[t];
  if (t !== curTurn) return false;
  cur = null;
  return true;
}
function newSpeaker(tok) { if (tok && !cast[tok]) loadCast(); }   // ink assigned on first sight

const handlers = {
  turn_start(e) {
    curTurn = e.turn; turnEls[curTurn] = []; turnNpc = []; cur = null;
    sugg = { turn: null, items: [] };
    add(meBlock(e.text));
    feed.scrollTop = feed.scrollHeight;   // the player's own move: the page follows the story again
    renderSugg();
  },
  narr_start() { cur = null; setBusy(true, "narrating"); },   // the paragraph appears with its first word
  narr_word(e) {
    follow(() => {
      if (!cur || cur.dataset.line !== "narr") { cur = add(narrBlock("")); streaming(cur); }
      cur.textContent = cur.textContent ? cur.textContent + " " + e.w : e.w;
    });
  },
  narr_end() { streaming(null); setBusy(true, "thinking"); },
  speaker(e) {
    speakingTok = e.tok; newSpeaker(e.tok);
    cur = add(sayBlock(e.tok, e.label, "")); turnNpc.push(cur); streaming(cur);
    setBusy(true, "speaking");
  },
  npc_act(e) { newSpeaker(e.tok); cur = add(actBlock(e.tok, e.label, e.text)); streaming(null); },
  word(e) {
    if (!cur || cur.dataset.line !== "say") return;
    const p = cur;
    follow(() => fillBody(p, p._raw ? p._raw + " " + e.w : e.w));
  },
  turn_done(e) {
    $("clock").textContent = e.clock + tag;
    (e.lines || []).forEach((id, i) => {
      if (!turnNpc[i]) return;
      addAsk(turnNpc[i], id);
      if ((e.cut_lines || []).includes(id)) turnNpc[i].classList.add("cut");
    });
    setPanel(e.panel);
    sugg.turn = e.turn;
    if (!sending) setBusy(false);       // a text typed during the turn is already on its way
    showError("");
    if (!$("debugPanel").hidden) loadDebug();
  },
  error(e) {
    if (dropTurn(e)) {
      if (!$("input").value.trim()) $("input").value = e.text;   // keep what is being typed now
      syncSend();
      setBusy(false);
    }
    showError(e.message);
    if (!$("debugPanel").hidden) loadDebug();
  },
  settled(e) {            // the slow lane is done: the panel now shows what the turn changed
    $("clock").textContent = e.clock + tag;
    setPanel(e.panel);
    loadCast();           // a learned name changes a label; token and ink stay
    if ($("drawer").open) loadPeople();
    if (!$("debugPanel").hidden) loadDebug();
  },
  retract(e) {            // the bookkeeping of the turn failed after the player had read it
    if (dropTurn(e)) {      // an earlier turn: the running one keeps its paragraphs, input and busy state
      if (!$("input").value.trim()) $("input").value = e.text;
      syncSend();
      setBusy(false);
    }
    showError(e.message);
  },
  suggestions(e) {        // the turn assistant: 2–3 actions above the input, never sent by itself
    if (e.turn !== curTurn && curTurn != null) return;
    sugg = { turn: e.turn, items: (sugg.turn === e.turn ? sugg.items : []).concat(e.items || []) };
    renderSugg();
  },
  ink(e) { setInk(e.tok, e.ink); renderLegend(); },
  ended(e) { showFinale(e.chronicle); },
  reset() {},
};
// events of a turn whose text the transcript already holds (a reload during its slow lane)
const FEED_EVENTS = new Set(["turn_start", "narr_start", "narr_word", "narr_end", "speaker", "npc_act", "word", "turn_done"]);

// the player character died: a final chronicle, the campaign is read-only
function showFinale(lines) {
  const box = $("finaleBody"); box.textContent = "";
  for (const l of lines || []) {
    const cls = l.kind === "death" ? "death" : l.kind === "outcome" ? "outcome" : l.kind === "line" ? "npc" : "narr";
    const p = el("p", cls);
    if (l.kind === "line") p.append(el("span", "who", l.who), el("span", "q", " — " + l.text));
    else p.textContent = l.text;
    box.appendChild(p);
  }
  $("finale").hidden = false;
  $("composer").hidden = true;
  $("sugg").hidden = true;
}

function beginReplay(state) {
  // the transcript holds the running turn only once its fast part is done (not after an error);
  // its entries carry the turn id
  const holds = state.running && state.phase === "idle" && state.turn != null &&
    (state.transcript || []).some((t) => t.kind === "player" && t.turn === state.turn);
  replay = holds ? { turn: null } : null;
}
function dispatch(type, e) {
  if (replay && FEED_EVENTS.has(type)) {
    if (replay.turn == null && type === "turn_start") {
      replay.turn = e.turn; curTurn = e.turn;
      turnEls[e.turn] = lastTurnNodes.slice();
      return;
    }
    if (replay.turn != null && e.turn === replay.turn) {
      if (type === "turn_done") sugg.turn = e.turn;
      return;
    }
  }
  handlers[type](e);
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
      dispatch(type, e);
    });
  }
}

async function load() {
  const state = await (await fetch("/api/state")).json();
  render(state);
  turnEls = {}; cur = null;
  beginReplay(state);
  setBusy(state.phase !== "idle", state.phase);
  showError("");
  connect(state.resume_after);
  loadCast();
  if (state.phase === "idle") loadSugg();
}

function syncSend() { $("btnSend").disabled = !$("input").value.trim(); }
function grow() { const i = $("input"); i.style.height = "auto"; i.style.height = Math.min(i.scrollHeight, 160) + "px"; }
$("input").addEventListener("input", () => { syncSend(); grow(); });
$("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("composer").requestSubmit(); }
});
$("composer").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const text = $("input").value.trim();
  if (!text) return;
  showError("");
  $("input").value = ""; syncSend(); grow();
  sending++;
  setBusy(true, "thinking");
  let r, d = {};
  try {
    r = await fetch("/api/turn", { method: "POST", body: JSON.stringify({ text }) });
    if (!r.ok) d = await r.json();
  } catch (err) { r = { ok: false }; d = { error: "Немає зв'язку." }; }
  sending--;
  if (!r.ok) {
    if (!$("input").value.trim()) $("input").value = text;
    syncSend();
    if (!sending) setBusy(false);
    showError(d.error || "Помилка.");
    if (d.ended) load();
  }
});
$("btnInterrupt").addEventListener("click", () => fetch("/api/interrupt", { method: "POST" }));
$("btnSkip").addEventListener("click", skipPace);
$("btnIdea").addEventListener("click", moreSugg);

// -- the ☰ drawer --------------------------------------------------------------------------
async function loadPeople() {
  let list = [];
  try { const r = await fetch("/api/people"); if (r.ok) list = await r.json(); } catch (e) { /* none */ }
  const box = $("people"); box.textContent = "";
  if (!list.length) box.appendChild(el("p", "note", "Поки нікого."));
  for (const c of list) {
    const row = el("div", "person"); row.dataset.tok = c.tok;
    row.style.setProperty("--c", inkVar(c.tok));
    const head = el("div", "person-h");
    const ink = el("button", "inkbtn"); ink.type = "button";
    ink.setAttribute("aria-label", "Чорнило: " + c.label);
    ink.addEventListener("click", () => { $("drawer").close(); openInk(c.tok); });
    head.append(ink, el("b", "", c.label), el("small", "", c.present ? "тут" : "не тут"));
    row.appendChild(head);
    if (c.known && c.known.length) {
      const ul = el("ul");
      for (const k of c.known) ul.appendChild(el("li", "", k));
      row.appendChild(ul);
    } else row.appendChild(el("p", "note", "Нічого певного."));
    box.appendChild(row);
  }
}
async function loadPlaces() {   // "where can I go" (Task 4); nothing when the endpoint is missing
  let list = [];
  try { const r = await fetch("/api/places"); if (r.ok) list = await r.json(); } catch (e) { list = []; }
  if (list && !Array.isArray(list)) list = list.places || [];
  const ul = $("places"); ul.textContent = "";
  for (const pl of list || []) {
    const name = typeof pl === "string" ? pl : (pl.name || pl.label || pl.title || "");
    if (!name) continue;
    const li = el("li");
    const b = el("button", "linkbtn", name); b.type = "button";   // a tap writes «Іду до …»
    b.addEventListener("click", () => {
      $("input").value = pl.go || ("Іду: " + name); syncSend(); grow();
      $("drawer").close(); $("input").focus();
    });
    li.appendChild(b);
    const mins = typeof pl === "object" ? Number(pl.minutes) : NaN;
    if (mins >= 0) li.appendChild(el("small", "", " · ~" + mins + " хв"));
    ul.appendChild(li);
  }
  $("placesSec").hidden = !ul.children.length;
}
$("btnMenu").addEventListener("click", () => {
  $("drawer").showModal();
  loadPeople(); loadPlaces();
});
$("drawerClose").addEventListener("click", () => $("drawer").close());
$("drawer").addEventListener("click", (ev) => { if (ev.target === $("drawer")) $("drawer").close(); });
$("btnDrawerSkip").addEventListener("click", () => { skipPace(); $("drawer").close(); });
$("btnNew").addEventListener("click", async () => {
  if (!confirm("Почати гру спочатку? Поточна пригода буде втрачена.")) return;
  const r = await fetch("/api/campaign/new", { method: "POST" });
  if (r.ok) { $("drawer").close(); cast = {}; load(); }
});
function showDebug(on) {
  $("debugPanel").hidden = !on;
  $("btnDebug").setAttribute("aria-pressed", String(on));
  if (on) loadDebug();
}
$("btnDebug").addEventListener("click", () => { $("drawer").close(); showDebug($("debugPanel").hidden); });
$("debugClose").addEventListener("click", () => { showDebug(false); $("btnMenu").focus(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("debugPanel").hidden) showDebug(false); });

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
  if (d.decisions) {
    const fmt = (c) => `${c.total} (суджень ${c.judgments}, ескалацій ${c.escalations}, ` +
      `викликів ${Object.entries(c.llm_calls_by_role).map(([k, n]) => k + " " + n).join(", ") || 0}, ` +
      `рішень коду ${c.code_choices})`;
    body.appendChild(section("Рішення", [
      ["хід", fmt(d.decisions.turn)], ["сцена", fmt(d.decisions.scene)],
      ["сесія", fmt(d.decisions.session)]]));
  }
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

// who knows what and from where (per character; debug only: real names), to check knowledge
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

setLegend(store("legendOpen") !== "0");
presence(document.visibilityState !== "hidden");   // a reload sent "hidden" on its way out
load();

$("btnNewFinale").addEventListener("click", async () => {
  const r = await fetch("/api/campaign/new", { method: "POST" });
  if (r.ok) { $("finale").hidden = true; $("composer").hidden = false; cast = {}; load(); }
});
