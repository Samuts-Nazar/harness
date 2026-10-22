// Runs app/static/app.js against a minimal DOM stub (used by test_app_client.py).
//   node client_harness.js app.js '<events JSON>'            replay events, print the feed
//   node client_harness.js app.js '{"state"|"load": …, "events": […], "eval": "<expr>"}'
//     ("load": as a page reload does, events then pass the reload's replay filter)
//     render a /api/state body first, then replay events; "eval" is evaluated in the app's
//     scope and its value is printed as "value".
"use strict";
const fs = require("fs"), vm = require("vm");
function node(tag) {
  const n = { tag, className: "", children: [], dataset: {}, hidden: false, value: "", disabled: false,
    textContent: "", classList: { _s: new Set(), add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
      toggle(c, on) { on ? this._s.add(c) : this._s.delete(c); }, contains(c) { return this._s.has(c); } },
    style: { setProperty(k, v) { this[k] = v; } }, scrollTop: 0, scrollHeight: 0, clientHeight: 0, parent: null,
    appendChild(c) { c.parent = this; this.children.push(c); return c; },
    append(...cs) { for (const c of cs) this.appendChild(typeof c === "object" ? c : { textContent: String(c), children: [] }); },
    remove() { if (this.parent) this.parent.children = this.parent.children.filter((x) => x !== this); this.parent = null; },
    replaceWith(c) { const p = this.parent; if (!p) return; p.children[p.children.indexOf(this)] = c; c.parent = p; this.parent = null; },
    querySelector() { return null; }, setAttribute() {}, focus() {},
    _l: {}, addEventListener(t, f) { (this._l[t] = this._l[t] || []).push(f); },
    click() { return Promise.all((this._l.click || []).map((f) => f({ target: this }))); },
    requestSubmit() {} };
  return n;
}
const ids = {};
const document = { getElementById: (id) => (ids[id] = ids[id] || node("div")),
  createElement: (t) => node(t), createTextNode: (t) => ({ textContent: t, children: [] }),
  createDocumentFragment: () => node("frag"), addEventListener() {}, visibilityState: "visible",
  documentElement: node("html"), body: node("body") };
const ctx = { document, window: { addEventListener() {} }, navigator: {}, console,
  fetch: () => new Promise(() => {}), EventSource: function () { this.addEventListener = () => {}; this.close = () => {}; },
  confirm: () => false, JSON, setTimeout, clearTimeout, getComputedStyle: () => ({ getPropertyValue: () => "" }) };
ctx.EventSource.CLOSED = 2;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[2], "utf8") +
  "\nthis.__h = handlers; this.__state = () => ({ busy }); this.__render = render;" +
  "\nthis.__load = (st) => { render(st); turnEls = {}; cur = null; beginReplay(st); }; this.__dispatch = dispatch;" +
  "\nthis.__eval = (s) => eval(s);", ctx);
let job = JSON.parse(process.argv[3]);
if (Array.isArray(job)) job = { events: job };
if (job.state) ctx.__render(job.state);
if (job.load) ctx.__load(job.load);   // as after a reload: events go through the replay filter
for (const e of job.events || []) (job.load ? ctx.__dispatch : (t, ev) => ctx.__h[t](ev))(e.type, e);
(async () => {
const value = job.eval ? await ctx.__eval(job.eval) : null;
const feed = ids.feed;
const text = (n) => (n.textContent || "") + (n.children || []).map(text).join("");
console.log(JSON.stringify({ feed: feed.children.map((n) => ({ cls: n.className, line: n.dataset.line,
  tok: n.dataset.tok, cut: n.classList.contains("cut"), event: n.dataset.event, text: text(n),
  q: (n.children || []).flatMap((c) => c.children || []).filter((c) => c.className === "q").map((c) => c.textContent),
  beat: (n.children || []).flatMap((c) => c.children || []).filter((c) => c.className === "beat").map((c) => c.textContent),
  ink: n.style && n.style["--c"] })),
  busy: ctx.__state().busy, input: ids.input.value, root: document.documentElement.style,
  value }));
})();
