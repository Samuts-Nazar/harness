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
let assistantOn = true;   // a game package may switch the turn assistant (💡) off

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
  for (const p of feed.querySelectorAll(".npc[data-tok]")) {   // a learned name changes the label of past lines too
    const c = cast[p.dataset.tok];
    if (!c || !c.label || c.label === p.dataset.label) continue;
    p.dataset.label = c.label;
    p.querySelectorAll(".who").forEach((w) => { w.textContent = c.label + ":"; });
  }
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
// the speaker's masked label; shown or hidden by the body class `names` (the ☰ switch), never rebuilt
function whoTag(p) { return el("span", "who", (p.dataset.label || "") + ":"); }
function setNames(on) {
  document.body.classList.toggle("names", on);
  $("btnNames").setAttribute("aria-pressed", String(on));
  $("btnNames").textContent = "🏷 Імена мовців: " + (on ? "так" : "ні");
}
function fillBody(p, text) {
  p._raw = text;
  const body = el("span", "body");
  const segs = segments(text);
  if (p.dataset.line === "say") body.append(whoTag(p), document.createTextNode(" "));
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
function who(p, tok, label) {
  p.dataset.tok = tok;
  p.dataset.label = label || "";
  p.style.setProperty("--c", inkVar(tok));
}
function sayBlock(tok, label, text, cut, event) {
  const p = el("p", "npc"); p.dataset.line = "say"; p.tabIndex = 0;
  who(p, tok, label);
  fillBody(p, text || "");
  if (cut) p.classList.add("cut");
  if (event != null) p.dataset.event = event;
  return p;
}
function actBlock(tok, label, text, event) {
  const p = el("p", "npc act"); p.dataset.line = "act"; p.tabIndex = 0;
  who(p, tok, label);
  if (event != null) p.dataset.event = event;
  p.append(whoTag(p), document.createTextNode(" "), el("span", "act-text", text));
  return p;
}
function narrBlock(text, cls = "narr") {
  const p = el("p", cls, text); p.dataset.line = cls === "intro" ? "intro" : "narr";
  if (cls === "narr") p.tabIndex = 0;   // the line menu (model error) is reachable by keyboard
  return p;
}
// what the player character read in an item: its own block, labelled with the item
function readBlock(label, text, found) {
  const p = el("div", "read" + (found === false ? " read-none" : ""));
  p.append(el("span", "read-label", label ? "Прочитано · " + label : "Прочитано"),
           el("span", "read-text", text));
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
  if (offered.includes("model_error") && x.lastWorld && (x.kind !== "act" || x.event) && !x.busy) out.push("model_error");
  if (offered.includes("cut") && x.kind === "say" && x.lastWorld && x.lastLine && !x.busy && !x.cut)
    out.push("cut");
  if (x.tok && (x.kind === "say" || x.kind === "act")) out.push("ink");
  // a rating of any world line (never the player's own); the line needs its id from the server
  if (x.event && ["say", "act", "narr"].includes(x.kind)) out.push("rate_up", "rate_down");
  return out;
}
const ITEM_TEXT = {
  challenge: "🔎 Звідки він це знає?", model_error: "⚠ Помилка моделі — переписати",
  cut: "✂ Перебити тут (заднім числом)", ink: "🎨 Чорнило цього персонажа",
  rate_up: "👍 Добре написано", rate_down: "👎 Погано написано",
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
  if (a === "rate_up") sendRating(p, "up", "");
  else if (a === "rate_down") openRateNote(p);
  else if (a === "challenge") openAsk(p);
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

// 👍/👎 on a world line: collected while playing. A quiet mark after the line (data-rating), kept
// by the server (ratings.jsonl) and restored after a reload.
const RATE_KIND = { narr: "narr", say: "npc", act: "npc_act" };
const RATE_MARK = { up: "👍", down: "👎" };
function setMark(p, rating) {
  const old = p.querySelector(".rmark"); if (old) old.remove();
  if (!RATE_MARK[rating]) { delete p.dataset.rating; return; }
  p.dataset.rating = rating;
  const m = el("span", "rmark", " " + RATE_MARK[rating]);
  m.setAttribute("aria-label", rating === "up" ? "Оцінено: добре" : "Оцінено: погано");
  (p._body || p).appendChild(m);   // right after the words, before any answer box
}
function applyRatings(map) {
  for (const p of lines()) if (p.dataset.event && map[p.dataset.event]) setMark(p, map[p.dataset.event]);
}
async function loadRatings() {
  try { const r = await fetch("/api/ratings"); if (r.ok) applyRatings(await r.json()); }
  catch (e) { /* the marks are a nicety */ }
}
async function sendRating(p, rating, note) {
  let r, d = {};
  try {
    r = await fetch("/api/rate", { method: "POST", body: JSON.stringify({
      event: Number(p.dataset.event), kind: RATE_KIND[p.dataset.line], rating, note }) });
    if (!r.ok) d = await r.json();
  } catch (e) { r = { ok: false }; d = { error: "Немає зв'язку." }; }
  if (!r.ok) { showError(d.error || "Не вдалося зберегти оцінку."); return false; }
  setMark(p, rating);
  return true;
}
function openRateNote(p) {
  inlineBox(p, "Що не так? (можна пропустити)", "Надіслати", async (note, go, box) => {
    go.disabled = true;
    if (await sendRating(p, "down", note.value.trim())) box.remove(); else go.disabled = false;
  }, ["Пропустити", () => sendRating(p, "down", "")]);
}

// "Звідки він це знає?": the player marks a line as impossible; the engine checks the channels
function addAsk(block, event) { block.dataset.event = event; }
function inlineBox(block, placeholder, goText, onGo, skip) {   // skip: [label, fn] replaces «Скасувати»
  if (block.querySelector(".askbox")) return;
  const box = el("span", "askbox");
  const note = el("textarea"); note.rows = 2; note.placeholder = placeholder;
  const go = el("button", "btn primary", goText); go.type = "button";
  const cancel = el("button", "btn ghost", skip ? skip[0] : "Скасувати"); cancel.type = "button";
  cancel.addEventListener("click", () => { box.remove(); if (skip) skip[1](); });
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
// «Помилка моделі» and «Перебити тут»: shown only when the server offers them (state.actions).
// In the turn's slow lane the server waits for it, so the button says «Зачекайте…» meanwhile;
// true when it worked (the page is reloaded), false after an error (shown).
async function postAndReload(url, body) {
  let r, d = {};
  try { r = await fetch(url, { method: "POST", body: JSON.stringify(body) }); if (!r.ok) d = await r.json(); }
  catch (e) { r = { ok: false }; d = { error: "Немає зв'язку." }; }
  if (!r.ok) { showError(d.error || "Не вдалося."); return false; }
  load();
  return true;
}
function openModelError(block) {
  inlineBox(block, "Що саме не так? (обов'язково)", "Переписати", async (note, go) => {
    if (!note.value.trim()) { note.focus(); return; }
    const label = go.textContent;
    go.disabled = true; go.textContent = "Зачекайте…";
    const ok = await postAndReload("/api/model_error", { event: Number(block.dataset.event) || null, explanation: note.value.trim() });
    if (!ok) { go.disabled = false; go.textContent = label; }   // the player can try again
  });
}
// the cut points of a line: after each spoken word but the last; words of a *beat* are not
// spoken, so they are shown (without asterisks) but cannot be a cut point. `after` counts every
// word of the stored text, as the server does.
function cutPoints(raw) {
  const words = String(raw || "").split(/\s+/).filter(Boolean);
  let inBeat = false;
  const out = words.map((w, i) => {
    const opens = !inBeat && w.startsWith("*");
    const beat = inBeat || opens;
    const t = beat ? w.replace(/\*/g, "") : w;
    if (beat && (opens ? w.length > 1 && w.slice(1).includes("*") : w.includes("*"))) inBeat = false;
    else if (opens) inBeat = true;
    return { text: t, beat, after: i + 1 };
  }).filter((x) => x.text);
  const spoken = out.filter((x) => !x.beat);
  const lastSpoken = spoken.length ? spoken[spoken.length - 1].after : 0;
  return out.map((x) => ({ ...x, cut: !x.beat && x.after < lastSpoken }));
}
function openCut(block) {   // tap the word after which he is cut off
  const body = el("span", "body cutpick");
  body.appendChild(el("span", "note", "Торкніться слова, після якого перебити: "));
  const buttons = [];
  for (const w of cutPoints(block._raw)) {
    if (!w.cut) { body.append(el("span", w.beat ? "beat" : "cwx", w.text), document.createTextNode(" ")); continue; }
    const b = el("button", "cw", w.text); b.type = "button";
    b.addEventListener("click", async () => {
      buttons.forEach((x) => { x.disabled = true; });
      b.textContent = w.text + " (зачекайте…)";
      if (!(await postAndReload("/api/cut", { event: Number(block.dataset.event), after_words: w.after }))) {
        buttons.forEach((x) => { x.disabled = false; });
        b.textContent = w.text;
      }
    });
    buttons.push(b);
    body.append(b, document.createTextNode(" "));
  }
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
  $("btnIdea").hidden = on || !assistantOn;
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
  assistantOn = state.assistant !== false;
  $("btnIdea").hidden = busy || !assistantOn;
  lastTurnNodes = [];   // the paragraphs since the last player paragraph (the last turn)
  for (const t of state.transcript) {
    let n = null;
    if (t.kind === "intro") n = narrBlock(t.text, "intro");
    else if (t.kind === "player") { n = meBlock(t.text); lastTurnNodes = []; }
    else if (t.kind === "narr") {
      if (t.text && t.text.trim()) { n = narrBlock(t.text); if (t.event != null) n.dataset.event = t.event; }
    }
    else if (t.kind === "npc_act") n = actBlock(t.tok, t.label, t.text, t.event);
    else if (t.kind === "read") n = readBlock(t.label, t.text, t.found);
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
  read(e) { cur = add(readBlock(e.label, e.text, e.found)); streaming(null); },
  npc_act(e) { newSpeaker(e.tok); cur = add(actBlock(e.tok, e.label, e.text, e.event)); streaming(null); },
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
    const narrs = (turnEls[e.turn != null ? e.turn : curTurn] || []).filter((n) => n.dataset.line === "narr");
    (e.narr_lines || []).forEach((id, i) => { if (narrs[i]) narrs[i].dataset.event = id; });
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
    if (Array.isArray(e.actions)) actions = e.actions;   // what the server supports now
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
  reset() { load(); },   // a new campaign (from another tab too): the page starts over
};
// events of a turn whose text the transcript already holds (a reload during its slow lane)
const FEED_EVENTS = new Set(["turn_start", "read", "narr_start", "narr_word", "narr_end", "speaker", "npc_act", "word", "turn_done"]);

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
  loadRatings();
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
  let list = [], ok = false;
  try { const r = await fetch("/api/places"); if (r.ok) { list = await r.json(); ok = true; } } catch (e) { list = []; }
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
  // an answering endpoint with no places (a start off the map): say so instead of an empty list
  $("placesNone").hidden = !ok || ul.children.length > 0;
  $("placesSec").hidden = !ok;
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
// -- "Нова гра з файлу": paste or upload a game package, see what is set, then start --------
function openNewGame() {
  if ($("drawer").open) $("drawer").close();
  $("newGame").hidden = false;
  $("newGameHead").focus();
  loadBundled();
}
// the packages that come with the app: a tap puts the package in the box and checks it
async function loadBundled() {
  const list = $("pkgList");
  if (list.childElementCount) return;
  let items = [];
  try { const r = await fetch("/api/packages"); if (r.ok) items = await r.json(); } catch (e) { items = []; }
  for (const it of items) {
    const b = el("button", "ng-pick");
    b.type = "button"; b.dataset.id = it.id;
    b.append(el("b", "", it.title));
    if (it.pitch) b.append(el("span", "", it.pitch));
    b.addEventListener("click", () => { $("pkgText").value = it.text; checkPackage(); });
    const li = el("li"); li.appendChild(b); list.appendChild(li);
  }
  $("pkgBundled").hidden = !items.length;
}
function closeNewGame() { $("newGame").hidden = true; $("btnMenu").focus(); }
function pkgErrors(list) {
  const box = el("div");
  box.appendChild(el("p", "note", "У файлі є помилки. Виправте їх (або попросіть про це ШІ-помічника) і перевірте ще раз."));
  for (const i of list) {
    const p = el("p", "ng-err");
    p.append(el("b", "", i.field), document.createTextNode(" — " + i.problem));
    p.appendChild(el("span", "fix", "Як виправити: " + i.fix));
    box.appendChild(p);
  }
  return box;
}
function pkgCard(s) {
  const card = el("div", "ng-card");
  card.appendChild(el("h3", "", s.title));
  card.appendChild(el("h4", "", "Задано у файлі"));
  const dl = el("dl");
  for (const it of s.set) { dl.append(el("dt", "", it.label), el("dd", "", it.value)); }
  card.appendChild(dl);
  card.appendChild(el("h4", "", "Вирішить світ"));
  if (s.world.length) {
    const ul = el("ul");
    for (const w of s.world) ul.appendChild(el("li", "", w));
    card.appendChild(ul);
  } else card.appendChild(el("p", "note", "Нічого: усе важливе задано у файлі."));
  if (s.warnings.length) {
    card.appendChild(el("h4", "", "Зауваження"));
    for (const w of s.warnings) {
      const p = el("p", "ng-warn");
      p.append(el("b", "", w.field), document.createTextNode(" — " + w.problem + " " + w.fix));
      card.appendChild(p);
    }
  }
  const go = el("button", "btn primary wide", "Почати гру");
  go.type = "button"; go.id = "pkgStart";
  go.addEventListener("click", () => startPackage(go));
  card.appendChild(go);
  card.appendChild(el("p", "note", "Поточна пригода збережеться на диску, але гра перейде на нову."));
  return card;
}
async function checkPackage() {
  const out = $("pkgResult");
  const text = $("pkgText").value;
  if (!text.trim()) { out.replaceChildren(el("p", "note", "Спершу вставте або завантажте файл гри.")); return; }
  out.replaceChildren(el("p", "note", "Перевіряю…"));
  try {
    const r = await fetch("/api/package/check", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
    const d = await r.json();
    out.replaceChildren(d.ok ? pkgCard(d.summary) : pkgErrors(d.errors || []));
    out.scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  } catch (e) { out.replaceChildren(el("p", "ng-err", "Не вдалося перевірити файл: немає зв'язку із застосунком.")); }
}
async function startPackage(btn) {
  btn.disabled = true; btn.textContent = "Світ готується…";
  let r, d = {};
  try {
    r = await fetch("/api/package/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: $("pkgText").value }) });
    d = await r.json();
  } catch (e) { r = null; }
  if (r && r.ok) {
    $("newGame").hidden = true; $("pkgResult").textContent = "";
    $("finale").hidden = true; $("composer").hidden = false;
    cast = {}; load();
    return;
  }
  btn.disabled = false; btn.textContent = "Почати гру";
  if (d.errors) $("pkgResult").replaceChildren(pkgErrors(d.errors));
  else $("pkgResult").appendChild(el("p", "ng-err", d.error || "Не вдалося почати гру."));
}
$("btnNewGame").addEventListener("click", openNewGame);
$("newGameClose").addEventListener("click", closeNewGame);
$("newGame").addEventListener("keydown", (ev) => { if (ev.key === "Escape") closeNewGame(); });
$("pkgCheck").addEventListener("click", checkPackage);
$("pkgText").addEventListener("input", () => { $("pkgResult").textContent = ""; });
$("pkgFile").addEventListener("change", async () => {
  const f = $("pkgFile").files[0];
  if (!f) return;
  $("pkgText").value = await f.text();
  $("pkgFile").value = "";
  checkPackage();
});
$("btnNames").addEventListener("click", () => {
  const on = !document.body.classList.contains("names");
  setNames(on); store("names", on ? "1" : "0");
});
setNames(store("names") !== "0");   // default on; the choice is per device
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
