// Trade Value v2 — Player values view.
//
// This file renders; it never computes a value. Every number comes from the
// current chart engine (curve-widget.js) through TradeValueCurveControls, which
// runs off-screen on this page. Settings changes go back through the engine's
// own setters, so v2 and the current page cannot disagree.
(function () {
  "use strict";

  const $ = id => document.getElementById(id);
  const SVG_NS = "http://www.w3.org/2000/svg";
  const PAGE_SIZE = 50;

  // Publisher identity: stable color + symbol + label (frame 17 / 22 #13).
  const PUBLISHERS = {
    espn: {label: "ESPN", color: "#0B7A4B", symbol: "●"},
    fantasycalc: {label: "FC", color: "#1F5FBF", symbol: "■"},
    fantasypros: {label: "FP", color: "#7652B8", symbol: "▲"},
    usatoday: {label: "USAT", color: "#0E7490", symbol: "◆"},
    cbs: {label: "CBS", color: "#4B5563", symbol: "▼"},
    cbsros: {label: "CBS ROS", color: "#6B7280", symbol: "▽"},
    razzball: {label: "Razzball", color: "#9D174D", symbol: "✚"}
  };
  // Dark theme: the same hues, lightened so symbols and lines keep 3:1 against the dark surfaces.
  const DARK_COLORS = {espn: "#3FBF85", fantasycalc: "#7AA7EE", fantasypros: "#AE93E4", usatoday: "#3DB6D0",
    cbs: "#A8B2BF", cbsros: "#B9BFC9", razzball: "#E7759F"};
  const darkQuery = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  const isDark = () => {
    const theme = document.documentElement.dataset.theme;
    return theme === "dark" || (theme !== "light" && Boolean(darkQuery && darkQuery.matches));
  };
  const pubColor = publisher => (isDark() && DARK_COLORS[publisher]) || PUBLISHERS[publisher]?.color || "#64736F";
  const PUBLISHER_NAMES = {
    espn: "ESPN", fantasycalc: "FantasyCalc", fantasypros: "FantasyPros", usatoday: "USA Today",
    cbs: "CBS Sports", cbsros: "CBS rest-of-season projections", razzball: "Razzball projections"
  };
  // Labels (Jeremy, 2026-10-08): plain words at 768 px and up, the short forms only below.
  const PLAIN_NAMES = {espn: "ESPN", fantasycalc: "FantasyCalc", fantasypros: "FantasyPros", usatoday: "USA Today",
    cbs: "CBS Sports", cbsros: "CBS rest of season", razzball: "Razzball"};
  const narrowQuery = window.matchMedia ? window.matchMedia("(max-width: 767px)") : null;
  const metaWideQuery = window.matchMedia ? window.matchMedia("(min-width: 1600px)") : null;   // JEG-473
  let metaNoRoom = false;   // set when the expanded columns would make the table scroll sideways
  const metaColumnsShown = () => Boolean(metaWideQuery && metaWideQuery.matches) && !metaNoRoom;
  const isNarrow = () => Boolean(narrowQuery && narrowQuery.matches);
  const SHORT_METHOD = {dda: "DDA", indexed: "Index", vorp: "VORP vs waivers"};
  const PLAIN_METHOD = {dda: "Our value", indexed: "Published chart", vorp: "VORP vs waivers"};
  const METHOD_LABEL = new Proxy({}, {get: (_, method) => (isNarrow() ? SHORT_METHOD : PLAIN_METHOD)[method]});
  // JEG-474 vocabulary: every series belongs to one of these groups, named the same everywhere.
  const SERIES_GROUPS = [
    {id: "proj", title: "Projections", one: "projection", many: "projections",
      note: "What players are projected to score, turned into trade value for your league."},
    {id: "adj", title: "Trade charts (adjusted)", one: "adjusted trade chart", many: "adjusted trade charts",
      note: "Published trade charts corrected for each publisher's known bias."},
    {id: "pub", title: "Trade charts (as published)", one: "trade chart as published", many: "trade charts as published",
      note: "Each publisher's own numbers, rescaled to our point scale."},
    {id: "vorp", title: "Value above waivers", one: "value-above-waivers series", many: "value-above-waivers series",
      note: "Advanced: raw points above a replacement-level player, each source on its own scale and shown in its own panel."}
  ];
  function seriesGroup(key) {
    if (key.endsWith("_vorp")) return "vorp";
    if (key.endsWith("_adjusted")) return "adj";
    if (key === "espn" || key === "cbsros" || key === "razzball") return "proj";
    return "pub";
  }
  // Prior-week badge (JEG-459 status language): shown only for a series whose week is behind.
  function weekBadge(key) {
    const item = view && view.infoByKey[key];
    const meta = sourceMeta(key);
    const badge = document.createElement("span");
    badge.className = "v2-wk";
    badge.textContent = item?.week ? `Wk ${item.week}` : "prior week";
    const name = PLAIN_NAMES[meta.publisher] || meta.label;
    badge.title = view?.refWeek && item?.week ? `${name} has not published Week ${view.refWeek} yet; showing Week ${item.week}.` : `${name} is from a prior week.`;
    badge.setAttribute("aria-label", badge.title);
    return badge;
  }

  // One series in plain words, whatever the width: "ESPN · Our value", "FantasyCalc chart".
  function plainSeries(publisher, method) {
    const name = PLAIN_NAMES[publisher] || PUBLISHER_NAMES[publisher] || publisher;
    return method === "indexed" ? `${name} chart` : `${name} · ${PLAIN_METHOD[method]}`;
  }

  function sourceMeta(key) {
    let method;
    let publisher;
    if (key.endsWith("_vorp")) { method = "vorp"; publisher = key.slice(0, -5); }
    else if (key.endsWith("_adjusted")) { method = "dda"; publisher = key.slice(0, -9); }
    else if (key === "espn" || key === "cbsros" || key === "razzball") { method = "dda"; publisher = key; }
    else { method = "indexed"; publisher = key; }
    const pub = PUBLISHERS[publisher] || {label: key, color: "#64736F", symbol: "•"};
    return {key, method, publisher, ...pub, color: PUBLISHERS[publisher] ? pubColor(publisher) : pub.color,
      short: isNarrow() ? `${pub.label} · ${SHORT_METHOD[method]}` : plainSeries(publisher, method)};
  }

  const SHOW_DEFAULT = "100";
  const state = {
    search: "",
    range: {min: null, max: null},
    delta: false,
    window: null,          // [lo, hi] 1-based rank window (chart and table)
    windowPreset: SHOW_DEFAULT,   // the toolbar's "Show" (JEG-475); "custom" after a brush, zoom or exact ranks
    sort: null,            // {key, dir}; null = rank-series order
    shown: PAGE_SIZE,
    hoverIndex: null,
    focusIndex: 0,
    metaCols: {pos: true, team: true, tier: true},
    hiddenGroups: new Set()   // JEG-473 Columns menu: method groups the reader hid
  };
  let C = null;            // TradeValueCurveControls
  let view = null;         // derived snapshot for rendering

  // ---------- engine bootstrap (fail closed) ----------
  function engineError() {
    const status = document.querySelector("#legacyEngine #curve-status");
    const text = status ? status.textContent || "" : "";
    return /unavailable|did not pass|failed/i.test(text) ? text.trim() : null;
  }

  function waitForEngine() {
    const started = Date.now();
    return new Promise((resolve, reject) => {
      (function poll() {
        const controls = window.TradeValueCurveControls;
        const err = engineError();
        if (err) return reject(new Error(err));
        if (controls && typeof controls.getRows === "function" && window.TradeValueCurveDiagnostics) {
          const rows = controls.getRows();
          if (rows.length) return resolve(controls);
        }
        if (Date.now() - started > 30000) return reject(new Error("The value engine did not finish loading."));
        setTimeout(poll, 120);
      })();
    });
  }

  // Frame 18: the engine failed or never finished. No tab is shown, so no
  // stale or partial value can be read as current; say why and offer a retry.
  function showFailure(reason) {
    setStatus("");
    ["v2Main", "v2Targets", "v2Risers", "v2Compare", "v2How", "v2Methods"].forEach(id => { $(id).hidden = true; });
    const card = $("v2State").querySelector(".v2-state");
    card.dataset.state = "failed";
    $("v2State").hidden = false;
    $("v2FreshnessLabel").textContent = "Values unavailable";
    $("v2StateSym").textContent = "!";
    $("v2StateTitle").textContent = "Values are unavailable right now";
    $("v2StateText").textContent = `${reason} No values are shown rather than showing wrong or partial ones.`;
    const retry = $("v2StateRetry");
    retry.hidden = false;
    retry.onclick = () => location.reload();
  }

  function setStatus(text, isError) {
    const node = $("v2Status");
    node.textContent = text || "";
    node.hidden = !text;
    node.classList.toggle("is-error", Boolean(isError));
  }

  // ---------- derived view ----------
  // Week labels come from the data's own freshness record (content week and
  // which series are an older week), the same record that picks first-load sources.
  function sourceInfoWithFreshness() {
    const info = C.getSourceInfo();
    const freshness = window.TradeValueProductData?.getSourceFreshness?.() || null;
    info.forEach(item => {
      const series = freshness?.series?.[item.key];
      if (series && typeof series.is_older_week === "boolean") item.stale = series.is_older_week;
      if (series && !item.week && Number.isFinite(series.vintage_week)) item.week = series.vintage_week;
    });
    return info;
  }
  const fmt = v => Number.isFinite(v) ? v.toFixed(1) : "—";

  // GAP-025: a label + symbol badge for players ESPN projects at 0
  // (injured/out). The engine flags them from ESPN's own row; a player ESPN has
  // no row for is missing, not 0, and gets nothing. Published values stay as
  // published; the engine gives the player an ESPN value of 0.0.
  function espnZeroBadge(row) {
    const copy = row && row.espnProjectsZero ? window.TradeValueProductData?.ESPN_ZERO_BADGE : null;
    if (!copy) return null;
    const badge = document.createElement("span");
    badge.className = "v2-espn-zero";
    badge.dataset.espnZero = "";
    badge.title = copy.title;
    const sym = document.createElement("span");
    sym.setAttribute("aria-hidden", "true");
    sym.textContent = copy.symbol;
    badge.append(sym, document.createTextNode(` ${copy.label}`));
    return badge;
  }
  function appendEspnZero(parent, row) {
    const badge = espnZeroBadge(row);
    if (badge) parent.appendChild(badge);
  }
  const tierLabel = role => ({starter: "Starter", bench: "Bench", waiver: "Waiver"}[role] || "—");

  function collect() {
    const info = sourceInfoWithFreshness();
    const infoByKey = Object.fromEntries(info.map(item => [item.key, item]));
    const active = C.getActiveSources();
    const rankKey = C.getRankSource();
    // Ranking series first, then DDA, Index, VORP (frame 22: one ordering everywhere).
    const methodOrder = {dda: 0, indexed: 1, vorp: 2};
    const ordered = active.slice().sort((a, b) => (b === rankKey) - (a === rankKey)
      || methodOrder[sourceMeta(a).method] - methodOrder[sourceMeta(b).method]);
    const plotKeys = ordered.filter(key => sourceMeta(key).method !== "vorp");
    const vorpKeys = ordered.filter(key => sourceMeta(key).method === "vorp");
    const allRows = C.getRows();
    allRows.forEach((row, index) => { row.fullRank = index + 1; });
    const needle = state.search.trim().toLowerCase();
    // Search narrows the list and renumbers it; the rank window (Show / X brush) and the value range
    // (Y brush) then compose: shown = ranks lo..hi ∩ ranking-series value in [min, max] (JEG-472).
    const rows = needle ? allRows.filter(row => String(row.name || "").toLowerCase().includes(needle)) : allRows;
    rows.forEach((row, index) => { row.rank = index + 1; });
    const freshness = window.TradeValueProductData?.getSourceFreshness?.() || null;
    const refWeek = freshness?.current_content_week || C.getReferenceWeek();
    const n = rows.length;
    const zone = zoneWindow(rows, state.windowPreset);
    if (zone) {
      state.window = [Math.min(zone[0], Math.max(1, n)), Math.max(1, Math.min(zone[1], n))];
    } else if (!state.window || state.windowPreset !== "custom") {
      const hi = state.windowPreset === "all" ? n : Number(state.windowPreset) || n;
      state.window = [1, Math.max(1, Math.min(n, hi))];
    } else {
      state.window = [Math.max(1, Math.min(state.window[0], n)), Math.max(1, Math.min(state.window[1], n))];
    }
    const {min, max} = state.range;
    const rangeOn = min !== null || max !== null;
    let omittedMissing = 0;
    const visible = rows.slice(state.window[0] - 1, state.window[1]).filter(row => {
      if (!rangeOn) return true;
      const v = row.values[rankKey];
      if (!Number.isFinite(v)) { omittedMissing += 1; return false; }
      return (min === null || v >= min) && (max === null || v <= max);
    });
    // The Y brush's scale: the ranking series' own spread over the listed players (display only).
    const rankValues = rows.map(row => row.values[rankKey]).filter(Number.isFinite);
    const yScale = {lo: Math.floor(Math.min(0, ...rankValues)), hi: Math.max(1, Math.ceil(Math.max(0, ...rankValues)))};
    view = {info, infoByKey, active, rankKey, plotKeys, vorpKeys, rows, visible, totalRows: allRows.length, omittedMissing,
      rangeOn, yScale, rankValues, refWeek, state: C.getState(), roster: C.getRosterShape()};
  }

  // Frame 21 Starter / Bench / Waiver: the engine's roster boundaries (getZones, in
  // ranking-series order) mapped onto the filtered list. null for the other presets.
  function zoneWindow(rows, preset) {
    if (!["starter", "bench", "waiver"].includes(preset) || !rows.length) return null;
    const zones = C.getZones ? C.getZones() : {};
    const sb = zones.starter_to_bench;
    const bw = zones.bench_to_waiver;
    if (!Number.isFinite(sb) || !Number.isFinite(bw)) return null;
    const inZone = row => (preset === "starter" ? row.fullRank < sb
      : preset === "bench" ? row.fullRank > sb && row.fullRank < bw : row.fullRank > bw);
    const first = rows.findIndex(inZone);
    if (first < 0) return [1, 1];
    let lastIndex = first;
    rows.forEach((row, index) => { if (inZone(row)) lastIndex = index; });
    return [first + 1, lastIndex + 1];
  }

  // GAP-043: the same per-source freshness wording the main page uses.
  function freshnessText(item) {
    const pd = window.TradeValueProductData;
    const row = pd?.getSourceFreshness?.()?.series?.[item.key];
    if (row && pd.freshnessLabel) return pd.freshnessLabel(row).text;
    return item.week ? `Week ${item.week}${item.stale ? " · older week" : ""}` : "content week unknown";
  }

  // V2-WAIVER-COVERAGE: a published chart that lists fewer players than this
  // league rosters has its waiver line extrapolated from the other charts
  // (engine getSourceInfo().waiverNote). Say so wherever its source is listed.
  function withWaiverNote(text, item) {
    return item && item.waiverNote ? `${text} · ${item.waiverNote}` : text;
  }

  function sourceLabelFor(key) {
    const meta = sourceMeta(key);
    const item = view.infoByKey[key];
    const week = item && item.week ? (isNarrow() ? ` · W${item.week}` : ` · Week ${item.week}`) : "";
    return `${meta.short}${week}`;
  }

  // JEG-475 "Show": one range control. A brush, zoom or exact ranks make it "Custom 12–48", naming the
  // ranks actually shown (rank window ∩ value range).
  function renderShow() {
    const custom = $("v2ShowCustom");
    const isCustom = state.windowPreset === "custom";
    custom.hidden = !isCustom;
    const first = view.visible[0];
    const last = view.visible[view.visible.length - 1];
    custom.textContent = first ? `Custom ${first.rank}–${last.rank}` : `Custom ${state.window[0]}–${state.window[1]}`;
    $("v2Show").value = state.windowPreset;
  }

  // ---------- header, league, methods ----------
  function renderHeader() {
    const s = view.state;
    const scoring = {standard: "Standard", half_ppr: "Half PPR", ppr: "Full PPR"}[s.scoring] || s.scoring;
    $("v2LeagueName").textContent = `${scoring} · ${s.teams} teams`;
    const r = view.roster;
    $("v2RosterLine").textContent = `${r.QB} QB · ${r.RB} RB · ${r.WR} WR · ${r.TE} TE · ${r.FLEX} FLEX · `
      + `${r.SUPERFLEX ? `${r.SUPERFLEX} SUPERFLEX · ` : ""}${r.BENCH} BN`;
    const older = view.active.some(key => view.infoByKey[key]?.stale);
    // JEG-463: the header chip summarizes root sources only; pipeline trouble shows as "not updating".
    const roots = rootFreshness();
    const stuck = roots.filter(r => r.status === "stuck").length;
    const behind = roots.filter(r => r.status === "prior").length;
    const weekText = view.refWeek ? `Week ${view.refWeek} · ` : "";
    $("v2FreshnessLabel").textContent = stuck ? `⚠ ${stuck} source${stuck === 1 ? "" : "s"} not updating`
      : `${weekText}${behind ? `${behind} source${behind === 1 ? "" : "s"} on a prior week` : "all sources current"}`;
    $("v2Freshness").classList.toggle("is-older", older || behind > 0);
    $("v2Freshness").classList.toggle("is-failing", stuck > 0);
    $("v2Freshness").setAttribute("aria-label", `Source freshness: ${$("v2FreshnessLabel").textContent}`);

    // JEG-474 / JEG-466: one "Showing: …" line, a compact legend (not buttons) and one Customize control.
    const counts = SERIES_GROUPS.map(g => ({g, n: view.active.filter(key => seriesGroup(key) === g.id).length})).filter(c => c.n);
    $("v2ShowingText").textContent = `${counts.map(c => `${c.n} ${c.n === 1 ? c.g.one : c.g.many}`).join(" + ") || "nothing selected"}`
      + (view.refWeek ? ` · Week ${view.refWeek}` : "");
    const legend = $("v2ShowingLegend");
    legend.replaceChildren();
    view.active.forEach(key => {
      const meta = sourceMeta(key);
      const item = view.infoByKey[key];
      const li = document.createElement("li");
      li.title = seriesName(key);
      li.innerHTML = `<span class="v2-sym" style="color:${meta.color}" aria-hidden="true">${meta.symbol}</span>`;
      li.append(document.createTextNode(` ${PLAIN_NAMES[meta.publisher] || meta.label}`));
      if (item?.stale) li.appendChild(weekBadge(key));
      legend.appendChild(li);
    });

    const rankBy = $("v2RankBy");
    rankBy.replaceChildren();
    view.plotKeys.concat(view.vorpKeys).forEach(key => {
      const option = document.createElement("option");
      option.value = key;
      option.textContent = `${sourceMeta(key).symbol} ${sourceMeta(key).short}`;
      option.selected = key === view.rankKey;
      rankBy.appendChild(option);
    });

    $("v2Position").value = view.state.position;
    renderShow();
    $("v2ValueLine").textContent = `Trade values for every player, tuned to your league${view.refWeek ? ` · Week ${view.refWeek}` : ""}`;
    $("v2DeltaBtn").textContent = `Δ Prior week · ${state.delta ? "On" : "Off"}`;
    $("v2DeltaBtn").setAttribute("aria-pressed", String(state.delta));
    const note = $("v2FilterNote");
    const notes = [];
    if (view.rangeOn && view.omittedMissing) {
      notes.push(`${view.omittedMissing} player${view.omittedMissing === 1 ? "" : "s"} omitted: no ${sourceMeta(view.rankKey).short} value to compare against the range.`);
    }
    if (state.delta) {
      const keys = view.plotKeys.concat(view.vorpKeys);
      const loaded = keys.filter(key => priorCache.has(key));
      const parts = loaded.map(key => {
        const prior = priorCache.get(key);
        return prior.available ? `${sourceMeta(key).short} vs Week ${prior.priorWeek}` : `${sourceMeta(key).short}: Δ —, ${prior.reason}`;
      });
      notes.push(`Δ = prior-week change for the same source at your league settings; a player with no prior value shows Δ —, never zero.${parts.length ? ` ${parts.join(". ")}.` : " Recomputing last week…"}`);
    }
    note.hidden = !notes.length;
    note.textContent = notes.join(" ");
  }

  // ---------- chart ----------
  function niceScale(value) {
    if (!Number.isFinite(value) || value <= 0) return {max: 10, step: 5};
    const step = value > 60 ? 20 : value > 20 ? 10 : value > 8 ? 5 : 2;
    return {max: Math.ceil(value / step) * step, step};
  }

  function el(name, attrs, parent) {
    const node = document.createElementNS(SVG_NS, name);
    Object.entries(attrs || {}).forEach(([k, v]) => node.setAttribute(k, v));
    if (parent) parent.appendChild(node);
    return node;
  }

  function renderLegend() {
    const legend = $("v2Legend");
    legend.replaceChildren();
    const keys = view.plotKeys.concat(view.vorpKeys);
    keys.forEach(key => {
      const meta = sourceMeta(key);
      const span = document.createElement("span");
      const swatch = el("svg", {width: 22, height: 8, "aria-hidden": "true"});
      el("line", {x1: 0, y1: 4, x2: 22, y2: 4, stroke: meta.color, "stroke-width": 2,
        "stroke-dasharray": meta.method === "indexed" ? "6 4" : meta.method === "vorp" ? "1.5 4" : ""}, swatch);
      span.appendChild(swatch);
      const twice = keys.filter(k => sourceMeta(k).publisher === meta.publisher).length > 1;
      const name = meta.method === "vorp" || twice || isNarrow() ? meta.short : (PLAIN_NAMES[meta.publisher] || meta.label);
      span.append(document.createTextNode(`${meta.symbol} ${name}`));
      span.title = plainSeries(meta.publisher, meta.method);
      legend.appendChild(span);
    });
    // The line-style key is part of the legend (JEG-475): the styles on the chart, plain words at 768 px and up.
    const methods = new Set(view.plotKeys.map(k => sourceMeta(k).method));
    const words = isNarrow() ? {dda: "Solid = DDA", indexed: "Dashed = Indexed"} : {dda: "Solid = our value", indexed: "Dashed = published chart"};
    const key = document.createElement("span");
    key.className = "v2-legend-key";
    key.textContent = ["dda", "indexed"].filter(m => methods.has(m)).map(m => words[m]).join(" · ");
    if (key.textContent) legend.appendChild(key);
  }

  function drawSeriesChart(container, keys, opts) {
    container.replaceChildren();
    const rect = container.getBoundingClientRect();
    const width = Math.max(280, rect.width);
    const height = Math.max(160, rect.height);
    // The rows shown: rank window ∩ value range (collect). X labels are each player's rank.
    const slice = view.visible;
    const n = slice.length;
    const names = opts.names && (n > 1 ? (width - 52) / (n - 1) : width) >= 64;
    const pad = {l: 40, r: 12, t: 12, b: names ? 46 : 30};
    if (opts.plot) opts.plot.style.setProperty("--v2-plot-pad-b", `${pad.b}px`);   // the Y brush lines up with the axis
    const lo = n ? slice[0].rank : state.window[0];
    const hi = n ? slice[n - 1].rank : state.window[1];
    const svg = el("svg", {viewBox: `0 0 ${width} ${height}`, role: "img",
      "aria-label": `${opts.label}: ranks ${lo} to ${hi}`}, container);
    let vmax = 0;
    slice.forEach(row => keys.forEach(key => {
      const v = row.values[key];
      if (Number.isFinite(v) && v > vmax) vmax = v;
    }));
    const {max: ymax, step: ystep} = niceScale(vmax);
    const ymin = 0;
    const x = i => pad.l + (n <= 1 ? (width - pad.l - pad.r) / 2 : (i / (n - 1)) * (width - pad.l - pad.r));
    const y = v => pad.t + (1 - (Math.min(ymax, Math.max(ymin, v)) - ymin) / (ymax - ymin)) * (height - pad.t - pad.b);
    const grid = el("g", {class: "grid"}, svg);
    const axis = el("g", {class: "axis"}, svg);
    for (let v = ymin; v <= ymax + 1e-9; v += ystep) {
      el("line", {x1: pad.l, x2: width - pad.r, y1: y(v), y2: y(v)}, grid);
      const label = el("text", {x: pad.l - 8, y: y(v) + 4, "text-anchor": "end"}, axis);
      label.textContent = Math.round(v);
    }
    const xTicks = Math.min(5, n);
    for (let t = 0; t < xTicks; t += 1) {
      const i = xTicks === 1 ? 0 : Math.round((t / (xTicks - 1)) * (n - 1));
      const label = el("text", {x: x(i), y: height - (names ? 30 : 10), "text-anchor": "middle"}, axis);
      label.textContent = slice[i].rank;
    }
    if (names) {
      {
        slice.forEach((row, i) => {
          const label = el("text", {x: x(i), y: height - 8, "text-anchor": "middle", class: "name-label"}, svg);
          const last = String(row.name || "").split(" ").slice(-1)[0];
          label.textContent = last.length > 11 ? `${last.slice(0, 10)}…` : last;
        });
      }
    }
    keys.forEach(key => {
      const meta = sourceMeta(key);
      let d = "";
      let pen = false;
      slice.forEach((row, i) => {
        const v = row.values[key];
        if (Number.isFinite(v)) {
          d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(Math.max(0, v)).toFixed(1)}`;
          pen = true;
        } else {
          pen = false;
        }
      });
      if (!d) return;
      const cls = `series is-${meta.method === "dda" ? "dda" : meta.method}${view.infoByKey[key]?.stale ? " is-older" : ""}`;
      el("path", {d, class: cls, stroke: meta.color, "data-source": key}, svg);
    });
    const overlay = el("g", {class: "hover"}, svg);
    return {svg, overlay, x, y, slice, width, height, pad, keys};
  }

  let mainChart = null;
  let vorpChart = null;

  function renderCharts() {
    renderLegend();
    mainChart = drawSeriesChart($("v2Chart"), view.plotKeys, {label: "Trade value by player rank", names: true, plot: $("v2Plot")});
    const vorpCard = $("v2VorpCard");
    vorpCard.hidden = !view.vorpKeys.length;
    vorpChart = view.vorpKeys.length
      ? drawSeriesChart($("v2VorpChart"), view.vorpKeys, {label: "VORP vs waivers by player rank"})
      : null;
    const [lo, hi] = state.window;
    const n = Math.max(1, view.rows.length);
    // X rank brush: the whole list under two handles, an overview line, labels at the thumbs.
    ["v2BrushLo", "v2BrushHi"].forEach(id => { $(id).max = String(n); });
    $("v2BrushLo").value = String(lo);
    $("v2BrushHi").value = String(hi);
    const xAt = v => ((v - 1) / Math.max(1, n - 1)) * 100;
    const fill = $("v2BrushFill");
    fill.style.left = `${xAt(lo)}%`;
    fill.style.width = `${xAt(hi) - xAt(lo)}%`;
    $("v2XLoLabel").textContent = String(lo);
    $("v2XHiLabel").textContent = String(hi);
    $("v2XLoLabel").style.left = `${xAt(lo)}%`;
    $("v2XHiLabel").style.left = `${xAt(hi)}%`;
    $("v2BrushLo").setAttribute("aria-valuetext", `Rank ${lo}`);
    $("v2BrushHi").setAttribute("aria-valuetext", `Rank ${hi}`);
    drawOverview();
    renderYBrush();
    drawHover();
  }

  // JEG-472 Y value brush: the ranking series' values on a vertical track beside the plot. The
  // handles set state.range (the same filter as "Set exact values"); full extent = no filter.
  function renderYBrush() {
    const {lo: ylo, hi: yhi} = view.yScale;
    const loV = Math.max(ylo, Math.min(yhi, state.range.min ?? ylo));
    const hiV = Math.max(ylo, Math.min(yhi, state.range.max ?? yhi));
    const yAt = v => (1 - (v - ylo) / Math.max(1e-9, yhi - ylo)) * 100;
    ["v2YBrushLo", "v2YBrushHi"].forEach(id => { $(id).min = String(ylo); $(id).max = String(yhi); });
    if (document.activeElement !== $("v2YBrushLo")) $("v2YBrushLo").value = String(loV);
    if (document.activeElement !== $("v2YBrushHi")) $("v2YBrushHi").value = String(hiV);
    $("v2YBrushLo").setAttribute("aria-valuetext", `Value ${fmt(loV)}`);
    $("v2YBrushHi").setAttribute("aria-valuetext", `Value ${fmt(hiV)}`);
    const fill = $("v2YBrushFill");
    fill.style.top = `${yAt(hiV)}%`;
    fill.style.height = `${yAt(loV) - yAt(hiV)}%`;
    $("v2YHiLabel").textContent = fmt(hiV);
    $("v2YLoLabel").textContent = fmt(loV);
    $("v2YHiLabel").style.top = `${yAt(hiV)}%`;
    $("v2YLoLabel").style.top = `${yAt(loV)}%`;
    $("v2YBrush").classList.toggle("is-on", view.rangeOn);
    drawYOverview();
  }

  // Mini overview of the Y brush: how many listed players sit at each value (ranking series).
  function drawYOverview() {
    const svg = $("v2YBrushOverview");
    svg.replaceChildren();
    const {lo: ylo, hi: yhi} = view.yScale;
    const bins = 24;
    const counts = new Array(bins).fill(0);
    view.rankValues.forEach(v => {
      const b = Math.min(bins - 1, Math.max(0, Math.floor(((v - ylo) / Math.max(1e-9, yhi - ylo)) * bins)));
      counts[b] += 1;
    });
    const most = Math.max(1, ...counts);
    svg.setAttribute("viewBox", `0 0 100 ${bins}`);
    counts.forEach((count, b) => {
      if (!count) return;
      const w = Math.max(14, Math.sqrt(count / most) * 100);   // square root: the long tail near zero stays readable
      el("rect", {x: 100 - w, y: bins - b - 1 + 0.12, width: w, height: 0.76, class: "overview-bar",
        fill: sourceMeta(view.rankKey).color}, svg);
    });
  }

  function drawOverview() {
    const svg = $("v2BrushOverview");
    svg.replaceChildren();
    const rows = view.rows;
    const values = rows.map(row => row.values[view.rankKey]);
    const max = Math.max(0, ...values.filter(Number.isFinite));
    if (!rows.length || !(max > 0)) return;
    svg.setAttribute("viewBox", `0 0 ${Math.max(1, rows.length - 1)} 100`);
    let d = "";
    let pen = false;
    values.forEach((v, i) => {
      if (Number.isFinite(v)) { d += `${pen ? "L" : "M"}${i},${(100 - (Math.max(0, v) / max) * 90).toFixed(1)}`; pen = true; }
      else pen = false;
    });
    el("path", {d, class: "overview", stroke: sourceMeta(view.rankKey).color, "vector-effect": "non-scaling-stroke"}, svg);
  }

  function drawHover() {
    [mainChart, vorpChart].forEach(chart => {
      if (!chart) return;
      chart.overlay.replaceChildren();
      const i = state.hoverIndex;
      if (i === null || i < 0 || i >= chart.slice.length) return;
      const row = chart.slice[i];
      const cx = chart.x(i);
      el("line", {x1: cx, x2: cx, y1: chart.pad.t, y2: chart.height - chart.pad.b, class: "crosshair"}, chart.overlay);
      chart.keys.forEach(key => {
        const v = row.values[key];
        if (!Number.isFinite(v)) return;
        el("circle", {cx, cy: chart.y(Math.max(0, v)), r: key === view.rankKey ? 5 : 4,
          fill: sourceMeta(key).color, class: "hover-dot"}, chart.overlay);
      });
    });
    showTip();
  }

  function hoveredRow() {
    if (state.hoverIndex === null || !mainChart) return null;
    return mainChart.slice[state.hoverIndex] || null;
  }

  // Prior-week values come from the engine (getPriorWeek, recomputed at the
  // current setting). Cached per series; cleared whenever the engine's rows change.
  const priorCache = new Map();
  let priorStamp = 0;
  function priorsFor(keys) {
    const stamp = priorStamp;
    const todo = [...new Set(keys)].filter(key => !priorCache.has(key));
    return Promise.all(todo.map(key => Promise.resolve()
      .then(() => C.getPriorWeek(key))
      .catch(error => ({available: false, reason: `could not recompute the prior week: ${error.message}`}))
      .then(result => { if (stamp === priorStamp) priorCache.set(key, result || {available: false, reason: "no prior week"}); })));
  }
  // Δ for one cell: {text, cls, title}. "Δ —" plus a reason when there is no exact pair.
  function deltaInfo(row, key) {
    const prior = priorCache.get(key);
    if (!prior) return {text: "Δ …", cls: "", title: "Recomputing last week for your league…"};
    const d = window.TradeValueMovers.deltaFor(row.values[key], prior, String(row.player_key));
    if (d.delta === null) return {text: "Δ —", cls: "", title: d.reason};
    const text = fmtGap(d.delta);
    return {text: `Δ ${text}`, cls: text === "0.0" ? "" : d.delta > 0 ? "up" : "down", title: `vs Week ${prior.priorWeek}: ${fmt(d.before)}`};
  }
  function deltaText(row, key) {
    return deltaInfo(row, key).text;
  }

  function showTip() {
    const tip = $("v2Tip");
    const row = hoveredRow();
    if (!row || !mainChart) { tip.hidden = true; return; }
    const keys = view.plotKeys.concat(view.vorpKeys);
    const weekNote = view.refWeek ? ` · W${view.refWeek}` : "";
    tip.innerHTML = "";
    const h = document.createElement("h3");
    h.textContent = row.name;
    appendEspnZero(h, row);
    const meta = document.createElement("span");
    meta.className = "v2-meta";
    meta.textContent = `#${row.rank} · ${row.pos} · ${row.team || "FA"} · ${tierLabel(row.espnRole)}${weekNote}`;
    tip.append(h, meta);
    keys.forEach(key => {
      const m = sourceMeta(key);
      const line = document.createElement("div");
      line.className = `row${key === view.rankKey ? " is-rank" : ""}`;
      line.style.color = key === view.rankKey ? "" : m.color;
      const v = row.values[key];
      line.innerHTML = `<span aria-hidden="true">${m.symbol}</span>`;
      line.append(document.createTextNode(m.short));
      const val = document.createElement("span");
      val.className = "val";
      val.textContent = Number.isFinite(v) ? fmt(v) + (state.delta ? `  ${deltaText(row, key)}` : "") : "—";
      line.appendChild(val);
      tip.appendChild(line);
    });
    const hint = document.createElement("span");
    hint.className = "v2-meta";
    hint.style.marginTop = "8px";
    hint.textContent = "Click for player details ↗";
    tip.appendChild(hint);
    tip.hidden = false;
    const box = $("v2Chart").getBoundingClientRect();
    const scale = box.width / mainChart.width;
    const px = box.left + mainChart.x(state.hoverIndex) * scale;
    const tipBox = tip.getBoundingClientRect();
    let left = px + 16;
    if (left + tipBox.width > window.innerWidth - 8) left = px - tipBox.width - 16;
    left = Math.max(8, left);
    let top = box.top + 12;
    if (top + tipBox.height > window.innerHeight - 8) top = window.innerHeight - tipBox.height - 8;
    tip.style.left = `${left}px`;
    tip.style.top = `${Math.max(8, top)}px`;
  }

  function indexFromEvent(event, chart, container) {
    const box = container.getBoundingClientRect();
    const scale = chart.width / box.width;
    const px = (event.clientX - box.left) * scale;
    const n = chart.slice.length;
    if (n <= 1) return 0;
    const step = (chart.width - chart.pad.l - chart.pad.r) / (n - 1);
    return Math.max(0, Math.min(n - 1, Math.round((px - chart.pad.l) / step)));
  }

  function bindChart(containerId, getChart) {
    const container = $(containerId);
    container.addEventListener("mousemove", event => {
      const chart = getChart();
      if (!chart) return;
      state.hoverIndex = indexFromEvent(event, chart, container);
      state.focusIndex = state.hoverIndex;
      drawHover();
    });
    container.addEventListener("mouseleave", () => { state.hoverIndex = null; drawHover(); });
    container.addEventListener("click", event => {
      const chart = getChart();
      if (!chart) return;
      const row = chart.slice[indexFromEvent(event, chart, container)];
      if (row) openDrawer(row);
    });
  }

  function bindChartKeys() {
    const chartNode = $("v2Chart");
    chartNode.addEventListener("keydown", event => {
      if (!mainChart) return;
      const n = mainChart.slice.length;
      if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        event.preventDefault();
        const base = state.hoverIndex ?? state.focusIndex ?? 0;
        state.hoverIndex = Math.max(0, Math.min(n - 1, base + (event.key === "ArrowRight" ? 1 : -1)));
        state.focusIndex = state.hoverIndex;
        drawHover();
      } else if (event.key === "Enter") {
        const row = hoveredRow();
        if (row) openDrawer(row);
      } else if (event.key === "Escape") {
        state.hoverIndex = null;
        drawHover();
      }
    });
    chartNode.addEventListener("blur", () => { state.hoverIndex = null; drawHover(); });
  }

  // ---------- table ----------
  // JEG-473: value columns are grouped by each series' existing method (and the publisher's kind for
  // Data Driven Adjustments), in this order. The Columns menu hides whole groups.
  const TABLE_GROUPS = [["projections", "Projections"], ["adjusted", "Trade charts adjusted"],
    ["published", "Trade charts as published"], ["vorp", "VORP vs waivers"], ["spread", "Spread"]];
  function tableGroup(key) {
    const meta = sourceMeta(key);
    if (meta.method === "vorp") return "vorp";
    if (meta.method === "indexed") return "published";
    return KIND[meta.publisher] === "Projection-based" ? "projections" : "adjusted";
  }
  const groupOrder = id => TABLE_GROUPS.findIndex(([g]) => g === id);

  function tableColumns() {
    const valueKeys = view.plotKeys.concat(view.vorpKeys)
      .filter(key => key === view.rankKey || !state.hiddenGroups.has(tableGroup(key)));
    const cols = [
      {id: "rank", label: "#", cls: "rank", get: row => row.rank},
      {id: "name", label: "Player", cls: "player", get: row => row.name, text: true},
      {id: "pos", label: "Pos", cls: "col-meta", get: row => row.pos, text: true},
      {id: "team", label: "Team", cls: "col-meta", get: row => row.team || "FA", text: true},
      {id: "tier", label: "Tier", cls: "col-meta", get: row => tierLabel(row.espnRole), text: true}
    ].filter(col => state.metaCols[col.id] !== false)
      .filter(col => col.cls !== "col-meta" || metaColumnsShown());
    // Ranking series first (it is the sort basis), then the groups in their fixed order.
    valueKeys.slice().sort((a, b) => (b === view.rankKey) - (a === view.rankKey) || groupOrder(tableGroup(a)) - groupOrder(tableGroup(b)))
      .forEach(key => cols.push({id: key, label: sourceLabelFor(key), source: key, cls: "num", group: tableGroup(key),
        get: row => row.values[key]}));
    const ddaKeys = view.plotKeys.filter(key => sourceMeta(key).method === "dda");
    if (ddaKeys.length >= 2 && !state.hiddenGroups.has("spread")) {
      cols.push({id: "spread", label: isNarrow() ? "DDA spread" : "Spread of our values", cls: "num", group: "spread", get: row => {
        const values = ddaKeys.map(key => row.values[key]).filter(Number.isFinite);
        return values.length >= 2 ? Math.max(...values) - Math.min(...values) : null;
      }});
    }
    return cols;
  }

  function sortedRows(cols) {
    const rows = view.visible.slice();
    if (!state.sort) return rows;
    const col = cols.find(c => c.id === state.sort.key);
    if (!col) return rows;
    const dir = state.sort.dir === "asc" ? 1 : -1;
    return rows.sort((a, b) => {
      const va = col.get(a);
      const vb = col.get(b);
      if (col.text) return dir * String(va).localeCompare(String(vb));
      const fa = Number.isFinite(va);
      const fb = Number.isFinite(vb);
      if (!fa && !fb) return a.rank - b.rank;
      if (!fa) return 1;   // missing values always sort last, never as zero
      if (!fb) return -1;
      return dir * (va - vb) || a.rank - b.rank;
    });
  }

  // Two-line header: publisher on line 1, method in small caps on line 2 (week only when older).
  function headerLabel(button, col) {
    const line1 = document.createElement("span");
    line1.className = "th-1";
    const line2 = document.createElement("span");
    line2.className = "th-2";
    if (col.source) {
      const meta = sourceMeta(col.source);
      const item = view.infoByKey[col.source];
      line1.innerHTML = `<span class="v2-sym" style="color:${meta.color}" aria-hidden="true">${meta.symbol}</span> `;
      line1.append(document.createTextNode(PLAIN_NAMES[meta.publisher] || meta.label));
      line2.textContent = METHOD_LABEL[meta.method];
      if (item?.stale && item.week) {
        const older = document.createElement("span");
        older.className = "is-older";
        older.textContent = ` · Week ${item.week}`;
        line2.appendChild(older);
      }
      button.title = `${plainSeries(meta.publisher, meta.method)}${item?.week ? ` · Week ${item.week}` : ""}`;
    } else if (col.id === "spread") {
      line1.textContent = "Spread";
      line2.textContent = isNarrow() ? "DDA" : "of our values";
    } else {
      line1.textContent = col.label;
    }
    button.append(line1);
    if (line2.textContent) button.append(line2);
  }

  // Heatmap tint (presentational): a cell against the same row's ranking-series value, both shown in
  // the row. Colour only, never a number; the direction is also in the cell's title and screen-reader text.
  function heatFor(row, key) {
    if (key === view.rankKey || sourceMeta(key).method === "vorp" || sourceMeta(view.rankKey).method === "vorp") return null;
    const v = row.values[key];
    const r = row.values[view.rankKey];
    if (!Number.isFinite(v) || !Number.isFinite(r)) return null;
    const ratio = Math.abs(v - r) / Math.max(Math.abs(r), 1);
    const level = ratio >= 0.3 ? 3 : ratio >= 0.15 ? 2 : ratio >= 0.05 ? 1 : 0;
    return {dir: level === 0 ? "same" : v > r ? "above" : "below", level, rankValue: r};
  }
  const HEAT_WORDS = {above: "above", below: "below", same: "about level with"};

  function missingReason(key) {
    const item = view.infoByKey[key];
    const name = sourceMeta(key).short;
    if (item && !item.available) return `${name} is unavailable right now, so no player has a value from it`;
    return `${name} has no value for this player`;
  }

  function renderTable(retry) {
    if (!retry) metaNoRoom = false;
    const cols = tableColumns();
    const table = $("v2Table");
    table.replaceChildren();
    const thead = document.createElement("thead");
    // Grouped top row (JEG-473): one cell per run of columns in the same group.
    const gr = document.createElement("tr");
    gr.className = "v2-group-row";
    const runs = [];
    cols.forEach(col => {
      const id = col.source === view.rankKey ? "rank-series" : col.group || "";
      const last = runs[runs.length - 1];
      if (last && last.id === id) last.span += 1;
      else runs.push({id, span: 1});
    });
    runs.forEach(run => {
      const th = document.createElement("th");
      th.scope = "colgroup";
      th.colSpan = run.span;
      th.className = run.id ? `grp grp-${run.id}` : "grp";
      if (run.id) th.dataset.group = run.id;
      if (run.id === "rank-series") { th.textContent = "Ranking"; th.classList.add("is-rank"); }
      else if (run.id) th.textContent = TABLE_GROUPS.find(([g]) => g === run.id)[1];
      gr.appendChild(th);
    });
    const hr = document.createElement("tr");
    hr.className = "v2-head-row";
    cols.forEach(col => {
      const th = document.createElement("th");
      th.scope = "col";
      th.dataset.col = col.id;
      if (col.group) th.dataset.group = col.group;
      if (col.cls) th.className = col.cls;
      if (col.source === view.rankKey) th.classList.add("is-rank");
      const sortKey = state.sort ? state.sort.key : view.rankKey;
      if (sortKey === col.id) th.setAttribute("aria-sort", state.sort && state.sort.dir === "asc" ? "ascending" : "descending");
      if (col.id === "rank") { th.textContent = col.label; }
      else {
        const button = document.createElement("button");
        button.type = "button";
        headerLabel(button, col);
        button.addEventListener("click", () => {
          const current = state.sort ? state.sort.key : view.rankKey;
          const dir = current === col.id && (!state.sort || state.sort.dir === "desc") ? "asc" : "desc";
          state.sort = {key: col.id, dir: col.text && current !== col.id ? "asc" : dir};
          renderTable();
        });
        th.appendChild(button);
      }
      hr.appendChild(th);
    });
    thead.append(gr, hr);
    const tbody = document.createElement("tbody");
    const rows = sortedRows(cols);
    const rankName = sourceMeta(view.rankKey).short;
    rows.slice(0, state.shown).forEach(row => {
      const tr = document.createElement("tr");
      tr.tabIndex = 0;
      tr.dataset.playerKey = String(row.player_key);
      tr.addEventListener("click", () => openDrawer(row));
      tr.addEventListener("keydown", event => { if (event.key === "Enter") openDrawer(row); });
      cols.forEach(col => {
        const td = document.createElement("td");
        if (col.cls) td.className = col.cls;
        if (col.source === view.rankKey) td.classList.add("is-rank");
        if (col.source) td.dataset.source = col.source;
        const v = col.get(row);
        if (col.cls === "num") {
          if (Number.isFinite(v)) {
            td.textContent = fmt(v);
            const heat = col.source ? heatFor(row, col.source) : null;
            if (heat) {
              if (heat.level) td.classList.add(`heat-${heat.dir === "above" ? "up" : "down"}-${heat.level}`);
              td.dataset.vs = heat.dir;
              td.title = `${fmt(v)}: ${HEAT_WORDS[heat.dir]} the ranking value (${rankName} ${fmt(heat.rankValue)})`;
              const sr = document.createElement("span");
              sr.className = "v2-sr";
              sr.textContent = `, ${HEAT_WORDS[heat.dir]} the ranking value`;
              td.appendChild(sr);
            }
            if (state.delta && col.source) {
              const info = deltaInfo(row, col.source);
              const d = document.createElement("span");
              d.className = `delta ${info.cls}`;
              d.dataset.source = col.source;
              d.textContent = info.text;
              d.title = info.title;
              td.appendChild(d);
            }
          } else {
            const reason = col.source ? missingReason(col.source) : "Needs at least two of our values for this player";
            const dash = document.createElement("span");
            dash.className = "missing";
            dash.title = reason;
            dash.textContent = "—";
            const sr = document.createElement("span");
            sr.className = "v2-sr";
            sr.textContent = `: ${reason}`;
            dash.appendChild(sr);
            td.appendChild(dash);
          }
        } else {
          td.textContent = v;
          if (col.id === "name") {
            appendEspnZero(td, row);
            // Pos / Team / Tier fold into this sub-line where their columns are collapsed (below 1600 px).
            const parts = metaColumnsShown() ? [] : [state.metaCols.pos !== false && row.pos, state.metaCols.team !== false && (row.team || "FA"),
              state.metaCols.tier !== false && tierLabel(row.espnRole)].filter(Boolean);
            if (parts.length) {
              const sub = document.createElement("span");
              sub.className = "player-sub";
              sub.textContent = parts.join(" · ");
              td.appendChild(sub);
            }
          }
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.append(thead, tbody);
    if (metaColumnsShown() && cols.some(col => col.cls === "col-meta")) {
      const wrap = $("v2TableWrap");
      if (wrap.scrollWidth > wrap.clientWidth + 1) { metaNoRoom = true; renderTable(true); return; }
    }
    const more = $("v2ShowMore");
    more.hidden = rows.length <= state.shown;
    more.textContent = `Show more players (${Math.min(state.shown, rows.length)} of ${rows.length})`;
    const weeks = [...new Set(cols.filter(col => col.source && !view.infoByKey[col.source]?.stale)
      .map(col => view.infoByKey[col.source]?.week).filter(Boolean))];
    const hidden = TABLE_GROUPS.filter(([g]) => state.hiddenGroups.has(g)).length;
    const [lo, hi] = state.window;
    const valueText = view.rangeOn ? ` · values ${fmt(state.range.min ?? view.yScale.lo)}–${fmt(state.range.max ?? view.yScale.hi)}` : "";
    $("v2TableMeta").textContent = `${rows.length} of ${view.rows.length} players · ranks ${lo}–${hi}${valueText}`
      + `${weeks.length === 1 ? ` · Week ${weeks[0]}` : ""}${hidden ? ` · ${hidden} column group${hidden === 1 ? "" : "s"} hidden` : ""}`
      + " · tint = above or below the ranking value";
  }

  // ---------- player detail (frame 13 drawer, frame 14 full screen) ----------
  let lastFocus = null;
  let drawerRow = null;
  const METHOD_COLUMNS = [["dda", "Our value"], ["indexed", "Published chart"], ["vorp", "VORP vs waivers"]];
  const METHOD_FULL = {dda: "Our Data Driven Adjustments", indexed: "Indexed", vorp: "VORP vs waivers"};

  function drawerSection(title, sub) {
    const section = document.createElement("section");
    section.className = "v2-dsection";
    const h = document.createElement("h3");
    h.textContent = title;
    section.appendChild(h);
    if (sub) {
      const p = document.createElement("p");
      p.className = "v2-meta";
      p.textContent = sub;
      section.appendChild(p);
    }
    return section;
  }

  // Hero (frame 13): the ranking series' value, and the range across the selected
  // Data Driven Adjustments series (the same unit; frame 03: DDA only in a spread).
  function drawerHero(row) {
    const key = view.rankKey;
    const meta = sourceMeta(key);
    const item = view.infoByKey[key];
    const hero = document.createElement("div");
    hero.className = "v2-dhero";
    const main = document.createElement("div");
    const eyebrow = document.createElement("p");
    eyebrow.className = "v2-eyebrow";
    eyebrow.textContent = `${PUBLISHER_NAMES[meta.publisher] || meta.label} · ${METHOD_FULL[meta.method]}${item?.week ? ` · W${item.week}` : ""}`;
    const big = document.createElement("p");
    big.className = "v2-dhero-value";
    big.dataset.source = key;
    const v = row.values[key];
    if (Number.isFinite(v)) big.textContent = fmt(v);
    else big.appendChild(missingNode(`No ${seriesName(key)} value for ${row.name}`, "not priced by this source"));
    const unit = document.createElement("p");
    unit.className = "v2-meta";
    unit.textContent = meta.method === "vorp" ? "VORP vs waivers, on this source's own scale" : "Trade-value points";
    main.append(eyebrow, big, unit);
    hero.appendChild(main);
    const dda = view.active.filter(k => sourceMeta(k).method === "dda" && view.infoByKey[k]?.available)
      .map(k => row.values[k]).filter(Number.isFinite);
    if (dda.length >= 2) {
      const range = document.createElement("div");
      range.className = "v2-dhero-range";
      const label = document.createElement("p");
      label.className = "v2-eyebrow";
      label.textContent = "Range across our selected values";
      const value = document.createElement("p");
      value.dataset.range = "dda";
      value.textContent = `${fmt(Math.min(...dda))}–${fmt(Math.max(...dda))}`;
      range.append(label, value);
      hero.appendChild(range);
    }
    return hero;
  }

  // Frame 13 "Source values": one row per publisher, one column per method.
  function drawerMatrix(row) {
    const section = drawerSection("Source values", "Every available method. A missing value stays missing, never zero.");
    const wrap = document.createElement("div");
    wrap.className = "v2-dmatrix-wrap";
    const table = document.createElement("table");
    table.className = "v2-dmatrix";
    const head = document.createElement("tr");
    [["Source / week", "player"]].concat(METHOD_COLUMNS.map(([, label]) => [label, "num"])).forEach(([text, cls]) => {
      const th = document.createElement("th");
      th.scope = "col";
      th.className = cls;
      th.textContent = text;
      head.appendChild(th);
    });
    const thead = document.createElement("thead");
    thead.appendChild(head);
    const tbody = document.createElement("tbody");
    const publishers = Object.keys(PUBLISHERS).filter(pub => view.info.some(item => sourceMeta(item.key).publisher === pub));
    publishers.forEach(pub => {
      const tr = document.createElement("tr");
      const series = Object.fromEntries(view.info.filter(item => sourceMeta(item.key).publisher === pub)
        .map(item => [sourceMeta(item.key).method, item]));
      const any = Object.values(series).find(item => item.available) || Object.values(series)[0];
      const th = document.createElement("th");
      th.scope = "row";
      th.className = `player${any?.stale ? " is-older" : ""}`;
      th.innerHTML = `<span style="color:${pubColor(pub)}" aria-hidden="true">${PUBLISHERS[pub].symbol}</span> `;
      th.append(document.createTextNode(`${PUBLISHER_NAMES[pub]}${any?.week ? ` · W${any.week}` : ""}`));
      const prov = document.createElement("span");
      prov.className = "th-sub";
      // Provenance only when it says more than the week already in the label.
      const provText = any ? withWaiverNote(freshnessText(any), any) : "";
      prov.textContent = provText === `Week ${any?.week}` ? "" : provText;
      if (prov.textContent) th.appendChild(prov);
      tr.appendChild(th);
      METHOD_COLUMNS.forEach(([method]) => {
        const td = document.createElement("td");
        td.className = "num";
        const item = series[method];
        if (!item) {
          const na = missingNode(`${PUBLISHER_NAMES[pub]} has no ${METHOD_LABEL[method]} series`, "no such series");
          na.querySelector(".why").className = "v2-sr";
          td.appendChild(na);
          td.classList.add("is-na");
        } else if (!item.available) {
          td.appendChild(missingNode(item.paused ? "Waiting on fresh inputs" : "Not available for this league",
            item.paused ? "waiting on inputs" : "not for this league"));
        } else if (view.active.includes(item.key)) {
          td.dataset.source = item.key;
          const v = row.values[item.key];
          if (Number.isFinite(v)) td.textContent = fmt(v);
          else td.appendChild(missingNode(`No ${seriesName(item.key)} value for ${row.name}`, "not priced"));
        } else {
          const add = document.createElement("button");
          add.type = "button";
          add.className = `v2-link v2-dadd${item.stale ? " is-older" : ""}`;
          add.dataset.addSeries = item.key;
          add.textContent = item.stale ? "Older ↗" : "Available ↗";
          add.setAttribute("aria-label", `Add ${seriesName(item.key)}${item.stale ? " (older week)" : ""} to the selected sources`);
          add.addEventListener("click", () => {
            if (!toggleEngineSource(item.key)) return;
            refresh();
            openDrawer(drawerRow);
          });
          td.appendChild(add);
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.append(thead, tbody);
    wrap.appendChild(table);
    const note = document.createElement("p");
    note.className = "v2-meta";
    note.textContent = "Adjusted and Indexed share the trade-value point scale for your league. VORP vs waivers is each source's own unit and is not comparable to them. Available ↗ adds that series to every tab.";
    section.append(wrap, note);
    return section;
  }

  // Frame 13: news and adjustments come from the data's own player context, read only.
  function drawerContext(row) {
    const out = [];
    const stats = drawerSection("Stats & context");
    const p = document.createElement("p");
    p.textContent = `Position: ${row.pos} · Team: ${row.team || "FA"} · Roster tier: ${tierLabel(row.espnRole)}`
      + (row.rank ? ` · #${row.rank} by ${sourceMeta(view.rankKey).short}` : "");
    stats.appendChild(p);
    out.push(stats);
    let context = null;
    try { context = window.TradeValueProductData?.getPlayerContext?.(row.player_key) || null; } catch (error) { context = null; }
    const asOf = context?.as_of ? ` · as of ${String(context.as_of).slice(0, 10)}` : "";
    const news = drawerSection("Latest player news");
    const items = (context?.news || []).slice().sort((a, b) => String(b.published_at).localeCompare(String(a.published_at))).slice(0, 3);
    if (!items.length) {
      const none = document.createElement("p");
      none.className = "v2-meta";
      none.textContent = "No linked news available.";
      news.appendChild(none);
    } else {
      const ul = document.createElement("ul");
      ul.className = "v2-dnews";
      items.forEach(item => {
        const li = document.createElement("li");
        const link = document.createElement(item.url ? "a" : "span");
        if (item.url) { link.href = item.url; link.target = "_blank"; link.rel = "noopener noreferrer"; }
        link.textContent = item.title || "Untitled";
        const sub = document.createElement("span");
        sub.className = "v2-meta";
        sub.textContent = ` ${item.source || ""}${item.published_at ? ` · ${String(item.published_at).slice(0, 10)}` : ""}`;
        li.append(link, sub);
        ul.appendChild(li);
      });
      news.appendChild(ul);
    }
    out.push(news);
    const adj = drawerSection("Adjustments applied");
    const base = document.createElement("p");
    base.textContent = "Starter / bench utilization weighting · Position-share calibration.";
    adj.appendChild(base);
    const notes = context?.adjustments || [];
    const line = document.createElement("p");
    line.className = "v2-meta";
    line.textContent = notes.length
      ? `News adjustment: ${notes.map(a => [a.kind, a.injury, a.date].filter(Boolean).join(", ")).join("; ")}${asOf}.`
      : `News adjustment: none for this player${asOf}.`;
    adj.appendChild(line);
    out.push(adj);
    return out;
  }

  function openDrawer(row) {
    if ($("v2Drawer").hidden) lastFocus = document.activeElement;
    drawerRow = row;
    const drawer = $("v2Drawer");
    drawer.replaceChildren();
    const head = document.createElement("div");
    head.className = "v2-dhead";
    const titles = document.createElement("div");
    const title = document.createElement("h2");
    title.id = "v2DrawerTitle";
    title.textContent = row.name;
    const meta = document.createElement("p");
    meta.className = "v2-meta";
    meta.textContent = `${row.pos} · ${row.team || "FA"} · ${tierLabel(row.espnRole)}`;
    titles.append(title, meta);
    const close = document.createElement("button");
    close.type = "button";
    close.className = "v2-btn close";
    close.textContent = "✕";
    close.setAttribute("aria-label", "Close player details");
    close.addEventListener("click", closeDrawer);
    head.append(titles, close);
    drawer.appendChild(head);
    const zeroBadge = espnZeroBadge(row);
    if (zeroBadge) {
      const zeroNote = document.createElement("p");
      zeroNote.className = "v2-espn-zero-note";
      zeroNote.append(zeroBadge, document.createTextNode(` ${zeroBadge.title}`));
      zeroBadge.removeAttribute("title");
      drawer.appendChild(zeroNote);
    }
    drawer.append(drawerHero(row), drawerMatrix(row), ...drawerContext(row), tradeActions(row));
    $("v2Scrim").hidden = false;
    drawer.hidden = false;
    close.focus();
  }
  // Player detail → trade targets or Compare a trade ("Add to trade" chooses Give or Get).
  function tradeActions(row) {
    const key = String(row.player_key);
    const on = ["give", "receive"].find(side => TR[side].some(p => p.key === key));
    const box = document.createElement("div");
    box.className = "v2-drawer-trade";
    const targets = document.createElement("button");
    targets.type = "button";
    targets.className = "v2-btn";
    targets.textContent = "See trade targets";
    targets.addEventListener("click", () => {
      T.search = row.name;
      $("v2TSearch").value = row.name;
      closeDrawer();
      location.hash = "#trade-targets";
    });
    box.appendChild(targets);
    if (on) {
      const p = document.createElement("p");
      p.className = "v2-meta";
      p.dataset.tradeOn = on;
      p.textContent = `✓ On your trade: ${SIDE_NAME[on].toLowerCase()}.`;
      const open = document.createElement("a");
      open.className = "v2-link";
      open.href = "v2/#compare-trade";
      open.textContent = "Open Compare a trade ↗";
      open.addEventListener("click", closeDrawer);
      box.append(p, open);
      return box;
    }
    const add = document.createElement("button");
    add.type = "button";
    add.className = "v2-btn v2-btn-soft";
    add.textContent = "Add to trade";
    add.setAttribute("aria-expanded", "false");
    const menu = document.createElement("div");
    menu.className = "v2-dmenu";
    menu.hidden = true;
    [["give", "↑ You give"], ["receive", "↓ You receive"]].forEach(([side, label]) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "v2-btn";
      b.dataset.tradeAdd = side;
      b.textContent = label;
      b.addEventListener("click", () => {
        TR[side] = TR[side].concat({key, name: row.name});
        closeDrawer();
        if (currentView() === "compare") renderCompare();
        else location.hash = "#compare-trade";
      });
      menu.appendChild(b);
    });
    add.addEventListener("click", () => {
      menu.hidden = !menu.hidden;
      add.setAttribute("aria-expanded", String(!menu.hidden));
      if (!menu.hidden) menu.querySelector("button").focus();
    });
    box.append(add, menu);
    return box;
  }

  function closeDrawer() {
    $("v2Drawer").hidden = true;
    $("v2Scrim").hidden = true;
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  // ---------- popovers (sources 09, league 12, weights 11, freshness 10, range) ----------
  let popoverAnchor = null;
  function openPopover(anchor, build) {
    const pop = $("v2Popover");
    pop.replaceChildren();
    pop.classList.remove("v2-info-pop");
    build(pop);
    pop.hidden = false;
    popoverAnchor = anchor;
    const a = anchor.getBoundingClientRect();
    const p = pop.getBoundingClientRect();
    let left = Math.min(a.left, window.innerWidth - p.width - 16);
    let top = a.bottom + 8;
    if (top + p.height > window.innerHeight - 16) top = Math.max(16, a.top - p.height - 8);
    pop.style.left = `${Math.max(16, left)}px`;
    pop.style.top = `${top}px`;
    const first = pop.querySelector("input, select, button");
    if (first) first.focus();
  }
  function closePopover() {
    const pop = $("v2Popover");
    if (pop.hidden) return;
    pop.hidden = true;
    if (panelOpen) {
      panelOpen = false;
      $("v2Scrim").hidden = $("v2Drawer").hidden;
    }
    // An anchor that announces its state (the ⓘ buttons) reads collapsed again.
    if (popoverAnchor && popoverAnchor.getAttribute("aria-expanded") === "true") popoverAnchor.setAttribute("aria-expanded", "false");
    if (popoverAnchor && popoverAnchor.focus) popoverAnchor.focus();
    popoverAnchor = null;
  }
  function toggleEngineSource(key) {
    const input = document.querySelector(`#legacyEngine #sourceToggles input[data-source="${key}"]`);
    if (!input || input.disabled) return false;
    input.click();
    return true;
  }

  // Overlay panels (frames 09–12, 20, 21): a titled panel with ✕, a draft the
  // user edits, and Cancel / Apply. Centered over a scrim on desktop, full
  // screen below 768 px (frame 17). Nothing reaches the engine until Apply.
  let panelOpen = false;
  function openPanel(anchor, title, sub, build) {
    openPopover(anchor, pop => {
      pop.classList.add("is-panel");
      const head = document.createElement("div");
      head.className = "v2-panel-head";
      const titles = document.createElement("div");
      const h = document.createElement("h2");
      h.id = "v2PanelTitle";
      h.textContent = title;
      titles.appendChild(h);
      if (sub) {
        const p = document.createElement("p");
        p.className = "v2-meta";
        p.textContent = sub;
        titles.appendChild(p);
      }
      const close = document.createElement("button");
      close.type = "button";
      close.className = "v2-btn v2-panel-close";
      close.textContent = "✕";
      close.setAttribute("aria-label", `Close ${title}`);
      close.addEventListener("click", closePopover);
      head.append(titles, close);
      pop.appendChild(head);
      pop.setAttribute("aria-labelledby", "v2PanelTitle");
      pop.setAttribute("aria-modal", "true");
      build(pop);
    });
    const pop = $("v2Popover");
    pop.style.left = "";
    pop.style.top = "";
    $("v2Scrim").hidden = false;
    panelOpen = true;
    const first = pop.querySelector(".v2-panel-body input, .v2-panel-body select, .v2-panel-body button") || pop.querySelector("button");
    if (first) first.focus();
  }
  function panelActions(pop, buttons, left) {
    const row = document.createElement("div");
    row.className = "actions v2-panel-foot";
    if (left) row.appendChild(left);
    buttons.forEach(([label, primary, fn, attrs]) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = `v2-btn${primary ? " v2-btn-primary" : ""}`;
      b.textContent = label;
      Object.entries(attrs || {}).forEach(([k, v]) => b.setAttribute(k, v));
      b.addEventListener("click", fn);
      row.appendChild(b);
    });
    pop.appendChild(row);
    return row;
  }
  function panelBody(pop) {
    const body = document.createElement("div");
    body.className = "v2-panel-body";
    pop.appendChild(body);
    return body;
  }
  function segmented(label, options, value, onPick) {
    const box = document.createElement("div");
    box.className = "v2-pseg";
    box.setAttribute("role", "group");
    box.setAttribute("aria-label", label);
    const buttons = options.map(([v, text]) => {
      const b = document.createElement("button");
      b.type = "button";
      b.dataset.value = String(v);
      b.textContent = text;
      b.addEventListener("click", () => { onPick(v); sync(v); });
      box.appendChild(b);
      return b;
    });
    function sync(current) {
      buttons.forEach(b => {
        const on = b.dataset.value === String(current);
        b.classList.toggle("is-on", on);
        b.setAttribute("aria-pressed", String(on));
      });
    }
    sync(value);
    return box;
  }
  function eyebrow(parent, text) {
    const h = document.createElement("h3");
    h.className = "v2-eyebrow";
    h.textContent = text;
    parent.appendChild(h);
    return h;
  }

  // ---------- 09 / 20 Customize values (JEG-466, spec JEG-474) ----------
  // Grouped by type, not publisher; each group explains itself. A draft until Done.
  function openSources(anchor) {
    const draft = new Set(view.active);
    openPanel(anchor || $("v2EditSources"), "Customize values", "Choose which series appear on every tab.", pop => {
      const body = panelBody(pop);
      const summary = document.createElement("p");
      summary.className = "v2-psummary";
      summary.setAttribute("role", "status");
      body.appendChild(summary);
      const groupsBox = document.createElement("div");
      body.appendChild(groupsBox);
      const err = document.createElement("p");
      err.className = "v2-perror";
      err.hidden = true;
      err.textContent = "Choose at least one series.";
      function rowFor(item) {
        const meta = sourceMeta(item.key);
        const label = document.createElement("label");
        label.className = `v2-crow${item.available ? "" : " is-disabled"}`;
        const box = document.createElement("input");
        box.type = "checkbox";
        box.dataset.series = item.key;
        box.checked = draft.has(item.key);
        box.disabled = !item.available;
        box.addEventListener("change", () => {
          if (box.checked) draft.add(item.key); else draft.delete(item.key);
          err.hidden = true;
          render();
          const again = groupsBox.querySelector(`[data-series="${item.key}"]`);
          if (again) again.focus();
        });
        const name = document.createElement("span");
        name.className = "v2-crow-name";
        name.innerHTML = `<span class="v2-sym" style="color:${meta.color}" aria-hidden="true">${meta.symbol}</span> `;
        name.append(document.createTextNode(PLAIN_NAMES[meta.publisher] || meta.label));
        label.append(box, name);
        if (item.stale) label.appendChild(weekBadge(item.key));
        if (!item.available) {
          const why = document.createElement("span");
          why.className = "v2-meta";
          why.textContent = item.paused ? "Waiting on fresh inputs" : "Not available for this league";
          label.appendChild(why);
        }
        if (item.waiverNote && item.available) label.title = item.waiverNote;
        return label;
      }
      function render() {
        groupsBox.replaceChildren();
        SERIES_GROUPS.forEach(g => {
          const items = view.info.filter(item => seriesGroup(item.key) === g.id);
          if (!items.length) return;
          const section = document.createElement(g.id === "vorp" ? "details" : "section");
          section.className = "v2-cgroup";
          section.dataset.group = g.id;
          const head = document.createElement(g.id === "vorp" ? "summary" : "div");
          head.className = "v2-cgroup-head";
          const title = document.createElement("h3");
          title.textContent = g.id === "vorp" ? `Advanced · ${g.title}` : g.title;
          head.appendChild(title);
          const selectable = items.filter(item => item.available);
          const allOn = selectable.length > 0 && selectable.every(item => draft.has(item.key));
          const all = document.createElement("button");
          all.type = "button";
          all.className = "v2-link v2-call";
          all.textContent = allOn ? "Select none" : "Select all";
          all.disabled = !selectable.length;
          all.addEventListener("click", event => {
            event.preventDefault();
            selectable.forEach(item => (allOn ? draft.delete(item.key) : draft.add(item.key)));
            render();
          });
          head.appendChild(all);
          const note = document.createElement("p");
          note.className = "v2-meta";
          note.textContent = g.note;
          section.append(head, note, ...items.map(rowFor));
          if (g.id === "vorp" && items.some(item => draft.has(item.key))) section.open = true;
          groupsBox.appendChild(section);
        });
        summary.textContent = `${draft.size} series selected · applies to every tab`;
      }
      body.appendChild(err);
      const reset = document.createElement("button");
      reset.type = "button";
      reset.className = "v2-btn v2-preset";
      reset.textContent = "Reset to default";
      reset.addEventListener("click", () => {
        draft.clear();
        (startActive || []).forEach(key => draft.add(key));
        render();
      });
      panelActions(pop, [["Cancel", false, closePopover], ["Done", true, () => {
        if (!draft.size) { err.hidden = false; return; }
        const adds = [...draft].filter(key => !view.active.includes(key));
        const drops = view.active.filter(key => !draft.has(key));
        adds.forEach(toggleEngineSource);
        drops.forEach(toggleEngineSource);
        closePopover();
        refresh();
      }, {"data-apply": "sources"}]], reset);
      render();
    });
  }
  let startActive = null;   // the first-load selection: what "Reset to default" returns to

  // Frame 18: when a league change makes a selected series unavailable, say which one was dropped.
  let statusTimer = null;
  // JEG-444: when the new league's feasible bench range moves the bench share, say so too.
  function leagueChange(apply) {
    const before = C.getActiveSources();
    const benchBefore = C.getBenchShare();
    apply();
    refresh();
    const after = new Set(C.getActiveSources());
    const dropped = before.filter(key => !after.has(key));
    const benchAfter = C.getBenchShare();
    const notes = [];
    if (dropped.length) notes.push(`Removed ${dropped.map(key => sourceMeta(key).short).join(", ")}: not available for this league.`);
    if (Number.isFinite(benchBefore) && Number.isFinite(benchAfter) && Math.abs(benchAfter - benchBefore) > 1e-9) {
      notes.push(`Bench share moved from ${(benchBefore * 100).toFixed(1)}% to ${(benchAfter * 100).toFixed(1)}% to stay inside this league's feasible range.`);
    }
    if (!notes.length) return;
    setStatus(notes.join(" "));
    clearTimeout(statusTimer);
    statusTimer = setTimeout(() => setStatus(""), 6000);
  }

  // ---------- 12 Your league ----------
  let leagueDefaults = null;   // the engine's state at first load: what "Reset defaults" returns to
  const ROSTER_SLOTS = [["QB", "QB", 1, 5], ["RB", "RB", 1, 5], ["WR", "WR", 1, 5], ["TE", "TE", 1, 5], ["FLEX", "FLEX", 1, 5],
    ["SUPERFLEX", "SUPERFLEX", 0, 1], ["BENCH", "Bench slots", 0, 14]];
  function openLeague() {
    const s = view.state;
    const draft = {scoring: s.scoring, teams: s.teams, roster: {...C.getRosterShape()}};
    openPanel($("v2EditLeague"), "Your league", "One league setup for charts, tables and trades.", pop => {
      const body = panelBody(pop);
      const content = document.createElement("div");
      body.appendChild(content);
      function render() {
        content.replaceChildren();
        eyebrow(content, "Scoring");
        content.appendChild(segmented("Scoring", [["standard", "Standard"], ["half_ppr", "Half PPR"], ["ppr", "Full PPR"]],
          draft.scoring, v => { draft.scoring = v; }));
        eyebrow(content, "Teams");
        content.appendChild(segmented("Teams", [8, 10, 12, 14].map(v => [v, String(v)]), draft.teams, v => { draft.teams = v; }));
        eyebrow(content, "Starting roster");
        ROSTER_SLOTS.forEach(([key, label, min, max]) => {
          const line = document.createElement("div");
          line.className = "v2-pstep";
          const name = document.createElement("span");
          name.id = `v2Step${key}`;
          name.textContent = label;
          const stepper = document.createElement("div");
          stepper.className = "v2-stepper";
          const value = document.createElement("output");
          value.setAttribute("aria-labelledby", name.id);
          value.textContent = String(draft.roster[key]);
          const mk = (text, delta, aria) => {
            const b = document.createElement("button");
            b.type = "button";
            b.textContent = text;
            b.setAttribute("aria-label", `${aria} ${label}`);
            b.disabled = delta < 0 ? draft.roster[key] <= min : draft.roster[key] >= max;
            b.addEventListener("click", () => {
              draft.roster[key] = Math.max(min, Math.min(max, draft.roster[key] + delta));
              render();
              const again = content.querySelector(`[aria-label="${aria} ${label}"]`);
              if (again && !again.disabled) again.focus();
            });
            return b;
          };
          stepper.append(mk("−", -1, "Fewer"), value, mk("+", 1, "More"));
          line.append(name, stepper);
          content.appendChild(line);
        });
        const note = document.createElement("p");
        note.className = "v2-meta";
        note.textContent = "SUPERFLEX is a QB-eligible slot filled after the dedicated slots. Position weights and bench allocation live in Weights & bench.";
        content.appendChild(note);
      }
      render();
      panelActions(pop, [["Cancel", false, closePopover], ["Apply", true, () => {
        const cur = view.state;
        const shape = C.getRosterShape();
        leagueChange(() => {
          if (draft.scoring !== cur.scoring) C.setScoring(draft.scoring);
          if (draft.teams !== cur.teams) C.setTeams(draft.teams);
          ROSTER_SLOTS.forEach(([key]) => { if (draft.roster[key] !== shape[key]) C.setRosterSpot(key, draft.roster[key]); });
        });
        closePopover();
      }, {"data-apply": "league"}]], (() => {
        const reset = document.createElement("button");
        reset.type = "button";
        reset.className = "v2-btn v2-preset";
        reset.textContent = "Reset defaults";
        reset.addEventListener("click", () => {
          if (!leagueDefaults) return;
          draft.scoring = leagueDefaults.scoring;
          draft.teams = leagueDefaults.teams;
          draft.roster = {...leagueDefaults.roster};
          render();
        });
        return reset;
      })());
    });
  }

  // ---------- 11 Weights & bench ----------
  function openWeights() {
    const bounds = C.getBenchBounds();
    let draft = C.getBenchShare();
    openPanel($("v2Weights"), "Weights & bench", "Applies across tabs", pop => {
      const body = panelBody(pop);
      eyebrow(body, "Bench allocation");
      const top = document.createElement("div");
      top.className = "v2-pbench";
      const label = document.createElement("label");
      label.htmlFor = "v2BenchSlider";
      label.innerHTML = "<b>Bench share</b><span class=\"v2-meta\">Share of total value allocated to bench depth</span>";
      const readout = document.createElement("output");
      readout.className = "v2-pbig";
      readout.htmlFor = "v2BenchSlider";
      top.append(label, readout);
      body.appendChild(top);
      const slider = document.createElement("input");
      slider.type = "range";
      slider.id = "v2BenchSlider";
      if (bounds) {
        slider.min = String(bounds[0]); slider.max = String(bounds[1]); slider.step = "0.005"; slider.value = String(draft);
      } else {
        slider.disabled = true;
      }
      body.appendChild(slider);
      const range = document.createElement("p");
      range.className = "v2-meta";
      range.textContent = bounds
        ? `Feasible ${(bounds[0] * 100).toFixed(1)}%–${(bounds[1] * 100).toFixed(1)}% for this league · Recommended 15%`
        : "Bench allocation is unavailable for this league setup.";
      body.appendChild(range);
      const split = document.createElement("div");
      split.className = "v2-psplit";
      body.appendChild(split);
      const sync = () => {
        readout.textContent = `${(draft * 100).toFixed(1)}%`;
        split.innerHTML = "";
        const b = document.createElement("b");
        b.textContent = `Starters ${(100 - draft * 100).toFixed(1)}% / Bench ${(draft * 100).toFixed(1)}%`;
        const p = document.createElement("span");
        p.className = "v2-meta";
        p.textContent = "Feasible bounds recalculate with league structure.";
        split.append(b, p);
      };
      slider.addEventListener("input", () => { draft = Number(slider.value); sync(); });
      sync();
      // Frame 11 position shares (JEG-452 engine API). The reader edits any shares; on Apply the
      // engine sets exactly those and splits the rest in proportion (setPositionWeights), so v2
      // never rebalances them itself.
      eyebrow(body, "Position shares of total value");
      const shares = document.createElement("p");
      shares.className = "v2-meta";
      shares.textContent = "Shares total 100%. Shares you leave alone split the rest in proportion when you apply.";
      body.appendChild(shares);
      const weights = C.getPositionWeights();
      const shareBounds = C.getPositionWeightBounds ? C.getPositionWeightBounds() : null;
      const edited = {};
      let resetShares = false;
      const inputs = {};
      ["QB", "RB", "WR", "TE"].forEach(pos => {
        const line = document.createElement("div");
        line.className = "v2-pshare";
        const v = Number(weights[pos]);
        const label = document.createElement("label");
        label.htmlFor = `v2Share${pos}`;
        label.textContent = pos;
        const bar = document.createElement("span");
        bar.className = "v2-pshare-bar";
        bar.setAttribute("aria-hidden", "true");
        bar.innerHTML = `<span style="width:${Number.isFinite(v) ? Math.min(100, v * 100) : 0}%"></span>`;
        const field = document.createElement("span");
        field.className = "v2-pshare-field";
        const input = document.createElement("input");
        input.type = "number";
        input.id = `v2Share${pos}`;
        input.step = "0.1";
        const [lo, hi] = shareBounds && shareBounds[pos] ? shareBounds[pos] : [0, 1];
        input.min = (lo * 100).toFixed(1);
        input.max = (hi * 100).toFixed(1);
        input.value = Number.isFinite(v) ? (v * 100).toFixed(1) : "";
        input.disabled = !shareBounds;
        input.addEventListener("input", () => {
          const n = Number(input.value);
          if (input.value !== "" && Number.isFinite(n)) edited[pos] = n / 100;
          else delete edited[pos];
          resetShares = false;
        });
        inputs[pos] = input;
        const now = document.createElement("span");
        now.className = "v2-meta";
        now.dataset.weight = pos;
        now.textContent = Number.isFinite(v) ? `${(v * 100).toFixed(1)}%` : "—";
        field.append(input, document.createTextNode("% "));
        line.append(label, bar, field, now);
        body.appendChild(line);
      });
      const reset = document.createElement("button");
      reset.type = "button";
      reset.className = "v2-btn v2-preset";
      reset.textContent = "Reset defaults";
      reset.addEventListener("click", () => {
        draft = 0.15; slider.value = String(draft); sync();
        const defaults = C.getDefaultPositionWeights ? C.getDefaultPositionWeights() : null;
        Object.keys(edited).forEach(pos => delete edited[pos]);
        resetShares = true;
        if (defaults) Object.entries(inputs).forEach(([pos, input]) => { input.value = (Number(defaults[pos]) * 100).toFixed(1); });
      });
      panelActions(pop, [["Cancel", false, closePopover], ["Apply", true, () => {
        if (bounds) C.setBenchShareFraction(draft);
        let note = "";
        if (resetShares && C.resetPositionWeights) C.resetPositionWeights();
        else if (Object.keys(edited).length && C.setPositionWeights) {
          const result = C.setPositionWeights(edited);
          if (result && result.ok && result.clamped) note = "Some position shares were held to their allowed range.";
          else if (result && !result.ok) note = "Position shares were not changed.";
        }
        closePopover();
        refresh();
        if (note) {
          setStatus(note);
          clearTimeout(statusTimer);
          statusTimer = setTimeout(() => setStatus(""), 6000);
        }
      }, {"data-apply": "weights"}]], reset);
    });
  }

  // ---------- 10 Source freshness (JEG-463: root sources only) ----------
  // One row per publisher. Pipeline health (import, fixture rebuild) is folded into that
  // source's status from assets/reference-freshness.json; users never see pipeline rows.
  let pipeline = null;          // reference-freshness items by key, once loaded
  let pipelineLoading = null;
  function loadPipeline() {
    if (pipeline || pipelineLoading) return pipelineLoading;
    pipelineLoading = fetch("assets/reference-freshness.json")
      .then(r => (r.ok ? r.json() : null))
      .catch(() => null)
      .then(doc => {
        pipeline = Object.fromEntries(((doc && doc.items) || []).filter(item => item && item.key).map(item => [item.key, item]));
        if (C) renderHeader();
        return pipeline;
      });
    return pipelineLoading;
  }
  const dayOf = text => (/^\d{4}-\d{2}-\d{2}/.test(String(text || "")) ? String(text).slice(0, 10) : "");
  function rootFreshness() {
    const pubs = Object.keys(PUBLISHERS).filter(pub => view.info.some(item => sourceMeta(item.key).publisher === pub));
    return pubs.map(pub => {
      const items = view.info.filter(item => sourceMeta(item.key).publisher === pub);
      const base = items.find(item => item.key === pub) || items[0];
      const name = PUBLISHER_NAMES[pub] || pub;
      const p = pipeline || {};
      const own = p[`comparison.source.${pub}`];
      const imp = p[`source_import.${pub}`];
      const failingStep = [imp, own, p["source_import.checked_at"], p["comparison.built_at"]].find(item => item && item.freshness_ok === false);
      const paused = items.some(item => item.paused);
      if (failingStep || paused) {
        const since = dayOf(imp && imp.value) || dayOf(own && own.value);
        return {pub, name, week: base?.week, status: "stuck",
          text: "Not updating", reason: `We couldn't refresh ${name}${since ? ` since ${since}` : ""}.`};
      }
      const prior = (own && Number(own.weeks_behind) > 0) || items.some(item => item.available && item.stale);
      return {pub, name, week: base?.week, status: prior ? "prior" : "current",
        text: prior ? "Prior week" : "Current",
        reason: prior && view.refWeek && base?.week ? `${name} has not published Week ${view.refWeek} yet; showing Week ${base.week}.` : ""};
    });
  }
  function openFreshness() {
    openPanel($("v2Freshness"), "Source freshness", view.refWeek ? `Week ${view.refWeek} board · each source's own week` : "Each source's own week", pop => {
      const body = panelBody(pop);
      const table = document.createElement("table");
      table.className = "v2-ptable";
      table.innerHTML = "<thead><tr><th scope=\"col\">Source</th><th scope=\"col\">Published</th><th scope=\"col\">Status</th></tr></thead>";
      const tbody = document.createElement("tbody");
      rootFreshness().forEach(r => {
        const tr = document.createElement("tr");
        tr.dataset.source = r.pub;
        tr.dataset.status = r.status;
        const name = document.createElement("th");
        name.scope = "row";
        name.innerHTML = `<span style="color:${pubColor(r.pub)}" aria-hidden="true">${PUBLISHERS[r.pub]?.symbol || ""}</span> `;
        name.append(document.createTextNode(r.name));
        const week = document.createElement("td");
        week.textContent = r.week ? `Week ${r.week}` : "—";
        const status = document.createElement("td");
        status.className = r.status === "stuck" ? "is-bad" : r.status === "prior" ? "is-older" : "is-ok";
        status.textContent = `${r.status === "stuck" ? "⚠ " : r.status === "current" ? "✓ " : ""}${r.text}`;
        if (r.reason) {
          const why = document.createElement("span");
          why.className = "th-sub";
          why.textContent = r.reason;
          status.appendChild(why);
        }
        tr.append(name, week, status);
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      const wrap = document.createElement("div");
      wrap.className = "v2-ptable-wrap";
      wrap.appendChild(table);
      body.appendChild(wrap);
      const manage = document.createElement("button");
      manage.type = "button";
      manage.className = "v2-btn v2-btn-soft";
      manage.textContent = "Customize values";
      manage.addEventListener("click", () => openSources($("v2EditSources")));
      panelActions(pop, [["Close", false, closePopover]], manage);
    });
  }

  // ---------- 24 Value range ----------
  function openRange() {
    const key = view.rankKey;
    const item = view.infoByKey[key];
    const values = C.getRows().map(row => row.values[key]).filter(Number.isFinite);
    const lo = values.length ? Math.floor(Math.min(...values)) : 0;
    const hi = values.length ? Math.ceil(Math.max(...values)) : 100;
    openPanel($("v2YExact"), "Value range", `Basis ${sourceMeta(key).short}${item?.week ? ` · Week ${item.week}` : ""}`, pop => {
      const body = panelBody(pop);
      const lead = document.createElement("p");
      lead.textContent = "Keep players with values between";
      body.appendChild(lead);
      const row = document.createElement("div");
      row.className = "row2";
      const mk = (text, value) => {
        const label = document.createElement("label");
        label.textContent = text;
        const input = document.createElement("input");
        input.type = "number"; input.step = "0.1"; input.min = "0";
        input.value = value === null ? "" : String(value);
        label.appendChild(input);
        row.appendChild(label);
        return input;
      };
      const minI = mk("Minimum", state.range.min);
      const maxI = mk("Maximum", state.range.max);
      body.appendChild(row);
      // Two handles over the basis series' own spread; they mirror the number fields.
      const dual = document.createElement("div");
      dual.className = "v2-dual";
      const mkSlider = (aria, value) => {
        const s = document.createElement("input");
        s.type = "range"; s.min = String(lo); s.max = String(hi); s.step = "0.1";
        s.value = String(value);
        s.setAttribute("aria-label", aria);
        dual.appendChild(s);
        return s;
      };
      const minS = mkSlider("Minimum value", state.range.min ?? lo);
      const maxS = mkSlider("Maximum value", state.range.max ?? hi);
      minS.addEventListener("input", () => { if (Number(minS.value) > Number(maxS.value)) minS.value = maxS.value; minI.value = minS.value; });
      maxS.addEventListener("input", () => { if (Number(maxS.value) < Number(minS.value)) maxS.value = minS.value; maxI.value = maxS.value; });
      minI.addEventListener("input", () => { if (minI.value !== "") minS.value = minI.value; });
      maxI.addEventListener("input", () => { if (maxI.value !== "") maxS.value = maxI.value; });
      body.appendChild(dual);
      const err = document.createElement("p");
      err.className = "v2-meta";
      err.textContent = "Inclusive. Blank = open ended. Missing values are excluded with a visible count.";
      body.appendChild(err);
      panelActions(pop, [
        ["Clear range", false, () => { setRange({min: null, max: null}); closePopover(); }],
        ["Apply", true, () => {
          const min = minI.value === "" ? null : Number(minI.value);
          const max = maxI.value === "" ? null : Number(maxI.value);
          if (min !== null && max !== null && min > max) {
            err.textContent = "Minimum is above maximum. Swap them or clear one.";
            err.classList.add("v2-perror");
            return;
          }
          closePopover();
          setRange({min, max});
        }, {"data-apply": "range"}]
      ]);
    });
  }

  // ---------- JEG-475 "More": exact From / To ranks ----------
  function setExpanded(id, open) { $(id).setAttribute("aria-expanded", String(open)); }
  function openMore() {
    const button = $("v2More");
    if (!$("v2Popover").hidden && popoverAnchor === button) { closePopover(); return; }
    openPopover(button, pop => {
      pop.classList.remove("is-panel");
      pop.setAttribute("aria-label", "Exact ranks");
      pop.setAttribute("aria-modal", "false");
      pop.removeAttribute("aria-labelledby");
      const h = document.createElement("h2");
      h.textContent = "Exact ranks";
      pop.appendChild(h);
      const lead = document.createElement("p");
      lead.className = "v2-meta";
      lead.textContent = `Show players ranked between (1–${view.rows.length}). Arrow keys on the rank brush move one rank.`;
      pop.appendChild(lead);
      const row = document.createElement("div");
      row.className = "row2";
      const mk = (text, id, value) => {
        const label = document.createElement("label");
        label.textContent = text;
        const input = document.createElement("input");
        input.type = "number"; input.id = id; input.min = "1"; input.max = String(view.rows.length); input.step = "1";
        input.inputMode = "numeric";
        input.value = String(value);
        label.appendChild(input);
        row.appendChild(label);
        return input;
      };
      const from = mk("From", "v2FromRank", state.window[0]);
      const to = mk("To", "v2ToRank", state.window[1]);
      pop.appendChild(row);
      const onBounds = () => {
        const n = view.rows.length;
        let lo = Math.round(Number(from.value));
        let hi = Math.round(Number(to.value));
        if (!Number.isFinite(lo) || !Number.isFinite(hi) || from.value === "" || to.value === "") return;
        lo = Math.max(1, Math.min(n, lo));
        hi = Math.max(1, Math.min(n, hi));
        if (lo > hi) [lo, hi] = [hi, lo];
        setWindow([lo, hi]);
      };
      from.addEventListener("change", onBounds);
      to.addEventListener("change", onBounds);
      const done = document.createElement("div");
      done.className = "actions";
      const doneBtn = document.createElement("button");
      doneBtn.type = "button";
      doneBtn.className = "v2-btn";
      doneBtn.textContent = "Done";
      doneBtn.addEventListener("click", closePopover);
      done.appendChild(doneBtn);
      pop.appendChild(done);
    });
    setExpanded("v2More", true);
  }

  // ---------- JEG-473 "Columns": hide method groups (and Pos / Team / Tier) ----------
  function openColumns() {
    const button = $("v2Columns");
    if (!$("v2Popover").hidden && popoverAnchor === button) { closePopover(); return; }
    openPopover(button, pop => {
      pop.classList.remove("is-panel");
      pop.setAttribute("aria-label", "Table columns");
      pop.setAttribute("aria-modal", "false");
      pop.removeAttribute("aria-labelledby");
      const h = document.createElement("h2");
      h.textContent = "Table columns";
      pop.appendChild(h);
      const present = new Set(view.plotKeys.concat(view.vorpKeys).map(tableGroup));
      if (view.plotKeys.filter(key => sourceMeta(key).method === "dda").length >= 2) present.add("spread");
      const box = (label, checked, attrs, onChange) => {
        const wrap = document.createElement("label");
        wrap.className = "v2-check v2-pcheck";
        const input = document.createElement("input");
        input.type = "checkbox";
        input.checked = checked;
        Object.entries(attrs).forEach(([k, v]) => { input.dataset[k] = v; });
        input.addEventListener("change", () => { onChange(input.checked); renderTable(); });
        wrap.append(input, document.createTextNode(` ${label}`));
        pop.appendChild(wrap);
      };
      eyebrow(pop, "Value groups");
      TABLE_GROUPS.filter(([g]) => present.has(g)).forEach(([g, label]) => {
        box(g === "spread" ? "Spread of our values" : label, !state.hiddenGroups.has(g), {group: g}, on => {
          if (on) state.hiddenGroups.delete(g); else state.hiddenGroups.add(g);
        });
      });
      const note = document.createElement("p");
      note.className = "v2-meta";
      note.textContent = `The ranking series (${sourceMeta(view.rankKey).short}) always shows.`;
      pop.appendChild(note);
      eyebrow(pop, "Player details");
      [["pos", "Position"], ["team", "Team"], ["tier", "Tier"]].forEach(([id, label]) => {
        box(label, state.metaCols[id] !== false, {meta: id}, on => { state.metaCols = {...state.metaCols, [id]: on}; });
      });
      const done = document.createElement("div");
      done.className = "actions";
      const doneBtn = document.createElement("button");
      doneBtn.type = "button";
      doneBtn.className = "v2-btn";
      doneBtn.textContent = "Done";
      doneBtn.addEventListener("click", closePopover);
      done.appendChild(doneBtn);
      pop.appendChild(done);
    });
    setExpanded("v2Columns", true);
  }

  // ---------- trade targets (frames 03 / 04) ----------
  // Every number here is read from the engine's rows; the one piece of
  // arithmetic (chart value − our value) lives in targets.js.
  //
  // Review fixes (JEG-456/458/459/461/464): both lists show at once (side by
  // side from 1280 px, stacked below), each collapsed to its top 5 with its own
  // "Show all"; every available chart is compared, and a chart still on an
  // earlier week carries a "Wk N" badge; chart values are labeled as indexed.
  const TARGETS_TOP = 5;
  const TARGETS_PAGE = 25;
  const TARGET_SIDES = ["sell", "buy"];
  const TARGET_IDS = {
    sell: {section: "v2TSell", table: "v2TTable", cards: "v2TCards", meta: "v2TSellMeta", empty: "v2TSellEmpty", more: "v2TSellMore", less: "v2TSellLess"},
    buy: {section: "v2TBuy", table: "v2TBuyTable", cards: "v2TBuyCards", meta: "v2TBuyMeta", empty: "v2TBuyEmpty", more: "v2TBuyMore", less: "v2TBuyLess"}
  };
  // ours: which projection-derived series is "our value". Module state, so the
  // choice survives switching tabs like the engine-held selections do.
  // shown / expanded are per list: each list opens and collapses on its own.
  const T = {search: "", chart: "all", ours: "espn",
    shown: {sell: TARGETS_TOP, buy: TARGETS_TOP}, expanded: {sell: new Set(), buy: new Set()}};
  let targetsView = null;

  // Shared (any tab may use these). JEG-459: a published source that has not
  // posted the current week yet is shown on its latest week with a small
  // "Wk N" badge in the older-week colour; its reason is the badge's tooltip
  // and accessible name. A current-week source gets no badge (null).
  function priorWeekInfo(key, item, refWeek) {
    if (!item || !item.stale) return null;
    const name = PUBLISHER_NAMES[key] || key;
    const week = Number.isFinite(item.week) ? item.week : null;
    const short = week ? `Wk ${week}` : "Earlier week";
    const label = week && Number.isFinite(refWeek) && refWeek !== week
      ? `${name} has not published Week ${refWeek} yet; showing Week ${week}.`
      : `${name} has not published this week yet; showing ${week ? `Week ${week}` : "an earlier week"}.`;
    return {short, label, week};
  }
  function priorWeekBadge(key, item, refWeek) {
    const info = priorWeekInfo(key, item, refWeek);
    if (!info) return null;
    const badge = document.createElement("span");
    badge.className = "v2-prior-badge";
    badge.dataset.priorWeek = key;
    badge.title = info.label;
    badge.setAttribute("role", "img");
    badge.setAttribute("aria-label", info.label);
    badge.textContent = info.short;
    return badge;
  }

  // Shared ⓘ (JEG-458): why published chart values are "indexed". A 44 px
  // target that opens a small popover (Esc or a click outside closes it); it
  // never reaches a row or column-header handler behind it.
  const INDEXED_INFO = "Published charts use their own point scales. We rescale each chart so its total value "
    + "matches our ESPN-based scale for your league, which makes the numbers comparable. Rankings within a chart "
    + "don't change; only the scale does.";
  function indexedInfoButton(context) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "v2-info";
    button.dataset.info = "indexed";
    button.setAttribute("aria-label", `What indexed means${context ? ` (${context})` : ""}`);
    button.setAttribute("aria-haspopup", "dialog");
    button.setAttribute("aria-expanded", "false");
    const glyph = document.createElement("span");
    glyph.setAttribute("aria-hidden", "true");
    glyph.textContent = "ⓘ";
    button.appendChild(glyph);
    ["keydown", "keyup"].forEach(type => button.addEventListener(type, event => {
      if (event.key === "Enter" || event.key === " ") event.stopPropagation();
    }));
    button.addEventListener("click", event => {
      event.preventDefault();
      event.stopPropagation();
      if (popoverAnchor === button && !$("v2Popover").hidden) { closePopover(); return; }
      closePopover();
      openPopover(button, pop => {
        pop.classList.remove("is-panel");
        pop.classList.add("v2-info-pop");
        pop.setAttribute("aria-modal", "false");
        pop.setAttribute("aria-labelledby", "v2InfoTitle");
        const h = document.createElement("h2");
        h.id = "v2InfoTitle";
        h.textContent = "Indexed values";
        const text = document.createElement("p");
        text.className = "v2-info-text";
        text.textContent = INDEXED_INFO;
        const foot = document.createElement("div");
        foot.className = "v2-info-foot";
        const link = document.createElement("a");
        link.className = "v2-link";
        link.href = "v2/#how-values";
        link.textContent = "How values work ↗";
        link.addEventListener("click", () => closePopover());
        const close = document.createElement("button");
        close.type = "button";
        close.className = "v2-btn";
        close.textContent = "Close";
        close.addEventListener("click", closePopover);
        foot.append(link, close);
        pop.append(h, text, foot);
      });
      button.setAttribute("aria-expanded", "true");
      const link = $("v2Popover").querySelector("a");
      if (link) link.focus();
    });
    return button;
  }

  const fmtGap = gap => {
    if (!Number.isFinite(gap)) return "—";
    const text = Math.abs(gap).toFixed(1);
    if (text === "0.0") return "0.0";
    return `${gap > 0 ? "+" : "−"}${text}`;
  };

  const targetBadge = key => priorWeekBadge(key, targetsView.infoByKey[key], targetsView.refWeek);

  function collectTargets() {
    const TT = window.TradeValueTargets;
    const info = sourceInfoWithFreshness();
    const infoByKey = Object.fromEntries(info.map(item => [item.key, item]));
    const ourKey = TT.OUR_KEYS.includes(T.ours) ? T.ours : TT.OUR_KEY;
    const ours = infoByKey[ourKey];
    const choices = TT.ourChoices(info);
    const freshness = window.TradeValueProductData?.getSourceFreshness?.() || null;
    const refWeek = freshness?.current_content_week || C.getReferenceWeek();
    // The published series are on the trade-value point scale only in the
    // engine's Indexed view; any other view would pair unlike units.
    const engineView = window.TradeValueCurveDiagnostics?.viewMode;
    const {used, skipped, prior} = TT.chartsToCompare(info, {only: T.chart === "all" ? null : T.chart});
    const needle = T.search.trim().toLowerCase();
    const rows = C.getRows();
    rows.forEach((row, index) => { row.rank = index + 1; });
    const searched = rows.filter(row => !needle || String(row.name || "").toLowerCase().includes(needle));
    // Fails closed: an unavailable choice is never swapped for another series.
    const blocked = !ours || !ours.available ? `Our value (${TT.OUR_NAMES[ourKey]}) is not available for this league right now.`
      : engineView && engineView !== "indexed" ? "Published charts are not on the trade-value point scale in this view, so no gaps are shown."
      : null;
    const result = blocked ? {ours: ourKey, sell: [], buy: [], compared: 0, omittedNoOurs: 0, atWaiverCells: 0}
      : TT.buildTargets(searched, used, {ours: ourKey});
    targetsView = {...result, ours: ourKey, choices, used, skipped, prior: prior || [], info, infoByKey, refWeek, blocked,
      position: C.getState().position};
  }

  function renderTargetControls() {
    const TT = window.TradeValueTargets;
    const select = $("v2TChart");
    select.replaceChildren();
    const all = document.createElement("option");
    all.value = "all";
    all.textContent = "All published charts";
    select.appendChild(all);
    TT.CHART_KEYS.forEach(key => {
      const item = targetsView.infoByKey[key];
      const option = document.createElement("option");
      option.value = key;
      option.disabled = !item || !item.available;
      const prior = option.disabled ? null : priorWeekInfo(key, item, targetsView.refWeek);
      option.textContent = `${PUBLISHERS[key].symbol} ${PUBLISHER_NAMES[key]}${option.disabled ? " — not available" : prior ? ` · ${prior.short} (prior week)` : ""}`;
      if (prior) {
        option.dataset.priorWeek = key;
        option.title = prior.label;
      }
      select.appendChild(option);
    });
    select.value = T.chart;
    // The picked chart's own badge sits beside the caption (an <option> cannot hold one).
    const slot = $("v2TChartBadge");
    slot.replaceChildren();
    if (T.chart !== "all") {
      const badge = targetBadge(T.chart);
      if (badge) slot.appendChild(badge);
    }
    const oursSelect = $("v2TOurs");
    oursSelect.replaceChildren();
    targetsView.choices.forEach(choice => {
      const option = document.createElement("option");
      option.value = choice.key;
      option.disabled = !choice.available;
      option.textContent = `${PUBLISHERS[choice.key].symbol} ${TT.OUR_NAMES[choice.key]}${choice.available ? "" : ` — ${choice.reason}`}`;
      oursSelect.appendChild(option);
    });
    oursSelect.value = targetsView.ours;
    $("v2TPosition").value = targetsView.position;
  }

  function gapNode(cell, tag) {
    const node = document.createElement(tag || "span");
    node.className = `delta gap ${cell.gap > 0 ? "up" : cell.gap < 0 ? "down" : ""}`;
    node.textContent = fmtGap(cell.gap);
    return node;
  }

  function missingNode(reason, short) {
    const span = document.createElement("span");
    span.className = "missing";
    span.title = reason;
    span.textContent = "—";
    const why = document.createElement("span");
    why.className = "why";
    why.textContent = short || reason;
    span.appendChild(why);
    return span;
  }

  // A chart value at or below that chart's waiver line: shown, but no gap.
  function waiverNode(reason) {
    const span = document.createElement("span");
    span.className = "why at-waiver";
    span.title = reason;
    span.textContent = "waiver line";
    return span;
  }

  const targetBest = (side, p) => (side === "sell" ? p.bestSell : p.bestBuy);

  // One chart's value for a player as a labeled run: "◆ USAT [Wk 4] 17.4 +9.8".
  // Used by the phone cards and by an expanded row in the two-column layout.
  function chartValueSpan(p, key) {
    const cell = p.cells[key];
    const span = document.createElement("span");
    span.dataset.chart = key;
    const label = document.createElement("span");
    label.className = "lbl";
    label.title = PUBLISHER_NAMES[key];
    const sym = document.createElement("span");
    sym.setAttribute("aria-hidden", "true");
    sym.style.color = pubColor(key);
    sym.textContent = `${PUBLISHERS[key].symbol} `;
    label.append(sym, document.createTextNode(PUBLISHERS[key].label));
    span.appendChild(label);
    const badge = targetBadge(key);
    if (badge) span.appendChild(badge);
    if (cell.value === null) {
      span.appendChild(missingNode(cell.reason, "not on chart"));
      return span;
    }
    const val = document.createElement("span");
    val.className = "val";
    val.textContent = fmt(cell.value);
    span.appendChild(val);
    span.appendChild(cell.atWaiver ? waiverNode(cell.reason) : gapNode(cell));
    return span;
  }

  // "Largest gap" attribution: the chart's name, plus its badge when it is on an earlier week.
  function bestChartNode(chart, verb, cls) {
    const who = document.createElement("span");
    who.className = cls || "th-sub t-who";
    who.append(document.createTextNode(verb ? `${PUBLISHER_NAMES[chart]} ${verb}` : PUBLISHER_NAMES[chart]));
    const badge = targetBadge(chart);
    if (badge) who.append(document.createTextNode(" "), badge);
    return who;
  }

  function renderTargetTable(side, list) {
    const ids = TARGET_IDS[side];
    const table = $(ids.table);
    table.replaceChildren();
    const thead = document.createElement("thead");
    const hr = document.createElement("tr");
    const head = (text, cls, sub, key, info) => {
      const th = document.createElement("th");
      th.scope = "col";
      if (cls) th.className = cls;
      const line = document.createElement("span");
      line.className = "th-line";
      if (key) {
        const sym = document.createElement("span");
        sym.className = "v2-sym";
        sym.style.color = pubColor(key);
        sym.setAttribute("aria-hidden", "true");
        sym.textContent = `${PUBLISHERS[key].symbol} `;
        line.appendChild(sym);
      }
      line.append(document.createTextNode(text));
      if (info) line.appendChild(indexedInfoButton(text));
      th.appendChild(line);
      if (sub) {
        const s = document.createElement("span");
        s.className = "th-sub";
        if (typeof sub === "string") s.textContent = sub;
        else s.append(...sub);
        th.appendChild(s);
      }
      if (key) th.dataset.chart = key;
      hr.appendChild(th);
      return th;
    };
    head("Player", "player");
    head("Our value", "num is-rank", window.TradeValueTargets.OUR_SHORT[targetsView.ours]);
    targetsView.used.forEach(key => {
      // JEG-458: "Wk 5 · indexed"; a chart on an earlier week shows its badge in place of the week.
      const item = targetsView.infoByKey[key];
      const week = targetBadge(key) || document.createTextNode(item && item.week ? `Wk ${item.week}` : "");
      head(PUBLISHER_NAMES[key] || key, "num t-chart", [week, document.createTextNode(`${week.textContent ? " · " : ""}indexed`)], key, true);
    });
    head("Largest gap", "num t-best", side === "sell" ? "chart pays more" : "chart pays less", null, true);
    const expandHead = head("", "t-expand");
    const sr = document.createElement("span");
    sr.className = "v2-sr";
    sr.textContent = "Each chart";
    expandHead.appendChild(sr);
    thead.appendChild(hr);
    const columns = hr.children.length;
    const tbody = document.createElement("tbody");
    list.slice(0, T.shown[side]).forEach(p => {
      const key = String(p.row.player_key);
      const tr = document.createElement("tr");
      tr.tabIndex = 0;
      tr.dataset.playerKey = key;
      tr.addEventListener("click", () => openDrawer(p.row));
      tr.addEventListener("keydown", event => { if (event.key === "Enter" && event.target === tr) openDrawer(p.row); });
      const td = (cls, text) => {
        const cell = document.createElement("td");
        if (cls) cell.className = cls;
        if (text !== undefined) cell.textContent = text;
        tr.appendChild(cell);
        return cell;
      };
      const name = td("player", p.row.name);
      appendEspnZero(name, p.row);
      const sub = document.createElement("span");
      sub.className = "player-sub";
      sub.textContent = `${p.row.pos} · ${p.row.team || "FA"} · ${tierLabel(p.row.espnRole)}`;
      name.appendChild(sub);
      const ours = td("num is-rank", fmt(p.ours));
      ours.dataset.ours = "";
      targetsView.used.forEach(chart => {
        const cell = p.cells[chart];
        const c = td("num t-chart");
        c.dataset.chart = chart;
        if (cell.value === null) {
          c.appendChild(missingNode(cell.reason, "not on chart"));
        } else if (cell.atWaiver) {
          c.append(document.createTextNode(fmt(cell.value)));
          c.appendChild(waiverNode(cell.reason));
        } else {
          c.append(document.createTextNode(fmt(cell.value)));
          c.appendChild(gapNode(cell));
        }
      });
      const b = targetBest(side, p);
      const bc = td(`num best ${b.gap > 0 ? "up" : "down"}`);
      bc.dataset.best = b.chart;
      bc.append(document.createTextNode(fmtGap(b.gap)));
      bc.appendChild(bestChartNode(b.chart));
      // Two-column layout (≥1280 px) hides the per-chart cells; this opens them under the row.
      const open = T.expanded[side].has(key);
      const ec = td("t-expand");
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "v2-texpand";
      toggle.dataset.expand = key;
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-label", `Each chart's value for ${p.row.name}`);
      const glyph = document.createElement("span");
      glyph.setAttribute("aria-hidden", "true");
      glyph.textContent = open ? "▴" : "▾";
      toggle.appendChild(glyph);
      toggle.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") event.stopPropagation(); });
      toggle.addEventListener("click", event => {
        event.stopPropagation();
        if (T.expanded[side].has(key)) T.expanded[side].delete(key);
        else T.expanded[side].add(key);
        renderTargetTable(side, list);
        const again = $(ids.table).querySelector(`[data-expand="${CSS.escape(key)}"]`);
        if (again) again.focus();
      });
      ec.appendChild(toggle);
      tbody.appendChild(tr);
      if (open) {
        const detail = document.createElement("tr");
        detail.className = "t-detail";
        detail.dataset.detailFor = key;
        const cell = document.createElement("td");
        cell.colSpan = columns;
        const line = document.createElement("div");
        line.className = "vals";
        targetsView.used.forEach(chart => line.appendChild(chartValueSpan(p, chart)));
        cell.appendChild(line);
        detail.appendChild(cell);
        tbody.appendChild(detail);
      }
    });
    table.append(thead, tbody);
  }

  function renderTargetCards(side, list) {
    const ol = $(TARGET_IDS[side].cards);
    ol.replaceChildren();
    list.slice(0, T.shown[side]).forEach(p => {
      const li = document.createElement("li");
      li.tabIndex = 0;
      li.dataset.playerKey = String(p.row.player_key);
      li.addEventListener("click", () => openDrawer(p.row));
      li.addEventListener("keydown", event => { if (event.key === "Enter") openDrawer(p.row); });
      const top = document.createElement("div");
      top.className = "top";
      const who = document.createElement("div");
      const name = document.createElement("b");
      name.textContent = p.row.name;
      appendEspnZero(name, p.row);
      const sub = document.createElement("span");
      sub.className = "v2-meta";
      sub.textContent = `${p.row.pos} · ${p.row.team || "FA"} · ${tierLabel(p.row.espnRole)}`;
      who.append(name, sub);
      const b = targetBest(side, p);
      const big = document.createElement("div");
      big.className = `big ${b.gap > 0 ? "up" : "down"}`;
      big.dataset.best = b.chart;
      big.append(document.createTextNode(fmtGap(b.gap)));
      big.appendChild(bestChartNode(b.chart, `pays ${b.gap > 0 ? "more" : "less"}`, "v2-meta t-who"));
      top.append(who, big);
      const line = document.createElement("div");
      line.className = "vals";
      const ours = document.createElement("span");
      ours.className = "ours";
      ours.textContent = `Ours ${fmt(p.ours)}`;
      line.appendChild(ours);
      targetsView.used.forEach(key => line.appendChild(chartValueSpan(p, key)));
      li.append(top, line);
      ol.appendChild(li);
    });
  }

  // JEG-461: each list opens on its top 5; "Show all N" then pages of 25; "Show top 5" collapses.
  function renderTargetFoot(side, list) {
    const ids = TARGET_IDS[side];
    const more = $(ids.more);
    const less = $(ids.less);
    const shown = Math.min(T.shown[side], list.length);
    const label = text => {
      const arrow = document.createElement("span");
      arrow.setAttribute("aria-hidden", "true");
      arrow.textContent = " ▾";
      more.replaceChildren(document.createTextNode(text), arrow);
    };
    more.hidden = list.length <= shown;
    less.hidden = T.shown[side] <= TARGETS_TOP || list.length <= TARGETS_TOP;
    if (T.shown[side] <= TARGETS_TOP) label(`Show all ${list.length} ${side} targets`);
    else label(`Show more (${shown} of ${list.length})`);
    more.setAttribute("aria-controls", `${ids.table} ${ids.cards}`);
  }

  function renderTargets() {
    collect();
    collectTargets();
    renderHeader();
    renderTargetControls();
    const blocked = targetsView.blocked;
    const noCharts = !targetsView.used.length;
    TARGET_SIDES.forEach(side => {
      const ids = TARGET_IDS[side];
      const list = targetsView[side];
      renderTargetTable(side, list);
      renderTargetCards(side, list);
      renderTargetFoot(side, list);
      const empty = $(ids.empty);
      empty.hidden = !(blocked || noCharts || !list.length);
      empty.textContent = blocked || (noCharts
        ? "No published chart is available to compare for this selection."
        : `No player has a ${side === "sell" ? "chart paying more" : "chart paying less"} than our value for this selection.`);
      $(ids.table).hidden = !list.length;
      $(ids.meta).textContent = blocked ? "—" : `${list.length} of ${targetsView.compared} players · largest gap first. `
        + (side === "sell" ? "Offer them to managers who trade off that chart." : "Ask for them from managers who trade off that chart.");
    });
    const notes = [];
    if (targetsView.skipped.length) {
      notes.push(`Not compared: ${targetsView.skipped.map(s => `${PUBLISHER_NAMES[s.key]}, ${s.reason}`).join("; ")}.`);
    }
    if (targetsView.omittedNoOurs) {
      notes.push(`${targetsView.omittedNoOurs} player${targetsView.omittedNoOurs === 1 ? "" : "s"} left out: we have no ${window.TradeValueTargets.OUR_SHORT[targetsView.ours]} value for them.`);
    }
    if (targetsView.atWaiverCells && !blocked) {
      notes.push("A chart value of 0.0 is at that chart's waiver line for your league: never a buy, no gap.");
    }
    const note = $("v2TNote");
    note.hidden = !notes.length;
    note.textContent = notes.join(" ");
    $("v2TOursNote").textContent = window.TradeValueTargets.OUR_NAMES[targetsView.ours];
    // Footnote: each compared chart that is still on an earlier week, with its badge.
    const priorNote = $("v2TPriorNote");
    priorNote.replaceChildren();
    targetsView.prior.filter(key => targetsView.used.includes(key)).forEach(key => {
      const badge = targetBadge(key);
      if (!badge) return;
      priorNote.append(badge, document.createTextNode(` ${priorWeekInfo(key, targetsView.infoByKey[key], targetsView.refWeek).label} `));
    });
  }

  function bindTargets() {
    let timer = null;
    const resetLists = () => {
      T.shown = {sell: TARGETS_TOP, buy: TARGETS_TOP};
      T.expanded = {sell: new Set(), buy: new Set()};
    };
    $("v2TSearch").addEventListener("input", event => {
      clearTimeout(timer);
      timer = setTimeout(() => { T.search = event.target.value; resetLists(); renderTargets(); }, 120);
    });
    $("v2TPosition").addEventListener("change", event => { C.setPosition(event.target.value); resetLists(); renderTargets(); });
    $("v2TChart").addEventListener("change", event => { T.chart = event.target.value; resetLists(); renderTargets(); });
    $("v2TOurs").addEventListener("change", event => { T.ours = event.target.value; resetLists(); renderTargets(); });
    $("v2TChartInfoSlot").replaceWith(indexedInfoButton("Compare against"));
    TARGET_SIDES.forEach(side => {
      const ids = TARGET_IDS[side];
      // Keep focus on a control that is still on screen after the list redraws.
      const refocus = () => ($(ids.more).hidden ? $(ids.less) : $(ids.more)).focus();
      $(ids.more).addEventListener("click", () => {
        T.shown[side] = T.shown[side] <= TARGETS_TOP ? TARGETS_PAGE : T.shown[side] + TARGETS_PAGE;
        renderTargets();
        refocus();
      });
      $(ids.less).addEventListener("click", () => {
        T.shown[side] = TARGETS_TOP;
        T.expanded[side] = new Set();
        renderTargets();
        const section = $(ids.section);
        if (section.getBoundingClientRect().top < 0) section.scrollIntoView({block: "start"});
        refocus();
      });
    });
  }

  // ---------- Compare a trade (frames 07 / 08, 24) ----------
  // Each row is one exact series: sum(receive) − sum(give) in that series'
  // values (app/v2/trade.js). No blended score (frame 22); the verdict reads one
  // series (JEG-469). The sides are v2 module state, so they survive switching tabs.
  const TR = {give: [], receive: [], shown: null, open: new Set()};   // give/receive: [{key, name}]
  let compareView = null;
  // JEG-469: the series the verdict reads. "Player values shown" for now; swap this one
  // line to the DDF Value series key once the engine exposes it.
  const verdictKey = () => TR.shown;
  let exampleCache = null;   // {signature, pick}: the empty-state sample trade
  const SIDE_IDS = {give: {search: "v2GiveSearch", results: "v2GiveResults", list: "v2GivePlayers", total: "v2GiveTotal"},
    receive: {search: "v2GetSearch", results: "v2GetResults", list: "v2GetPlayers", total: "v2GetTotal"}};
  const SIDE_NAME = {give: "You give", receive: "You receive"};

  function seriesName(key) {
    const meta = sourceMeta(key);
    return plainSeries(meta.publisher, meta.method);
  }

  function collectCompare() {
    const rowsByKey = new Map(C.getAllRows().map(row => [String(row.player_key), row]));
    // A player the engine no longer has a row for stays listed, missing in every series.
    const resolve = list => list.map(p => rowsByKey.get(p.key) || {player_key: p.key, name: p.name, values: {}, unpriced: true});
    const usable = keys => keys.filter(key => view.infoByKey[key]?.available);
    const pointKeys = usable(view.plotKeys);
    const vorpKeys = usable(view.vorpKeys);
    const unavailable = view.active.filter(key => !view.infoByKey[key]?.available);
    // "Player values shown": one exact series, the ranking series unless picked.
    const shownChoices = pointKeys.concat(vorpKeys);
    if (!shownChoices.includes(TR.shown)) TR.shown = shownChoices.includes(view.rankKey) ? view.rankKey : shownChoices[0] || null;
    const TC = window.TradeValueTrade;
    // JEG-469 empty state: before any player is added, a sample trade marked "Example".
    const example = !TR.give.length && !TR.receive.length && verdictKey() ? exampleTrade(pointKeys) : null;
    const giveRows = example ? example.give : resolve(TR.give);
    const receiveRows = example ? example.receive : resolve(TR.receive);
    const ready = giveRows.length > 0 && receiveRows.length > 0;
    const points = ready ? TC.compareTrade(giveRows, receiveRows, pointKeys).rows : [];
    const vorp = ready ? TC.compareTrade(giveRows, receiveRows, vorpKeys).rows : [];
    const metaFor = key => ({...sourceMeta(key), week: view.infoByKey[key]?.week ?? null});
    // JEG-468: one waterfall per row; trade-value rows share one scale, each VORP vs waivers
    // series keeps its own (those scales are not comparable).
    const falls = keys => (ready ? keys.map(key => TC.waterfall(giveRows, receiveRows, key)) : []);
    const pointFalls = falls(pointKeys);
    compareView = {rowsByKey, giveRows, receiveRows, ready, example: Boolean(example), pointKeys, vorpKeys, unavailable, shownChoices,
      points, story: ready ? TC.tradeStory(points, metaFor) : {kind: null},
      verdict: ready ? TC.tradeVerdict(points.concat(vorp), verdictKey()) : {kind: null, key: verdictKey()},
      totals: TR.shown ? {give: TC.sideTotal(giveRows, TR.shown), receive: TC.sideTotal(receiveRows, TR.shown)} : null,
      vorp, falls: {points: pointFalls, vorp: falls(vorpKeys)}, scale: TC.waterfallScale(pointFalls)};
  }

  // The example trade, recomputed only when the series or the values change.
  function exampleTrade(pointKeys) {
    const key = verdictKey();
    const rows = C.getAllRows();
    const keys = pointKeys.concat(key);
    const signature = `${keys.join(",")}|${rows.length}|${rows.reduce((acc, r) => acc + keys.reduce((a, k) => a + (Number.isFinite(r.values[k]) ? r.values[k] : 0.123), 0), 0)}`;
    if (!exampleCache || exampleCache.signature !== signature) {
      exampleCache = {signature, pick: window.TradeValueTrade.pickExample(rows, pointKeys, key)};
    }
    return exampleCache.pick;
  }

  function sourceCell(td, key) {
    const meta = sourceMeta(key);
    const item = view.infoByKey[key];
    const sym = document.createElement("span");
    sym.className = "v2-sym";
    sym.style.color = meta.color;
    sym.setAttribute("aria-hidden", "true");
    sym.textContent = `${meta.symbol} `;
    td.appendChild(sym);
    td.append(document.createTextNode(seriesName(key)));
    const sub = document.createElement("span");
    sub.className = "th-sub";
    sub.textContent = item?.week ? `Week ${item.week}${item.stale ? " · older week" : ""}` : "week unknown";
    td.appendChild(document.createElement("br"));
    td.appendChild(sub);
  }

  function netLabel(net) {
    const text = fmtGap(net);
    if (text === "0.0") return {text, cls: "", label: "= even by this source"};
    return net > 0 ? {text, cls: "up", label: "▲ you receive more by this source"}
      : {text, cls: "down", label: "▼ you give more by this source"};
  }

  // Frame 24 "Expanded result": every player's value in this series, each side's total, then the net.
  function breakdownRow(result, columns) {
    const tr = document.createElement("tr");
    tr.className = "v2-cbreak";
    tr.dataset.breakdown = result.key;
    const td = document.createElement("td");
    td.colSpan = columns;
    const grid = document.createElement("div");
    grid.className = "v2-cbreak-grid";
    [["give", compareView.giveRows, result.give], ["receive", compareView.receiveRows, result.receive]].forEach(([side, rows, total]) => {
      const col = document.createElement("div");
      const h = document.createElement("p");
      h.className = "v2-meta";
      h.textContent = SIDE_NAME[side];
      col.appendChild(h);
      rows.forEach(row => {
        const v = row.values ? row.values[result.key] : null;
        const line = document.createElement("p");
        line.dataset.playerKey = String(row.player_key);
        line.append(document.createTextNode(`${row.name} `));
        if (Number.isFinite(v)) {
          const b = document.createElement("b");
          b.textContent = fmt(v);
          line.appendChild(b);
        } else {
          line.appendChild(missingNode(`No ${seriesName(result.key)} value for ${row.name}`, "no value"));
        }
        col.appendChild(line);
      });
      const t = document.createElement("p");
      t.className = "v2-cbreak-total";
      t.textContent = total === null ? "Total: incomplete" : `Total ${fmt(total)}`;
      col.appendChild(t);
      grid.appendChild(col);
    });
    const sum = document.createElement("p");
    sum.className = `v2-cbreak-net ${result.net === null ? "" : netLabel(result.net).cls}`;
    sum.textContent = result.net === null
      ? "Receive − give: incomplete. A missing value is never counted as zero."
      : `Receive − give = ${fmtGap(result.net)} ${sourceMeta(result.key).method === "vorp" ? "VORP vs waivers points" : "trade-value points"}`;
    td.append(grid, sum);
    tr.appendChild(td);
    return tr;
  }

  // JEG-468: short names for the step labels; a shared last name gets an initial.
  function shortNames(rows) {
    const suffix = /^(jr\.?|sr\.?|ii|iii|iv|v)$/i;
    const last = row => {
      const parts = String(row.name || "").split(/\s+/).filter(Boolean);
      while (parts.length > 1 && suffix.test(parts[parts.length - 1])) parts.pop();
      return {first: parts[0] || "", last: parts[parts.length - 1] || String(row.name || "Player")};
    };
    const names = rows.map(last);
    const count = new Map();
    names.forEach(n => count.set(n.last, (count.get(n.last) || 0) + 1));
    return new Map(rows.map((row, i) => [String(row.player_key),
      count.get(names[i].last) > 1 && names[i].first !== names[i].last ? `${names[i].first.charAt(0)}. ${names[i].last}` : names[i].last]));
  }

  // JEG-468 waterfall: 0 → a step down per player given → a step up per player received →
  // a landing bar from 0 to the net. Three lanes (give, receive, result) on the table's
  // scale. Each step is focusable, with a text alternative and the shared tooltip.
  function renderWaterfall(cell, fall, scale) {
    const name = seriesName(fall.key);
    const span = scale.hi - scale.lo;
    const x = v => Math.max(0, Math.min(100, ((v - scale.lo) / span) * 100));
    const short = shortNames(compareView.giveRows.concat(compareView.receiveRows));
    const box = document.createElement("div");
    box.className = "v2-wf";
    box.setAttribute("role", "group");
    box.setAttribute("aria-label", `${name}, step by step from 0`);
    box.dataset.lo = String(scale.lo);
    box.dataset.hi = String(scale.hi);
    const zero = document.createElement("span");
    zero.className = "v2-wf-zero";
    zero.setAttribute("aria-hidden", "true");
    zero.style.left = `${x(0)}%`;
    box.appendChild(zero);
    const lanes = {};
    ["give", "receive", "net"].forEach(lane => {
      const div = document.createElement("div");
      div.className = "v2-wf-lane";
      div.dataset.lane = lane;
      lanes[lane] = div;
      box.appendChild(div);
    });
    const runningText = step => (step.partial ? `running ${fmtGap(step.running)} so far, row incomplete` : `running ${fmtGap(step.running)}`);
    fall.steps.forEach(step => {
      const who = short.get(String(step.row.player_key)) || step.row.name;
      const verb = step.side === "give" ? "Give" : "Receive";
      const el = document.createElement("span");
      el.className = `v2-wf-step ${step.side}${step.missing ? " is-missing" : ""}`;
      el.tabIndex = 0;
      el.setAttribute("role", "img");
      el.dataset.playerKey = String(step.row.player_key);
      el.dataset.side = step.side;
      if (step.missing) {
        const reason = `No ${name} value for ${step.row.name}`;
        const w = 14;
        const at = x(step.start);
        const left = step.side === "give" ? Math.max(0, at - w) : Math.min(at, 100 - w);
        el.style.left = `${left}%`;
        el.style.width = `${w}%`;
        el.dataset.missing = "true";
        el.setAttribute("aria-label", `${verb} ${who}: no value. ${reason}; this row is incomplete and has no result`);
        const label = document.createElement("span");
        label.className = "v2-wf-label";
        label.setAttribute("aria-hidden", "true");
        label.textContent = `— ${who}`;
        el.appendChild(label);
        el._tip = {title: step.row.name, lines: [name, `${verb}: — no value`, reason, "Row incomplete: a missing value is never counted as zero"]};
      } else {
        const from = Math.min(x(step.start), x(step.end));
        const width = Math.abs(x(step.end) - x(step.start));
        el.style.left = `${from}%`;
        el.style.width = `${width}%`;
        el.dataset.value = fmtGap(step.delta);
        el.dataset.running = fmtGap(step.running);
        el.setAttribute("aria-label", `${verb} ${who} ${fmtGap(step.delta)}, ${runningText(step)}`);
        const label = document.createElement("span");
        label.className = "v2-wf-label";
        label.setAttribute("aria-hidden", "true");
        label.textContent = width >= 16 ? `${who} ${fmtGap(step.delta)}` : width >= 7 ? fmtGap(step.delta) : "";
        el.appendChild(label);
        el._tip = {title: step.row.name, lines: [name, `${verb} ${fmtGap(step.delta)}`, runningText(step).replace(/^running/, "Running total")]};
      }
      lanes[step.side].appendChild(el);
    });
    // A dashed link where the give steps end and the receive steps start.
    const turn = fall.steps.filter(st => st.side === "give").pop();
    if (turn) {
      const link = document.createElement("span");
      link.className = "v2-wf-link";
      link.setAttribute("aria-hidden", "true");
      link.style.left = `${x(turn.end)}%`;
      box.appendChild(link);
    }
    if (fall.complete) {
      const n = netLabel(fall.net);
      const land = document.createElement("span");
      land.className = `v2-wf-land ${n.cls}`;
      land.tabIndex = 0;
      land.setAttribute("role", "img");
      land.dataset.net = n.text;
      land.setAttribute("aria-label", `Result ${n.text}: ${n.label.replace(/^[▲▼=] /, "")}`);
      const a = x(0);
      const b = x(fall.net);
      land.style.left = `${Math.min(a, b)}%`;
      land.style.width = `${Math.abs(b - a)}%`;
      land._tip = {title: `${name}: Receive − give`, lines: [`${fmt(fall.receive)} receive − ${fmt(fall.give)} give`, `= ${n.text}`, n.label]};
      const tag = document.createElement("span");
      tag.className = `v2-wf-net ${n.cls}`;
      tag.setAttribute("aria-hidden", "true");
      tag.textContent = `${n.cls === "up" ? "▲" : n.cls === "down" ? "▼" : "="} ${n.text}`;
      // Beside the bar's far end, or on the other side of 0 when the end is near the edge.
      if (fall.net >= 0) {
        if (b < 84) tag.style.left = `calc(${b}% + 6px)`;
        else tag.style.right = `calc(${100 - a}% + 6px)`;
      } else if (b > 16) tag.style.right = `calc(${100 - b}% + 6px)`;
      else tag.style.left = `calc(${a}% + 6px)`;
      lanes.net.append(land, tag);
    } else {
      const none = document.createElement("span");
      none.className = "v2-wf-none";
      none.textContent = "No result: a value is missing";
      lanes.net.appendChild(none);
    }
    cell.appendChild(box);
  }

  function showStepTip(el) {
    const tip = $("v2Tip");
    if (!el || !el._tip) { tip.hidden = true; return; }
    tip.replaceChildren();
    const h = document.createElement("h3");
    h.textContent = el._tip.title;
    tip.appendChild(h);
    el._tip.lines.forEach((text, i) => {
      const line = document.createElement(i === 0 ? "span" : "div");
      line.className = i === 0 ? "v2-meta" : "row";
      line.textContent = text;
      tip.appendChild(line);
    });
    tip.hidden = false;
    const box = el.getBoundingClientRect();
    const tipBox = tip.getBoundingClientRect();
    const left = Math.min(box.left, window.innerWidth - tipBox.width - 8);
    let top = box.bottom + 8;
    if (top + tipBox.height > window.innerHeight - 8) top = box.top - tipBox.height - 8;
    tip.style.left = `${Math.max(8, left)}px`;
    tip.style.top = `${Math.max(8, top)}px`;
  }

  function renderCompareTable(table, keys, rows, falls, sharedScale) {
    table.replaceChildren();
    const thead = document.createElement("thead");
    const hr = document.createElement("tr");
    [["Source", "player"], ["Give", "num"], ["Receive", "num"], ["From 0: give ↓ · receive ↑ · result", "bar"], ["Receive − give", "num"]].forEach(([text, cls]) => {
      const th = document.createElement("th");
      th.scope = "col";
      th.className = cls;
      th.textContent = text;
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    const tbody = document.createElement("tbody");
    const fallByKey = new Map((falls || []).map(f => [f.key, f]));
    rows.forEach(result => {
      const tr = document.createElement("tr");
      tr.dataset.source = result.key;
      if (result.key === view.rankKey) tr.className = "is-rank";
      const source = document.createElement("td");
      source.className = "player";
      sourceCell(source, result.key);
      const open = TR.open.has(result.key);
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "v2-link v2-cexpand";
      toggle.setAttribute("aria-expanded", String(open));
      toggle.textContent = open ? "Hide players ▴" : "Show players ▾";
      toggle.addEventListener("click", () => {
        if (TR.open.has(result.key)) TR.open.delete(result.key);
        else TR.open.add(result.key);
        renderCompare();
        const again = document.querySelector(`#${table.id} tr[data-source="${result.key}"] .v2-cexpand`);
        if (again) again.focus();
      });
      source.appendChild(toggle);
      tr.appendChild(source);
      const cell = (label, name, cls) => {
        const td = document.createElement("td");
        td.className = cls || "num";
        td.dataset.label = label;
        td.dataset.col = name;
        tr.appendChild(td);
        return td;
      };
      const give = cell("Give", "give");
      const get = cell("Receive", "receive");
      const bar = cell("", "bar", "bar");
      const net = cell("Receive − give", "net");
      if (result.net === null) {
        const names = result.missing.map(m => m.row.name || "a player");
        const reason = `No ${seriesName(result.key)} value for ${names.join(", ")}`;
        [give, get].forEach(td => {
          const dash = document.createElement("span");
          dash.className = "missing";
          dash.title = reason;
          dash.textContent = "—";
          td.appendChild(dash);
        });
        const node = missingNode(reason, `Incomplete: ${reason.charAt(0).toLowerCase()}${reason.slice(1)}`);
        net.appendChild(node);
      } else {
        give.textContent = fmt(result.give);
        get.textContent = fmt(result.receive);
        const n = netLabel(result.net);
        net.append(document.createTextNode(n.text));
        const why = document.createElement("span");
        why.className = `delta ${n.cls}`;
        why.textContent = n.label;
        net.appendChild(why);
      }
      // JEG-468: incomplete rows draw their steps too (hatched "no value"), but no landing.
      const fall = fallByKey.get(result.key);
      if (fall) renderWaterfall(bar, fall, sharedScale || window.TradeValueTrade.waterfallScale([fall]));
      tbody.appendChild(tr);
      if (open) tbody.appendChild(breakdownRow(result, 5));
    });
    table.append(thead, tbody);
  }

  function renderSidePlayers(side) {
    const list = $(SIDE_IDS[side].list);
    list.replaceChildren();
    const rows = side === "give" ? compareView.giveRows : compareView.receiveRows;
    const shown = TR.shown;
    rows.forEach(row => {
      const li = document.createElement("li");
      li.dataset.playerKey = String(row.player_key);
      const who = document.createElement("div");
      const name = document.createElement(row.unpriced ? "b" : "button");
      if (!row.unpriced) {
        name.type = "button";
        name.className = "v2-trade-name";
        name.setAttribute("aria-label", `${row.name}: player details`);
        name.addEventListener("click", () => openDrawer(row));
      }
      name.textContent = row.name;
      appendEspnZero(name, row);
      const sub = document.createElement("span");
      sub.className = "v2-meta";
      sub.textContent = row.unpriced ? "No value in any source for this league"
        : `${row.pos} · ${row.team || "FA"} · ${tierLabel(row.espnRole)}`;
      who.append(name, sub);
      const value = document.createElement("span");
      value.className = "v2-trade-value";
      value.dataset.source = shown || "";
      const v = shown && row.values ? row.values[shown] : null;
      if (Number.isFinite(v)) value.textContent = fmt(v);
      else value.appendChild(missingNode(`No ${shown ? seriesName(shown) : ""} value for ${row.name}`, "no value"));
      if (compareView.example) {
        li.classList.add("is-example");
        li.append(who, value, document.createElement("span"));
        list.appendChild(li);
        return;
      }
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "v2-link v2-remove";
      remove.textContent = "✕";
      remove.setAttribute("aria-label", `Remove ${row.name}`);
      remove.addEventListener("click", () => {
        TR[side] = TR[side].filter(p => p.key !== String(row.player_key));
        renderCompare();
        $(SIDE_IDS[side].search).focus();
      });
      li.append(who, value, remove);
      list.appendChild(li);
    });
    if (!rows.length) {
      const li = document.createElement("li");
      li.className = "v2-meta is-empty";
      li.textContent = "Search and add a player.";
      list.appendChild(li);
    }
    // Frame 07: "<series> total" at the foot of each side.
    const total = $(SIDE_IDS[side].total);
    const t = compareView.totals && compareView.totals[side];
    total.hidden = !rows.length || !t;
    total.replaceChildren();
    if (rows.length && t) {
      const label = document.createElement("span");
      label.className = "v2-meta";
      label.textContent = `${seriesName(t.key)} total`;
      const value = document.createElement("b");
      value.dataset.total = side;
      if (t.total === null) {
        value.appendChild(missingNode(`No ${seriesName(t.key)} value for ${t.missing.map(r => r.name).join(", ")}`, "incomplete"));
      } else {
        value.textContent = fmt(t.total);
      }
      total.append(label, value);
    }
  }

  function searchMatches(needle) {
    const rankKey = view.rankKey;
    const value = row => (Number.isFinite(row.values[rankKey]) ? row.values[rankKey] : -Infinity);
    return [...compareView.rowsByKey.values()]
      .filter(row => String(row.name || "").toLowerCase().includes(needle))
      .sort((a, b) => value(b) - value(a) || String(a.name).localeCompare(String(b.name)))
      .slice(0, 8);
  }

  function addToSide(side, row) {
    TR[side] = TR[side].concat({key: String(row.player_key), name: row.name});
    const input = $(SIDE_IDS[side].search);
    input.value = "";
    $(SIDE_IDS[side].results).hidden = true;
    renderCompare();
    input.focus();
  }

  // Frame 24 / 18: results show position, team and the ranking series' value; a player
  // already on the trade stays listed as "✓ Added" (disabled) instead of vanishing.
  function renderSearch(side) {
    const input = $(SIDE_IDS[side].search);
    const results = $(SIDE_IDS[side].results);
    const raw = input.value.trim();
    const needle = raw.toLowerCase();
    results.replaceChildren();
    if (!needle || !compareView) { results.hidden = true; return []; }
    const where = new Map(["give", "receive"].flatMap(s => TR[s].map(p => [p.key, s])));
    const matches = searchMatches(needle);
    const addable = [];
    matches.forEach(row => {
      const key = String(row.player_key);
      const on = where.get(key);
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.playerKey = key;
      const name = document.createElement("b");
      name.textContent = row.name;
      const sub = document.createElement("span");
      sub.className = "v2-meta";
      const v = row.values[view.rankKey];
      sub.textContent = ` ${row.pos} · ${row.team || "FA"} · ${sourceMeta(view.rankKey).short} ${Number.isFinite(v) ? fmt(v) : "—"}`;
      button.append(name, sub);
      if (on) {
        button.disabled = true;
        button.setAttribute("aria-disabled", "true");
        const added = document.createElement("span");
        added.className = "v2-added";
        added.textContent = on === side ? "✓ Added" : `✓ On ${SIDE_NAME[on]}`;
        button.appendChild(added);
      } else {
        button.addEventListener("click", () => addToSide(side, row));
        addable.push(row);
      }
      li.appendChild(button);
      results.appendChild(li);
    });
    if (!matches.length) {
      const li = document.createElement("li");
      li.className = "v2-meta is-empty";
      li.append(document.createTextNode(`No player matches “${raw}”. `));
      const clear = document.createElement("button");
      clear.type = "button";
      clear.className = "v2-link";
      clear.textContent = "Clear search";
      clear.addEventListener("click", () => { input.value = ""; results.hidden = true; input.focus(); });
      li.appendChild(clear);
      results.appendChild(li);
    }
    results.hidden = false;
    return addable;
  }

  // "A, B and C" (or "A, B or C") from series keys, in plain words.
  function listSeries(keys, joiner) {
    const names = keys.map(seriesName);
    if (names.length <= 1) return names.join("");
    return `${names.slice(0, -1).join(", ")} ${joiner || "and"} ${names[names.length - 1]}`;
  }

  // Frame 22 #15: copy names the publisher, methods and signed nets from data.
  function renderStory() {
    const box = $("v2CStory");
    const s = compareView.story;
    box.hidden = !s.kind || s.kind === "single";
    // Folded into the verdict card (JEG-469): open for a same-publisher contrast, which the
    // verdict does not say; otherwise one click away. A reader's own toggle is kept.
    if (box.dataset.story !== (s.kind || "")) box.open = s.kind === "contrast";
    box.dataset.story = s.kind || "";
    if (box.hidden) return;
    const title = $("v2CStoryTitle");
    const text = $("v2CStoryText");
    if (s.kind === "contrast") {
      const name = PUBLISHER_NAMES[s.publisher] || s.publisher;
      title.textContent = "Same publisher. Different result.";
      text.textContent = `${name}: the Indexed chart shows ${fmtGap(s.indexed.net)}; Data Driven Adjustments show ${fmtGap(s.dda.net)}. `
        + "Your league's adjustments reverse the direction. Compare the same publisher before comparing across sources.";
    } else if (s.kind === "agree") {
      const all = listSeries(s.upKeys.concat(s.downKeys, s.evenKeys));
      title.textContent = "Every complete source points the same way.";
      text.textContent = s.up ? `You receive more value than you give by every complete source: ${all}.`
        : s.down ? `You give more value than you receive by every complete source: ${all}.`
          : `The trade is even by every complete source: ${all}.`;
    } else if (s.kind === "split") {
      // Name the series on each side (Jeremy, 2026-10-08), then who is likeliest to say yes.
      title.textContent = "The sources split.";
      const parts = [];
      if (s.up) parts.push(`You receive more by ${listSeries(s.upKeys)}.`);
      if (s.down) parts.push(`You give more by ${listSeries(s.downKeys)}.`);
      if (s.even) parts.push(`Even by ${listSeries(s.evenKeys)}.`);
      if (s.down) parts.push(`A manager who trades off ${listSeries(s.downKeys, "or")} is the likeliest to accept.`);
      text.textContent = parts.join(" ");
    } else {
      title.textContent = "No complete source yet.";
      text.textContent = "Every selected source is missing a value for at least one player, so no row has a result. See each row for who is missing.";
    }
  }

  // JEG-469 verdict (Jeremy, 2026-10-08): "Primary thing that matters is that DDF thinks you
  // win, and it can be better if the other sources DON'T agree." One series decides (verdictKey);
  // the complete series that see it the other way are named as the selling point.
  function verdictCopy() {
    const v = compareView.verdict;
    const key = v.key || verdictKey();
    const name = key ? seriesName(key) : "";
    const thinks = keys => (keys.length === 1 ? "thinks" : "think");
    if (!key) return {kind: "none", title: "No verdict yet", text: "Pick a series in Player values shown."};
    if (!compareView.ready || !v.kind) {
      return {kind: "none", title: "No verdict yet", text: `Add a player to both sides. The verdict reads ${name}, then names the sources that see it the other way.`};
    }
    const notCounted = v.incompleteKeys.length
      ? ` Not counted, a value is missing: ${listSeries(v.incompleteKeys)}.` : "";
    if (v.kind === "incomplete") {
      const names = v.missing.map(m => m.row.name || "a player").join(", ");
      return {kind: v.kind, title: `${name}: no verdict yet`,
        text: `No ${name} value for ${names}, so this series cannot score the trade (a missing value is never counted as zero). Pick another series in Player values shown.`};
    }
    const net = fmtGap(v.net);
    if (v.kind === "win") {
      let text;
      if (v.againstKeys.length) {
        text = `${listSeries(v.againstKeys)} ${thinks(v.againstKeys)} you lose this trade. A manager who trades off ${listSeries(v.againstKeys, "or")} is the likeliest to accept.`;
        if (v.evenKeys.length) text += ` Even by ${listSeries(v.evenKeys)}.`;
      } else if (!v.others) {
        text = "No other complete source to compare with yet.";
      } else if (v.allAgree) {
        text = `Every source agrees you win: ${listSeries(v.agreeKeys)}. A fair-looking deal to them, so harder to get accepted.`;
      } else {
        text = `No source thinks you lose. ${v.agreeKeys.length ? `${listSeries(v.agreeKeys)} also ${thinks(v.agreeKeys)} you win; ` : ""}even by ${listSeries(v.evenKeys)}.`;
      }
      return {kind: v.kind, sym: "▲", title: `${name}: you win by ${net}`, text: text + notCounted};
    }
    if (v.kind === "lose") {
      const text = v.againstKeys.length
        ? `${listSeries(v.againstKeys)} ${thinks(v.againstKeys)} you win, but ${name} has you giving more value than you get. Rework the offer before you send it.`
        : !v.others ? "No other complete source to compare with yet."
          : `Every complete source agrees you lose: ${listSeries(v.agreeKeys.concat(v.evenKeys))}.`;
      return {kind: v.kind, sym: "▼", title: `${name}: you lose by ${net}`, text: text + notCounted};
    }
    const parts = [];
    if (v.upKeys.length) parts.push(`${listSeries(v.upKeys)} ${thinks(v.upKeys)} you win.`);
    if (v.downKeys.length) parts.push(`${listSeries(v.downKeys)} ${thinks(v.downKeys)} you lose.`);
    if (!parts.length) parts.push(v.others ? "Every complete source calls it even too." : "No other complete source to compare with yet.");
    return {kind: v.kind, sym: "=", title: `${name}: an even trade, 0.0`, text: parts.join(" ") + notCounted};
  }

  function renderVerdict() {
    const copy = verdictCopy();
    const card = $("v2CVerdict");
    card.dataset.verdict = copy.kind;
    card.classList.toggle("is-example", compareView.example);
    $("v2CVerdictEyebrow").textContent = compareView.example ? "Example · Verdict" : "Verdict";
    const title = $("v2CVerdictTitle");
    title.replaceChildren();
    if (copy.sym) {
      const sym = document.createElement("span");
      sym.className = "v2-cverdict-sym";
      sym.setAttribute("aria-hidden", "true");
      sym.textContent = `${copy.sym} `;
      title.appendChild(sym);
    }
    title.append(document.createTextNode(copy.title));
    $("v2CVerdictText").textContent = copy.text;
    // JEG-468/469: the verdict series' own waterfall, on the table's shared scale, above the fold.
    const holder = $("v2CVerdictFall");
    holder.querySelectorAll(".v2-wf").forEach(node => node.remove());
    const key = verdictKey();
    const isPoint = compareView.pointKeys.includes(key);
    const fall = (isPoint ? compareView.falls.points : compareView.falls.vorp).find(f => f.key === key);
    holder.hidden = !compareView.ready || !fall;
    if (fall) {
      $("v2CVerdictFallNote").textContent = "From 0: down by each player you give, up by each you receive, then the result"
        + (isPoint ? " · same scale as the table below." : " · this series' own scale.");
      renderWaterfall(holder, fall, isPoint ? compareView.scale : window.TradeValueTrade.waterfallScale([fall]));
    }
    // Phone: once both sides have a player, the verdict headline stays at the bottom.
    const bar = $("v2CVerdictBar");
    bar.dataset.verdict = copy.kind;
    bar.textContent = `${copy.sym ? `${copy.sym} ` : ""}${copy.title}`;
    bar.setAttribute("aria-label", `${copy.title}. Show the verdict`);
    TR.barWanted = compareView.ready && !compareView.example && copy.kind !== "none";
    syncVerdictBar();
  }

  function syncVerdictBar() {
    const bar = $("v2CVerdictBar");
    const show = Boolean(TR.barWanted) && isNarrow() && !TR.verdictInView && currentView() === "compare";
    bar.hidden = !show;
    $("v2Compare").classList.toggle("has-verdict-bar", Boolean(TR.barWanted) && isNarrow());
  }

  function renderShownPicker() {
    const select = $("v2CShown");
    select.replaceChildren();
    compareView.shownChoices.forEach(key => {
      const option = document.createElement("option");
      option.value = key;
      option.textContent = `${sourceMeta(key).symbol} ${sourceMeta(key).short}`;
      select.appendChild(option);
    });
    select.value = TR.shown || "";
    select.disabled = !compareView.shownChoices.length;
  }

  function renderCompare() {
    collect();
    collectCompare();
    renderHeader();
    renderShownPicker();
    renderSidePlayers("give");
    renderSidePlayers("receive");
    const ready = compareView.ready;
    renderVerdict();
    $("v2CExample").hidden = !compareView.example;
    $("v2Compare").classList.toggle("has-trade", Boolean(TR.give.length || TR.receive.length));
    $("v2Compare").classList.toggle("is-example", compareView.example);
    $("v2CEmpty").hidden = ready && compareView.pointKeys.length > 0;
    $("v2CEmpty").textContent = !ready ? "No result until both sides have at least one player."
      : "No trade-value source is selected. Use Edit sources to pick one.";
    const table = $("v2CTable");
    table.hidden = !ready || !compareView.pointKeys.length;
    renderCompareTable(table, compareView.pointKeys, compareView.points, compareView.falls.points, compareView.scale);
    $("v2CVorpCard").hidden = !ready || !compareView.vorpKeys.length;
    renderCompareTable($("v2CVorpTable"), compareView.vorpKeys, compareView.vorp, compareView.falls.vorp, null);
    renderStory();
    const notes = [];
    if (compareView.unavailable.length) {
      notes.push(`Not compared: ${compareView.unavailable.map(key => sourceMeta(key).short).join(", ")}, not available for this league.`);
    }
    const note = $("v2CNote");
    note.hidden = !notes.length;
    note.textContent = notes.join(" ");
    const count = compareView.giveRows.length + compareView.receiveRows.length;
    const sc = compareView.scale;
    $("v2CMeta").textContent = ready
      ? `${compareView.example ? "Example trade · " : ""}Receive − give · ${compareView.pointKeys.length} source${compareView.pointKeys.length === 1 ? "" : "s"} · trade-value points, never blended. `
        + `Every row's steps share one scale, ${fmt(sc.lo)} to ${fmt(sc.hi)}.`
      : "Receive − give, one row per source, once both sides have a player.";
    $("v2CClear").hidden = !count;
    $("v2CSwap").hidden = !count;
    $("v2CShare").hidden = !ready || compareView.example;
    if (!ready) $("v2CShareNote").hidden = true;
    syncTradeHash();
  }

  // Shareable trade: the sides live in the hash, so a copied link opens the same trade.
  // A shared trade also carries the sender's scoring and roster (Jeremy, 2026-10-08: the receiver
  // is assumed to be in the same league). Team count is not carried yet.
  const LINK_ROSTER = [["QB", "QB"], ["RB", "RB"], ["WR", "WR"], ["TE", "TE"], ["FLEX", "FLEX"], ["SUPERFLEX", "SF"], ["BENCH", "BN"]];
  const LINK_SCORING = ["standard", "half_ppr", "ppr"];
  function tradeHash() {
    const keys = side => TR[side].map(p => encodeURIComponent(p.key)).join(",");
    const parts = [];
    if (TR.give.length) parts.push(`give=${keys("give")}`);
    if (TR.receive.length) parts.push(`get=${keys("receive")}`);
    if (parts.length) {
      const shape = C.getRosterShape();
      parts.push(`scoring=${C.getState().scoring}`);
      parts.push(`roster=${LINK_ROSTER.map(([key, code]) => `${code}${shape[key] || 0}`).join(".")}`);
      parts.push(`bench=${Number(C.getBenchShare()).toFixed(3)}`);
      // Position shares only when the sender changed them (back end: encode when not default).
      const shares = C.getPositionWeights();
      const defaults = C.getDefaultPositionWeights ? C.getDefaultPositionWeights() : null;
      const custom = defaults && ["QB", "RB", "WR", "TE"].some(pos => Math.abs(Number(shares[pos]) - Number(defaults[pos])) > 5e-4);
      if (custom) parts.push(`shares=${["QB", "RB", "WR", "TE"].map(pos => `${pos}${Number(shares[pos]).toFixed(3)}`).join("_")}`);
    }
    return `#compare-trade${parts.length ? `?${parts.join("&")}` : ""}`;
  }
  // Apply a link's scoring and roster when they differ from the reader's; say so.
  function applyLinkLeague(params) {
    const scoring = params.get("scoring");
    const roster = {};
    String(params.get("roster") || "").split(".").forEach(part => {
      const m = /^([A-Z]+)(\d+)$/.exec(part);
      const slot = m && LINK_ROSTER.find(([, code]) => code === m[1]);
      if (slot) roster[slot[0]] = Number(m[2]);
    });
    const shape = C.getRosterShape();
    const scoringChange = LINK_SCORING.includes(scoring) && scoring !== C.getState().scoring;
    const rosterChange = Object.entries(roster).filter(([key, value]) => key in shape && shape[key] !== value);
    const bench = Number(params.get("bench"));
    const benchChange = params.has("bench") && Number.isFinite(bench) && Math.abs(bench - C.getBenchShare()) > 5e-4;
    const shares = {};
    String(params.get("shares") || "").split("_").forEach(part => {
      const m = /^(QB|RB|WR|TE)(\d*\.?\d+)$/.exec(part);
      if (m) shares[m[1]] = Number(m[2]);
    });
    const sharesGiven = Object.keys(shares).length === 4 && Boolean(C.setPositionWeights);
    if (!scoringChange && !rosterChange.length && !benchChange && !sharesGiven) return;
    if (scoringChange || rosterChange.length) {
      leagueChange(() => {
        if (scoringChange) C.setScoring(scoring);
        rosterChange.forEach(([key, value]) => C.setRosterSpot(key, value));
      });
    }
    // The link's bench share is the sender's choice, set after the league (not a re-clamp notice).
    if (benchChange) { C.setBenchShareFraction(bench); refresh(); }
    // Shares last: a league change resets them to that league's defaults. A rejected set keeps them.
    if (sharesGiven) { C.setPositionWeights(shares, false); refresh(); }
    const earlier = $("v2Status").hidden ? "" : ` ${$("v2Status").textContent}`;
    setStatus(`Opened with the link's league settings: ${$("v2LeagueName").textContent}, ${$("v2RosterLine").textContent}, `
      + `bench ${(C.getBenchShare() * 100).toFixed(1)}%.${earlier}`);
    clearTimeout(statusTimer);
    statusTimer = setTimeout(() => setStatus(""), 8000);
  }
  function readTradeHash() {
    const [base, query] = location.hash.split("?");
    if (base !== "#compare-trade" || !query) return;
    const params = new URLSearchParams(query);
    const rowsByKey = new Map(C.getAllRows().map(row => [String(row.player_key), row]));
    const seen = new Set();
    const read = name => (params.get(name) || "").split(",").map(k => decodeURIComponent(k).trim())
      .filter(k => k && !seen.has(k) && seen.add(k))
      .map(k => ({key: k, name: rowsByKey.get(k)?.name || `Player ${k}`}));
    TR.give = read("give");
    TR.receive = read("get");
    applyLinkLeague(params);
  }
  function syncTradeHash() {
    if (currentView() !== "compare") return;
    const want = tradeHash();
    if (location.hash !== want) history.replaceState(null, "", want);
  }
  async function copyTradeLink() {
    const url = location.href;
    const note = $("v2CShareNote");
    note.hidden = false;
    try {
      await navigator.clipboard.writeText(url);
      note.textContent = "✓ Link copied. It opens this trade with your scoring, roster, bench share and position shares; the team count stays the reader's.";
    } catch (error) {
      note.textContent = `Copy this link: ${url}`;
    }
  }

  function bindCompare() {
    $("v2CShare").addEventListener("click", copyTradeLink);
    // JEG-468: hover / focus tooltip for every waterfall step.
    const compare = $("v2Compare");
    const stepOf = event => event.target.closest && event.target.closest(".v2-wf-step, .v2-wf-land");
    compare.addEventListener("mouseover", event => { const el = stepOf(event); if (el) showStepTip(el); });
    compare.addEventListener("mouseout", event => { if (stepOf(event)) $("v2Tip").hidden = true; });
    compare.addEventListener("focusin", event => { const el = stepOf(event); if (el) showStepTip(el); });
    compare.addEventListener("focusout", event => { if (stepOf(event)) $("v2Tip").hidden = true; });
    compare.addEventListener("keydown", event => { if (event.key === "Escape" && stepOf(event)) $("v2Tip").hidden = true; });
    $("v2CUseExample").addEventListener("click", () => {
      if (!compareView || !compareView.example) return;
      const pick = list => list.map(row => ({key: String(row.player_key), name: row.name}));
      TR.give = pick(compareView.giveRows);
      TR.receive = pick(compareView.receiveRows);
      renderCompare();
      $("v2GiveSearch").focus();
    });
    $("v2CVerdictBar").addEventListener("click", () => {
      const card = $("v2CVerdict");
      card.scrollIntoView({block: "center"});
      card.setAttribute("tabindex", "-1");
      card.focus({preventScroll: true});
    });
    if (window.IntersectionObserver) {
      new IntersectionObserver(entries => {
        TR.verdictInView = entries[entries.length - 1].isIntersecting;
        syncVerdictBar();
      }).observe($("v2CVerdict"));
    }
    if (narrowQuery && narrowQuery.addEventListener) narrowQuery.addEventListener("change", syncVerdictBar);
    ["give", "receive"].forEach(side => {
      const input = $(SIDE_IDS[side].search);
      input.addEventListener("input", () => renderSearch(side));
      input.addEventListener("keydown", event => {
        if (event.key === "Enter") {
          event.preventDefault();
          const first = renderSearch(side)[0];
          if (first) addToSide(side, first);
        } else if (event.key === "Escape") {
          $(SIDE_IDS[side].results).hidden = true;
        }
      });
    });
    $("v2CClear").addEventListener("click", () => { TR.give = []; TR.receive = []; TR.open.clear(); renderCompare(); });
    $("v2CSwap").addEventListener("click", () => { [TR.give, TR.receive] = [TR.receive, TR.give]; renderCompare(); });
    $("v2CShown").addEventListener("change", event => { TR.shown = event.target.value; renderCompare(); });
  }

  // ---------- How values work (frames 15 / 16) ----------
  // Explains the three views (docs/methodology.md, "The Three Views"). It adds no
  // numbers: the league line and the source lists come straight from the engine.
  function renderHow() {
    collect();
    renderHeader();
    $("v2HowLeague").textContent = $("v2LeagueName").textContent;
    $("v2HowRoster").textContent = $("v2RosterLine").textContent;
    const weights = C.getPositionWeights();
    $("v2HowWeights").textContent = ["QB", "RB", "WR", "TE"]
      .map(pos => `${pos} ${Number.isFinite(Number(weights[pos])) ? `${(Number(weights[pos]) * 100).toFixed(1)}%` : "—"}`).join(" · ");
    const bench = C.getBenchShare();
    $("v2HowBench").textContent = Number.isFinite(bench) ? `${(bench * 100).toFixed(1)}%` : "—";
    document.querySelectorAll("#v2How [data-sources]").forEach(list => {
      const method = list.dataset.sources;
      list.replaceChildren();
      view.info.filter(item => sourceMeta(item.key).method === method).forEach(item => {
        const meta = sourceMeta(item.key);
        const li = document.createElement("li");
        li.dataset.source = item.key;
        li.dataset.available = String(Boolean(item.available));
        const sym = document.createElement("span");
        sym.className = "v2-sym";
        sym.style.color = meta.color;
        sym.setAttribute("aria-hidden", "true");
        sym.textContent = `${meta.symbol} `;
        li.append(sym, document.createTextNode(PUBLISHER_NAMES[meta.publisher] || meta.label));
        const why = document.createElement("span");
        why.className = `v2-meta${item.stale ? " is-older" : ""}`;
        why.textContent = !item.available
          ? (item.paused ? " — waiting on fresh inputs" : " — not available for this league")
          : item.stale ? " · older week" : "";
        // V2-WAIVER-COVERAGE: a short chart's waiver line is extrapolated; say so here too.
        if (item.available && item.waiverNote) why.textContent += ` · ${item.waiverNote}`;
        if (why.textContent) li.appendChild(why);
        list.appendChild(li);
      });
    });
  }

  // ---------- Risers & fallers (frames 05 / 06) ----------
  // One exact series at a time: Δ = later week − earlier week, both recomputed by
  // the engine at the current setting (app/v2/movers.js does the subtraction).
  // The served pair uses the engine's rows for "now" and getPriorWeek for the week
  // before; an earlier pair (frame 19 #05: the N−1 → N control) uses getWeekValues
  // for both weeks. A series with no prior week is listed disabled with the reason.
  const RISERS_PAGE = 10;
  const R = {series: null, week: null, search: "", shown: {rise: RISERS_PAGE, fall: RISERS_PAGE}};
  let risersView = null;
  const weeksCache = new Map();   // series -> getHistoryWeeks result (the saved weeks do not change)
  const pairCache = new Map();    // "series:week" -> {prior, after} for an earlier week pair

  function priorLabel(key) {
    const meta = sourceMeta(key);
    return plainSeries(meta.publisher, meta.method);
  }

  // Week pairs the engine can price for a series: every saved week whose week before is
  // also saved, up to the week served now. Latest first.
  function weekPairs(key) {
    const info = weeksCache.get(key);
    if (!info || !Number.isInteger(info.servedWeek)) return [];
    const saved = new Set(info.weeks);
    return info.weeks.filter(week => week <= info.servedWeek && saved.has(week - 1)).reverse();
  }

  function loadPair(key, week) {
    const id = `${key}:${week}`;
    const stamp = priorStamp;
    return Promise.all([C.getWeekValues(key, week), C.getWeekValues(key, week - 1)])
      .catch(error => [{available: false, reason: error.message}, {available: false, reason: error.message}])
      .then(([after, before]) => {
        if (stamp !== priorStamp) return;
        const available = after.available && before.available;
        pairCache.set(id, {after, prior: {available, reason: available ? null : (after.available ? before.reason : after.reason),
          values: before.values, currentWeek: week, priorWeek: week - 1}});
      });
  }

  function renderRisers() {
    collect();
    renderHeader();
    const M = window.TradeValueMovers;
    const loading = text => {
      $("v2RMeta").textContent = text;
      ["v2RRise", "v2RFall"].forEach(id => $(id).replaceChildren());
    };
    const missing = M.SERIES.filter(key => !priorCache.has(key));
    if (missing.length) {
      loading("Recomputing last week for your league…");
      priorsFor(M.SERIES).then(() => { if (currentView() === "risers") renderRisers(); });
      return;
    }
    const choices = M.SERIES.map(key => ({key, prior: priorCache.get(key)}));
    if (!R.series || !choices.some(c => c.key === R.series)) {
      R.series = (choices.find(c => c.prior.available) || choices[0]).key;
    }
    const select = $("v2RSeries");
    select.replaceChildren();
    choices.forEach(({key, prior}) => {
      const option = document.createElement("option");
      option.value = key;
      option.disabled = !prior.available;
      option.textContent = `${sourceMeta(key).symbol} ${priorLabel(key)}` + (prior.available ? "" : " — no prior week");
      option.title = prior.available ? "" : prior.reason;
      select.appendChild(option);
    });
    select.value = R.series;
    $("v2RPosition").value = view.state.position;
    const servedPrior = priorCache.get(R.series);
    if (servedPrior.available && !weeksCache.has(R.series)) {
      loading("Reading the saved weeks…");
      Promise.resolve().then(() => C.getHistoryWeeks(R.series))
        .catch(error => ({servedWeek: null, weeks: [], reason: error.message}))
        .then(info => { weeksCache.set(R.series, info); if (currentView() === "risers") renderRisers(); });
      return;
    }
    const pairs = servedPrior.available ? weekPairs(R.series) : [];
    if (!pairs.includes(R.week)) R.week = servedPrior.available ? servedPrior.currentWeek : null;
    const weeks = $("v2RWeeks");
    weeks.replaceChildren();
    (pairs.length ? pairs : [R.week]).forEach(week => {
      const option = document.createElement("option");
      option.value = String(week);
      option.textContent = Number.isInteger(week) ? `Week ${week - 1} → Week ${week}` : "No week pair";
      weeks.appendChild(option);
    });
    weeks.value = String(R.week);
    weeks.disabled = pairs.length < 2;
    let prior = servedPrior;
    let source = C.getRows();
    if (servedPrior.available && R.week !== servedPrior.currentWeek) {
      const pair = pairCache.get(`${R.series}:${R.week}`);
      if (!pair) {
        loading(`Recomputing Weeks ${R.week - 1} and ${R.week} for your league…`);
        loadPair(R.series, R.week).then(() => { if (currentView() === "risers") renderRisers(); });
        return;
      }
      prior = pair.prior;
      const later = pair.after.values || {};
      source = source.map(row => ({...row, values: {...row.values, [R.series]: later[String(row.player_key)] ?? null}}));
    }
    const needle = R.search.trim().toLowerCase();
    const rows = source.filter(row => !needle || String(row.name || "").toLowerCase().includes(needle));
    risersView = M.buildMovers(rows, R.series, prior);
    const label = priorLabel(R.series);
    const v = risersView;
    $("v2RMeta").textContent = v.available
      ? `${label} · Δ = Week ${v.currentWeek} − Week ${v.priorWeek}, both priced for your league. `
        + (sourceMeta(R.series).method === "dda"
          ? "A projection moving is a change in that source's outlook."
          : "A riser now costs more from a manager who trades off this chart; a faller costs less.")
      : `No Δ for ${label}: ${v.reason}.`;
    // One bar scale for both lists, so a bar's length means the same number of points on either side.
    const shownItems = v.risers.slice(0, R.shown.rise).concat(v.fallers.slice(0, R.shown.fall));
    const scale = shownItems.reduce((max, item) => Math.max(max, Math.abs(item.delta)), 0);
    renderMoverList("rise", v.risers, scale);
    renderMoverList("fall", v.fallers, scale);
    $("v2RScale").textContent = scale > 0
      ? `Bars share a scale of ${scale.toFixed(1)} value points (the largest change shown). Δ — for missing history: never a zero change.`
      : "Δ — for missing history: never a zero change.";
    const notes = [];
    if (v.noPrior) notes.push(`${v.noPrior} player${v.noPrior === 1 ? "" : "s"} left out: not priced by ${label} in Week ${v.priorWeek}, so no Δ.`);
    if (v.noCurrent) notes.push(`${v.noCurrent} without a Week ${v.currentWeek} ${label} value.`);
    if (v.unchanged) notes.push(`${v.unchanged} unchanged (Δ 0.0).`);
    const unavailable = choices.filter(c => !c.prior.available);
    if (unavailable.length) notes.push(`No prior week: ${unavailable.map(c => `${priorLabel(c.key)} (${c.prior.reason})`).join("; ")}.`);
    const note = $("v2RNote");
    note.hidden = !notes.length;
    note.textContent = notes.join(" ");
  }

  function renderMoverList(side, list, scale) {
    const ids = side === "rise" ? {list: "v2RRise", empty: "v2RRiseEmpty", more: "v2RRiseMore"}
      : {list: "v2RFall", empty: "v2RFallEmpty", more: "v2RFallMore"};
    const ol = $(ids.list);
    ol.replaceChildren();
    const v = risersView;
    list.slice(0, R.shown[side]).forEach(item => {
      const row = item.row;
      const li = document.createElement("li");
      li.tabIndex = 0;
      li.dataset.playerKey = String(row.player_key);
      li.addEventListener("click", () => openDrawer(row));
      li.addEventListener("keydown", event => { if (event.key === "Enter") openDrawer(row); });
      const top = document.createElement("div");
      top.className = "m-top";
      const who = document.createElement("div");
      const name = document.createElement("b");
      name.textContent = row.name;
      appendEspnZero(name, row);
      const sub = document.createElement("span");
      sub.className = "v2-meta";
      sub.textContent = `${row.pos} · ${row.team || "FA"}`;
      who.append(name, sub);
      const big = document.createElement("div");
      big.className = `big ${item.delta > 0 ? "up" : "down"}`;
      big.dataset.col = "delta";
      big.textContent = `${item.delta > 0 ? "▲" : "▼"} ${fmtGap(item.delta)}`;
      top.append(who, big);
      const bottom = document.createElement("div");
      bottom.className = "m-bottom";
      const vals = document.createElement("span");
      vals.className = "v2-meta m-vals";
      vals.title = `Week ${v.priorWeek} → Week ${v.currentWeek}`;
      const before = document.createElement("span");
      before.dataset.col = "before";
      before.textContent = fmt(item.before);
      const now = document.createElement("span");
      now.dataset.col = "now";
      now.textContent = fmt(item.current);
      vals.append(before, document.createTextNode(" → "), now);
      const bar = document.createElement("span");
      bar.className = `m-bar ${item.delta > 0 ? "up" : "down"}`;
      bar.setAttribute("aria-hidden", "true");
      const fill = document.createElement("span");
      fill.style.width = `${scale > 0 ? Math.min(100, (Math.abs(item.delta) / scale) * 100) : 0}%`;
      bar.appendChild(fill);
      bottom.append(vals, bar);
      li.append(top, bottom);
      ol.appendChild(li);
    });
    const empty = $(ids.empty);
    empty.hidden = v.available && list.length > 0;
    empty.textContent = !v.available ? "No Δ for this source: see the note above."
      : `No player ${side === "rise" ? "rose" : "fell"} in ${priorLabel(R.series)} for this selection.`;
    const more = $(ids.more);
    more.hidden = list.length <= R.shown[side];
    more.textContent = `Show more ${side === "rise" ? "risers" : "fallers"} (${Math.min(R.shown[side], list.length)} of ${list.length})`;
  }

  function bindRisers() {
    let timer = null;
    const reset = () => { R.shown = {rise: RISERS_PAGE, fall: RISERS_PAGE}; };
    $("v2RSearch").addEventListener("input", event => {
      clearTimeout(timer);
      timer = setTimeout(() => { R.search = event.target.value; reset(); renderRisers(); }, 120);
    });
    $("v2RPosition").addEventListener("change", event => { C.setPosition(event.target.value); reset(); renderRisers(); });
    $("v2RSeries").addEventListener("change", event => { R.series = event.target.value; R.week = null; reset(); renderRisers(); });
    $("v2RWeeks").addEventListener("change", event => { R.week = Number(event.target.value); reset(); renderRisers(); });
    $("v2RRiseMore").addEventListener("click", () => { R.shown.rise += RISERS_PAGE; renderRisers(); });
    $("v2RFallMore").addEventListener("click", () => { R.shown.fall += RISERS_PAGE; renderRisers(); });
  }

  // ---------- routing ----------
  // A hash may carry a query (a shared trade: #compare-trade?give=1,2&get=3).
  const hashBase = () => location.hash.split("?")[0];
  const currentView = () => (hashBase() === "#trade-targets" ? "targets"
    : hashBase() === "#risers-fallers" ? "risers"
    : hashBase() === "#compare-trade" ? "compare"
    : hashBase() === "#how-values" ? "how"
    : hashBase() === "#player-values" ? "values" : "targets");   // landing: Trade targets (Jeremy, 2026-10-08)

  function applyRoute() {
    const v = currentView();
    $("v2Main").hidden = v !== "values";
    $("v2Targets").hidden = v !== "targets";
    $("v2Compare").hidden = v !== "compare";
    $("v2Risers").hidden = v !== "risers";
    $("v2How").hidden = v !== "how";
    // The source selection applies on Compare a trade too; Trade targets has its own pickers.
    $("v2Methods").hidden = v === "targets" || v === "risers";
    document.querySelectorAll(".v2-tab[data-view]").forEach(tab => {
      const on = tab.dataset.view === v;
      tab.classList.toggle("is-active", on);
      if (on) tab.setAttribute("aria-current", "page");
      else tab.removeAttribute("aria-current");
    });
    closePopover();
    $("v2Tip").hidden = true;
    refresh();
  }

  // ---------- wiring ----------
  function refreshValues() {
    collect();
    renderHeader();
    renderEmpty();
    renderNotice();
    renderTable();
    renderCharts();
  }

  // Frame 18: filters that leave no player say which filter did it.
  function renderEmpty() {
    const empty = !view.visible.length;
    $("v2Empty").hidden = !empty;
    $("v2Plot").hidden = empty;
    $("v2Chart").hidden = empty;
    $("v2TableCard").hidden = empty;
    if (!empty) return;
    const why = [];
    if (state.search.trim()) why.push(`no player name contains “${state.search.trim()}”`);
    if (state.range.min !== null || state.range.max !== null) {
      why.push(`no ${sourceMeta(view.rankKey).short} value is in ${state.range.min ?? "…"}–${state.range.max ?? "…"}`);
    }
    if (view.state.position !== "ALL") why.push(`the position filter is ${view.state.position}`);
    if (view.rows.length && state.windowPreset !== SHOW_DEFAULT) why.push(`Show is set to ${$("v2Show").selectedOptions[0]?.textContent || state.windowPreset}`);
    $("v2EmptyText").textContent = why.length ? `With these filters, ${why.join("; ")}.` : "No player is priced for this selection.";
    const active = {search: Boolean(state.search.trim()), range: state.range.min !== null || state.range.max !== null,
      position: view.state.position !== "ALL"};
    document.querySelectorAll("#v2EmptyActions [data-clear]").forEach(button => { button.hidden = !active[button.dataset.clear]; });
    $("v2EmptyClear").hidden = Object.values(active).filter(Boolean).length < 2;
  }

  // Frame 18: "Only one comparable series" and "No current-week sources".
  function renderNotice() {
    const keys = view.plotKeys.filter(key => view.infoByKey[key]?.available);
    let text = "";
    if (keys.length && keys.every(key => view.infoByKey[key]?.stale)) {
      text = "No current-week values are selected. The values shown are from an older week and are labeled; choose a current-week source to compare.";
    } else if (keys.length === 1) {
      text = `Only one series is selected (${sourceMeta(keys[0]).short}). Choose another source to see where the sources disagree.`;
    }
    $("v2Notice").hidden = !text;
    $("v2NoticeText").textContent = text;
  }

  // Settings popovers and shared-state changes call this; it redraws whichever tab is showing.
  function refresh() {
    if (currentView() === "targets") renderTargets();
    else if (currentView() === "risers") renderRisers();
    else if (currentView() === "compare") renderCompare();
    else if (currentView() === "how") renderHow();
    else refreshValues();
  }

  // Brushes and drags redraw once per frame.
  let valuesFrame = 0;
  function scheduleValues() {
    if (valuesFrame) return;
    valuesFrame = requestAnimationFrame(() => { valuesFrame = 0; if (currentView() === "values") refreshValues(); });
  }
  // A brush, zoom or exact ranks: Show becomes "Custom lo–hi".
  function setWindow(win) {
    state.window = win;
    state.windowPreset = "custom";
    state.shown = PAGE_SIZE;
    scheduleValues();
  }
  // The value range (Y brush or "Set exact values") composes with the rank window; Show reads Custom.
  function setRange(range) {
    state.range = range;
    if (range.min !== null || range.max !== null) state.windowPreset = "custom";
    state.shown = PAGE_SIZE;
    scheduleValues();
  }
  // JEG-475: one Reset for search, position, Show, value range, sort and Δ. Rank by, sources,
  // columns and league settings are selections, not filters, and stay.
  function resetValues() {
    state.search = ""; $("v2Search").value = "";
    state.range = {min: null, max: null};
    state.windowPreset = SHOW_DEFAULT; state.window = null;
    state.sort = null; state.shown = PAGE_SIZE; state.delta = false;
    if (view && view.state.position !== "ALL") C.setPosition("ALL");
    refresh();
  }

  function bind() {
    let searchTimer = null;
    $("v2Search").addEventListener("input", event => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => { state.search = event.target.value; state.shown = PAGE_SIZE; refresh(); }, 120);
    });
    $("v2Position").addEventListener("change", event => { C.setPosition(event.target.value); refresh(); });
    $("v2RankBy").addEventListener("change", event => { C.setLockOrder(event.target.value); state.sort = null; refresh(); });
    $("v2DeltaBtn").addEventListener("click", () => {
      state.delta = !state.delta;
      refresh();
      if (state.delta) priorsFor(view.plotKeys.concat(view.vorpKeys)).then(() => { if (state.delta) refresh(); });
    });
    $("v2Show").addEventListener("change", event => {
      if (event.target.value === "custom") return;
      state.windowPreset = event.target.value;
      state.shown = PAGE_SIZE;
      refresh();
    });
    $("v2More").addEventListener("click", openMore);
    $("v2Columns").addEventListener("click", openColumns);
    $("v2YExact").addEventListener("click", openRange);
    $("v2Reset").addEventListener("click", resetValues);
    $("v2EmptyClear").addEventListener("click", resetValues);
    $("v2NoticeBtn").addEventListener("click", event => openSources(event.currentTarget));
    document.querySelectorAll("#v2EmptyActions [data-clear]").forEach(button => {
      button.addEventListener("click", () => {
        const what = button.dataset.clear;
        if (what === "search") { state.search = ""; $("v2Search").value = ""; }
        if (what === "range") state.range = {min: null, max: null};
        if (what === "position") C.setPosition("ALL");
        state.shown = PAGE_SIZE;
        refresh();
      });
    });
    $("v2EditSources").addEventListener("click", event => openSources(event.currentTarget));
    $("v2EditLeague").addEventListener("click", openLeague);
    $("v2Weights").addEventListener("click", openWeights);
    $("v2Freshness").addEventListener("click", openFreshness);
    $("v2HowWeightsBtn").addEventListener("click", openWeights);
    // Skip link: a button, because a #fragment would change the hash route.
    $("v2Skip").addEventListener("click", () => {
      const main = [...document.querySelectorAll("main.v2-main")].find(m => !m.hidden);
      if (!main) return;
      main.tabIndex = -1;
      main.focus();
    });
    $("v2ShowMore").addEventListener("click", () => { state.shown += PAGE_SIZE; renderTable(); });
    // X rank brush: dragging sets Show to "Custom lo–hi" (JEG-475).
    const onBrush = () => {
      let lo = Number($("v2BrushLo").value);
      let hi = Number($("v2BrushHi").value);
      if (lo > hi) [lo, hi] = [hi, lo];
      setWindow([lo, hi]);
    };
    $("v2BrushLo").addEventListener("input", onBrush);
    $("v2BrushHi").addEventListener("input", onBrush);
    // Y value brush (JEG-472): live filter on the ranking series; the ends of the track mean open ended.
    const onYBrush = event => {
      const {lo: ylo, hi: yhi} = view.yScale;
      let lo = Number($("v2YBrushLo").value);
      let hi = Number($("v2YBrushHi").value);
      if (lo > hi) {
        if (event.target.id === "v2YBrushLo") lo = hi; else hi = lo;
        event.target.value = String(event.target.id === "v2YBrushLo" ? lo : hi);
      }
      setRange({min: lo <= ylo ? null : lo, max: hi >= yhi ? null : hi});
    };
    ["v2YBrushLo", "v2YBrushHi"].forEach(id => {
      $(id).addEventListener("input", onYBrush);
      // PageUp / PageDown jump a tenth of the scale; arrows step 0.5 (native).
      $(id).addEventListener("keydown", event => {
        if (event.key !== "PageUp" && event.key !== "PageDown") return;
        event.preventDefault();
        const input = event.currentTarget;
        const {lo: ylo, hi: yhi} = view.yScale;
        const jump = Math.max(0.5, Math.round((yhi - ylo) / 10 * 2) / 2);
        input.value = String(Math.max(ylo, Math.min(yhi, Number(input.value) + (event.key === "PageUp" ? jump : -jump))));
        onYBrush({target: input});
      });
    });
    const zoom = factor => {
      const n = view.rows.length;
      const [lo, hi] = state.window;
      const center = state.hoverIndex !== null && view.visible[state.hoverIndex] ? view.visible[state.hoverIndex].rank : (lo + hi) / 2;
      const span = Math.max(5, Math.min(n, Math.round((hi - lo + 1) * factor)));
      let nlo = Math.round(center - span / 2);
      nlo = Math.max(1, Math.min(n - span + 1, nlo));
      setWindow([nlo, Math.min(n, nlo + span - 1)]);
    };
    $("v2ZoomIn").addEventListener("click", () => zoom(0.5));
    $("v2ZoomOut").addEventListener("click", () => zoom(2));
    bindChart("v2Chart", () => mainChart);
    bindChart("v2VorpChart", () => vorpChart);
    bindChartKeys();
    $("v2Scrim").addEventListener("click", () => { if (panelOpen) closePopover(); else closeDrawer(); });
    document.addEventListener("keydown", event => {
      if (event.key === "Tab") {
        const box = !$("v2Popover").hidden && panelOpen ? $("v2Popover") : !$("v2Drawer").hidden ? $("v2Drawer") : null;
        if (!box) return;
        const items = [...box.querySelectorAll("button, a[href], input, select, [tabindex='0']")]
          .filter(n => !n.disabled && n.offsetParent !== null);
        if (!items.length) return;
        const first = items[0];
        const last = items[items.length - 1];
        if (!box.contains(document.activeElement)) { event.preventDefault(); first.focus(); }
        else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        return;
      }
      if (event.key !== "Escape") return;
      if (!$("v2Popover").hidden) closePopover();
      else if (!$("v2Drawer").hidden) closeDrawer();
    });
    document.addEventListener("mousedown", event => {
      const pop = $("v2Popover");
      if (pop.hidden || pop.contains(event.target) || (popoverAnchor && popoverAnchor.contains(event.target))) return;
      closePopover();
    });
    let resizeTimer = null;
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => { if (currentView() === "values") renderCharts(); }, 100);
    });
    window.addEventListener("hashchange", () => { readTradeHash(); applyRoute(); });
    if (darkQuery && darkQuery.addEventListener) darkQuery.addEventListener("change", () => { if (C) refresh(); });
    if (narrowQuery && narrowQuery.addEventListener) narrowQuery.addEventListener("change", () => { if (C) refresh(); });
    if (metaWideQuery && metaWideQuery.addEventListener) metaWideQuery.addEventListener("change", () => { if (C && currentView() === "values") renderTable(); });
    bindTargets();
    bindCompare();
    window.addEventListener("trade-value-shared-change", () => { if (C) refresh(); });
    // New rows (league, weights, sources): every prior-week recompute is stale.
    window.addEventListener("trade-value-rows-change", () => {
      priorCache.clear();
      pairCache.clear();
      priorStamp += 1;
      if (!C) return;
      if (currentView() === "risers") renderRisers();
      else if (state.delta && currentView() === "values") {
        refresh();
        priorsFor(view.plotKeys.concat(view.vorpKeys)).then(() => { if (state.delta) refresh(); });
      }
    });
    bindRisers();
  }

  async function start() {
    document.body.classList.add("v2");
    try {
      C = await waitForEngine();
    } catch (error) {
      showFailure(error.message);
      return;
    }
    leagueDefaults = {scoring: C.getState().scoring, teams: C.getState().teams, roster: {...C.getRosterShape()}};
    startActive = C.getActiveSources().slice();
    loadPipeline();
    bind();
    setStatus("");
    readTradeHash();   // may set a status: a shared link's league settings were applied
    $("v2State").hidden = true;
    applyRoute();
    window.TradeValueV2 = {state, view: () => view, targets: () => targetsView, targetState: T,
      compare: () => compareView, tradeState: TR,
      risers: () => risersView, risersState: R, priors: () => Object.fromEntries(priorCache)};
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
