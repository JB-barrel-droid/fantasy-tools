// JEG-1304: the USO journey's pair-finder group reader (PAIR_GROUP in tests/test_uso_site_journey_render.py) on group
// cards drawn the way app/v2/finder.js groupCard draws them. A group with one give candidate and nothing optional to
// receive is not selectable there: it draws no checkboxes, and only its Open in Compare link names the give player.
//
// Usage: node uso_journey_pair_group.cjs <pair_group.json>
// Prints {fixed, selectable, otherGive} as one JSON line: for each package, the group that matched and what it reads.
"use strict";
const fs = require("fs");

class Element_ {
  constructor(tag, attrs = {}, ...kids) {
    this.tagName = tag.toUpperCase(); this.attrs = {}; this.dataset = {}; this.childNodes = []; this.parentNode = null;
    this.checked = false; this.disabled = false;
    Object.entries(attrs).forEach(([k, v]) => this.setAttribute(k, v));
    kids.forEach(k => { if (typeof k === "string") k = {textContent: k, isText: true}; k.parentNode = this; this.childNodes.push(k); });
  }
  setAttribute(k, v) {
    this.attrs[k] = String(v);
    if (k.startsWith("data-")) this.dataset[k.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = String(v);
  }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  get textContent() { return this.childNodes.map(c => c.textContent).join(""); }
  descendants() { return this.childNodes.filter(c => !c.isText).flatMap(c => [c, ...c.descendants()]); }
  closest(sel) { for (let n = this; n && n.tagName; n = n.parentNode) if (n.tagName === sel.toUpperCase()) return n; return null; }
  querySelectorAll(sel) {
    const all = this.descendants();
    if (sel === "input[data-key]") return all.filter(e => e.tagName === "INPUT" && "data-key" in e.attrs);
    if (sel === "legend") return all.filter(e => e.tagName === "LEGEND");
    if (sel === 'a[href*="compare-trade"]') return all.filter(e => e.tagName === "A" && (e.getAttribute("href") || "").includes("compare-trade"));
    throw new Error(`selector not modeled here: ${sel}`);
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
}
const el = (tag, attrs, ...kids) => new Element_(tag, attrs, ...kids);

// groupCard's sideSet: a fieldset with a legend and one ticked-or-not checkbox row per player.
const sideSet = (title, keys, ticked) => el("fieldset", {class: "v2-find-side-pick"}, el("legend", {}, title),
  ...keys.map(k => { const input = el("input", {type: "checkbox", "data-key": k, "aria-label": `Include ${k} (value 10.0)`});
    input.checked = ticked.includes(k); return el("label", {class: "v2-find-pick-row"}, input, el("span", {}, `${k} `)); }));
// groupCard: target, trade label, meta, fit line, notes, the side sets when selectable, cap note, Open in Compare.
const card = ({heavy, give, giveCandidates = [], receiveSide = [], recvTicked = []}) => {
  const selectable = giveCandidates.length > 1 || receiveSide.length > 0;
  const ids = keys => keys.map(encodeURIComponent).join(",");
  return el("li", {class: "v2-find-group", "data-group": heavy.join(",")},
    el("span", {class: "v2-find-target"}, `Target: ${heavy.join(", ")} · 40.0 DDF Value`),
    el("b", {class: "v2-find-trade"}, `You give ${give.join(", ")}; you receive ${heavy.join(", ")}`),
    el("span", {class: "v2-meta v2-find-edge"}), el("p", {class: "v2-find-fit"}), el("span", {class: "v2-meta v2-find-notes"}),
    ...(selectable ? [sideSet("You give", giveCandidates, give)] : []),
    ...(receiveSide.length ? [sideSet("You also receive (core stays)", receiveSide, recvTicked)] : []),
    el("span", {class: "v2-meta v2-find-cap"}),
    el("a", {class: "v2-link", href: `v2/#compare-trade?give=${ids(give)}&get=${ids(heavy.concat(recvTicked))}`}, "Open in Compare a trade"));
};

const src = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
// eslint-disable-next-line no-eval
const reader = eval(`(() => {${src} return {matches, packageOf}; })`)();
const groups = [
  card({heavy: ["ken-walker"], give: ["jsn"]}),                                         // one give candidate, nothing optional
  card({heavy: ["drake-london"], give: ["jsn"], giveCandidates: ["jsn", "kyren"]}),       // two give candidates
  card({heavy: ["ken-walker"], give: ["kyren"]}),                                        // same core, another fixed give
];
const read = (give, get) => {
  const at = groups.findIndex(g => reader.matches(g, new Set(give.concat(get))));
  return {group: at, ...(at < 0 ? {} : reader.packageOf(groups[at]))};
};
process.stdout.write(JSON.stringify({fixed: read(["jsn"], ["ken-walker"]), selectable: read(["jsn"], ["drake-london"]),
  otherGive: read(["kyren"], ["ken-walker"]), unlisted: read(["allen"], ["ken-walker"])}) + "\n");
