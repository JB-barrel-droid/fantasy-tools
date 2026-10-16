// Trade Value v2 — Find a trade (JEG-481, first slice).
//
// You type in your roster and a rival's. The search lists packages (1-for-1 up to N-for-N)
// where the published trade charts say the rival breaks even or wins, and DDF Value says you win.
//
// No value math of its own: every number is an engine row value (TradeValueCurveControls
// .getAllRows()); the search only adds and compares them, as Compare a trade does. A missing
// value stays missing, never 0.
//
// Decisions (Jeremy, 2026-10-09 / 2026-10-10, recorded on JEG-481):
//   * rosters are typed in with player search; league import comes later;
//   * default 1-for-1 up to 2-for-2, a toggle raises the maximum players per side;
//   * "fair to the rival" = at least 3 of the 4 trade charts say the rival breaks even or wins;
//   * ranking prefers simpler trades.
// Defaults chosen here, listed in docs/math-review-agenda.md: the simplicity weight (EXTRA_PLAYER_WEIGHT)
// and the cap on subsets searched per side (MAX_SUBSETS).
(function (root) {
  "use strict";

  const OUR_KEY = "ddf_value";
  const CHART_KEYS = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
  const MIN_CHARTS = 3;
  const MAX_SIZE_CHOICES = [2, 3, 4];
  const MAX_SUBSETS = 6000;          // per side; larger rosters search the top players by DDF Value
  const EXTRA_PLAYER_WEIGHT = 0.1;   // each player beyond a 1-for-1 takes 10% off the ranking score
  const LIMIT = 10;
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const pointsAsShown = net => (Math.abs(net) < 0.05 ? 0 : net);   // 0.0 as shown points neither way

  // Every subset of 1..maxSize items, as arrays of indices.
  function subsets(count, maxSize) {
    const out = [];
    const walk = (start, picked) => {
      if (picked.length) out.push(picked.slice());
      if (picked.length === maxSize) return;
      for (let i = start; i < count; i++) { picked.push(i); walk(i + 1, picked); picked.pop(); }
    };
    walk(0, []);
    return out;
  }
  const choose = (n, k) => { let r = 1; for (let i = 1; i <= k; i++) r = r * (n - k + i) / i; return Math.round(r); };
  const subsetCount = (n, maxSize) => { let total = 0; for (let k = 1; k <= Math.min(n, maxSize); k++) total += choose(n, k); return total; };

  // The most players to search on one side so the subsets stay under the cap: the top by DDF Value.
  function pool(rows, ourKey, maxSize) {
    const priced = rows.filter(row => row.values && finite(row.values[ourKey]))
      .sort((a, b) => b.values[ourKey] - a.values[ourKey] || String(a.player_key).localeCompare(String(b.player_key)));
    let n = priced.length;
    while (n > maxSize && subsetCount(n, maxSize) > MAX_SUBSETS) n -= 1;
    return {rows: priced.slice(0, n), unpriced: rows.length - priced.length, searched: n, of: priced.length};
  }

  // mine / theirs: engine rows. opts: {ourKey, chartKeys, maxSize, minCharts, limit}.
  // Each trade: {give, receive, edge, charts: [{key, net, rivalOk}], pricedCharts, rivalOkCount, score}.
  // edge and net are receive - give for you; the rival is happy when a chart's net is <= 0 as shown.
  // A chart that does not price every player in the package is left out of the count (net null).
  function findTrades(mine, theirs, opts) {
    const o = opts || {};
    const ourKey = o.ourKey || OUR_KEY;
    const maxSize = Math.max(1, o.maxSize || 2);
    const chartKeys = (o.chartKeys || CHART_KEYS).slice();
    const minCharts = o.minCharts || Math.min(MIN_CHARTS, chartKeys.length);
    const limit = o.limit || LIMIT;
    const mineP = pool(mine, ourKey, maxSize);
    const theirsP = pool(theirs, ourKey, maxSize);
    const keys = [ourKey].concat(chartKeys);
    // Per subset: the sum in each series, or null when any player in it lacks that series.
    const describe = (rows, combo) => {
      const sums = keys.map(key => {
        let total = 0;
        for (const i of combo) { const v = rows[i].values[key]; if (!finite(v)) return null; total += v; }
        return total;
      });
      return {combo, sums};
    };
    const mineSubs = subsets(mineP.rows.length, maxSize).map(c => describe(mineP.rows, c));
    const theirSubs = subsets(theirsP.rows.length, maxSize).map(c => describe(theirsP.rows, c))
      .sort((a, b) => a.sums[0] - b.sums[0]);
    const found = [];
    for (const give of mineSubs) {
      // DDF Value: you must win, so only their packages worth more than yours (sorted: binary search).
      let lo = 0; let hi = theirSubs.length;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (pointsAsShown(theirSubs[mid].sums[0] - give.sums[0]) > 0) hi = mid; else lo = mid + 1;
      }
      for (let t = lo; t < theirSubs.length; t++) {
        const get = theirSubs[t];
        const edge = get.sums[0] - give.sums[0];
        if (pointsAsShown(edge) <= 0) continue;
        let priced = 0;
        let ok = 0;
        const charts = [];
        for (let c = 0; c < chartKeys.length; c++) {
          const g = give.sums[c + 1];
          const r = get.sums[c + 1];
          if (g === null || r === null) { charts.push({key: chartKeys[c], net: null, rivalOk: null}); continue; }
          const net = r - g;
          const rivalOk = pointsAsShown(net) <= 0;
          priced += 1;
          if (rivalOk) ok += 1;
          charts.push({key: chartKeys[c], net, rivalOk});
        }
        if (priced < minCharts || ok < minCharts) continue;
        const players = give.combo.length + get.combo.length;
        found.push({give: give.combo.map(i => mineP.rows[i]), receive: get.combo.map(i => theirsP.rows[i]), edge, charts,
          pricedCharts: priced, rivalOkCount: ok, score: edge * (1 - EXTRA_PLAYER_WEIGHT * (players - 2))});
      }
    }
    const idOf = trade => `${trade.give.map(r => r.player_key)}|${trade.receive.map(r => r.player_key)}`;
    found.sort((a, b) => b.score - a.score || b.edge - a.edge
      || (a.give.length + a.receive.length) - (b.give.length + b.receive.length)
      || idOf(a).localeCompare(idOf(b)));
    return {trades: found.slice(0, limit), total: found.length, ourKey, chartKeys, minCharts, maxSize,
      mine: mineP, theirs: theirsP};
  }

  const api = {findTrades, subsets, subsetCount, OUR_KEY, CHART_KEYS, MIN_CHARTS, MAX_SIZE_CHOICES, MAX_SUBSETS, EXTRA_PLAYER_WEIGHT, LIMIT};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.TradeValueFinder = api;

  // ---------- page (browser only) ----------
  const CHART_NAMES = {usatoday: "USA Today", fantasycalc: "FantasyCalc", fantasypros: "FantasyPros", cbs: "CBS Sports"};
  const $ = id => document.getElementById(id);
  const engine = () => root.TradeValueCurveControls;
  const S = {mine: [], theirs: [], maxSize: 2};   // mine / theirs: [{key, name, pos}]

  function el(tag, props, ...kids) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach(([k, v]) => { if (k === "text") node.textContent = v; else node.setAttribute(k, v); });
    node.append(...kids);
    return node;
  }
  const clearOutput = () => { const out = $("v2FindOut"); out.hidden = true; out.replaceChildren(); };

  function sideCard(side, title) {
    const id = `v2Find${side[0].toUpperCase()}${side.slice(1)}`;
    const list = el("ul", {class: "v2-trade-players", id: `${id}Players`});
    const results = el("ul", {class: "v2-trade-results", id: `${id}Results`, hidden: ""});
    const input = el("input", {type: "search", id: `${id}Search`, placeholder: "Search and add a player…", autocomplete: "off", "aria-controls": `${id}Results`});
    const label = el("label", {class: "v2-search"}, el("span", {class: "v2-sr", text: `Search and add a player to ${title.toLowerCase()}`}), input);
    const wrap = el("div", {class: "v2-trade-side v2-find-side"}, el("h3", {text: title}), label, results, list);
    const render = () => {
      list.replaceChildren(...S[side].map(p => {
        const remove = el("button", {type: "button", class: "v2-link", "aria-label": `Remove ${p.name}`, text: "Remove"});
        remove.addEventListener("click", () => { S[side] = S[side].filter(q => q.key !== p.key); render(); clearOutput(); });
        return el("li", {}, el("div", {}, el("b", {text: p.name}), el("span", {class: "v2-meta", text: p.pos ? ` ${p.pos}` : ""})), remove);
      }));
    };
    input.addEventListener("input", () => {
      const q = input.value.trim();
      results.replaceChildren();
      results.hidden = !q;
      if (!q || !engine()) return;
      const taken = new Set(S.mine.concat(S.theirs).map(p => p.key));
      const hits = engine().getAllRows().filter(r => r.name && r.name.toLowerCase().includes(q.toLowerCase())).slice(0, 8);
      if (!hits.length) results.append(el("li", {class: "is-empty v2-meta", text: `No player name contains “${q}”.`}));
      hits.forEach(row => {
        const key = String(row.player_key);
        const added = taken.has(key);
        const button = el("button", {type: "button", text: `${`${row.name} · ${row.pos || ""} ${row.team || ""}`.trim()}${added ? " ✓ Added" : ""}`});
        if (added) button.disabled = true;
        button.addEventListener("click", () => {
          S[side].push({key, name: row.name, pos: row.pos});
          input.value = "";
          results.replaceChildren();
          results.hidden = true;
          render();
          clearOutput();
          input.focus();
        });
        results.append(el("li", {}, button));
      });
    });
    return wrap;
  }

  const fmt = n => (Math.abs(n) < 0.05 ? "0.0" : (n > 0 ? "+" : "") + n.toFixed(1));
  const names = rows => rows.map(r => r.name).join(" + ");

  function run() {
    const out = $("v2FindOut");
    out.hidden = false;
    out.replaceChildren();
    const note = text => out.append(el("p", {class: "v2-meta", text}));
    const C = engine();
    if (!C) return note("Values are still loading.");
    if (!S.mine.length || !S.theirs.length) return note("Add at least one player to each roster.");
    const all = C.getAllRows();
    const byKey = new Map(all.map(r => [String(r.player_key), r]));
    const rowsOf = list => list.map(p => byKey.get(p.key)).filter(Boolean);
    const charts = CHART_KEYS.filter(key => all.some(r => r.values && finite(r.values[key])));
    if (charts.length < MIN_CHARTS) return note(`Only ${charts.length} of the 4 trade charts are priced for this league, so no trade can clear the 3-chart test.`);
    const res = findTrades(rowsOf(S.mine), rowsOf(S.theirs), {chartKeys: charts, maxSize: S.maxSize});
    const skipped = res.mine.unpriced + res.theirs.unpriced;
    if (skipped) note(`${skipped} player${skipped === 1 ? " has" : "s have"} no DDF Value and ${skipped === 1 ? "is" : "are"} left out, not counted as 0.`);
    if (res.mine.searched < res.mine.of || res.theirs.searched < res.theirs.of) {
      note(`Packages of up to ${S.maxSize} are searched among your top ${res.mine.searched} and their top ${res.theirs.searched} players by DDF Value.`);
    }
    if (!res.trades.length) {
      return note(`No trade found where DDF Value says you win and at least ${res.minCharts} of ${charts.length} trade charts say they break even or win. Try a larger package.`);
    }
    note(`${res.total} trade${res.total === 1 ? "" : "s"} found; the top ${res.trades.length} are listed, ranked by DDF Value edge with simpler trades first.`);
    const list = el("ol", {class: "v2-find-list", id: "v2FindList"});
    res.trades.forEach(t => {
      const favor = t.charts.filter(c => c.rivalOk).map(c => CHART_NAMES[c.key] || c.key);
      const unpriced = t.charts.filter(c => c.net === null).length;
      const ids = rows => rows.map(r => encodeURIComponent(r.player_key)).join(",");
      const open = el("a", {class: "v2-link", href: `v2/#compare-trade?give=${ids(t.give)}&get=${ids(t.receive)}`, text: "Open in Compare a trade"});
      list.append(el("li", {"data-find-edge": String(t.edge)},
        el("b", {text: `You give ${names(t.give)}; you receive ${names(t.receive)}`}),
        el("span", {class: "v2-meta", text: `DDF Value edge ${fmt(t.edge)} for you. ${favor.length} of ${t.pricedCharts} trade charts have them winning or even: ${favor.join(", ")}.`
          + (unpriced ? ` ${unpriced} chart${unpriced === 1 ? " does" : "s do"} not price every player and ${unpriced === 1 ? "is" : "are"} not counted.` : "")}),
        open));
    });
    out.append(list);
  }

  function build() {
    const host = $("v2Compare");
    if (!host || $("v2Find")) return;
    const size = el("select", {id: "v2FindSize"}, ...MAX_SIZE_CHOICES.map(n => el("option", {value: String(n), text: `Up to ${n}-for-${n}`})));
    size.addEventListener("change", () => { S.maxSize = Number(size.value); clearOutput(); });
    const go = el("button", {type: "button", class: "v2-btn", id: "v2FindGo", text: "Find trades"});
    go.addEventListener("click", run);
    const card = el("section", {class: "v2-card", id: "v2Find", "aria-labelledby": "v2FindTitle"},
      el("div", {class: "v2-card-head"}, el("div", {},
        el("h2", {id: "v2FindTitle", text: "Find a trade to propose"}),
        el("p", {class: "v2-meta", text: "Type in your roster and another manager's. Lists trades where DDF Value says you win and at least 3 of 4 trade charts say they break even or win, so they are likely to accept."}))),
      el("div", {class: "v2-trade-sides"}, sideCard("mine", "Your roster"), sideCard("theirs", "Their roster")),
      el("div", {class: "v2-ctoolbar"}, el("label", {class: "v2-field"}, el("span", {class: "v2-field-label", text: "Package size:"}), size), go),
      el("div", {id: "v2FindOut", "aria-live": "polite", hidden: ""}));
    host.insertBefore(card, host.querySelector(".v2-footnote"));
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", build);
  else build();
})(typeof window !== "undefined" ? window : globalThis);
