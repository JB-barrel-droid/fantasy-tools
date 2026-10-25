// Value overrides tab (JEG-1035).
//
// Jeremy, 2026-10-24: "select a player and say their ddf is actually a different value. Make it interactive so
// it opens a graph and as you drag the selector it shows the players that player is comparable to. Make it have
// a default filter for same position ... adjust as many players as we want to and have it permeate through the
// full dashboard."
//
// The engine owns the math: TradeValueCurveControls.setValueOverrides({player_key: value}) replaces DDF Value on
// those players' rows, and every view reads rows. This module only picks the values (search, a graph with a
// draggable value line, the players nearest that value) and keeps them in the browser (localStorage).
//
// Contract: window.DDFOverrides = {boot(engine), render(), count(), all()}.
//   boot(engine)  v2.js calls it once the engine is ready, before the first view renders, so saved overrides
//                 apply everywhere from the first paint.
//   render()      v2.js calls it when the Overrides tab shows; idempotent.
(function (root) {
  "use strict";

  const SAVE_KEY = "ddf-v2-value-overrides";
  const POSITIONS = ["QB", "RB", "WR", "TE"];
  const NEAR = 4;   // comparable players shown above and below the chosen value

  const S = {engine: null, values: {}, names: {}, selected: null, draft: null, scope: "pos", query: "", dragging: false};

  const $ = id => document.getElementById(id);
  const finite = v => typeof v === "number" && Number.isFinite(v);
  const fmt = v => (finite(v) ? (Math.abs(v) < 0.05 ? "0.0" : v.toFixed(1)) : "—");
  const signed = v => (finite(v) ? (Math.abs(v) < 0.05 ? "±0.0" : (v > 0 ? "+" : "−") + Math.abs(v).toFixed(1)) : "—");
  const round1 = v => Math.round(v * 10) / 10;
  function el(tag, attrs, kids) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (v === null || v === undefined || v === false) return;
      if (k === "text") node.textContent = v;
      else if (k === "class") node.className = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    });
    (kids || []).forEach(kid => kid !== null && kid !== undefined && node.append(kid));
    return node;
  }
  const SVG_NS = "http://www.w3.org/2000/svg";
  function svg(tag, attrs, text) {
    const node = document.createElementNS(SVG_NS, tag);
    Object.entries(attrs || {}).forEach(([k, v]) => node.setAttribute(k, v));
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // ---------- storage ----------
  function load() {
    try {
      const saved = JSON.parse(localStorage.getItem(SAVE_KEY) || "null");
      if (saved && saved.v === 1 && saved.values && typeof saved.values === "object") {
        S.values = {};
        Object.entries(saved.values).forEach(([k, v]) => { if (finite(v) && v >= 0) S.values[k] = v; });
        S.names = saved.names && typeof saved.names === "object" ? saved.names : {};
      }
    } catch (error) { /* private mode or bad JSON: start empty */ }
  }
  function save() {
    try { localStorage.setItem(SAVE_KEY, JSON.stringify({v: 1, values: S.values, names: S.names})); }
    catch (error) { /* the overrides still apply for this visit */ }
  }

  // ---------- engine ----------
  const rows = () => (S.engine ? S.engine.getAllRows() : []);
  const rowOf = key => {
    const hit = rows().find(r => String(r.player_key) === String(key));
    if (hit) return hit;
    const found = S.engine && S.engine.searchPlayers ? S.engine.searchPlayers(S.names[key] || "", {limit: 20}) : [];
    return found.find(r => String(r.player_key) === String(key)) || null;
  };
  // The model's DDF Value for a row, before any override.
  const modelValue = row => (row ? (finite(row.ddfPipelineValue) ? row.ddfPipelineValue : (row.valueOverride === null || row.valueOverride === undefined ? row.values.ddf_value : null)) : null);
  function push() {
    if (!S.engine || typeof S.engine.setValueOverrides !== "function") return;
    S.engine.setValueOverrides(S.values);
    save();
    syncBadge();
  }
  function setOverride(key, value, name) {
    if (value === null) delete S.values[key];
    else S.values[key] = round1(Math.max(0, value));
    if (name) S.names[key] = name;
    if (value === null) delete S.names[key];
    push();
  }

  // ---------- header badge (every view) ----------
  function syncBadge() {
    const n = Object.keys(S.values).length;
    let badge = $("v2OverrideBadge");
    const host = $("v2Freshness");
    if (!badge && host && host.parentNode) {
      badge = el("a", {id: "v2OverrideBadge", class: "v2-ov-badge", href: "v2/#value-overrides"});
      host.parentNode.insertBefore(badge, host);
    }
    if (!badge) return;
    badge.hidden = n === 0;
    badge.textContent = `${n} value override${n === 1 ? "" : "s"} on`;
    badge.title = "Your values replace DDF Value for these players on every tab. Open Overrides to change them.";
  }

  // ---------- search ----------
  function renderSearch(box) {
    const input = el("input", {type: "search", id: "v2OvSearch", placeholder: "Search a player to override…", autocomplete: "off",
      "aria-label": "Search a player", value: S.query});
    const list = el("ul", {class: "v2-ov-results", id: "v2OvResults", role: "listbox", "aria-label": "Matching players"});
    const fill = () => {
      list.replaceChildren();
      const q = input.value.trim();
      S.query = input.value;
      if (!q || !S.engine) return;
      const hits = S.engine.searchPlayers(q, {limit: 8});
      if (!hits.length) { list.append(el("li", {class: "v2-ov-none", text: "No player matches."})); return; }
      hits.forEach(row => {
        const v = row.values.ddf_value;
        list.append(el("li", {role: "option"}, [el("button", {type: "button", class: "v2-ov-hit",
          onclick: () => { select(row.player_key, row.name); }}, [
          el("span", {class: "v2-ov-hit-name", text: row.name}),
          el("span", {class: "v2-ov-hit-meta", text: `${row.pos}${row.team ? " · " + row.team : ""} · DDF ${fmt(v)}${S.values[row.player_key] !== undefined ? " (yours)" : ""}`})])]));
      });
    };
    input.addEventListener("input", fill);
    input.addEventListener("keydown", event => {
      if (event.key === "Enter") { const first = list.querySelector("button"); if (first) first.click(); }
    });
    box.append(el("label", {class: "v2-search v2-ov-search"}, [input]), list);
    fill();
  }
  function select(key, name) {
    S.selected = String(key);
    S.draft = null;
    S.query = "";
    render();
    const editor = $("v2OvEditor");
    if (editor && editor.scrollIntoView) editor.scrollIntoView({block: "nearest"});
  }

  // ---------- editor: graph + comparables ----------
  // The pool the chosen value is compared against: every other priced player (same position by default), at the
  // values the dashboard shows now (other overrides included).
  function pool(row) {
    return rows().filter(r => String(r.player_key) !== String(row.player_key) && finite(r.values.ddf_value) && r.values.ddf_value > 0
      && (S.scope === "all" || r.pos === row.pos))
      .sort((a, b) => b.values.ddf_value - a.values.ddf_value || a.name.localeCompare(b.name));
  }
  const rankAt = (list, value) => list.filter(r => r.values.ddf_value > value).length + 1;
  const scopeLabel = row => (S.scope === "all" ? "overall" : row.pos);

  function renderEditor(box) {
    const row = S.selected ? rowOf(S.selected) : null;
    box.replaceChildren();
    box.hidden = !row;
    if (!row) return;
    const model = modelValue(row);
    const saved = S.values[S.selected];
    if (S.draft === null) S.draft = saved !== undefined ? saved : finite(model) ? model : 0;
    const list = pool(row);
    const top = list.length ? list[0].values.ddf_value : 0;
    const peak = Math.max(10, top, finite(model) ? model : 0, S.draft) * 1.08;
    const step = [2, 5, 10, 20, 25, 50, 100].find(st => peak / st <= 6) || 200;
    const yMax = Math.ceil(peak / step) * step;

    // Head: who, model value, your value.
    const numberInput = el("input", {type: "number", id: "v2OvNumber", min: "0", step: "0.1", value: fmt(S.draft), "aria-label": `Your value for ${row.name}`});
    const head = el("div", {class: "v2-ov-head"}, [
      el("div", {}, [
        el("h2", {id: "v2OvName", text: row.name}),
        el("p", {class: "v2-meta", text: `${row.pos}${row.team ? " · " + row.team : ""} · DDF Value ${fmt(model)}${finite(model) ? ` (${row.pos}${rankAt(pool({...row, pos: row.pos}).filter(r => r.pos === row.pos), model)})` : ""}`})]),
      el("label", {class: "v2-ov-yours"}, [el("span", {text: "Your value"}), numberInput])]);

    // Scope toggle (same position by default).
    const scope = el("div", {class: "v2-ov-scope", role: "group", "aria-label": "Compare against"}, [
      ["pos", `Same position (${row.pos})`], ["all", "All positions"]].map(([key, label]) =>
      el("button", {type: "button", class: "v2-select", "aria-pressed": String(S.scope === key),
        onclick: () => { S.scope = key; renderEditor(box); }}, [document.createTextNode(label)])));

    // Graph.
    const W = 720, H = 300, L = 44, R = 16, T = 14, B = 30;
    const n = Math.max(list.length, 1);
    const x = rank => L + (rank - 1) / Math.max(n - 1, 1) * (W - L - R);
    const y = v => T + (1 - v / yMax) * (H - T - B);
    const chart = svg("svg", {viewBox: `0 0 ${W} ${H}`, class: "v2-ov-chart", role: "img", id: "v2OvChart",
      "aria-label": `DDF Value by ${scopeLabel(row)} rank, with a draggable line for ${row.name}'s value`});
    for (let v = 0; v <= yMax + 1e-9; v += step) {
      chart.append(svg("line", {x1: L, x2: W - R, y1: y(v), y2: y(v), class: "v2-ov-grid"}));
      chart.append(svg("text", {x: L - 6, y: y(v) + 4, class: "v2-ov-axis", "text-anchor": "end"}, String(v)));
    }
    chart.append(svg("text", {x: (L + W - R) / 2, y: H - 6, class: "v2-ov-axis", "text-anchor": "middle"}, `${scopeLabel(row) === "overall" ? "Overall" : row.pos} rank by DDF Value`));
    const dots = svg("g", {});
    list.forEach((r, i) => dots.append(svg("circle", {cx: x(i + 1), cy: y(r.values.ddf_value), r: 3, class: "v2-ov-dot", "data-key": r.player_key},
    )));
    chart.append(dots);
    if (finite(model)) {
      chart.append(svg("line", {x1: L, x2: W - R, y1: y(model), y2: y(model), class: "v2-ov-model"}));
      chart.append(svg("text", {x: W - R, y: y(model) - 5, class: "v2-ov-model-label", "text-anchor": "end"}, `DDF Value ${fmt(model)}`));
    }
    const line = svg("line", {x1: L, x2: W - R, class: "v2-ov-line"});
    const handle = svg("circle", {r: 7, class: "v2-ov-handle"});
    const tag = svg("text", {class: "v2-ov-tag"});
    chart.append(line, handle, tag);

    // Range slider: the keyboard and screen-reader way to drag.
    const range = el("input", {type: "range", id: "v2OvRange", min: "0", max: String(yMax), step: "0.1", value: String(S.draft),
      "aria-label": `Drag ${row.name}'s value`});

    const near = el("div", {class: "v2-ov-near", "aria-live": "polite"});

    function draw(value) {
      S.draft = round1(Math.min(yMax, Math.max(0, value)));
      const rank = rankAt(list, S.draft);
      line.setAttribute("y1", y(S.draft)); line.setAttribute("y2", y(S.draft));
      handle.setAttribute("cx", x(Math.min(rank, n))); handle.setAttribute("cy", y(S.draft));
      const tx = Math.min(Math.max(x(Math.min(rank, n)) + 12, L + 4), W - R - 150);
      tag.setAttribute("x", tx); tag.setAttribute("y", Math.max(y(S.draft) - 10, T + 10));
      tag.textContent = `${fmt(S.draft)} · ${scopeLabel(row) === "overall" ? "#" : row.pos}${rank}`;
      if (document.activeElement !== numberInput) numberInput.value = fmt(S.draft);
      range.value = String(S.draft);
      // Comparable players: the NEAR above and NEAR below where this value lands.
      const at = rank - 1;
      const above = list.slice(Math.max(0, at - NEAR), at);
      const below = list.slice(at, at + NEAR);
      const keys = new Set(above.concat(below).map(r => String(r.player_key)));
      dots.querySelectorAll("circle").forEach(c => c.classList.toggle("is-near", keys.has(c.dataset.key)));
      near.replaceChildren(
        el("h3", {text: `At ${fmt(S.draft)}, ${row.name} ranks ${scopeLabel(row) === "overall" ? "#" : row.pos}${rank}${finite(model) ? ` (DDF Value: ${scopeLabel(row) === "overall" ? "#" : row.pos}${rankAt(list, model)})` : ""}. Comparable players:`}),
        compTable(above, below, row));
    }
    function compTable(above, below, row) {
      const tbl = el("table", {class: "v2-table v2-ov-table"});
      tbl.append(el("thead", {}, [el("tr", {}, ["Player", "Pos", "Team", "Value", "vs yours"].map((h, i) =>
        el("th", {scope: "col", class: i >= 3 ? "num" : null, text: h})))]));
      const body = el("tbody");
      const add = r => body.append(el("tr", {}, [
        el("td", {}, [el("button", {type: "button", class: "v2-ov-link", text: r.name, title: `Override ${r.name} instead`,
          onclick: () => select(r.player_key, r.name)}),
          r.valueOverride !== null && r.valueOverride !== undefined ? el("span", {class: "v2-ov-mark", text: " yours"}) : null]),
        el("td", {text: r.pos}), el("td", {text: r.team || ""}),
        el("td", {class: "num", text: fmt(r.values.ddf_value)}),
        el("td", {class: "num", text: signed(r.values.ddf_value - S.draft)})]));
      above.forEach(add);
      body.append(el("tr", {class: "v2-ov-self"}, [el("td", {text: `${row.name} (your value)`}), el("td", {text: row.pos}),
        el("td", {text: row.team || ""}), el("td", {class: "num", text: fmt(S.draft)}), el("td", {class: "num", text: ""})]));
      below.forEach(add);
      tbl.append(body);
      return tbl;
    }

    // Drag on the graph: anywhere in the plot moves the line; release applies it.
    const valueAt = event => {
      const box = chart.getBoundingClientRect();
      const py = (event.clientY - box.top) / box.height * H;
      return (1 - (py - T) / (H - T - B)) * yMax;
    };
    chart.addEventListener("pointerdown", event => {
      S.dragging = true;
      if (chart.setPointerCapture) chart.setPointerCapture(event.pointerId);
      draw(valueAt(event));
      event.preventDefault();
    });
    chart.addEventListener("pointermove", event => { if (S.dragging) draw(valueAt(event)); });
    const release = () => { if (!S.dragging) return; S.dragging = false; commit(); };
    chart.addEventListener("pointerup", release);
    chart.addEventListener("pointercancel", release);
    range.addEventListener("input", () => draw(Number(range.value)));
    range.addEventListener("change", commit);
    numberInput.addEventListener("change", () => { const v = Number(numberInput.value); if (finite(v)) { draw(v); commit(); } });

    function commit() {
      // Settling back on the model's own value is no override.
      if (finite(model) && Math.abs(S.draft - model) < 0.05) setOverride(S.selected, null);
      else setOverride(S.selected, S.draft, row.name);
      renderList($("v2OvList"));
      actions.querySelector("[data-ov-reset]").hidden = S.values[S.selected] === undefined;
    }

    const actions = el("div", {class: "v2-ov-actions"}, [
      el("button", {type: "button", class: "v2-btn", "data-ov-reset": true, hidden: saved === undefined || null,
        text: `Reset to DDF Value (${fmt(model)})`, onclick: () => { setOverride(S.selected, null); S.draft = null; render(); }}),
      el("button", {type: "button", class: "v2-btn v2-btn-quiet", text: "Close", onclick: () => { S.selected = null; S.draft = null; render(); }})]);

    box.append(head, scope, el("div", {class: "v2-ov-plot"}, [chart, el("label", {class: "v2-ov-range"}, [range])]),
      el("p", {class: "v2-meta", text: "Drag the line on the graph (or the slider) to set his value. It applies when you let go, on every tab."}),
      near, actions);
    draw(S.draft);
  }

  // ---------- list of overrides ----------
  function renderList(box) {
    if (!box) return;
    box.replaceChildren();
    const keys = Object.keys(S.values);
    box.append(el("div", {class: "v2-card-head"}, [el("h2", {id: "v2OvListTitle", text: `Your overrides (${keys.length})`}),
      keys.length ? el("button", {type: "button", class: "v2-btn v2-btn-quiet", text: "Remove all",
        onclick: () => { S.values = {}; S.names = {}; push(); render(); }}) : null]));
    if (!keys.length) {
      box.append(el("p", {class: "v2-meta", text: "None yet. Pick a player above and drag his value; every tab then uses your value in place of DDF Value."}));
      return;
    }
    const tbl = el("table", {class: "v2-table v2-ov-table", "aria-labelledby": "v2OvListTitle"});
    tbl.append(el("thead", {}, [el("tr", {}, ["Player", "Pos", "DDF Value", "Your value", "Change", ""].map((h, i) =>
      el("th", {scope: "col", class: i >= 2 && i <= 4 ? "num" : null, text: h})))]));
    const body = el("tbody");
    keys.map(key => ({key, row: rowOf(key)}))
      .sort((a, b) => S.values[b.key] - S.values[a.key])
      .forEach(({key, row}) => {
        const model = modelValue(row);
        body.append(el("tr", {class: key === S.selected ? "is-selected" : null}, [
          el("td", {}, [el("button", {type: "button", class: "v2-ov-link", text: row ? row.name : (S.names[key] || `Player ${key}`), onclick: () => select(key, row && row.name)})]),
          el("td", {text: row ? row.pos : ""}),
          el("td", {class: "num", text: fmt(model)}),
          el("td", {class: "num v2-ov-yours-cell", text: fmt(S.values[key])}),
          el("td", {class: "num", text: finite(model) ? signed(S.values[key] - model) : "—"}),
          el("td", {}, [el("button", {type: "button", class: "v2-ov-link", text: "Remove", "aria-label": `Remove override for ${row ? row.name : key}`,
            onclick: () => { setOverride(key, null); if (key === S.selected) S.draft = null; render(); }})])]));
      });
    tbl.append(body);
    box.append(el("div", {class: "v2-table-wrap"}, [tbl]));
  }

  // ---------- page ----------
  function render() {
    const page = $("v2Overrides");
    if (!page) return;
    const search = $("v2OvSearchBox");
    if (search) { search.replaceChildren(); renderSearch(search); }
    const editor = $("v2OvEditor");
    if (editor) renderEditor(editor);
    renderList($("v2OvList"));
    syncBadge();
  }

  function boot(engine) {
    S.engine = engine;
    load();
    if (Object.keys(S.values).length) push();
    else syncBadge();
  }

  root.DDFOverrides = {boot, render, count: () => Object.keys(S.values).length, all: () => ({...S.values}), state: S};
})(window);
