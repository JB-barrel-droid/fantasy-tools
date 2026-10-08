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
  const isNarrow = () => Boolean(narrowQuery && narrowQuery.matches);
  const SHORT_METHOD = {dda: "DDA", indexed: "Index", vorp: "VORP vs waivers"};
  const PLAIN_METHOD = {dda: "Our value", indexed: "Published chart", vorp: "VORP vs waivers"};
  const METHOD_LABEL = new Proxy({}, {get: (_, method) => (isNarrow() ? SHORT_METHOD : PLAIN_METHOD)[method]});
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

  const state = {
    search: "",
    range: {min: null, max: null},
    delta: false,
    window: null,          // [lo, hi] 1-based rank window for the chart
    windowPreset: "100",
    sort: null,            // {key, dir}; null = rank-series order
    shown: PAGE_SIZE,
    hoverIndex: null,
    focusIndex: 0,
    hideZeroTail: false,   // frame 21: chart only
    yBounds: null,         // frame 21: {lo, hi} custom Y axis, null = auto
    metaCols: {pos: true, team: true, tier: true}
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
    const {min, max} = state.range;
    let omittedMissing = 0;
    const rows = allRows.filter(row => {
      if (needle && !String(row.name || "").toLowerCase().includes(needle)) return false;
      if (min !== null || max !== null) {
        const v = row.values[rankKey];
        if (!Number.isFinite(v)) { omittedMissing += 1; return false; }
        if (min !== null && v < min) return false;
        if (max !== null && v > max) return false;
      }
      return true;
    });
    rows.forEach((row, index) => { row.rank = index + 1; });
    const freshness = window.TradeValueProductData?.getSourceFreshness?.() || null;
    const refWeek = freshness?.current_content_week || C.getReferenceWeek();
    view = {info, infoByKey, active, rankKey, plotKeys, vorpKeys, rows, totalRows: allRows.length, omittedMissing,
      refWeek, state: C.getState(), roster: C.getRosterShape()};
    const n = rows.length;
    // Frame 21 "Hide zero-value tail": the chart stops at the last player with a ranking value above 0.
    let last = n;
    if (state.hideZeroTail) {
      while (last > 1 && !(rows[last - 1].values[rankKey] > 0)) last -= 1;
    }
    const zone = zoneWindow(rows, state.windowPreset);
    if (zone) {
      state.window = [Math.min(zone[0], last), Math.max(1, Math.min(zone[1], last))];
    } else if (!state.window || state.windowPreset !== "custom") {
      const hi = state.windowPreset === "all" ? last : Number(state.windowPreset) || last;
      state.window = [1, Math.max(1, Math.min(last, hi))];
    } else {
      state.window = [Math.max(1, Math.min(state.window[0], n)), Math.max(1, Math.min(state.window[1], n))];
    }
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

  // ---------- header, league, methods ----------
  function renderHeader() {
    const s = view.state;
    const scoring = {standard: "Standard", half_ppr: "Half PPR", ppr: "Full PPR"}[s.scoring] || s.scoring;
    $("v2LeagueName").textContent = `${scoring} · ${s.teams} teams`;
    const r = view.roster;
    $("v2RosterLine").textContent = `${r.QB} QB · ${r.RB} RB · ${r.WR} WR · ${r.TE} TE · ${r.FLEX} FLEX · ${r.BENCH} BN`;
    const older = view.active.some(key => view.infoByKey[key]?.stale);
    // Frame 18 "partial source failure": a selected series the engine cannot price right now.
    const failing = view.active.filter(key => !view.infoByKey[key]?.available);
    $("v2FreshnessLabel").textContent = `${failing.length ? "⚠ " : ""}${view.refWeek ? `W${view.refWeek} · ` : ""}Freshness ↗`;
    $("v2Freshness").classList.toggle("is-older", older);
    $("v2Freshness").classList.toggle("is-failing", failing.length > 0);
    $("v2Freshness").setAttribute("aria-label", `Source freshness${failing.length ? `: ${failing.length} selected source${failing.length === 1 ? "" : "s"} unavailable` : ""}`);

    const methods = $("v2MethodChips");
    methods.replaceChildren();
    (isNarrow() ? [["dda", "DDA"], ["indexed", "Indexed"], ["vorp", "VORP vs waivers"]]
      : [["dda", "Our values"], ["indexed", "Published charts"], ["vorp", "VORP vs waivers"]]).forEach(([method, label]) => {
      const on = view.active.some(key => sourceMeta(key).method === method);
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = `v2-chip${on ? " is-on" : ""}${method === "indexed" ? " is-indexed" : ""}`;
      chip.textContent = on ? `✓ ${label}` : `${label} +`;
      chip.setAttribute("aria-pressed", String(on));
      chip.addEventListener("click", event => openSources(event.currentTarget, method));
      methods.appendChild(chip);
    });

    const chips = $("v2SourceChips");
    chips.replaceChildren();
    view.active.forEach(key => {
      const meta = sourceMeta(key);
      const item = view.infoByKey[key];
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = `v2-chip${item?.stale ? " is-older" : ""}`;
      chip.style.color = item?.stale ? "" : meta.color;
      chip.title = `${PUBLISHER_NAMES[meta.publisher] || meta.label} · ${METHOD_LABEL[meta.method]}${item?.stale ? " · older week" : ""}`;
      chip.innerHTML = `<span class="v2-sym" aria-hidden="true">${meta.symbol}</span>`;
      chip.append(document.createTextNode(sourceLabelFor(key)));
      chip.addEventListener("click", event => openSources(event.currentTarget));
      chips.appendChild(chip);
    });
    $("v2EditSources").textContent = `Edit sources · ${view.active.length} selected`;

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
    const rangeOn = state.range.min !== null || state.range.max !== null;
    $("v2RangeBtn").textContent = rangeOn
      ? `Value ${state.range.min ?? "…"}–${state.range.max ?? "…"}`
      : "Value range";
    $("v2DeltaBtn").textContent = `Δ Prior week · ${state.delta ? "On" : "Off"}`;
    $("v2DeltaBtn").setAttribute("aria-pressed", String(state.delta));
    const note = $("v2FilterNote");
    const notes = [];
    if (rangeOn && view.omittedMissing) {
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
    view.plotKeys.concat(view.vorpKeys).forEach(key => {
      const meta = sourceMeta(key);
      const span = document.createElement("span");
      const swatch = el("svg", {width: 22, height: 8, "aria-hidden": "true"});
      el("line", {x1: 0, y1: 4, x2: 22, y2: 4, stroke: meta.color, "stroke-width": 2,
        "stroke-dasharray": meta.method === "indexed" ? "6 4" : meta.method === "vorp" ? "1.5 4" : ""}, swatch);
      span.appendChild(swatch);
      span.append(document.createTextNode(`${meta.symbol} ${meta.short}`));
      legend.appendChild(span);
    });
  }

  function drawSeriesChart(container, keys, opts) {
    container.replaceChildren();
    const rect = container.getBoundingClientRect();
    const width = Math.max(280, rect.width);
    const height = Math.max(160, rect.height);
    const pad = {l: 40, r: 12, t: 12, b: opts.names ? 46 : 30};
    const [lo, hi] = state.window;
    const slice = view.rows.slice(lo - 1, hi);
    const n = slice.length;
    const svg = el("svg", {viewBox: `0 0 ${width} ${height}`, role: "img",
      "aria-label": `${opts.label}: ranks ${lo} to ${hi}`}, container);
    let vmax = 0;
    slice.forEach(row => keys.forEach(key => {
      const v = row.values[key];
      if (Number.isFinite(v) && v > vmax) vmax = v;
    }));
    let {max: ymax, step: ystep} = niceScale(vmax);
    let ymin = 0;
    if (opts.yBounds) {
      ymin = Number.isFinite(opts.yBounds.lo) ? opts.yBounds.lo : 0;
      if (Number.isFinite(opts.yBounds.hi)) ymax = opts.yBounds.hi;
      ystep = niceScale(ymax - ymin).step;
    }
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
      const label = el("text", {x: x(i), y: height - (opts.names ? 30 : 10), "text-anchor": "middle"}, axis);
      label.textContent = lo + i;
    }
    if (opts.names) {
      const pxPer = n > 1 ? (width - pad.l - pad.r) / (n - 1) : width;
      if (pxPer >= 64) {
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
    mainChart = drawSeriesChart($("v2Chart"), view.plotKeys, {label: "Trade value by player rank", names: true, yBounds: state.yBounds});
    const vorpCard = $("v2VorpCard");
    vorpCard.hidden = !view.vorpKeys.length;
    vorpChart = view.vorpKeys.length
      ? drawSeriesChart($("v2VorpChart"), view.vorpKeys, {label: "VORP vs waivers by player rank"})
      : null;
    const [lo, hi] = state.window;
    $("v2RangeLabel").textContent = `Ranks ${lo}–${hi} of ${view.rows.length}`;
    const n = Math.max(1, view.rows.length);
    ["v2BrushLo", "v2BrushHi"].forEach(id => { $(id).max = String(n); });
    $("v2BrushLo").value = String(lo);
    $("v2BrushHi").value = String(hi);
    const fill = $("v2BrushFill");
    fill.style.left = `${((lo - 1) / Math.max(1, n - 1)) * 100}%`;
    fill.style.width = `${((hi - lo) / Math.max(1, n - 1)) * 100}%`;
    // Frame 24: numeric bounds and an overview line of the ranking series under the handles.
    ["v2FromRank", "v2ToRank"].forEach(id => { $(id).max = String(n); });
    if (document.activeElement !== $("v2FromRank")) $("v2FromRank").value = String(lo);
    if (document.activeElement !== $("v2ToRank")) $("v2ToRank").value = String(hi);
    drawOverview();
    document.querySelectorAll("#v2Main .v2-seg button[data-window]").forEach(button => {
      button.classList.toggle("is-on", button.dataset.window === state.windowPreset);
    });
    drawHover();
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
  function tableColumns() {
    const valueKeys = view.plotKeys.concat(view.vorpKeys);
    const cols = [
      {id: "rank", label: "#", cls: "rank", get: row => row.rank},
      {id: "name", label: "Player", cls: "player", get: row => row.name, text: true},
      {id: "pos", label: "Pos", cls: "col-meta", get: row => row.pos, text: true},
      {id: "team", label: "Team", cls: "col-meta", get: row => row.team || "FA", text: true},
      {id: "tier", label: "Tier", cls: "col-meta", get: row => tierLabel(row.espnRole), text: true}
    ].filter(col => state.metaCols[col.id] !== false);
    valueKeys.forEach(key => cols.push({id: key, label: sourceLabelFor(key), source: key, cls: "num",
      get: row => row.values[key]}));
    const ddaKeys = view.plotKeys.filter(key => sourceMeta(key).method === "dda");
    if (ddaKeys.length >= 2) {
      cols.push({id: "spread", label: isNarrow() ? "DDA spread" : "Spread of our values", cls: "num", get: row => {
        const values = ddaKeys.map(key => row.values[key]).filter(Number.isFinite);
        return values.length >= 2 ? Math.max(...values) - Math.min(...values) : null;
      }});
    }
    return cols;
  }

  function sortedRows(cols) {
    const rows = view.rows.slice();
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

  function renderTable() {
    const cols = tableColumns();
    const table = $("v2Table");
    table.replaceChildren();
    const thead = document.createElement("thead");
    const hr = document.createElement("tr");
    cols.forEach(col => {
      const th = document.createElement("th");
      th.scope = "col";
      if (col.cls) th.className = col.cls;
      if (col.source === view.rankKey) th.classList.add("is-rank");
      const sortKey = state.sort ? state.sort.key : view.rankKey;
      if (sortKey === col.id) th.setAttribute("aria-sort", state.sort && state.sort.dir === "asc" ? "ascending" : "descending");
      if (col.id === "rank") { th.textContent = col.label; }
      else {
        const button = document.createElement("button");
        button.type = "button";
        if (col.source) {
          const meta = sourceMeta(col.source);
          button.innerHTML = `<span class="v2-sym" style="color:${meta.color}" aria-hidden="true">${meta.symbol}</span> `;
        }
        button.append(document.createTextNode(col.label));
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
    thead.appendChild(hr);
    const tbody = document.createElement("tbody");
    const rows = sortedRows(cols);
    rows.slice(0, state.shown).forEach(row => {
      const tr = document.createElement("tr");
      tr.tabIndex = 0;
      tr.addEventListener("click", () => openDrawer(row));
      tr.addEventListener("keydown", event => { if (event.key === "Enter") openDrawer(row); });
      cols.forEach(col => {
        const td = document.createElement("td");
        if (col.cls) td.className = col.cls;
        if (col.source === view.rankKey) td.classList.add("is-rank");
        const v = col.get(row);
        if (col.cls === "num") {
          if (Number.isFinite(v)) {
            td.textContent = fmt(v);
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
            td.innerHTML = '<span class="missing" title="No value from this source for this player">—</span>';
          }
        } else {
          td.textContent = v;
          if (col.id === "name") {
            appendEspnZero(td, row);
            const sub = document.createElement("span");
            sub.className = "player-sub";
            sub.textContent = `${row.pos} · ${row.team || "FA"} · ${tierLabel(row.espnRole)}`;
            td.appendChild(sub);
          }
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.append(thead, tbody);
    const more = $("v2ShowMore");
    more.hidden = rows.length <= state.shown;
    more.textContent = `Show more players (${Math.min(state.shown, rows.length)} of ${rows.length})`;
    $("v2TableMeta").textContent = `${rows.length} players · ranked by ${sourceMeta(view.rankKey).short}. Every plotted series has a sortable column; the ranking series is highlighted.`;
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

  // ---------- 09 / 20 Choose your sources ----------
  const KIND = {espn: "Projection-based", cbsros: "Projection-based", razzball: "Projection-based"};
  let includeOlder = false;
  function openSources(anchor) {
    const draft = new Set(view.active);
    const publishers = Object.keys(PUBLISHERS).filter(pub => view.info.some(item => sourceMeta(item.key).publisher === pub));
    const staleWeeks = [...new Set(view.info.filter(item => item.stale && item.week).map(item => item.week))];
    openPanel(anchor || $("v2EditSources"), "Choose your sources", "Select the source + method pairs you want to compare.", pop => {
      const body = panelBody(pop);
      const summary = document.createElement("div");
      summary.className = "v2-psummary";
      summary.setAttribute("role", "status");
      body.appendChild(summary);
      const blocks = document.createElement("div");
      body.appendChild(blocks);
      const err = document.createElement("p");
      err.className = "v2-perror";
      err.hidden = true;
      err.textContent = "Choose at least one pair. The last one stays selected.";
      let apply = null;
      function render() {
        blocks.replaceChildren();
        publishers.forEach(pub => {
          const items = view.info.filter(item => sourceMeta(item.key).publisher === pub)
            .sort((a, b) => ["dda", "indexed", "vorp"].indexOf(sourceMeta(a.key).method) - ["dda", "indexed", "vorp"].indexOf(sourceMeta(b.key).method));
          const lead = items.find(item => item.available) || items[0];
          const block = document.createElement("section");
          block.className = "v2-pblock";
          block.dataset.publisher = pub;
          const top = document.createElement("div");
          top.className = "v2-pblock-top";
          const name = document.createElement("h3");
          name.innerHTML = `<span style="color:${pubColor(pub)}" aria-hidden="true">${PUBLISHERS[pub].symbol}</span> `;
          name.append(document.createTextNode(PUBLISHER_NAMES[pub]));
          const kind = document.createElement("span");
          kind.className = "v2-meta";
          kind.textContent = KIND[pub] || "Published trade chart";
          const week = document.createElement("span");
          week.className = `v2-meta v2-pweek${lead?.stale ? " is-older" : ""}`;
          week.textContent = lead?.week ? `Week ${lead.week}${lead.stale ? " · older" : ""}` : "week unknown";
          top.append(name, week, kind);
          const row = document.createElement("div");
          row.className = "v2-ppairs";
          items.forEach(item => {
            const m = sourceMeta(item.key);
            const on = draft.has(item.key);
            const blocked = !item.available || (item.stale && !includeOlder && !on);
            const b = document.createElement("button");
            b.type = "button";
            b.className = `v2-ppair${on ? " is-on" : ""}`;
            b.dataset.series = item.key;
            b.setAttribute("aria-pressed", String(on));
            b.disabled = blocked;
            b.textContent = `${on ? "✓" : "+"} ${PLAIN_METHOD[m.method]}`;
            if (!item.available) b.title = item.paused ? "Waiting on fresh inputs" : "Not available for this league";
            else if (blocked) b.title = "Older week: turn on Include older weeks below";
            b.addEventListener("click", () => {
              if (draft.has(item.key)) draft.delete(item.key);
              else draft.add(item.key);
              err.hidden = true;
              render();
              const again = blocks.querySelector(`[data-series="${item.key}"]`);
              if (again) again.focus();
            });
            row.appendChild(b);
          });
          block.append(top, row);
          const reason = items.find(item => !item.available) ? (lead && !lead.available
            ? (lead.paused ? "Waiting on fresh inputs." : "Not available for this league.") : "") : "";
          const note = withWaiverNote("", lead || {}).replace(/^ · /, "");
          if (reason || note) {
            const why = document.createElement("p");
            why.className = "v2-meta";
            why.textContent = [reason, note].filter(Boolean).join(" ");
            block.appendChild(why);
          }
          blocks.appendChild(block);
        });
        summary.innerHTML = "";
        const count = document.createElement("b");
        count.textContent = `${draft.size} pair${draft.size === 1 ? "" : "s"} selected`;
        const unit = document.createElement("span");
        unit.className = "v2-meta";
        unit.textContent = "Our values and published charts share trade-value points; VORP vs waivers stays in its own panel.";
        summary.append(count, unit);
        if (apply) apply.textContent = `Apply ${draft.size} pair${draft.size === 1 ? "" : "s"}`;
      }
      if (staleWeeks.length) {
        const older = document.createElement("label");
        older.className = "v2-polder";
        const box = document.createElement("input");
        box.type = "checkbox";
        box.checked = includeOlder;
        box.addEventListener("change", () => { includeOlder = box.checked; render(); });
        const text = document.createElement("span");
        text.innerHTML = "<b>Older snapshots are off by default.</b> ";
        text.append(document.createTextNode(`Include Week ${staleWeeks.join(", ")}`));
        older.append(box, text);
        body.appendChild(older);
      }
      const foot = document.createElement("p");
      foot.className = "v2-meta";
      foot.textContent = "Only supported pairs are offered. VORP vs waivers stays in its own panel.";
      body.append(foot, err);
      const row = panelActions(pop, [["Cancel", false, closePopover], ["Apply", true, () => {
        if (!draft.size) { err.hidden = false; return; }
        const adds = [...draft].filter(key => !view.active.includes(key));
        const drops = view.active.filter(key => !draft.has(key));
        adds.forEach(toggleEngineSource);
        drops.forEach(toggleEngineSource);
        closePopover();
        refresh();
      }, {"data-apply": "sources"}]]);
      apply = row.querySelector("[data-apply]");
      render();
    });
  }

  // Frame 18: when a league change makes a selected series unavailable, say which one was dropped.
  let statusTimer = null;
  function leagueChange(apply) {
    const before = C.getActiveSources();
    apply();
    refresh();
    const after = new Set(C.getActiveSources());
    const dropped = before.filter(key => !after.has(key));
    if (!dropped.length) return;
    setStatus(`Removed ${dropped.map(key => sourceMeta(key).short).join(", ")}: not available for this league.`);
    clearTimeout(statusTimer);
    statusTimer = setTimeout(() => setStatus(""), 6000);
  }

  // ---------- 12 Your league ----------
  let leagueDefaults = null;   // the engine's state at first load: what "Reset defaults" returns to
  const ROSTER_SLOTS = [["QB", "QB", 1, 5], ["RB", "RB", 1, 5], ["WR", "WR", 1, 5], ["TE", "TE", 1, 5], ["FLEX", "FLEX", 1, 5], ["BENCH", "Bench slots", 0, 14]];
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
        note.textContent = "Position weights and bench allocation live in Weights & bench. Superflex leagues are not supported yet.";
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
    openPanel($("v2Weights"), "Weights & bench", "Applies across tabs · Same model as the chart dashboard", pop => {
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
      eyebrow(body, "Position shares of total value");
      const shares = document.createElement("p");
      shares.className = "v2-meta";
      shares.textContent = "Shares total 100%. Bench share splits each position. Set by the Data Driven Football model for your league.";
      body.appendChild(shares);
      const weights = C.getPositionWeights();
      ["QB", "RB", "WR", "TE"].forEach(pos => {
        const line = document.createElement("div");
        line.className = "v2-pshare";
        const v = Number(weights[pos]);
        line.innerHTML = `<b>${pos}</b><span class="v2-pshare-bar" aria-hidden="true"><span style="width:${Number.isFinite(v) ? Math.min(100, v * 100) : 0}%"></span></span>`;
        const val = document.createElement("span");
        val.dataset.weight = pos;
        val.textContent = Number.isFinite(v) ? `${(v * 100).toFixed(1)}%` : "—";
        line.appendChild(val);
        body.appendChild(line);
      });
      const reset = document.createElement("button");
      reset.type = "button";
      reset.className = "v2-btn v2-preset";
      reset.textContent = "Reset defaults";
      reset.addEventListener("click", () => { draft = 0.15; slider.value = String(draft); sync(); });
      panelActions(pop, [["Cancel", false, closePopover], ["Apply", true, () => {
        if (bounds) C.setBenchShareFraction(draft);
        closePopover();
        refresh();
      }, {"data-apply": "weights"}]], reset);
    });
  }

  // ---------- 10 Source freshness ----------
  function openFreshness() {
    const fresh = window.TradeValueProductData?.getSourceFreshness?.() || null;
    openPanel($("v2Freshness"), "Source freshness",
      view.refWeek ? `Week ${view.refWeek} board · each source's own week` : "Each source's own week", pop => {
        const body = panelBody(pop);
        const older = view.info.filter(item => item.stale && item.available);
        if (older.length) {
          const banner = document.createElement("div");
          banner.className = "v2-pbanner";
          const b = document.createElement("b");
          const names = [...new Set(older.map(item => `${PUBLISHER_NAMES[sourceMeta(item.key).publisher]} W${item.week}`))];
          b.textContent = `${names.length} source${names.length === 1 ? " is" : "s are"} from an earlier week`;
          const p = document.createElement("span");
          p.textContent = `${names.join(", ")} ${names.length === 1 ? "is" : "are"} left out of first-use selections unless you choose to include ${names.length === 1 ? "it" : "them"}.`;
          banner.append(b, p);
          body.appendChild(banner);
        }
        const table = document.createElement("table");
        table.className = "v2-ptable";
        table.innerHTML = "<thead><tr><th scope=\"col\">Source</th><th scope=\"col\">Snapshot</th><th scope=\"col\">Status</th></tr></thead>";
        const tbody = document.createElement("tbody");
        view.info.forEach(item => {
          const m = sourceMeta(item.key);
          const tr = document.createElement("tr");
          tr.dataset.series = item.key;
          const name = document.createElement("th");
          name.scope = "row";
          name.innerHTML = `<span style="color:${m.color}" aria-hidden="true">${m.symbol}</span> `;
          name.append(document.createTextNode(seriesName(item.key)));
          const prov = document.createElement("span");
          prov.className = "th-sub";
          const row = fresh?.series?.[item.key];
          prov.textContent = withWaiverNote(freshnessText(item), item);
          if (row && (row.published_at || row.fetched_at)) prov.textContent += ` · ${String(row.published_at || row.fetched_at).slice(0, 10)}`;
          name.appendChild(prov);
          const snap = document.createElement("td");
          snap.textContent = item.week ? `Week ${item.week}` : "—";
          const status = document.createElement("td");
          const active = view.active.includes(item.key);
          if (!item.available) {
            status.className = "is-bad";
            status.textContent = item.paused ? "⚠ Unavailable · waiting on fresh inputs" : "— Not available for this league";
          } else if (item.stale) {
            status.className = "is-older";
            status.textContent = active ? "Older · selected " : "Older · not selected";
            if (active) {
              const remove = document.createElement("button");
              remove.type = "button";
              remove.className = "v2-link";
              remove.dataset.removeSeries = item.key;
              remove.textContent = "Remove older source";
              remove.addEventListener("click", () => { toggleEngineSource(item.key); refresh(); openFreshness(); });
              status.appendChild(remove);
            }
          } else {
            status.className = "is-ok";
            status.textContent = active ? "✓ Current · selected" : "Current";
          }
          tr.append(name, snap, status);
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
        manage.textContent = "Manage selected sources";
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
    openPanel($("v2RangeBtn"), "Value range", `Basis ${sourceMeta(key).short}${item?.week ? ` · Week ${item.week}` : ""}`, pop => {
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
        ["Clear range", false, () => { state.range = {min: null, max: null}; closePopover(); refresh(); }],
        ["Apply", true, () => {
          const min = minI.value === "" ? null : Number(minI.value);
          const max = maxI.value === "" ? null : Number(maxI.value);
          if (min !== null && max !== null && min > max) {
            err.textContent = "Minimum is above maximum. Swap them or clear one.";
            err.classList.add("v2-perror");
            return;
          }
          state.range = {min, max};
          state.windowPreset = "100";
          closePopover();
          refresh();
        }, {"data-apply": "range"}]
      ]);
    });
  }

  // ---------- 21 Chart options ----------
  function openChartOptions() {
    const draft = {preset: state.windowPreset, hideZeroTail: state.hideZeroTail, y: state.yBounds ? {...state.yBounds} : null,
      meta: {...state.metaCols}};
    openPanel($("v2ChartOptions"), "Chart options", "Player range, axis and table columns for Player values.", pop => {
      const body = panelBody(pop);
      eyebrow(body, "Player range");
      body.appendChild(segmented("Player range", [["all", "Full"], ["100", "Top 100"], ["50", "Top 50"], ["25", "Top 25"],
        ["starter", "Starter"], ["bench", "Bench"], ["waiver", "Waiver"]], draft.preset, v => { draft.preset = v; }));
      const tail = document.createElement("label");
      tail.className = "v2-check";
      const tailBox = document.createElement("input");
      tailBox.type = "checkbox";
      tailBox.checked = draft.hideZeroTail;
      tailBox.addEventListener("change", () => { draft.hideZeroTail = tailBox.checked; });
      tail.append(tailBox, document.createTextNode(" Hide zero-value tail"));
      body.appendChild(tail);
      eyebrow(body, "Y axis");
      const yRow = document.createElement("div");
      yRow.className = "row2";
      const mk = (text, value) => {
        const label = document.createElement("label");
        label.textContent = text;
        const input = document.createElement("input");
        input.type = "number"; input.step = "1";
        input.value = value === null || value === undefined ? "" : String(value);
        label.appendChild(input);
        yRow.appendChild(label);
        return input;
      };
      body.appendChild(segmented("Y axis", [["auto", "Auto"], ["custom", "Custom bounds"]], draft.y ? "custom" : "auto", v => {
        draft.y = v === "custom" ? (draft.y || {lo: 0, hi: null}) : null;
        yRow.hidden = !draft.y;
      }));
      const yLo = mk("Lower value", draft.y?.lo ?? 0);
      const yHi = mk("Upper value", draft.y?.hi ?? "");
      yRow.hidden = !draft.y;
      body.appendChild(yRow);
      eyebrow(body, "Table metadata");
      [["pos", "Position"], ["team", "Team"], ["tier", "Tier"]].forEach(([id, text]) => {
        const label = document.createElement("label");
        label.className = "v2-check v2-pcheck";
        const box = document.createElement("input");
        box.type = "checkbox";
        box.checked = draft.meta[id];
        box.dataset.meta = id;
        box.addEventListener("change", () => { draft.meta[id] = box.checked; });
        label.append(box, document.createTextNode(` ${text}`));
        body.appendChild(label);
      });
      const notes = document.createElement("p");
      notes.className = "v2-meta";
      notes.textContent = "Presets use the chosen ranking source. Starter / Bench / Waiver use your league's roster boundaries. These options affect this chart and table only; value filters affect the player list.";
      body.appendChild(notes);
      const err = document.createElement("p");
      err.className = "v2-perror";
      err.hidden = true;
      body.appendChild(err);
      panelActions(pop, [["Cancel", false, closePopover], ["Apply chart options", true, () => {
        if (draft.y) {
          const lo = yLo.value === "" ? 0 : Number(yLo.value);
          const hi = yHi.value === "" ? null : Number(yHi.value);
          if (hi !== null && !(hi > lo)) { err.hidden = false; err.textContent = "The upper value must be above the lower value."; return; }
          draft.y = {lo, hi};
        }
        state.windowPreset = draft.preset;
        state.hideZeroTail = draft.hideZeroTail;
        state.yBounds = draft.y;
        state.metaCols = draft.meta;
        closePopover();
        refresh();
      }, {"data-apply": "chart"}]]);
    });
  }

  // ---------- trade targets (frames 03 / 04) ----------
  // Every number here is read from the engine's rows; the one piece of
  // arithmetic (chart value − our value) lives in targets.js.
  const TARGETS_PAGE = 25;
  // ours: which projection-derived series is "our value". Module state, so the
  // choice survives switching tabs like the engine-held selections do.
  const T = {side: "sell", search: "", chart: "all", includeOlder: false, shown: TARGETS_PAGE, ours: "espn"};
  let targetsView = null;

  const fmtGap = gap => {
    if (!Number.isFinite(gap)) return "—";
    const text = Math.abs(gap).toFixed(1);
    if (text === "0.0") return "0.0";
    return `${gap > 0 ? "+" : "−"}${text}`;
  };

  function chartHeading(key) {
    const item = targetsView.infoByKey[key];
    const week = item && item.week ? `Week ${item.week}${item.stale ? " · older" : ""}` : "";
    return {name: PUBLISHER_NAMES[key] || key, week};
  }

  function collectTargets() {
    const TT = window.TradeValueTargets;
    const info = sourceInfoWithFreshness();
    const infoByKey = Object.fromEntries(info.map(item => [item.key, item]));
    const ourKey = TT.OUR_KEYS.includes(T.ours) ? T.ours : TT.OUR_KEY;
    const ours = infoByKey[ourKey];
    const choices = TT.ourChoices(info);
    // The published series are on the trade-value point scale only in the
    // engine's Indexed view; any other view would pair unlike units.
    const engineView = window.TradeValueCurveDiagnostics?.viewMode;
    const {used, skipped} = TT.chartsToCompare(info, {only: T.chart === "all" ? null : T.chart, includeOlder: T.includeOlder});
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
    targetsView = {...result, ours: ourKey, choices, used, skipped, info, infoByKey, blocked, position: C.getState().position};
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
      option.textContent = `${PUBLISHERS[key].symbol} ${PUBLISHER_NAMES[key]}${option.disabled ? " — not available" : item.stale ? ` · Week ${item.week} (older)` : ""}`;
      select.appendChild(option);
    });
    select.value = T.chart;
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
    $("v2TOlder").checked = T.includeOlder;
    $("v2TPosition").value = targetsView.position;
    document.querySelectorAll("#v2Targets [data-side]").forEach(button => {
      const on = button.dataset.side === T.side;
      button.classList.toggle("is-on", on);
      button.setAttribute("aria-pressed", String(on));
    });
    $("v2TCardTitle").textContent = T.side === "sell"
      ? "Sell: the charts pay more than we would"
      : "Buy: the charts pay less than we would";
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

  function renderTargetTable(list) {
    const table = $("v2TTable");
    table.replaceChildren();
    const best = p => (T.side === "sell" ? p.bestSell : p.bestBuy);
    const thead = document.createElement("thead");
    const hr = document.createElement("tr");
    const head = (text, cls, sub, key) => {
      const th = document.createElement("th");
      th.scope = "col";
      if (cls) th.className = cls;
      if (key) {
        const sym = document.createElement("span");
        sym.className = "v2-sym";
        sym.style.color = pubColor(key);
        sym.setAttribute("aria-hidden", "true");
        sym.textContent = `${PUBLISHERS[key].symbol} `;
        th.appendChild(sym);
      }
      th.append(document.createTextNode(text));
      if (sub) {
        const s = document.createElement("span");
        s.className = "th-sub";
        s.textContent = sub;
        th.appendChild(s);
      }
      if (key) th.dataset.chart = key;
      hr.appendChild(th);
    };
    head("Player", "player");
    head("Pos", "col-meta");
    head("Team", "col-meta");
    head("Tier", "col-meta");
    head("Our value", "num is-rank", window.TradeValueTargets.OUR_SHORT[targetsView.ours]);
    targetsView.used.forEach(key => {
      const h = chartHeading(key);
      head(h.name, "num", h.week ? `${h.week} · gap vs ours` : "gap vs ours", key);
    });
    head("Largest gap", "num", T.side === "sell" ? "chart pays more" : "chart pays less");
    thead.appendChild(hr);
    const tbody = document.createElement("tbody");
    list.slice(0, T.shown).forEach(p => {
      const tr = document.createElement("tr");
      tr.tabIndex = 0;
      tr.dataset.playerKey = String(p.row.player_key);
      tr.addEventListener("click", () => openDrawer(p.row));
      tr.addEventListener("keydown", event => { if (event.key === "Enter") openDrawer(p.row); });
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
      td("col-meta", p.row.pos);
      td("col-meta", p.row.team || "FA");
      td("col-meta", tierLabel(p.row.espnRole));
      const ours = td("num is-rank", fmt(p.ours));
      ours.dataset.ours = "";
      targetsView.used.forEach(key => {
        const cell = p.cells[key];
        const c = td("num");
        c.dataset.chart = key;
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
      const b = best(p);
      const bc = td("num best");
      bc.dataset.best = b.chart;
      bc.append(document.createTextNode(fmtGap(b.gap)));
      const who = document.createElement("span");
      who.className = "th-sub";
      who.textContent = PUBLISHER_NAMES[b.chart];
      bc.appendChild(who);
      tbody.appendChild(tr);
    });
    table.append(thead, tbody);
  }

  function renderTargetCards(list) {
    const ol = $("v2TCards");
    ol.replaceChildren();
    const best = p => (T.side === "sell" ? p.bestSell : p.bestBuy);
    list.slice(0, T.shown).forEach(p => {
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
      const b = best(p);
      const big = document.createElement("div");
      big.className = `big ${b.gap > 0 ? "up" : "down"}`;
      big.textContent = fmtGap(b.gap);
      const by = document.createElement("span");
      by.className = "v2-meta";
      by.textContent = `${PUBLISHER_NAMES[b.chart]} pays ${b.gap > 0 ? "more" : "less"}`;
      big.appendChild(by);
      top.append(who, big);
      const line = document.createElement("div");
      line.className = "vals";
      const ours = document.createElement("span");
      ours.className = "ours";
      ours.textContent = `Ours ${fmt(p.ours)}`;
      line.appendChild(ours);
      targetsView.used.forEach(key => {
        const cell = p.cells[key];
        const span = document.createElement("span");
        span.dataset.chart = key;
        span.append(document.createTextNode(`${PUBLISHERS[key].label} `));
        if (cell.value === null) span.appendChild(missingNode(cell.reason, "not on chart"));
        else if (cell.atWaiver) {
          span.append(document.createTextNode(fmt(cell.value)));
          span.appendChild(waiverNode(cell.reason));
        } else {
          span.append(document.createTextNode(fmt(cell.value)));
          span.appendChild(gapNode(cell));
        }
        line.appendChild(span);
      });
      li.append(top, line);
      ol.appendChild(li);
    });
  }

  function renderTargets() {
    collect();
    collectTargets();
    renderHeader();
    renderTargetControls();
    const list = T.side === "sell" ? targetsView.sell : targetsView.buy;
    renderTargetTable(list);
    renderTargetCards(list);
    const empty = $("v2TEmpty");
    const blocked = targetsView.blocked;
    const noCharts = !targetsView.used.length;
    empty.hidden = !(blocked || noCharts || !list.length);
    empty.textContent = blocked || (noCharts
      ? "No published chart is available to compare for this selection."
      : `No player has a ${T.side === "sell" ? "chart paying more" : "chart paying less"} than our value for this selection.`);
    $("v2TTable").hidden = !list.length;
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
    const more = $("v2TShowMore");
    more.hidden = list.length <= T.shown;
    more.textContent = `Show more players (${Math.min(T.shown, list.length)} of ${list.length})`;
    $("v2TOursNote").textContent = window.TradeValueTargets.OUR_NAMES[targetsView.ours];
    $("v2TMeta").textContent = blocked ? "—" : `${list.length} of ${targetsView.compared} players · `
      + `gap = chart value − our value · largest gap first. `
      + (T.side === "sell" ? "Offer these players to managers who trade off that chart." : "Ask for these players from managers who trade off that chart.");
  }

  function bindTargets() {
    let timer = null;
    $("v2TSearch").addEventListener("input", event => {
      clearTimeout(timer);
      timer = setTimeout(() => { T.search = event.target.value; T.shown = TARGETS_PAGE; renderTargets(); }, 120);
    });
    $("v2TPosition").addEventListener("change", event => { C.setPosition(event.target.value); T.shown = TARGETS_PAGE; renderTargets(); });
    $("v2TChart").addEventListener("change", event => { T.chart = event.target.value; T.shown = TARGETS_PAGE; renderTargets(); });
    $("v2TOlder").addEventListener("change", event => { T.includeOlder = event.target.checked; renderTargets(); });
    $("v2TOurs").addEventListener("change", event => { T.ours = event.target.value; T.shown = TARGETS_PAGE; renderTargets(); });
    document.querySelectorAll("#v2Targets [data-side]").forEach(button => {
      button.addEventListener("click", () => { T.side = button.dataset.side; T.shown = TARGETS_PAGE; renderTargets(); });
    });
    $("v2TShowMore").addEventListener("click", () => { T.shown += TARGETS_PAGE; renderTargets(); });
  }

  // ---------- Compare a trade (frames 07 / 08, 24) ----------
  // Each row is one exact series: sum(receive) − sum(give) in that series'
  // values (app/v2/trade.js). No blended score, no overall verdict (frame 22).
  // The sides are v2 module state, so they survive switching tabs.
  const TR = {give: [], receive: [], shown: null, open: new Set()};   // give/receive: [{key, name}]
  let compareView = null;
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
    const giveRows = resolve(TR.give);
    const receiveRows = resolve(TR.receive);
    const ready = giveRows.length > 0 && receiveRows.length > 0;
    const usable = keys => keys.filter(key => view.infoByKey[key]?.available);
    const pointKeys = usable(view.plotKeys);
    const vorpKeys = usable(view.vorpKeys);
    const unavailable = view.active.filter(key => !view.infoByKey[key]?.available);
    // "Player values shown": one exact series, the ranking series unless picked.
    const shownChoices = pointKeys.concat(vorpKeys);
    if (!shownChoices.includes(TR.shown)) TR.shown = shownChoices.includes(view.rankKey) ? view.rankKey : shownChoices[0] || null;
    const TC = window.TradeValueTrade;
    const points = ready ? TC.compareTrade(giveRows, receiveRows, pointKeys).rows : [];
    const metaFor = key => ({...sourceMeta(key), week: view.infoByKey[key]?.week ?? null});
    compareView = {rowsByKey, giveRows, receiveRows, ready, pointKeys, vorpKeys, unavailable, shownChoices,
      points, story: ready ? TC.tradeStory(points, metaFor) : {kind: null},
      totals: TR.shown ? {give: TC.sideTotal(giveRows, TR.shown), receive: TC.sideTotal(receiveRows, TR.shown)} : null,
      vorp: ready ? TC.compareTrade(giveRows, receiveRows, vorpKeys).rows : []};
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

  function renderCompareTable(table, keys, rows) {
    table.replaceChildren();
    const thead = document.createElement("thead");
    const hr = document.createElement("tr");
    [["Source", "player"], ["Give", "num"], ["Receive", "num"], ["Less value · More value", "bar"], ["Receive − give", "num"]].forEach(([text, cls]) => {
      const th = document.createElement("th");
      th.scope = "col";
      th.className = cls;
      th.textContent = text;
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    const tbody = document.createElement("tbody");
    // Frame 24: empty or incomplete rows draw no bar; one scale per table.
    const scale = rows.reduce((max, r) => (r.net === null ? max : Math.max(max, Math.abs(r.net))), 0);
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
        const track = document.createElement("span");
        track.className = "v2-dbar";
        track.setAttribute("aria-hidden", "true");
        const fill = document.createElement("span");
        fill.className = `v2-dbar-fill ${n.cls}`;
        const half = scale > 0 ? Math.min(50, (Math.abs(result.net) / scale) * 50) : 0;
        fill.style.width = `${half}%`;
        fill.style.left = result.net < 0 ? `${50 - half}%` : "50%";
        track.appendChild(fill);
        bar.appendChild(track);
      }
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

  // Frame 22 #15: copy names the publisher, methods and signed nets from data.
  function renderStory() {
    const box = $("v2CStory");
    const s = compareView.story;
    box.hidden = !s.kind || s.kind === "single";
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
      title.textContent = "Every complete source points the same way.";
      text.textContent = s.up ? `All ${s.total} complete sources show you receive more value than you give.`
        : s.down ? `All ${s.total} complete sources show you give more value than you receive.`
          : `All ${s.total} complete sources show the trade as even.`;
    } else if (s.kind === "split") {
      title.textContent = "The sources split.";
      text.textContent = `${s.up} show you receive more, ${s.down} show you give more${s.even ? `, ${s.even} even` : ""}. `
        + "A manager who trades off a source that favors their side is the one most likely to accept.";
    } else {
      title.textContent = "No complete source yet.";
      text.textContent = "Every selected source is missing a value for at least one player, so no row has a result. See each row for who is missing.";
    }
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
    $("v2CEmpty").hidden = ready && compareView.pointKeys.length > 0;
    $("v2CEmpty").textContent = !ready ? "No result until both sides have at least one player."
      : "No trade-value source is selected. Use Edit sources to pick one.";
    const table = $("v2CTable");
    table.hidden = !ready || !compareView.pointKeys.length;
    renderCompareTable(table, compareView.pointKeys, compareView.points);
    $("v2CVorpCard").hidden = !ready || !compareView.vorpKeys.length;
    renderCompareTable($("v2CVorpTable"), compareView.vorpKeys, compareView.vorp);
    renderStory();
    const notes = [];
    if (compareView.unavailable.length) {
      notes.push(`Not compared: ${compareView.unavailable.map(key => sourceMeta(key).short).join(", ")}, not available for this league.`);
    }
    const note = $("v2CNote");
    note.hidden = !notes.length;
    note.textContent = notes.join(" ");
    const count = compareView.giveRows.length + compareView.receiveRows.length;
    $("v2CMeta").textContent = ready
      ? `Receive − give · ${compareView.pointKeys.length} source${compareView.pointKeys.length === 1 ? "" : "s"} · trade-value points, not a blended verdict.`
      : "Receive − give, one row per source, once both sides have a player.";
    $("v2CClear").hidden = !count;
    $("v2CSwap").hidden = !count;
    $("v2CShare").hidden = !ready;
    if (!ready) $("v2CShareNote").hidden = true;
    syncTradeHash();
  }

  // Shareable trade: the sides live in the hash, so a copied link opens the same trade.
  function tradeHash() {
    const keys = side => TR[side].map(p => encodeURIComponent(p.key)).join(",");
    const parts = [];
    if (TR.give.length) parts.push(`give=${keys("give")}`);
    if (TR.receive.length) parts.push(`get=${keys("receive")}`);
    return `#compare-trade${parts.length ? `?${parts.join("&")}` : ""}`;
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
      note.textContent = "✓ Link copied. Anyone who opens it sees this trade, priced for their own league settings.";
    } catch (error) {
      note.textContent = `Copy this link: ${url}`;
    }
  }

  function bindCompare() {
    $("v2CShare").addEventListener("click", copyTradeLink);
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
    renderCharts();
    renderTable();
  }

  // Frame 18: filters that leave no player say which filter did it.
  function renderEmpty() {
    const empty = !view.rows.length;
    $("v2Empty").hidden = !empty;
    $("v2Chart").hidden = empty;
    document.querySelector("#v2Main .v2-brush").hidden = empty;
    document.querySelector("#v2Main .v2-table-card").hidden = empty;
    if (!empty) return;
    const why = [];
    if (state.search.trim()) why.push(`no player name contains “${state.search.trim()}”`);
    if (state.range.min !== null || state.range.max !== null) {
      why.push(`no ${sourceMeta(view.rankKey).short} value is in ${state.range.min ?? "…"}–${state.range.max ?? "…"}`);
    }
    if (view.state.position !== "ALL") why.push(`the position filter is ${view.state.position}`);
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

  function bind() {
    let searchTimer = null;
    $("v2Search").addEventListener("input", event => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => { state.search = event.target.value; state.shown = PAGE_SIZE; refresh(); }, 120);
    });
    $("v2Position").addEventListener("change", event => { C.setPosition(event.target.value); state.windowPreset = "100"; refresh(); });
    $("v2RankBy").addEventListener("change", event => { C.setLockOrder(event.target.value); state.sort = null; refresh(); });
    $("v2DeltaBtn").addEventListener("click", () => {
      state.delta = !state.delta;
      refresh();
      if (state.delta) priorsFor(view.plotKeys.concat(view.vorpKeys)).then(() => { if (state.delta) refresh(); });
    });
    $("v2RangeBtn").addEventListener("click", openRange);
    $("v2EmptyClear").addEventListener("click", () => $("v2ClearFilters").click());
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
    $("v2ClearFilters").addEventListener("click", () => {
      state.search = ""; $("v2Search").value = "";
      state.range = {min: null, max: null};
      state.sort = null; state.windowPreset = "100"; state.shown = PAGE_SIZE;
      if (view.state.position !== "ALL") C.setPosition("ALL");
      refresh();
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
    document.querySelectorAll(".v2-seg button[data-window]").forEach(button => {
      button.addEventListener("click", () => { state.windowPreset = button.dataset.window; refresh(); });
    });
    const onBrush = () => {
      let lo = Number($("v2BrushLo").value);
      let hi = Number($("v2BrushHi").value);
      if (lo > hi) [lo, hi] = [hi, lo];
      state.window = [lo, hi];
      state.windowPreset = "custom";
      renderCharts();
    };
    $("v2BrushLo").addEventListener("input", onBrush);
    $("v2BrushHi").addEventListener("input", onBrush);
    const zoom = factor => {
      const n = view.rows.length;
      const [lo, hi] = state.window;
      const center = state.hoverIndex !== null ? lo + state.hoverIndex : (lo + hi) / 2;
      const span = Math.max(5, Math.min(n, Math.round((hi - lo + 1) * factor)));
      let nlo = Math.round(center - span / 2);
      nlo = Math.max(1, Math.min(n - span + 1, nlo));
      state.window = [nlo, Math.min(n, nlo + span - 1)];
      state.windowPreset = "custom";
      renderCharts();
    };
    $("v2ZoomIn").addEventListener("click", () => zoom(0.5));
    $("v2ZoomOut").addEventListener("click", () => zoom(2));
    $("v2ZoomReset").addEventListener("click", () => { state.windowPreset = "100"; refresh(); });
    $("v2ResetAll").addEventListener("click", () => { state.windowPreset = "all"; refresh(); });
    const onBounds = () => {
      const n = view.rows.length;
      let lo = Math.round(Number($("v2FromRank").value));
      let hi = Math.round(Number($("v2ToRank").value));
      if (!Number.isFinite(lo) || !Number.isFinite(hi)) return;
      lo = Math.max(1, Math.min(n, lo));
      hi = Math.max(1, Math.min(n, hi));
      if (lo > hi) [lo, hi] = [hi, lo];
      state.window = [lo, hi];
      state.windowPreset = "custom";
      renderCharts();
    };
    $("v2FromRank").addEventListener("change", onBounds);
    $("v2ToRank").addEventListener("change", onBounds);
    $("v2ChartOptions").addEventListener("click", openChartOptions);
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
    bind();
    readTradeHash();
    $("v2State").hidden = true;
    applyRoute();
    setStatus("");
    window.TradeValueV2 = {state, view: () => view, targets: () => targetsView, targetState: T,
      compare: () => compareView, tradeState: TR,
      risers: () => risersView, risersState: R, priors: () => Object.fromEntries(priorCache)};
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
