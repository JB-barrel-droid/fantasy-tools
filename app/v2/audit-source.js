/* Values auditing > Single-source build-up view (JEG-849, parent JEG-847).
 *
 * Trade charts: Published, Indexed, Adjusted. Projections: points per game
 * through the league model to the displayed published (Adjusted) value.
 * A curve chart, worked projection player and table, laid out like Player values.
 * Reads the engine's own pipeline output
 * (TradeValueCurveControls.getInspection(), the runValuePipeline result);
 * it does no value math. Missing values stay missing (null), never zero.
 *
 * Registers with the Values auditing shell:
 *   window.DDFAudit.register("single-source", (root, ctx) => ...)
 * and re-renders on every call and on the engine's rows-change event, so it
 * follows the page's current league settings. It never touches the engine's
 * source selection (no applyShown); its source/position choice is page-local.
 *
 * Pure part: build(inspection, source, position) -> model. Exposed as
 * window.DDFAuditSource.build so tests can tie it to the engine output.
 */
(function (root) {
  "use strict";

  // Four trade charts first, then the projections (the shell's order of sources).
  const SOURCES = [
    {key: "fantasycalc", label: "FantasyCalc", family: "chart"},
    {key: "usatoday", label: "USA Today", family: "chart"},
    {key: "fantasypros", label: "FantasyPros", family: "chart"},
    {key: "cbs", label: "CBS Sports", family: "chart"},
    {key: "espn", label: "ESPN", family: "projection"},
    {key: "cbsros", label: "CBS rest of season", family: "projection"},
    {key: "razzball", label: "Razzball", family: "projection"}
  ];
  const POSITIONS = ["ALL", "QB", "RB", "WR", "TE"];
  const STAGES = ["published", "indexed", "adjusted"];
  const STAGE_LABEL = {published: "Published", indexed: "Indexed", adjusted: "Adjusted"};
  const stageLabel = (model, stage) => model.family === "projection"
    ? ({published: "Projected points/game", indexed: "Indexed", adjusted: "Published value"})[stage]
    : STAGE_LABEL[stage];
  const ROLE_LABEL = {starter: "Starter", bench: "Bench", waiver: "Waiver"};
  const PAGE = 50;

  const finite = v => (typeof v === "number" && Number.isFinite(v) ? v : null);

  // ---- pure model -------------------------------------------------------
  function build(inspection, sourceKey, position) {
    const meta = SOURCES.find(s => s.key === sourceKey) || SOURCES[0];
    const isChart = meta.family === "chart";
    const players = (inspection && inspection.players && inspection.players[meta.key]) || {};
    const rows = (inspection && inspection.rows) || {};
    const pos = POSITIONS.includes(position) ? position : "ALL";
    const excluded = ((inspection && inspection.excluded) || []).find(e => e.key === meta.key) || null;

    const pipeline = (inspection && inspection.valuePipeline) || {};
    const source = (pipeline.sources && pipeline.sources[meta.key]) || {};
    const all = Object.keys(players).map(key => {
      const p = players[key];
      const row = rows[key] || {};
      const published = finite(p.native);
      // Indexed exists for the published charts only; a projection has no indexed stage.
      const indexed = isChart ? finite(row.indexed && row.indexed[meta.key]) : null;
      const adjusted = finite(row.adjusted && row.adjusted[meta.key]);
      return {
        key, name: row.name || `Player ${key}`, pos: p.pos || row.pos || "", role: p.role || "",
        positionRank: finite(p.rank), estimated: Boolean(p.estimated),
        reason: (row.estimated && row.estimated[meta.key]) || (row.reasons && row.reasons[meta.key]) || "",
        published, indexed, adjusted,
        // Read the exact pipeline intermediates; never derive a player value here.
        trace: isChart ? null : {
          waiver: finite(source.positions && source.positions[p.pos] && source.positions[p.pos].waiver),
          starterLine: finite(source.positions && source.positions[p.pos] && source.positions[p.pos].starterLine),
          availability: finite(source.positions && source.positions[p.pos] && source.positions[p.pos].avail),
          aboveWaivers: finite(p.vorp), startWorthy: finite(p.startWorthy), lineupShare: finite(p.lineupShare),
          starterPart: finite(p.starterSlice), fillInPart: finite(p.benchSlice),
          starterRate: finite(source.rates && source.rates[`${p.pos}|starter`]),
          fillInRate: finite(source.rates && source.rates[`${p.pos}|bench`])
        }
      };
    });
    // The source's own order: published high to low, ties by player key.
    all.sort((a, b) => (b.published ?? -Infinity) - (a.published ?? -Infinity) || Number(a.key) - Number(b.key));
    const shown = all.filter(r => pos === "ALL" || r.pos === pos);
    shown.forEach((r, i) => { r.rank = i + 1; });

    const series = {};
    STAGES.forEach(stage => {
      series[stage] = shown.map(r => ({key: r.key, rank: r.rank, value: r[stage], estimated: r.estimated}))
        .filter(pt => pt.value !== null);
    });
    const stages = {
      published: {exists: series.published.length > 0, unit: isChart ? "the source's own units" : "points per game",
        plotted: true},
      indexed: {exists: isChart && series.indexed.length > 0,
        reason: isChart ? "" : `${meta.label} is a projection: its values are not indexed to another chart.`},
      adjusted: {exists: series.adjusted.length > 0}
    };
    const sum = stage => series[stage].reduce((t, pt) => t + pt.value, 0);
    return {
      method: pipeline.method || null, pie: finite(pipeline.pie),
      source: meta.key, label: meta.label, family: meta.family, position: pos,
      engineLabel: (inspection && inspection.labels && inspection.labels[meta.key]) || meta.label,
      status: excluded ? excluded.reason : "",
      hasData: all.length > 0, total: all.length, shown: shown.length,
      estimatedCount: shown.filter(r => r.estimated).length,
      stages, rows: shown, series,
      totals: {published: sum("published"), indexed: sum("indexed"), adjusted: sum("adjusted")},
      setting: (inspection && inspection.setting) || null
    };
  }

  // ---- DOM --------------------------------------------------------------
  const NS = "http://www.w3.org/2000/svg";
  function h(tag, attrs, ...kids) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (v === null || v === undefined || v === false) return;
      if (k === "text") node.textContent = v; else node.setAttribute(k, v === true ? "" : v);
    });
    kids.flat().forEach(kid => { if (kid !== null && kid !== undefined) node.append(kid); });
    return node;
  }
  function s(tag, attrs, ...kids) {
    const node = document.createElementNS(NS, tag);
    Object.entries(attrs || {}).forEach(([k, v]) => { if (v !== null && v !== undefined) node.setAttribute(k, v); });
    kids.forEach(kid => node.append(kid));
    return node;
  }

  // Source pages: the same data the rest of Player values reads (assets/comparison-sources-data.json,
  // sources.<id>.url, falling back to .source_url). No address is kept in this file.
  let sourcePages = {};
  let pagesLoading = null;
  function loadSourcePages() {
    if (pagesLoading) return pagesLoading;
    pagesLoading = fetch("assets/comparison-sources-data.json")
      .then(r => (r.ok ? r.json() : null)).catch(() => null)
      .then(doc => {
        const sources = (doc && doc.sources) || {};
        sourcePages = {};
        Object.entries(sources).forEach(([key, src]) => {
          const url = src && (src.url || src.source_url);
          if (typeof url === "string" && /^https?:\/\//.test(url)) sourcePages[key] = url;
        });
        if (state.host && state.host.isConnected) render();
        return sourcePages;
      });
    return pagesLoading;
  }
  // Same position swap as v2.js sourceUrl: the all-positions view uses the QB page.
  function sourceUrl(key, position) {
    const url = sourcePages[key];
    if (!url) return "";
    const pos = ["QB", "RB", "WR", "TE"].includes(position) ? position : "QB";
    if (key === "cbsros") return url.replace("/QB/", `/${pos}/`);
    if (key === "razzball") return url.replace("-qb-", `-${pos.toLowerCase()}-`);
    return url;
  }
  function pageLink(key, label, text, position) {
    const url = sourceUrl(key, position);
    if (!url) return null;
    return h("a", {class: "as-link", href: url, target: "_blank", rel: "noopener", "data-source-link": key, text,
      "aria-label": `${label}: open the source's page in a new tab`});
  }

  const state = {source: null, position: "ALL", limit: PAGE, lastModel: null, host: null, hoverRank: null, playerKey: null};
  try { state.source = localStorage.getItem("ddf.v2.audit.source"); } catch (e) { /* storage may be blocked */ }
  if (!SOURCES.some(x => x.key === state.source)) state.source = SOURCES[0].key;

  // One minus sign (U+2212) and one zero ("0.0", never "-0.0").
  function minus(text) { return /^-0(\.0+)?$/.test(text) ? text.slice(1) : text.replace("-", "−"); }

  function fmtValue(v, stage, family) {
    if (v === null) return "—";
    if (stage === "published") return family === "projection" ? minus(v.toFixed(2)) : (Number.isInteger(v) ? v.toLocaleString("en-US") : minus(v.toFixed(1)));
    return minus(v.toFixed(1));
  }
  const fullPrecision = v => (v === null ? "" : String(v));

  function inspect() {
    const C = root.TradeValueCurveControls;
    if (!C || typeof C.getInspection !== "function") return null;
    try { if (typeof C.isReady === "function" && !C.isReady()) return null; return C.getInspection(); } catch (e) { return null; }
  }

  function settingText(setting) {
    if (!setting) return "";
    const r = setting.roster || {};
    const parts = [`${setting.teams} teams`, String(setting.scoring || "").toUpperCase() === "PPR" ? "PPR" : String(setting.scoring || "")];
    const slots = ["QB", "RB", "WR", "TE"].map(p => `${r[p] || 0} ${p}`);
    if (r.FLEX) slots.push(`${r.FLEX} flex`);
    if (r.SUPERFLEX) slots.push(`${r.SUPERFLEX} superflex`);
    if (r.BENCH !== undefined) slots.push(`${r.BENCH} bench`);
    return `${parts.join(", ")}; ${slots.join(", ")}`;
  }

  // ---- chart ------------------------------------------------------------
  let W = 720;
  const H = 300, PAD = {l: 46, r: 56, t: 14, b: 30};

  function niceMax(v) {
    if (!(v > 0)) return 1;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    const n = v / p;
    return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
  }

  // Left axis: DDF value (Indexed and Adjusted). Right axis (JEG-1011, Jeremy 2026-10-24): the
  // Published line is drawn as a percentage of the source's own largest Published value, so the
  // shape is comparable whatever the source's units; the raw numbers stay in the table.
  function chartScales(model) {
    const max = stage => model.series[stage].reduce((m, pt) => Math.max(m, pt.value), 0);
    const left = niceMax(Math.max(max("indexed"), max("adjusted")));
    return {left, publishedMax: max("published"), n: model.shown};
  }

  function pathFor(sx, sy, shownRows, stage) {
    // Break the line at a missing value instead of drawing it through zero.
    let d = "", pen = false;
    shownRows.forEach(r => {
      const v = r[stage];
      if (v === null) { pen = false; return; }
      d += `${pen ? "L" : "M"}${sx(r.rank).toFixed(1)},${sy(v).toFixed(1)}`;
      pen = true;
    });
    return d;
  }

  function drawChart(model, readout) {
    W = Math.max(300, Math.round((state.host && state.host.clientWidth) || 720) - 40);
    const svg = s("svg", {viewBox: `0 0 ${W} ${H}`, class: "as-svg", role: "img",
      "aria-label": `${model.label}: ${STAGES.filter(st => model.stages[st].exists).map(st => stageLabel(model, st)).join(", ")} by rank`, width: W, height: H});
    if (!model.shown) return svg;
    const sc = chartScales(model);
    const plotW = W - PAD.l - PAD.r, plotH = H - PAD.t - PAD.b;
    const sx = rank => PAD.l + (model.shown <= 1 ? 0 : (rank - 1) / (model.shown - 1)) * plotW;
    const syLeft = v => PAD.t + plotH - Math.min(1, Math.max(0, v / sc.left)) * plotH;
    const syRight = v => PAD.t + plotH - Math.min(1, Math.max(0, sc.publishedMax > 0 ? v / sc.publishedMax : 0)) * plotH;
    for (let i = 0; i <= 4; i += 1) {
      const y = PAD.t + (plotH * i) / 4;
      svg.append(s("line", {x1: PAD.l, x2: W - PAD.r, y1: y, y2: y, class: "as-grid"}));
      const lv = sc.left * (1 - i / 4), rv = 100 * (1 - i / 4);
      svg.append(Object.assign(s("text", {x: PAD.l - 6, y: y + 4, class: "as-tick as-tick-l", "text-anchor": "end"}), {textContent: lv >= 10 ? Math.round(lv) : lv.toFixed(1)}));
      svg.append(Object.assign(s("text", {x: W - PAD.r + 6, y: y + 4, class: "as-tick as-tick-r"}), {textContent: `${Math.round(rv)}%`}));
    }
    [1, Math.ceil(model.shown / 2), model.shown].filter((v, i, a) => a.indexOf(v) === i).forEach(rank => {
      svg.append(Object.assign(s("text", {x: sx(rank), y: H - 8, class: "as-tick", "text-anchor": rank === 1 ? "start" : rank === model.shown ? "end" : "middle"}), {textContent: `#${rank}`}));
    });
    const order = ["published", "indexed", "adjusted"];
    order.forEach(stage => {
      if (!model.series[stage].length) return;
      const yOf = stage === "published" ? syRight : syLeft;
      svg.append(s("path", {d: pathFor(sx, yOf, model.rows, stage), class: `as-line as-line-${stage}`,
        "data-series": stage, "data-count": model.series[stage].length, fill: "none"}));
    });
    // Estimated players: hollow markers on every stage, so the fill-in is visible on the curve.
    const marks = s("g", {class: "as-estimated-marks"});
    model.rows.filter(r => r.estimated).forEach(r => {
      order.forEach(stage => {
        if (r[stage] === null || !model.series[stage].length) return;
        const yOf = stage === "published" ? syRight : syLeft;
        marks.append(s("circle", {cx: sx(r.rank).toFixed(1), cy: yOf(r[stage]).toFixed(1), r: 3.5,
          class: `as-mark as-mark-${stage}`, "data-estimated": "", "data-player-key": r.key, "data-series": stage}));
      });
    });
    svg.append(marks);
    const cursor = s("line", {y1: PAD.t, y2: PAD.t + plotH, class: "as-cursor", visibility: "hidden"});
    svg.append(cursor);
    const overlay = s("rect", {x: PAD.l, y: PAD.t, width: plotW, height: plotH, fill: "transparent", class: "as-overlay"});
    const showAt = evt => {
      const box = svg.getBoundingClientRect();
      const px = ((evt.clientX - box.left) / box.width) * W;
      const rank = Math.min(model.shown, Math.max(1, Math.round(1 + ((px - PAD.l) / plotW) * (model.shown - 1))));
      const r = model.rows[rank - 1];
      cursor.setAttribute("x1", sx(rank)); cursor.setAttribute("x2", sx(rank)); cursor.setAttribute("visibility", "visible");
      readout.textContent = readoutText(model, r);
    };
    overlay.addEventListener("pointermove", showAt);
    overlay.addEventListener("pointerdown", showAt);
    overlay.addEventListener("pointerleave", () => { cursor.setAttribute("visibility", "hidden"); readout.textContent = defaultReadout(model); });
    svg.append(overlay);
    return svg;
  }

  function readoutText(model, r) {
    if (!r) return defaultReadout(model);
    const bits = STAGES.filter(st => model.stages[st].exists).map(st => `${stageLabel(model, st)} ${fmtValue(r[st], st, model.family)}`);
    return `#${r.rank} ${r.name} (${r.pos})${r.estimated ? ", estimated" : ""}: ${bits.join(", ")}`;
  }
  const defaultReadout = model => (model.shown ? "Point at the chart to read a player." : "");

  // ---- render -----------------------------------------------------------
  function render() {
    const host = state.host;
    if (!host) return;
    const insp = inspect();
    loadSourcePages();
    host.textContent = "";
    host.classList.add("as-root");
    host.append(h("header", {class: "as-head"},
      h("h2", {class: "as-title", text: "How a source's values are built"}),
      h("p", {class: "as-lede", text: "Trade charts start with published chart numbers, then Indexed and Adjusted values. Projections start with points per game and become a published value through the league model. Choose a source to trace its path."})));

    if (!insp) {
      host.append(h("p", {class: "as-note", role: "status", text: "Values are still loading."}));
      return;
    }
    const model = build(insp, state.source, state.position);
    state.lastModel = model;

    // Source toggle.
    const group = (label, family) => h("div", {class: "as-group", role: "group", "aria-label": label},
      h("span", {class: "as-group-label", text: label}),
      SOURCES.filter(x => x.family === family).map(x => {
        const b = h("button", {type: "button", class: "as-seg", "data-source": x.key, "aria-pressed": String(x.key === state.source), text: x.label});
        b.addEventListener("click", () => {
          state.source = x.key; state.limit = PAGE;
          try { localStorage.setItem("ddf.v2.audit.source", x.key); } catch (e) { /* storage may be blocked */ }
          render();
        });
        return h("span", {class: "as-seg-wrap"}, b, pageLink(x.key, x.label, "↗", state.position));
      }));
    host.append(h("div", {class: "as-toolbar"}, group("Trade charts", "chart"), group("Projections", "projection")));

    const posSel = h("select", {class: "as-select", id: "as-position", "aria-label": "Position"},
      POSITIONS.map(p => h("option", {value: p, text: p === "ALL" ? "All positions" : p, selected: p === state.position})));
    posSel.value = state.position;
    posSel.addEventListener("change", () => { state.position = posSel.value; state.limit = PAGE; render(); });
    const headLink = pageLink(model.source, model.label, `Open ${model.label}'s page`, state.position);
    host.append(h("p", {class: "as-source-head"}, h("strong", {text: model.label}), " ",
      headLink || h("span", {class: "as-muted", "data-no-link": "", text: "(no page link available)"})));
    host.append(h("div", {class: "as-meta"},
      h("label", {class: "as-label", for: "as-position", text: "Position "}), posSel,
      h("span", {class: "as-setting", text: settingText(model.setting)})));

    // Stage notes: say where a stage does not exist, instead of faking it.
    const notes = h("ul", {class: "as-stages"});
    STAGES.forEach(stage => {
      const st = model.stages[stage];
      let text;
      if (stage === "published") {
        text = model.family === "projection"
          ? "Projected points/game: the source input at your scoring. The right-hand axis shows a percentage of its largest input; the table shows points per game."
          : "Published: the chart's own numbers at your scoring, before any rescaling. It is drawn as a percentage of the source's largest value (right-hand axis); the raw numbers are in the table.";
      } else if (stage === "indexed") {
        text = st.exists ? "Indexed: the published numbers times one factor, so the chart lines up with DDF Value (left-hand axis). Player values calls this Rescaled."
          : `Indexed: not available. ${st.reason || "This source has no indexed values."}`;
      } else {
        text = model.family === "projection"
          ? "Published value: the engine's Adjusted output, shown for this projection in Player values (left-hand axis). The worked player below traces how it is built."
          : "Adjusted: the value after the starter and bench split, rescaled so the source's total is the league's value pie (left-hand axis).";
      }
      notes.append(h("li", {class: `as-stage as-stage-${stage}`, "data-stage": stage, "data-exists": String(st.exists)},
        h("span", {class: `as-swatch as-swatch-${stage}`, "aria-hidden": "true"}), text));
    });

    if (!model.hasData) {
      host.append(notes, h("p", {class: "as-note", role: "status", "data-empty": "",
        text: `${model.label} has no values at these league settings${model.status ? ` (${model.status})` : ""}.`}));
      return;
    }
    if (model.status) host.append(h("p", {class: "as-note as-status", "data-status": "", text: `Engine status for ${model.label}: ${model.status}. Values shown are what the engine holds for it.`}));

    const readout = h("p", {class: "as-readout", "aria-live": "polite", text: defaultReadout(model)});
    const legend = h("div", {class: "as-legend"},
      STAGES.filter(st => model.stages[st].exists).map(st =>
        h("span", {class: "as-legend-item"}, h("span", {class: `as-swatch as-swatch-${st}`, "aria-hidden": "true"}), stageLabel(model, st))),
      model.estimatedCount ? h("span", {class: "as-legend-item"}, h("span", {class: "as-swatch as-swatch-est", "aria-hidden": "true"}), `Hollow marker: estimated from other charts (${model.estimatedCount})`) : null);
    host.append(h("section", {class: "as-card", "aria-label": "Curve chart"},
      h("div", {class: "as-card-head"}, h("h3", {class: "as-card-title", text: `${model.label} by rank`}),
        h("span", {class: "as-count", text: `${model.shown} players${model.position === "ALL" ? "" : ` at ${model.position}`}`})),
      notes, legend, h("div", {class: "as-plot"}, drawChart(model, readout)), readout));

    if (model.family === "projection") host.append(projectionCard(model));
    host.append(tableCard(model));
  }

  function projectionCard(model) {
    const card = h("section", {class: "as-card as-projection", "aria-label": "Projection path to published value"},
      h("h3", {class: "as-card-title", text: "From projection to published value"}),
      h("p", {class: "as-foot", text: "Published here means the modeled value displayed in Player values, not a trade value supplied by the projection publisher. The trace starts at the points per game supplied to the engine; source totals and their conversion are not exposed in this readout."}));
    const player = model.rows.find(r => r.key === state.playerKey) || model.rows[0];
    if (!player) {
      card.append(h("p", {class: "as-foot", text: "No player at this position has an engine readout."}));
      return card;
    }
    const select = h("select", {id: "as-worked-player", class: "as-select"}, model.rows.map(r =>
      h("option", {value: r.key, text: `${r.name} (${r.pos})`})));
    select.value = player.key;
    select.addEventListener("change", () => { state.playerKey = select.value; render(); });
    card.append(h("div", {class: "as-meta"}, h("label", {for: "as-worked-player", text: "Worked player "}), select));
    const t = player.trace;
    const metric = (key, label, value, unit = "") => h("li", {},
      h("span", {text: `${label}: `}), h("strong", {"data-readout": key, "data-value": fullPrecision(value),
        title: value === null ? "Not exposed by the engine" : String(value),
        text: value === null ? "— (unavailable)" : `${minus(value.toFixed(4))}${unit}`}));
    const step = (title, text, metrics) => h("li", {class: "as-path-step"},
      h("h4", {text: title}), h("p", {class: "as-foot", text}), h("ul", {class: "as-metrics"}, metrics));
    card.append(h("ol", {class: "as-path", "data-player-key": player.key},
      step("Source input", "The source's points per game at the current scoring, before the league model.",
        [metric("input", "Projected points/game", player.published, " PPG")]),
      step("League lines and value above waivers", "The league's roster determines the waiver line and starter line at this position. Value above waivers is the positive surplus over the waiver line, with a floor of zero.",
        [metric("waiver", `${player.pos} waiver line`, t.waiver, " PPG"), metric("starterLine", `${player.pos} starter line`, t.starterLine, " PPG"), metric("aboveWaivers", "Value above waivers", t.aboveWaivers, " PPG")]),
      step("Starter and fill-in parts", model.method === "expected-starts"
        ? "The expected-starts model uses projection uncertainty to estimate the chance of playing above the starter line. Value above waivers × availability × that chance gives the starter part. The fill-in part uses chances across bench depth bands, weighted by openings in the lineup. Expected lineup share combines starter and fill-in chances with availability. The parts need not add up to value above waivers."
        : model.method === "slices" ? "The starter line splits value above waivers into starter and fill-in parts."
        : "The engine's weighting method is unavailable; only exposed parts are shown.",
        [metric("availability", "Availability (fraction)", t.availability), metric("startWorthy", "Chance above starter line (fraction)", t.startWorthy), metric("lineupShare", "Expected lineup share (fraction)", t.lineupShare), metric("starterPart", "Starter part", t.starterPart), metric("fillInPart", "Fill-in part", t.fillInPart)]),
      step("Scale to the league's value pie", "The engine funds position and starter/fill-in budgets from the league pie. Each rate is the funded group budget divided by that source's group total. Starter part × starter rate + fill-in part × fill-in rate gives the published value below.",
        [metric("pie", "League value pie", model.pie), metric("starterRate", "Starter rate", t.starterRate), metric("fillInRate", "Fill-in rate", t.fillInRate), metric("output", "Published value (Adjusted)", player.adjusted)])));
    card.append(h("p", {class: "as-foot", text: model.status
      ? `Engine status: ${model.status}. This trace shows the engine's retained readouts; it does not establish that a held source is currently displayed or included.`
      : "No Indexed step applies to a projection. Missing readouts stay unavailable; zero is shown only when the engine supplies zero."}));
    return card;
  }

  function tableCard(model) {
    const cols = [["rank", "#"], ["player", "Player"], ["pos", "Pos"], ["role", "Role"], ["published", stageLabel(model, "published")]];
    if (model.stages.indexed.exists) cols.push(["indexed", "Indexed"]);
    cols.push(["adjusted", stageLabel(model, "adjusted")]);
    if (model.stages.indexed.exists) cols.push(["change", "Change"]);
    const table = h("table", {class: "as-table", "data-source": model.source},
      h("thead", {}, h("tr", {}, cols.map(([key, label]) => h("th", {scope: "col", "data-col": key, class: ["published", "indexed", "adjusted", "change", "rank"].includes(key) ? "as-num" : null, text: label})))));
    const tbody = h("tbody");
    model.rows.slice(0, state.limit).forEach(r => {
      const tr = h("tr", {"data-player-key": r.key, "data-estimated": r.estimated ? "" : null, class: r.estimated ? "as-row-est" : null});
      const nameCell = h("td", {class: "as-name", "data-col": "player"}, r.name);
      if (r.estimated) nameCell.append(" ", h("span", {class: "as-badge", "data-estimated-badge": "", title: r.reason || "Estimated from other charts", text: "Estimated"}));
      tr.append(h("td", {class: "as-num", "data-col": "rank", text: String(r.rank)}), nameCell,
        h("td", {"data-col": "pos", text: r.pos}), h("td", {"data-col": "role", text: ROLE_LABEL[r.role] || r.role || "—"}));
      const valueCell = stage => {
        const v = r[stage];
        const td = h("td", {class: `as-num as-val as-val-${stage}${v === null ? " as-missing" : ""}`, "data-col": stage, "data-stage": stage,
          "data-value": fullPrecision(v), title: v === null ? "No value" : String(v), text: fmtValue(v, stage, model.family)});
        if (v !== null && r.estimated && stage === "published") td.textContent = `≈ ${td.textContent}`;
        return td;
      };
      tr.append(valueCell("published"));
      if (model.stages.indexed.exists) tr.append(valueCell("indexed"));
      tr.append(valueCell("adjusted"));
      if (model.stages.indexed.exists) {
        const diff = r.adjusted !== null && r.indexed !== null ? r.adjusted - r.indexed : null;
        tr.append(h("td", {class: `as-num as-val${diff === null ? " as-missing" : ""}`, "data-col": "change", "data-value": fullPrecision(diff),
          text: diff === null ? "—" : Math.abs(diff) < 0.05 ? "0.0" : `${diff > 0 ? "+" : "−"}${Math.abs(diff).toFixed(1)}`}));
      }
      tbody.append(tr);
    });
    table.append(tbody);
    const card = h("section", {class: "as-card", "aria-label": "Table"},
      h("div", {class: "as-card-head"}, h("h3", {class: "as-card-title", text: "Player by player"}),
        h("span", {class: "as-count", text: `Showing ${Math.min(state.limit, model.shown)} of ${model.shown}`})),
      h("div", {class: "as-scroll", tabindex: "0", role: "region", "aria-label": `${model.label} values table`}, table));
    if (model.estimatedCount) card.append(h("p", {class: "as-foot", text: "Estimated players are not listed by this source; the engine fills their value in from other charts (marked Estimated, and shown with ≈)."}));
    card.append(h("p", {class: "as-foot", text: "A dash means the engine has no value at that stage. It is never zero."}));
    if (model.shown > state.limit) {
      const more = h("button", {type: "button", class: "as-more", text: `Show ${Math.min(PAGE, model.shown - state.limit)} more`});
      more.addEventListener("click", () => { state.limit += PAGE; render(); });
      card.append(more);
    }
    return card;
  }

  function mount(host) {
    const el = typeof host === "string" ? document.querySelector(host) : host;
    if (!el) return;
    state.host = el;
    render();
  }

  let lastWidth = 0;
  root.addEventListener("resize", () => {
    const w = state.host ? state.host.clientWidth : 0;
    if (w && Math.abs(w - lastWidth) > 8 && state.host.offsetParent !== null) { lastWidth = w; render(); }
  });
  root.addEventListener("trade-value-rows-change", () => {
    if (state.host && state.host.isConnected && state.host.offsetParent !== null) render();
  });

  root.DDFAuditSource = {build, SOURCES, state, current: () => state.lastModel, render};
  if (root.DDFAudit && typeof root.DDFAudit.register === "function") {
    root.DDFAudit.register("single-source", (host, ctx) => mount(host || document.getElementById("audit-source-root"), ctx));
  }
})(window);
