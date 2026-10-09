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
  const ADJUSTED_NOTE = "The *_adjusted series (bias-corrected fits) are a different model from the Adjusted values view; they appear in Indexed only.";

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
  const groupKey = (pos, role) => `${pos} ${role}`;

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
  const position = () => $("#miPosition").value;
  const inPosition = key => position() === "ALL" || playerPos(key) === position();
  const selectedSource = () => $("#miSource").value;
  const publishedKeys = () => snap.publishedKeys;
  const selectedPublished = () => publishedKeys().includes(selectedSource()) ? [selectedSource()] : publishedKeys();
  const anchorRole = key => snap.anchor.roles[key] || "waiver";
  function comboKey12(source) {
    const base = source === "cbs_adjusted" ? "cbs" : source.replace(/_adjusted$/, "");
    const key = window.ValueModel.sourceComboKey(base, snap.setting.scoring, 12, 1);
    return key;
  }

  // ---------- 0. checks ----------
  function indexedTotals(seriesKey) {
    const values = snap.series[seriesKey] || {};
    const anchor = snap.anchor.values;
    let shared = 0, seriesShared = 0, anchorShared = 0, seriesAll = 0, anchorOver = 0, n = 0;
    Object.entries(values).forEach(([key, value]) => {
      if (!snap.positions.includes(playerPos(key)) || !isNum(value)) return;
      n += 1;
      seriesAll += value;
      const a = anchor[key];
      if (isNum(a)) {
        shared += 1;
        seriesShared += value;
        anchorShared += Math.max(0, a);
        anchorOver += Math.max(0, a);
      }
    });
    return {n, shared, seriesShared, anchorShared, seriesAll, anchorOver};
  }
  function renderChecks() {
    const body = section("mi-checks");
    body.appendChild(para("Jeremy's three view invariants, measured on the numbers below. Indexed: every chart's total equals the anchor's over the same players. VORP vs waivers: every chart's total equals our anchor's total over its players (the sum of its eight group budgets). Adjusted values: each position x starter/bench group's total equals our weight for that group times the common top-of-scale factor. Differences are shown, not hidden; the views-audit work owns whether a difference is a defect."));
    const indexedRows = snap.seriesKeys.filter(key => Object.keys(snap.series[key] || {}).length).map(key => {
      const t = indexedTotals(key);
      const delta = t.seriesShared - t.anchorShared;
      return {_id: key, series: key, label: label(key), players: t.n, shared: t.shared,
        series_total_shared: t.seriesShared, anchor_total_shared: t.anchorShared, delta,
        delta_pct: t.anchorShared > 0 ? delta / t.anchorShared : null,
        series_total_all: t.seriesAll,
        status: key === "espn" ? "anchor" : Math.abs(delta) <= Math.max(0.5, 0.001 * t.anchorShared) ? "equal" : "differs"};
    });
    body.appendChild(table("checks-indexed", "Indexed: total pie per series vs the anchor (players both price)", [
      {key: "label", label: "Series"}, {key: "players", label: "Players", fmt: "int"},
      {key: "shared", label: "Shared with anchor", fmt: "int"},
      {key: "series_total_shared", label: "Series sum (shared)", fmt: "n3"},
      {key: "anchor_total_shared", label: "Anchor sum (shared)", fmt: "n3"},
      {key: "delta", label: "Difference", fmt: "delta"}, {key: "delta_pct", label: "Difference share", fmt: "pct"},
      {key: "series_total_all", label: "Series sum (all its players)", fmt: "n3"},
      {key: "status", label: "Status"}
    ], indexedRows));

    const vorpRows = publishedKeys().map(key => {
      const p = snap.published[key];
      const displayed = sum(Object.values(p.vorp.values));
      const target = p.views ? p.views.total : null;
      return {_id: key, source: key, label: label(key), mode: p.vorp.mode, displayed_total: displayed,
        target_total: target, delta: isNum(target) ? displayed - target : null,
        status: isNum(target) && Math.abs(displayed - target) <= Math.max(0.5, 0.001 * target) ? "equal" : "differs"};
    });
    body.appendChild(table("checks-vorp", "VORP vs waivers: chart total vs our anchor's total over its players", [
      {key: "label", label: "Chart"}, {key: "mode", label: "Values shown"},
      {key: "displayed_total", label: "Chart sum (shown)", fmt: "n3"},
      {key: "target_total", label: "Anchor sum over its players (sum of budgets)", fmt: "n3"},
      {key: "delta", label: "Difference", fmt: "delta"}, {key: "status", label: "Status"}
    ], vorpRows, {note: "\"saved\" = the pipeline's saved view (exists only at its own setup); \"derived\" = the browser derivation at this setting."}));

    const adjRows = [];
    publishedKeys().forEach(key => {
      const p = snap.published[key];
      if (!p.views) return;
      snap.positions.forEach(pos => GROUPS.forEach(role => {
        const shown = sum(Object.entries(p.adj.values).filter(([k]) => p.views.roles[k]?.pos === pos && p.views.roles[k]?.role === role).map(([, v]) => v));
        const budget = Number(p.views.budgets?.[pos]?.[role]) || 0;
        const expected = budget * snap.batch.adjScale;
        adjRows.push({_id: `${key}|${pos}|${role}`, source: key, label: label(key), mode: p.adj.mode, group: groupKey(pos, role),
          shown_total: shown, budget, expected, delta: shown - expected,
          status: Math.abs(shown - expected) <= Math.max(0.05, 0.001 * expected) ? "equal" : "differs"});
      }));
    });
    body.appendChild(table("checks-adjusted", "Adjusted values: each group's total vs our weight for that group", [
      {key: "label", label: "Chart"}, {key: "mode", label: "Values shown"}, {key: "group", label: "Group"},
      {key: "shown_total", label: "Chart group sum (shown)", fmt: "n3"},
      {key: "budget", label: "Our group budget (anchor sum)", fmt: "n3"},
      {key: "expected", label: "Budget x top-of-scale factor", fmt: "n3"},
      {key: "delta", label: "Difference", fmt: "delta"}, {key: "status", label: "Status"}
    ], adjRows, {note: `Top-of-scale factor (batch) = 70 / ${fmt.n4(snap.batch.batchMax)} = ${fmt.sci(snap.batch.adjScale)}. Groups use each chart's own starter/bench split from its translation.`}));

    const fixed = (snap.fixedPie?.checks || []).map(check => ({_id: check.source, label: label(check.source), basis: check.basis,
      shared: check.shared, total: check.total, target: check.target, delta: check.delta, ok: check.ok ? "pass" : "FAIL"}));
    body.appendChild(table("checks-engine-fixed-pie", "The engine's own fixed-pie guard (fixedPieDiagnostics)", [
      {key: "label", label: "Series"}, {key: "basis", label: "Basis"}, {key: "shared", label: "Shared", fmt: "int"},
      {key: "total", label: "Total", fmt: "n3"}, {key: "target", label: "Target", fmt: "n3"},
      {key: "delta", label: "Difference", fmt: "delta"}, {key: "ok", label: "Guard"}
    ], fixed, {note: "basis \"pipeline\" = the guard does not check this chart in the browser."}));
  }

  // ---------- 1. inputs ----------
  function sourceMetaRows() {
    const snapshot = PD().getSnapshot();
    const freshness = PD().getSourceFreshness?.()?.series || {};
    return Object.entries(snapshot.sources || {}).map(([key, meta]) => {
      const combos = Object.keys(meta.combos || {});
      const combo = meta.combos?.[comboKey12(key)] || null;
      const fresh = freshness[key] || {};
      return {_id: key, source: key, name: meta.name || label(key), url: meta.url || meta.source_url || null,
        content_week: fresh.vintage_week ?? null, week_basis: fresh.basis || fresh.vintage_basis || null,
        freshness: fresh.status || null, week_designated: meta.week_designated || null,
        content_vintage: meta.content_vintage || meta.vintage || null, fetched_at: meta.fetched_at || null,
        promoted_at: meta.promoted_at || null, fit_bake_id: meta.fit_bake_id || null,
        native_unit: meta.native_unit || null, combos: combos.join(" "),
        listed_at_12: combo ? Object.keys(combo.native || {}).length : null,
        raw_vintage: meta.lineage?.raw_vintage || null, raw_sha256: meta.lineage?.raw_content_sha256 || null};
    });
  }
  function identityRows(source) {
    const snapshot = PD().getSnapshot();
    const keysById = PD().getPlayerKeysBySourceId() || new Map();
    const combo = snapshot.sources?.[source]?.combos?.[comboKey12(source)];
    if (!combo) return [];
    const nativeField = combo.native || {};
    const shownField = combo.values || combo.reindexed || {};
    const seen = new Map();
    Object.keys(nativeField).forEach(id => {
      const key = keysById.get(id);
      if (Number.isInteger(key)) seen.set(key, (seen.get(key) || 0) + 1);
    });
    return Object.keys(nativeField).map(id => {
      const key = keysById.get(id);
      const player = Number.isInteger(key) ? players.get(key) : null;
      let status = "resolved";
      if (!Number.isInteger(key)) status = "unresolved: no player_key";
      else if (!player) status = "resolved to a player not on the chart";
      else if (!snap.positions.includes(player.pos)) status = `resolved, position ${player.pos} not charted`;
      else if (seen.get(key) > 1) status = "review: two source names share this player_key";
      return {_id: `${source}|${id}`, source, source_id: id, player_key: Number.isInteger(key) ? key : null,
        player: player ? player.name : null, pos: player?.pos || null, team: player?.team || null,
        native: Number(nativeField[id]), saved_12: isNum(Number(shownField[id])) ? Number(shownField[id]) : null, status};
    });
  }
  function renderInputs() {
    const body = section("mi-inputs");
    const snapshot = PD().getSnapshot();
    body.appendChild(para(`Bake ${snapshot.bake_id || "—"}, fixture built ${snapshot.built_at || "—"}. Published charts are saved once per scoring at 12 teams and the standard roster; every other setting is derived from those saved inputs in the browser.`));
    body.appendChild(table("inputs-provenance", "Sources: provenance and content week", [
      {key: "source", label: "Key"}, {key: "name", label: "Name"}, {key: "content_week", label: "Content week", fmt: "int"},
      {key: "week_basis", label: "Week from"}, {key: "freshness", label: "Freshness"},
      {key: "week_designated", label: "Publisher label"}, {key: "content_vintage", label: "Content date"},
      {key: "fetched_at", label: "Fetched"}, {key: "promoted_at", label: "Promoted"}, {key: "fit_bake_id", label: "Fit bake"},
      {key: "native_unit", label: "Native unit"}, {key: "listed_at_12", label: "Listed (12 teams, this scoring)", fmt: "int"},
      {key: "combos", label: "Saved setups"}, {key: "url", label: "URL"},
      {key: "raw_vintage", label: "Raw vintage"}, {key: "raw_sha256", label: "Raw content sha256"}
    ], sourceMetaRows()));

    const source = selectedSource();
    const projectionField = {espn: "espn_ppg", cbsros: "cbsros_ppg", razzball: "rz_ppg",
      espn_vorp: "espn_ppg", cbsros_vorp: "cbsros_ppg", razzball_vorp: "rz_ppg"}[source];
    if (projectionField) {
      const field = snap.setting.scoringField;
      const rows = [];
      players.forEach((player, key) => {
        const ppg = player.raw?.[projectionField]?.[field];
        if (!isNum(ppg) || !inPosition(key)) return;
        rows.push({_id: key, player_key: key, player: player.name, pos: player.pos, team: player.team, per_game: ppg,
          espn_projects_zero: player.raw?.espn_projects_zero === true ? "yes" : ""});
      });
      body.appendChild(table("inputs-values", `${label(source)}: per-game projections as saved (${field})`, [
        {key: "player", label: "Player"}, {key: "pos", label: "Pos"}, {key: "team", label: "Team"},
        {key: "player_key", label: "player_key", fmt: "int"}, {key: "per_game", label: "Per game (native)", fmt: "n3"},
        {key: "espn_projects_zero", label: "ESPN projects 0"}
      ], rows, {note: "Projection series are valued by our two-tier model in the browser; the inspector shows their inputs and outputs, not the fit internals."}));
    } else {
      const rows = identityRows(source).filter(row => row.player_key === null || inPosition(row.player_key));
      body.appendChild(table("inputs-values", `${label(source)}: values as saved (12 teams, ${snap.setting.scoring})`, [
        {key: "source_id", label: "Source name"}, {key: "player", label: "Player"}, {key: "pos", label: "Pos"},
        {key: "team", label: "Team"}, {key: "player_key", label: "player_key", fmt: "int"},
        {key: "native", label: "Native (publisher units)", fmt: "n3"},
        {key: "saved_12", label: "Saved 12-team chart value", fmt: "n3"}, {key: "status", label: "Identity"}
      ], rows, {note: source.endsWith("_adjusted") ? ADJUSTED_NOTE : null}));
    }
    const review = [];
    Object.keys(snapshot.sources || {}).forEach(key => identityRows(key).forEach(row => {
      if (row.status !== "resolved") review.push(row);
    }));
    body.appendChild(table("inputs-identity", "Identity: rows not resolved to a charted player (every source, this scoring, 12 teams)", [
      {key: "source", label: "Source"}, {key: "source_id", label: "Source name"}, {key: "player_key", label: "player_key", fmt: "int"},
      {key: "player", label: "Resolved to"}, {key: "pos", label: "Pos"}, {key: "native", label: "Native", fmt: "n3"},
      {key: "status", label: "Status"}
    ], review));
  }

  // ---------- 2. translation ----------
  function renderTranslation() {
    const body = section("mi-translation");
    body.appendChild(para("Per chart and position: how many players the league rosters (dedicated starters, flex share, bench), where the waiver line falls, and each player's value above it in the chart's own units. The waiver line is the value of the first player past the rostered count; a chart that lists too few players has its line extrapolated from the other charts (imputed_from_other_charts)."));
    const posRows = [];
    publishedKeys().forEach(key => {
      const p = snap.published[key];
      const t = p.derivation?.translation;
      if (!t) return;
      const groups = p.views?.groups || {};
      const groupTotal = sum(snap.positions.flatMap(pos => GROUPS.map(role => groups[pos]?.[role])));
      snap.positions.forEach(pos => {
        const r = t.positions[pos];
        if (!r) return;
        posRows.push({_id: `${key}|${pos}`, label: label(key), pos, n_listed: r.n_listed, n_dedicated: r.n_dedicated,
          n_flex: r.n_flex, n_bench: r.n_bench, n_rostered: r.n_rostered, n_imputed: r.n_imputed,
          waiver_line: r.waiver_line_value, waiver_method: r.waiver_method, max_above: r.max_vorp, total_above: r.total_vorp,
          implied_weight: r.implied_weight,
          starter_above: groups[pos]?.starter, bench_above: groups[pos]?.bench,
          starter_weight: groupTotal > 0 ? (groups[pos]?.starter || 0) / groupTotal : null,
          bench_weight: groupTotal > 0 ? (groups[pos]?.bench || 0) / groupTotal : null});
      });
    });
    body.appendChild(table("translation-positions", "Rostered counts, waiver line and implied weights", [
      {key: "label", label: "Chart"}, {key: "pos", label: "Pos"}, {key: "n_listed", label: "Listed", fmt: "int"},
      {key: "n_dedicated", label: "Starters (dedicated)", fmt: "int"}, {key: "n_flex", label: "Flex share", fmt: "int"},
      {key: "n_bench", label: "Bench", fmt: "int"}, {key: "n_rostered", label: "Rostered", fmt: "int"},
      {key: "n_imputed", label: "Imputed past list", fmt: "int"}, {key: "waiver_line", label: "Waiver line (native)", fmt: "n3"},
      {key: "waiver_method", label: "Waiver line from"}, {key: "max_above", label: "Top above waivers (native)", fmt: "n3"},
      {key: "total_above", label: "Total above waivers (native)", fmt: "n3"},
      {key: "implied_weight", label: "Implied position weight", fmt: "pct"},
      {key: "starter_above", label: "Starter sum above waivers", fmt: "n3"}, {key: "bench_above", label: "Bench sum above waivers", fmt: "n3"},
      {key: "starter_weight", label: "Implied starter weight (share)", fmt: "pct"},
      {key: "bench_weight", label: "Implied bench weight (share)", fmt: "pct"}
    ], posRows, {note: `Translation ${snap.versions.translation} (the VORP vs waivers view's); waiver imputation ${snap.versions.imputation}. Starter/bench sums use the chart's own order: the first (dedicated + flex) players at a position are starters. Indexed does not use this translation: it is the natives times one factor (JEG-482).`}));

    selectedPublished().forEach(key => {
      const p = snap.published[key];
      const t = p.derivation?.translation;
      if (!t) return;
      const byPos = {};
      Object.entries(p.native).forEach(([k, v]) => {
        const pos = playerPos(k);
        if (!pos) return;
        (byPos[pos] = byPos[pos] || []).push({key: k, value: v});
      });
      const rows = [];
      Object.entries(byPos).forEach(([pos, list]) => {
        list.sort((a, b) => b.value - a.value).forEach((row, i) => {
          if (!inPosition(row.key)) return;
          const tr = t.translated[row.key];
          const role = p.views?.roles?.[row.key]?.role || (tr ? "above waivers" : "at or below waivers");
          rows.push({_id: `${key}|${row.key}`, player_key: Number(row.key), player: playerName(row.key), pos, rank: i + 1,
            native: row.value, waiver_line: t.positions[pos]?.waiver_line_value,
            above_native: tr ? tr.vorp : 0, role,
            indexed: p.indexed.values[row.key] ?? null});
        });
      });
      body.appendChild(table(`translation-players-${key}`, `${label(key)}: each player above waivers`, [
        {key: "player", label: "Player"}, {key: "pos", label: "Pos"}, {key: "player_key", label: "player_key", fmt: "int"},
        {key: "rank", label: "Rank at pos", fmt: "int"},
        {key: "native", label: "Native", fmt: "n3"}, {key: "waiver_line", label: "Waiver line", fmt: "n3"},
        {key: "above_native", label: "Above waivers (native, rounded 0.1)", fmt: "n1"}, {key: "role", label: "Role"},
        {key: "indexed", label: "Indexed (shown)", fmt: "n3"}
      ], rows, {note: `Indexed = native x ${p.derivation?.factor ?? "the saved factor"} (${p.indexed.mode === "saved" ? "the pipeline's saved values at this setup" : `factor measured against the anchor here, basis ${p.derivation?.basis}`}); the chart's own order is kept.`}));
    });
  }

  // ---------- 3. indexed ----------
  function renderIndexed() {
    const body = section("mi-indexed");
    body.appendChild(para("Groups are the anchor's roles at this setting (dedicated starters, then flex, then bench, by the anchor's value). Each column sums a series over the players it shares with the anchor, so the anchor column beside it is the same players. Equal totals with different group shares is the expected Indexed picture."));
    const keys = snap.seriesKeys.filter(key => Object.keys(snap.series[key] || {}).length);
    const groupRows = [];
    const shareRows = [];
    const groups = [...snap.positions.flatMap(pos => GROUPS.map(role => [pos, role])), [null, "waiver"]];
    const sums = {};
    keys.forEach(key => {
      const values = snap.series[key];
      const s = {}; const a = {};
      Object.entries(values).forEach(([k, v]) => {
        const pos = playerPos(k);
        if (!snap.positions.includes(pos) || !isNum(v) || !isNum(snap.anchor.values[k])) return;
        const role = anchorRole(k);
        const g = role === "waiver" ? "waiver" : groupKey(pos, role);
        s[g] = (s[g] || 0) + v;
        a[g] = (a[g] || 0) + Math.max(0, snap.anchor.values[k]);
      });
      sums[key] = {s, a, st: sum(Object.values(s)), at: sum(Object.values(a))};
    });
    groups.forEach(([pos, role]) => {
      const g = role === "waiver" ? "waiver" : groupKey(pos, role);
      const row = {_id: g, group: g};
      const share = {_id: g, group: g};
      keys.forEach(key => {
        row[key] = sums[key].s[g] || 0;
        row[`${key}__anchor`] = sums[key].a[g] || 0;
        share[key] = sums[key].st > 0 ? (sums[key].s[g] || 0) / sums[key].st : null;
        share[`${key}__anchor`] = sums[key].at > 0 ? (sums[key].a[g] || 0) / sums[key].at : null;
      });
      groupRows.push(row); shareRows.push(share);
    });
    const total = {_id: "total", group: "Total", _className: "mi-total"};
    keys.forEach(key => { total[key] = sums[key].st; total[`${key}__anchor`] = sums[key].at; });
    groupRows.push(total);
    const cols = fmtKey => [{key: "group", label: "Group"}, ...keys.flatMap(key => [
      {key, label: label(key), fmt: fmtKey}, {key: `${key}__anchor`, label: `anchor on ${label(key)}'s players`, fmt: fmtKey}])];
    body.appendChild(table("indexed-split-points", "Pie split, points (sum over players shared with the anchor)", cols("n2"), groupRows));
    body.appendChild(table("indexed-split-share", "Pie split, share of each series' own total", cols("pct"), shareRows));

    const rows = [];
    const universe = new Set();
    keys.forEach(key => Object.keys(snap.series[key]).forEach(k => universe.add(k)));
    universe.forEach(k => {
      if (!inPosition(k)) return;
      const row = {_id: k, player_key: Number(k), player: playerName(k), pos: playerPos(k),
        anchor_role: anchorRole(k), espn_role: snap.espnRoles[k] || "waiver"};
      keys.forEach(key => { row[key] = snap.series[key][k] ?? null; });
      rows.push(row);
    });
    rows.sort((x, y) => (y.espn ?? -1) - (x.espn ?? -1));
    body.appendChild(table("indexed-players", "Every player, every series (Indexed, as the chart shows them)", [
      {key: "player", label: "Player"}, {key: "pos", label: "Pos"}, {key: "player_key", label: "player_key", fmt: "int"},
      {key: "anchor_role", label: "Anchor role"},
      ...keys.map(key => ({key, label: label(key), fmt: "n3"}))
    ], rows, {note: ADJUSTED_NOTE}));
  }

  // ---------- 4. VORP vs waivers ----------
  function renderVorp() {
    const body = section("mi-vorp");
    body.appendChild(para("Each chart's value above waivers (its own units) times ONE factor per chart, so the chart's total equals our anchor's total over the players it ranks. The publisher's own cross-position valuation is kept; the scale is shared."));
    const summary = publishedKeys().map(key => {
      const p = snap.published[key];
      const v = p.views;
      return {_id: key, label: label(key), mode: p.vorp.mode,
        native_total: v ? sum(snap.positions.flatMap(pos => GROUPS.map(role => v.groups[pos]?.[role]))) : null,
        target: v?.total ?? null, scale: v?.vorpScale ?? null,
        shown_total: sum(Object.values(p.vorp.values)), peers: p.peers.join(" ")};
    });
    body.appendChild(table("vorp-summary", "Per chart: one factor onto the shared scale", [
      {key: "label", label: "Chart"}, {key: "mode", label: "Values shown"},
      {key: "native_total", label: "Sum above waivers (native)", fmt: "n3"},
      {key: "target", label: "Anchor sum over its players", fmt: "n3"},
      {key: "scale", label: "Factor (ratio)", fmt: "sci"}, {key: "shown_total", label: "Shown sum", fmt: "n3"},
      {key: "peers", label: "Waiver-line peers"}
    ], summary, {note: `Views ${snap.versions.views}.`}));
    const keys = publishedKeys();
    const universe = new Set();
    keys.forEach(key => Object.keys(snap.published[key].vorp.values).forEach(k => universe.add(k)));
    const rows = [];
    universe.forEach(k => {
      if (!inPosition(k)) return;
      const row = {_id: k, player_key: Number(k), player: playerName(k), pos: playerPos(k)};
      keys.forEach(key => {
        const p = snap.published[key];
        const role = p.views?.roles?.[k];
        row[`${key}__native`] = role ? role.vorp : (k in p.vorp.values ? 0 : null);
        row[`${key}__derived`] = p.views?.vorp?.[k] ?? null;
        row[key] = p.vorp.values[k] ?? null;
      });
      rows.push(row);
    });
    rows.sort((x, y) => Math.max(...keys.map(k => y[k] ?? -1)) - Math.max(...keys.map(k => x[k] ?? -1)));
    body.appendChild(table("vorp-players", "Each player on the shared scale, side by side", [
      {key: "player", label: "Player"}, {key: "pos", label: "Pos"}, {key: "player_key", label: "player_key", fmt: "int"},
      ...keys.flatMap(key => [
        {key: `${key}__native`, label: `${label(key)}: above waivers (native)`, fmt: "n1"},
        ...(snap.published[key].vorp.mode === "saved" ? [{key: `${key}__derived`, label: `${label(key)}: browser derivation`, fmt: "n3"}] : []),
        {key, label: `${label(key)}: VORP vs waivers (shown)`, fmt: "n3"}])
    ], rows));
  }

  // ---------- 5. adjusted ----------
  function renderAdjusted() {
    const body = section("mi-adjusted");
    body.appendChild(para("Players are grouped position x starter/bench by each chart's own order. Each group shares OUR anchor's total for the same group (its budget) in proportion to value above waivers; then one common factor puts the top player across every chart at 70."));
    const rows = [];
    publishedKeys().forEach(key => {
      const p = snap.published[key];
      const v = p.views;
      if (!v) return;
      const budgetTotal = sum(snap.positions.flatMap(pos => GROUPS.map(role => v.budgets?.[pos]?.[role])));
      snap.positions.forEach(pos => GROUPS.forEach(role => {
        const budget = Number(v.budgets?.[pos]?.[role]) || 0;
        const groupTotal = v.groups?.[pos]?.[role] || 0;
        const native = groupTotal;
        const nativeTotal = sum(snap.positions.flatMap(q => GROUPS.map(r => v.groups?.[q]?.[r])));
        rows.push({_id: `${key}|${pos}|${role}`, label: label(key), group: groupKey(pos, role),
          ddf_weight: budgetTotal > 0 ? budget / budgetTotal : null, chart_weight: nativeTotal > 0 ? native / nativeTotal : null,
          budget, group_native: groupTotal, group_factor: groupTotal > 0 ? budget / groupTotal : null,
          final_factor: groupTotal > 0 ? budget / groupTotal * snap.batch.adjScale : null});
      }));
    });
    body.appendChild(table("adjusted-groups", "Our weight per group, and each chart's normalization factor per group", [
      {key: "label", label: "Chart"}, {key: "group", label: "Group"},
      {key: "ddf_weight", label: "Our weight (share of budgets)", fmt: "pct"},
      {key: "chart_weight", label: "Chart's own weight (share above waivers)", fmt: "pct"},
      {key: "budget", label: "Budget (anchor sum, its players)", fmt: "n3"},
      {key: "group_native", label: "Chart sum above waivers (native)", fmt: "n3"},
      {key: "group_factor", label: "Budget / chart sum (ratio)", fmt: "sci"},
      {key: "final_factor", label: "x top-of-scale factor (ratio)", fmt: "sci"}
    ], rows, {note: `Top-of-scale: batch max ${fmt.n4(snap.batch.batchMax)} -> 70, factor ${fmt.sci(snap.batch.adjScale)}.`}));
    const keys = publishedKeys();
    const universe = new Set();
    keys.forEach(key => Object.keys(snap.published[key].adj.values).forEach(k => universe.add(k)));
    const players_ = [];
    universe.forEach(k => {
      if (!inPosition(k)) return;
      const row = {_id: k, player_key: Number(k), player: playerName(k), pos: playerPos(k)};
      keys.forEach(key => {
        const p = snap.published[key];
        const role = p.views?.roles?.[k];
        row[`${key}__role`] = role ? role.role : "at or below waivers";
        const groupTotal = role ? p.views.groups[role.pos][role.role] : 0;
        const budget = role ? Number(p.views.budgets?.[role.pos]?.[role.role]) : 0;
        row[`${key}__check`] = role && groupTotal > 0 ? role.vorp * budget / groupTotal * snap.batch.adjScale : (k in p.adj.values ? 0 : null);
        row[key] = p.adj.values[k] ?? null;
      });
      players_.push(row);
    });
    players_.sort((x, y) => Math.max(...keys.map(k => y[k] ?? -1)) - Math.max(...keys.map(k => x[k] ?? -1)));
    body.appendChild(table("adjusted-players", "Each player's adjusted value, side by side", [
      {key: "player", label: "Player"}, {key: "pos", label: "Pos"}, {key: "player_key", label: "player_key", fmt: "int"},
      ...keys.flatMap(key => [
        {key: `${key}__role`, label: `${label(key)}: group`},
        {key: `${key}__check`, label: `${label(key)}: above waivers x factor (check)`, fmt: "n3"},
        {key, label: `${label(key)}: Adjusted (shown)`, fmt: "n3"}])
    ], players_, {note: "The check column multiplies the engine's own numbers (above waivers x budget / group sum x top-of-scale factor); it equals the shown value wherever the browser derivation is what the chart shows."}));
  }

  // ---------- 6. player drill-down ----------
  function settingKey() {
    const s = snap.setting;
    return JSON.stringify([s.scoring, s.teams, s.roster, s.benchShare]);
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
    const rows = await Promise.all(snap.seriesKeys.map(async source => {
      const row = {_id: source, source, label: label(source)};
      const p = snap.published[source];
      if (p) {
        const t = p.derivation?.translation;
        const tr = t?.translated?.[k];
        const role = p.views?.roles?.[k];
        const groupTotal = role ? p.views.groups[role.pos][role.role] : null;
        const budget = role ? Number(p.views.budgets?.[role.pos]?.[role.role]) : null;
        Object.assign(row, {
          native: p.native[k] ?? null, waiver_line: t?.positions?.[player.pos]?.waiver_line_value ?? null,
          waiver_method: t?.positions?.[player.pos]?.waiver_method ?? null,
          above_native: tr ? tr.vorp : (k in p.native ? 0 : null), role: role ? role.role : (k in p.native ? "at or below waivers" : null),
          saved_12: p.saved12[k] ?? null, indexed_factor: p.derivation?.factor ?? null,
          indexed: p.indexed.values[k] ?? null, indexed_mode: p.indexed.mode,
          vorp_scale: p.views?.vorpScale ?? null, vorp: p.vorp.values[k] ?? null, vorp_mode: p.vorp.mode,
          group_budget: budget, group_native: groupTotal,
          adj_factor: groupTotal > 0 ? budget / groupTotal * snap.batch.adjScale : null,
          adj: p.adj.values[k] ?? null, adj_mode: p.adj.mode
        });
      } else {
        const field = {espn: "espn_ppg", cbsros: "cbsros_ppg", razzball: "rz_ppg", espn_vorp: "espn_ppg",
          cbsros_vorp: "cbsros_ppg", razzball_vorp: "rz_ppg"}[source];
        row.native = field ? (player.raw?.[field]?.[snap.setting.scoringField] ?? null) : null;
        row.indexed = snap.series[source]?.[k] ?? null;
        row.indexed_mode = source.endsWith("_adjusted") ? "bias-adjusted fit" : "projection model";
      }
      const prior = await priorFor(source);
      row.prior_week = prior?.priorWeek ?? prior?.week ?? null;
      row.prior = prior?.available ? (prior.values?.[k] ?? null) : null;
      row.prior_delta = isNum(row.indexed) && isNum(row.prior) ? row.indexed - row.prior : null;
      row.prior_note = prior?.available ? (row.prior === null ? "not priced that week" : prior.method || "") : (prior?.reason || "");
      return row;
    }));
    if (ticket !== renderCount) return;
    body.appendChild(para(`${player.name} (${player.pos}, ${player.team}), player_key ${key}. Anchor role at this setting: ${anchorRole(k)}; anchor value ${fmt.n3(snap.anchor.values[k])}.`));
    body.appendChild(table("player-drilldown", `${player.name}: every source, every step`, [
      {key: "label", label: "Source"}, {key: "native", label: "Input (native)", fmt: "n3"},
      {key: "waiver_line", label: "Waiver line", fmt: "n3"}, {key: "waiver_method", label: "Line from"},
      {key: "above_native", label: "Above waivers (native)", fmt: "n3"}, {key: "role", label: "Group role"},
      {key: "indexed_factor", label: "Indexed factor (one per chart)", fmt: "sci"},
      {key: "saved_12", label: "Saved 12-team value", fmt: "n3"},
      {key: "indexed", label: "Indexed (shown)", fmt: "n3"}, {key: "indexed_mode", label: "Indexed from"},
      {key: "vorp_scale", label: "VORP vs waivers factor", fmt: "sci"}, {key: "vorp", label: "VORP vs waivers (shown)", fmt: "n3"},
      {key: "vorp_mode", label: "VORP vs waivers from"},
      {key: "group_budget", label: "Group budget", fmt: "n3"}, {key: "group_native", label: "Group sum above waivers", fmt: "n3"},
      {key: "adj_factor", label: "Adjusted factor", fmt: "sci"}, {key: "adj", label: "Adjusted (shown)", fmt: "n3"},
      {key: "adj_mode", label: "Adjusted from"},
      {key: "prior_week", label: "Prior week", fmt: "int"}, {key: "prior", label: "Prior week Indexed", fmt: "n3"},
      {key: "prior_delta", label: "Change", fmt: "delta"}, {key: "prior_note", label: "Prior week note"}
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
      source.value = publishedKeys()[0];
    }
    $("#miSetting").textContent = `${s.savedSetup ? "Saved setup (published charts show saved values)" : "Derived setup (published charts derived in the browser)"}; anchor bench share measured ${fmt.pct(s.displayShare)}.`;
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
