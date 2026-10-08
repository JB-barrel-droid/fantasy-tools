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
  const PUBLISHER_NAMES = {
    espn: "ESPN", fantasycalc: "FantasyCalc", fantasypros: "FantasyPros", usatoday: "USA Today",
    cbs: "CBS Sports", cbsros: "CBS ROS projections", razzball: "Razzball projections"
  };
  const METHOD_LABEL = {dda: "DDA", indexed: "Index", vorp: "VORP vs waivers"};

  function sourceMeta(key) {
    let method;
    let publisher;
    if (key.endsWith("_vorp")) { method = "vorp"; publisher = key.slice(0, -5); }
    else if (key.endsWith("_adjusted")) { method = "dda"; publisher = key.slice(0, -9); }
    else if (key === "espn" || key === "cbsros" || key === "razzball") { method = "dda"; publisher = key; }
    else { method = "indexed"; publisher = key; }
    const pub = PUBLISHERS[publisher] || {label: key, color: "#64736F", symbol: "•"};
    return {key, method, publisher, ...pub, short: `${pub.label} · ${METHOD_LABEL[method]}`};
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
    focusIndex: 0
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
    if (!state.window || state.windowPreset !== "custom") {
      const hi = state.windowPreset === "all" ? n : Number(state.windowPreset) || n;
      state.window = [1, Math.max(1, Math.min(n, hi))];
    } else {
      state.window = [Math.max(1, Math.min(state.window[0], n)), Math.max(1, Math.min(state.window[1], n))];
    }
  }

  // GAP-043: the same per-source freshness wording the main page uses.
  function freshnessText(item) {
    const pd = window.TradeValueProductData;
    const row = pd?.getSourceFreshness?.()?.series?.[item.key];
    if (row && pd.freshnessLabel) return pd.freshnessLabel(row).text;
    return item.week ? `Week ${item.week}${item.stale ? " · older week" : ""}` : "content week unknown";
  }

  function sourceLabelFor(key) {
    const meta = sourceMeta(key);
    const item = view.infoByKey[key];
    const week = item && item.week ? ` · W${item.week}` : "";
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
    $("v2FreshnessLabel").textContent = view.refWeek ? `W${view.refWeek} · Freshness ↗` : "Freshness ↗";
    $("v2Freshness").classList.toggle("is-older", older);

    const methods = $("v2MethodChips");
    methods.replaceChildren();
    [["dda", "DDA"], ["indexed", "Indexed"], ["vorp", "VORP vs waivers"]].forEach(([method, label]) => {
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
    if (rangeOn && view.omittedMissing) {
      note.hidden = false;
      note.textContent = `${view.omittedMissing} player${view.omittedMissing === 1 ? "" : "s"} omitted: no ${sourceMeta(view.rankKey).short} value to compare against the range.`;
    } else {
      note.hidden = true;
    }
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
    const {max: ymax, step: ystep} = niceScale(vmax);
    const x = i => pad.l + (n <= 1 ? (width - pad.l - pad.r) / 2 : (i / (n - 1)) * (width - pad.l - pad.r));
    const y = v => pad.t + (1 - v / ymax) * (height - pad.t - pad.b);
    const grid = el("g", {class: "grid"}, svg);
    const axis = el("g", {class: "axis"}, svg);
    for (let v = 0; v <= ymax + 1e-9; v += ystep) {
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
    mainChart = drawSeriesChart($("v2Chart"), view.plotKeys, {label: "Trade value by player rank", names: true});
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
    document.querySelectorAll(".v2-seg button").forEach(button => {
      button.classList.toggle("is-on", button.dataset.window === state.windowPreset);
    });
    drawHover();
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

  function deltaText() {
    return "Δ —";
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
      val.textContent = Number.isFinite(v) ? fmt(v) + (state.delta ? `  ${deltaText()}` : "") : "—";
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
    ];
    valueKeys.forEach(key => cols.push({id: key, label: sourceLabelFor(key), source: key, cls: "num",
      get: row => row.values[key]}));
    const ddaKeys = view.plotKeys.filter(key => sourceMeta(key).method === "dda");
    if (ddaKeys.length >= 2) {
      cols.push({id: "spread", label: "DDA spread", cls: "num", get: row => {
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
              const d = document.createElement("span");
              d.className = "delta";
              d.textContent = deltaText();
              d.title = "No prior-week snapshot is saved for this source yet, so there is nothing to compare. Shown as —, never zero.";
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

  // ---------- drawer (frame 13 / 14) ----------
  let lastFocus = null;
  function openDrawer(row) {
    lastFocus = document.activeElement;
    const drawer = $("v2Drawer");
    drawer.replaceChildren();
    const close = document.createElement("button");
    close.type = "button";
    close.className = "v2-btn close";
    close.textContent = "Close";
    close.addEventListener("click", closeDrawer);
    const title = document.createElement("h2");
    title.id = "v2DrawerTitle";
    title.textContent = row.name;
    const meta = document.createElement("p");
    meta.className = "v2-meta";
    meta.textContent = `#${row.rank} by ${sourceMeta(view.rankKey).short} · ${row.pos} · ${row.team || "FA"} · ${tierLabel(row.espnRole)}`;
    const zeroBadge = espnZeroBadge(row);
    let zeroNote = null;
    if (zeroBadge) {
      zeroNote = document.createElement("p");
      zeroNote.className = "v2-espn-zero-note";
      zeroNote.append(zeroBadge, document.createTextNode(` ${zeroBadge.title}`));
      zeroBadge.removeAttribute("title");
    }
    const dl = document.createElement("dl");
    const methodRank = {dda: 0, indexed: 1, vorp: 2};
    view.info.filter(item => item.available)
      .sort((a, b) => methodRank[sourceMeta(a.key).method] - methodRank[sourceMeta(b.key).method])
      .forEach(item => {
      const m = sourceMeta(item.key);
      const dt = document.createElement("dt");
      dt.innerHTML = `<span style="color:${m.color}" aria-hidden="true">${m.symbol}</span>`;
      dt.append(document.createTextNode(`${PUBLISHER_NAMES[m.publisher] || m.label} · ${METHOD_LABEL[m.method]}${item.week ? ` · W${item.week}` : ""}${view.active.includes(item.key) ? "" : " (not plotted)"}`));
      const dd = document.createElement("dd");
      const v = row.values[item.key];
      if (Number.isFinite(v)) dd.textContent = fmt(v);
      else dd.innerHTML = '<span class="missing">— not priced</span>';
      dl.append(dt, dd);
    });
    const note = document.createElement("p");
    note.className = "v2-note";
    note.textContent = "DDA and Index values share the trade-value point scale for your league. VORP vs waivers is its own unit and is not comparable to them.";
    drawer.append(close, title, meta);
    if (zeroNote) drawer.appendChild(zeroNote);
    drawer.append(dl, note);
    $("v2Scrim").hidden = false;
    drawer.hidden = false;
    close.focus();
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
    if (popoverAnchor && popoverAnchor.focus) popoverAnchor.focus();
    popoverAnchor = null;
  }
  function heading(pop, text, sub) {
    const h = document.createElement("h2");
    h.textContent = text;
    pop.appendChild(h);
    if (sub) {
      const p = document.createElement("p");
      p.className = "v2-meta";
      p.textContent = sub;
      pop.appendChild(p);
    }
  }
  function actions(pop, buttons) {
    const row = document.createElement("div");
    row.className = "actions";
    buttons.forEach(([label, primary, fn]) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = `v2-btn${primary ? " v2-btn-primary" : ""}`;
      b.textContent = label;
      b.addEventListener("click", fn);
      row.appendChild(b);
    });
    pop.appendChild(row);
  }

  function toggleEngineSource(key) {
    const input = document.querySelector(`#legacyEngine #sourceToggles input[data-source="${key}"]`);
    if (!input || input.disabled) return false;
    input.click();
    return true;
  }

  function openSources(anchor, focusMethod) {
    openPopover(anchor || $("v2EditSources"), pop => {
      heading(pop, "Sources", "Pick the series to compare. Selection applies across tabs.");
      [["dda", "Data Driven Adjustments (DDA)"], ["indexed", "Indexed trade charts"], ["vorp", "VORP vs waivers"]].forEach(([method, title]) => {
        const group = document.createElement("div");
        group.className = "group";
        const h = document.createElement("h3");
        h.textContent = title;
        group.appendChild(h);
        view.info.filter(item => sourceMeta(item.key).method === method).forEach(item => {
          const m = sourceMeta(item.key);
          const label = document.createElement("label");
          label.className = `opt${item.available ? "" : " is-disabled"}`;
          const box = document.createElement("input");
          box.type = "checkbox";
          box.checked = view.active.includes(item.key);
          box.disabled = !item.available;
          box.addEventListener("change", () => {
            if (!toggleEngineSource(item.key)) { box.checked = !box.checked; return; }
            refresh();
            // The engine keeps at least one series on; reflect what it decided.
            box.checked = view.active.includes(item.key);
          });
          const name = document.createElement("span");
          name.innerHTML = `<span style="color:${m.color}" aria-hidden="true">${m.symbol}</span> `;
          name.append(document.createTextNode(`${PUBLISHER_NAMES[m.publisher] || m.label}`));
          const reason = document.createElement("span");
          reason.className = `reason${item.stale ? " is-older" : ""}`;
          reason.textContent = !item.available
            ? (item.paused ? "— waiting on fresh inputs" : "— not available for this league")
            : freshnessText(item);
          label.append(box, name, reason);
          group.appendChild(label);
        });
        pop.appendChild(group);
        if (focusMethod === method) setTimeout(() => group.scrollIntoView({block: "nearest"}), 0);
      });
      actions(pop, [["Done", true, closePopover]]);
    });
  }

  function openLeague() {
    openPopover($("v2EditLeague"), pop => {
      heading(pop, "League settings", "Values recompute for your scoring, league size and roster.");
      const s = view.state;
      const row = document.createElement("div");
      row.className = "row2";
      const scoring = document.createElement("label");
      scoring.textContent = "Scoring";
      const sSel = document.createElement("select");
      [["standard", "Standard"], ["half_ppr", "Half PPR"], ["ppr", "Full PPR"]].forEach(([v, t]) => {
        const o = document.createElement("option"); o.value = v; o.textContent = t; o.selected = v === s.scoring; sSel.appendChild(o);
      });
      sSel.addEventListener("change", () => { C.setScoring(sSel.value); refresh(); });
      scoring.appendChild(sSel);
      const teams = document.createElement("label");
      teams.textContent = "Teams";
      const tSel = document.createElement("select");
      [8, 10, 12, 14].forEach(v => {
        const o = document.createElement("option"); o.value = String(v); o.textContent = `${v} teams`; o.selected = v === s.teams; tSel.appendChild(o);
      });
      tSel.addEventListener("change", () => { C.setTeams(Number(tSel.value)); refresh(); });
      teams.appendChild(tSel);
      row.append(scoring, teams);
      pop.appendChild(row);
      const roster = document.createElement("div");
      roster.className = "row2";
      roster.style.flexWrap = "wrap";
      const shape = C.getRosterShape();
      [["QB", "QB", 1, 5], ["RB", "RB", 1, 5], ["WR", "WR", 1, 5], ["TE", "TE", 1, 5], ["FLEX", "FLEX", 1, 5], ["BENCH", "Bench", 0, 14]].forEach(([key, text, min, max]) => {
        const label = document.createElement("label");
        label.style.flex = "1 1 30%";
        label.textContent = text;
        const input = document.createElement("input");
        input.type = "number"; input.min = String(min); input.max = String(max); input.step = "1";
        input.value = String(shape[key]);
        input.addEventListener("change", () => { C.setRosterSpot(key, input.value); refresh(); input.value = String(C.getRosterShape()[key]); });
        label.appendChild(input);
        roster.appendChild(label);
      });
      pop.appendChild(roster);
      actions(pop, [["Done", true, closePopover]]);
    });
  }

  function openWeights() {
    openPopover($("v2Weights"), pop => {
      heading(pop, "Weights & bench", "How the league's value is split by position, and how much goes to bench players.");
      const weights = C.getPositionWeights();
      const grid = document.createElement("div");
      grid.className = "weights";
      ["QB", "RB", "WR", "TE"].forEach(pos => {
        const cell = document.createElement("div");
        cell.innerHTML = `<span class="v2-meta">${pos}</span><b>${(Number(weights[pos]) * 100).toFixed(1)}%</b>`;
        grid.appendChild(cell);
      });
      pop.appendChild(grid);
      const bounds = C.getBenchBounds();
      const share = C.getBenchShare();
      const label = document.createElement("label");
      label.className = "v2-meta";
      label.style.display = "block";
      label.style.marginTop = "14px";
      const readout = document.createElement("b");
      readout.textContent = `Bench allocation ${(share * 100).toFixed(1)}%`;
      label.appendChild(readout);
      const slider = document.createElement("input");
      slider.type = "range";
      if (bounds) {
        slider.min = String(bounds[0]); slider.max = String(bounds[1]); slider.step = "0.005"; slider.value = String(share);
      } else {
        slider.disabled = true;
      }
      slider.setAttribute("aria-label", "Bench allocation");
      slider.addEventListener("change", () => {
        C.setBenchShareFraction(Number(slider.value));
        const now = C.getBenchShare();
        slider.value = String(now);
        readout.textContent = `Bench allocation ${(now * 100).toFixed(1)}%`;
        refresh();
      });
      slider.addEventListener("input", () => { readout.textContent = `Bench allocation ${(Number(slider.value) * 100).toFixed(1)}%`; });
      label.appendChild(slider);
      pop.appendChild(label);
      const note = document.createElement("p");
      note.className = "v2-meta";
      note.textContent = bounds
        ? `Allowed range ${(bounds[0] * 100).toFixed(1)}–${(bounds[1] * 100).toFixed(1)}% for this league; 15% is the recommended default.`
        : "Bench allocation is unavailable for this league setup.";
      pop.appendChild(note);
      actions(pop, [["Reset to 15%", false, () => { C.setBenchShareFraction(0.15); refresh(); openWeights(); }], ["Done", true, closePopover]]);
    });
  }

  function openFreshness() {
    openPopover($("v2Freshness"), pop => {
      heading(pop, "Freshness", view.refWeek ? `Board week: Week ${view.refWeek}. Older weeks stay available and are marked.` : "Source weeks");
      const group = document.createElement("div");
      group.className = "group";
      view.info.filter(item => item.available).forEach(item => {
        const m = sourceMeta(item.key);
        const line = document.createElement("label");
        line.className = "opt";
        line.style.cursor = "default";
        line.innerHTML = `<span style="color:${m.color}" aria-hidden="true">${m.symbol}</span>`;
        line.append(document.createTextNode(` ${PUBLISHER_NAMES[m.publisher] || m.label} · ${METHOD_LABEL[m.method]}`));
        const reason = document.createElement("span");
        reason.className = `reason${item.stale ? " is-older" : ""}`;
        reason.textContent = freshnessText(item);
        line.appendChild(reason);
        group.appendChild(line);
      });
      pop.appendChild(group);
      actions(pop, [["Done", true, closePopover]]);
    });
  }

  function openRange() {
    openPopover($("v2RangeBtn"), pop => {
      heading(pop, "Value range", `Measured against one exact series: ${sourceMeta(view.rankKey).short}. Blank = open ended.`);
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
      pop.appendChild(row);
      const err = document.createElement("p");
      err.className = "v2-meta";
      err.style.marginTop = "8px";
      err.textContent = "Inclusive. Players without a value in this series are left out and counted.";
      pop.appendChild(err);
      actions(pop, [
        ["Clear", false, () => { state.range = {min: null, max: null}; closePopover(); refresh(); }],
        ["Show matching players", true, () => {
          const min = minI.value === "" ? null : Number(minI.value);
          const max = maxI.value === "" ? null : Number(maxI.value);
          if (min !== null && max !== null && min > max) {
            err.textContent = "Minimum is above maximum. Swap them or clear one.";
            err.style.color = "var(--v2-negative)";
            return;
          }
          state.range = {min, max};
          state.windowPreset = "100";
          closePopover();
          refresh();
        }]
      ]);
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
        sym.style.color = PUBLISHERS[key].color;
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

  // ---------- Compare a trade (frames 07 / 08) ----------
  // Each row is one exact series: sum(receive) − sum(give) in that series'
  // values (app/v2/trade.js). No blended score, no overall verdict (frame 22).
  // The sides are v2 module state, so they survive switching tabs.
  const TR = {give: [], receive: []};   // [{key, name}]
  let compareView = null;
  const SIDE_IDS = {give: {search: "v2GiveSearch", results: "v2GiveResults", list: "v2GivePlayers"},
    receive: {search: "v2GetSearch", results: "v2GetResults", list: "v2GetPlayers"}};

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
    const TC = window.TradeValueTrade;
    compareView = {rowsByKey, giveRows, receiveRows, ready, pointKeys, vorpKeys, unavailable,
      points: ready ? TC.compareTrade(giveRows, receiveRows, pointKeys).rows : [],
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
    td.append(document.createTextNode(`${PUBLISHER_NAMES[meta.publisher] || meta.label} · ${METHOD_LABEL[meta.method]}`));
    const sub = document.createElement("span");
    sub.className = "th-sub";
    sub.textContent = item?.week ? `Week ${item.week}${item.stale ? " · older week" : ""}` : "week unknown";
    td.appendChild(sub);
  }

  function netLabel(net) {
    const text = fmtGap(net);
    if (text === "0.0") return {text, cls: "", label: "= even by this source"};
    return net > 0 ? {text, cls: "up", label: "▲ you get more by this source"}
      : {text, cls: "down", label: "▼ you give more by this source"};
  }

  function renderCompareTable(table, keys, rows) {
    table.replaceChildren();
    const thead = document.createElement("thead");
    const hr = document.createElement("tr");
    [["Source", "player"], ["You give", "num"], ["You get", "num"], ["Get − give", "num"]].forEach(([text, cls]) => {
      const th = document.createElement("th");
      th.scope = "col";
      th.className = cls;
      th.textContent = text;
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    const tbody = document.createElement("tbody");
    rows.forEach(result => {
      const tr = document.createElement("tr");
      tr.dataset.source = result.key;
      if (result.key === view.rankKey) tr.className = "is-rank";
      const source = document.createElement("td");
      source.className = "player";
      sourceCell(source, result.key);
      tr.appendChild(source);
      const cell = (label, name) => {
        const td = document.createElement("td");
        td.className = "num";
        td.dataset.label = label;
        td.dataset.col = name;
        tr.appendChild(td);
        return td;
      };
      const give = cell("You give", "give");
      const get = cell("You get", "receive");
      const net = cell("Get − give", "net");
      if (result.net === null) {
        const names = result.missing.map(m => m.row.name || "a player");
        const meta = sourceMeta(result.key);
        const reason = `No ${PUBLISHER_NAMES[meta.publisher] || meta.label} · ${METHOD_LABEL[meta.method]} value for ${names.join(", ")}`;
        [give, get].forEach(td => {
          const dash = document.createElement("span");
          dash.className = "missing";
          dash.title = reason;
          dash.textContent = "—";
          td.appendChild(dash);
        });
        net.appendChild(missingNode(reason));
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
      tbody.appendChild(tr);
    });
    table.append(thead, tbody);
  }

  function renderSidePlayers(side) {
    const list = $(SIDE_IDS[side].list);
    list.replaceChildren();
    const rows = side === "give" ? compareView.giveRows : compareView.receiveRows;
    rows.forEach(row => {
      const li = document.createElement("li");
      li.dataset.playerKey = String(row.player_key);
      const who = document.createElement("div");
      const name = document.createElement("b");
      name.textContent = row.name;
      appendEspnZero(name, row);
      const sub = document.createElement("span");
      sub.className = "v2-meta";
      sub.textContent = row.unpriced ? "No value in any source for this league"
        : `${row.pos} · ${row.team || "FA"} · ${tierLabel(row.espnRole)}`;
      who.append(name, sub);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "v2-link";
      remove.textContent = "Remove ✕";
      remove.setAttribute("aria-label", `Remove ${row.name}`);
      remove.addEventListener("click", () => {
        TR[side] = TR[side].filter(p => p.key !== String(row.player_key));
        renderCompare();
        $(SIDE_IDS[side].search).focus();
      });
      li.append(who, remove);
      list.appendChild(li);
    });
    if (!rows.length) {
      const li = document.createElement("li");
      li.className = "v2-meta is-empty";
      li.textContent = "No players yet.";
      list.appendChild(li);
    }
  }

  function searchMatches(needle) {
    const chosen = new Set(TR.give.concat(TR.receive).map(p => p.key));
    const rankKey = view.rankKey;
    const value = row => (Number.isFinite(row.values[rankKey]) ? row.values[rankKey] : -Infinity);
    return [...compareView.rowsByKey.values()]
      .filter(row => !chosen.has(String(row.player_key)) && String(row.name || "").toLowerCase().includes(needle))
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

  function renderSearch(side) {
    const input = $(SIDE_IDS[side].search);
    const results = $(SIDE_IDS[side].results);
    const needle = input.value.trim().toLowerCase();
    results.replaceChildren();
    if (!needle || !compareView) { results.hidden = true; return []; }
    const matches = searchMatches(needle);
    matches.forEach(row => {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.playerKey = String(row.player_key);
      const name = document.createElement("b");
      name.textContent = row.name;
      const sub = document.createElement("span");
      sub.className = "v2-meta";
      sub.textContent = ` ${row.pos} · ${row.team || "FA"}`;
      button.append(name, sub);
      button.addEventListener("click", () => addToSide(side, row));
      li.appendChild(button);
      results.appendChild(li);
    });
    if (!matches.length) {
      const li = document.createElement("li");
      li.className = "v2-meta is-empty";
      li.textContent = "No player matches.";
      results.appendChild(li);
    }
    results.hidden = false;
    return matches;
  }

  function renderCompare() {
    collect();
    collectCompare();
    renderHeader();
    renderSidePlayers("give");
    renderSidePlayers("receive");
    const ready = compareView.ready;
    $("v2CEmpty").hidden = ready && compareView.pointKeys.length > 0;
    $("v2CEmpty").textContent = !ready ? "Add at least one player to each side."
      : "No trade-value source is selected. Use Edit sources to pick one.";
    const table = $("v2CTable");
    table.hidden = !ready || !compareView.pointKeys.length;
    renderCompareTable(table, compareView.pointKeys, compareView.points);
    $("v2CVorpCard").hidden = !ready || !compareView.vorpKeys.length;
    renderCompareTable($("v2CVorpTable"), compareView.vorpKeys, compareView.vorp);
    const notes = [];
    if (compareView.unavailable.length) {
      notes.push(`Not compared: ${compareView.unavailable.map(key => sourceMeta(key).short).join(", ")}, not available for this league.`);
    }
    const note = $("v2CNote");
    note.hidden = !notes.length;
    note.textContent = notes.join(" ");
    const count = compareView.giveRows.length + compareView.receiveRows.length;
    $("v2CMeta").textContent = ready
      ? `${count} player${count === 1 ? "" : "s"} · ${compareView.pointKeys.length} source${compareView.pointKeys.length === 1 ? "" : "s"} · `
        + "each row is that source's values only. Positive means you get more value than you give by that source."
      : "Pick the players on both sides to see each source's numbers.";
    $("v2CClear").hidden = !count;
  }

  function bindCompare() {
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
    $("v2CClear").addEventListener("click", () => { TR.give = []; TR.receive = []; renderCompare(); });
  }

  // ---------- routing ----------
  const currentView = () => (location.hash === "#trade-targets" ? "targets"
    : location.hash === "#compare-trade" ? "compare" : "values");

  function applyRoute() {
    const v = currentView();
    $("v2Main").hidden = v !== "values";
    $("v2Targets").hidden = v !== "targets";
    $("v2Compare").hidden = v !== "compare";
    // The source selection applies on Compare a trade too; Trade targets has its own pickers.
    $("v2Methods").hidden = v === "targets";
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
    renderCharts();
    renderTable();
  }

  // Settings popovers and shared-state changes call this; it redraws whichever tab is showing.
  function refresh() {
    if (currentView() === "targets") renderTargets();
    else if (currentView() === "compare") renderCompare();
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
    $("v2DeltaBtn").addEventListener("click", () => { state.delta = !state.delta; refresh(); });
    $("v2RangeBtn").addEventListener("click", openRange);
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
    $("v2ShowMore").addEventListener("click", () => { state.shown += PAGE_SIZE; renderTable(); });
    document.querySelectorAll(".v2-seg button").forEach(button => {
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
    bindChart("v2Chart", () => mainChart);
    bindChart("v2VorpChart", () => vorpChart);
    bindChartKeys();
    $("v2Scrim").addEventListener("click", closeDrawer);
    document.addEventListener("keydown", event => {
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
    window.addEventListener("hashchange", applyRoute);
    bindTargets();
    bindCompare();
    window.addEventListener("trade-value-shared-change", () => { if (C) refresh(); });
  }

  async function start() {
    document.body.classList.add("v2");
    try {
      C = await waitForEngine();
    } catch (error) {
      setStatus(`Values unavailable: ${error.message}`, true);
      $("v2Main").setAttribute("aria-busy", "false");
      return;
    }
    bind();
    applyRoute();
    setStatus("");
    window.TradeValueV2 = {state, view: () => view, targets: () => targetsView, targetState: T,
      compare: () => compareView, tradeState: TR};
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
