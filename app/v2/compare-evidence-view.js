/* JEG-1271: isolated Fieldnotes Compare evidence view (part of JEG-1138). Contract:
   docs/design/compare-evidence-view-contract.md.

   Presentation only. It renders outputs that already exist (trade.js dealRead, compareTrade rows,
   tradeVerdict's againstKeys, explanation and disclosure text) and computes nothing: no sums, no sides,
   no thresholds, no confidence, no ranking and no choice of a winning view. Every word on screen comes
   from the injected input (its `copy`, labels, verdict text, names and explanation); the only things
   this file adds are the two number formats copied from v2.js (fmtGap, fmt) and a few separators.
   It reads no engine, storage, network, route or share state, and never writes to its input.

   The shared trade readout (JEG-1260 owns it) goes in an opaque slot: the caller fills it once and
   this view never reads, clears or rebuilds what is inside it.

   Layers, so JEG-1274 can reuse the internals for its detail slot:
     adapt(input)          -> model (validates the contract; throws on a violation)
     tree(model, state)    -> plain {tag, attrs, children | text} nodes; pure, testable without a DOM
     toDom(doc, node)      -> DOM
     mount(root, input, o) -> {update(input), destroy(), readoutSlot}; keeps open disclosures and focus
   and the parts tree() is built from: verdictTree, netsTree, evidenceGroupTree, disclosureTree. */
