// Runs app/static/app.js against a minimal DOM stub and replays events given as JSON on argv[2];
// prints what the feed holds afterwards (used by test_app_client.py).
"use strict";
const fs = require("fs"), vm = require("vm");
function node(tag) {
  const n = { tag, className: "", children: [], dataset: {}, hidden: false, value: "", disabled: false,
    textContent: "", classList: { _s: new Set(), add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
      toggle(c, on) { on ? this._s.add(c) : this._s.delete(c); }, contains(c) { return this._s.has(c); } },
    style: {}, scrollTop: 0, scrollHeight: 0, clientHeight: 0, parent: null,
    appendChild(c) { c.parent = this; this.children.push(c); return c; },
    append(...cs) { for (const c of cs) if (typeof c === "object") this.appendChild(c); },
    remove() { if (this.parent) this.parent.children = this.parent.children.filter((x) => x !== this); this.parent = null; },
    querySelector() { return null; }, addEventListener() {}, setAttribute() {}, focus() {},
    requestSubmit() {} };
  return n;
}
const ids = {};
const document = { getElementById: (id) => (ids[id] = ids[id] || node("div")),
  createElement: (t) => node(t), createTextNode: (t) => ({ textContent: t }),
  createDocumentFragment: () => node("frag"), addEventListener() {}, visibilityState: "visible" };
const ctx = { document, window: { addEventListener() {} }, navigator: {}, console,
  fetch: () => new Promise(() => {}), EventSource: function () { this.addEventListener = () => {}; this.close = () => {}; },
  confirm: () => false, JSON };
ctx.EventSource.CLOSED = 2;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[2], "utf8") + "\nthis.__h = handlers; this.__state = () => ({ busy });", ctx);
for (const e of JSON.parse(process.argv[3])) ctx.__h[e.type](e);
const feed = ids.feed;
const text = (n) => n.textContent + n.children.map(text).join("");
console.log(JSON.stringify({ feed: feed.children.map((n) => ({ cls: n.className, text: text(n) })),
  busy: ctx.__state().busy, input: ids.input.value }));
