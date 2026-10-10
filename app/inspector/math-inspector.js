// Math inspector (internal page; noindex, linked from no public page).
//
// Renders every input and intermediate number of the trade-value math for the
// active league setting, read from the chart engine that runs off-screen on
// this same page (TradeValueCurveControls.getInspection). It never prices a
// player: the only arithmetic here is sums, shares and ratios of the engine's
// own numbers, and each such column says so in its header ("sum", "share",
// "ratio", "check"). tests/test_math_inspector.py holds the tables to the
// engine's getAllRows() in all three views at three settings.
(function () {
  "use strict";

  const $ = selector => document.querySelector(selector);
  const C = () => window.TradeValueCurveControls;
  const PD = () => window.TradeValueProductData;
  const GROUPS = ["starter", "bench"];

  let snap = null;
  let players = new Map();
  let renderTimer = null;
  let renderCount = 0;
  const tables = {};
  const sortState = {};
  const priorCache = new Map();

  // ---------- formatting ----------
  const isNum = value => typeof value === "number" && Number.isFinite(value);
  const fmt = {
    text: value => value === null || value === undefined || value === "" ? "—" : String(value),
    int: value => isNum(value) ? String(Math.round(value)) : "—",
    n1: value => isNum(value) ? value.toFixed(1) : "—",
    n2: value => isNum(value) ? value.toFixed(2) : "—",
    n3: value => isNum(value) ? value.toFixed(3) : "—",
    n4: value => isNum(value) ? value.toFixed(4) : "—",
    sci: value => isNum(value) ? (Math.abs(value) >= 0.01 || value === 0 ? value.toFixed(5) : value.toExponential(4)) : "—",
    pct: value => isNum(value) ? (value * 100).toFixed(2) + "%" : "—",
    delta: value => isNum(value) ? (value > 0 ? "+" : "") + value.toFixed(3) : "—"
  };
  const el = (tag, attrs, children) => {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([key, value]) => {
      if (value === null || value === undefined) return;
      if (key === "text") node.textContent = value;
      else if (key === "className") node.className = value;
      else node.setAttribute(key, value);
    });
    (children || []).forEach(child => child && node.appendChild(typeof child === "string" ? document.createTextNode(child) : child));
    return node;
  };
  const sum = values => values.reduce((total, value) => total + (isNum(value) ? value : 0), 0);
  const playerName = key => players.get(Number(key))?.name || `player ${key}`;
  const playerPos = key => players.get(Number(key))?.pos || null;
  const label = key => snap?.labels?.[key] || key;

  // ---------- tables (render + export registry) ----------
  function csvCell(value) {
    if (value === null || value === undefined) return "";
    const text = typeof value === "object" ? JSON.stringify(value) : String(value);
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }
  function download(name, mime, text) {
    const blob = new Blob([text], {type: mime});
    const url = URL.createObjectURL(blob);
    const link = el("a", {href: url, download: name});
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function settingSlug() {
    const s = snap?.setting;
    if (!s) return "unknown";
    const roster = Object.entries(s.roster).filter(([k]) => !["K", "DST"].includes(k)).map(([k, v]) => `${k}${v}`).join("");
    return `${s.scoring}-${s.teams}t-${roster}`;
  }
  function exportRows(id) {
    const spec = tables[id];
    return spec ? spec.rows.map(row => Object.fromEntries(spec.columns.map(col => [col.key, row[col.key] ?? null]))) : null;
  }
  function exportCsv(id) {
    const spec = tables[id];
    const lines = [spec.columns.map(col => csvCell(col.label)).join(",")];
    spec.rows.forEach(row => lines.push(spec.columns.map(col => csvCell(row[col.key])).join(",")));
    return lines.join("\n") + "\n";
  }

  // columns: [{key, label, fmt}] ; rows: [{...}] (full precision; the page rounds for display only)
  function table(id, title, columns, rows, opts = {}) {
    tables[id] = {title, columns, rows};
    const wrap = el("div", {className: "mi-table-wrap", "data-table": id});
    const head = el("div", {className: "mi-table-head"}, [
      el("h3", {text: title}),
      el("span", {className: "mi-count", text: `${rows.length} row${rows.length === 1 ? "" : "s"}`}),
      el("button", {type: "button", "data-export": "csv", text: "CSV"}),
      el("button", {type: "button", "data-export": "json", text: "JSON"})
    ]);
    head.querySelector('[data-export="csv"]').addEventListener("click", () =>
      download(`${id}-${settingSlug()}.csv`, "text/csv", exportCsv(id)));
    head.querySelector('[data-export="json"]').addEventListener("click", () =>
      download(`${id}-${settingSlug()}.json`, "application/json",
        JSON.stringify({table: id, title, setting: snap.setting, rows: exportRows(id)}, null, 2)));
    wrap.appendChild(head);
    if (opts.note) wrap.appendChild(el("p", {className: "mi-note", text: opts.note}));
    const scroller = el("div", {className: "mi-scroll"});
    const tbl = el("table", {className: "mi-table"});
    const thead = el("thead");
    const tr = el("tr");
    columns.forEach(col => {
      const th = el("th", {text: col.label, title: col.title || col.label, "data-col": col.key,
        className: col.fmt && col.fmt !== "text" ? "num" : null});
      th.addEventListener("click", () => {
        const current = sortState[id];
        sortState[id] = {key: col.key, dir: current?.key === col.key && current.dir === "desc" ? "asc" : "desc"};
        const replacement = table(id, title, columns, rows, opts);
        wrap.replaceWith(replacement);
      });
      tr.appendChild(th);
    });
    thead.appendChild(tr);
    tbl.appendChild(thead);
    const sorted = rows.slice();
    const sort = sortState[id];
    if (sort) {
      sorted.sort((a, b) => {
        const x = a[sort.key], y = b[sort.key];
        const xm = x === null || x === undefined, ym = y === null || y === undefined;
        if (xm !== ym) return xm ? 1 : -1;
        const order = isNum(x) && isNum(y) ? x - y : String(x).localeCompare(String(y));
        return sort.dir === "asc" ? order : -order;
      });
    }
    const tbody = el("tbody");
    const limit = opts.limit || 2000;
    sorted.slice(0, limit).forEach(row => {
      const r = el("tr", {"data-row": row._id ?? null, className: row._className || null});
      columns.forEach(col => {
        const formatter = fmt[col.fmt || "text"] || fmt.text;
        r.appendChild(el("td", {text: formatter(row[col.key]), "data-col": col.key,
          className: col.fmt && col.fmt !== "text" ? "num" : null}));
      });
      tbody.appendChild(r);
    });
    tbl.appendChild(tbody);
    scroller.appendChild(tbl);
    wrap.appendChild(scroller);
    return wrap;
  }
  function section(id) {
    const body = document.querySelector(`#${id} .mi-body`);
    body.replaceChildren();
    return body;
  }
  const para = (text, className = "mi-note") => el("p", {className, text});

  // ---------- shared helpers over the snapshot ----------
  // JEG-508: every number comes from the value pipeline result the chart
  // draws (getInspection: valuePipeline, rows, views, players).
  const position = () => $("#miPosition").value;
  const inPosition = key => position() === "ALL" || playerPos(key) === position();
  const selectedSource = () => $("#miSource").value;
  const vp = () => snap.valuePipeline;
  const pipelineSources = () => Object.keys(vp()?.sources || {});
  // The pipeline source behind a series key (a source, "*_vorp", "*_adjusted").
  const sourceOfSeries = key => key.endsWith("_vorp") ? key.slice(0, -5) : key.replace(/_adjusted$/, "");
  const GROUPS8 = ["QB", "RB", "WR", "TE"].flatMap(pos => GROUPS.map(role => `${pos}|${role}`));

  // ---------- 0. checks ----------
  function renderChecks() {
    const body = section("mi-checks");
    body.appendChild(para("The fixed-pie invariant (VP-5): every source's Adjusted values over its work list (listed and estimated players) sum to the league pie, each group to its budget (pie x DDF weight), and its VORP vs waivers values to the pie. Each chart's Indexed values over the players it lists sum to their blended DDF Value (VP-6.4)."));
    const fp = snap.fixedPie;
    body.appendChild(table("fixed-pie", `Every source against the ${fmt.n1(fp.pie)} pie`, [
      {key: "label", label: "Source"}, {key: "n", label: "Players (work list)", fmt: "int"},
      {key: "total", label: "Adjusted total", fmt: "n4"}, {key: "target", label: "Pie (less unpaid)", fmt: "n4"},
      {key: "delta", label: "Delta", fmt: "sci"}, {key: "vorpTotal", label: "VORP vs waivers total", fmt: "n4"},
      {key: "groupsOk", label: "Groups = budgets"}, {key: "ok", label: "Holds"}
    ], fp.checks.map(c => ({_id: c.source, label: label(c.source), ...c, groupsOk: String(c.groupsOk), ok: String(c.ok)}))));
    body.appendChild(table("indexed-check", "Indexed: listed players' total = their blended DDF Value", [
      {key: "label", label: "Chart"}, {key: "factor", label: "Factor", fmt: "sci"}, {key: "shared", label: "Shared players", fmt: "int"},
      {key: "ddfTotal", label: "DDF Value total", fmt: "n4"}, {key: "delta", label: "Delta", fmt: "sci"}, {key: "ok", label: "Holds"}
    ], Object.entries(fp.indexed).map(([k, r]) => ({_id: k, label: label(k), ...r, ok: String(r.ok)}))));
  }

  // ---------- 1. inputs ----------
  function renderInputs() {
    const body = section("mi-inputs");
    const v = vp();
    // JEG-536 (ES-14): benchShare is the readout {QB, RB, WR, TE, overall, override, ...}.
    const bs = v.benchShare && typeof v.benchShare === "object" ? v.benchShare : null;
    const bsText = bs
      ? `Bench share ${fmt.pct(bs.overall)} (${bs.override ? "override" : "computed from the league settings"}; QB ${fmt.pct(bs.QB)}, RB ${fmt.pct(bs.RB)}, WR ${fmt.pct(bs.WR)}, TE ${fmt.pct(bs.TE)}; paid on fill-in parts ${fmt.pct(v.benchShareApplied)})`
      : `Bench share ${fmt.pct(v.benchShare)} (applied ${fmt.pct(v.benchShareApplied)})`;
    body.appendChild(para(`Pie ${fmt.n1(v.pie)} (28 per starting slot). ${bsText}. Included set: ${v.included.join(", ") || "none"}.`));
    body.appendChild(table("sources-included", "Sources this week (VP-1)", [
      {key: "key", label: "Source"}, {key: "family", label: "Family"}, {key: "included", label: "Counts in DDF"},
      {key: "reason", label: "Why not"}
    ], pipelineSources().map(k => ({_id: k, key: label(k), family: v.sources[k].family,
      included: String(v.sources[k].included), reason: (snap.excluded.find(e => e.key === k) || {}).reason || ""}))));
    const alloc = v.slotFill || {};
    body.appendChild(table("allocation", "League allocation (VP-2.2: slots by mean projected points)", [
      {key: "pos", label: "Pos"}, {key: "dedicated", label: "Dedicated", fmt: "int"}, {key: "superflex", label: "Superflex", fmt: "int"},
      {key: "flex", label: "Flex", fmt: "int"}, {key: "bench", label: "Bench", fmt: "int"}, {key: "starters", label: "Starters", fmt: "int"},
      {key: "rostered", label: "Rostered", fmt: "int"}, {key: "fill", label: "Fill set (rostered + 1, by projected points)"}
    ], ["QB", "RB", "WR", "TE"].map(pos => ({_id: pos, pos, ...(alloc[pos] || {}),
      fill: (v.fillSets[pos] || []).map(playerName).join(", ")}))));
    const weightRows = GROUPS8.map(g => {
      const row = {_id: g, group: g.replace("|", " "), ddf: v.ddfWeights[g]};
      pipelineSources().forEach(k => { row[k] = v.sources[k].weights ? v.sources[k].weights[g] : null; });
      return row;
    });
    body.appendChild(table("weights", "Weights: each source's (bench normalized to the bench share) and the DDF weights, their average (VP-3, VP-4)", [
      {key: "group", label: "Group"}, ...pipelineSources().map(k => ({key: k, label: label(k), fmt: "pct"})),
      {key: "ddf", label: "DDF weight", fmt: "pct"}
    ], weightRows));
  }

  // ---------- 2. per source: waiver and starter lines, groups, rates ----------
  function renderTranslation() {
    const body = section("mi-translation");
    const v = vp();
    const rows = [];
    pipelineSources().forEach(k => ["QB", "RB", "WR", "TE"].forEach(pos => {
      const p = v.sources[k].positions[pos];
      rows.push({_id: `${k}|${pos}`, source: label(k), pos, method: p.method, waiver: p.waiver, starterLine: p.starterLine,
        starters: p.starters, rostered: p.rostered, listed: p.listed, estimated: p.nEstimated,
        starterGroup: v.sources[k].groups[`${pos}|starter`], benchGroup: v.sources[k].groups[`${pos}|bench`],
        starterRate: v.sources[k].rates[`${pos}|starter`], benchRate: v.sources[k].rates[`${pos}|bench`]});
    }));
    body.appendChild(table("lines", "Waiver line, starter line, groups and rates (VP-2.3, VP-2.5, VP-3, VP-5.4)", [
      {key: "source", label: "Source"}, {key: "pos", label: "Pos"}, {key: "method", label: "Waiver line from"},
      {key: "waiver", label: "Waiver line", fmt: "n3"}, {key: "starterLine", label: "Starter line", fmt: "n3"},
      {key: "starters", label: "Starters", fmt: "int"}, {key: "rostered", label: "Rostered", fmt: "int"},
      {key: "listed", label: "Listed", fmt: "int"}, {key: "estimated", label: "Estimated", fmt: "int"},
      {key: "starterGroup", label: "Starter slices", fmt: "n3"}, {key: "benchGroup", label: "Bench slices", fmt: "n3"},
      {key: "starterRate", label: "Starter rate", fmt: "sci"}, {key: "benchRate", label: "Bench rate", fmt: "sci"}
    ], rows.filter(r => position() === "ALL" || r.pos === position())));
    const est = [];
    pipelineSources().forEach(k => ["QB", "RB", "WR", "TE"].forEach(pos => {
      Object.entries(v.sources[k].positions[pos].estimates || {}).forEach(([pk, e]) => {
        est.push({_id: `${k}|${pk}`, source: label(k), player: playerName(pk), pos, path: e.path,
          peers: Object.entries(e.peers || {}).map(([peer, r]) => `${peer}: ${r.usable ? fmt.n4(r.ratio) + " -> " + fmt.n3(r.estimate) : "not usable"}`).join("; "),
          curve: e.curve && e.curve.kind === "ols" ? `${fmt.n3(e.curve.intercept)} + ${fmt.n3(e.curve.slope)} x m` : (e.curve ? e.curve.kind : ""),
          raw: e.raw, cap: e.cap, capped: String(e.capped), value: e.value, reason: e.reason});
      });
    }));
    body.appendChild(table("estimates", "Estimated players (VP-2.4: rosterable players a chart does not list)", [
      {key: "source", label: "Chart"}, {key: "player", label: "Player"}, {key: "pos", label: "Pos"}, {key: "path", label: "Path"},
      {key: "peers", label: "Peers (ratio -> estimate)"}, {key: "curve", label: "Curve"}, {key: "raw", label: "Raw", fmt: "n3"},
      {key: "cap", label: "Cap (lowest listed)", fmt: "n3"}, {key: "capped", label: "Capped"}, {key: "value", label: "Estimate", fmt: "n3"},
      {key: "reason", label: "Shown as"}
    ], est.filter(r => position() === "ALL" || r.pos === position())));
  }

  // ---------- 3-5. players in each view ----------
  // Per series, the value the chart shows in that view (snap.views) and a
  // check column rebuilt from the pipeline's intermediates.
  function viewRows(view) {
    const values = snap.views[view];
    const v = vp();
    const keys = Object.keys(snap.rows).filter(inPosition);
    return keys.map(k => {
      const prow = snap.rows[k];
      const row = {_id: k, player_key: Number(k), name: playerName(k), pos: playerPos(k),
        ddf_value: prow.ddfByVersion.blended.value, tier: prow.tier};
      snap.seriesKeys.forEach(key => {
        row[key] = values[key]?.[k] ?? null;
        const source = sourceOfSeries(key);
        const s = v.sources[source];
        const p = snap.players[source]?.[k];
        if (!s || !p) return;
        row[`${key}__native`] = p.native;
        const field = view === "indexed" && snap.publishedKeys.includes(key) ? "indexed"
          : key.endsWith("_vorp") || (view === "vorp" && snap.publishedKeys.includes(key)) ? "vorp" : "adjusted";
        row[`${key}__check`] = field === "indexed" ? (s.indexedFactor === null ? null : p.native * s.indexedFactor)
          : field === "vorp" ? p.vorp * s.vorpFactor
          : s.rates[`${p.pos}|bench`] * p.benchSlice + s.rates[`${p.pos}|starter`] * p.starterSlice;
      });
      return row;
    });
  }
  function viewTable(id, view, title, note) {
    const columns = [{key: "player_key", label: "Key", fmt: "int"}, {key: "name", label: "Player"}, {key: "pos", label: "Pos"},
      {key: "ddf_value", label: "DDF Value", fmt: "n3"}, {key: "tier", label: "Tier"},
      ...snap.seriesKeys.flatMap(key => [{key, label: label(key), fmt: "n3"},
        {key: `${key}__check`, label: `${label(key)} rebuilt`, fmt: "n3"}])];
    return table(id, title, columns, viewRows(view), {note, limit: 400});
  }
  function renderIndexed() {
    section("mi-indexed").appendChild(viewTable("indexed-players", "indexed", "Indexed (trade charts as published): natives x one factor per chart",
      "Charts: native (or estimate) x the chart's factor. Projections: their Adjusted values. Rebuilt columns recompute each value from the pipeline's intermediates."));
  }
  function renderVorp() {
    section("mi-vorp").appendChild(viewTable("vorp-players", "vorp", "VORP vs waivers: value above waivers x one factor per source (total = pie)",
      "Rebuilt = value above waivers (own units) x pie / the source's total above waivers."));
  }
  function renderAdjusted() {
    section("mi-adjusted").appendChild(viewTable("adjusted-players", "adj", "Adjusted values: slices paid at the source's group rates (total = pie)",
      "Rebuilt = bench slice x bench rate + starter slice x starter rate."));
  }

  function settingKey() {
    const s = snap.setting;
    return JSON.stringify([s.scoring, s.teams, s.roster, s.benchShare, s.positionShares]);
  }
  function priorFor(source) {
    const cacheKey = `${settingKey()}|${source}`;
    if (!priorCache.has(cacheKey)) {
      const promise = C().getPriorWeek ? C().getPriorWeek(source) : Promise.resolve({available: false, reason: "no history accessor"});
      priorCache.set(cacheKey, promise.catch(error => ({available: false, reason: String(error.message || error)})));
    }
    return priorCache.get(cacheKey);
  }
  async function renderPlayer() {
    const body = section("mi-player");
    const wanted = $("#miPlayerSearch").value.trim().toLowerCase();
    let key = null;
    players.forEach((player, k) => { if (key === null && player.name.toLowerCase() === wanted) key = k; });
    if (key === null) {
      body.appendChild(para("Pick a player to see every intermediate number for him across every source and view."));
      return;
    }
    const k = String(key);
    const player = players.get(key);
    const ticket = renderCount;
    const prow = snap.rows[k];
    const rows = await Promise.all(pipelineSources().map(async source => {
      const p = snap.players[source]?.[k];
      const s = vp().sources[source];
      const pos = s.positions[player.pos] || {};
      const row = {_id: source, label: label(source), native: p ? p.native : (snap.natives[source]?.[k] ?? null),
        estimated: prow?.estimated?.[source] || "", rank: p ? p.rank : null, role: p ? p.role : null,
        waiver: pos.waiver ?? null, starterLine: pos.starterLine ?? null, vorp: p ? p.vorp : null,
        benchSlice: p ? p.benchSlice : null, starterSlice: p ? p.starterSlice : null,
        adjusted: prow ? prow.adjusted[source] : null, vorpShown: prow ? prow.vorp[source] : null,
        indexed: prow ? prow.indexed[source] : null, reason: prow?.reasons?.[source] || ""};
      const prior = await priorFor(source);
      row.prior = prior?.available ? (prior.values?.[k] ?? null) : null;
      row.prior_note = prior?.available ? "" : (prior?.reason || "");
      return row;
    }));
    if (ticket !== renderCount) return;
    body.appendChild(para(`${player.name} (${player.pos}, ${player.team}), player_key ${key}. DDF Value ${fmt.n3(prow?.ddfByVersion?.blended?.value)} (${prow?.tier || "no"} tier); mean projected points ${fmt.n2(prow?.meanPpg)}.`));
    body.appendChild(table("player-drilldown", `${player.name}: every source, every step`, [
      {key: "label", label: "Source"}, {key: "native", label: "Native", fmt: "n3"}, {key: "estimated", label: "Estimated"},
      {key: "rank", label: "Rank", fmt: "int"}, {key: "role", label: "Role"},
      {key: "waiver", label: "Waiver line", fmt: "n3"}, {key: "starterLine", label: "Starter line", fmt: "n3"},
      {key: "vorp", label: "Above waivers (own units)", fmt: "n3"}, {key: "benchSlice", label: "Bench slice", fmt: "n3"},
      {key: "starterSlice", label: "Starter slice", fmt: "n3"}, {key: "adjusted", label: "Adjusted", fmt: "n3"},
      {key: "vorpShown", label: "VORP vs waivers", fmt: "n3"}, {key: "indexed", label: "Indexed", fmt: "n3"},
      {key: "reason", label: "Why no value"}, {key: "prior", label: "Prior week (this tab)", fmt: "n3"},
      {key: "prior_note", label: "Prior week note"}
    ], rows));
  }

  // ---------- controls ----------
  function loadPlayers() {
    players = new Map();
    (PD().getPlayers() || []).forEach(p => {
      const key = Number(p.player_key);
      const name = String(p.canonical_name || p.full_name || p.name || "").trim();
      if (Number.isInteger(key) && name) players.set(key, {name, pos: p.pos, team: p.team || "—", raw: p});
    });
    const list = $("#miPlayerList");
    list.replaceChildren(...[...players.values()].filter(p => ["QB", "RB", "WR", "TE"].includes(p.pos))
      .map(p => el("option", {value: p.name})));
  }
  function syncControls() {
    const s = snap.setting;
    $("#miScoring").value = s.scoring;
    $("#miTeams").value = String(s.teams);
    $("#miBenchShare").value = String(s.benchShare);
    const roster = $("#miRoster");
    if (!roster.childElementCount) {
      Object.keys(s.roster).filter(spot => !["K", "DST"].includes(spot)).forEach(spot => {
        const input = el("input", {type: "number", min: spot === "BENCH" ? "0" : "1", max: spot === "BENCH" ? "14" : "5", "data-spot": spot});
        input.addEventListener("change", () => C().setRosterSpot(spot, input.value));
        roster.appendChild(el("label", {}, [spot === "FLEX" ? "Flex " : spot === "BENCH" ? "Bench " : `${spot} `, input]));
      });
    }
    roster.querySelectorAll("[data-spot]").forEach(input => { input.value = String(s.roster[input.dataset.spot]); });
    const source = $("#miSource");
    if (!source.childElementCount) {
      snap.seriesKeys.forEach(key => source.appendChild(el("option", {value: key, text: label(key)})));
      source.value = snap.publishedKeys[0];
    }
    $("#miSetting").textContent = s.savedSetup ? "The charts' saved setup." : "Derived: the charts' saved 12-team lists deconstructed at this league (VP-9).";
  }
  function render() {
    renderCount += 1;
    try {
      snap = C().getInspection();
    } catch (error) {
      $("#miStatus").textContent = `Engine inspection failed: ${error.message}`;
      $("#miStatus").className = "mi-status mi-bad";
      throw error;
    }
    if (!players.size) loadPlayers();
    syncControls();
    renderChecks();
    renderInputs();
    renderTranslation();
    renderIndexed();
    renderVorp();
    renderAdjusted();
    const playerDone = renderPlayer();
    const s = snap.setting;
    $("#miStatus").textContent = `Engine ready: ${s.scoring}, ${s.teams} teams, bench share ${s.benchShare}.`;
    $("#miStatus").className = "mi-status mi-ok";
    window.MathInspector.renderedSetting = settingKey();
    return playerDone;
  }
  function scheduleRender() {
    clearTimeout(renderTimer);
    renderTimer = setTimeout(render, 30);
  }
  function bind() {
    $("#miScoring").addEventListener("change", event => C().setScoring(event.target.value));
    $("#miTeams").addEventListener("change", event => C().setTeams(Number(event.target.value)));
    $("#miBenchShare").addEventListener("change", event => C().setBenchShareFraction(Number(event.target.value)));
    ["#miSource", "#miPosition"].forEach(id => $(id).addEventListener("change", () => render()));
    $("#miPlayerSearch").addEventListener("change", () => renderPlayer());
    $("#miExportAll").addEventListener("click", () =>
      download(`math-inspector-${settingSlug()}.json`, "application/json", JSON.stringify(snap, null, 2)));
    window.addEventListener("trade-value-rows-change", scheduleRender);
  }

  window.MathInspector = {
    tables: () => Object.keys(tables),
    table: id => exportRows(id),
    csv: id => exportCsv(id),
    snapshot: () => snap,
    render,
    renderedSetting: null
  };

  function start() {
    const stamp = document.getElementById("buildStamp");
    if (stamp) $("#miBuild").textContent = stamp.textContent;
    bind();
    const wait = () => {
      if (C()?.isReady?.() && C().getInspection) render();
      else setTimeout(wait, 100);
    };
    wait();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