(function (root) {
  "use strict";

  // v2.js fmtGap (signed net, true minus sign, a rounding residue shows as 0.0) and fmt (a value).
  // tests/test_compare_evidence_view_contract.py checks both against the v2.js source.
  const fmtGap = gap => {
    if (!Number.isFinite(gap)) return "—";
    const text = Math.abs(gap).toFixed(1);
    if (text === "0.0") return "0.0";
    return `${gap > 0 ? "+" : "−"}${text}`;
  };
  const fmt = v => { if (!Number.isFinite(v)) return "—"; const text = v.toFixed(1); return text === "-0.0" ? "0.0" : text.replace("-", "−"); };
  // The only text this file writes itself.
  const SEPARATORS = Object.freeze([" · ", " (", ")", ": ", " ", ", "]);

  const SIDES = ["win", "even", "lose"];
  const NET_IDS = ["value", "market", "projections"];
  const COPY_KEYS = ["sideWords", "missingValue", "tooFewCharts", "chartsSplit", "rangeJoin", "noValue", "held",
    "give", "receive", "directions", "conflicting", "verdictHeading", "evidenceHeading", "explanationHeading"];
  const finite = n => typeof n === "number" && Number.isFinite(n);
  const isText = s => typeof s === "string" && s.trim().length > 0;

  function fail(message) { throw new Error(`compare-evidence-view: ${message}`); }
  function need(cond, message) { if (!cond) fail(message); }

  // ---- adapt: check the contract and pick fields. Reads only; never copies a value into a new number.
  function adapt(input) {
    need(input && typeof input === "object", "input must be an object");
    need(typeof input.synthetic === "boolean", "synthetic must be stated true or false");
    if (input.synthetic) need(isText(input.syntheticLabel), "a synthetic input needs a visible syntheticLabel");
    const copy = input.copy;
    need(copy && typeof copy === "object", "copy is required");
    COPY_KEYS.forEach(key => need(copy[key] !== undefined, `copy.${key} is required`));
    SIDES.forEach(side => need(isText(copy.sideWords[side]), `copy.sideWords.${side} is required`));
    ["up", "down", "even"].forEach(d => need(isText(copy.directions[d]), `copy.directions.${d} is required`));

    const verdict = adaptVerdict(input.verdict, input.nets);
    const seen = new Set();
    need(Array.isArray(input.groups) && input.groups.length > 0, "groups are required");
    const againstKeys = Array.isArray(input.againstKeys) ? input.againstKeys : [];
    const groupIds = new Set();
    const groups = input.groups.map(group => {
      need(isText(group.id) && !groupIds.has(group.id), `group ids must be distinct (${group && group.id})`);
      groupIds.add(group.id);
      need(isText(group.label), `group ${group.id} needs a label`);
      need(Array.isArray(group.rows), `group ${group.id} needs rows`);
      return {id: group.id, label: group.label, note: isText(group.note) ? group.note : null,
        rows: group.rows.map(row => {
          need(isText(row.key) && !seen.has(row.key), `series ${row && row.key} must appear in exactly one group`);
          seen.add(row.key);
          return adaptRow(row, againstKeys.includes(row.key));
        })};
    });
    const explanation = (input.explanation || []).map(line => { need(isText(line), "explanation lines must be text"); return line; });
    const disclosureIds = new Set();
    const disclosures = (input.disclosures || []).map(d => {
      need(isText(d.id) && !disclosureIds.has(d.id) && /^[a-z0-9-]+$/.test(d.id), `disclosure ids must be distinct slugs (${d && d.id})`);
      disclosureIds.add(d.id);
      need(isText(d.summary), `disclosure ${d.id} needs a summary`);
      need(Array.isArray(d.lines) && d.lines.every(isText), `disclosure ${d.id} lines must be text`);
      return {id: d.id, summary: d.summary, lines: d.lines.slice()};
    });
    return {synthetic: input.synthetic, syntheticLabel: input.synthetic ? input.syntheticLabel : null,
      copy, verdict, groups, explanation, disclosures};
  }

  function adaptVerdict(deal, nets) {
    need(deal && (deal.kind === "read" || deal.kind === "incomplete"), "verdict.kind must be read or incomplete");
    need(isText(deal.text), "verdict.text is required");
    need(Array.isArray(nets) && nets.length === NET_IDS.length, "nets must name value, market and projections");
    const netRows = nets.map(spec => {
      need(NET_IDS.includes(spec.id) && isText(spec.name), `net ${spec && spec.id} needs a known id and a name`);
      const n = deal[spec.id];
      need(n && typeof n === "object", `verdict.${spec.id} is missing`);
      need(n.net === null || finite(n.net), `verdict.${spec.id}.net must be a number or null`);
      if (n.net !== null && !n.split) need(SIDES.includes(n.side), `verdict.${spec.id}.side must be win, even or lose`);
      if (n.split) need(n.charts && finite(n.charts.min) && finite(n.charts.max), `verdict.${spec.id}.charts min and max are required for a split`);
      return {id: spec.id, name: spec.name, question: isText(spec.question) ? spec.question : null,
        net: n.net, side: n.net === null ? null : n.side, tooFew: Boolean(n.tooFew), split: Boolean(n.split),
        min: n.split ? n.charts.min : null, max: n.split ? n.charts.max : null};
    });
    // Same title rule as v2.js renderDeal (JEG-841): add the action unless the title already holds it.
    let title = null;
    if (deal.kind === "read") {
      need(isText(deal.title) && typeof deal.action === "string", "a read needs a title and an action");
      title = deal.title.toLowerCase().includes(deal.action.toLowerCase()) ? [deal.title] : [deal.title, deal.action];
    }
    return {kind: deal.kind, cell: deal.kind === "read" ? deal.cell || null : null, title, text: deal.text,
      production: isText(deal.production) ? deal.production : null, nets: netRows};
  }

  // A series row: compareTrade's {key, give, receive, net, missing}, its label, and an optional hold.
  //   held        the source is held (its values are hidden); show the supplied reason, no number
  //   missing     net is null: a player has no value here; never shown as 0
  //   zero        net is exactly 0, a real value
  //   complete    any other number
  //   conflicting a complete row named in tradeVerdict's againstKeys (it points the other way)
  function adaptRow(row, against) {
    need(isText(row.label), `series ${row.key} needs a label`);
    need(row.net === null || finite(row.net), `series ${row.key} net must be a number or null`);
    const missing = Array.isArray(row.missing) ? row.missing : [];
    if (row.held) {
      need(isText(row.held.reason), `held series ${row.key} needs a reason`);
      return {key: row.key, label: row.label, state: "held", heldReason: row.held.reason,
        net: null, give: null, receive: null, missing: [], conflicting: false};
    }
    if (row.net === null) {
      need(missing.length > 0, `series ${row.key} has no net and names nobody missing`);
      return {key: row.key, label: row.label, state: "missing", heldReason: null,
        net: null, give: null, receive: null, conflicting: false,
        missing: missing.map(m => { need(m && m.row && isText(m.row.name), `series ${row.key} missing entries need a player name`); return {name: m.row.name, side: m.side}; })};
    }
    need(finite(row.give) && finite(row.receive), `series ${row.key} needs give and receive totals`);
    return {key: row.key, label: row.label, state: row.net === 0 ? "zero" : "complete", heldReason: null,
      net: row.net, give: row.give, receive: row.receive, missing: [], conflicting: Boolean(against) && row.net !== 0};
  }

  // ---- tree: plain nodes. text nodes are {text}; elements {tag, attrs, children}.
  const el = (tag, attrs, children) => ({tag, attrs: attrs || {}, children: (children || []).filter(Boolean)});
  const tx = text => ({text});

  // Same reading as v2.js netLabel: the shown text decides "even", not the raw sign.
  function direction(net, copy) {
    const text = fmtGap(net);
    if (text === "0.0") return {cls: "even", label: copy.directions.even};
    return net > 0 ? {cls: "up", label: copy.directions.up} : {cls: "down", label: copy.directions.down};
  }

  function netValueNodes(n, copy) {
    if (n.net === null) return [tx(n.tooFew ? copy.tooFewCharts : copy.missingValue)];
    if (n.split) return [tx(fmtGap(n.net)), tx(" · "), tx(copy.chartsSplit), tx(" ("), tx(fmtGap(n.min)), tx(" "), tx(copy.rangeJoin), tx(" "), tx(fmtGap(n.max)), tx(")")];
    return [tx(fmtGap(n.net)), tx(" · "), tx(copy.sideWords[n.side])];
  }

  function netsTree(nets, copy) {
    return el("ul", {class: "cev-nets"}, nets.map(n => el("li", {class: "cev-net", "data-net": n.id, "data-side": n.side || "", "data-state": n.net === null ? (n.tooFew ? "too-few" : "missing") : n.split ? "split" : "complete"}, [
      el("span", {class: "cev-net-name"}, [tx(n.name)]),
      el("b", {class: "cev-net-value"}, netValueNodes(n, copy)),
      n.question ? el("span", {class: "cev-net-question"}, [tx(n.question)]) : null
    ])));
  }

  function verdictTree(model) {
    const v = model.verdict;
    const copy = model.copy;
    const title = v.title ? el("p", {class: "cev-verdict-title ddf-fn-display"}, v.title.length === 2 ? [tx(v.title[0]), tx(": "), tx(v.title[1])] : [tx(v.title[0])]) : null;
    return el("section", {class: "cev-verdict", "data-verdict": v.kind, "data-cell": v.cell || "", "aria-label": copy.verdictHeading}, [
      el("h3", {class: "cev-heading"}, [tx(copy.verdictHeading)]),
      title,
      el("p", {class: "cev-verdict-text"}, [tx(v.text)]),
      v.production ? el("p", {class: "cev-verdict-production"}, [tx(v.production)]) : null,
      netsTree(v.nets, copy)
    ]);
  }

  function rowTree(row, copy) {
    const name = el("span", {class: "cev-row-name"}, [tx(row.label)]);
    let body;
    if (row.state === "held") {
      body = [el("b", {class: "cev-row-value"}, [tx(copy.held)]), el("span", {class: "cev-row-detail"}, [tx(row.heldReason)])];
    } else if (row.state === "missing") {
      const who = [];
      row.missing.forEach((m, i) => { if (i) who.push(tx(", ")); who.push(tx(m.name), tx(" "), tx(copy.noValue)); });
      body = [el("b", {class: "cev-row-value"}, [tx(copy.missingValue)]), el("span", {class: "cev-row-detail"}, who)];
    } else {
      const d = direction(row.net, copy);
      body = [
        el("b", {class: "cev-row-value", "data-dir": d.cls}, [tx(fmtGap(row.net))]),
        el("span", {class: "cev-row-direction"}, [tx(d.label)]),
        el("span", {class: "cev-row-detail"}, [tx(copy.give), tx(" "), tx(fmt(row.give)), tx(" · "), tx(copy.receive), tx(" "), tx(fmt(row.receive))]),
        row.conflicting ? el("span", {class: "cev-row-flag"}, [tx(copy.conflicting)]) : null
      ];
    }
    return el("li", {class: "cev-row", "data-series": row.key, "data-state": row.state, "data-conflicting": row.conflicting ? "true" : "false"}, [name].concat(body));
  }

  // One group per source category (JEG-1212). Groups sit side by side with equal weight, in input order;
  // nothing totals across them and nothing marks one as preferred.
  function evidenceGroupTree(group, copy) {
    return el("section", {class: "cev-group", "data-group": group.id, "aria-label": group.label}, [
      el("h4", {class: "cev-group-label"}, [tx(group.label)]),
      group.note ? el("p", {class: "cev-group-note"}, [tx(group.note)]) : null,
      el("ul", {class: "cev-rows"}, group.rows.map(row => rowTree(row, copy)))
    ]);
  }

  function disclosureTree(d, idBase, open) {
    const btnId = `${idBase}-d-${d.id}`;
    const panelId = `${btnId}-panel`;
    return el("div", {class: "cev-disclosure", "data-disclosure": d.id}, [
      el("button", {type: "button", class: "cev-disclosure-toggle ddf-fn-focus", id: btnId, "aria-expanded": open ? "true" : "false",
        "aria-controls": panelId, "data-cev-focus": `d-${d.id}`}, [el("span", {}, [tx(d.summary)])]),
      el("div", {class: "cev-disclosure-panel", id: panelId, role: "region", "aria-labelledby": btnId, hidden: open ? null : ""},
        d.lines.map(line => el("p", {}, [tx(line)])))
    ]);
  }

  function tree(model, state) {
    const open = (state && state.open) || new Set();
    const idBase = (state && state.idBase) || "cev";
    const copy = model.copy;
    return el("article", {class: "cev", "data-synthetic": model.synthetic ? "true" : "false"}, [
      model.synthetic ? el("p", {class: "cev-synthetic", role: "note"}, [tx(model.syntheticLabel)]) : null,
      verdictTree(model),
      el("div", {class: "cev-readout", "data-cev-slot": "readout"}, []),
      el("section", {class: "cev-evidence", "aria-label": copy.evidenceHeading}, [
        el("h3", {class: "cev-heading"}, [tx(copy.evidenceHeading)]),
        el("div", {class: "cev-groups"}, model.groups.map(g => evidenceGroupTree(g, copy)))
      ]),
      model.explanation.length || model.disclosures.length ? el("section", {class: "cev-explain", "aria-label": copy.explanationHeading}, [
        el("h3", {class: "cev-heading"}, [tx(copy.explanationHeading)]),
        ...model.explanation.map(line => el("p", {class: "cev-explain-line"}, [tx(line)])),
        ...model.disclosures.map(d => disclosureTree(d, idBase, open.has(d.id)))
      ]) : null
    ]);
  }

  // Every text node in reading order (the contract test checks each one against the input).
  function texts(node, out) {
    out = out || [];
    if ("text" in node) out.push(node.text);
    else node.children.forEach(child => texts(child, out));
    return out;
  }

  function toDom(doc, node) {
    if ("text" in node) return doc.createTextNode(node.text);
    const element = doc.createElement(node.tag);
    Object.entries(node.attrs).forEach(([name, value]) => { if (value !== null && value !== undefined) element.setAttribute(name, value); });
    node.children.forEach(child => element.appendChild(toDom(doc, child)));
    return element;
  }

  // ---- mount: render into root; update() re-renders with new input and keeps which disclosures are open,
  // where focus was, and the readout slot node (moved, never rebuilt or read).
  let instances = 0;
  function mount(rootEl, input, options) {
    const doc = rootEl.ownerDocument;
    const idBase = `cev${++instances}`;
    const open = new Set();
    const slot = doc.createElement("div");
    slot.className = "cev-readout";
    slot.setAttribute("data-cev-slot", "readout");
    if (options && typeof options.readout === "function") options.readout(slot);
    let current = null;

    function onClick(event) {
      const button = event.target.closest && event.target.closest(".cev-disclosure-toggle");
      if (!button || !current || !current.contains(button)) return;
      const id = button.closest("[data-disclosure]").getAttribute("data-disclosure");
      const panel = doc.getElementById(button.getAttribute("aria-controls"));
      const opening = button.getAttribute("aria-expanded") !== "true";
      if (opening) open.add(id); else open.delete(id);
      button.setAttribute("aria-expanded", opening ? "true" : "false");
      panel.hidden = !opening;
    }

    function render(next) {
      const model = adapt(next);
      const active = doc.activeElement;
      const focusId = current && active && current.contains(active) ? active.getAttribute("data-cev-focus") : null;
      const ids = new Set(model.disclosures.map(d => d.id));
      [...open].forEach(id => { if (!ids.has(id)) open.delete(id); });
      const fresh = toDom(doc, tree(model, {open, idBase}));
      fresh.querySelector('[data-cev-slot="readout"]').replaceWith(slot);
      if (current) current.replaceWith(fresh); else rootEl.appendChild(fresh);
      current = fresh;
      if (focusId) {
        const target = fresh.querySelector(`[data-cev-focus="${focusId}"]`);
        if (target) target.focus();
      }
      return model;
    }

    rootEl.addEventListener("click", onClick);
    render(input);
    return {
      update: render,
      readoutSlot: slot,
      element: () => current,
      destroy() { rootEl.removeEventListener("click", onClick); if (current) current.remove(); current = null; }
    };
  }

  const api = {adapt, tree, texts, toDom, mount, verdictTree, netsTree, evidenceGroupTree, disclosureTree,
    format: Object.freeze({gap: fmtGap, value: fmt}), SEPARATORS};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.CompareEvidenceView = api;
})(typeof window !== "undefined" ? window : globalThis);
