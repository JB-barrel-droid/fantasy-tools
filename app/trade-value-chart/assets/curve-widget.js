(() => {
  "use strict";

  // distinctSourcePeaks guard core. The guard exists to catch every active
  // curve being the SAME data (an aggregate, or one map served for all
  // sources). Equal peaks alone are not that bug: the value-above-waivers
  // translation scales every published chart's top player to the same
  // positional max (RB 70), so translated sources legitimately share a peak
  // (JEG332-STORED-DRIFT, 2026-10-07). Distinct = peaks differ OR the curves
  // differ anywhere (values compared to 0.1).
  function sourceCurvesDistinct(keys, maps) {
    const peaks = new Set(keys.map(key => Math.max(...maps.get(key).values()).toFixed(1)));
    if (peaks.size > 1) return true;
    const signature = key => [...maps.get(key).entries()]
      .map(([player, value]) => `${player}:${Number(value).toFixed(1)}`)
      .sort()
      .join(",");
    return new Set(keys.map(signature)).size > 1;
  }

  const POSITIONS = ["ALL", "QB", "RB", "WR", "TE", "FLEX"];  // JEG-211: K/DST honestly excluded
  const SCORINGS = [["standard", "Standard"], ["half_ppr", "Half PPR"], ["ppr", "Full PPR"]];
  const SOURCE_LABELS = {
    usatoday: "USA Today",
    fantasycalc: "FantasyCalc",
    fantasypros: "FantasyPros",
    cbs: "CBS",
    espn: "ESPN adjusted",
    cbsros: "CBS ROS",
    razzball: "Razzball",
    fantasycalc_adjusted: "FC Adjusted",
    usatoday_adjusted: "USAT Adjusted",
    fantasypros_adjusted: "FP Adjusted",
    cbs_adjusted: "CBS Adjusted",
    espn_vorp: "ESPN raw VORP vs waivers",
    cbsros_vorp: "CBS ROS raw VORP vs waivers",
    razzball_vorp: "Razzball raw VORP vs waivers",
    ddf_value: "DDF Value"
  };
  const WEEKED_SOURCE_KEYS = new Set(["usatoday", "fantasycalc", "fantasypros", "cbs", "fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted", "cbs_adjusted"]);
  const SOURCE_KEYS = [
    "usatoday",
    "fantasycalc",
    "fantasypros",
    "cbs",
    "espn",
    "cbsros",
    "razzball",
    "fantasycalc_adjusted",
    "usatoday_adjusted",
    "fantasypros_adjusted",
    "cbs_adjusted"
  ];
  const SOURCE_STYLES = {
    usatoday: {color: "#d5531d", dash: []},
    fantasycalc: {color: "#236a96", dash: []},
    fantasypros: {color: "#16815d", dash: []},
    cbs: {color: "#b83e45", dash: []},
    espn: {color: "#6b55a3", dash: []},
    cbsros: {color: "#c9842b", dash: []},
    razzball: {color: "#2b9dc9", dash: []},
    fantasycalc_adjusted: {color: "#236a96", dash: [7, 4]},
    usatoday_adjusted: {color: "#d5531d", dash: [7, 4]},
    fantasypros_adjusted: {color: "#16815d", dash: [7, 4]},
    cbs_adjusted: {color: "#b83e45", dash: [7, 4]},
    espn_vorp: {color: "#6b55a3", dash: []},
    cbsros_vorp: {color: "#c9842b", dash: []},
    razzball_vorp: {color: "#2b9dc9", dash: []}
  };
  const SOURCE_GROUPS = [
    {label:"Projections (Adjusted values)", keys:["espn", "cbsros", "razzball"]},
    {label:"Trade charts (Adjusted values)", keys:["fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted", "cbs_adjusted"]},
    {label:"Projections (VORP vs waivers)", keys:["espn_vorp", "cbsros_vorp", "razzball_vorp"]},
    {label:"Trade charts (as published)", keys:["usatoday", "fantasycalc", "fantasypros", "cbs"]}
  ];
  // Pure raw value-above-waivers curves: projection-minus-waiver VORP from
  // each source's own per-game projections, before starter/bench
  // utilization. JEG-38: ESPN plus the two DDF-native legs (CBS ROS, Razzball).
  const VORP_SOURCE_DEFS = {
    espn_vorp: {ppgField: "espn_ppg", short: "ESPN"},
    cbsros_vorp: {ppgField: "cbsros_ppg", short: "CBS ROS"},
    razzball_vorp: {ppgField: "rz_ppg", short: "Razzball"},
  };
  const PURE_VORP_KEYS = ["espn_vorp", "cbsros_vorp", "razzball_vorp"];
  // DDF Value (JEG-497 / JEG-508, docs/methodology.md "Value Pipeline",
  // VP-6.3): the equal-weight mean of the included sources' Adjusted values,
  // in three versions (blended, charts, projections), one number per player in
  // every view and tab. It lives on the rows (values.ddf_value / _charts /
  // _projections, ddfByVersion, ddfTier, ...), never in sourceMaps.
  const COMPOSITE_KEY = "ddf_value";
  // VP-11: the DDF inputs are source keys. The pre-JEG-508 names of the
  // charts' inputs (fantasycalc_adjusted, ...) are still accepted by
  // setCompositeInputs and mapped to the chart (COMPOSITE_INPUT_ALIASES).
  const COMPOSITE_INPUT_KEYS = ["espn", "cbsros", "razzball", "fantasycalc", "usatoday", "fantasypros", "cbs"];
  const EXTRA_SOURCE_KEYS = [];
  // The four "*_adjusted" series are deprecated aliases (VP-11 retires them):
  // each carries its chart's Adjusted values (VP-5.5) in every tab, so the v2
  // "Trade charts (adjusted)" group keeps working until the front end reads
  // the chart keys in the Adjusted tab instead. No fit, no cells.
  const ADJUSTED_INDEXED_KEYS = ["fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted", "cbs_adjusted"];
  const COMPOSITE_INPUT_ALIASES = Object.fromEntries(ADJUSTED_INDEXED_KEYS.map(key => [key, key.replace(/_adjusted$/, "")]));
  const DEFAULT_INDEXED_SOURCES = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
  const POSITION_ORDER = ["QB", "RB", "WR", "TE"];
  // JEG-211 (Jeremy 2026-10-03): K/DST are honestly excluded from the chart.
  // The computed artifact (dist/modules/ddf-kdst-group-vorps.json) remains as
  // internal evidence, but no chart surface renders K/DST.
  // (Re-restored 2026-10-03: the JEG-292 commit 49cd201 reintroduced
  // SPECIALIST_POSITIONS/CHART_POSITIONS-with-specialists from a stale base.)
  const CHART_POSITIONS = [...POSITION_ORDER];
  // The default league roster (the charts' saved 12-team setup).
  // SUPERFLEX (JEG332-SUPERFLEX-FLEX option A, Jeremy 2026-10-08): dedicated
  // superflex slots per team (0 or 1), QB-eligible, filled after the
  // dedicated slots and before FLEX (value-model.js superflexCount).
  const DEFAULT_ROSTER = Object.freeze({QB:1, RB:2, WR:3, TE:1, FLEX:1, SUPERFLEX:0, BENCH:6, K:0, DST:0});
  // Stepper bounds per roster key (setRosterSpot clamps to them).
  const ROSTER_BOUNDS = Object.freeze({BENCH: [0, 14], SUPERFLEX: [0, 1]});
  const rosterBounds = key => ROSTER_BOUNDS[key] || [1, 5];
  const DEFAULT_FLEX_ELIGIBLE = Object.freeze(["RB", "WR", "TE"]);
  const DEFAULT_BENCH_SHARE = 0.15;
  // Minimum plausible peak for an indexed curve. See the collapse guard in
  // runRegressionGuards() for the derivation: the fixed pie spreads ~3197
  // across ~596 players (mean ~5.4) and healthy curves peak 60-95, so this
  // floor separates "scale is broken" from "this source ranks flatter than
  // the others". Raise it only with a curve that genuinely cannot go lower.
  const CURVE_COLLAPSE_FLOOR = 25;
  // Set once runRegressionGuards() returns clean; draw() refuses to paint until then.
  let guardsPassed = false;
  // Bench-share slider range (VP-3.4: the reader's slider replaces the 15%
  // default; the pipeline is defined for any share in [0, 1]).
  const BENCH_SHARE_BOUNDS = Object.freeze([0.01, 0.30]);  // product-data options bench_share_min/max

  // ---------------------------------------------------------------------------
  // ChartHealth: active runtime invariant checks that root out errors.
  //
  // These are NOT passive unit tests. They run on every curve build in the
  // live page, validate the computed values against known invariants, and
  // surface failures visibly in the Health panel and console. A check that
  // fails means the rendered numbers are wrong -- the panel shows it in red
  // and the console carries the full detail. Silence is not an option.
  // ---------------------------------------------------------------------------
  const ChartHealth = (() => {
    const checks = new Map(); // id -> {name, status, detail, at, diagnostics}
    function record(id, name, ok, detail, diagnostics) {
      const status = ok ? "pass" : "fail";
      checks.set(id, {name, status, detail: detail || "", at: new Date().toISOString(), diagnostics: diagnostics || null});
      if (!ok) {
        console.error("[ChartHealth] FAIL:", name, "--", detail);
      }
      render();
    }
    function warn(id, name, detail, diagnostics) {
      checks.set(id, {name, status: "warn", detail: detail || "", at: new Date().toISOString(), diagnostics: diagnostics || null});
      console.warn("[ChartHealth] WARN:", name, "--", detail);
      render();
    }
    // JEG-30: structured per-source guard diagnostics. Renders a collapsible
    // detail view under a failed/warned check, showing per-source numbers
    // (total, target, delta, basis, player count, per-position breakdown).
    // The happy path stays clean: detail only renders on failure/warning.
    function renderDiagnosticsTable(diagnostics) {
      if (!diagnostics || !Array.isArray(diagnostics.checks)) return "";
      const rows = diagnostics.checks.map(c => {
        const label = sourceLabel(c.source);
        const total = c.total === null || c.total === undefined ? "—" : Number(c.total).toFixed(1);
        const target = c.target === null || c.target === undefined ? "—" : Number(c.target).toFixed(1);
        const delta = c.delta === null || c.delta === undefined ? "—" : Number(c.delta).toFixed(2);
        const basis = c.basis || "—";
        const n = c.n !== undefined ? c.n : (c.shared !== undefined && c.shared !== null ? c.shared : "—");
        const status = c.ok ? "✓" : "✗";
        let perPosRows = "";
        if (c.perPos && typeof c.perPos === "object") {
          perPosRows = Object.entries(c.perPos).map(([pos, d]) =>
            `<tr class="health-perpos"><td></td><td>${pos}</td><td>${Number(d.total).toFixed(1)}</td><td>${Number(d.pie).toFixed(1)}</td><td>${Number(d.total - d.pie).toFixed(2)}</td><td>pos</td><td>${d.n}</td><td></td></tr>`
          ).join("");
        }
        return `<tr class="health-diag-${c.ok ? "ok" : "fail"}"><td>${status}</td><td>${label}</td><td>${total}</td><td>${target}</td><td>${delta}</td><td>${basis}</td><td>${n}</td><td></td></tr>${perPosRows}`;
      }).join("");
      return `<details class="health-diagnostics"><summary>Guard diagnostics (per source)</summary>` +
        `<table class="health-diag-table"><thead><tr><th></th><th>Source</th><th>Total</th><th>Target</th><th>Delta</th><th>Basis</th><th>Players</th><th></th></tr></thead>` +
        `<tbody>${rows}</tbody></table>` +
        `<p class="health-diag-note">Tolerance: ±${diagnostics.tolerance}. ` +
        `Each source's Adjusted values over its work list (listed and estimated players) must sum to the league pie and each group to its budget (VP-5).</p></details>`;
    }
    function render() {
      const el = document.getElementById("chartHealthList");
      if (!el) return;
      const rows = [...checks.values()];
      const fails = rows.filter(r => r.status === "fail").length;
      const warns = rows.filter(r => r.status === "warn").length;
      const badge = document.getElementById("chartHealthBadge");
      if (badge) {
        badge.textContent = fails > 0 ? `Health: ${fails} FAIL` : warns > 0 ? `Health: ${warns} warn` : "Health: OK";
        badge.dataset.status = fails > 0 ? "fail" : warns > 0 ? "warn" : "ok";
      }
      el.innerHTML = rows.length === 0
        ? '<li class="health-empty">No checks have run yet.</li>'
        : rows.map(r => {
            const icon = r.status === "pass" ? "✓" : r.status === "fail" ? "✗" : "!";
            // JEG-30: failed/warned checks with structured diagnostics get a
            // collapsible detail view; passing checks stay clean.
            const diagHtml = (r.status !== "pass" && r.diagnostics) ? renderDiagnosticsTable(r.diagnostics) : "";
            return `<li class="health-${r.status}"><span class="health-icon">${icon}</span><span class="health-name">${r.name}</span><span class="health-detail">${r.detail}</span>${diagHtml}</li>`;
          }).join("");
    }
    function summary() {
      const rows = [...checks.values()];
      return {
        total: rows.length,
        pass: rows.filter(r => r.status === "pass").length,
        fail: rows.filter(r => r.status === "fail").length,
        warn: rows.filter(r => r.status === "warn").length,
        checks: Object.fromEntries(checks),
      };
    }
    return {record, warn, render, summary};
  })();

  // JEG-508 (docs/methodology.md "Value Pipeline", VP-6.4 / OC-7): the
  // Indexed tab ("Trade charts (as published)") opens on the four published
  // charts. Projections are available there as their Adjusted values but off
  // by default. No source is favoured. Pure in (excluded) so it is
  // unit-testable; `inputs` is accepted and ignored (the retired adjustment
  // cells used to decide it). JEG-432 R5: `excluded` is the first-load
  // exclusion set (weekly charts older than the newest week on the board).
  function defaultIndexedSourceKeys(inputs, excluded) {
    const skip = excluded instanceof Set ? excluded : new Set(excluded || []);
    return DEFAULT_INDEXED_SOURCES.filter(key => !skip.has(key));
  }
  // DEFECT 1 (2026-10-01): true when every default curve is either active or
  // was deliberately hidden by the user.
  function defaultCurvesSatisfied(inputs, activeSet, userHiddenSet, excluded) {
    return defaultIndexedSourceKeys(inputs, excluded).every(
      key => activeSet.has(key) || (userHiddenSet && userHiddenSet.has(key)));
  }
  globalThis.TradeValueCurvePause = {defaultIndexedSourceKeys, defaultCurvesSatisfied};

  // Collapse guard, pure in (peaks) so it is unit-testable without a DOM.
  // `peaks` maps an active source key to that curve's maximum value. True
  // means every active curve still has a plausible scale. An empty set is
  // vacuously true.
  function peaksAboveCollapseFloor(peaks, floor = CURVE_COLLAPSE_FLOOR) {
    const values = Object.values(peaks || {});
    if (!values.length) return true;
    return values.every(value => Number.isFinite(value) && value > floor);
  }
  globalThis.TradeValueCurveGuards = {peaksAboveCollapseFloor, CURVE_COLLAPSE_FLOOR};

  const root = typeof document !== "undefined" ? document.getElementById("curve-widget") : null;
  if (!root) return;
  const $ = selector => root.querySelector(selector);
  const canvas = $("#chart");
  const tip = $("#tip");

  // JEG-363 (2026-10-04): all legacy fixture reads delegated to product-data.js.
  // product-data.js is the ONLY module that talks to the FE contract; this
  // widget calls into its five semantic methods and transitional helpers
  // instead of touching assets/* paths or the #players-data inline island.
  function loadComparisonData() {
    // Back-compat shim: legacy callers still get a payload via this promise,
    // but the payload is the contract api.product_snapshot (frozen). All
    // deep-path reads have been removed from this file; the snapshot is only
    // used for per-source metadata (week_designated, fit_bake_id, etc.).
    if (window.TradeValueProductData && window.TradeValueProductData.initProductData) {
      return window.TradeValueProductData.initProductData().then(() => {
        // Expose the snapshot under the legacy global name so any out-of-tree
        // consumer (e.g. the inline health card) keeps working.
        const snap = window.TradeValueProductData.getSnapshot();
        window.TradeValueComparisonData = snap;
        return snap;
      });
    }
    return Promise.reject(new Error("product-data.js missing; render refused."));
  }

  let data = null;
  let canonicalByKey = new Map();
  let sourceMaps = new Map();
  let nativeSourceMaps = new Map();
  // As-published sources sort the lock order by their native published values,
  // not the reindexed chart values. Native values are the source's own
  // cross-position ranking (e.g., FantasyCalc's JSN at #3 overall). The
  // plotted Indexed values keep this order at every setting: they are the
  // natives times ONE factor per chart (JEG-482; ValueModel.
  // derivePublishedSetup, pipelines/check_rank_guard.py). Per-position
  // roster-shape factors are skipped for these sources for the same reason.
  const AS_PUBLISHED_KEYS = new Set(["usatoday", "fantasycalc", "fantasypros", "cbs"]);
  let universe = [];
  let orderedRows = [];
  let position = "ALL";
  let scoring = "ppr";
  let teams = 12;
  let rosterShape = {...DEFAULT_ROSTER};
  // The bench share in effect: the reader's override when set, else the
  // computed readout's overall share (JEG-536, ES-14). Recomputed on every
  // rebuild; DEFAULT_BENCH_SHARE only until the first one, or when the lineup
  // parameters failed to load (then the VP-2.6 slices run at it).
  let benchShare = DEFAULT_BENCH_SHARE;
  // ES-14 reader settings (es-value-001). The override is off (null) by
  // default; on, it replaces the computed share as the bench groups' weight.
  let benchShareOverride = null;
  let lineupSettings = {regularSeasonEnd: 14, playoffWeeks: [15, 17], optimizeFor: "season",
    injuryHistory: "recent", projectionConfidence: 1};
  // config/lineup_parameters.json, served as assets/lineup-parameters.json.
  let lineupConfig = null;
  let lineupConfigError = null;
  // Reader position shares (VP-4.4 / BE-2): null = none (the DDF weights
  // as computed); otherwise {QB, RB, WR, TE} fractions summing to exactly 1.
  let positionWeights = null;
  let yAxisAuto = true;
  let yLow = 0;
  let yHigh = 100;
  // VP-7.4: the default ranking, lock and curve are the blended DDF Value.
  let lockOrder = "ddf_value";
  let activeSources = new Set(DEFAULT_INDEXED_SOURCES);
  // DEFECT 1 (2026-10-01): curves the user deliberately unchecked. The
  // defaultGroupedSources regression guard must not treat a user-hidden
  // default curve as a missing default, or the next scoring/teams change
  // throws inside runRegressionGuards() before draw()/publishShared() and
  // the comparison table freezes on the old scoring with no visible error.
  let userDeselectedSources = new Set();
  // JEG-432 R5: weekly charts left off the first load because a newer week is
  // on the board (product-data getSourceFreshness().first_load_excluded).
  let firstLoadExcluded = new Set();
  // JEG-210: chart view mode (Indexed | Value above waivers | Adjusted values)
  // Restored 2026-10-03 (Jeremy): wired to vorp_views from the JEG-242 pipeline.
  // Re-restored 2026-10-04: the JEG-325 strangler refactor dropped this block;
  // the view tabs are a shipped feature (QA'd 2026-10-04), not migration scope.
  const VIEW_MODE_DEFS = {
    indexed: { title: "Indexed", viewKey: null },
    vorp: { title: "VORP vs waivers" },
    adj: { title: "Adjusted values", viewKey: "adj_values" }
  };
  const VIEW_MODE_ORDER = ["indexed", "vorp", "adj"];
  // JEG-242: resolve the vorp_views data key for a view mode.
  // "indexed" -> null (no lookup); "adj" -> explicit viewKey; otherwise the mode key itself.
  // The "vorp" literal appears only in VIEW_MODE_ORDER (JEG-225 exemption); never in copy.
  function getViewKey(mode) {
    const def = VIEW_MODE_DEFS[mode];
    if (!def || def.viewKey === null) return null;
    return def.viewKey || mode;
  }
  let viewMode = "indexed";
  // JEG-210: the user's source selection before entering a non-indexed view,
  // restored when they return to Indexed.
  let savedActiveSourcesForView = null;
  // The curves the user hid in the Indexed selection, parked with it.
  let savedUserDeselectedForView = null;
  let hideZeroTail = false;
  let zoomLow = 1;
  let zoomHigh = 1;
  let crossRank = null;
  let geometry = null;

  const clampValue = value => {
    if (value === null || value === undefined || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? Math.max(0, number) : null;
  };
  const scoreLabel = () => SCORINGS.find(([key]) => key === scoring)?.[1] || scoring;
  const scoringButtonLabel = key => key === "ppr" ? "Full" : key === "half_ppr" ? "Half" : "Standard";
  const formatOne = value => Number.isFinite(Number(value)) ? Number(value).toFixed(1) : "—";
  const formatTwo = value => Number.isFinite(Number(value)) ? Number(value).toFixed(2) : "—";
  // GAP-043 / GAP-CHART-STALE-LABEL-CALENDAR: every week label and stale flag
  // reads the one freshness record (product-data getSourceFreshness():
  // week_designated, then content_vintage, on the Tuesday-flip content
  // calendar of pipelines/nfl_week.py). No local week rule, no fallback to a
  // global week: a series nothing dates gets no week label.
  function sourceFreshness() {
    try {
      return window.TradeValueProductData?.getSourceFreshness?.() || null;
    } catch (error) {
      return null;
    }
  }
  const freshnessRow = key => sourceFreshness()?.series?.[key] || null;
  function freshnessText(key) {
    const label = window.TradeValueProductData?.freshnessLabel;
    return label ? label(freshnessRow(key)).text : "";
  }

  function weekForSource(key) {
    if (!WEEKED_SOURCE_KEYS.has(key)) return null;
    const week = freshnessRow(key)?.vintage_week;
    return Number.isFinite(week) ? week : null;
  }

  // The content week the reader is in (Tuesday flip), not a build-time rule.
  function activeReferenceWeek() {
    return sourceFreshness()?.current_content_week || null;
  }

  const sourceIsStale = key => WEEKED_SOURCE_KEYS.has(key) && freshnessRow(key)?.status === "older";

  function sourceLabel(key) {
    const base = SOURCE_LABELS[key] || key;
    const week = weekForSource(key);
    if (!week || key === "espn") return base;
    return `${base} Wk ${week}`;
  }
  const lockLabel = key => key === "disagreement" ? "Largest disagreement" : `${sourceLabel(key)} value`;
  const flexEligiblePositions = () => [...DEFAULT_FLEX_ELIGIBLE];
  const isPosition = player => position === "ALL" || (position === "FLEX" ? flexEligiblePositions().includes(player.pos) : player.pos === position);
  const visibleSourceKeys = () => [...SOURCE_KEYS, ...EXTRA_SOURCE_KEYS, ...PURE_VORP_KEYS];
  const sourceAvailable = key => sourceMaps.get(key)?.size > 0 && sourceComboExists(key);
  const activeSourceKeys = () => visibleSourceKeys().filter(key => activeSources.has(key) && sourceAvailable(key));
  const isLockKey = key => ["disagreement", COMPOSITE_KEY, ...SOURCE_KEYS, ...EXTRA_SOURCE_KEYS, ...PURE_VORP_KEYS].includes(key);
  // VP-7.4: the default lock is the blended DDF Value.
  const defaultValueLock = () => COMPOSITE_KEY;
  const sourceValidationStatus = key => {
    // JEG-363: source validation lives on api.product_snapshot.source_validation.
    const sv = (typeof window !== "undefined" && window.TradeValueProductData)
      ? window.TradeValueProductData.getSnapshot().source_validation
      : null;
    return key === "cbs_adjusted" ? sv?.cbs : sv?.[key];
  };
  // GAP-MISSING-SECTION-REFUSES-RENDER: a source whose whole section is
  // absent from the fixture is dropped by product-data. It is listed, greyed
  // out and labelled unavailable; it never draws and never reads as zero.
  // VP-1.6: no source's absence refuses the render, ESPN's included.
  const sourceMissingFromData = key => {
    const missing = (typeof window !== "undefined" && window.TradeValueProductData?.getMissingSources)
      ? window.TradeValueProductData.getMissingSources() : [];
    return missing.includes(key);
  };
  function comboKey(key) {
    if (PURE_VORP_KEYS.includes(key)) return null;
    return ValueModel.sourceComboKey(key, scoring, teams, 1);
  }

  function buildCanonicalMap() {
    // JEG-363 (2026-10-04): canonical players come from product-data.js
    // (api.players surface). The inline #players-data island is read only by
    // product-data.js; the widget never touches it.
    const players = (typeof window !== "undefined" && window.TradeValueProductData)
      ? window.TradeValueProductData.getPlayers()
      : [];
    const map = new Map();
    players.forEach(player => {
      const playerKey = Number(player.player_key);
      const name = String(player.canonical_name || player.full_name || player.name || "").trim();
      if (!Number.isInteger(playerKey) || !name || !CHART_POSITIONS.includes(player.pos)) return;
      map.set(playerKey, {
        player_key: playerKey,
        name,
        team: String(player.team || "—"),
        pos: player.pos,
        espn_ppg: player.espn_ppg || null,
        rz_ppg: player.rz_ppg || null,
        cbsros_ppg: player.cbsros_ppg || null,
        projectionSource: player.espn_ppg ? "ESPN" : null,
        // GAP-025: ESPN projects 0 (injured/out); not set when ESPN has no row.
        espnProjectsZero: player.espn_projects_zero === true,
        // JEG-502: roster status from the active NFL universe (bake_players.py).
        roster_status: player.roster_status || null,
        roster_status_label: player.roster_status_label || null,
        roster_status_inferred: player.roster_status_inferred === true,
        injury_status: player.injury_status || null,
        depth_chart_position: player.depth_chart_position || null,
        depth_chart_order: Number.isFinite(Number(player.depth_chart_order)) && player.depth_chart_order !== null
          ? Number(player.depth_chart_order) : null,
        sleeper_id: player.sleeper_id || null,
        universe_only: player.universe_only === true,
        unpriced_reason: player.unpriced_reason || null,
      });
    });
    return map;
  }

  // Frame 22: never compute a spread across unlike units. VORP vs waivers
  // series -- the raw *_vorp curves always, and the published charts while
  // the VORP vs waivers view is on -- are not on the trade-value point scale
  // the Indexed and Adjusted series share, so they stay out of the spread.
  const spreadSourceKeys = () => visibleSourceKeys().filter(key => !PURE_VORP_KEYS.includes(key)
    && !(viewMode === VIEW_MODE_ORDER[1] && AS_PUBLISHED_KEYS.has(key)));

  function disagreement(row) {
    const values = spreadSourceKeys().map(key => row.values[key]).filter(Number.isFinite);
    return values.length >= 2 ? Math.max(...values) - Math.min(...values) : null;
  }

  function orderComparator(a, b) {
    const aValue = lockOrder === "disagreement" ? disagreement(a)
      : AS_PUBLISHED_KEYS.has(lockOrder) ? nativeSourceMaps.get(lockOrder)?.get(a.player_key)
      : a.values[lockOrder];
    const bValue = lockOrder === "disagreement" ? disagreement(b)
      : AS_PUBLISHED_KEYS.has(lockOrder) ? nativeSourceMaps.get(lockOrder)?.get(b.player_key)
      : b.values[lockOrder];
    const aMissing = !Number.isFinite(aValue);
    const bMissing = !Number.isFinite(bValue);
    if (aMissing !== bMissing) return aMissing ? 1 : -1;
    if (!aMissing && aValue !== bValue) return bValue - aValue;
    return ValueModel.stableTiebreak(a, b);
  }

  function scoringField() {
    return scoring === "ppr" ? "ppr" : scoring === "half_ppr" ? "half_ppr" : "standard";
  }

  function rosterIsDefault() {
    return Object.keys(DEFAULT_ROSTER).every(key => Number(rosterShape[key]) === Number(DEFAULT_ROSTER[key]));
  }

  // The charts' saved setup (12 teams, standard roster). Every other setting
  // is the same natives deconstructed at the reader's league (VP-9): the
  // values are labelled derived there.
  const onSavedSetup = () => ValueModel.isSavedSetup(teams, rosterShape);
  const rosterSignature = () => Object.keys(DEFAULT_ROSTER).map(key => `${key}${rosterShape[key]}`).join("");

  function savedPublishedRow(key, view) {
    return window.TradeValueProductData.getPlayerValues({
      source: key, scoring, teams: ValueModel.SAVED_SETUP_TEAMS, qbVariant: "qb1", view,
    });
  }

  // A published chart's saved 12-team native values at this scoring. With a
  // superflex slot on the roster, the publisher's own superflex / 2-QB values
  // (saved as `native_superflex`, same units) replace its 1-QB values where it
  // publishes them (VP-0 "Superflex"). Where it publishes none, the 1-QB
  // values go through the league math unchanged (JEG332-SUPERFLEX-FLEX).
  function savedPublishedNative(key) {
    const native = new Map();
    const take = row => row?.values?.forEach((rawValue, playerKey) => {
      const value = Number(rawValue);
      if (canonicalByKey.has(playerKey) && Number.isFinite(value)) native.set(playerKey, value);
    });
    take(savedPublishedRow(key, "native"));
    if (native.size && ValueModel.superflexCount(rosterShape)) take(savedPublishedRow(key, "native_superflex"));
    return native;
  }

  // Which published charts carry their own superflex values (for the note).
  function publishesSuperflex(key) {
    return Boolean(savedPublishedRow(key, "native_superflex")?.values?.size);
  }

  // =====================================================================
  // Value pipeline (JEG-508; docs/methodology.md "Value Pipeline
  // (source-neutral, 2026-10-09)", VP-0..VP-11). Every number the chart and
  // the rows show comes from ValueModel.runValuePipeline: each source's
  // natives -> value above waivers -> its own weights (bench fixed at the
  // bench share) -> the averaged DDF weights -> the fixed league pie ->
  // Adjusted values; DDF Value = the mean of Adjusted values; Indexed = each
  // chart's natives times one factor against blended DDF Value. No source is
  // an anchor: a missing ESPN is dropped like any other source (VP-1.6).
  // =====================================================================
  const PIPELINE_SOURCE_KEYS = ["espn", "cbsros", "razzball", "fantasycalc", "usatoday", "fantasypros", "cbs"];
  const PROJECTION_SOURCE_KEYS = ["espn", "cbsros", "razzball"];
  const PPG_FIELD_OF = {espn: "espn_ppg", cbsros: "cbsros_ppg", razzball: "rz_ppg"};
  const PROJECTION_NAMES = {espn: "ESPN", cbsros: "CBS rest of season", razzball: "Razzball"};
  // The label a pipeline reason names a source by ("<label> doesn't price QB").
  const pipelineLabel = key => PROJECTION_NAMES[key] || SOURCE_LABELS[key] || key;
  const familyOf = key => PROJECTION_SOURCE_KEYS.includes(key) ? "projection" : "chart";
  // The pipeline source behind a series: a source key itself, a deprecated
  // "*_adjusted" alias, or a projection's "*_vorp" series.
  const seriesSource = key => PIPELINE_SOURCE_KEYS.includes(key) ? key
    : COMPOSITE_INPUT_ALIASES[key] || (PURE_VORP_KEYS.includes(key) ? key.slice(0, -5) : null);
  // Which pipeline value a series shows in a view (VP-11): a chart shows
  // Indexed / VORP vs waivers / Adjusted by tab; a projection shows its
  // Adjusted values; a "*_vorp" series its VORP vs waivers; a "*_adjusted"
  // alias its chart's Adjusted values.
  function seriesField(key, view = viewMode) {
    if (PURE_VORP_KEYS.includes(key)) return "vorp";
    if (ADJUSTED_INDEXED_KEYS.includes(key)) return "adjusted";
    if (AS_PUBLISHED_KEYS.has(key)) return view === "vorp" ? "vorp" : view === "adj" ? "adjusted" : "indexed";
    return "adjusted";
  }

  // The reader's league as the pipeline's setting (VP-0 "League setting L").
  function pipelineSetting() {
    return {
      teams,
      slots: {QB: rosterShape.QB, RB: rosterShape.RB, WR: rosterShape.WR, TE: rosterShape.TE},
      flex: rosterShape.FLEX,
      superflex: ValueModel.superflexCount(rosterShape),
      bench_per_team: rosterShape.BENCH,
      // Slices (no lineup parameters): the override or the 15% default.
      bench_share: benchShareOverride ?? DEFAULT_BENCH_SHARE,
      bench_share_override: benchShareOverride,
      position_shares: positionWeights ? {...positionWeights} : null,
    };
  }

  // ES-14: the reader's settings as derive_lineup_parameters.resolve()
  // arguments, and the resolved parameters the pipeline prices with (null
  // when the parameters file did not load: the slices run instead).
  function lineupResolveArgs() {
    return {
      objective: lineupSettings.optimizeFor,
      injury_history: lineupSettings.injuryHistory,
      league_weeks: {regular_season_end: lineupSettings.regularSeasonEnd,
        playoff_weeks: [...lineupSettings.playoffWeeks]},
      projection_confidence: lineupSettings.projectionConfidence,
    };
  }
  function resolvedLineup() {
    if (!lineupConfig) return null;
    try {
      return ValueModel.resolveLineupParameters(lineupConfig, lineupResolveArgs());
    } catch (error) {
      lineupConfigError = error;
      return null;
    }
  }
  async function loadLineupConfig() {
    try {
      const response = await fetch("assets/lineup-parameters.json");
      if (!response.ok) throw new Error(`assets/lineup-parameters.json request failed (${response.status})`);
      const cfg = await response.json();
      if (cfg?.schema !== "lineup-parameters-config/2") throw new Error(`unexpected schema ${cfg?.schema}`);
      lineupConfig = cfg;
      const d = cfg.defaults || {};
      lineupSettings = {
        regularSeasonEnd: d.league_weeks?.regular_season_end ?? 14,
        playoffWeeks: [...(d.league_weeks?.playoff_weeks || [15, 17])],
        optimizeFor: d.objective || "season",
        injuryHistory: d.injury_history || "recent",
        projectionConfidence: d.projection_confidence ?? 1,
      };
    } catch (error) {
      // A warning, not a stop (CLAUDE.md): the page prices with the VP-2.6
      // slices at the 15% default and the readout says so (method "fixed-share").
      lineupConfig = null;
      lineupConfigError = error;
      console.warn("Lineup parameters unavailable; bench share fixed at 15%:", error);
    }
  }

  let pipelinePlayersCache = null;
  function pipelinePlayers() {
    if (!pipelinePlayersCache) {
      pipelinePlayersCache = {};
      canonicalByKey.forEach((player, playerKey) => {
        pipelinePlayersCache[playerKey] = {pos: player.pos, name: player.name};
      });
    }
    return pipelinePlayersCache;
  }

  // A source's natives this week at the active scoring: a projection's
  // per-game points from the player records, a chart's saved list.
  function currentNatives(key) {
    if (familyOf(key) === "chart") return savedPublishedNative(key);
    const field = scoringField();
    const values = new Map();
    canonicalByKey.forEach((player, playerKey) => {
      // JEG-508 rulings 1 and 6: the natives are the bake's full-precision
      // per-game points at the scoring; a player ESPN marks "ineligible"
      // (espn_ppg null, injured or out) is LISTED by ESPN at 0 (JEG-496) and
      // counts as 0 in m. Only ESPN has this status.
      if (key === "espn" && player.espnProjectsZero && !player.espn_ppg) {
        values.set(playerKey, 0);
        return;
      }
      const raw = player[PPG_FIELD_OF[key]]?.[field];
      if (raw === null || raw === undefined) return;
      const ppg = Number(raw);
      if (Number.isFinite(ppg)) values.set(playerKey, ppg);
    });
    return values;
  }

  // VP-1.1: why a source is not eligible this week, or null. A source that is
  // held or not yet published is still shown (VP-1.4); one without values
  // at this setting is not run at all.
  function eligibilityReason(key, natives) {
    if (sourceMissingFromData(key)) return {reason: "missing from this build", run: false};
    if (!natives.size) return {reason: `not available for ${scoreLabel()} / ${teams} teams`, run: false};
    const block = compositeBlock(key);
    if (block) return {reason: block.reason, run: true, block};
    if (sourceValidationStatus(key) !== undefined && sourceValidationStatus(key) !== "live") {
      return {reason: "held: did not pass source validation", run: true};
    }
    return null;
  }

  // A saved week's natives for one source: {values} | {reason}.
  function weekNatives(key, week, index, doc) {
    const found = historyEntryOf(key, week, index, doc);
    if (!found.entry) return {reason: found.error || found.missing};
    const values = familyOf(key) === "projection" ? historyPpg(found.entry) : historyNatives(found.entry);
    if (!values.size) return {reason: `no ${scoreLabel()} values saved for Week ${week}`};
    return {values, entry: found.entry};
  }

  // VP-1.2 / VP-8: a source's prior-week snapshot (the week before the one it
  // serves now). {available, currentWeek, priorWeek, values, reason}.
  function priorInputFor(key) {
    let index;
    try {
      index = historyNow("index");
    } catch (error) {
      return {available: false, reason: `history could not be read: ${error.message}`};
    }
    const found = servedWeekOf(key, null, index);
    if (found.error) return {available: false, reason: found.error};
    const currentWeek = found.served.week;
    const priorWeek = currentWeek - 1;
    let doc;
    try {
      doc = historyWeekDocNow(index, priorWeek);
    } catch (error) {
      return {available: false, currentWeek, priorWeek, reason: `history could not be read: ${error.message}`};
    }
    const got = weekNatives(key, priorWeek, index, doc);
    if (!got.values) return {available: false, currentWeek, priorWeek, reason: got.reason};
    return {available: true, currentWeek, priorWeek, values: got.values};
  }

  const mapToValues = map => {
    const out = {};
    map.forEach((value, playerKey) => { out[playerKey] = value; });
    return out;
  };

  function runPipeline(nativesByKey, included, extra = {}) {
    const sources = {};
    PIPELINE_SOURCE_KEYS.forEach(key => {
      const natives = nativesByKey[key];
      if (!natives || !natives.size) return;
      sources[key] = {family: familyOf(key), status: included.includes(key) ? "included" : "excluded",
        values: mapToValues(natives), label: pipelineLabel(key)};
    });
    return ValueModel.runValuePipeline({
      setting: pipelineSetting(), players: pipelinePlayers(), sources, included,
      compositeInputs: compositeInputs ? [...compositeInputs] : null, lineup: resolvedLineup(), ...extra,
    });
  }

  // The current and prior week (VP-1, VP-8), rebuilt by computePipeline().
  let pipeline = null;
  let pipelinePrior = null;
  let pipelineNatives = {};
  let pipelineState = {eligible: [], included: [], excluded: [], priorAvailable: false, priorReason: null,
    currentWeek: null, priorWeek: null, priorBySource: {}, runReasons: {}};
  let weekPipelineCache = new Map();

  function computePipeline() {
    pipelinePlayersCache = null;
    weekPipelineCache = new Map();
    const natives = {};
    const runReasons = {};
    const excluded = [];
    const eligible = [];
    PIPELINE_SOURCE_KEYS.forEach(key => {
      const values = currentNatives(key);
      const why = eligibilityReason(key, values);
      if (why) {
        excluded.push({key, series: key, reason: why.reason, ...(why.block || {})});
        if (!why.run) { runReasons[key] = why.reason; return; }
      } else {
        eligible.push(key);
      }
      natives[key] = values;
    });
    // VP-1.2: I = the eligible sources with a prior-week snapshot, paired on
    // the newest served week; if none has one, I = the eligible sources.
    const priorBySource = {};
    eligible.forEach(key => { priorBySource[key] = priorInputFor(key); });
    const served = eligible.map(key => priorBySource[key].currentWeek).filter(Number.isInteger);
    const currentWeek = served.length ? Math.max(...served) : null;
    const paired = eligible.filter(key => priorBySource[key].available && priorBySource[key].currentWeek === currentWeek);
    const priorAvailable = paired.length > 0;
    const included = priorAvailable ? paired : [...eligible];
    if (priorAvailable) {
      eligible.filter(key => !paired.includes(key)).forEach(key => {
        const prior = priorBySource[key];
        excluded.push({key, series: key, reason: `no prior week: ${prior.available
          ? `serves Week ${prior.currentWeek}, not Week ${currentWeek}` : prior.reason}`});
      });
    }
    pipelineNatives = natives;
    pipeline = runPipeline(natives, included);
    // ES-14: the bench share in effect is an output unless overridden.
    benchShare = benchShareOverride ?? pipeline.benchShare?.overall ?? DEFAULT_BENCH_SHARE;
    pipelineState = {
      eligible, included,
      excluded: PIPELINE_SOURCE_KEYS.map(key => excluded.find(e => e.key === key)).filter(Boolean),
      priorAvailable,
      priorReason: priorAvailable ? null : (eligible.length
        ? `no source has a prior week at this setting (${eligible.map(key => `${key}: ${priorBySource[key].reason}`).join("; ")})`
        : "no source is available at this setting"),
      currentWeek: priorAvailable ? currentWeek : (currentWeek ?? activeReferenceWeek()),
      priorWeek: priorAvailable ? currentWeek - 1 : null,
      priorBySource, runReasons,
    };
    // VP-8: the prior week on the prior inputs, the same I, league and pie.
    pipelinePrior = null;
    if (priorAvailable) {
      const run = weekPipeline(currentWeek - 1);
      pipelinePrior = run.result || null;
    }
  }

  // One saved week priced on that week's inputs with the current league,
  // included set and pie (VP-8); the served week too (read back from its
  // saved inputs, so it reproduces the live values only when the history
  // saved what is served). Every source the current week runs is run
  // on its own snapshot of that week when it has one; sources in I without
  // the week drop out (listed in `dropped`). Sources outside I are shown,
  // never counted. {result, dropped} | {reason, dropped}.
  function weekPipeline(week) {
    week = Number(week);
    const cacheKey = String(week);
    if (weekPipelineCache.has(cacheKey)) return weekPipelineCache.get(cacheKey);
    let result;
    {
      let index, doc;
      try {
        index = historyNow("index");
        doc = historyWeekDocNow(index, week);
      } catch (error) {
        result = {reason: `history could not be read: ${error.message}`, dropped: []};
      }
      if (!result) {
        const natives = {};
        const dropped = [];
        Object.keys(pipeline.sources).forEach(key => {
          const got = weekNatives(key, week, index, doc);
          if (got.values) natives[key] = got.values;
          else dropped.push({source: key, reason: got.reason});
        });
        const included = pipelineState.included.filter(key => natives[key]);
        result = Object.keys(natives).length
          ? {result: runPipeline(natives, included, {pie: pipeline.pie}), dropped}
          : {reason: `no source has Week ${week} saved`, dropped};
      }
    }
    weekPipelineCache.set(cacheKey, result);
    return result;
  }

  // One series' values from a pipeline result, in a view: Map player_key ->
  // value over every row that has a number (zeros included).
  function seriesValuesFrom(result, key, view = viewMode) {
    const source = seriesSource(key);
    const field = seriesField(key, view);
    const out = new Map();
    if (!result || !source || !result.sources[source]) return out;
    Object.entries(result.rows).forEach(([playerKey, row]) => {
      const value = row[field]?.[source];
      if (typeof value === "number" && Number.isFinite(value)) out.set(Number(playerKey), value);
    });
    return out;
  }

  // The reason a series has no value for a player (VP-6.2, VP-11).
  function pipelineReason(key, playerKey, result = pipeline) {
    const source = seriesSource(key);
    if (!source) return "No value for this player";
    if (!result?.sources?.[source]) {
      const why = pipelineState.runReasons[source];
      if (why === "missing from this build") return "Missing from this build";
      return `Not available for ${scoreLabel()} / ${teams} teams`;
    }
    const row = result.rows[playerKey];
    if (!row) {
      if (familyOf(source) === "projection") return `${pipelineLabel(source)} doesn't project this player`;
      return `Below rosterable depth; ${pipelineLabel(source)} doesn't list him`;
    }
    if (seriesField(key) === "indexed" && result.sources[source].indexedFactor === null) return "Not enough shared players to index";
    return row.reasons[source] || "No value for this player";
  }

  const pipelineAvailable = key => seriesValuesFrom(pipeline, key).size > 0;
  // Every sourceMaps-backed series is available when the pipeline prices it.
  const sourceComboExists = key => Boolean(seriesSource(key) && pipeline?.sources?.[seriesSource(key)]);

  // Slot fill (VP-7.2): the league allocation; with no projection in I, the
  // allocation on blended DDF Value.
  function slotFill() {
    return pipeline?.slotFill || null;
  }

  // ---- DDF Value (VP-6.3) ----
  // null = every included source; otherwise the reader's chosen sources
  // (setCompositeInputs), kept across league changes. The choice narrows
  // only the DDF averaging (VP-1.5), never I, the weights or any series.
  let compositeInputs = null;
  let compositeMap = new Map();
  const COMPOSITE_MIN_SOURCES = 1;
  const COMPOSITE_NONE_REASON = "No source prices this player";
  const COMPOSITE_EMPTY_REASON = "No source available this week";
  const COMPOSITE_ONE_SOURCE_NOTE = "Only one source prices this player";
  const COMPOSITE_PROJECTION_INPUTS = ["espn", "cbsros", "razzball"];
  const COMPOSITE_CHART_INPUTS = ["fantasycalc", "usatoday", "fantasypros", "cbs"];
  const COMPOSITE_VERSIONS = {
    ddf_value: COMPOSITE_INPUT_KEYS,
    ddf_value_charts: COMPOSITE_CHART_INPUTS,
    ddf_value_projections: COMPOSITE_PROJECTION_INPUTS,
  };
  const COMPOSITE_VERSION_KEYS = Object.keys(COMPOSITE_VERSIONS);
  const isCompositeKey = key => COMPOSITE_VERSION_KEYS.includes(key);
  // The short names of the versions (VP-11): row.ddfByVersion keys, and
  // accepted by getCompositeInputs / getCompositeValues.
  const COMPOSITE_VERSION_NAMES = {ddf_value: "blended", ddf_value_charts: "charts", ddf_value_projections: "projections"};
  const compositeVersionOf = key => isCompositeKey(key) ? key
    : (COMPOSITE_VERSION_KEYS.find(version => COMPOSITE_VERSION_NAMES[version] === key) || COMPOSITE_KEY);
  // "Not yet published for the current week": the stale flag (a weekly chart
  // older than the current content week) or the first-load rule (JEG-432 R5).
  // Projections carry no week and are always current.
  const compositeKeyOlderWeek = key => sourceIsStale(key) || firstLoadExcluded.has(key);
  // JEG-479: a source held for the week is held with every series derived
  // from it. A hold is a section field the pipeline writes:
  //   validationHold: {reason, week, root, kept_week}
  //   promotionHold: {reason, week}
  const HOLD_FIELDS = ["validationHold", "promotionHold"];
  const HOLD_DERIVED_SERIES = {
    espn: ["espn_vorp"],
    cbsros: ["cbsros_vorp"],
    razzball: ["razzball_vorp"],
    fantasycalc: ["fantasycalc_adjusted"],
    usatoday: ["usatoday_adjusted"],
    fantasypros: ["fantasypros_adjusted"],
    cbs: ["cbs_adjusted"],
  };
  function sectionHold(sectionKey) {
    const section = data?.sources?.[sectionKey];
    if (!section || typeof section !== "object") return null;
    for (const field of HOLD_FIELDS) {
      const hold = section[field];
      if (!hold) continue;
      const reason = typeof hold === "object" && hold.reason ? String(hold.reason)
        : typeof hold === "string" ? hold : field;
      const detail = typeof hold === "object" ? hold : {};
      return {field, reason, week: detail.week ?? null, root: detail.root ?? null,
        keptWeek: detail.kept_week ?? null, source: sectionKey};
    }
    return null;
  }
  // The hold on a source: its own section's, else one on a section derived
  // from it (a hold on either holds both).
  function seriesHold(key) {
    const own = sectionHold(key);
    if (own) return own;
    for (const derived of HOLD_DERIVED_SERIES[key] || []) {
      const hold = sectionHold(derived);
      if (hold) return hold;
    }
    const base = Object.keys(HOLD_DERIVED_SERIES).find(source => HOLD_DERIVED_SERIES[source].includes(key));
    return base ? sectionHold(base) : null;
  }
  const compositeKeyHeld = key => seriesHold(key) !== null;
  // Why a source can never be an input this week (held, or not yet
  // published for the current week), or null.
  function compositeBlock(key) {
    const hold = seriesHold(key);
    if (hold) {
      return {key, reason: `held: ${hold.reason}`, heldBy: hold.source, holdField: hold.field, holdWeek: hold.week,
        holdRoot: hold.root, holdKeptWeek: hold.keptWeek};
    }
    if (compositeKeyOlderWeek(key)) {
      const week = activeReferenceWeek();
      return {key, reason: week ? `not yet published for week ${week}` : "not yet published for the current week",
        notPublished: true};
    }
    return null;
  }
  const normalizeInputKey = key => COMPOSITE_INPUT_ALIASES[key] || key;
  // The sources of one version that feed its DDF Value (I narrowed by family
  // and the reader's selection).
  function versionInputs(version) {
    const family = COMPOSITE_VERSIONS[version];
    return pipelineState.included.filter(key => family.includes(key)
      && (!compositeInputs || compositeInputs.includes(key)));
  }
  // JEG-484: product-data's per-asset load outcome (read-only).
  const productLoadStatus = () => window.TradeValueProductData?.getLoadStatus?.() || {assets: {}, adjustmentsLoaded: false};
  function compositeInputsInfo(version = COMPOSITE_KEY) {
    version = compositeVersionOf(version);
    const family = COMPOSITE_VERSIONS[version];
    const inputs = versionInputs(version);
    const excluded = [];
    family.forEach(key => {
      if (inputs.includes(key)) return;
      const entry = pipelineState.excluded.find(e => e.key === key);
      if (entry) excluded.push({...entry});
      else if (compositeInputs && !compositeInputs.includes(key)) excluded.push({key, series: key, reason: "not selected"});
    });
    return {
      version,
      inputs,
      series: [...inputs],
      requested: compositeInputs ? [...compositeInputs] : null,
      isDefault: compositeInputs === null,
      defaults: [...pipelineState.included],
      allowed: [...COMPOSITE_INPUT_KEYS],
      excluded,
      held: COMPOSITE_INPUT_KEYS.filter(compositeKeyHeld),
      notPublished: COMPOSITE_INPUT_KEYS.filter(key => compositeBlock(key)?.notPublished),
      currentWeek: pipelineState.currentWeek,
      priorWeek: pipelineState.priorWeek,
      priorAvailable: pipelineState.priorAvailable,
      priorReason: pipelineState.priorReason,
      minSources: COMPOSITE_MIN_SOURCES
    };
  }
  // The row's DDF fields from the pipeline (VP-6.3, VP-11): values[version],
  // ddfByVersion[blended | charts | projections] = {value, count, sources,
  // reason, lowConfidence, confidenceNote, prior, priorCount,
  // priorLowConfidence}, the flat blended fields, and ddfTier (VP-7.3).
  function setCompositeFields(row) {
    if (!row.missingReasons) row.missingReasons = {};
    const now = pipeline?.rows?.[row.player_key];
    const before = pipelinePrior?.rows?.[row.player_key];
    row.ddfByVersion = Object.fromEntries(COMPOSITE_VERSION_KEYS.map(version => {
      const name = COMPOSITE_VERSION_NAMES[version];
      const cur = now?.ddfByVersion?.[name];
      const pri = before?.ddfByVersion?.[name];
      const value = cur && Number.isFinite(cur.value) ? cur.value : null;
      const count = cur ? cur.count : 0;
      const reason = value !== null ? null
        : (!pipelineState.included.length ? COMPOSITE_EMPTY_REASON : COMPOSITE_NONE_REASON);
      const entry = {value, count, sources: cur ? [...cur.sources] : [], reason,
        lowConfidence: count === 1,
        confidenceNote: count === 1 ? COMPOSITE_ONE_SOURCE_NOTE : null,
        prior: pri && Number.isFinite(pri.value) ? pri.value : null,
        priorCount: pri ? pri.count : 0,
        priorLowConfidence: Boolean(pri && pri.count === 1)};
      row.values[version] = entry.value;
      if (entry.value === null) row.missingReasons[version] = entry.reason;
      else delete row.missingReasons[version];
      return [name, entry];
    }));
    const {blended: blend, charts, projections} = row.ddfByVersion;
    row.ddfCount = blend.count;
    row.ddfChartsCount = charts.count;
    row.ddfProjectionsCount = projections.count;
    row.ddfSources = [...blend.sources];
    row.ddfReason = blend.reason;
    row.ddfLowConfidence = blend.lowConfidence;
    row.ddfConfidenceNote = blend.confidenceNote;
    row.ddfChartsLowConfidence = charts.lowConfidence;
    row.ddfProjectionsLowConfidence = projections.lowConfidence;
    row.ddfPrior = blend.prior;
    row.ddfPriorCount = blend.priorCount;
    row.ddfPriorLowConfidence = blend.priorLowConfidence;
    row.ddfTier = now ? now.tier : null;
    // ES-10 (JEG-536): the expected lineup share of his surplus and P(level
    // above the starter line), blended over the included sources; null
    // without lineup parameters or when no included source has him.
    row.lineupShare = now && Number.isFinite(now.lineupShare) ? now.lineupShare : null;
    row.startWorthy = now && Number.isFinite(now.startWorthy) ? now.startWorthy : null;
    return blend;
  }
  function applyComposite(rows) {
    compositeMap = new Map();
    rows.forEach(row => {
      const blend = setCompositeFields(row);
      if (blend.value !== null) compositeMap.set(row.player_key, blend.value);
    });
  }
  // getCompositeValues([version]): one version's DDF Value for both weeks as
  // plain objects keyed by player_key, over every player either week prices.
  function compositeValuesInfo(version = COMPOSITE_KEY) {
    version = compositeVersionOf(version);
    if (!pipeline) return null;
    const name = COMPOSITE_VERSION_NAMES[version];
    const pick = result => {
      const values = {}, counts = {};
      Object.entries(result?.rows || {}).forEach(([playerKey, row]) => {
        const entry = row.ddfByVersion[name];
        if (!Number.isFinite(entry.value)) return;
        values[playerKey] = entry.value;
        counts[playerKey] = entry.count;
      });
      return {values, counts};
    };
    const now = pick(pipeline);
    const before = pipelinePrior ? pick(pipelinePrior) : null;
    const inputs = versionInputs(version);
    return {version, inputs, series: [...inputs], currentWeek: pipelineState.currentWeek,
      priorWeek: pipelineState.priorWeek, priorAvailable: pipelineState.priorAvailable, priorReason: pipelineState.priorReason,
      current: now.values, currentCounts: now.counts,
      prior: before ? before.values : null, priorCounts: before ? before.counts : null,
      minSources: COMPOSITE_MIN_SOURCES};
  }
  // getSourceInfo({includeComposite: true}) entries, one per version.
  const COMPOSITE_LABELS = {ddf_value: ["DDF Value", "DDF Value"],
    ddf_value_charts: ["DDF Value · trade charts", "DDF Value, trade charts only"],
    ddf_value_projections: ["DDF Value · projections", "DDF Value, projections only"]};
  function compositeSourceInfo(version = COMPOSITE_KEY) {
    const inputs = versionInputs(version);
    const name = COMPOSITE_VERSION_NAMES[version];
    return {
      key: version,
      label: COMPOSITE_LABELS[version][0],
      longLabel: COMPOSITE_LABELS[version][1],
      composite: true,
      inputs,
      series: [...inputs],
      isDefault: compositeInputs === null,
      week: pipelineState.currentWeek ?? activeReferenceWeek(),
      priorWeek: pipelineState.priorWeek,
      stale: false,
      available: Object.values(pipeline?.rows || {}).some(row => Number.isFinite(row.ddfByVersion[name].value)),
      paused: false,
      unavailable: false,
      active: false,
      color: null,
      waiverNote: null,
      waiver: null
    };
  }
  const compositeAvailable = () => compositeMap.size > 0;
  const lockSourceAvailable = key => isCompositeKey(key) ? compositeSourceInfo(key).available : sourceAvailable(key);
  // A copy of an engine row for the read-only accessors.
  const rowCopy = row => ({...row, values: {...row.values}, ddfSources: [...(row.ddfSources || [])],
    missingReasons: {...(row.missingReasons || {})}, estimated: {...(row.estimated || {})},
    ddfByVersion: Object.fromEntries(Object.entries(row.ddfByVersion || {}).map(([version, entry]) =>
      [version, {...entry, sources: [...entry.sources]}]))});

  // One player's row from the pipeline: values per series in the active view,
  // a reason for every null (VP-6.2), and `estimated: {sourceKey: reason}`
  // for every chart value that comes from the fill-in (VP-2.4, VP-11).
  function buildRow(player) {
    const pipelineRow = pipeline?.rows?.[player.player_key] || null;
    const values = {};
    const missingReasons = {};
    visibleSourceKeys().forEach(key => {
      let value = sourceMaps.get(key)?.get(player.player_key);
      // VP-6.2: a player no source lists has no pipeline row; a chart that
      // prices his position still shows 0 for him (below rosterable depth).
      const source = seriesSource(key);
      if (value === undefined && !pipelineRow && source && familyOf(source) === "chart"
          && pipeline?.sources?.[source]?.positions?.[player.pos]?.method !== undefined
          && pipeline.sources[source].positions[player.pos].method !== "no_players"
          && !(seriesField(key) === "indexed" && pipeline.sources[source].indexedFactor === null)) {
        value = 0;
      }
      if (value === undefined) {
        values[key] = null;
        missingReasons[key] = pipelineReason(key, player.player_key);
      } else {
        values[key] = value;
        if (value === 0 && !pipelineRow) missingReasons[key] = pipelineReason(key, player.player_key);
      }
    });
    const estimated = {};
    if (pipelineRow) {
      Object.entries(pipelineRow.estimated).forEach(([source, reason]) => {
        estimated[source] = reason;
        ADJUSTED_INDEXED_KEYS.filter(key => COMPOSITE_INPUT_ALIASES[key] === source).forEach(key => { estimated[key] = reason; });
      });
    }
    const row = {...player, values, missingReasons, estimated, meanPpg: pipelineRow ? pipelineRow.meanPpg : null};
    setCompositeFields(row);
    return row;
  }

  // JEG-502 (lazy): a player no source prices (universe_only) is not one of
  // the computed rows. searchPlayers/getPlayer build his row on demand with
  // the same rules (VP-6.2); a computed player's row is a copy of the engine's.
  function playerRow(playerKey) {
    const key = Number(playerKey);
    const computed = universe.find(row => row.player_key === key);
    if (computed) return rowCopy(computed);
    const player = canonicalByKey.get(key);
    if (!player || !POSITION_ORDER.includes(player.pos)) return null;
    return {...buildRow(player), materialized: true};
  }
  const searchKey = text => String(text || "").normalize("NFD").replace(/[̀-ͯ]/g, "")
    .toLowerCase().replace(/[.'’]/g, "").replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim();
  // Every player in players.json whose name contains the query (accents and
  // punctuation ignored): exact name, then name start, then a word start, then
  // anywhere; priced players before unpriced ones, then by name.
  function searchPlayers(query, {limit = 20} = {}) {
    const needle = searchKey(query);
    if (!needle) return [];
    const hits = [];
    canonicalByKey.forEach((player, playerKey) => {
      if (!POSITION_ORDER.includes(player.pos)) return;
      const name = searchKey(player.name);
      const at = name.indexOf(needle);
      if (at < 0) return;
      const rank = name === needle ? 0 : at === 0 ? 1 : name.includes(` ${needle}`) ? 2 : 3;
      hits.push({playerKey, rank, unpriced: player.universe_only ? 1 : 0, name: player.name});
    });
    hits.sort((a, b) => a.rank - b.rank || a.unpriced - b.unpriced || a.name.localeCompare(b.name) || a.playerKey - b.playerKey);
    return hits.slice(0, Math.max(0, Number(limit) || 0)).map(hit => playerRow(hit.playerKey)).filter(Boolean);
  }

  function rebuildDomain() {
    computePipeline();
    sourceMaps = new Map();
    visibleSourceKeys().forEach(key => sourceMaps.set(key, seriesValuesFrom(pipeline, key)));
    // As-published charts sort a lock by their own natives (the order the
    // Indexed values keep exactly, VP-6.4).
    nativeSourceMaps = new Map();
    AS_PUBLISHED_KEYS.forEach(key => nativeSourceMaps.set(key, pipelineNatives[key] || new Map()));
    // VP-6.1: every player any source lists gets a row (held sources too).
    universe = Object.keys(pipeline.rows).map(Number)
      .map(playerKey => canonicalByKey.get(playerKey))
      .filter(Boolean)
      .map(player => buildRow(player));
    applyComposite(universe);
    orderedRows = universe.filter(row => isPosition(row)).sort(orderComparator);
    syncPlayerOptions();
    syncContext();
    notifyRowsChanged();
  }

  // The main page's comparison table renders these rows, not a copy of the
  // value math (GAP-MAIN-TABLE-ESPN-DRIFT). It reads getAllRows() once init
  // has finished (isReady) and again after every rebuild, signalled here.
  let engineReady = false;
  function notifyRowsChanged() {
    if (engineReady) window.dispatchEvent(new CustomEvent("trade-value-rows-change"));
  }

  function displayRows() {
    if (!hideZeroTail) return orderedRows;
    const tailKey = selectedRankSourceKey();
    let lastPriced = -1;
    orderedRows.forEach((row, index) => {
      if (Number.isFinite(row.values[tailKey]) && row.values[tailKey] > 0) lastPriced = index;
    });
    return lastPriced >= 0 ? orderedRows.slice(0, lastPriced + 1) : orderedRows.slice(0, 1);
  }

  function selectedRankSourceKey() {
    if (isCompositeKey(lockOrder) && lockSourceAvailable(lockOrder)) return lockOrder;
    if (visibleSourceKeys().includes(lockOrder) && sourceAvailable(lockOrder)) return lockOrder;
    if (compositeAvailable()) return COMPOSITE_KEY;
    return activeSourceKeys()[0] || COMPOSITE_KEY;
  }

  function syncContext() {
    const context = $("#curveContext");
    if (!context) return;
    const positionLabel = position === "ALL" ? "All positions" : position === "FLEX" ? "RB / WR / TE" : position;
    const freshness = sourceFreshness();
    const referenceWeek = freshness?.first_load_reference_week;
    const weekLabel = referenceWeek ? `Week ${referenceWeek} references` : "references of unknown week";
    const rosterLabel = `${rosterShape.QB}QB/${rosterShape.RB}RB/${rosterShape.WR}WR/${rosterShape.TE}TE/${rosterShape.FLEX}FLEX/` +
      `${rosterShape.SUPERFLEX ? `${rosterShape.SUPERFLEX}SF/` : ""}${rosterShape.BENCH}BN`;
    const staleLabel = activeSourceKeys().filter(sourceIsStale)
      .map(key => ` · ${SOURCE_LABELS[key] || key}: ${freshnessText(key)}`).join("");
    const axisLabel = yAxisAuto ? "auto y-axis" : `y ${Math.round(yLow)}-${Math.round(yHigh)}`;
    const benchShareText = `${(benchShare * 100).toFixed(benchShare * 100 % 1 ? 1 : 0)}% bench share`;
    context.replaceChildren(
      `${scoreLabel()} · ${teams} teams · ${rosterLabel} · `,
      Object.assign(document.createElement("span"), {
        textContent: benchShareText,
        title: "The bench tier's share of the league pie, computed from your league settings (the Bench % override replaces it)."
      }),
      ` · ${positionLabel} · ${axisLabel} · ${weekLabel}${staleLabel} · locked to ${lockLabel(lockOrder)}`,
      // league-settings-001 / methodology.md: values derived for a league
      // setting the source did not publish must be labelled derived.
      onSavedSetup() ? "" : " · published charts derived from their 12-team, standard-roster values",
      waiverContextNote()
    );
  }

  // VP-2.4h: name the active charts that carry estimated players at this
  // setting (rosterable players they do not list, filled in and marked).
  function waiverContextNote() {
    const notes = [...AS_PUBLISHED_KEYS]
      .filter(key => activeSourceKeys().some(active => seriesSource(active) === key))
      .map(key => {
        const note = sourceWaiverNote(key);
        return note ? `${SOURCE_LABELS[key] || key} (${note})` : null;
      })
      .filter(Boolean);
    return notes.length ? ` · estimated players: ${notes.join("; ")}` : "";
  }

  // How each position's waiver line is set for a series' source at the
  // active setting (VP-2.3): {positions: {pos: {method, waiver, starterLine,
  // listed, estimated}}, estimated: [pos], short: [pos]}; null when the
  // source is not priced.
  function sourceWaiverInfo(key) {
    const source = seriesSource(key);
    const positions = pipeline?.sources?.[source]?.positions;
    if (!positions) return null;
    const out = {positions: {}, estimated: [], short: []};
    POSITION_ORDER.forEach(pos => {
      const p = positions[pos];
      out.positions[pos] = {method: p.method, waiver: p.waiver, starterLine: p.starterLine,
        listed: p.listed, estimated: p.nEstimated};
      if (p.nEstimated > 0) out.estimated.push(pos);
      if (p.method === "insufficient_coverage") out.short.push(pos);
    });
    return out;
  }
  function sourceWaiverNote(key) {
    const info = sourceWaiverInfo(key);
    if (!info) return null;
    const parts = [];
    if (info.estimated.length) {
      parts.push(`estimated players at ${info.estimated.map(pos => `${pos} (${info.positions[pos].estimated})`).join(", ")}`);
    }
    if (info.short.length) parts.push(`waiver line at the end of its list (${info.short.join(", ")})`);
    return parts.length ? parts.join("; ") : null;
  }

  function makeTabs() {
    const posTabs = $("#posTabs");
    posTabs.replaceChildren();
    POSITIONS.forEach(key => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "tab";
      button.dataset.value = key;
      button.textContent = key === "ALL" ? "All" : key === "FLEX" ? "Flex" : key;
      button.addEventListener("click", () => setPosition(key));
      posTabs.appendChild(button);
    });
    syncTabs();
  }

  function makeLeagueControls() {
    const score = $("#curveScoring");
    const team = $("#curveTeams");
    if (score) {
      score.replaceChildren();
      SCORINGS.forEach(([key, label]) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = scoringButtonLabel(key);
        button.title = label;
        button.setAttribute("aria-label", label);
        button.classList.toggle("active", scoring === key);
        button.setAttribute("aria-pressed", String(scoring === key));
        button.addEventListener("click", () => setScoring(key));
        score.appendChild(button);
      });
    }
    if (team) {
      team.replaceChildren();
      [8, 10, 12, 14].forEach(size => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = `${size}`;
        button.classList.toggle("active", teams === size);
        button.setAttribute("aria-pressed", String(teams === size));
        button.addEventListener("click", () => setTeams(size));
        team.appendChild(button);
      });
    }
  }

  // The default position shares: each position's DDF weight (starter plus
  // bench, VP-4.3) before any reader shares, from the averaged source mixes.
  function bakedPositionWeights() {
    if (!pipeline) return null;
    const base = pipeline.ddfWeightsBeforeShares;
    if (base) {
      const w = Object.fromEntries(POSITION_ORDER.map(pos => [pos, base[`${pos}|starter`] + base[`${pos}|bench`]]));
      return POSITION_ORDER.some(pos => w[pos] > 0) ? w : null;
    }
    const S = pipeline.starterMixMean, B = pipeline.benchMixMean, bs = pipeline.benchShareApplied;
    const sumS = POSITION_ORDER.reduce((s, pos) => s + S[pos], 0);
    const sumB = POSITION_ORDER.reduce((s, pos) => s + B[pos], 0);
    if (!(sumS > 0) && !(sumB > 0)) return null;
    const w = {};
    POSITION_ORDER.forEach(pos => {
      w[pos] = (sumS > 0 ? (1 - bs) * S[pos] / sumS : 0) + (sumB > 0 ? bs * B[pos] / sumB : 0);
    });
    return w;
  }

  function activePositionWeights() {
    if (positionWeights) return {...positionWeights};
    return bakedPositionWeights() || {QB: 0.25, RB: 0.25, WR: 0.25, TE: 0.25};
  }

  // Linked sliders: moving one position's share takes from (or gives to) the
  // other three proportionally, so the four shares always total exactly 100%.
  function setPositionWeight(pos, fraction) {
    if (!POSITION_ORDER.includes(pos)) return;
    const w = activePositionWeights();
    let next = Number(fraction);
    if (!Number.isFinite(next)) return;
    next = Math.min(1, Math.max(0, next));
    const delta = next - w[pos];
    if (Math.abs(delta) < 1e-9) return;
    w[pos] = next;
    const others = POSITION_ORDER.filter(p => p !== pos);
    const otherTotal = others.reduce((s, p) => s + w[p], 0);
    if (otherTotal > 1e-9) {
      others.forEach(p => { w[p] = Math.max(0, w[p] - delta * (w[p] / otherTotal)); });
    } else if (others.length) {
      const rem = Math.max(0, 1 - next);
      others.forEach(p => { w[p] = rem / others.length; });
    }
    const total = POSITION_ORDER.reduce((s, p) => s + w[p], 0);
    if (total > 1e-9) POSITION_ORDER.forEach(p => { w[p] /= total; });
    positionWeights = w;
    refreshAfterWeightChange();
  }

  function resetPositionWeights() {
    positionWeights = null;
    refreshAfterWeightChange();
  }

  function resetAllWeights() {
    positionWeights = null;
    setBenchShareOverride(null, false);
    refreshAfterWeightChange();
  }

  // JEG-452 (BE-2): programmatic position shares for the v2 Weights panel.
  // A share scales its position's DDF weights (VP-4.4); the floor keeps all four
  // priced. 1% matches the bench-share slider's floor.
  const POSITION_WEIGHT_FLOOR = 0.01;

  function positionWeightBounds() {
    if (!bakedPositionWeights()) return null;
    const hi = 1 - (POSITION_ORDER.length - 1) * POSITION_WEIGHT_FLOOR;
    return Object.fromEntries(POSITION_ORDER.map(pos => [pos, [POSITION_WEIGHT_FLOOR, hi]]));
  }

  // Lift any share in `positions` below the floor to it and take the
  // difference from that set's shares above the floor, proportionally
  // (water-fill). The set's total is unchanged.
  function liftToPositionFloor(weights, positions = POSITION_ORDER) {
    const w = {...weights};
    const setTotal = positions.reduce((s, pos) => s + w[pos], 0);
    for (let pass = 0; pass < positions.length; pass += 1) {
      const low = positions.filter(pos => w[pos] < POSITION_WEIGHT_FLOOR - 1e-12);
      if (!low.length) break;
      low.forEach(pos => { w[pos] = POSITION_WEIGHT_FLOOR; });
      const fixed = positions.filter(pos => w[pos] <= POSITION_WEIGHT_FLOOR + 1e-12);
      const rest = positions.filter(pos => !fixed.includes(pos));
      if (!rest.length) break;
      const room = setTotal - fixed.length * POSITION_WEIGHT_FLOOR;
      const restTotal = rest.reduce((s, pos) => s + w[pos], 0);
      rest.forEach(pos => { w[pos] = restTotal > 0 ? w[pos] * room / restTotal : room / rest.length; });
    }
    return w;
  }

  // setPositionWeights({QB, RB, WR, TE}, publish = true)
  //   Fractions of the total pie. Partial objects are allowed: the named
  //   shares are set and the unnamed ones share what is left in proportion to
  //   their current shares (the classic page's linked sliders, setPositionWeight).
  //   With all four named, they are rescaled to total 1. Every share is then
  //   clamped into getPositionWeightBounds() and the result totals exactly 1.
  //   null / undefined / "default" resets to the derived defaults. A league
  //   change (setScoring, setTeams) also resets them.
  //   Returns {ok, weights, requested, clamped, isDefault} or {ok:false, error}
  //   with no state change when the input is invalid.
  function setPositionWeights(request, publish = true) {
    if (request === null || request === undefined || request === "default") {
      positionWeights = null;
      if (engineReady) refreshAfterWeightChange(publish);
      else if (publish) publishShared();
      return {ok: true, weights: activePositionWeights(), requested: null, clamped: false, isDefault: true};
    }
    if (typeof request !== "object" || Array.isArray(request)) {
      return {ok: false, error: "expected an object of position shares, e.g. {QB: 0.2}"};
    }
    const bounds = positionWeightBounds();
    if (!bounds) return {ok: false, error: "position shares are not available until the engine has loaded"};
    const keys = Object.keys(request);
    if (!keys.length) return {ok: false, error: "no position shares given"};
    const unknown = keys.filter(key => !POSITION_ORDER.includes(key));
    if (unknown.length) return {ok: false, error: `unknown position(s): ${unknown.join(", ")} (expected QB, RB, WR, TE)`};
    const asked = {};
    for (const pos of keys) {
      const value = request[pos];
      const n = typeof value === "number" || typeof value === "string" ? Number(value) : NaN;
      if (!Number.isFinite(n)) return {ok: false, error: `${pos} share must be a finite number between 0 and 1`};
      asked[pos] = n;
    }
    const [lo, hi] = bounds[keys[0]];
    const clampShare = v => Math.min(hi, Math.max(lo, v));
    const current = activePositionWeights();
    const free = POSITION_ORDER.filter(pos => !(pos in asked));
    let w = {};
    if (!free.length) {
      const set = Object.fromEntries(POSITION_ORDER.map(pos => [pos, clampShare(asked[pos])]));
      const total = POSITION_ORDER.reduce((s, pos) => s + set[pos], 0);
      POSITION_ORDER.forEach(pos => { w[pos] = set[pos] / total; });
    } else {
      keys.forEach(pos => { w[pos] = clampShare(asked[pos]); });
      // The named shares can take at most what leaves every unnamed one its floor.
      const named = keys.reduce((s, pos) => s + w[pos], 0);
      const room = 1 - free.length * lo;
      if (named > room) keys.forEach(pos => { w[pos] *= room / named; });
      const left = 1 - keys.reduce((s, pos) => s + w[pos], 0);
      const freeTotal = free.reduce((s, pos) => s + current[pos], 0);
      free.forEach(pos => { w[pos] = freeTotal > 1e-12 ? left * current[pos] / freeTotal : left / free.length; });
      // Floor the unnamed shares out of what was left, so the named ones keep
      // their (clamped) values.
      w = liftToPositionFloor(w, free);
    }
    w = liftToPositionFloor(w);
    const total = POSITION_ORDER.reduce((s, pos) => s + w[pos], 0);
    POSITION_ORDER.forEach(pos => { w[pos] /= total; });
    const clamped = keys.some(pos => Math.abs(w[pos] - asked[pos]) > 1e-9);
    const baked = bakedPositionWeights();
    const isDefault = POSITION_ORDER.every(pos => Math.abs(w[pos] - baked[pos]) <= 1e-12);
    const before = activePositionWeights();
    // Setting the derived defaults back is the default state itself, so the
    // outputs are exactly the no-edit outputs (no float drift through activePies).
    positionWeights = isDefault ? null : w;
    const changed = POSITION_ORDER.some(pos => Math.abs(activePositionWeights()[pos] - before[pos]) > 1e-12);
    if (changed) {
      if (engineReady) refreshAfterWeightChange(publish);
      else if (publish) publishShared();
    }
    return {ok: true, weights: activePositionWeights(), requested: {...asked}, clamped, isDefault};
  }

  // Re-price + redraw + republish after any weight change (position or bench).
  function refreshAfterWeightChange(publish = true) {
    crossRank = null;
    rebuildDomain();
    syncPositionWeightControls();
    syncWeightsReadout();
    syncBenchShareControl();
    resetZoom();
    runRegressionGuards();
    draw();
    syncCurveStatus();
    if (publish) publishShared();
  }

  function benchSharePct(share) {
    return `${(share * 100).toFixed(1)}%`;
  }

  // The bench-share slider (VP-3.4): 15% by default; the reader's share
  // replaces it at the source level and in the DDF weights. The readout shows
  // the DDF weights' bench split the active share produces.
  function syncBenchShareControl() {
    const block = $("#benchShareBlock");
    if (!block) return;
    const input = block.querySelector("input[type=range]");
    const valueEl = block.querySelector(".bench-share-value");
    const readout = block.querySelector(".bench-share-readout");
    const tick = block.querySelector(".bench-share-tick");
    const fill = block.querySelector(".fill");
    const resetBtn = block.querySelector(".bench-share-reset");
    const [lo, hi] = BENCH_SHARE_BOUNDS;
    if (input) {
      input.disabled = false;
      input.min = String(lo);
      input.max = String(hi);
      input.step = "0.001";
      input.value = String(benchShare);
      input.setAttribute("aria-label", `Bench share override, ${benchSharePct(lo)} to ${benchSharePct(hi)}; off by default`);
    }
    if (resetBtn) {
      resetBtn.disabled = benchShareOverride === null;
      resetBtn.title = "Use the bench share computed from your league settings";
    }
    const frac = value => (value - lo) / (hi - lo);
    const computed = pipeline?.benchShare?.override === false ? pipeline.benchShare.overall : null;
    if (tick) {
      tick.hidden = computed === null;
      if (computed !== null) tick.style.left = `calc(8px + ${frac(Math.min(hi, Math.max(lo, computed)))} * (100% - 16px) - 1px)`;
    }
    if (fill) {
      fill.style.left = "8px";
      fill.style.width = `calc(${frac(benchShare)} * (100% - 16px))`;
    }
    if (valueEl) valueEl.textContent = benchShareOverride === null ? `${benchSharePct(benchShare)} computed`
      : `${benchSharePct(benchShareOverride)} (your override)`;
    const r = benchShareReadout();
    if (readout && r) {
      const byPos = POSITION_ORDER.map(pos => `${pos} ${r[pos] === null ? "n/a" : benchSharePct(r[pos])}`).join(", ");
      readout.textContent = r.method === "expected-starts"
        ? (r.override ? `Bench share: ${benchSharePct(r.overrideValue)} (your override). By position this week: ${byPos}.`
          : `Bench share this week: ${byPos}, from your league settings.`)
        : `Bench share fixed at ${benchSharePct(benchShare)}: the league settings model did not load.`;
      readout.title = "The bench share is how much of each position's value sits with bench players. It comes from how often bench players actually reach a lineup in your league setup: byes, injuries and how deep your bench is.";
    }
  }

  // ---- Standalone Weights section ----
  // Four linked position-share sliders (always sum to exactly 100%) plus the
  // bench-share slider, moved here from the roster panel. All write to the
  // same global state and drive a true live recalibration.
  function makePositionWeightControls() {
    const grid = $("#positionWeightControls");
    if (!grid) return;
    grid.innerHTML = "";
    const weights = activePositionWeights();
    POSITION_ORDER.forEach(pos => {
      const wrap = document.createElement("div");
      wrap.className = "weight-step";
      wrap.dataset.pos = pos;
      const label = document.createElement("label");
      label.htmlFor = `weight-${pos}`;
      const name = document.createElement("span");
      name.textContent = pos;
      const val = document.createElement("span");
      val.className = "weight-val";
      label.append(name, val);
      const input = document.createElement("input");
      input.type = "range";
      input.id = `weight-${pos}`;
      input.min = "0";
      input.max = "100";
      input.step = "0.1";
      input.value = String((weights[pos] || 0) * 100);
      input.setAttribute("aria-label", `${pos} share of total value pie, percent`);
      input.addEventListener("input", () => setPositionWeight(pos, Number(input.value) / 100));
      wrap.append(label, input);
      grid.appendChild(wrap);
    });
    syncPositionWeightControls();
    const resetBtn = $("#weightsReset");
    if (resetBtn && !resetBtn.dataset.bound) {
      resetBtn.dataset.bound = "1";
      resetBtn.addEventListener("click", resetAllWeights);
    }
  }

  // Displayed pie percentages: largest-remainder rounding to 0.1% so the four
  // shown shares always total exactly 100.0 (independent toFixed(1) per
  // position missed by 0.1 in 5 of the 12 league shapes, JEG-24). Display
  // only: the underlying weights, pies and calibration stay exact.
  function pieDisplayTenths(weights) {
    const raw = POSITION_ORDER.map(pos => Math.max(0, Number(weights?.[pos]) || 0));
    const total = raw.reduce((s, v) => s + v, 0);
    if (!(total > 0)) return raw.map(() => 0);
    const scaled = raw.map(v => (v / total) * 1000);
    const tenths = scaled.map(v => Math.floor(v + 1e-9));
    let remainder = 1000 - tenths.reduce((s, v) => s + v, 0);
    const order = scaled
      .map((v, i) => ({i, frac: v - Math.floor(v + 1e-9)}))
      .sort((a, b) => b.frac - a.frac || a.i - b.i);
    for (let k = 0; remainder > 0; k = (k + 1) % order.length, remainder -= 1) tenths[order[k].i] += 1;
    return tenths;
  }

  function syncPositionWeightControls() {
    const grid = $("#positionWeightControls");
    if (!grid) return;
    const weights = activePositionWeights();
    const displayTenths = pieDisplayTenths(weights);
    let total = 0;
    POSITION_ORDER.forEach((pos, idx) => {
      const wrap = grid.querySelector(`.weight-step[data-pos="${pos}"]`);
      if (!wrap) return;
      const pct = (weights[pos] || 0) * 100;
      const shown = displayTenths[idx] / 10;
      total += shown;
      const input = wrap.querySelector("input[type=range]");
      const val = wrap.querySelector(".weight-val");
      if (input && document.activeElement !== input) input.value = String(pct);
      if (val) val.textContent = `${shown.toFixed(1)}%`;
    });
    const readout = $("#weightsReadout");
    if (readout) readout.dataset.total = String(total);
  }

  function syncWeightsReadout() {
    const readout = $("#weightsReadout");
    if (!readout) return;
    const weights = activePositionWeights();
    const baked = bakedPositionWeights();
    const shown = pieDisplayTenths(weights);
    const shownBaked = baked ? pieDisplayTenths(baked) : null;
    const parts = POSITION_ORDER.map((pos, idx) => {
      const pct = (shown[idx] / 10).toFixed(1);
      const b = shownBaked ? ` (default ${(shownBaked[idx] / 10).toFixed(1)}%)` : "";
      return `${pos} ${pct}%${b}`;
    });
    const benchPct = (benchShare * 100).toFixed(1);
    readout.textContent = `Pie: ${parts.join(" · ")} — sums to 100%. Bench ${benchPct}% (${benchShareOverride === null ? "computed from your league settings" : "your override"}). Values above re-price live from every included source.`;
  }

  function makeRosterControls() {
    const grid = $("#rosterShapeControls");
    if (!grid) return;
    const controls = [
      ["QB", "QB"],
      ["RB", "RB"],
      ["WR", "WR"],
      ["TE", "TE"],
      ["FLEX", "Flex"],
      ["SUPERFLEX", "Superflex"],
      ["BENCH", "Bench"]
      // JEG-298: K/DST inputs removed — JEG-211 excluded K/DST from the chart
      // entirely, and these inputs were no-ops (POSITION_ORDER has no K/DST).
    ];
    grid.replaceChildren();
    controls.forEach(([key, label]) => {
      const wrapper = document.createElement("label");
      wrapper.className = "roster-step";
      const text = document.createElement("span");
      text.textContent = label;
      const input = document.createElement("input");
      input.type = "number";
      input.min = String(rosterBounds(key)[0]);
      input.max = String(rosterBounds(key)[1]);
      input.step = "1";
      input.value = rosterShape[key];
      input.dataset.rosterKey = key;
      input.setAttribute("aria-label", `${label} roster spots`);
      input.addEventListener("change", () => setRosterSpot(key, input.value));
      wrapper.append(text, input);
      grid.appendChild(wrapper);
    });
    // Bench share: the override slider (ES-14, VP-3.4), off by default; the
    // tick marks the share computed from the league settings.
    const shareBlock = document.createElement("div");
    shareBlock.className = "bench-share-block";
    shareBlock.id = "benchShareBlock";
    const shareHead = document.createElement("div");
    shareHead.className = "bench-share-head";
    const shareTitle = document.createElement("span");
    shareTitle.className = "bench-share-title";
    shareTitle.textContent = "Bench %";
    const shareValue = document.createElement("span");
    shareValue.className = "bench-share-value";
    shareValue.textContent = benchSharePct(benchShare);
    const shareReset = document.createElement("button");
    shareReset.type = "button";
    shareReset.className = "bench-share-reset";
    shareReset.textContent = "Use computed";
    shareReset.addEventListener("click", () => setBenchShareOverride(null));
    shareHead.append(shareTitle, shareValue, shareReset);
    const slider = document.createElement("div");
    slider.className = "zslider bench-share-slider";
    const track = document.createElement("div");
    track.className = "track";
    const tick = document.createElement("div");
    tick.className = "bench-share-tick";
    tick.title = "Bench share computed from your league settings";
    const fill = document.createElement("div");
    fill.className = "fill";
    const shareInput = document.createElement("input");
    shareInput.type = "range";
    shareInput.step = "0.001";
    shareInput.value = String(benchShare);
    shareInput.setAttribute("aria-label", "Bench share");
    shareInput.addEventListener("input", () => setBenchShareFraction(Number(shareInput.value), false));
    shareInput.addEventListener("change", () => { setBenchShareFraction(Number(shareInput.value), false); publishShared(); });
    shareInput.addEventListener("dblclick", () => setBenchShareOverride(null));
    slider.append(track, tick, fill, shareInput);
    const readout = document.createElement("p");
    readout.className = "bench-share-readout";
    shareBlock.append(shareHead, slider, readout);
    // The bench slider lives in the standalone Weights section, not the roster panel.
    const benchSlot = $("#weightsBenchSlot");
    if (benchSlot) {
      benchSlot.innerHTML = "";
      benchSlot.appendChild(shareBlock);
    } else {
      grid.appendChild(shareBlock);
    }
    syncBenchShareControl();
  }

  function chartValueExtent(rows = displayRows()) {
    const values = rows
      .slice(Math.max(0, zoomLow - 1), Math.max(zoomLow, zoomHigh))
      .flatMap(row => activeSourceKeys().map(key => row.values[key]))
      .filter(Number.isFinite);
    const max = values.length ? Math.max(...values) : 10;
    return {min:0, max:Math.max(10, Math.ceil(max / 5) * 5)};
  }

  function makeValueBandControl() {
    syncYAxis();
  }

  function syncTabs() {
    $("#posTabs")?.querySelectorAll("button").forEach(button => {
      const active = button.dataset.value === position;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function makeValueModeControl() {
    const container = $("#valueModeSeg");
    if (!container) return;
    container.closest(".basis-row")?.remove();
  }

  // The league allocation (VP-2.2): dedicated, superflex and flex slots by
  // mean projected points, bench seats by D'Hondt.
  function adjustmentAllocationRows() {
    const alloc = slotFill();
    return POSITION_ORDER.map(pos => {
      const a = alloc?.[pos] || {dedicated: 0, superflex: 0, flex: 0, bench: 0, starters: 0, rostered: 0};
      return {
        pos,
        direct: a.dedicated,
        superflex: a.superflex,
        flex: a.flex,
        bench: a.bench,
        lineup: a.starters,
        rostered: a.rostered
      };
    });
  }

  // Per-source weights (VP-3.4) and the averaged DDF weights (VP-4), one row
  // per group: {key, source, position, tier, weight, included}.
  function adjustmentWeightRows() {
    if (!pipeline) return [];
    const rows = [];
    const groups = POSITION_ORDER.flatMap(pos => ["starter", "bench"].map(tier => [pos, tier]));
    PIPELINE_SOURCE_KEYS.forEach(key => {
      const weights = pipeline.sources[key]?.weights;
      if (!weights) return;
      groups.forEach(([pos, tier]) => rows.push({key, source: pipelineLabel(key), position: pos, tier,
        weight: weights[`${pos}|${tier}`], included: pipelineState.included.includes(key)}));
    });
    groups.forEach(([pos, tier]) => rows.push({key: COMPOSITE_KEY, source: "DDF Value", position: pos, tier,
      weight: pipeline.ddfWeights[`${pos}|${tier}`], included: true}));
    return rows;
  }

  function appendCell(parent, tag, text, className) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = text;
    parent.appendChild(node);
    return node;
  }

  function renderAdjustmentWeights() {
    const container = $("#adjustmentWeights");
    if (!container || !canonicalByKey.size || !pipeline) return;
    container.replaceChildren();

    const meta = document.createElement("p");
    meta.className = "adjustment-note";
    meta.textContent = `${scoreLabel()} · ${teams} teams · slots filled by mean projected points of the included projections · league pie ${formatOne(pipeline.pie)}`;
    container.appendChild(meta);

    const allocWrap = document.createElement("div");
    allocWrap.className = "adjustment-table-wrap allocation-table-wrap";
    const allocTable = document.createElement("table");
    const allocHead = document.createElement("thead");
    const allocHeadRow = document.createElement("tr");
    ["Pos", "Dedicated", "Superflex", "Flex", "Bench", "Rostered"].forEach(label => appendCell(allocHeadRow, "th", label));
    allocHead.appendChild(allocHeadRow);
    const allocBody = document.createElement("tbody");
    adjustmentAllocationRows().forEach(row => {
      const tr = document.createElement("tr");
      appendCell(tr, "td", row.pos);
      appendCell(tr, "td", String(row.direct));
      appendCell(tr, "td", String(row.superflex), row.superflex > 0 ? "is-flex-hit" : "");
      appendCell(tr, "td", String(row.flex), row.flex > 0 ? "is-flex-hit" : "");
      appendCell(tr, "td", String(row.bench));
      appendCell(tr, "td", String(row.rostered));
      allocBody.appendChild(tr);
    });
    allocTable.append(allocHead, allocBody);
    allocWrap.appendChild(allocTable);
    container.appendChild(allocWrap);

    // One table: each source's weights (bench normalized to the bench share)
    // and the DDF weights, their average.
    const rows = adjustmentWeightRows();
    const keys = [...new Set(rows.map(row => row.key))];
    const tableWrap = document.createElement("div");
    tableWrap.className = "adjustment-table-wrap";
    const table = document.createElement("table");
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    ["Group", ...keys.map(key => key === COMPOSITE_KEY ? "DDF Value" : pipelineLabel(key))].forEach(label => appendCell(headRow, "th", label));
    thead.appendChild(headRow);
    const tbody = document.createElement("tbody");
    POSITION_ORDER.forEach(pos => ["starter", "bench"].forEach(tier => {
      const tr = document.createElement("tr");
      appendCell(tr, "td", `${pos} ${tier}`);
      keys.forEach(key => {
        const row = rows.find(r => r.key === key && r.position === pos && r.tier === tier);
        appendCell(tr, "td", row ? `${(row.weight * 100).toFixed(1)}%` : "—", row && !row.included ? "is-excluded" : "");
      });
      tbody.appendChild(tr);
    }));
    table.append(thead, tbody);
    tableWrap.appendChild(table);
    container.appendChild(tableWrap);
  }

  function makeSourceToggles() {
    const container = $("#sourceToggles");
    if (!container) return;
    container.replaceChildren();
    SOURCE_GROUPS.forEach(group => {
      const groupNode = document.createElement("div");
      groupNode.className = "source-toggle-group";
      const title = document.createElement("span");
      title.className = "source-toggle-heading";
      title.textContent = group.label;
      groupNode.appendChild(title);
      group.keys.forEach(key => {
      const label = document.createElement("label");
      label.className = "src-toggle";
      const input = document.createElement("input");
      input.type = "checkbox";
      const hasData = sourceMaps.get(key)?.size > 0;
      const staleWeek = sourceIsStale(key);
      const available = hasData && sourceComboExists(key);
      input.checked = activeSources.has(key) && available;
      input.disabled = !available;
      input.dataset.source = key;
      input.setAttribute("aria-label", `Show ${sourceLabel(key)} curve`);
      if (key.startsWith("fantasycalc")) label.title = "FantasyCalc publisher basis: 1 QB";
      label.classList.toggle("is-stale", staleWeek && available);
      const missingFromData = sourceMissingFromData(key);
      if (missingFromData) {
        label.classList.add("is-disabled");
        label.title = `${sourceLabel(key)} is unavailable: its data is missing from this build, so it is left off the chart. Every other source is unaffected.`;
      } else if (!available) {
        label.classList.add("is-disabled");
        label.title = `${sourceLabel(key)} is not available for ${scoreLabel()} / ${teams} teams in the current artifact.`;
      } else if (staleWeek) {
        label.title = `${sourceLabel(key)}: ${freshnessText(key)}. The current content week is Week ${activeReferenceWeek()}.`;
      }
      input.addEventListener("change", () => {
        if (input.checked) { activeSources.add(key); userDeselectedSources.delete(key); }
        else if (activeSourceKeys().length > 1) { activeSources.delete(key); userDeselectedSources.add(key); }
        else input.checked = true;
        crossRank = null;
        syncZoom();
        makeSourceToggles();
        makeLockControl();
        renderAdjustmentWeights();
        draw();
        syncCurveStatus();
      });
      const swatch = document.createElement("span");
      swatch.className = "source-line";
      swatch.style.borderTopColor = SOURCE_STYLES[key].color;
      swatch.style.borderTopStyle = key.endsWith("_adjusted") ? "dashed" : "solid";
      const text = document.createElement("span");
      text.className = "src-text";
      text.textContent = sourceLabel(key);
      if (missingFromData) {
        const meta = document.createElement("span");
        meta.className = "src-meta";
        meta.textContent = "unavailable · missing from this build";
        text.appendChild(meta);
      } else if (staleWeek && hasData) {
        const meta = document.createElement("span");
        meta.className = "src-meta";
        meta.textContent = "newer week not yet published";
        text.appendChild(meta);
      }
      label.append(input, swatch, text);
      groupNode.appendChild(label);
      });
      container.appendChild(groupNode);
    });
  }

  function makeLockControl() {
    const select = $("#curveLockOrder");
    if (!select) return;
    const options = [
      ["disagreement", "Largest disagreement"],
      ...(compositeAvailable() ? [[COMPOSITE_KEY, sourceLabel(COMPOSITE_KEY)]] : []),
      ...visibleSourceKeys().filter(sourceAvailable).map(key => [key, sourceLabel(key)])
    ];
    select.innerHTML = options.map(([value, label]) => `<option value="${value}">${label}</option>`).join("");
    select.value = lockOrder;
    select.onchange = event => setLockOrder(event.target.value);
    syncLockNote();
  }

  function syncLockNote() {
    const select = $("#curveLockOrder");
    if (select) select.value = lockOrder;
    const note = $("#curveLockNote");
    if (!note) return;
    note.textContent = [COMPOSITE_KEY, ...SOURCE_KEYS, ...EXTRA_SOURCE_KEYS, ...PURE_VORP_KEYS].includes(lockOrder)
      ? `Every curve uses the ${sourceLabel(lockOrder)} player order, so each x-position is the same player across all visible lines.`
      : lockOrder === "disagreement"
        ? `Every curve shares one player axis; cutoff lines use ${sourceLabel(selectedRankSourceKey())} as the roster-rank reference.`
        : position === "ALL"
          ? `Every curve shares one player axis; cutoff lines use ${sourceLabel(selectedRankSourceKey())} as the roster-rank reference.`
          : `Every curve shares one player axis; cutoff lines use ${sourceLabel(selectedRankSourceKey())} as the roster-rank reference.`;
  }

  function syncCurveStatus() {
    const status = $("#curve-status");
    if (!status) return;
    const activeNotices = [...status.querySelectorAll(".lock-revert-notice")];
    status.classList.add("validated");
    // JEG-432 R5: charts left off because they are a week behind the newest
    // one on the board.
    const olderWeekKeys = DEFAULT_INDEXED_SOURCES.filter(key => firstLoadExcluded.has(key) && sourceAvailable(key));
    const olderWeekNote = olderWeekKeys.length
      ? ` ${olderWeekKeys.map(sourceLabel).join(", ")} ${olderWeekKeys.length === 1 ? "is" : "are"} from an older week and start${olderWeekKeys.length === 1 ? "s" : ""} off; turn ${olderWeekKeys.length === 1 ? "it" : "them"} on below.`
      : "";
    const included = pipelineState.included.length;
    const ddfText = included
      ? `DDF Value is the mean of ${included} source${included === 1 ? "" : "s"}' Adjusted values, every source on one league pie.`
      : "No source is available this week, so there is no DDF Value.";
    status.innerHTML = `<strong>Validated:</strong> ${ddfText} The published trade charts are shown by default; projections and value-above-waivers series can be turned on below.${olderWeekNote}`;
    activeNotices.forEach(note => status.appendChild(note));
  }

  // QA-003: Show user-visible notification when lock order is force-reverted.
  // Silent reverts are indistinguishable from bugs and erode trust.
  function notifyLockRevert(prevLock, reason) {
    const status = $("#curve-status");
    if (!status) return;
    const prevLabel = sourceLabel(prevLock) || prevLock;
    const note = document.createElement("div");
    note.className = "lock-revert-notice";
    note.style.cssText = "margin-top:8px;padding:8px 12px;background:#fff3cd;border:1px solid #ffc107;border-radius:6px;font-size:12.5px;color:#856404";
    note.innerHTML = `<b>Note:</b> Player lock order was reset from "${prevLabel}" to "${sourceLabel(defaultValueLock())}" (${reason} made "${prevLabel}" unavailable).`;
    // Remove any existing notice first
    status.querySelectorAll(".lock-revert-notice").forEach(n => n.remove());
    status.appendChild(note);
    // Auto-dismiss after 8 seconds
    setTimeout(() => note.remove(), 8000);
  }

  function publishShared() {
    const detail = {scoring, teams, position, model: "monday", lockOrder, rosterShape:{...rosterShape}, benchShare, absenceRate:benchShare,
      benchShareOverride, lineupSettings: getLineupSettings(), positionWeights: activePositionWeights(),
      compositeInputs: compositeInputs ? [...compositeInputs] : null};
    window.TradeValueSharedState = detail;
    window.dispatchEvent(new CustomEvent("trade-value-shared-change", {detail}));
  }

  // Bench-share override (ES-14, VP-3.4): off (null) by default, when the
  // bench share is computed from the league settings. A share in
  // BENCH_SHARE_BOUNDS turns it on: every source is normalized to it before
  // averaging, so it re-prices every series. Returns the override in effect.
  function setBenchShareOverride(share, publish = true) {
    let next = share === null || share === undefined || share === "" ? null : Number(share);
    if (next !== null) {
      if (!Number.isFinite(next)) {
        syncBenchShareControl();
        return benchShareOverride;
      }
      const [lo, hi] = BENCH_SHARE_BOUNDS;
      next = Math.min(hi, Math.max(lo, next));
    }
    const same = next === null ? benchShareOverride === null
      : benchShareOverride !== null && Math.abs(next - benchShareOverride) < 1e-9;
    if (same) {
      syncBenchShareControl();
      return benchShareOverride;
    }
    benchShareOverride = next;
    if (next !== null) benchShare = next;
    crossRank = null;
    if (engineReady) {
      refreshAfterWeightChange(publish);
      return benchShareOverride;
    }
    syncBenchShareControl();
    syncWeightsReadout();
    if (publish) publishShared();
    return benchShareOverride;
  }

  // Legacy entry (the classic page's slider and v2's links): a share sets the
  // override; it is the same control, now off by default.
  function setBenchShareFraction(share, publish = true) {
    return setBenchShareOverride(share, publish);
  }

  // ES-14 reader settings. Each setter validates, re-prices and returns the
  // settings in effect; an invalid value leaves them unchanged (and throws a
  // RangeError so the caller can say why).
  const PROJECTION_CONFIDENCE_STEPS = Object.freeze([0.5, 1, 1.5]);
  function setLineupSettings(partial, publish = true) {
    const next = {...lineupSettings, playoffWeeks: [...lineupSettings.playoffWeeks]};
    const p = partial || {};
    if (p.regularSeasonEnd !== undefined) next.regularSeasonEnd = Number(p.regularSeasonEnd);
    if (p.playoffWeeks !== undefined) next.playoffWeeks = Array.isArray(p.playoffWeeks)
      ? p.playoffWeeks.map(Number) : [];
    if (p.optimizeFor !== undefined) next.optimizeFor = p.optimizeFor;
    if (p.injuryHistory !== undefined) next.injuryHistory = p.injuryHistory;
    if (p.projectionConfidence !== undefined) next.projectionConfidence = Number(p.projectionConfidence);
    const [pLo, pHi] = next.playoffWeeks;
    const week = n => Number.isInteger(n) && n >= 1 && n <= 18;
    if (!week(next.regularSeasonEnd)) throw new RangeError("Last regular-season week must be a week from 1 to 18");
    if (next.playoffWeeks.length !== 2 || !week(pLo) || !week(pHi) || pLo > pHi) {
      throw new RangeError("Playoff weeks must be two weeks from 1 to 18, first to last");
    }
    if (pLo <= next.regularSeasonEnd) throw new RangeError("Playoffs must start after the last regular-season week");
    if (!ValueModel.LINEUP_OBJECTIVES.includes(next.optimizeFor)) {
      throw new RangeError(`Optimize for must be one of ${ValueModel.LINEUP_OBJECTIVES.join(", ")}`);
    }
    if (!ValueModel.LINEUP_INJURY_HISTORY.includes(next.injuryHistory)) {
      throw new RangeError(`Injury history must be one of ${ValueModel.LINEUP_INJURY_HISTORY.join(", ")}`);
    }
    if (!PROJECTION_CONFIDENCE_STEPS.includes(next.projectionConfidence)) {
      throw new RangeError(`Projection confidence must be one of ${PROJECTION_CONFIDENCE_STEPS.join(", ")}`);
    }
    const changed = JSON.stringify(next) !== JSON.stringify(lineupSettings);
    lineupSettings = next;
    if (changed) {
      crossRank = null;
      if (engineReady) refreshAfterWeightChange(publish);
      else if (publish) publishShared();
    }
    return getLineupSettings();
  }
  function getLineupSettings() {
    return {...lineupSettings, playoffWeeks: [...lineupSettings.playoffWeeks],
      benchShareOverride};
  }
  function lineupDefaults() {
    const d = lineupConfig?.defaults;
    return {regularSeasonEnd: d?.league_weeks?.regular_season_end ?? 14,
      playoffWeeks: [...(d?.league_weeks?.playoff_weeks || [15, 17])],
      optimizeFor: d?.objective || "season", injuryHistory: d?.injury_history || "recent",
      projectionConfidence: d?.projection_confidence ?? 1, benchShareOverride: null};
  }
  // ES-14 readout: {QB, RB, WR, TE, overall, override, overrideValue,
  // fillInShare, method, contentWeek, window}; null before the first build or
  // with no projection in the included set.
  function benchShareReadout() {
    const r = pipeline?.benchShare;
    if (!r) return null;
    const lineup = pipeline.lineup;
    return {QB: r.QB, RB: r.RB, WR: r.WR, TE: r.TE, overall: r.overall, override: r.override,
      overrideValue: r.overrideValue, fillInShare: r.fillInShare, method: r.method,
      contentWeek: lineup ? lineup.content_week : null, window: lineup ? [...lineup.window] : null,
      error: lineupConfigError ? String(lineupConfigError.message || lineupConfigError) : null};
  }

  // Backward-compatible entry: the retired free input passed an integer
  // percent; external callers may still do so.
  function setBenchShare(raw, publish = true) {
    setBenchShareFraction(Number(raw) / 100, publish);
  }

  function setRosterSpot(key, raw, publish = true) {
    if (!Object.prototype.hasOwnProperty.call(rosterShape, key)) return;
    const [min, max] = rosterBounds(key);
    const next = Math.max(min, Math.min(max, Math.round(Number(raw))));
    if (!Number.isFinite(next) || next === rosterShape[key]) {
      makeRosterControls();
      return;
    }
    rosterShape[key] = next;
    crossRank = null;
    rebuildDomain();
    makeRosterControls();
    makeLockControl();
    renderAdjustmentWeights();
    resetZoom();
    runRegressionGuards();
    draw();
    syncCurveStatus();
    if (publish) publishShared();
  }

  function setPosition(value, publish = true) {
    if (!POSITIONS.includes(value) || value === position) return;
    position = value;
    crossRank = null;
    rebuildDomain();
    syncTabs();
    makeLockControl();
    renderAdjustmentWeights();
    resetZoom();
    runRegressionGuards();
    draw();
    syncCurveStatus();
    if (publish) publishShared();
  }

  function setScoring(value, publish = true) {
    const normalized = value === "half" ? "half_ppr" : value === "full" ? "ppr" : value;
    if (!SCORINGS.some(([key]) => key === normalized) || normalized === scoring) return;
    scoring = normalized;
    crossRank = null;
    // League change: custom position weights reset to the new combo's baked defaults.
    positionWeights = null;
    rebuildDomain();
    // QA-003: Notify user when lock order is force-reverted. Silent reverts erode trust.
    if (!["disagreement"].includes(lockOrder) && !lockSourceAvailable(lockOrder)) {
      const prevLock = lockOrder;
      lockOrder = defaultValueLock();
      if (prevLock !== lockOrder) notifyLockRevert(prevLock, "scoring change");
    }
    makeLeagueControls();
    makeRosterControls();
    makePositionWeightControls();
    syncWeightsReadout();
    makeValueBandControl();
    makeSourceToggles();
    makeLockControl();
    renderAdjustmentWeights();
    resetZoom();
    runRegressionGuards();
    draw();
    syncCurveStatus();
    // DEFECT 2: syncContext() only ran inside rebuildDomain() (before the
    // forced lock reset above), leaving the "locked to ..." caption stale
    // after a reset. Re-render it with the post-reset lockOrder.
    syncContext();
    if (publish) publishShared();
  }

  function setTeams(value, publish = true) {
    const normalized = Number(value);
    if (![8, 10, 12, 14].includes(normalized) || normalized === teams) return;
    teams = normalized;
    crossRank = null;
    // League change: custom position weights reset to the new combo's baked defaults.
    positionWeights = null;
    rebuildDomain();
    // QA-003: Notify user when lock order is force-reverted. Silent reverts erode trust.
    if (!["disagreement"].includes(lockOrder) && !lockSourceAvailable(lockOrder)) {
      const prevLock = lockOrder;
      lockOrder = defaultValueLock();
      if (prevLock !== lockOrder) notifyLockRevert(prevLock, "team size change");
    }
    makeLeagueControls();
    makeRosterControls();
    makePositionWeightControls();
    syncWeightsReadout();
    makeValueBandControl();
    makeSourceToggles();
    makeLockControl();
    renderAdjustmentWeights();
    resetZoom();
    runRegressionGuards();
    draw();
    syncCurveStatus();
    // DEFECT 2: syncContext() only ran inside rebuildDomain() (before the
    // forced lock reset above), leaving the "locked to ..." caption stale
    // after a reset. Re-render it with the post-reset lockOrder.
    syncContext();
    if (publish) publishShared();
  }

  function setLockOrder(value, publish = true) {
    if (!isLockKey(value) || value === lockOrder) return;
    lockOrder = value;
    window.TradeValueLockOrder = value;
    crossRank = null;
    rebuildDomain();
    syncLockNote();
    renderAdjustmentWeights();
    resetZoom();
    draw();
    if (publish) window.dispatchEvent(new CustomEvent("trade-value-lock-order-change", {detail: {lockOrder:value}}));
  }

  // JEG-471 / VP-1.5: choose the DDF Value inputs. keys: an array of source
  // keys (COMPOSITE_INPUT_KEYS; the pre-JEG-508 "*_adjusted" names are
  // accepted and mean their chart), any order, duplicates ignored; null (or
  // "default") restores the default (every included source). The choice only
  // narrows the DDF averaging: I, the weights and every series are untouched.
  // A source that is held, not yet published or outside I this week is
  // dropped and listed in `dropped`; if that leaves none, the defaults apply
  // (fellBackToDefaults). A list that names no usable source and drops
  // nothing is refused. Recomputes, redraws and fires trade-value-rows-change,
  // then trade-value-shared-change (with compositeInputs) unless publish is false.
  function setCompositeInputs(keys, publish = true) {
    let next = null;
    let dropped = [];
    let fellBack = false;
    if (!(keys === null || keys === undefined || keys === "default")) {
      if (!Array.isArray(keys)) return {ok: false, error: "expected an array of source keys, or null for the defaults"};
      if (!keys.length) return {ok: false, error: "no sources given: DDF Value needs at least one"};
      const normalized = keys.map(normalizeInputKey);
      const unknown = keys.filter((key, i) => !COMPOSITE_INPUT_KEYS.includes(normalized[i]));
      if (unknown.length) {
        return {ok: false, error: `not a DDF Value input: ${unknown.map(String).join(", ")} (expected ${COMPOSITE_INPUT_KEYS.join(", ")})`};
      }
      if (!engineReady) return {ok: false, error: "DDF Value inputs cannot be set until the engine has loaded"};
      const asked = COMPOSITE_INPUT_KEYS.filter(key => normalized.includes(key));
      dropped = asked.filter(key => !pipelineState.included.includes(key)).map(key =>
        compositeBlock(key) || {key, reason: pipelineState.excluded.find(e => e.key === key)?.reason || "not available this week"});
      next = asked.filter(key => pipelineState.included.includes(key));
      if (next.length < COMPOSITE_MIN_SOURCES) {
        if (dropped.length) {
          fellBack = true;
          next = null;
        } else {
          return {ok: false, error: `DDF Value needs at least ${COMPOSITE_MIN_SOURCES} usable input for ${scoreLabel()} / ${teams} teams`};
        }
      }
      const defaults = pipelineState.included;
      if (next && next.length === defaults.length && next.every(key => defaults.includes(key))) next = null;
    }
    const before = JSON.stringify(compositeInputs);
    compositeInputs = next;
    if (engineReady && JSON.stringify(compositeInputs) !== before) refreshComposite(publish);
    return {ok: true, ...compositeInputsInfo(), ...(dropped.length ? {dropped} : {}), ...(fellBack ? {fellBackToDefaults: true} : {})};
  }

  // Only the DDF Value fields depend on the inputs, but they are computed in
  // the pipeline with its rows, so the pipeline re-runs (every series comes
  // out unchanged: VP-1.5).
  function refreshComposite(publish = true) {
    crossRank = null;
    rebuildDomain();
    makeLockControl();
    resetZoom();
    runRegressionGuards();
    draw();
    syncCurveStatus();
    if (publish) publishShared();
  }

  // ---------------------------------------------------------------------
  // Back-end contract: history (docs/v2-design-notes.md). Read-only: a saved
  // week's inputs (assets/history/week-<N>.json, built by
  // pipelines/build_week_history.py) run through the same value pipeline at
  // the CURRENT league, roster, bench share, position shares, included set
  // and pie (VP-8). Only the sources' own inputs come from the saved week:
  // nothing from the current week enters it. Every series of a saved week is
  // read from that week's one pipeline run, so a series and the DDF Value
  // move together.
  const HISTORY_INDEX_PATH = "assets/history/index.json";
  const HISTORY_SCORING_INDEX = {standard: 0, half_ppr: 1, ppr: 2};
  let historyIndexPromise = null;
  const historyWeekPromises = new Map();
  // JEG-479: what each history read resolved to ({value} or {error}), so the
  // prior week can be priced synchronously inside a rebuild. Keys: "index",
  // "served", "doc:<file>". A read not made yet throws "not loaded".
  const historyLoaded = new Map();
  const remember = (key, promise) => promise.then(value => {
    historyLoaded.set(key, {value});
    return value;
  }, error => {
    historyLoaded.set(key, {error});
    throw error;
  });
  function historyNow(key) {
    const loaded = historyLoaded.get(key);
    if (!loaded) throw new Error(`${key} is not loaded yet`);
    if (loaded.error) throw loaded.error;
    return loaded.value;
  }
  function historyWeekDocNow(index, week) {
    const file = index?.weeks?.[String(week)]?.file;
    return file ? historyNow(`doc:${file}`) : null;
  }
  function fetchHistoryJson(path) {
    return fetch(path).then(response => {
      if (!response.ok) throw new Error(`${path} request failed (${response.status})`);
      return response.json();
    });
  }
  function historyIndex() {
    if (!historyIndexPromise) {
      historyIndexPromise = remember("index", fetchHistoryJson(HISTORY_INDEX_PATH)).catch(error => {
        historyIndexPromise = null;
        throw error;
      });
    }
    return historyIndexPromise;
  }
  let historyServedPromise = null;
  function historyServedVersions() {
    if (!historyServedPromise) {
      historyServedPromise = remember("served", fetchHistoryJson("assets/history/served.json")).catch(error => {
        historyServedPromise = null;
        throw error;
      });
    }
    return historyServedPromise;
  }
  function historyWeekDoc(index, week) {
    const file = index?.weeks?.[String(week)]?.file;
    if (!file) return Promise.resolve(null);
    if (!historyWeekPromises.has(file)) {
      historyWeekPromises.set(file, remember(`doc:${file}`, fetchHistoryJson(file).then(doc => {
        if (doc?.week !== week) throw new Error(`${file} says week ${doc?.week}, not ${week}`);
        return doc;
      })).catch(error => {
        historyWeekPromises.delete(file);
        throw error;
      }));
    }
    return historyWeekPromises.get(file);
  }
  function historySetting(view = viewMode) {
    return {scoring, teams, roster: {...rosterShape}, benchShare, benchShareOverride, lineupSettings: getLineupSettings(),
      viewMode: view, weights: activePositionWeights()};
  }
  function historyUnavailable(source, week, reason, extra) {
    return {source, week, available: false, reason, values: null, setting: historySetting(), ...(extra || {})};
  }
  // A saved published chart's natives at the active scoring, keyed like
  // savedPublishedNative (canonical players, finite values). The saved weeks
  // carry 1-QB natives only, so a saved week at a superflex setting runs on
  // them (no superflex overlay).
  function historyNatives(entry) {
    const native = new Map();
    Object.entries(entry?.natives?.[scoring] || {}).forEach(([key, rawValue]) => {
      const playerKey = Number(key);
      const value = Number(rawValue);
      if (canonicalByKey.has(playerKey) && Number.isFinite(value)) native.set(playerKey, value);
    });
    return native;
  }
  // A saved week's per-game projections at the active scoring.
  function historyPpg(entry) {
    const idx = HISTORY_SCORING_INDEX[scoringField()];
    const ppg = new Map();
    Object.entries(entry?.ppg || {}).forEach(([key, triple]) => {
      const playerKey = Number(key);
      const value = Number(triple?.[idx]);
      if (canonicalByKey.has(playerKey) && Number.isFinite(value)) ppg.set(playerKey, value);
    });
    return ppg;
  }
  // Is this source's week served from a kept version, not the week's snapshot?
  const servedVersionAt = (index, base, week) =>
    index?.served?.[base]?.week === week && index?.served?.[base]?.version === "superseded";
  // The saved entry of one source for one week: the served version when the
  // source serves that week from a kept version (index served.version
  // "superseded"), else the week's snapshot. {entry} | {missing: reason}
  // (nothing saved for that week) | {error: reason} (a history read failed).
  function historyEntryOf(base, week, index, doc) {
    let entry = doc?.sources?.[base];
    const servedRec = index?.served?.[base];
    if (servedRec?.week === week && servedRec?.version === "superseded") {
      try {
        const served = historyNow("served");
        const version = served?.sources?.[base];
        if (!version || version.fingerprint !== servedRec.entry_fingerprint) {
          return {missing: `the served ${sourceLabel(base)} version is not saved`};
        }
        entry = version;
      } catch (error) {
        return {error: `history could not be read: ${error.message}`};
      }
    }
    if (!entry) return {missing: `no Week ${week} ${sourceLabel(base)} content saved`};
    if (entry.week !== week) return {missing: `saved entry is labelled week ${entry.week}`};
    return {entry};
  }
  // One saved week of one series at the reader's current setting.
  // Resolves {source, week, available, reason?, values: {player_key: value}
  // (players the saved week does not price are absent), setting, origin,
  // fingerprint, method}.
  async function getWeekValues(source, week) {
    if (isCompositeKey(source)) return compositeWeekValues(source, week);
    await loadHistoryFor(week);
    return weekValuesSync(source, week, viewMode);
  }
  // Fetches what a saved week's pipeline run reads: the index, the week's
  // document and, when any source serves that week from a kept version, the
  // served versions. A failed read is recorded (historyLoaded).
  async function loadHistoryFor(week) {
    week = Number(week);
    if (!Number.isInteger(week)) return;
    try {
      const index = await historyIndex();
      await historyWeekDoc(index, week);
      if (PIPELINE_SOURCE_KEYS.some(key => servedVersionAt(index, key, week))) await historyServedVersions();
    } catch (error) {
      // historyLoaded holds the error; weekValuesSync words it.
    }
  }
  // A saved week's pipeline run including every source that has the week
  // (VP-8: the current I, league and pie; sources outside I are run and
  // shown, never counted). {result, dropped} | {reason}.
  function weekRun(week) {
    return weekPipeline(week);
  }
  // getWeekValues without the fetches (they must have resolved). view: the
  // tab whose values are read.
  function weekValuesSync(source, week, view) {
    week = Number(week);
    const unavailable = (reason, extra) => ({...historyUnavailable(source, week, reason, extra), setting: historySetting(view)});
    if (!Number.isInteger(week)) return unavailable("no week given");
    const base = seriesSource(source);
    if (!base || !visibleSourceKeys().includes(source)) return unavailable(`unknown series ${source}`);
    let index, doc;
    try {
      index = historyNow("index");
      doc = historyWeekDocNow(index, week);
    } catch (error) {
      return unavailable(`history could not be read: ${error.message}`);
    }
    const found = historyEntryOf(base, week, index, doc);
    if (!found.entry) return unavailable(found.error || found.missing);
    const run = weekRun(week);
    if (!run.result) return unavailable(run.reason);
    if (!run.result.sources[base]) {
      const why = run.dropped?.find(item => item.source === base)?.reason;
      return unavailable(why || `${sourceLabel(base)} is not priced on Week ${week}`);
    }
    const values = mapToValues(seriesValuesFrom(run.result, source, view));
    if (!Object.keys(values).length) return unavailable(`no ${scoreLabel()} values for Week ${week} at this setting`);
    return {source, week, available: true, values, setting: historySetting(view), origin: found.entry.origin,
      fingerprint: found.entry.fingerprint,
      method: `ValueModel.runValuePipeline ${run.result.version} on the Week ${week} saved inputs`,
      peers: Object.keys(run.result.sources).filter(key => key !== base)};
  }
  // The served week of a series from the history index, or an unavailable answer.
  function servedWeekOf(source, week, index) {
    if (index?.fixture_built_at && data?.built_at && index.fixture_built_at !== data.built_at) {
      return {error: "the history index belongs to a different build of the values"};
    }
    const served = index?.served?.[seriesSource(source) || source];
    if (!served || !Number.isInteger(served.week)) {
      return {error: served?.reason || `no saved week matches the ${sourceLabel(source)} values served now`};
    }
    return {served};
  }
  // The week before the one this series serves now (frame 22's exact pair).
  // The served week comes from the history index, which matches the served
  // inputs to a saved week by content fingerprint, not by the section label.
  async function getPriorWeek(source, week) {
    if (isCompositeKey(source)) return compositePriorWeek(source, week);
    let index;
    try {
      index = await historyIndex();
    } catch (error) {
      return historyUnavailable(source, week ?? null, `history could not be read: ${error.message}`);
    }
    const found = servedWeekOf(source, week, index);
    if (found.served) await loadHistoryFor(found.served.week - 1);
    return priorWeekSync(source, week, viewMode);
  }
  function priorWeekSync(source, week, view) {
    const unavailable = (asked, reason, extra) => ({...historyUnavailable(source, asked, reason, extra), setting: historySetting(view)});
    let index;
    try {
      index = historyNow("index");
    } catch (error) {
      return unavailable(week ?? null, `history could not be read: ${error.message}`);
    }
    const found = servedWeekOf(source, week, index);
    if (found.error) return unavailable(week ?? null, found.error);
    const served = found.served;
    const prior = served.week - 1;
    const extra = {currentWeek: served.week, priorWeek: prior,
      ...(served.label_mismatch ? {labelMismatch: served.label_mismatch} : {})};
    if (week !== undefined && week !== null && Number(week) !== prior) {
      return unavailable(Number(week), `Week ${week} is not the week before the served Week ${served.week}`, extra);
    }
    return {...weekValuesSync(source, prior, view), ...extra};
  }
  // Every history read the prior week needs (each served week's prior week,
  // the served versions). Awaited once before the first rebuild; a failure
  // only leaves the sources without a prior week (VP-1.2).
  async function preloadCompositeHistory() {
    try {
      const index = await historyIndex();
      const weeks = new Set(Object.values(index?.served || {}).map(rec => rec?.week).filter(Number.isInteger));
      const servedNeeded = [...weeks].some(week => PIPELINE_SOURCE_KEYS.some(key => servedVersionAt(index, key, week - 1)));
      await Promise.all([
        ...[...weeks].map(week => historyWeekDoc(index, week - 1).catch(() => null)),
        ...(servedNeeded ? [historyServedVersions().catch(() => null)] : []),
      ]);
    } catch (error) {
      // Recorded in historyLoaded; every pair then reports it.
    }
  }
  // Read-only: which saved weeks exist for a series, and the week served now.
  async function getHistoryWeeks(source) {
    if (isCompositeKey(source)) return compositeHistoryWeeks(source);
    let index;
    try {
      index = await historyIndex();
    } catch (error) {
      return {source, servedWeek: null, weeks: [], reason: `history could not be read: ${error.message}`};
    }
    const base = seriesSource(source) || source;
    const weeks = Object.keys(index?.weeks || {}).map(Number).filter(week => Number.isInteger(week)
      && index.weeks[String(week)]?.sources?.[base]).sort((a, b) => a - b);
    const served = index?.served?.[base];
    return {source, servedWeek: Number.isInteger(served?.week) ? served.week : null, weeks};
  }

  // ---- DDF Value history (JEG-465 / JEG-497 / VP-8) ----
  // A saved week's DDF Value is that week's pipeline run's (the same included
  // set, league and pie); the prior week is pipelinePrior.
  const COMPOSITE_HISTORY_METHOD = "ValueModel.runValuePipeline: equal-weight mean of the included sources' Adjusted values (VP-6.3)";
  const compositeExtra = version => {
    const inputs = versionInputs(version);
    return {version, inputs, series: [...inputs], excluded: compositeInputsInfo(version).excluded,
      minSources: COMPOSITE_MIN_SOURCES};
  };
  function ddfValuesOf(result, version) {
    const name = COMPOSITE_VERSION_NAMES[version];
    const values = {}, counts = {};
    Object.entries(result?.rows || {}).forEach(([playerKey, row]) => {
      const entry = row.ddfByVersion[name];
      if (!Number.isFinite(entry.value)) return;
      values[playerKey] = entry.value;
      counts[playerKey] = entry.count;
    });
    return {values, counts};
  }
  async function compositeWeekValues(version, week) {
    version = compositeVersionOf(version);
    week = Number(week);
    if (!pipeline) return historyUnavailable(version, week, "the engine has not loaded");
    const extra = compositeExtra(version);
    if (!Number.isInteger(week)) return historyUnavailable(version, week, "no week given", extra);
    if (!extra.inputs.length) return historyUnavailable(version, week, "no DDF Value input is available at this setting", extra);
    await loadHistoryFor(week);
    const run = weekRun(week);
    if (!run.result) return historyUnavailable(version, week, run.reason, {...extra, sources: [], dropped: run.dropped || []});
    const sources = extra.inputs.filter(key => run.result.included.includes(key));
    if (!sources.length) {
      return historyUnavailable(version, week, `no DDF Value input has Week ${week} saved`,
        {...extra, sources: [], dropped: run.dropped || []});
    }
    const blend = ddfValuesOf(run.result, version);
    return {source: version, week, available: true, values: blend.values, counts: blend.counts,
      ...extra, sources, dropped: (run.dropped || []).filter(item => extra.inputs.includes(item.source)),
      setting: historySetting(), method: COMPOSITE_HISTORY_METHOD};
  }
  // Δ pair for a version: exactly the rows' values[version] and its prior.
  // values/counts: the prior week; currentValues/currentCounts: this week.
  async function compositePriorWeek(version, week) {
    version = compositeVersionOf(version);
    const asked = week === undefined || week === null ? null : Number(week);
    if (!pipeline) return historyUnavailable(version, asked, "the engine has not loaded");
    const extra = {...compositeExtra(version), currentWeek: pipelineState.currentWeek, priorWeek: pipelineState.priorWeek};
    if (!pipelineState.priorAvailable || !pipelinePrior) return historyUnavailable(version, asked, pipelineState.priorReason, {...extra, sources: []});
    if (asked !== null && asked !== pipelineState.priorWeek) {
      return historyUnavailable(version, asked, `Week ${week} is not the week before the served Week ${pipelineState.currentWeek}`, extra);
    }
    const before = ddfValuesOf(pipelinePrior, version);
    const now = ddfValuesOf(pipeline, version);
    const sources = extra.inputs;
    return {source: version, week: pipelineState.priorWeek, available: true, values: before.values, counts: before.counts,
      currentValues: now.values, currentCounts: now.counts, sources: [...sources], dropped: [],
      seriesValues: Object.fromEntries(sources.map(key => [key, mapToValues(seriesValuesFrom(pipelinePrior, key, "adj"))])),
      ...extra, setting: historySetting(), method: COMPOSITE_HISTORY_METHOD};
  }
  // Saved weeks any input has, and the current week of the pair.
  async function compositeHistoryWeeks(version) {
    version = compositeVersionOf(version);
    const inputs = pipeline ? versionInputs(version) : [];
    const results = await Promise.all(inputs.map(key => getHistoryWeeks(key)));
    const weeks = [...new Set(results.flatMap(result => result.weeks))].sort((a, b) => a - b);
    return {source: version, servedWeek: pipelineState.priorAvailable ? pipelineState.currentWeek : null, weeks,
      inputs: [...inputs], series: [...inputs]};
  }

  // Math inspector (internal page, read-only). Every input and intermediate
  // of the value pipeline at the active setting, straight from the result the
  // chart draws (VP-11 TradeValueCurveDiagnostics.valuePipeline plus the
  // per-player rows). Nothing here prices a player.
  const mapToObject = map => {
    const out = {};
    map?.forEach((value, key) => { out[key] = value; });
    return out;
  };
  function getInspection() {
    const views = {};
    VIEW_MODE_ORDER.forEach(view => {
      views[view] = Object.fromEntries(visibleSourceKeys().map(key => [key, mapToObject(seriesValuesFrom(pipeline, key, view))]));
    });
    return {
      setting: {scoring, scoringField: scoringField(), teams, roster: {...rosterShape}, benchShare,
        positionShares: positionWeights ? {...positionWeights} : null,
        viewMode, savedSetup: onSavedSetup(), flexEligible: flexEligiblePositions()},
      versions: {pipeline: ValueModel.VALUE_PIPELINE_VERSION},
      positions: [...POSITION_ORDER],
      publishedKeys: [...AS_PUBLISHED_KEYS],
      seriesKeys: visibleSourceKeys(),
      labels: Object.fromEntries(visibleSourceKeys().map(key => [key, sourceLabel(key)])),
      included: [...pipelineState.included],
      excluded: pipelineState.excluded.map(entry => ({...entry})),
      natives: Object.fromEntries(Object.entries(pipelineNatives).map(([key, map]) => [key, mapToObject(map)])),
      valuePipeline: pipeline ? ValueModel.valuePipelineDiagnostics(pipeline) : null,
      priorValuePipeline: pipelinePrior ? ValueModel.valuePipelineDiagnostics(pipelinePrior) : null,
      rows: pipeline ? JSON.parse(JSON.stringify(pipeline.rows)) : {},
      // Per source, per player on its work list: native (or estimate), rank,
      // role, value above waivers, slices, Adjusted and VORP vs waivers.
      players: pipeline ? Object.fromEntries(Object.entries(pipeline.sources).map(([key, src]) =>
        [key, JSON.parse(JSON.stringify(src.players))])) : {},
      views,
      series: views.indexed,
      fixedPie: fixedPieDiagnostics()
    };
  }

  // JEG-482: a published chart's own ranking. The publisher's native values at
  // the active scoring (its superflex values where the roster has a superflex
  // slot and it publishes them), ranked high to low; ties share the better
  // rank. {playerKey: rank} over the canonical players the chart prices.
  function nativeRanksFor(source) {
    if (!AS_PUBLISHED_KEYS.has(source)) return null;
    const native = savedPublishedNative(source);
    const ordered = [...native.entries()].sort((a, b) => b[1] - a[1] || a[0] - b[0]);
    const ranks = new Map();
    let previous = null, rank = 0;
    ordered.forEach(([playerKey, value], index) => {
      if (value !== previous) { rank = index + 1; previous = value; }
      ranks.set(playerKey, rank);
    });
    return ranks;
  }

  // JEG-482 / VP-6.4 rank check, at the active setting: for every published
  // chart the Indexed values (listed and estimated players) must keep the
  // chart's own order -- every pair the chart ranks strictly apart stays
  // strictly apart, same way round (estimated players sit at or below the
  // lowest listed one). Informational in the diagnostics (indexedOrder);
  // tests/test_rank_guard.py gates it across the 12 combos.
  function indexedOrderDiagnostics() {
    const sources = {};
    AS_PUBLISHED_KEYS.forEach(key => {
      const src = pipeline?.sources?.[key];
      if (!src || src.indexedFactor === null || src.indexedFactor === undefined) return;
      const indexed = seriesValuesFrom(pipeline, key, "indexed");
      // The chart's own order: native (or estimate) descending, listed first.
      const order = Object.entries(src.players).map(([playerKey, p]) => ({playerKey: Number(playerKey), ...p}));
      order.sort((a, b) => b.native - a.native || (a.estimated === b.estimated ? 0 : a.estimated ? 1 : -1) || a.playerKey - b.playerKey);
      let pairs = 0, inversions = 0, first = null;
      for (let i = 0; i < order.length; i += 1) {
        for (let j = i + 1; j < order.length; j += 1) {
          if (order[i].native === order[j].native) continue;
          pairs += 1;
          if (indexed.get(order[i].playerKey) > indexed.get(order[j].playerKey)) continue;
          inversions += 1;
          if (!first) first = {higher: order[i].playerKey, lower: order[j].playerKey};
        }
      }
      sources[key] = {n: order.length, pairs, inversions, first, factor: src.indexedFactor};
    });
    return {ok: Object.values(sources).every(row => row.inversions === 0), sources};
  }

  window.TradeValueCurveControls = {
    setPosition,
    setScoring,
    setTeams,
    setBenchShare,
    setAbsenceRate: setBenchShare,
    setLockOrder,
    setModel: () => {},
    redraw: () => draw(),
    getState: () => ({position, scoring, teams, model: "monday", valueMode:"indexed", viewMode, viewTitle:VIEW_MODE_DEFS[viewMode]?.title || null, lockOrder, benchShare, absenceRate:benchShare, activeSources:activeSourceKeys()}),
    getLockedDomain: () => displayRows().map((row, index) => ({rank:index + 1, player_key:row.player_key, name:row.name})),
    getPlayerValues: query => {
      const needle = String(query || "").trim().toLowerCase();
      if (!needle) return [];
      return universe.filter(row => row.name.toLowerCase().includes(needle)).slice(0, 8).map(row => ({
        player_key: row.player_key,
        name: row.name,
        team: row.team,
        pos: row.pos,
        ddfTier: row.ddfTier,
        values: Object.fromEntries([...visibleSourceKeys(), ...COMPOSITE_VERSION_KEYS].map(key => [key, row.values[key] ?? null]))
      }));
    },
    // v2 front end (read-only): the ranked rows and source metadata the new
    // layout renders, straight from the same maps this chart draws.
    // JEG-471 / JEG-479 / JEG-497: each row also carries the DDF Composite
    // Value in three versions, the same in every view: values.ddf_value,
    // values.ddf_value_charts, values.ddf_value_projections (null when no
    // included input prices him; missingReasons and ddfReason say so),
    // ddfCount / ddfChartsCount / ddfProjectionsCount, the low-confidence
    // flags (one input), ddfPrior, ddfTier and ddfByVersion (all three, both
    // weeks). Field list: docs/v2-design-notes.md "Back-end contract: DDF Value".
    getRows: () => displayRows().map(rowCopy),
    // Every priced player at every position (Compare a trade), ignoring the
    // position filter; the same value maps getRows reads.
    getAllRows: () => universe.map(rowCopy),
    // JEG-502 (read-only, lazy): search every player in players.json, the
    // whole active NFL universe included, and get any one player's row. A
    // player no source prices is materialised on demand (materialized: true,
    // universe_only: true) with values 0 where a chart is fully loaded, null
    // with missingReasons[key] elsewhere, and roster_status / roster_status_label
    // / unpriced_reason. He never enters getAllRows, the curves or the pies.
    searchPlayers: (query, options) => searchPlayers(query, options),
    getPlayer: playerKey => playerRow(playerKey),
    // JEG-482 (read-only): the player's rank on the publisher's own chart at
    // the active scoring ("#3 on FantasyCalc"); null when the chart does not
    // price him or the source is not a published chart. getNativeRanks(source)
    // returns every rank as {playerKey: rank}. See docs/v2-design-notes.md.
    getNativeRank: (playerKey, source) => nativeRanksFor(source)?.get(Number(playerKey)) ?? null,
    getNativeRanks: source => {
      const ranks = nativeRanksFor(source);
      return ranks ? Object.fromEntries(ranks) : null;
    },
    isReady: () => engineReady,
    getRankSource: () => selectedRankSourceKey(),
    getActiveSources: () => activeSourceKeys(),
    getReferenceWeek: () => activeReferenceWeek(),
    getRosterShape: () => ({...rosterShape}),
    // Back-end contract: history (read-only; both return Promises).
    getWeekValues,
    getPriorWeek,
    getHistoryWeeks,
    setRosterSpot,
    setBenchShareFraction,
    // The bench share in effect: the override when on, else the computed
    // readout's overall share (JEG-536, ES-14).
    getBenchShare: () => benchShare,
    // ES-14 (JEG-536): the readout and the reader settings that cause it.
    // Field list: docs/v2-design-notes.md "Back-end contract: bench share".
    getBenchShareReadout: () => benchShareReadout(),
    getBenchShareOverride: () => benchShareOverride,
    setBenchShareOverride,
    getLeagueWeeks: () => ({regularSeasonEnd: lineupSettings.regularSeasonEnd, playoffWeeks: [...lineupSettings.playoffWeeks]}),
    setLeagueWeeks: (weeks, publish = true) => setLineupSettings({regularSeasonEnd: weeks?.regularSeasonEnd,
      playoffWeeks: weeks?.playoffWeeks}, publish),
    getOptimizeFor: () => lineupSettings.optimizeFor,
    setOptimizeFor: (value, publish = true) => setLineupSettings({optimizeFor: value}, publish),
    getInjuryHistory: () => lineupSettings.injuryHistory,
    setInjuryHistory: (value, publish = true) => setLineupSettings({injuryHistory: value}, publish),
    getProjectionConfidence: () => lineupSettings.projectionConfidence,
    setProjectionConfidence: (value, publish = true) => setLineupSettings({projectionConfidence: value}, publish),
    getLineupSettings,
    setLineupSettings: (partial, publish = true) => {
      const p = {...(partial || {})};
      const hasOverride = Object.prototype.hasOwnProperty.call(p, "benchShareOverride");
      const override = p.benchShareOverride;
      delete p.benchShareOverride;
      setLineupSettings(p, publish && !hasOverride);
      if (hasOverride) setBenchShareOverride(override, publish);
      return getLineupSettings();
    },
    getLineupSettingsDefaults: () => lineupDefaults(),
    getLineupParameters: () => (pipeline?.lineup ? JSON.parse(JSON.stringify(pipeline.lineup)) : null),
    // Read-only (fe-fidelity): the share each position was actually priced
    // at, bench_share_used from the live two-tier calibration at `share`
    // (default: the active bench share). Below a position's feasible window
    // the engine prices at a higher share than requested. {QB, RB, WR, TE};
    // null for a withheld position; null when there is no calibration.
    // Read-only: the bench share the DDF weights are built with at `share`
    // (default: the active one), VP-4.2: the share itself, 0 when no source
    // has bench surplus (e.g. bench 0), 1 when none has starter surplus. One
    // share for every position ({QB, RB, WR, TE}); there are no feasibility
    // windows any more (the two-tier calibration is retired, VP-10).
    getBenchShareUsed: (share = benchShare) => {
      if (!pipeline) return null;
      const sum = mix => POSITION_ORDER.reduce((t, pos) => t + mix[pos], 0);
      const sumS = sum(pipeline.starterMixMean), sumB = sum(pipeline.benchMixMean);
      const used = sumB === 0 ? 0 : sumS === 0 ? 1 : Number(share);
      return Object.fromEntries(POSITION_ORDER.map(pos => [pos, used]));
    },
    getBenchBounds: () => [...BENCH_SHARE_BOUNDS],
    getPositionWeights: () => activePositionWeights(),
    // JEG-452 (BE-2): see setPositionWeights above for the semantics.
    setPositionWeights,
    resetPositionWeights: (publish = true) => setPositionWeights(null, publish),
    getDefaultPositionWeights: () => bakedPositionWeights(),
    getPositionWeightBounds: () => positionWeightBounds(),
    // JEG-471: getSourceInfo({includeComposite: true}) appends the DDF Value
    // entry (key "ddf_value", composite: true). Without the option the list
    // is the plotted series only, as before.
    getSourceInfo: options => [...visibleSourceKeys().map(key => ({
      key,
      label: sourceLabel(key),
      week: weekForSource(key),
      stale: sourceIsStale(key),
      available: sourceAvailable(key),
      paused: false,
      // The source's section is missing from this build's data (dropped,
      // not fatal): show it as unavailable, never as zeros.
      unavailable: sourceMissingFromData(key),
      active: activeSources.has(key),
      color: SOURCE_STYLES[key]?.color || null,
      // VP-2.4h: the positions where this source's values include estimated
      // players (rosterable players it does not list), and how each
      // position's waiver line was set.
      waiverNote: sourceWaiverNote(key),
      waiver: sourceWaiverInfo(key),
      // VP-1: whether the source counts in the DDF Value and weights this
      // week, and why not.
      included: pipelineState.included.includes(seriesSource(key)),
      excludedReason: pipelineState.excluded.find(e => e.key === seriesSource(key))?.reason || null
    })), ...(options && options.includeComposite ? COMPOSITE_VERSION_KEYS.map(compositeSourceInfo) : [])],
    // JEG-471: the DDF Value inputs; see setCompositeInputs.
    // JEG-479: getCompositeInputs([view]) for the active view by default;
    // getCompositeValues([view]) gives one view's DDF Value for both weeks.
    // JEG-497: getCompositeInputs([version]) / getCompositeValues([version]),
    // version "blended" (default) | "charts" | "projections", or the series
    // key ddf_value | ddf_value_charts | ddf_value_projections; the same in
    // every view. Anything else (a former view name) reads the blend.
    getCompositeInputs: version => compositeInputsInfo(version),
    getCompositeValues: version => compositeValuesInfo(version),
    getLoadStatus: () => productLoadStatus(),
    setCompositeInputs,
    resetCompositeInputs: (publish = true) => setCompositeInputs(null, publish),
    getAdjustmentWeights: () => ({allocation: adjustmentAllocationRows(), cells: adjustmentWeightRows()}),
    getZones: () => Object.fromEntries(boundaryMarkers().map(marker => [marker.key, marker.value])),
    // v2 tier labels (read-only, 2026-10-08): the roster-zone cutoffs getZones()
    // would give if the list were ranked by `key` in position `pos` (default:
    // the current position), unclamped. Same roster ordinals as rosterOrdinals();
    // for DDF Value use row.ddfTier instead (null here).
    getZonesFor: (key, pos = position) => {
      if (isCompositeKey(key)) return null;
      const shape = rosterShape;
      const slots = shape.QB + shape.RB + shape.WR + shape.TE + shape.FLEX + (shape.SUPERFLEX || 0);
      let starter;
      let bench;
      if (pos === "ALL") {
        starter = teams * slots;
        bench = teams * (slots + shape.BENCH);
      } else {
        const counts = allocationCounts();
        const group = pos === "FLEX" ? ["RB", "WR", "TE"] : [pos];
        starter = group.reduce((sum, p) => sum + (counts.lineup[p] || 0), 0);
        bench = group.reduce((sum, p) => sum + (counts.rostered[p] || 0), 0);
      }
      if (!Number.isFinite(starter) || !Number.isFinite(bench)) return null;
      return {starter_to_bench: starter + 0.5, bench_to_waiver: bench + 0.5};
    },
    // Internal math inspector (read-only): see getInspection above.
    getInspection
  };

  function fullRankMax() {
    return Math.max(1, displayRows().length);
  }

  function resetZoom() {
    zoomLow = 1;
    zoomHigh = fullRankMax();
    syncZoom();
  }

  function syncZoom() {
    const maximum = fullRankMax();
    zoomHigh = Math.min(zoomHigh || maximum, maximum);
    zoomLow = Math.max(1, Math.min(zoomLow, zoomHigh));
    const zoom = $("#zoomSeg");
    zoom.replaceChildren();
    const ordinals = rosterOrdinals();
    const benchToWaiver = markerDefinitions().find(marker => marker.key === "bench_to_waiver")?.ordinal || ordinals.bench;
    const presets = [
      ["Full", 1, maximum],
      ["Top 25", 1, Math.min(25, maximum)],
      ["Top 50", 1, Math.min(50, maximum)],
      ["Starter", 1, Math.min(maximum, Math.max(1, ordinals.starter))],
      ["Bench", Math.min(maximum, Math.max(1, ordinals.starter + 1)), Math.min(maximum, Math.max(ordinals.starter + 1, benchToWaiver))],
      ["Waiver", Math.min(maximum, Math.max(1, benchToWaiver + 1)), maximum]
    ];
    presets.forEach(([label, low, high]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.disabled = high < low;
      button.classList.toggle("active", zoomLow === low && zoomHigh === high);
      button.addEventListener("click", () => { zoomLow = low; zoomHigh = high; syncZoom(); draw(); });
      zoom.appendChild(button);
    });
    const low = $("#zLo"), high = $("#zHi");
    low.max = maximum;
    high.max = maximum;
    low.value = zoomLow;
    high.value = zoomHigh;
    const percent = value => maximum <= 1 ? 0 : (value - 1) / (maximum - 1) * 100;
    $("#zfill").style.left = `calc(8px + (100% - 16px) * ${percent(zoomLow) / 100})`;
    $("#zfill").style.width = `calc((100% - 16px) * ${(percent(zoomHigh) - percent(zoomLow)) / 100})`;
    $("#zlabel").textContent = `Player rank ${zoomLow}–${zoomHigh}`;
    syncYAxis();
    renderVisiblePlayers();
  }

  function syncYAxis() {
    const low = $("#yLo"), high = $("#yHi"), fill = $("#yfill"), label = $("#ylabel");
    if (!low || !high || !fill || !label) return;
    const extent = chartValueExtent();
    low.max = extent.max;
    high.max = extent.max;
    if (yAxisAuto) {
      yLow = extent.min;
      yHigh = extent.max;
    } else {
      yLow = Math.max(extent.min, Math.min(yLow, yHigh - 1));
      yHigh = Math.min(extent.max, Math.max(yHigh, yLow + 1));
    }
    low.value = yLow;
    high.value = yHigh;
    const pct = value => extent.max <= 0 ? 0 : value / extent.max * 100;
    fill.style.left = `calc(8px + (100% - 16px) * ${pct(yLow) / 100})`;
    fill.style.width = `calc((100% - 16px) * ${(pct(yHigh) - pct(yLow)) / 100})`;
    label.textContent = yAxisAuto ? `Y axis auto · 0–${extent.max}` : `Y value ${Math.round(yLow)}–${Math.round(yHigh)}`;
    $("#yReset")?.toggleAttribute("disabled", yAxisAuto);
  }

  function bindZoom() {
    $("#zLo").addEventListener("input", event => {
      zoomLow = Math.min(Number(event.target.value), zoomHigh);
      syncZoom();
      draw();
    });
    $("#zHi").addEventListener("input", event => {
      zoomHigh = Math.max(Number(event.target.value), zoomLow);
      syncZoom();
      draw();
    });
    $("#hideZeroTail")?.addEventListener("change", event => {
      hideZeroTail = event.target.checked;
      crossRank = null;
      resetZoom();
      draw();
    });
    $("#yLo")?.addEventListener("input", event => {
      yAxisAuto = false;
      yLow = Math.min(Number(event.target.value), yHigh - 1);
      syncYAxis();
      draw();
    });
    $("#yHi")?.addEventListener("input", event => {
      yAxisAuto = false;
      yHigh = Math.max(Number(event.target.value), yLow + 1);
      syncYAxis();
      draw();
    });
    $("#yReset")?.addEventListener("click", () => {
      yAxisAuto = true;
      syncYAxis();
      draw();
    });
    $("#curveFindPlayer")?.addEventListener("click", findPlayerByName);
    $("#curvePlayerSearch")?.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        event.preventDefault();
        findPlayerByName();
      }
    });
  }

  // The slot fill (VP-7.2) in the shape the zone code reads:
  // {direct, lineup, rostered} per position.
  function allocationCounts() {
    const alloc = slotFill() || {};
    const pick = field => Object.fromEntries(POSITION_ORDER.map(pos => [pos, alloc[pos]?.[field] || 0]));
    return {direct: pick("dedicated"), lineup: pick("starters"), rostered: pick("rostered")};
  }

  // Each boundary sits at the cutoff for the LAST player of its division
  // (2026-09-19, user directive): Starter = last startable player
  // (dedicated starters + flex share), Bench = last benchable player
  // (last rostered), Waiver = last waiver player shown on the chart.
  function rosterOrdinals() {
    const counts = allocationCounts();
    if (position === "ALL") return {
      starter: teams * (rosterShape.QB + rosterShape.RB + rosterShape.WR + rosterShape.TE + rosterShape.FLEX + (rosterShape.SUPERFLEX || 0)),
      bench: teams * (rosterShape.QB + rosterShape.RB + rosterShape.WR + rosterShape.TE + rosterShape.FLEX + (rosterShape.SUPERFLEX || 0) + rosterShape.BENCH)
    };
    // JEG-471: ranked by DDF Value, a position's zones are its DDF tiers
    // (cut at the league's slot counts by DDF Value), so the boundaries and
    // row.ddfTier always agree.
    if (selectedRankSourceKey() === COMPOSITE_KEY) {
      const rows = universe.filter(isPosition);
      const starter = rows.filter(row => row.ddfTier === "starter").length;
      return {starter, bench: starter + rows.filter(row => row.ddfTier === "bench").length};
    }
    if (position === "FLEX") return {
      starter: counts.lineup.RB + counts.lineup.WR + counts.lineup.TE,
      bench: counts.rostered.RB + counts.rostered.WR + counts.rostered.TE
    };
    return {
      starter: counts.lineup[position],
      bench: counts.rostered[position]
    };
  }

  function markerDefinitions() {
    const ordinals = rosterOrdinals();
    const sourceKey = selectedRankSourceKey();
    // 2026-10-03 (Jeremy, supersedes 2026-09-19): BOTH markers use roster
    // ordinals so they shift with league parameters. Bench-to-Waiver sits
    // after the last rostered player (ordinals.bench), not after the last
    // positive value -- the waiver line is a roster concept, and the values
    // are calibrated to it. Using lastPositive measured coverage depth, not
    // the league's waiver line.
    return [
      {key:"starter_to_bench", ordinal:ordinals.starter, value:ordinals.starter + 0.5, label:"Starter → Bench", color:"#238a52", source:sourceKey},
      {key:"bench_to_waiver", ordinal:ordinals.bench, value:ordinals.bench + 0.5, label:"Bench → Waiver", color:"#c43d32", dotted:true, source:sourceKey}
    ];
  }

  // Vertical roster rank cutoffs under EVERY lock (2026-09-19, user
  // directive; marker yardstick updated 2026-10-03): show the transitions
  // between roster zones. Starter-to-Bench sits after the last startable
  // player; Bench-to-Waiver sits after the last rostered player, so waiver
  // territory is the pool to the right of the second line. Both cutoffs
  // shift with league parameters (teams, roster shape). No horizontal value
  // thresholds under any lock.
  function boundaryMarkers() {
    const maximum = fullRankMax();
    return markerDefinitions().map(marker => ({
      ...marker,
      axis:"x",
      value:Math.max(1, Math.min(maximum, marker.value))
    }));
  }

  // The fixed-pie invariant (VP-5): over its work list (listed and estimated
  // players), every source's Adjusted values sum to the league pie (less any
  // budget a source cannot fund, VP-5.3), each of its eight groups to its
  // funded budget (pie x DDF weight), and its VORP vs waivers values to the
  // pie. Each chart's Indexed values over its shared players sum to their
  // blended DDF Value (VP-6.4). `overrides` ({source: Map player -> Adjusted
  // value}) checks a substitute map instead (harness simulations).
  function fixedPieDiagnostics(overrides = null, result = pipeline) {
    const pie = result?.pie ?? null;
    const tolerance = Math.max(1e-6, 1e-9 * (pie || 0));
    const checks = [];
    Object.entries(result?.sources || {}).forEach(([key, src]) => {
      if (!src.hasWeights) {
        checks.push({source: key, basis: "no implied weights", total: 0, target: 0, delta: 0, ok: true});
        return;
      }
      const override = overrides?.[key] || null;
      const valueOf = (playerKey, p) => override ? (override.get(Number(playerKey)) ?? 0) : p.adjusted;
      const funded = {...result.budgets};
      (src.unfundedMoved || []).forEach(move => { funded[move.to] += move.amount; funded[move.from] -= move.amount; });
      const unpaid = (src.unfundedGroups || []).reduce((sum, g) => sum + g.amount, 0);
      (src.unfundedGroups || []).forEach(g => { funded[g.group] = 0; });
      const groups = {};
      Object.keys(funded).forEach(g => { groups[g] = {total: 0, budget: funded[g]}; });
      let total = 0, vorpTotal = 0;
      Object.entries(src.players).forEach(([playerKey, p]) => {
        const value = valueOf(playerKey, p);
        total += value;
        vorpTotal += p.vorpDisplay;
        // A player's value splits over his two slices at the source's rates.
        const bench = src.rates[`${p.pos}|bench`] * p.benchSlice;
        const starter = src.rates[`${p.pos}|starter`] * p.starterSlice;
        const share = bench + starter > 0 ? value / (bench + starter) : 0;
        groups[`${p.pos}|bench`].total += bench * share;
        groups[`${p.pos}|starter`].total += starter * share;
      });
      const target = pie - unpaid;
      const groupsOk = Object.values(groups).every(g => Math.abs(g.total - g.budget) <= tolerance);
      const ok = Math.abs(total - target) <= tolerance && groupsOk && Math.abs(vorpTotal - pie) <= tolerance;
      checks.push({source: key, basis: "work list", n: Object.keys(src.players).length, total, target,
        delta: total - target, vorpTotal, groups, groupsOk, unpaid, included: src.included, ok});
    });
    const indexed = {};
    Object.entries(result?.indexed || {}).forEach(([key, ix]) => {
      if (ix.factor === null) {
        indexed[key] = {factor: null, ok: true, reason: "Not enough shared players to index"};
        return;
      }
      const delta = ix.nativeTotal * ix.factor - ix.ddfTotal;
      indexed[key] = {factor: ix.factor, shared: ix.sharedPlayers, ddfTotal: ix.ddfTotal, delta,
        ok: Math.abs(delta) <= tolerance};
    });
    return {tolerance, pie, checks, indexed,
      ok: checks.every(check => check.ok) && Object.values(indexed).every(row => row.ok)};
  }

  // views-audit/2 (VP-5, VP-6.4): each tab's invariant, measured on the
  // values the tab plots, for every source it shows, at the active setting.
  //   indexed  -- each chart's Indexed total over its shared players equals
  //               their blended DDF Value total;
  //   vorp     -- each source's VORP vs waivers total equals the pie;
  //   adjusted -- each source's Adjusted total equals the pie and each group
  //               its budget (fixedPieDiagnostics).
  function viewInvariantsDiagnostics() {
    const fixedPie = fixedPieDiagnostics();
    const out = {version: "views-audit/2", informational: false, tolerance: fixedPie.tolerance, pie: fixedPie.pie,
      basis: "each source's work list (VP-5); each chart's shared players (VP-6.4)",
      indexed: {sources: {}}, vorp: {sources: {}}, adjusted: {sources: {}}};
    Object.entries(fixedPie.indexed).forEach(([key, row]) => {
      out.indexed.sources[key] = {...row, holds: row.ok, gated: true};
    });
    fixedPie.checks.forEach(check => {
      const vorpHolds = check.vorpTotal === undefined || Math.abs(check.vorpTotal - fixedPie.pie) <= fixedPie.tolerance;
      out.vorp.sources[check.source] = {total: check.vorpTotal ?? 0, target: fixedPie.pie, holds: vorpHolds, gated: true};
      out.adjusted.sources[check.source] = {total: check.total, target: check.target, groups: check.groups || null,
        holds: check.ok, gated: true};
    });
    ["indexed", "vorp", "adjusted"].forEach(view => {
      const rows = Object.values(out[view].sources);
      out[view].holds = rows.every(row => row.holds);
      out[view].gatedHold = out[view].holds;
    });
    out.gatedHold = out.indexed.gatedHold && out.vorp.gatedHold && out.adjusted.gatedHold;
    return out;
  }

  function positionalPeaks(values) {
    const peaks = {};
    POSITION_ORDER.forEach(pos => { peaks[pos] = 0; });
    values?.forEach((value, playerKey) => {
      const pos = canonicalByKey.get(playerKey)?.pos;
      if (!POSITION_ORDER.includes(pos) || !Number.isFinite(value)) return;
      if (value > peaks[pos]) peaks[pos] = value;
    });
    return peaks;
  }

  function yAxisScale(rows) {
    const values = rows
      .slice(Math.max(0, zoomLow - 1), Math.max(zoomLow, zoomHigh))
      .flatMap(row => activeSourceKeys().map(key => row.values[key]))
      .filter(Number.isFinite);
    const dataMax = values.length ? Math.max(...values) : 0;
    const bandMin = yAxisAuto ? 0 : yLow;
    const cappedMax = yAxisAuto ? dataMax : yHigh;
    const effectiveMax = Math.max(cappedMax, bandMin + 1);
    if (dataMax <= 0) return {min:bandMin, max:Math.max(10, effectiveMax), step:1};
    const roughStep = (effectiveMax - bandMin) / 9;
    const magnitude = 10 ** Math.floor(Math.log10(roughStep));
    const normalized = roughStep / magnitude;
    const niceFactor = [1, 2, 2.5, 5, 10].find(candidate => candidate >= normalized) || 10;
    const step = niceFactor * magnitude;
    return {min:bandMin, max: Math.max(bandMin + step, Math.ceil(effectiveMax / step) * step), step};
  }

  function formatScore(value) {
    return Number.isFinite(value) ? Number(value).toFixed(1) : "—";
  }

  function renderVisiblePlayers() {
    const container = $("#visiblePlayersList");
    if (!container) return;
    const keys = activeSourceKeys();
    const axis = yAxisScale(displayRows());
    const axisMin = yAxisAuto ? axis.min : yLow;
    const axisMax = yAxisAuto ? axis.max : yHigh;
    const rows = displayRows()
      .slice(Math.max(0, zoomLow - 1), zoomHigh)
      .filter(row => keys.some(key => Number.isFinite(row.values[key]) && row.values[key] >= axisMin && row.values[key] <= axisMax));
    if (!rows.length || !keys.length) {
      container.innerHTML = `<p class="visible-empty">No players or active scores in the current view.</p>`;
      return;
    }
    const head = `<tr><th>Rank</th><th>Player</th><th>DDF Value tier</th>${keys.map(key => `<th>${sourceLabel(key)}</th>`).join("")}</tr>`;
    const body = rows.map(row => {
      const rank = displayRows().findIndex(candidate => candidate.player_key === row.player_key) + 1;
      return `<tr><td>${rank}</td><td><strong>${row.name}</strong><span>${row.pos} · ${row.team}</span></td><td>${row.ddfTier || "—"}</td>${keys.map(key => `<td>${formatScore(row.values[key])}</td>`).join("")}</tr>`;
    }).join("");
    container.innerHTML = `<p class="visible-note">Players shown match the selected player-rank axis plus the current X and Y view. Reset Y axis to restore the full value range.</p><div class="visible-table-wrap"><table><thead>${head}</thead><tbody>${body}</tbody></table></div>`;
  }

  function syncPlayerOptions() {
    const list = $("#curvePlayerOptions");
    if (!list || !universe.length) return;
    list.innerHTML = universe
      .slice()
      .sort((a, b) => a.name.localeCompare(b.name))
      .map(row => `<option value="${row.name}">${row.pos} · ${row.team}</option>`)
      .join("");
  }

  function findPlayerByName() {
    const input = $("#curvePlayerSearch");
    const status = $("#curveFindStatus");
    const query = String(input?.value || "").trim().toLowerCase();
    if (!query) {
      if (status) status.textContent = "Type a player name.";
      return;
    }
    const rows = displayRows();
    const exact = rows.find(row => row.name.toLowerCase() === query);
    const match = exact || rows.find(row => row.name.toLowerCase().includes(query));
    if (!match) {
      if (status) status.textContent = "No match in this view.";
      return;
    }
    const rank = rows.findIndex(row => row.player_key === match.player_key) + 1;
    const windowSize = Math.min(28, Math.max(12, Math.round(fullRankMax() * 0.08)));
    zoomLow = Math.max(1, rank - Math.floor(windowSize / 2));
    zoomHigh = Math.min(fullRankMax(), zoomLow + windowSize);
    zoomLow = Math.max(1, Math.min(zoomLow, Math.max(1, zoomHigh - windowSize)));
    crossRank = rank;
    syncZoom();
    draw();
    const rect = canvas.getBoundingClientRect();
    const clientX = rect.left + geometry.pad.left + (rank - zoomLow) / Math.max(1, zoomHigh - zoomLow) * geometry.innerWidth;
    showTooltip(rank, clientX, rect.top + geometry.pad.top + 18, false);
    if (status) status.textContent = `${match.name}: ${sourceLabel(selectedRankSourceKey())} player-axis rank ${rank}.`;
  }

  function clearCanvasForFailedGuard() {
    const context = canvas?.getContext?.("2d");
    if (!context) return;
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, canvas.width, canvas.height);
  }

  function draw() {
    // Fail closed consistently. The resize listener calls draw() directly, so
    // without this a guard failure produced a contradictory page: the status
    // line said "Curves unavailable" while the next window resize quietly
    // painted the very chart the guard had rejected.
    if (!guardsPassed) return;
    const rows = displayRows();
    if (!data || !rows.length) return;
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (!width || !height) return;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    const context = canvas.getContext("2d");
    context.scale(ratio, ratio);
    context.clearRect(0, 0, width, height);
    const dark = matchMedia("(prefers-color-scheme: dark)").matches;
    const grid = dark ? "#3f4a52" : "#e1e5e2";
    const text = dark ? "#c2cbd1" : "#65727c";
    const pad = {left: 48, right: 12, top: 28, bottom: 74};
    const innerWidth = Math.max(1, width - pad.left - pad.right);
    const innerHeight = Math.max(1, height - pad.top - pad.bottom);
    const x = rank => pad.left + (rank - zoomLow) / Math.max(1, zoomHigh - zoomLow) * innerWidth;
    const axis = yAxisScale(rows);
    const y = value => {
      const clamped = Math.max(axis.min, Math.min(axis.max, clampValue(value)));
      return pad.top + innerHeight - (clamped - axis.min) / Math.max(1, axis.max - axis.min) * innerHeight;
    };
    geometry = {width, height, pad, innerWidth, innerHeight, zoomLow, zoomHigh, yMin:axis.min, yMax:axis.max};

    context.font = '9px "IBM Plex Mono", monospace';
    context.textAlign = "right";
    context.strokeStyle = grid;
    context.fillStyle = text;
    context.lineWidth = 1;
    for (let value = axis.min; value <= axis.max + axis.step / 2; value += axis.step) {
      context.beginPath();
      context.moveTo(pad.left, y(value));
      context.lineTo(width - pad.right, y(value));
      context.stroke();
      context.fillText(Number.isInteger(value) ? String(value) : value.toFixed(1), pad.left - 5, y(value) + 3);
    }
    context.textAlign = "center";
    for (let index = 0; index <= 5; index += 1) {
      const rank = Math.round(zoomLow + (zoomHigh - zoomLow) * index / 5);
      context.fillText(String(rank), x(rank), height - 24);
    }
    context.font = '600 10px "IBM Plex Mono", monospace';
    context.fillText("Player rank", pad.left + innerWidth / 2, height - 7);
    context.save();
    context.translate(10, pad.top + innerHeight / 2);
    context.rotate(-Math.PI / 2);
    context.fillText("Value", 0, 0);
    context.restore();
    context.font = '9px "IBM Plex Mono", monospace';

    const markers = boundaryMarkers();
    markers.forEach((marker, index) => {
      context.strokeStyle = marker.color;
      context.fillStyle = marker.color;
      context.lineWidth = 1.35;
      context.setLineDash(marker.dotted ? [4, 3] : []);
      context.beginPath();
      if (marker.value < zoomLow || marker.value > zoomHigh) {
        context.setLineDash([]);
        return;
      }
      context.moveTo(x(marker.value), pad.top);
      context.lineTo(x(marker.value), pad.top + innerHeight);
      context.stroke();
      context.textAlign = "center";
      context.fillText(marker.label, Math.min(Math.max(x(marker.value), pad.left + 27), width - pad.right - 27), pad.top + innerHeight + 13 + index * 9);
      context.setLineDash([]);
    });

    context.save();
    context.beginPath();
    context.rect(pad.left, pad.top, innerWidth, innerHeight);
    context.clip();
    activeSourceKeys().forEach(key => {
      const style = SOURCE_STYLES[key];
      context.strokeStyle = style.color;
      context.lineWidth = key.endsWith("_adjusted") ? 1.8 : 2.3;
      context.lineJoin = "round";
      context.lineCap = "round";
      context.setLineDash(style.dash);
      context.beginPath();
      let drawing = false;
      let prevPx = 0, prevPy = 0;
      rows.forEach((row, index) => {
        const rank = index + 1;
        const value = row.values[key];
        if (rank < zoomLow || rank > zoomHigh || !Number.isFinite(value)) {
          drawing = false;
          return;
        }
        const px = x(rank), py = y(value);
        if (!drawing) {
          context.moveTo(px, py);
        } else {
          // Quadratic smoothing: curve through midpoints for a smoother
          // visual without changing the underlying data values.
          const midX = (prevPx + px) / 2, midY = (prevPy + py) / 2;
          context.quadraticCurveTo(prevPx, prevPy, midX, midY);
        }
        prevPx = px; prevPy = py;
        drawing = true;
      });
      context.stroke();
      context.setLineDash([]);
    });

    if (crossRank !== null && crossRank >= zoomLow && crossRank <= zoomHigh) {
      context.strokeStyle = dark ? "rgba(255,255,255,.58)" : "rgba(18,32,44,.52)";
      context.lineWidth = 1;
      context.setLineDash([5, 4]);
      context.beginPath();
      context.moveTo(x(crossRank), pad.top);
      context.lineTo(x(crossRank), pad.top + innerHeight);
      context.stroke();
      context.setLineDash([]);
    }
    context.restore();

    $("#legend").innerHTML = activeSourceKeys().map(key => {
      const style = SOURCE_STYLES[key];
      const lineStyle = key.endsWith("_adjusted") ? "dashed" : "solid";
      return `<span><span class="sw" style="background:transparent;border-top:3px ${lineStyle} ${style.color}"></span>${sourceLabel(key)}</span>`;
    }).join("");
    const markerText = markers.map(marker => `${marker.label} after rank ${marker.ordinal}`).join(" · ");
    // JEG-290: the middle clause of the footnote must vary by viewMode — the
    // Indexed/Value-above-waivers/Adjusted tabs each describe a different
    // underlying valuation, so a single static sentence was misleading readers.
    // JEG-225: compare via VIEW_MODE_ORDER — the "vorp" string literal may
    // only appear in the VIEW_MODE_ORDER declaration, never in code or copy.
    // Re-restored 2026-10-04 (dropped by the JEG-325 refactor).
    const footnoteMiddle = viewMode === VIEW_MODE_ORDER[1]
      ? "VORP vs waivers: each source's value above its waiver line, one factor per source so every source totals the league pie"
      : viewMode === "adj"
      ? `Adjusted values: every source split by the DDF Value weights (bench ${Math.round(benchShare * 100)}% of the pie) and summing to the league pie`
      : "Indexed: each chart's own numbers times one factor so its listed players total their DDF Value; estimated players marked";
    $("#curveFootnote").textContent = `${activeSourceKeys().length} active league-compatible series shown · every curve shares the ${sourceLabel(selectedRankSourceKey())} player order; ${footnoteMiddle} · roster transitions: ${markerText}.`;
    renderVisiblePlayers();
    canvas.setAttribute("aria-label", "Trade value curves with the selected player rank on the horizontal axis, value on the vertical axis, and vertical roster transition lines from starter to bench and bench to waiver. Use Home or End, then the left and right arrow keys, to inspect each player.");
  }

  function nearestRank(clientX) {
    if (!geometry) return null;
    const rect = canvas.getBoundingClientRect();
    const local = clientX - rect.left;
    const fraction = (local - geometry.pad.left) / geometry.innerWidth;
    return Math.max(geometry.zoomLow, Math.min(geometry.zoomHigh, Math.round(geometry.zoomLow + fraction * (geometry.zoomHigh - geometry.zoomLow))));
  }

  function tooltipHtml(rank) {
    const row = displayRows()[rank - 1];
    if (!row) return "";
    const rankLabel = `${lockLabel(lockOrder)} rank ${rank}`;
    const values = activeSourceKeys().map(key => `<span class="tip-source"><i style="background:${SOURCE_STYLES[key].color}"></i>${sourceLabel(key)}</span><b>${Number.isFinite(row.values[key]) ? Number(row.values[key]).toFixed(1) : "—"}</b>`).join("");
    const zero = row.espnProjectsZero ? window.TradeValueProductData?.ESPN_ZERO_BADGE : null;
    const zeroBadge = zero ? `<span class="tip-espn-zero" data-espn-zero title="${zero.title}"><span aria-hidden="true">${zero.symbol}</span> ${zero.label}</span>` : "";
    return `<strong>${rank}. ${row.name}</strong>${zeroBadge}<span class="tip-meta">${row.pos} · ${row.team} · DDF Value tier: ${row.ddfTier || "none"} · ${rankLabel}</span><span class="tip-grid">${values}</span>`;
  }

  function showTooltip(rank, clientX, clientY, above) {
    if (rank === null) return;
    crossRank = rank;
    tip.innerHTML = tooltipHtml(rank);
    tip.style.display = "block";
    tip.style.maxWidth = "calc(100vw - 24px)";
    const width = tip.offsetWidth, height = tip.offsetHeight;
    const viewport = window.visualViewport || {width:document.documentElement.clientWidth, height:document.documentElement.clientHeight, offsetLeft:0, offsetTop:0};
    const minLeft = viewport.offsetLeft + 8;
    const maxLeft = viewport.offsetLeft + viewport.width - width - 8;
    tip.style.left = `${Math.min(Math.max(clientX - width / 2, minLeft), Math.max(minLeft, maxLeft))}px`;
    let top = above ? clientY - height - 24 : clientY + 16;
    const minTop = viewport.offsetTop + 8;
    const maxTop = viewport.offsetTop + viewport.height - height - 8;
    if (top < minTop) top = clientY + 18;
    if (top > maxTop) top = Math.max(minTop, maxTop);
    tip.style.top = `${top}px`;
    draw();
  }

  function hideTooltip() {
    crossRank = null;
    tip.style.display = "none";
    draw();
  }

  canvas.addEventListener("pointermove", event => {
    if (event.pointerType === "touch") return;
    showTooltip(nearestRank(event.clientX), event.clientX, event.clientY, false);
  });
  canvas.addEventListener("pointerleave", event => {
    if (event.pointerType === "touch") return;
    hideTooltip();
  });
  canvas.addEventListener("touchstart", event => {
    event.preventDefault();
    const touch = event.touches[0];
    showTooltip(nearestRank(touch.clientX), touch.clientX, touch.clientY, true);
  }, {passive: false});
  canvas.addEventListener("touchmove", event => {
    event.preventDefault();
    const touch = event.touches[0];
    showTooltip(nearestRank(touch.clientX), touch.clientX, touch.clientY, true);
  }, {passive: false});
  canvas.addEventListener("touchend", hideTooltip, {passive: true});
  canvas.addEventListener("touchcancel", hideTooltip, {passive: true});
  canvas.addEventListener("pointerup", event => {
    if (event.pointerType === "touch") hideTooltip();
  }, {passive: true});
  canvas.addEventListener("keydown", event => {
    if (!["Home", "End", "ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    if (event.key === "Home") crossRank = zoomLow;
    else if (event.key === "End") crossRank = zoomHigh;
    else crossRank = Math.max(zoomLow, Math.min(zoomHigh, (crossRank ?? zoomLow) + (event.key === "ArrowRight" ? 1 : -1)));
    const rect = canvas.getBoundingClientRect();
    const px = rect.left + geometry.pad.left + (crossRank - zoomLow) / Math.max(1, zoomHigh - zoomLow) * geometry.innerWidth;
    showTooltip(crossRank, px, rect.top + geometry.pad.top + 12, false);
    canvas.setAttribute("aria-description", tip.textContent.trim());
  });
  window.addEventListener("resize", draw, {passive: true});

  function runRegressionGuards() {
    const rows = displayRows();
    // Coverage proof is derived from the registry itself: every registered source
    // must have a built map. A hardcoded key count here rotted the moment
    // cbsros/razzball joined SOURCE_KEYS (2026-10-01: length === 9 failed on
    // an 11-key registry and took all curves down on production).
    const sourceMapCoverage = SOURCE_KEYS.every(key => sourceMaps.has(key));
    const expectedToggleCount = SOURCE_GROUPS.reduce((sum, group) => sum + group.keys.length, 0);
    const sourceToggles = $("#sourceToggles")?.querySelectorAll("input[type=checkbox]").length === expectedToggleCount;
    const noAggregate = !Object.prototype.hasOwnProperty.call(window, "TradeValueCurveMedian");
    const stableDomain = rows.every((row, index) => index === 0 || row.player_key !== rows[index - 1].player_key);
    const validValues = SOURCE_KEYS.every(key => [...sourceMaps.get(key).values()].every(value => Number.isFinite(value) && value >= 0));
    // Only check active (non-paused) sources for the peak guard. Paused
    // adjusted curves carry stale fixture data and must not block the
    // live curves from rendering. Sources with no data (empty maps)
    // are skipped rather than failing the guard.
    const activeKeysForGuard = activeSourceKeys().filter(key => {
      const vals = sourceMaps.get(key);
      return vals && vals.size > 0;
    });
    const sourcePeaks = Object.fromEntries(activeKeysForGuard.map(key => [key, Math.max(...sourceMaps.get(key).values())]));
    const distinctSourcePeaks = activeKeysForGuard.length <= 1
      || sourceCurvesDistinct(activeKeysForGuard, sourceMaps);
    // Collapse guard. What this is actually for: catching a curve that has
    // lost its scale -- all-equal values, a bad reindex, a divide-by-total
    // error -- which puts the peak down near the per-player mean. The pie is
    // fixed at ~3197 across ~596 players, so that mean is ~5.4; a healthy
    // curve peaks between 60 and 95. CURVE_COLLAPSE_FLOOR sits well above
    // any collapsed state and well below any legitimate one.
    //
    // This was `> 70` until 2026-09-22, which is not a collapse floor but a
    // transcription of what the curves happened to peak at when it was
    // written. The ESPN leg legitimately peaks at ~67.8 after Week 2
    // re-anchoring, so the guard threw on every load, init() never reached
    // draw(), and the chart rendered blank behind a "Curves unavailable"
    // banner until an unrelated window resize redrew it.
    const valuesAboveCollapseFloor = peaksAboveCollapseFloor(sourcePeaks);
    const scale = yAxisScale(rows);
    const visiblePeak = Math.max(...rows.flatMap(row => activeSourceKeys().map(key => row.values[key])).filter(Number.isFinite));
    const dynamicAxisCoversData = scale.max >= visiblePeak;
    const sharedPlayerAxis = activeSourceKeys().every(key => displayRows().every((row, index) => row.player_key === displayRows()[index]?.player_key && (Number.isFinite(row.values[key]) || row.values[key] === null)));
    const markers = boundaryMarkers();
    const rosterTransitions = markers.length === 2
      && markers.every((marker, index) => marker.axis === "x" && Number.isFinite(marker.value) && marker.label === ["Starter → Bench", "Bench → Waiver"][index]);
    const fixedPie = fixedPieDiagnostics();
    const viewInvariants = viewInvariantsDiagnostics();
    // JEG-30: record the fixed-pie guard in Chart Health with its structured
    // per-source diagnostics. The detail view renders on failure; the happy
    // path stays clean. The thrown error below keeps a plain-words summary.
    ChartHealth.record(
      "fixed-pie-indexed",
      "Every source sums to the league pie",
      fixedPie.ok,
      fixedPie.ok
        ? `${fixedPie.checks.length} sources sum to the ${formatOne(fixedPie.pie)} pie; Indexed charts match the DDF Value total on their shared players`
        : `${fixedPie.checks.filter(c => !c.ok).length + Object.values(fixedPie.indexed).filter(r => !r.ok).length} source(s) off the pie — see diagnostics`,
      fixedPie
    );
    // JEG-392: in the VORP vs waivers / Adjusted views setViewMode() swaps
    // activeSources to that view's set and parks the Indexed selection in
    // savedActiveSourcesForView. Guard the Indexed selection the user will
    // return to.
    const indexedSelection = viewMode === "indexed"
      ? activeSources : (savedActiveSourcesForView || activeSources);
    const indexedHidden = viewMode === "indexed"
      ? userDeselectedSources : (savedUserDeselectedForView || userDeselectedSources);
    const defaultGroupedSources = defaultCurvesSatisfied(null, indexedSelection, indexedHidden, firstLoadExcluded);
    const pureVorpAvailable = PURE_VORP_KEYS.some(key => sourceMaps.get(key)?.size > 0);
    const adjustableBenchShare = DEFAULT_BENCH_SHARE === 0.15 && Number.isFinite(benchShare) && typeof setBenchShare === "function";
    // VP-7.3: DDF tiers exist whenever any source prices players.
    const ddfTiers = new Set(universe.map(row => row.ddfTier).filter(Boolean));
    const tieredDdfValues = !compositeAvailable() || ["starter", "waiver"].every(role => ddfTiers.has(role));
    const valuePipeline = pipeline ? ValueModel.valuePipelineDiagnostics(pipeline) : null;
    const diagnostics = {sourceMapCoverage, sourceToggles, noAggregate, stableDomain, validValues, distinctSourcePeaks,
      valuesAboveCollapseFloor, curveCollapseFloor:CURVE_COLLAPSE_FLOOR, dynamicAxisCoversData, sharedPlayerAxis, sourcePeaks,
      yAxisMax:scale.max, rosterTransitions, rosterMarkerAxis:"x", fixedPieIndexed:fixedPie.ok, fixedPie,
      indexedOrder:indexedOrderDiagnostics(), viewInvariants, defaultGroupedSources, pureVorpAvailable, adjustableBenchShare,
      tieredDdfValues, valueMode:"indexed", viewMode, lockOrder, rankSource:selectedRankSourceKey(),
      sourceCount:SOURCE_KEYS.length, activeCount:activeSourceKeys().length, curveCount:activeSourceKeys().length,
      firstLoadExcluded:[...firstLoadExcluded], savedSetup:onSavedSetup(),
      adjustmentWeightRows:adjustmentWeightRows().length, adjustmentAllocation:adjustmentAllocationRows(),
      // VP-11: the value pipeline at this setting (the math inspector reads it).
      valuePipeline,
      included:[...pipelineState.included], excluded:pipelineState.excluded.map(entry => ({...entry})),
      priorAvailable:pipelineState.priorAvailable, priorReason:pipelineState.priorReason,
      // Per chart: saved setup or derived at the reader's league (VP-9), and
      // whose values a superflex slot uses (the publisher's own, VP-0).
      publishedDerivation:Object.fromEntries([...AS_PUBLISHED_KEYS].map(key => [key, {
        mode: onSavedSetup() ? "saved" : "derived",
        superflex: ValueModel.superflexCount(rosterShape)
          ? (publishesSuperflex(key) ? "publisher superflex values" : "derived from 1-QB values") : null}]))};
    window.TradeValueCurveDiagnostics = Object.freeze(diagnostics);
    const failed = Object.entries(diagnostics).filter(([key, value]) => ["sourceMapCoverage", "sourceToggles", "noAggregate", "stableDomain", "validValues", "distinctSourcePeaks", "valuesAboveCollapseFloor", "dynamicAxisCoversData", "sharedPlayerAxis", "rosterTransitions", "fixedPieIndexed", "defaultGroupedSources", "adjustableBenchShare", "tieredDdfValues"].includes(key) && value !== true);
    // JEG-30: the per-source numbers live in the Chart Health detail view
    // (recorded above), not in the error string. pureVorpAvailable is
    // informational: with no projection this week the page still renders
    // (VP-1.6).
    if (failed.length) {
      const error = new Error(`Curve regression guard failed: ${failed.map(([key]) => key).join(", ")}. See Chart Health for per-source diagnostics.`);
      // Fail closed for THIS setting only: no curves painted (draw() and the
      // resize listener refuse) and the status says why. The next control
      // change re-runs the guards and, when they pass, repaints and resets
      // the status (GAP-BENCH-SHARE-LOW-PIE: a failure used to leave
      // guardsPassed true, so a resize repainted the rejected curves).
      guardsPassed = false;
      clearCanvasForFailedGuard();
      const status = $("#curve-status");
      if (status) {
        status.classList.remove("validated");
        status.innerHTML = `<strong>Curves unavailable:</strong> ${error.message}`;
      }
      throw error;
    }
    guardsPassed = true;
  }

  // JEG-210 / VP-11: view mode switching. Every tab reads the same pipeline
  // run; a chart series shows Indexed, VORP vs waivers or Adjusted values by
  // tab. Entering a non-indexed view activates that view's series; returning
  // to Indexed restores the user's prior source selection.
  function setViewMode(mode, publish = true) {
    if (!VIEW_MODE_DEFS[mode]) mode = "indexed";
    viewMode = mode;
    const tabs = document.querySelectorAll("#viewModeTabs [data-view-mode]");
    tabs.forEach(tab => {
      const selected = tab.dataset.viewMode === mode;
      tab.setAttribute("aria-selected", selected ? "true" : "false");
    });
    // The Indexed selection and the curves the user hid in it travel
    // together: parked while another view shows its own set, restored on
    // return. Clearing the hidden set while parking (before 2026-10-09) made
    // the defaultGroupedSources guard read every default the user had hidden
    // (v2 hides ESPN and the *_adjusted curves) as a vanished default and
    // throw on the first view switch.
    if (mode === "indexed") {
      if (savedActiveSourcesForView) {
        activeSources = savedActiveSourcesForView;
        savedActiveSourcesForView = null;
        userDeselectedSources = savedUserDeselectedForView || new Set();
        savedUserDeselectedForView = null;
      }
    } else {
      if (!savedActiveSourcesForView) {
        savedActiveSourcesForView = new Set(activeSources);
        savedUserDeselectedForView = new Set(userDeselectedSources);
      }
      // VP-11: the VORP vs waivers tab draws the charts' and the
      // projections' value above waivers; the Adjusted tab the charts' and
      // the projections' Adjusted values.
      const viewKeys = [...AS_PUBLISHED_KEYS, ...(mode === "vorp" ? PURE_VORP_KEYS : PROJECTION_SOURCE_KEYS)];
      activeSources = new Set(viewKeys);
      userDeselectedSources = new Set();
    }
    // Rebuild source maps with the new view's values, then redraw.
    rebuildDomain();
    makeSourceToggles();
    // JEG332-VORP-VIEWS: re-run the guards (and refresh the diagnostics) for
    // the view just entered, as every other control does. Skipped during
    // init, before the first guard run, when the toggles do not exist yet.
    if (engineReady || guardsPassed) runRegressionGuards();
    draw();
    syncCurveStatus();
    if (publish) window.dispatchEvent(new CustomEvent("trade-value-view-mode-change", { detail: { viewMode: mode } }));
  }

  function makeViewModeTabs() {
    const container = $("#viewModeTabs");
    if (!container) return;
    const tabs = container.querySelectorAll("[data-view-mode]");
    tabs.forEach(tab => {
      tab.addEventListener("click", () => setViewMode(tab.dataset.viewMode));
    });
    setViewMode(viewMode, false);
  }

  async function init() {
    try {
      data = await loadComparisonData();
      // JEG-479 / VP-1.2: the prior week is priced inside every rebuild, so
      // its history reads are fetched before the first one.
      await preloadCompositeHistory();
      // JEG-536 (ES-14): the expected-starts building blocks, before the first build.
      await loadLineupConfig();
      // JEG-432 R5: weekly charts older than the newest week on the board
      // start switched off (the reader can still turn them on).
      const freshness = window.TradeValueProductData?.getSourceFreshness?.() || null;
      firstLoadExcluded = new Set(freshness?.first_load_excluded || []);
      activeSources = new Set(defaultIndexedSourceKeys(null, firstLoadExcluded));
      userDeselectedSources = new Set();
      canonicalByKey = buildCanonicalMap();
      if (!canonicalByKey.size) throw new Error("Canonical player records are unavailable.");
      // VP-1.6: no source is required. A source that failed validation is
      // left out of the included set (eligibilityReason), never fatal.
      if (isLockKey(window.TradeValueLockOrder)) lockOrder = window.TradeValueLockOrder;
      rebuildDomain();
      makeLeagueControls();
      makeRosterControls();
      makePositionWeightControls();
      syncWeightsReadout();
      makeTabs();
      makeValueModeControl();
      makeValueBandControl();
      makeViewModeTabs();
      makeSourceToggles();
      makeLockControl();
      renderAdjustmentWeights();
      bindZoom();
      resetZoom();
      runRegressionGuards();
      draw();
      syncCurveStatus();
      publishShared();
      window.TradeValueCurveHarness = {
        fixedPieDiagnostics,
        // A substitute Adjusted map for one source, checked against the same
        // pie and budgets (guard-harness simulations).
        fixedPieDiagnosticsForMap: (sourceKey, values) => fixedPieDiagnostics({[seriesSource(sourceKey) || sourceKey]: values}),
        pipeline: () => pipeline,
        pipelinePrior: () => pipelinePrior,
        pipelineSetting,
        runPipelineWith: extra => runPipeline(pipelineNatives, pipelineState.included, extra || {}),
        sourceMaps: () => new Map(sourceMaps),
        state: () => ({scoring, teams, benchShare, sourceCount:SOURCE_KEYS.length, activeCount:activeSourceKeys().length})
      };
      engineReady = true;
      notifyRowsChanged();
    } catch (error) {
      $("#curve-status").innerHTML = `<strong>Curves unavailable:</strong> ${String(error.message)}`;
      console.error(error);
    }
  }

  init();
})();
