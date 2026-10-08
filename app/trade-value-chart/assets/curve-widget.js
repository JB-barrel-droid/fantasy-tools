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
    razzball_vorp: "Razzball raw VORP vs waivers"
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
    {label:"Bottoms Up Value Curves", keys:["espn", "cbsros", "razzball"]},
    {label:"Adjusted source projections", keys:["fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted", "cbs_adjusted"]},
    {label:"Raw VORP vs waivers", keys:["espn_vorp", "cbsros_vorp", "razzball_vorp"]},
    {label:"Direct published charts", keys:["usatoday", "fantasycalc", "fantasypros", "cbs"]}
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
  const EXTRA_SOURCE_KEYS = [];
  // Fixture-transition Option B (staged 2026-09-22): the *_adjusted curves
  // return to the default active set only when their sources carry live
  // adjustment cells for the selected league setup.
  const ADJUSTED_INDEXED_KEYS = ["fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted", "cbs_adjusted"];
  const DEFAULT_INDEXED_SOURCES = ["espn"];
  const POSITION_ORDER = ["QB", "RB", "WR", "TE"];
  const EXPECTED_ADJUSTMENT_CELL_KEYS = POSITION_ORDER.flatMap(pos => ["starter", "bench"].map(tier => `${pos}|${tier}`));
  // JEG-211 (Jeremy 2026-10-03): K/DST are honestly excluded from the chart.
  // The computed artifact (dist/modules/ddf-kdst-group-vorps.json) remains as
  // internal evidence, but no chart surface renders K/DST.
  // (Re-restored 2026-10-03: the JEG-292 commit 49cd201 reintroduced
  // SPECIALIST_POSITIONS/CHART_POSITIONS-with-specialists from a stale base.)
  const CHART_POSITIONS = [...POSITION_ORDER];
  // Matches the engine's reference shape (REF_SLOTS/REF_FLEX_COUNT in both
  // TwoTier below and build_ddf_two_tier_leg.py). The previous WR:2/FLEX:2
  // default disagreed with the shape every published number was priced under.
  const DEFAULT_ROSTER = Object.freeze({QB:1, RB:2, WR:3, TE:1, FLEX:1, BENCH:6, K:0, DST:0});
  const DEFAULT_FLEX_ELIGIBLE = Object.freeze(["RB", "WR", "TE"]);
  const DEFAULT_BENCH_SHARE = 0.15;
  // Minimum plausible peak for an indexed curve. See the collapse guard in
  // runRegressionGuards() for the derivation: the fixed pie spreads ~3197
  // across ~596 players (mean ~5.4) and healthy curves peak 60-95, so this
  // floor separates "scale is broken" from "this source ranks flatter than
  // the others". Raise it only with a curve that genuinely cannot go lower.
  const CURVE_COLLAPSE_FLOOR = 25;
  // Minimum shared players before a source may be anchored on the shared set.
  const MIN_SHARED_FOR_PIE = 40;
  // Set once runRegressionGuards() returns clean; draw() refuses to paint until then.
  let guardsPassed = false;
  // Stage 1 display freeze: the rendered fallback curves (fixed-pie indexed
  // maps, ESPN indexed map) always normalize at this share, so moving the
  // bench-share slider reruns the live two-tier calibration and its readout
  // WITHOUT changing any fallback curve. Only live-derived stage-2 paths
  // (baked adjustment cells present) normalize at the active slider share.
  const DISPLAY_BENCH_SHARE = DEFAULT_BENCH_SHARE;

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
        `Basis "shared" compares on players priced by both source and anchor; "fallback" uses the full-set total against the common pie; "anchor" is the ESPN reference itself; "pipeline" sources are indexed upstream and checked there.</p></details>`;
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

  // Two-tier marginal-price model: pure browser port of
  // lottery/bin/starter_model.py (reference implementation). No DOM, no
  // widget state -- safe to load in Node for tests. See the reference
  // module docstring for the economics; the port notes below call out the
  // JS-specific decisions.
  const TwoTier = (() => {
    const POSITIONS = ["QB", "RB", "WR", "TE"];
    const DEFAULT_BENCH_SHARE_TT = 0.15;
    const GLIDE_WIDTH_FRAC = 0.25;
    const FEAS_TOL = 1e-4;
    // 12-team reference bench depths (elboberto-aligned). Scaled by
    // teams / 12 with round-half-up for other league sizes.
    const REF_BENCH_SLOTS = 6;
    // Kept only as the regression anchor for the pinned-constant test.
    const LEGACY_BENCH_MIX_12 = {QB: 10, RB: 27, WR: 33, TE: 10};
    // JEG-392 (2026-10-05): 0.01 -> 0.0075. On the 2026-10-03 ESPN data the
    // 0.01 cutoff found no steep tail window below WR #25, giving 0 WR bench
    // spots at 12 teams. 0.0075 lands WR ~#100 on both pre- and post-refresh
    // data (QB 36-37, RB 67-70, TE 49-55); approved by Jeremy 2026-10-05.
    const FLOOR_SLOPE_FRAC = 0.0075;
    const FLOOR_WINDOW = 5;
    // Reference league shape for the calibration pool (fixed; the slider
    // bounds are per scoring x teams, not per custom roster shape).
    const REF_SLOTS = {QB: 1, RB: 2, WR: 3, TE: 1};
    const REF_FLEX_COUNT = 1;
    const REF_FLEX_ELIGIBLE = ["RB", "WR", "TE"];
    // Visible fail-closed flag: a position whose calibration is infeasible
    // at the active share is withheld, never zero-filled or guessed.
    const WITHHELD_FLAG = "withheld: calibration failed closed";

    // log(1 + e^z), numerically stable. d/dz softplus = sigmoid.
    const softplus = z => Math.log1p(Math.exp(-Math.abs(z))) + (z > 0 ? z : 0);

    // Bench-rate (A) and starter-rate (B) exposures of one player's surplus:
    // value(x) = p_bench * A + p_starter * B, marginal price gliding from
    // p_bench to p_starter across the starter line rs. Returns [0, 0] at or
    // below the waiver line.
    function sliceExposures(x, rw, rs, tau) {
      if (!(x > rw)) return [0, 0];
      const glide = tau * (softplus((x - rs) / tau) - softplus((rw - rs) / tau));
      return [(x - rw) - glide, glide];
    }

    // A bench share is a fraction of the pie: strictly between 0 and 1.
    function checkShare(share, pos = "?") {
      const s = Number(share);
      if (!Number.isFinite(s) || !(s > 0 && s < 1)) {
        throw new Error(`cannot calibrate ${pos}: bench share ${String(share)} is not between 0 and 1 (exclusive)`);
      }
      return s;
    }

    // Solve the per-position 2x2 system from the fixed-pie identity:
    //   a_bench * p_b + b_bench * p_s = bench_share * pie        (bench total)
    //   a_start * p_b + b_start * p_s = (1-bench_share) * pie    (starter total)
    // Fail closed: degenerate exposures, a non-(0,1) share, a non-positive
    // bench rate, a starter rate that does not exceed the bench rate, or a
    // solved split that misses the identity pre-rounding all throw. This
    // guard is the backstop behind the bounded slider.
    function solveTierPrices(aBench, bBench, aStart, bStart, pie, pos = "?", benchShare = DEFAULT_BENCH_SHARE_TT) {
      const share = checkShare(benchShare, pos);
      const starterShare = 1 - share;
      if (!(pie > 0)) throw new Error(`cannot calibrate ${pos}: non-positive pie ${pie}`);
      const det = aBench * bStart - aStart * bBench;
      if (det === 0) {
        throw new Error(`cannot calibrate ${pos}: degenerate slice exposures (a_bench=${aBench} b_bench=${bBench} a_start=${aStart} b_start=${bStart})`);
      }
      const pb = (share * pie * bStart - bBench * starterShare * pie) / det;
      const ps = (aBench * starterShare * pie - share * pie * aStart) / det;
      if (!(pb > 0)) throw new Error(`cannot calibrate ${pos} at bench share ${share}: bench rate ${pb} not positive`);
      if (!(ps > pb)) {
        throw new Error(`cannot calibrate ${pos} at bench share ${share}: starter rate ${ps} does not exceed bench rate ${pb} -- the economics break (bench slices would pay more than starter slices)`);
      }
      // Exactness: the solved rates must reproduce the split pre-rounding.
      const tol = 1e-9 * pie;
      if (Math.abs(pb * aBench + ps * bBench - share * pie) > tol ||
          Math.abs(pb * aStart + ps * bStart - starterShare * pie) > tol) {
        throw new Error(`cannot calibrate ${pos} at bench share ${share}: solved rates miss the split (bench=${pb * aBench + ps * bBench} starter=${pb * aStart + ps * bStart} pie=${pie})`);
      }
      return {pb, ps};
    }

    function feasibleAt(aBench, bBench, aStart, bStart, pie, share, pos = "?") {
      try {
        solveTierPrices(aBench, bBench, aStart, bStart, pie, pos, share);
        return true;
      } catch {
        return false;
      }
    }

    // The bench-share range where the economics hold, via bisection.
    // Returns [lo, hi] or null when the recommended default (0.15) is
    // itself infeasible. Bisection mirrors the reference exactly (same
    // tolerance, same start points) so pinned vectors match to 1e-9.
    function feasibleBenchShareInterval(aBench, bBench, aStart, bStart, pie, pos = "?") {
      if (!feasibleAt(aBench, bBench, aStart, bStart, pie, DEFAULT_BENCH_SHARE_TT, pos)) return null;
      let lo = 1e-6, hi = DEFAULT_BENCH_SHARE_TT;
      while (hi - lo > FEAS_TOL) {
        const mid = (lo + hi) / 2;
        if (feasibleAt(aBench, bBench, aStart, bStart, pie, mid, pos)) hi = mid;
        else lo = mid;
      }
      const loEdge = hi;
      lo = DEFAULT_BENCH_SHARE_TT; hi = 1 - 1e-6;
      while (hi - lo > FEAS_TOL) {
        const mid = (lo + hi) / 2;
        if (feasibleAt(aBench, bBench, aStart, bStart, pie, mid, pos)) lo = mid;
        else hi = mid;
      }
      return [loEdge, lo];
    }

    // Slider min/max for the active league config: the INTERSECTION across
    // positions, so no reachable setting can break any position's
    // economics. Returns [lo, hi], or null when the intersection is empty
    // (fail closed -- no valid setting exists for this config).
    function sliderBounds(intervals) {
      let lo = -Infinity, hi = Infinity, seen = 0;
      for (const pos of Object.keys(intervals)) {
        const iv = intervals[pos];
        if (!iv) return null;
        seen += 1;
        if (iv[0] > lo) lo = iv[0];
        if (iv[1] < hi) hi = iv[1];
      }
      if (!seen || lo > hi) return null;
      return [lo, hi];
    }

    // Round-half-even (matches Python round(), the reference display step).
    function roundHalfEven(x) {
      const n = Math.floor(x), d = x - n;
      if (d < 0.5) return n;
      if (d > 0.5) return n + 1;
      return n % 2 === 0 ? n : n + 1;
    }

    // One raw value -> display int. The shared normalize-then-round step:
    // the pool's single 70-max multiplier applies to the full-precision
    // raw value BEFORE rounding; rounding is display-only (min 1 when above
    // the waiver line, else 0).
    function displayValue(rawValue, scale, aboveWaiver) {
      if (!aboveWaiver) return 0;
      return Math.max(1, roundHalfEven(rawValue * scale));
    }

    // Normalize-then-round over a pool: scale = 70 / max(raw), applied to
    // full-precision raw values BEFORE rounding. rawByKey: Map id -> raw.
    // aboveWaiverByKey: id -> boolean. Returns {values: Map, scale}.
    function normalizeThenRound(rawByKey, aboveWaiverByKey) {
      let mx = 0;
      rawByKey.forEach(v => { if (v > mx) mx = v; });
      const scale = mx > 0 ? 70 / mx : 1;
      const values = new Map();
      rawByKey.forEach((v, k) => values.set(k, displayValue(v, scale, aboveWaiverByKey(k))));
      return {values, scale};
    }

    // Rank where a position's projections stop separating (1-based). Scanned
    // from the BOTTOM up -- scanning top-down finds the UPPER plateau (QB is
    // flat from ~#6-20 too) and returns nonsense.
    function tailFloor(xs, frac = FLOOR_SLOPE_FRAC, win = FLOOR_WINDOW) {
      if (xs.length <= win) return xs.length;
      const thr = frac * (xs[0] - xs[xs.length - 1]);
      if (!(thr > 0)) return xs.length;
      for (let s = xs.length - win - 1; s >= 0; s--) {
        if ((xs[s] - xs[s + win]) / win >= thr) return s + win + 1;
      }
      return 1;
    }

    // Bench spots per position, derived. Exact port of bench_mix_for() in
    // pipelines/build_ddf_two_tier_leg.py -- keep the two in lockstep.
    //
    // A bench spot covers a starting slot when its starter is out, so cover
    // demand at a position is the expected number of simultaneous absences
    // among its starters: sum_n P(>= n out) == lambda == S_p * q. Demand is
    // therefore EXACTLY proportional to S_p, the starting-slot load, and q
    // cancels in the normalisation -- no free parameter, no injury rate to
    // estimate. The irrelevance floor caps each position and largest-remainder
    // rounding makes the parts sum EXACTLY to teams * benchSlots, which the
    // pinned constant never did (80 across 12 teams = 6.67 spots per team).
    function benchMixFor(teams, benchSlots, slots, flexCount, flexEligible, pools) {
      const capacity = teams * benchSlots;
      const out = {};
      for (const pos of POSITIONS) out[pos] = 0;
      if (capacity <= 0) return out;

      const ranked = {};
      for (const pos of POSITIONS) ranked[pos] = (pools[pos] || []).slice().sort((a, b) => b - a);
      const taken = {}, flexHits = {};
      for (const pos of POSITIONS) { taken[pos] = teams * (slots[pos] || 0); flexHits[pos] = 0; }
      const flexPool = [];
      for (const pos of POSITIONS) {
        if (!flexEligible.includes(pos)) continue;
        for (const x of ranked[pos].slice(taken[pos])) flexPool.push([x, pos]);
      }
      flexPool.sort((a, b) => b[0] - a[0]);
      for (const [, pos] of flexPool.slice(0, teams * flexCount)) flexHits[pos] += 1;

      const starters = {}, load = {}, cap = {};
      for (const pos of POSITIONS) {
        starters[pos] = taken[pos] + flexHits[pos];
        load[pos] = (slots[pos] || 0) + flexHits[pos] / teams;
        cap[pos] = Math.max(0, tailFloor(ranked[pos]) - starters[pos]);
      }

      const alloc = {};
      for (const pos of POSITIONS) alloc[pos] = 0;
      let remaining = capacity;
      for (let i = 0; i < 8; i++) {
        const open = POSITIONS.filter(p => alloc[p] < cap[p] - 1e-9 && load[p] > 0);
        const weight = open.reduce((sum, p) => sum + load[p], 0);
        if (!open.length || weight <= 0 || remaining < 1e-9) break;
        for (const p of open) alloc[p] = Math.min(cap[p], alloc[p] + remaining * load[p] / weight);
        remaining = capacity - POSITIONS.reduce((sum, p) => sum + alloc[p], 0);
      }

      for (const pos of POSITIONS) out[pos] = Math.floor(alloc[pos]);
      const order = POSITIONS.slice().sort((a, b) =>
        (alloc[b] - Math.floor(alloc[b])) - (alloc[a] - Math.floor(alloc[a])));
      let guard = 0;
      while (POSITIONS.reduce((sum, p) => sum + out[p], 0) < capacity && guard < 10000) {
        const p = order[guard % order.length];
        if (out[p] < cap[p]) out[p] += 1;
        guard += 1;
      }
      return out;
    }

    // Round slider bounds INWARD (lo up, hi down) so the reachable
    // endpoints remain strictly feasible.
    function inwardBounds(lo, hi, step = 0.001) {
      return [Math.ceil(lo / step - 1e-12) * step, Math.floor(hi / step + 1e-12) * step];
    }

    // Build the frozen pool structure for one league config.
    // lists: {pos: [{id, x}]} per-game projections (unsorted ok).
    // cfg: {teams, slots, flexCount, flexEligible, benchMix}.
    // Returns {tiers, starters: Set, bench: Set, rostered: Set}.
    // tiers[pos] = {rw, rs, tau, aBench, bBench, aStart, bStart, surplus}
    // or null when the position has no players.
    function buildPositionTiers(lists, cfg) {
      const {teams, slots, flexCount, flexEligible, benchMix} = cfg;
      const byPos = {};
      for (const pos of POSITIONS) {
        byPos[pos] = (lists[pos] || [])
          .map(d => ({id: d.id, x: d.x}))
          .filter(d => Number.isFinite(d.x))
          .sort((a, b) => b.x - a.x || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
      }
      const dedicated = new Set(), starters = new Set();
      for (const pos of POSITIONS) {
        byPos[pos].slice(0, teams * (slots[pos] || 0)).forEach(d => { dedicated.add(d.id); starters.add(d.id); });
      }
      const flexPool = [];
      for (const pos of POSITIONS) {
        if (!flexEligible.includes(pos)) continue;
        byPos[pos].forEach(d => { if (!dedicated.has(d.id)) flexPool.push(d); });
      }
      flexPool.sort((a, b) => b.x - a.x || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
      flexPool.slice(0, teams * (flexCount || 0)).forEach(d => starters.add(d.id));
      const rostered = new Set(starters);
      const bench = new Set();
      for (const pos of POSITIONS) {
        byPos[pos].filter(d => !rostered.has(d.id)).slice(0, benchMix[pos] || 0)
          .forEach(d => { rostered.add(d.id); bench.add(d.id); });
      }
      const tiers = {};
      for (const pos of POSITIONS) {
        const lst = byPos[pos];
        if (!lst.length) { tiers[pos] = null; continue; }
        const nxt = lst.find(d => !rostered.has(d.id));
        const rw = nxt ? nxt.x : 0;
        const sProjs = lst.filter(d => starters.has(d.id)).map(d => d.x);
        const bProjs = lst.filter(d => !starters.has(d.id)).map(d => d.x);
        let rs;
        if (!sProjs.length) rs = lst[0].x + 1;
        else if (!bProjs.length) rs = lst[lst.length - 1].x - 1;
        else rs = (Math.min(...sProjs) + Math.max(...bProjs)) / 2;
        if (!(rs > rw)) throw new Error(`buildPositionTiers: starter line ${rs} must exceed waiver line ${rw} at ${pos}`);
        const tau = GLIDE_WIDTH_FRAC * (rs - rw);
        let aBench = 0, bBench = 0, aStart = 0, bStart = 0, surplus = 0;
        for (const d of lst) {
          if (!(d.x > rw)) continue;
          surplus += d.x - rw;
          const [a, b] = sliceExposures(d.x, rw, rs, tau);
          if (starters.has(d.id)) { aStart += a; bStart += b; }
          else { aBench += a; bBench += b; }
        }
        tiers[pos] = {rw, rs, tau, aBench, bBench, aStart, bStart, surplus};
      }
      return {tiers, starters, bench, rostered};
    }

    // Calibrate one position at a bench share. Fail closed per position:
    // infeasible -> {invalid: true, invalidReason} with pb/ps null (values
    // withheld downstream), never a guessed rate. Empty tier (no surplus)
    // -> zero rates, every value zero.
    function calibratePosition(tier, pie, benchShare = DEFAULT_BENCH_SHARE_TT) {
      if (!tier) return null;
      if (!(tier.surplus > 0)) {
        return {...tier, pb: 0, ps: 0, invalid: false, invalidReason: null, benchRaw: 0, starterRaw: 0};
      }
      if (!(pie > 0)) {
        return {...tier, pb: null, ps: null, invalid: true, invalidReason: `cannot calibrate: non-positive pie ${pie}`};
      }
      try {
        const {pb, ps} = solveTierPrices(tier.aBench, tier.bBench, tier.aStart, tier.bStart, pie, "?", benchShare);
        return {...tier, pb, ps, invalid: false, invalidReason: null,
          benchRaw: pb * tier.aBench + ps * tier.bBench,
          starterRaw: pb * tier.aStart + ps * tier.bStart};
      } catch (e) {
        return {...tier, pb: null, ps: null, invalid: true, invalidReason: String((e && e.message) || e)};
      }
    }

    // Calibrate one position at the requested share, falling back to the
    // nearest feasible share when the request cannot price it. Mirrors the
    // leg builders (pipelines/build_ddf_two_tier_leg.py::build_leg and
    // build_cbsros_ddf_leg.py) step for step:
    //  - bench rate not positive (request BELOW the feasible window, JEG-74):
    //    step up 0.01 at a time to the first feasible share, then 15
    //    bisection iterations toward the window's lower edge.
    //  - economics break (request ABOVE the window): 20 bisection
    //    iterations on [0.01, requested] for the highest feasible share.
    // Records bench_share_used on the returned calibration. Degenerate
    // exposures or a non-positive pie stay invalid (fail closed), never
    // guessed. If no share is feasible, the original failure is returned.
    // Without the upward step the browser withheld every CBS ROS QB at 8
    // teams (2026-10-02 snapshot) while the baked leg priced them
    // (GAP-CBSROS-8T-NO-QB).
    function calibratePositionFeasible(tier, pie, requestedShare, pos = "?") {
      const first = calibratePosition(tier, pie, requestedShare);
      if (!first || !first.invalid) {
        if (first) first.bench_share_used = Number(requestedShare);
        return first;
      }
      const reason = String(first.invalidReason || "");
      if (/bench rate .* not positive/i.test(reason)) {
        let lo = Number(requestedShare), hi = null, s = lo;
        while (s < 0.99) {
          s = Math.min(0.99, s + 0.01);
          const attempt = calibratePosition(tier, pie, s);
          if (attempt && !attempt.invalid) { hi = s; break; }
          lo = s;
        }
        if (hi === null) return first;
        for (let i = 0; i < 15; i++) {
          const mid = (lo + hi) / 2;
          const attempt = calibratePosition(tier, pie, mid);
          if (attempt && !attempt.invalid) hi = mid;
          else lo = mid;
        }
        const best = calibratePosition(tier, pie, hi);
        if (!best || best.invalid) return first;
        best.bench_share_used = hi;
        return best;
      }
      if (!/does not exceed|economics break/i.test(reason)) return first;
      let lo = 0.01, hi = Number(requestedShare);
      for (let i = 0; i < 20; i++) {
        const mid = (lo + hi) / 2;
        const attempt = calibratePosition(tier, pie, mid);
        if (attempt && !attempt.invalid) lo = mid;
        else hi = mid;
      }
      const best = calibratePosition(tier, pie, lo);
      if (!best || best.invalid) return first;
      best.bench_share_used = lo;
      return best;
    }

    // Two-tier value of a hypothetical per-game projection x against a
    // frozen calibrated position. Invalid positions price at zero -- never
    // a guessed value.
    function priceForProjection(x, cal) {
      if (!cal || cal.invalid || cal.pb === null || cal.pb === undefined) return 0;
      if (!(x > cal.rw)) return 0;
      const [a, b] = sliceExposures(x, cal.rw, cal.rs, cal.tau);
      return cal.pb * a + cal.ps * b;
    }

    // Global bench-share object: one slider writes the same share to every
    // skill position (each position falls back to `default`). K/DST are
    // excluded (never keys here; the two-tier model does not price them).
    // Per-position sliders are the documented future extension: they would
    // set individual position keys on this object.
    function skillBenchShares(share) {
      const s = checkShare(share);
      return {default: s, QB: s, RB: s, WR: s, TE: s};
    }
    function skillBenchShare(shares, pos) {
      if (!shares || typeof shares !== "object") return DEFAULT_BENCH_SHARE_TT;
      const v = shares[pos];
      if (typeof v === "number" && Number.isFinite(v)) return checkShare(v);
      const d = shares.default;
      if (typeof d === "number" && Number.isFinite(d)) return checkShare(d);
      return DEFAULT_BENCH_SHARE_TT;
    }

    // Legacy fixed bench mix scaled by team count, matching the pipeline
    // legs (pipelines/build_ddf_two_tier_leg.py::bench_mix_for_teams).
    // The pipeline bakes legs with this mix; the live paths must build the
    // same pool or the 0.15 reference share will not reproduce the leg.
    function legacyBenchMixFor(teams) {
      const out = {};
      for (const pos of POSITIONS) {
        out[pos] = Math.floor(LEGACY_BENCH_MIX_12[pos] * teams / 12 + 0.5);
      }
      return out;
    }

    return {
      POSITIONS, DEFAULT_BENCH_SHARE: DEFAULT_BENCH_SHARE_TT, GLIDE_WIDTH_FRAC,
      REF_SLOTS, REF_FLEX_COUNT, REF_FLEX_ELIGIBLE, WITHHELD_FLAG,
      softplus, sliceExposures, checkShare, solveTierPrices, feasibleAt,
      feasibleBenchShareInterval, sliderBounds, roundHalfEven,
      displayValue, normalizeThenRound, benchMixFor, tailFloor,
      REF_BENCH_SLOTS, LEGACY_BENCH_MIX_12, legacyBenchMixFor, inwardBounds,
      buildPositionTiers, calibratePosition, calibratePositionFeasible, priceForProjection,
      skillBenchShares, skillBenchShare
    };
  })();

  // Test surface: pure helpers loadable in Node (no DOM) before the
  // widget's root early-return below.
  globalThis.TradeValueTwoTier = TwoTier;

  // Fixture-transition Option B (staged 2026-09-22): an *_adjusted curve is
  // PAUSED while its source has no validated-live adjustment cells in
  // adjustment-inputs.json. espn ("ESPN adjusted") is the live bottom-up leg
  // and is never paused. Pure in (key, inputs) so it is unit-testable; the
  // widget calls it with the loaded adjustmentInputs. Cells may exist while a
  // source stays pending model-quality review or while a source is partial;
  // only a status:"live" source with every position/tier cell activates.
  function adjustmentCellCompleteness(entry) {
    if (!(entry && entry.status === "live" && Array.isArray(entry.cells))) {
      return {complete:false, present:[], missing:[...EXPECTED_ADJUSTMENT_CELL_KEYS]};
    }
    const present = new Set();
    entry.cells.forEach(cell => {
      const pos = String(cell.position || "").toUpperCase();
      const tier = String(cell.tier || "").toLowerCase();
      const alpha = Number(cell.alpha);
      const beta = Number(cell.beta);
      if (POSITION_ORDER.includes(pos) && ["starter", "bench"].includes(tier) &&
          Number.isFinite(alpha) && Number.isFinite(beta)) {
        present.add(`${pos}|${tier}`);
      }
    });
    const missing = EXPECTED_ADJUSTMENT_CELL_KEYS.filter(key => !present.has(key));
    return {complete: missing.length === 0, present: [...present], missing};
  }
  function adjustedCurvePaused(key, inputs) {
    if (key === "espn" || !key.endsWith("_adjusted")) return false;
    const rawKey = key === "cbs_adjusted" ? "cbs" : key.replace(/_adjusted$/, "");
    const entry = inputs && inputs.sources ? inputs.sources[rawKey] : null;
    return !adjustmentCellCompleteness(entry).complete;
  }
  globalThis.TradeValueCurvePause = {adjustedCurvePaused, defaultIndexedSourceKeys, adjustmentCellCompleteness};

  // Default active set: ESPN adjusted plus every *_adjusted curve with live
  // stage-2 cells. Pure in (inputs) so it is unit-testable; init() applies it
  // on fresh load, which is what makes the "shown by default" banner copy
  // true once cells land.
  // JEG-432 R5: `excluded` is the first-load exclusion set from
  // TradeValueProductData.getSourceFreshness() -- weekly charts older than the
  // newest week on the board. They stay selectable; they just start off.
  function defaultIndexedSourceKeys(inputs, excluded) {
    const skip = excluded instanceof Set ? excluded : new Set(excluded || []);
    return [...DEFAULT_INDEXED_SOURCES,
            ...ADJUSTED_INDEXED_KEYS.filter(key => !adjustedCurvePaused(key, inputs))]
      .filter(key => !skip.has(key));
  }
  globalThis.TradeValueCurvePause.defaultIndexedSourceKeys = defaultIndexedSourceKeys;
  // DEFECT 1 (2026-10-01): pure in (inputs, activeSet, userHiddenSet) so it
  // is unit-testable. True when every default curve is either active or was
  // deliberately hidden by the user. A default that vanished WITHOUT the
  // user asking still fails, preserving the guard's regression-catching
  // power; a user-hidden default no longer throws inside
  // runRegressionGuards() on the next scoring/teams change (which used to
  // die before draw()/publishShared() and freeze the comparison table).
  function defaultCurvesSatisfied(inputs, activeSet, userHiddenSet, excluded) {
    return defaultIndexedSourceKeys(inputs, excluded).every(
      key => activeSet.has(key) || (userHiddenSet && userHiddenSet.has(key)));
  }
  globalThis.TradeValueCurvePause.defaultCurvesSatisfied = defaultCurvesSatisfied;

  // Collapse guard, pure in (peaks) so it is unit-testable without a DOM.
  // `peaks` maps an active source key to that curve's maximum indexed value.
  // True means every active curve still has a plausible scale. An empty set
  // is vacuously true: a source with no data at all is a separate failure
  // (validValues / sourceMapCoverage), not a collapse.
  function peaksAboveCollapseFloor(peaks, floor = CURVE_COLLAPSE_FLOOR) {
    const values = Object.values(peaks || {});
    if (!values.length) return true;
    return values.every(value => Number.isFinite(value) && value > floor);
  }
  // Scale-aware anchor guard check (2026-10-01): the DDF-native ESPN anchor
  // carries the 70/max display scale (ddfTwoTierValues multiplies raw values
  // by 70/max(raw)), while the pie targets are raw economics. Comparing
  // display-scaled values against the raw pie (2322 vs 795 on 2026-10-01)
  // fails the guard on every config -- the guard was scale-blind. Unscale
  // before comparing so the check verifies the economics.
  function anchorScaleCorrectedCheck(displayTotal, pieSum, displayScale, tolerance) {
    const scale = Number(displayScale) > 0 ? Number(displayScale) : 1;
    const rawTotal = Number(displayTotal) / scale;
    const target = Number(pieSum);
    const delta = rawTotal - target;
    return {total: rawTotal, target, delta, ok: Math.abs(delta) <= tolerance};
  }
  globalThis.TradeValueCurveGuards = {peaksAboveCollapseFloor, CURVE_COLLAPSE_FLOOR, anchorScaleCorrectedCheck};
  // Debug handle (2026-10-01): expose the fixedPieDiagnostics runtime values
  // so the guard failure can be diagnosed from the console without guessing.
  // Returns the raw check inputs for the ESPN anchor: display total, pie sum,
  // scale used, and the computed check result.
  globalThis.TradeValueCurveDebug = {
    fixedPieEspn: () => {
      try {
        const anchor = sourceMaps.get("espn");
        if (!anchor) return {error: "no espn anchor in sourceMaps"};
        const pieSum = POSITION_ORDER.reduce((sum, pos) => {
          const t = Number(espnTargetTotal(pos, NaN));
          return sum + (Number.isFinite(t) && t > 0 ? t : 0);
        }, 0) || commonFixedPieTotal(0);
        const total = [...anchor.entries()]
          .filter(([playerKey]) => POSITION_ORDER.includes(canonicalByKey.get(playerKey)?.pos))
          .reduce((sum, [, value]) => sum + (Number.isFinite(value) ? value : 0), 0);
        const displayScale = ddfTwoTierValues()?.scale || 1;
        const ddfNull = ddfTwoTierValues() === null;
        const check = anchorScaleCorrectedCheck(total, pieSum, displayScale, 2);
        // Also report max anchor value to verify the 70/max assumption.
        let maxAnchor = 0;
        anchor.forEach(v => { if (v > maxAnchor) maxAnchor = v; });
        return {displayTotal: total, pieSum, displayScale, ddfNull, maxAnchor, check};
      } catch (e) {
        return {error: String(e?.message || e)};
      }
    }
  };

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

  // Versioned adjustment inputs (trade-value-adjustment-inputs-v1). Stage 1 ships
  // the stage1-empty asset: every source is pending-stage2 with no cells, so
  // every *_adjusted curve falls back exactly to today's behavior. A missing or
  // unparsable asset also falls back (fail-open) rather than breaking the chart.
  function loadAdjustmentInputs() {
    // product-data.js owns the fixture read; the widget only sees the projected
    // payload via getAdjustmentInputs().
    if (window.TradeValueProductData && window.TradeValueProductData.initProductData) {
      return window.TradeValueProductData.initProductData().then(() => {
        const inputs = window.TradeValueProductData.getAdjustmentInputs();
        window.TradeValueAdjustmentInputs = inputs;
        return inputs;
      });
    }
    return Promise.resolve(null);
  }

  let data = null;
  let adjustmentInputs = null;
  let canonicalByKey = new Map();
  let sourceMaps = new Map();
  let nativeSourceMaps = new Map();
  // As-published sources sort the lock order by their native published values,
  // not the reindexed chart values. Native values are the source's own
  // cross-position ranking (e.g., FantasyCalc's JSN at #3 overall). The
  // plotted values preserve this order via proportional global scaling;
  // per-position roster-shape factors are skipped for these sources to
  // avoid destroying the native cross-position order.
  const AS_PUBLISHED_KEYS = new Set(["usatoday", "fantasycalc", "fantasypros", "cbs"]);
  let universe = [];
  let orderedRows = [];
  let position = "ALL";
  let scoring = "ppr";
  let teams = 12;
  let rosterShape = {...DEFAULT_ROSTER};
  let benchShare = DEFAULT_BENCH_SHARE;
  // Position weights: null = baked defaults from the fixture pies; otherwise
  // {QB, RB, WR, TE} fractions summing to exactly 1. Changed via the
  // standalone Weights section; drives a true live recalibration.
  let positionWeights = null;
  // Two-tier calibration caches. Bounds/intervals depend only on the league
  // config (scoring x teams; reference pool shape); calibrations and live
  // cells additionally depend on the active bench share.
  let twoTierConfigCache = new Map();
  let twoTierCalCache = new Map();
  let liveCellsCache = null;
  let vorpRowsCache = new Map();
  let espnFixtureLegCache = null;
  // The split the charts were actually matched to, for the footnote. Measured
  // off the anchor each rebuild; DISPLAY_BENCH_SHARE is only the fall-back.
  let lastDisplayShare = DEFAULT_BENCH_SHARE;
  let espnRoleByKey = new Map();
  let yAxisAuto = true;
  let yLow = 0;
  let yHigh = 100;
  let lockOrder = "espn";
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
  const rawKeyForAdjusted = key => key === "cbs_adjusted" ? "cbs" : key.replace(/_adjusted$/, "");
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
  const flexEligiblePositions = (shape = rosterShape) => shape.SUPERFLEX ? ["QB", ...DEFAULT_FLEX_ELIGIBLE] : [...DEFAULT_FLEX_ELIGIBLE];
  const isPosition = player => position === "ALL" || (position === "FLEX" ? flexEligiblePositions().includes(player.pos) : player.pos === position);
  const visibleSourceKeys = () => [...SOURCE_KEYS, ...EXTRA_SOURCE_KEYS, ...PURE_VORP_KEYS];
  const sourceAvailable = key => sourceMaps.get(key)?.size > 0 && sourceComboExists(key);
  const activeSourceKeys = () => visibleSourceKeys().filter(key => activeSources.has(key) && sourceAvailable(key) && !isAdjustedCurvePaused(key));
  const isLockKey = key => ["disagreement", ...SOURCE_KEYS, ...EXTRA_SOURCE_KEYS, ...PURE_VORP_KEYS].includes(key);
  const defaultValueLock = () => "espn";
  const sourceValidationStatus = key => {
    // JEG-363: source validation lives on api.product_snapshot.source_validation.
    const sv = (typeof window !== "undefined" && window.TradeValueProductData)
      ? window.TradeValueProductData.getSnapshot().source_validation
      : null;
    return key === "cbs_adjusted" ? sv?.cbs : sv?.[key];
  };
  const sourceComboExists = key => {
    // Pure VORP curves are browser-computed from each source's per-game
    // projections on the player records, not from fixture combos.
    if (PURE_VORP_KEYS.includes(key)) {
      const field = VORP_SOURCE_DEFS[key].ppgField;
      return [...canonicalByKey.values()].some(p => Number.isFinite(Number(p[field]?.[scoringField()])));
    }
    // league-settings-001: published charts (and their adjusted series) exist
    // at every league setting when their saved 12-team setup exists; other
    // settings are derived from it in the browser (derivedPublishedSourceMap).
    const publishedBase = key === "cbs_adjusted" ? "cbs" : key.replace(/_adjusted$/, "");
    if (AS_PUBLISHED_KEYS.has(publishedBase)) {
      return Boolean(data?.sources?.[key === "cbs_adjusted" ? "cbs" : key]?.combos?.[
        ValueModel.sourceComboKey(publishedBase, scoring, ValueModel.SAVED_SETUP_TEAMS, 1)]);
    }
    // DDF-native sources (cbsros, razzball): check fixture has native PPG data.
    // Razzball uses rz_ppg on player objects; CBS ROS uses cbsros_ppg,
    // baked by pipelines/bake_players.py from the CBS ROS snapshot (JEG-33).
    if (key === "razzball") {
      return [...canonicalByKey.values()].some(p => Number.isFinite(Number(p.rz_ppg?.[scoringField()])));
    }
    if (key === "cbsros") {
      return [...canonicalByKey.values()].some(p => Number.isFinite(Number(p.cbsros_ppg?.[scoringField()])));
    }
    return Boolean(data?.sources?.[key]?.combos?.[comboKey(key)]);
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
        espnProjectsZero: player.espn_projects_zero === true
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

  // Roster order comes from ESPN projected points. It used to come from
  // preseason_ecr_rank, which is a POSITIONAL rank -- four players share
  // rank 1 -- so the QB1 sorted ahead of the RB1 and Josh Allen landed at
  // x=1 on a 1QB board.
  function allocationCountsFor(pool, shape = rosterShape) {
    const field = scoringField();
    return ValueModel.allocationCounts({
      pool,
      teams,
      shape,
      rankOf: player => Number(player.espn_ppg?.[field])
    });
  }

  function espnTargetTotal(pos, fallback) {
    // The calibration pie is the tier surplus from the live pool (matching
    // the pipeline legs), NOT the fixture's index_total.target_total. The
    // guard and the ESPN curve scales must use the same pie the calibration
    // uses, or the fixedPieIndexed guard fails and blanks the chart.
    try {
      const pies = twoTierConfig().pies || {};
      const target = Number(pies[pos]);
      if (Number.isFinite(target) && target > 0) return target;
    } catch (e) {
      // Config not ready; fall through to the api.player_values row.
    }
    // JEG-363: read the ESPN combo's index_total via product-data.js.
    const espnRow = (typeof window !== "undefined" && window.TradeValueProductData)
      ? window.TradeValueProductData.getPlayerValues({source: "espn", scoring, teams, qbVariant: "qb1", view: "combo_reindexed"})
      : null;
    const target = Number(espnRow?.index_total?.[pos]?.target_total);
    return Number.isFinite(target) && target > 0 ? target : fallback;
  }

  function sourceTargetTotal(key) {
    const sourceKey = key === "cbs_adjusted" ? "cbs" : key;
    // JEG-363: read the per-source combo's index_total via product-data.js.
    const row = (typeof window !== "undefined" && window.TradeValueProductData)
      ? window.TradeValueProductData.getPlayerValues({source: sourceKey, scoring, teams, qbVariant: "qb1", view: "combo_reindexed"})
      : null;
    const totals = Object.values(row?.index_total || {}).map(item => Number(item?.target_total)).filter(Number.isFinite);
    return totals.reduce((sum, value) => sum + value, 0);
  }

  function commonFixedPieTotal(fallback) {
    const totals = [...SOURCE_KEYS, ...EXTRA_SOURCE_KEYS]
      .map(sourceTargetTotal)
      .filter(value => Number.isFinite(value) && value > 0)
      .sort((a, b) => a - b);
    if (!totals.length) return fallback;
    const middle = Math.floor(totals.length / 2);
    return totals.length % 2 ? totals[middle] : (totals[middle - 1] + totals[middle]) / 2;
  }

  function espnTargetPool(fallback) {
    return commonFixedPieTotal(fallback);
  }

  // league-settings-001 (JEG-332): the backend saves one setup per scoring
  // (12 teams, standard roster). Published charts read their saved values at
  // that setup and are DERIVED in the browser from the saved 12-team inputs
  // everywhere else. Memoised: the derivation is a pure function of
  // (source, scoring, teams, roster) and the loaded data.
  const onSavedSetup = () => ValueModel.isSavedSetup(teams, rosterShape);
  const rosterSignature = () => Object.keys(DEFAULT_ROSTER).map(key => `${key}${rosterShape[key]}`).join("");
  let derivedPublishedCache = new Map();
  let lastPublishedDerivation = {};
  // JEG332-VORP-VIEWS: per-rebuild cache of the derived VORP-vs-waivers /
  // Adjusted views (they depend on the live anchor, so rebuildDomain clears it).
  let derivedViewBatchCache = null;
  let lastPublishedView = {};

  function savedPublishedRow(key, view) {
    return window.TradeValueProductData.getPlayerValues({
      source: key, scoring, teams: ValueModel.SAVED_SETUP_TEAMS, qbVariant: "qb1", view,
    });
  }

  // A published chart's saved 12-team native values at this scoring.
  function savedPublishedNative(key) {
    const native = new Map();
    savedPublishedRow(key, "native")?.values?.forEach((rawValue, playerKey) => {
      const value = Number(rawValue);
      if (canonicalByKey.has(playerKey) && Number.isFinite(value)) native.set(playerKey, value);
    });
    return native;
  }

  // V2-WAIVER-COVERAGE (Jeremy 2026-10-07): the OTHER published charts' saved
  // natives. A chart that lists fewer players at a position than the league
  // rosters has its waiver line extrapolated from them; the imputed players
  // are never shown as that chart's values.
  function publishedPeers(key) {
    const peers = {};
    AS_PUBLISHED_KEYS.forEach(other => {
      if (other === key) return;
      const native = savedPublishedNative(other);
      if (native.size) peers[other] = native;
    });
    return peers;
  }

  // How each position's waiver line is set for a published chart at the
  // active setting ({positions, imputed, short}); memoised like the values.
  let publishedWaiverCache = new Map();
  function publishedWaiver(key) {
    const raw = AS_PUBLISHED_KEYS.has(key) ? key : (key.endsWith("_adjusted") ? rawKeyForAdjusted(key) : null);
    if (!raw || !AS_PUBLISHED_KEYS.has(raw)) return null;
    const cacheKey = `${raw}|${scoring}|${teams}|${rosterSignature()}`;
    if (publishedWaiverCache.has(cacheKey)) return publishedWaiverCache.get(cacheKey);
    const native = savedPublishedNative(raw);
    const info = native.size ? ValueModel.publishedWaiverInfo({
      native, peers: publishedPeers(raw), posOf: playerKey => canonicalByKey.get(playerKey)?.pos,
      teams, shape: rosterShape
    }) : null;
    publishedWaiverCache.set(cacheKey, info);
    return info;
  }

  // The denotation copy: which positions' waiver line is extrapolated from
  // the other charts, or still sits at the end of the chart's own list.
  function waiverNote(key) {
    const info = publishedWaiver(key);
    if (!info) return null;
    const parts = [];
    if (info.imputed.length) parts.push(`waiver line extrapolated from other charts (${info.imputed.join(", ")})`);
    if (info.short.length) parts.push(`waiver line at the end of its list, no other chart covers enough players (${info.short.join(", ")})`);
    return parts.length ? parts.join("; ") : null;
  }

  function derivedPublishedSourceMap(key) {
    const cacheKey = `${key}|${scoring}|${teams}|${rosterSignature()}`;
    if (derivedPublishedCache.has(cacheKey)) {
      const hit = derivedPublishedCache.get(cacheKey);
      lastPublishedDerivation[key] = hit.info;
      return new Map(hit.values);
    }
    const savedRow = savedPublishedRow(key, "combo_reindexed");
    const nativeRow = savedPublishedRow(key, "native");
    const saved = new Map();
    const native = new Map();
    savedRow?.values?.forEach((rawValue, playerKey) => {
      const value = clampValue(rawValue);
      if (canonicalByKey.has(playerKey) && value !== null) saved.set(playerKey, value);
    });
    nativeRow?.values?.forEach((rawValue, playerKey) => {
      const value = Number(rawValue);
      if (canonicalByKey.has(playerKey) && Number.isFinite(value)) native.set(playerKey, value);
    });
    let values = new Map();
    let info = {mode: "unavailable", reason: "no saved 12-team setup for this scoring"};
    if (saved.size && native.size) {
      // JEG332-DERIVED-PEAKS: our ESPN projections let the positional maxes
      // follow the league (ValueModel.positionalMaxForSetup).
      const field = scoringField();
      const projection = new Map();
      canonicalByKey.forEach((player, playerKey) => {
        const ppg = player.espn_ppg?.[field];
        if (typeof ppg === "number" && Number.isFinite(ppg)) projection.set(playerKey, ppg);
      });
      const derived = ValueModel.derivePublishedSetup({
        native, saved, indexTotal: savedRow.index_total,
        posOf: playerKey => canonicalByKey.get(playerKey)?.pos,
        teams, shape: rosterShape, projection, peers: publishedPeers(key)
      });
      values = derived.values;
      info = {mode: "derived", version: derived.version,
        positionalMax: derived.positionalMax, ourMax: derived.ourMax,
        translationVersion: derived.translationVersion, translated: derived.translated,
        belowWaiver: derived.belowWaiver, waiver: derived.waiver};
    }
    derivedPublishedCache.set(cacheKey, {values, info});
    lastPublishedDerivation[key] = info;
    return new Map(values);
  }

  function buildPublishedSourceMap(key) {
    // JEG-363 (2026-10-04): per-cell values come from product-data.js
    // (api.player_values surface, view=combo_reindexed). The widget no
    // longer walks the legacy detail deep-path `data.sources[key].combos[...]`;
    // the contract adapter owns every fixture read.
    if (typeof window === "undefined" || !window.TradeValueProductData) {
      throw new Error("product-data.js missing; buildPublishedSourceMap refused.");
    }
    if (AS_PUBLISHED_KEYS.has(key) && !onSavedSetup()) return derivedPublishedSourceMap(key);
    if (AS_PUBLISHED_KEYS.has(key)) lastPublishedDerivation[key] = {mode: "saved", waiver: publishedWaiver(key)};
    const row = window.TradeValueProductData.getPlayerValues({
      source: key,
      scoring,
      teams,
      qbVariant: "qb1",
      view: "combo_reindexed",
    });
    const values = new Map();
    if (!row || !row.values) return values;
    row.values.forEach((rawValue, playerKey) => {
      const player = canonicalByKey.get(playerKey);
      const value = clampValue(rawValue);
      if (!player || value === null) return;
      if (values.has(playerKey) && values.get(playerKey) !== value) throw new Error(`Conflicting canonical identity ${playerKey} in ${sourceLabel(key)}.`);
      values.set(playerKey, value);
    });
    return values;
  }

  // JEG-242: build a source map from vorp_views (indexed/vorp/adj_values).
  // vorp_views keys are normalized lowercase display names, exactly the form
  // used by the fixture's player_keys table. JEG332-VORP-VIEWS (2026-10-07):
  // resolve through product-data's copy of that table -- since JEG-363 the
  // snapshot `data` carries no player_keys, so this lookup came back empty and
  // the views silently showed the Indexed values instead.
  function buildVorpViewSourceMap(key, viewKey) {
    const vorpViews = data.sources?.[key]?.vorp_views;
    const viewData = vorpViews?.views?.[viewKey];
    if (!viewData || typeof viewData !== "object") return new Map();
    const keysById = window.TradeValueProductData?.getPlayerKeysBySourceId?.() || new Map();
    const nameToKey = new Map();
    keysById.forEach((playerKey, displayName) => {
      const norm = String(displayName).trim().toLowerCase();
      if (canonicalByKey.has(Number(playerKey)) && norm && !nameToKey.has(norm)) nameToKey.set(norm, Number(playerKey));
    });
    const values = new Map();
    Object.entries(viewData).forEach(([displayName, rawValue]) => {
      const playerKey = nameToKey.get(String(displayName).trim().toLowerCase());
      const player = canonicalByKey.get(playerKey);
      const value = clampValue(rawValue);
      if (!player || value === null) return;
      values.set(playerKey, value);
    });
    return values;
  }

  // JEG332-VORP-VIEWS: the saved vorp_views apply only at the exact setup
  // they were built for -- their own scoring and team count, standard roster.
  // (Before 2026-10-07 the scoring was never compared, so Standard / Half PPR
  // at 12 teams showed the full-PPR views.)
  const VIEW_SCORING = {ppr: "ppr", full: "ppr", half_ppr: "half_ppr", half: "half_ppr", standard: "standard"};
  function savedViewApplies(key) {
    const vorpViews = data.sources?.[key]?.vorp_views;
    if (!vorpViews || !onSavedSetup()) return false;
    return VIEW_SCORING[String(vorpViews.scoring || "").toLowerCase()] === scoring
      && Number(vorpViews.teams) === teams;
  }

  // JEG332-VORP-VIEWS: every published chart derived into the VORP-vs-waivers
  // and Adjusted views at the active setting (ValueModel.derivePublishedViews),
  // as one batch so the Adjusted 70 anchor is shared. Inputs: each chart's
  // saved 12-team native values, its saved player set, and the live anchor's
  // eight group totals at this setting over that player set.
  function derivedViewBatch() {
    if (derivedViewBatchCache) return derivedViewBatchCache;
    const anchor = sourceMaps.get("espn");
    const inputs = {};
    [...AS_PUBLISHED_KEYS].forEach(key => {
      const savedRow = savedPublishedRow(key, "combo_reindexed");
      const nativeRow = savedPublishedRow(key, "native");
      const native = new Map();
      const keys = [];
      nativeRow?.values?.forEach((rawValue, playerKey) => {
        const value = Number(rawValue);
        if (canonicalByKey.has(playerKey) && Number.isFinite(value)) native.set(playerKey, value);
      });
      savedRow?.values?.forEach((rawValue, playerKey) => {
        if (canonicalByKey.has(playerKey) && clampValue(rawValue) !== null) keys.push(playerKey);
      });
      if (native.size && keys.length) inputs[key] = {native, keys};
    });
    // The anchor's eight group totals at this setting, measured over each
    // chart's own players (roles from the whole anchor).
    if (anchor?.size) {
      const playerOf = playerKey => canonicalByKey.get(playerKey);
      const roles = ValueModel.roleMap({values: anchor, playerOf, teams, shape: rosterShape});
      Object.values(inputs).forEach(input => {
        input.budgets = ValueModel.anchorGroupTotals({values: anchor, playerOf, roles, keys: new Set(input.keys)});
      });
    }
    // V2-WAIVER-COVERAGE: every published chart's natives, so each chart's
    // peers are exactly the ones the Indexed derivation uses.
    const natives = {};
    AS_PUBLISHED_KEYS.forEach(key => {
      const native = savedPublishedNative(key);
      if (native.size) natives[key] = native;
    });
    derivedViewBatchCache = anchor?.size && Object.keys(inputs).length
      ? ValueModel.derivePublishedViews({
          sources: inputs, natives, posOf: playerKey => canonicalByKey.get(playerKey)?.pos,
          teams, shape: rosterShape
        })
      : {version: ValueModel.PUBLISHED_VIEWS_VERSION, sources: {}, batchMax: 0, adjScale: 0};
    return derivedViewBatchCache;
  }

  // The VORP-vs-waivers / Adjusted map for a published chart at the active
  // setting: the saved view at its own setup, derived everywhere else.
  function publishedViewMap(key, viewKey) {
    if (savedViewApplies(key)) {
      const saved = buildVorpViewSourceMap(key, viewKey);
      if (saved.size) {
        lastPublishedView[key] = {mode: "saved", view: viewKey};
        return saved;
      }
    }
    const batch = derivedViewBatch();
    const derived = viewKey === "adj_values" ? batch.sources[key]?.adj : batch.sources[key]?.vorp;
    lastPublishedView[key] = derived?.size
      ? {mode: "derived", view: viewKey, version: batch.version, batchMax: batch.batchMax, adjScale: batch.adjScale}
      : {mode: "unavailable", view: viewKey};
    return derived ? new Map(derived) : new Map();
  }

  // JEG-210: does this source have a view for the current view mode? Since
  // JEG332-VORP-VIEWS every published chart with saved 12-team inputs for this
  // scoring has one at every setting (saved at its own setup, else derived).
  function sourceHasVorpView(key) {
    const viewKey = getViewKey(viewMode);
    if (!viewKey) return true;
    if (savedViewApplies(key) && buildVorpViewSourceMap(key, viewKey).size) return true;
    const nativeRow = savedPublishedRow(key, "native");
    return !!(nativeRow?.values && nativeRow.values.size);
  }

  function buildNativeSourceMap(key) {
    // Razzball: native PPG lives on the canonical player objects (rz_ppg),
    // not in api.player_values. Build from getPlayers() via product-data.
    if (key === "razzball") {
      const values = new Map();
      const field = scoringField();
      canonicalByKey.forEach((player, playerKey) => {
        const ppg = Number(player.rz_ppg?.[field]);
        if (!Number.isFinite(ppg)) return;
        values.set(playerKey, ppg);
      });
      return values;
    }
    // CBS ROS: same pattern — native PPG baked onto canonical player objects
    // (cbsros_ppg) by pipelines/bake_players.py (JEG-33).
    if (key === "cbsros") {
      const values = new Map();
      const field = scoringField();
      canonicalByKey.forEach((player, playerKey) => {
        const ppg = Number(player.cbsros_ppg?.[field]);
        if (!Number.isFinite(ppg)) return;
        values.set(playerKey, ppg);
      });
      return values;
    }
    // JEG-363: native values come from product-data.js (view=native).
    if (typeof window === "undefined" || !window.TradeValueProductData) {
      throw new Error("product-data.js missing; buildNativeSourceMap refused.");
    }
    // league-settings-001: a source's native values are the same at every
    // league setting; only the saved 12-team setup carries them.
    const row = window.TradeValueProductData.getPlayerValues({
      source: key,
      scoring,
      teams: AS_PUBLISHED_KEYS.has(key) ? ValueModel.SAVED_SETUP_TEAMS : teams,
      qbVariant: "qb1",
      view: "native",
    });
    const values = new Map();
    if (!row || !row.values) return values;
    row.values.forEach((nativeValue, playerKey) => {
      const player = canonicalByKey.get(playerKey);
      const value = Number(nativeValue);
      if (!player || !Number.isFinite(value)) return;
      if (values.has(playerKey) && values.get(playerKey) !== value) throw new Error(`Conflicting canonical identity ${playerKey} in ${sourceLabel(key)} native.`);
      values.set(playerKey, value);
    });
    return values;
  }

  // Delegates to the shared value model. Both renderers must agree here; a
  // second implementation is what put the curve at 69.5 and the table at 76.5
  // for the same source on the same page load.
  function roleMapForValues(values) {
    return ValueModel.roleMap({
      values,
      playerOf: playerKey => canonicalByKey.get(playerKey),
      teams,
      shape: rosterShape
    });
  }

  // share defaults to the frozen stage-1 display share: fallback curves never
  // move with the bench-share slider. Live-derived stage-2 paths (baked
  // adjustment cells present) pass the active slider share explicitly.
  // Players the anchor prices but this source does not are NOT part of this
  // source's pie. Scaling a 124-player chart and a 350-player anchor to the
  // SAME total forces the thinner chart's curve taller everywhere -- that is
  // why the published charts peaked at 85-92 against the anchor's 69.5 while
  // every pie total agreed to 1e-12. The pie basis is the SHARED set: the
  // target is the anchor's total over exactly the players both price.
  // Players the anchor prices but this source does not are NOT part of this
  // source's pie. Scaling a 124-player chart and a 350-player anchor to the
  // SAME total forces the thinner chart's curve taller everywhere -- that is
  // why the published charts peaked at 85-92 against the anchor's 69.5 while
  // every pie total agreed to 1e-12. The pie basis is the SHARED set.
  //
  // Both sides must be measured on that same basis. Taking the target from the
  // shared set while totalling the source over ALL its players leaves the
  // scale short by whatever sits outside the overlap -- a source whose players
  // are all in the anchor (CBS) still balances, so the error hides until a
  // source carries players the anchor lacks.
  function normalizeTradeChartToFixedPie(values, share = DISPLAY_BENCH_SHARE, anchor = null, sourceKey = null) {
    return ValueModel.normalizeToFixedPie({
      values,
      anchor,
      share,
      playerOf: playerKey => canonicalByKey.get(playerKey),
      teams,
      shape: rosterShape,
      fallbackTarget: commonFixedPieTotal,
      // As-published sources use a single global scale to preserve their
      // native cross-position order; the starter/bench two-tier scaling
      // would create a discontinuity at the transition.
      singleScale: sourceKey ? AS_PUBLISHED_KEYS.has(sourceKey) : false,
    });
  }

  function compareEspnPlayers(a, b) {
    return b.ppg - a.ppg || ValueModel.stableTiebreak(a.player, b.player);
  }

  function vorpPricedRows(vorpKey) {
    const def = VORP_SOURCE_DEFS[vorpKey];
    const field = scoringField();
    return [...canonicalByKey.values()]
      .filter(player => POSITION_ORDER.includes(player.pos))
      .map(player => ({player, ppg:Number(player[def.ppgField]?.[field])}))
      .filter(item => Number.isFinite(item.ppg))
      .sort(compareEspnPlayers);
  }

  function espnPricedRows() {
    return vorpPricedRows("espn_vorp");
  }

  // Raw value-above-waivers rows per VORP source (JEG-38): the same
  // projection-minus-waiver math for ESPN, CBS ROS, and Razzball, each from
  // its own per-game projections. The target pie is the shared anchor pie
  // for all three, so the raw curves sit on a comparable scale.
  function buildVorpRows(vorpKey) {
    if (vorpRowsCache.has(vorpKey)) return vorpRowsCache.get(vorpKey);
    const def = VORP_SOURCE_DEFS[vorpKey];
    const priced = vorpPricedRows(vorpKey);
    // Roles come from the shared model, ranked on surplus over each
    // position's dedicated-starter baseline. Assigning them here by raw
    // per-game points filled the bench with quarterbacks, collapsed the QB
    // waiver line and made Josh Allen the most valuable asset in a 1QB league.
    const ppgByKey = new Map(priced.map(row => [row.player.player_key, row.ppg]));
    const assigned = ValueModel.projectionRoles({
      pool: priced.map(row => row.player),
      teams: teams,
      shape: rosterShape,
      rankOf: player => Number(ppgByKey.get(player.player_key))
    }).roles;
    const tiered = priced.map(row => ({
      ...row,
      role: assigned.get(row.player.player_key) || "waiver"
    }));
    const baselineByPos = new Map();
    POSITION_ORDER.forEach(pos => {
      const waiver = tiered
        .filter(row => row.player.pos === pos && row.role === "waiver")
        .sort(compareEspnPlayers)[0];
      const fallback = tiered.filter(row => row.player.pos === pos).sort(compareEspnPlayers).at(-1);
      baselineByPos.set(pos, Number(waiver?.ppg ?? fallback?.ppg ?? 0));
    });
    const withRaw = tiered.map(row => ({
      ...row,
      rawProjectionVorp: row.role === "waiver" ? 0 : Math.max(0, row.ppg - (baselineByPos.get(row.player.pos) || 0))
    }));
    // The raw curves use the true raw projection-minus-waiver VORP computed
    // from each source's own projections above. We intentionally do NOT use
    // the published combo values here: those are already run through a
    // valuation model (and can carry a ~91% starter share), which inverts
    // the fixed-pie direction. Raw VORP keeps starters at ~69% of the pie,
    // so the 85/15 fixed-pie correctly marks starters up and bench down.
    // This also keeps each raw curve source-pure (projections only, no
    // expert/model blending).
    const withVorp = withRaw.map(row => ({
      ...row,
      rawVorp: row.rawProjectionVorp
    }));
    const starterRaw = withVorp.filter(row => row.role === "starter").reduce((sum, row) => sum + row.rawVorp, 0);
    const benchRaw = withVorp.filter(row => row.role === "bench").reduce((sum, row) => sum + row.rawVorp, 0);
    const rawTotal = starterRaw + benchRaw;
    // Same total as the per-position pie the adjusted curves are priced on,
    // so the raw curve sits on a comparable scale. Using the single common
    // pie here left it 26 points short of the anchor and failed the guard.
    const targetTotal = POSITION_ORDER.reduce((sum, pos) => {
      const t = Number(espnTargetTotal(pos, NaN));
      return sum + (Number.isFinite(t) && t > 0 ? t : 0);
    }, 0) || espnTargetPool(rawTotal);
    // Frozen stage-1 display share: the indexed maps are fallback
    // curves and never move with the bench-share slider.
    const starterShare = Math.max(0, Math.min(1, 1 - DISPLAY_BENCH_SHARE));
    const normalizedBenchShare = Math.max(0, Math.min(1, DISPLAY_BENCH_SHARE));
    const rawScale = rawTotal > 0 && targetTotal > 0 ? targetTotal / rawTotal : 1;
    const starterScale = starterRaw > 0 && targetTotal > 0 ? (targetTotal * starterShare) / starterRaw : 0;
    const benchScale = benchRaw > 0 && targetTotal > 0 ? (targetTotal * normalizedBenchShare) / benchRaw : 0;
    // Active invariant checks: the fixed-pie must mark starters UP and bench
    // DOWN relative to the raw curve. If the raw pool is materially
    // starter-heavy, the pie inverts -- the exact defect this guards against
    // (pre-valued inputs at ~91% raw starter share, JEG-68). The share and
    // scale inequalities below are the same strict condition stated three
    // ways (starterScale > rawScale and benchScale < rawScale both reduce to
    // rawStarterShare < starterShare for positive pools), so the single
    // epsilon-tolerant predicate replaces all three -- a strict inequality
    // is knife-edge (CBS ROS genuinely sits 0.2-0.3pp over target at 14-team
    // standard, JEG-69). These run on every build; failures are visible,
    // never silent.
    // For ESPN these two describe the FALL-BACK leg: the browser-derived
    // pricing that `adjusted` carries. While the pipeline's built leg is
    // present that is what the ESPN line renders, so a wobble in the
    // fall-back is a note, not a failure -- recording it as a failure is how
    // a 1.048-vs-1.05 markup on an undisplayed curve came to sit red in the
    // health panel. CBS ROS and Razzball have no built-leg fallback, so
    // their checks record directly.
    const recordForKey = vorpKey === "espn_vorp"
      ? (() => {
          const legIsFallback = espnLegIsFallback();
          return legIsFallback
            ? (id, label, ok, detail) => ChartHealth.record(id, label, ok, detail)
            : (id, label, ok, detail) => (ok ? ChartHealth.record(id, label, true, detail)
                                             : ChartHealth.warn(id, label, `${detail} -- fall-back leg only; the ESPN line renders the built leg`));
        })()
      : (id, label, ok, detail) => ChartHealth.record(id, label, ok, detail);
    if (rawTotal > 0 && starterRaw > 0 && benchRaw > 0) {
      const rawStarterShare = starterRaw / rawTotal;
      recordForKey(
        `${vorpKey}-fixed-pie-direction`,
        `${def.short} fixed-pie direction (starters up, bench down)`,
        ValueModel.fixedPieDirectionSane(rawStarterShare, starterShare),
        `raw starter share ${(rawStarterShare * 100).toFixed(1)}% vs target ${(starterShare * 100).toFixed(1)}% ` +
        `(tolerance +${(ValueModel.STARTER_DIRECTION_EPS * 100).toFixed(1)}pp); ` +
        `starter scale ${starterScale.toFixed(3)} vs raw ${rawScale.toFixed(3)}, bench scale ${benchScale.toFixed(3)} vs raw ${rawScale.toFixed(3)}`
      );
      // The starter markup ratio is deterministic: target_share / raw_share.
      // ~1.0 is correct when a source's raw pool already sits at the target
      // split (CBS ROS: 84.96% raw starter share, verified source-pure --
      // JEG-68); the adjustment is vacuous there, not broken. Flag material
      // inversions (starters marked down: pre-valued inputs) and absurd
      // inflations instead -- see ValueModel.starterMarkupSane.
      const markup = starterScale / rawScale;
      recordForKey(
        `${vorpKey}-starter-markup`,
        `${def.short} starter markup ratio sane`,
        ValueModel.starterMarkupSane(markup),
        `starter adjusted/pure = ${markup.toFixed(3)} (sane band ${ValueModel.STARTER_MARKUP_SANE_LOW}-${ValueModel.STARTER_MARKUP_SANE_HIGH}; ~${(starterShare / Math.max(rawStarterShare, 1e-9)).toFixed(2)} at ${(rawStarterShare * 100).toFixed(1)}% raw starter share)`
      );
    } else {
      ChartHealth.warn(
        `${vorpKey}-fixed-pie-direction`,
        `${def.short} fixed-pie direction (starters up, bench down)`,
        `skipped: degenerate pool (rawTotal=${rawTotal.toFixed(1)}, starterRaw=${starterRaw.toFixed(1)}, benchRaw=${benchRaw.toFixed(1)})`
      );
    }
    // Per-position, per-tier scales: each position lands on its own pie and
    // splits DISPLAY_BENCH_SHARE the same way, so the pool-level identity holds too.
    // A single global pair of scales cannot do both, and skipping the pie is
    // what left quarterbacks at roughly double the published charts.
    const tierScales = ValueModel.positionalTierScales(
      withVorp.map(row => ({pos: row.player.pos, role: row.role, value: row.rawVorp})),
      pos => espnTargetTotal(pos, NaN),
      DISPLAY_BENCH_SHARE
    );
    const rows = withVorp.map(row => ({
      ...row,
      pure: row.rawVorp * rawScale,
      adjusted: row.role === "starter" ? row.rawVorp * (tierScales.starter[row.player.pos] || 0)
        : row.role === "bench" ? row.rawVorp * (tierScales.bench[row.player.pos] || 0) : 0
    }));
    vorpRowsCache.set(vorpKey, rows);
    // The table's tier column is ESPN-based; only ESPN rows feed it.
    if (vorpKey === "espn_vorp") {
      espnRoleByKey = new Map(rows.map(row => [row.player.player_key, row.role]));
    }
    return rows;
  }

  function buildEspnRows() {
    return buildVorpRows("espn_vorp");
  }

  function espnVorpRows(pos) {
    return buildEspnRows().filter(row => row.player.pos === pos);
  }

  function vorpRows(vorpKey, pos) {
    return buildVorpRows(vorpKey).filter(row => row.player.pos === pos);
  }

  function buildVorpMap(vorpKey) {
    const values = new Map();
    buildVorpRows(vorpKey).forEach(row => values.set(row.player.player_key, row.pure));
    return values;
  }

  function buildEspnVorpMap() {
    return buildVorpMap("espn_vorp");
  }

  // The ESPN line IS the two-tier leg the pipeline built, read from the
  // fixture like every other source. It used to be re-derived here from raw
  // ESPN per-game projections (ppg minus a positional waiver line, then
  // scaled onto the positional pie), and that re-derivation is a SECOND,
  // cruder valuation wearing the anchor's name: no softplus glide, no
  // two-tier slice pricing, and a bench assigned by surplus-over-baseline
  // that handed 17 of 72 bench slots to quarterbacks in a 1QB league.
  //
  // The two models do not agree, and the published charts are isotonically
  // reindexed onto the PIPELINE leg at build time, so the re-derivation left
  // exactly one curve off-shape: RB peak 99.1 against the charts' 79-82,
  // QB peak 12.5 against their 16.6-16.9 -- with every positional total
  // matching to a rounding error, which is why the pie guards stayed green.
  // The charts were right. The anchor was a different model.
  //
  // buildEspnRows() still runs: it prices the raw value-above-waivers series
  // (a deliberately separate, labelled curve) and assigns the ESPN tier shown
  // in the table. Its `adjusted` field is the fail-safe used only when the
  // fixture carries no leg for this combo.
  // Memoised so the guards in buildEspnRows can ask whether the built leg is
  // present without rebuilding it. Cleared with the rest of the domain.
  function espnFixtureLeg() {
    if (!espnFixtureLegCache) espnFixtureLegCache = buildPublishedSourceMap("espn");
    return espnFixtureLegCache;
  }

  function espnLegIsFallback() {
    return espnFixtureLeg().size < ValueModel.MIN_SHARED_FOR_PIE;
  }

  function buildEspnIndexedMap() {
    const leg = espnFixtureLeg();
    if (leg.size >= ValueModel.MIN_SHARED_FOR_PIE) return new Map(leg);
    ChartHealth.warn(
      "espn-leg-source",
      "ESPN anchor read from the built leg",
      `fixture leg for ${comboKey("espn")} has ${leg.size} players (< ${ValueModel.MIN_SHARED_FOR_PIE}); ` +
      "falling back to the browser-derived leg, which is a different model"
    );
    const values = new Map();
    buildEspnRows().forEach(row => values.set(row.player.player_key, row.adjusted));
    return values;
  }

  // Match the charts to the anchor's OWN starter/bench split rather than to a
  // constant. DISPLAY_BENCH_SHARE stays the two-tier calibration parameter;
  // it is not a claim about how the built leg happens to divide.
  function anchorDisplayShare(anchor) {
    const measured = ValueModel.benchShareOf({
      values: anchor,
      playerOf: playerKey => canonicalByKey.get(playerKey),
      teams,
      shape: rosterShape
    });
    return Number.isFinite(measured) ? measured : DISPLAY_BENCH_SHARE;
  }

  function buildSourceMap(key) {
    // JEG-210/242: when a non-indexed view is active and the source has
    // vorp_views, use the view's values instead of the indexed combo values.
    // Re-restored 2026-10-04 (dropped by the JEG-325 refactor).
    if (viewMode !== "indexed" && AS_PUBLISHED_KEYS.has(key)) {
      const viewKey = getViewKey(viewMode);
      // JEG332-VORP-VIEWS: saved view at its own setup, derived at every other
      // scoring / team count / roster (never the Indexed values in disguise).
      if (viewKey) return publishedViewMap(key, viewKey);
    }
    return buildPublishedSourceMap(key);
  }

  function applyRosterShape(values, key) {
    // As-published sources (FantasyCalc, USA Today, etc.) carry their own
    // native cross-position ranking. The per-position factors below would
    // destroy that order (e.g., QBs scaled differently from RBs), causing
    // the plotted curve to deviate from the sort order. These sources are
    // already indexed to the anchor's pie via normalizeTradeChartToFixedPie;
    // they must pass through unshaped to preserve their native order.
    if (AS_PUBLISHED_KEYS.has(key)) return values;
    if (rosterIsDefault() || PURE_VORP_KEYS.includes(key)) return values;
    const shaped = new Map(values);
    const defaultCounts = allocationCountsFor([...canonicalByKey.values()], DEFAULT_ROSTER);
    const customCounts = allocationCountsFor([...canonicalByKey.values()], rosterShape);
    // Totals are taken over QB/RB/WR/TE only, and the correction is applied
    // to the same set. Kickers and defenses sit outside the skill pie: rolling
    // them into the before/after totals let them dilute the correction, which
    // left the anchor's skill total 7.9 short of its positional targets the
    // moment a roster slot moved. They pass through unshaped, which is right --
    // a WR slot does not reprice a kicker.
    const inPie = playerKey => POSITION_ORDER.includes(canonicalByKey.get(playerKey)?.pos);
    const totalBefore = [...values.entries()].reduce((sum, [playerKey, value]) => sum + (inPie(playerKey) ? value : 0), 0);
    POSITION_ORDER.forEach(pos => {
      const rows = [...values.entries()]
        .filter(([playerKey]) => canonicalByKey.get(playerKey)?.pos === pos)
        .map(([playerKey, value]) => ({playerKey, value}))
        .sort((a, b) => b.value - a.value);
      if (!rows.length) return;
      const defaultDepth = Math.max(1, Math.min(rows.length, defaultCounts.rostered[pos] || 1));
      const customDepth = Math.max(1, Math.min(rows.length, customCounts.rostered[pos] || 1));
      const averageTop = depth => rows.slice(0, depth).reduce((sum, row) => sum + row.value, 0) / depth;
      const defaultAverage = averageTop(defaultDepth);
      const customAverage = averageTop(customDepth);
      const factor = defaultAverage > 0 ? Math.max(0.25, Math.min(1.8, customAverage / defaultAverage)) : 1;
      rows.forEach(row => shaped.set(row.playerKey, row.value * factor));
    });
    const totalAfter = [...shaped.entries()].reduce((sum, [playerKey, value]) => sum + (inPie(playerKey) ? value : 0), 0);
    const fixedPieScale = totalBefore > 0 && totalAfter > 0 ? totalBefore / totalAfter : 1;
    shaped.forEach((value, playerKey) => { if (inPie(playerKey)) shaped.set(playerKey, value * fixedPieScale); });
    return shaped;
  }

  function buildCbsAdjustedMap() {
    const direct = sourceMaps.get("cbs");
    if (!direct?.size) return new Map();
    const pairs = [
      ["fantasycalc", "fantasycalc_adjusted"],
      ["usatoday", "usatoday_adjusted"],
      ["fantasypros", "fantasypros_adjusted"]
    ];
    const multipliers = new Map();
    direct.forEach((directValue, playerKey) => {
      const player = canonicalByKey.get(playerKey);
      if (!player || !Number.isFinite(directValue)) return;
      const ratios = pairs.map(([rawKey, adjustedKey]) => {
        const raw = sourceMaps.get(rawKey)?.get(playerKey);
        const adjusted = sourceMaps.get(adjustedKey)?.get(playerKey);
        return Number.isFinite(raw) && raw > 0 && Number.isFinite(adjusted) ? adjusted / raw : null;
      }).filter(Number.isFinite);
      const ratio = ratios.length ? ratios.reduce((sum, value) => sum + value, 0) / ratios.length : 1;
      multipliers.set(playerKey, Math.max(0, directValue * ratio));
    });
    // JEG-363: read CBS index_total via product-data.js (api.player_values).
    const cbsRow = (typeof window !== "undefined" && window.TradeValueProductData)
      ? window.TradeValueProductData.getPlayerValues({source: "cbs", scoring, teams, qbVariant: "qb1", view: "combo_reindexed"})
      : null;
    POSITION_ORDER.forEach(pos => {
      const rows = [...multipliers.entries()].filter(([playerKey]) => canonicalByKey.get(playerKey)?.pos === pos);
      const total = rows.reduce((sum, [, value]) => sum + value, 0);
      const target = Number(cbsRow?.index_total?.[pos]?.target_total);
      const scale = total > 0 && Number.isFinite(target) && target > 0 ? target / total : 1;
      rows.forEach(([playerKey, value]) => multipliers.set(playerKey, value * scale));
    });
    return multipliers;
  }

  // Generic live-adjust path. A source must carry the full position/tier cell
  // set before the adjusted curve is available; partial sources stay paused so
  // raw published values are never silently mixed into an adjusted projection.
  // Live-first (2026-10-01): when the browser has refit cells at the ACTIVE
  // bench share, they take precedence over the pipeline-baked cells (which
  // are frozen at the 0.15 reference share). The refit runs on every slider
  // move via refreshAfterWeightChange and on init before rebuildDomain.
  function liveCellsForSource(rawKey) {
    if (!liveCellsCache || !Array.isArray(liveCellsCache.cells)) return null;
    const cells = liveCellsCache.cells.filter(c => c.source === rawKey);
    return cells.length ? cells : null;
  }

  function adjustmentCellsFor(rawKey) {
    const live = liveCellsForSource(rawKey);
    if (live) return live;
    const entry = adjustmentInputs?.sources?.[rawKey];
    return adjustmentCellCompleteness(entry).complete ? entry.cells : null;
  }

  // Widget-scope pause check: bound to the loaded adjustmentInputs.
  // Fail-closed: before inputs load (or when absent), adjusted curves read
  // as paused.
  const isAdjustedCurvePaused = key => adjustedCurvePaused(key, adjustmentInputs);

  function buildLiveAdjustedMap(rawKey, cells, options) {
    options = options || {};
    const raw = buildPublishedSourceMap(rawKey);
    // Tier assignment (JEG-5 fix, 2026-10-01): the OLS cells are trained on
    // the DDF tier partition (ddf.starters/ddf.bench). Applying them via
    // roleMapForValues (published-value tiers) mismatches 69 players and
    // breaks the fixedPieIndexed guard by -79.90. Use the DDF tiers directly
    // — the same partition the cells were trained on. Falls back to
    // roleMapForValues only when the DDF is unavailable (data failure edge).
    const ddf = ["cbsros", "razzball"].includes(rawKey) ? ddfTwoTierValuesFor(rawKey) : ddfTwoTierValues();
    const usePublishedTierPartition = options.tierPartition === "published";
    const roles = (ddf && !usePublishedTierPartition) ? null : roleMapForValues(raw);
    const tierOf = playerKey => {
      if (ddf && !usePublishedTierPartition) {
        if (ddf.starters.has(playerKey)) return "starter";
        if (ddf.bench.has(playerKey)) return "bench";
        return null;
      }
      return roles.get(playerKey) || null;
    };
    const posOf = playerKey => (ddf && !usePublishedTierPartition) ? ddf.posOf.get(playerKey) : canonicalByKey.get(playerKey)?.pos;
    const cellByPosTier = new Map();
    cells.forEach(cell => {
      const pos = String(cell.position || "").toUpperCase();
      const tier = String(cell.tier || "").toLowerCase();
      const alpha = Number(cell.alpha);
      const beta = Number(cell.beta);
      if (!POSITION_ORDER.includes(pos) || !["starter", "bench"].includes(tier) || !Number.isFinite(alpha) || !Number.isFinite(beta)) return;
      cellByPosTier.set(`${pos}|${tier}`, {alpha, beta});
    });
    // two-tier-native sources (espn/cbsros/razzball, 2026-10-01) re-price live on
    // the bench-share slider. Fail-closed: a starter/bench player with NO
    // live cell is WITHHELD (infeasible share at the active setting), never
    // passed through with the raw fixture value. The pipeline always bakes
    // all 8 cells for these sources, so a missing live cell means the refit
    // withheld that position -- falling back to raw would silently show a
    // 0.15-frozen value on a moved slider.
    const isDdfNative = ["espn", "cbsros", "razzball"].includes(rawKey);
    const adjusted = new Map();
    raw.forEach((value, playerKey) => {
      const player = canonicalByKey.get(playerKey);
      const tier = tierOf(playerKey);
      const pos = posOf(playerKey);
      const cell = player && tier && pos ? cellByPosTier.get(`${pos}|${tier}`) : null;
      // DDF-native sources: only starter/bench players with live cells are
      // included. Waiver-tier players have no cells (the two-tier model does
      // not price them) and are not part of the calibration pie (surplus
      // only). Including them with raw display-scale values mixes scales
      // and breaks the fixedPieIndexed guard (2026-10-01).
      if (isDdfNative) {
        if (!cell) return;
      } else if (!cell && player && (tier === "starter" || tier === "bench")) {
        return;
      }
      const safeValue = Number.isFinite(value) ? Math.max(0, value) : 0;
      adjusted.set(playerKey, cell ? Math.max(0, cell.alpha + cell.beta * safeValue) : safeValue);
    });
    return adjusted;
  }

  function adjustedMapFor(key) {
    const rawKey = key === "cbs_adjusted" ? "cbs" : key.replace(/_adjusted$/, "");
    // DDF-native sources (cbsros, razzball): their "adjusted" map IS the
    // live DDF two-tier values from their own native projections. No
    // published-source cells to apply.
    if (["cbsros", "razzball"].includes(rawKey)) {
      const ddf = ddfTwoTierValuesFor(rawKey);
      return ddf ? ddf.values : new Map();
    }
    const cells = adjustmentCellsFor(rawKey);
    if (cells) return buildLiveAdjustedMap(rawKey, cells);
    return new Map();
  }

  // Stage-2 activation: when baked adjustment cells exist for a source, its
  // live-adjusted path normalizes at the ACTIVE slider share; every fallback
  // path stays frozen at the stage-1 display share so moving the slider
  // cannot change a fallback curve.
  function adjustedShareFor(key, fallbackShare = DISPLAY_BENCH_SHARE) {
    const rawKey = rawKeyForAdjusted(key);
    return adjustmentCellsFor(rawKey) ? benchShare : fallbackShare;
  }

  function normalizedAdjustedMapFor(key, anchorMap, displayShare) {
    const rawKey = rawKeyForAdjusted(key);
    const values = applyRosterShape(adjustedMapFor(key), key);
    if (adjustmentCellsFor(rawKey)) {
      return ValueModel.shapeToAnchorPeaksThenSharedTotal({
        values,
        anchor: anchorMap,
        playerOf: playerKey => canonicalByKey.get(playerKey)
      });
    }
    return normalizeTradeChartToFixedPie(values, adjustedShareFor(key, displayShare), anchorMap);
  }

  // GAP-025 (Jeremy, 2026-10-07: "Yes, use 0"): a player ESPN lists but
  // projects at 0 (injured/out) is worth 0.0 on the ESPN series, not missing,
  // so a chart that still pays for him has a real gap.
  // GAP-ESPN-BELOW-LEG (Jeremy, 2026-10-07): the same for a player a source
  // projects above 0 but below its built leg: 0.0 on that leg, not missing.
  // "Below the leg" is proved, not assumed: his per-game projection is at or
  // below the lowest projection the leg prices at his position. A player above
  // that line whom the leg still lacks, or a position the leg does not price
  // at all (CBS ROS quarterbacks at 8 teams), stays missing (fail closed).
  // Display only: the zeros go into the row, never into sourceMaps, so the
  // ESPN anchor every chart is indexed against, its pie and its peaks are
  // unchanged. A player with no row in the source stays missing (—).
  // The raw *_vorp series already price every projected player (0 at or below
  // waivers), so only ESPN-0 needs a rule there.
  const ESPN_ZERO_VALUE_KEYS = new Set(["espn", "espn_vorp"]);
  const LEG_PPG_FIELDS = {espn: "espn_ppg", cbsros: "cbsros_ppg", razzball: "rz_ppg"};
  let legFloors = new Map();
  function projectionOf(player, key) {
    const ppg = player?.[LEG_PPG_FIELDS[key]]?.[scoringField()];
    return typeof ppg === "number" && Number.isFinite(ppg) ? ppg : null;
  }
  // key -> {pos: lowest per-game projection the leg prices at that position}.
  function buildLegFloors() {
    const floors = new Map();
    Object.keys(LEG_PPG_FIELDS).forEach(key => {
      const byPos = {};
      sourceMaps.get(key)?.forEach((_, playerKey) => {
        const player = canonicalByKey.get(playerKey);
        const ppg = projectionOf(player, key);
        if (ppg === null) return;
        byPos[player.pos] = Math.min(byPos[player.pos] ?? Infinity, ppg);
      });
      floors.set(key, byPos);
    });
    return floors;
  }
  function rowValue(key, player) {
    const map = sourceMaps.get(key);
    if (map?.has(player.player_key)) return map.get(player.player_key);
    if (!map?.size) return null;
    if (ESPN_ZERO_VALUE_KEYS.has(key) && player.espnProjectsZero) return 0;
    if (LEG_PPG_FIELDS[key]) {
      const ppg = projectionOf(player, key);
      const floor = legFloors.get(key)?.[player.pos];
      if (ppg !== null && Number.isFinite(floor) && ppg <= floor) return 0;
    }
    return null;
  }

  function rebuildDomain() {
    // Live cells first: the two-tier-native curves (espn/cbsros/razzball) and the
    // _adjusted family re-price on the bench-share slider via the refit cells.
    // Cache-hit when refreshAfterWeightChange already refit for this share.
    refitLiveCells();
    vorpRowsCache.clear();
    espnFixtureLegCache = null;
    derivedViewBatchCache = null;
    lastPublishedView = {};
    espnRoleByKey = new Map();
    sourceMaps = new Map();
    nativeSourceMaps = new Map();
    // The anchor must exist before anything normalises against it.
    // 2026-10-01: the anchor (espn) re-prices live on the bench-share slider
    // via its refit cells. At the 0.15 reference share the cells are identity
    // and this reproduces the baked fixture leg (pinned regression test).
    buildEspnRows();
    const espnLiveCells = adjustmentCellsFor("espn");
    const espnAnchorValues = espnLiveCells
      ? buildLiveAdjustedMap("espn", espnLiveCells)
      : buildEspnIndexedMap();
    const anchorMap = applyRosterShape(espnAnchorValues, "espn");
    sourceMaps.set("espn", anchorMap);
    const displayShare = anchorDisplayShare(anchorMap);
    lastDisplayShare = displayShare;
    // two-tier-native sources (cbsros, razzball) re-price live on the slider via
    // the same cell path as the _adjusted family; normalizedAdjustedMapFor
    // is key-agnostic (rawKeyForAdjusted passes them through unchanged).
    const TWO_TIER_NATIVE_LIVE_KEYS = new Set(["cbsros", "razzball"]);
    SOURCE_KEYS.filter(key => key !== "espn").forEach(key => {
      // As-published sources (FantasyCalc, USA Today, etc.) are already
      // indexed to the anchor's pie by the pipeline via
      // proportional_scaling_vorp_overlap. Re-applying normalizeToFixedPie
      // here double-scales them and breaks the fixed-pie guard. Use the
      // fixture values directly.
      const sourceMap = key.endsWith("_adjusted") || TWO_TIER_NATIVE_LIVE_KEYS.has(key)
        ? normalizedAdjustedMapFor(key, anchorMap, displayShare)
        : AS_PUBLISHED_KEYS.has(key)
          ? buildSourceMap(key)
          : normalizeTradeChartToFixedPie(applyRosterShape(buildSourceMap(key), key), displayShare, anchorMap, key);
      sourceMaps.set(key, sourceMap);
      // As-published sources get a native-value map for lock-order sorting.
      if (AS_PUBLISHED_KEYS.has(key)) {
        nativeSourceMaps.set(key, buildNativeSourceMap(key));
      }
    });
    // Level-matched to the anchor over the players they share; each SHAPE is
    // deliberately its own. Scaling to the positional-target sum instead
    // put ESPN 15.7 above the anchor on the shared set and failed the pie guard.
    PURE_VORP_KEYS.forEach(vorpKey => {
      sourceMaps.set(vorpKey, ValueModel.scaleToSharedTotal({
        values: buildVorpMap(vorpKey),
        anchor: anchorMap,
        playerOf: playerKey => canonicalByKey.get(playerKey)
      }));
    });

    legFloors = buildLegFloors();
    const keys = new Set();
    visibleSourceKeys().forEach(key => sourceMaps.get(key)?.forEach((_, playerKey) => keys.add(playerKey)));
    universe = [...keys].map(playerKey => {
      const player = canonicalByKey.get(playerKey);
      if (!player) return null;
      const values = Object.fromEntries(visibleSourceKeys().map(key => [key, rowValue(key, player)]));
      return {...player, espnRole:espnRoleByKey.get(playerKey) || "waiver", values};
    }).filter(Boolean);
    orderedRows = universe.filter(row => isPosition(row)).sort(orderComparator);
    syncPlayerOptions();
    syncContext();
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
    if (visibleSourceKeys().includes(lockOrder) && sourceAvailable(lockOrder) && !isAdjustedCurvePaused(lockOrder)) return lockOrder;
    if (!isAdjustedCurvePaused("fantasycalc_adjusted") && sourceAvailable("fantasycalc_adjusted")) return "fantasycalc_adjusted";
    if (sourceAvailable("espn")) return "espn";
    return activeSourceKeys()[0] || "espn";
  }

  function syncContext() {
    const context = $("#curveContext");
    if (!context) return;
    const positionLabel = position === "ALL" ? "All positions" : position === "FLEX" ? "RB / WR / TE" : position;
    const freshness = sourceFreshness();
    const referenceWeek = freshness?.first_load_reference_week;
    const weekLabel = referenceWeek ? `Week ${referenceWeek} references` : "references of unknown week";
    const espnText = freshnessText("espn");
    const rosterLabel = `${rosterShape.QB}QB/${rosterShape.RB}RB/${rosterShape.WR}WR/${rosterShape.TE}TE/${rosterShape.FLEX}FLEX/${rosterShape.BENCH}BN`;
    const staleLabel = activeSourceKeys().filter(sourceIsStale)
      .map(key => ` · ${SOURCE_LABELS[key] || key}: ${freshnessText(key)}`).join("");
    const axisLabel = yAxisAuto ? "auto y-axis" : `y ${Math.round(yLow)}-${Math.round(yHigh)}`;
    const benchShareText = `${Math.round(DISPLAY_BENCH_SHARE * 100)}% bench share`;
    // JEG-291: the subtitle's bench-share segment is the recommended calibration
    // parameter, NOT the anchor leg's measured split (that lives in the footnote).
    // Surface the distinction on hover so readers don't conflate the two.
    // Re-restored 2026-10-04 (dropped by the JEG-325 refactor).
    context.replaceChildren(
      `${scoreLabel()} · ${teams} teams · ${rosterLabel} · `,
      Object.assign(document.createElement("span"), {
        textContent: benchShareText,
        title: "15% bench share — the recommended two-tier calibration parameter; the chart caption shows the anchor leg's measured split."
      }),
      ` · ${positionLabel} · ${axisLabel} · ${weekLabel} plus ESPN projections${espnText ? ` (${espnText})` : ""}${staleLabel} · locked to ${lockLabel(lockOrder)}`,
      // league-settings-001 / methodology.md: values derived for a league
      // setting the source did not publish must be labelled derived.
      onSavedSetup() ? "" : " · published charts derived from their 12-team, standard-roster values",
      waiverContextNote()
    );
  }

  // V2-WAIVER-COVERAGE: name the active published charts whose waiver line is
  // extrapolated from the other charts (they list fewer players than this
  // league rosters). Players those charts do not list stay "—".
  function waiverContextNote() {
    const notes = [...AS_PUBLISHED_KEYS]
      .filter(key => activeSourceKeys().some(active => active === key || (active.endsWith("_adjusted") && rawKeyForAdjusted(active) === key)))
      .map(key => {
        const info = publishedWaiver(key);
        return info && info.imputed.length ? `${SOURCE_LABELS[key] || key} (${info.imputed.join(", ")})` : null;
      })
      .filter(Boolean);
    return notes.length ? ` · waiver line extrapolated from other charts: ${notes.join(", ")}` : "";
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

  // ---- Live two-tier calibration (bench-share slider) ----
  // The calibration pool uses the fixed reference league shape (QB1 / RB2 /
  // WR3 / TE1 / 1 FLEX over RB-WR-TE, bench depths scaled by teams); the
  // slider bounds are therefore per scoring x teams, cached here. 0.15 is
  // feasible in all 12 supported combos (verified); if a config ever has no
  // feasible interval the UI fails closed instead of clamping silently.
  function twoTierConfigKey() {
    return `${scoring}|${teams}`;
  }

  function espnProjectionsByPos() {
    const field = scoringField();
    const lists = {QB: [], RB: [], WR: [], TE: []};
    canonicalByKey.forEach(player => {
      if (!TwoTier.POSITIONS.includes(player.pos)) return;
      const x = Number(player.espn_ppg?.[field]);
      if (!Number.isFinite(x)) return;
      lists[player.pos].push({id: player.player_key, x});
    });
    return lists;
  }

  // Position weights: baked defaults derived from the calibration pies, the
  // active weights (custom or baked), and the active pies (custom weights
  // rescale the baked total pie). Weights always sum to exactly 1.
  function bakedPositionWeights() {
    // Default weights reflect the calibration pies (tier surplus from the
    // live pool), so the weights UI starts from the actual allocation.
    const pies = twoTierConfig().pies || {};
    const total = TwoTier.POSITIONS.reduce((s, pos) => s + (Number(pies[pos]) || 0), 0);
    if (!(total > 0)) return null;
    const w = {};
    TwoTier.POSITIONS.forEach(pos => { w[pos] = (Number(pies[pos]) || 0) / total; });
    return w;
  }

  function activePositionWeights() {
    if (positionWeights) return {...positionWeights};
    return bakedPositionWeights() || {QB: 0.25, RB: 0.25, WR: 0.25, TE: 0.25};
  }

  function activePies() {
    const cfg = twoTierConfig();
    if (!positionWeights || !cfg.pies) return cfg.pies;
    const total = TwoTier.POSITIONS.reduce((s, pos) => s + (Number(cfg.pies[pos]) || 0), 0);
    const pies = {};
    TwoTier.POSITIONS.forEach(pos => { pies[pos] = total * (Number(positionWeights[pos]) || 0); });
    return pies;
  }

  function pieSignature(pies) {
    return TwoTier.POSITIONS.map(pos => (Number(pies?.[pos]) || 0).toFixed(3)).join(",");
  }

  // Linked sliders: moving one position's share takes from (or gives to) the
  // other three proportionally, so the four shares always total exactly 100%.
  function setPositionWeight(pos, fraction) {
    if (!TwoTier.POSITIONS.includes(pos)) return;
    const w = activePositionWeights();
    let next = Number(fraction);
    if (!Number.isFinite(next)) return;
    next = Math.min(1, Math.max(0, next));
    const delta = next - w[pos];
    if (Math.abs(delta) < 1e-9) return;
    w[pos] = next;
    const others = TwoTier.POSITIONS.filter(p => p !== pos);
    const otherTotal = others.reduce((s, p) => s + w[p], 0);
    if (otherTotal > 1e-9) {
      others.forEach(p => { w[p] = Math.max(0, w[p] - delta * (w[p] / otherTotal)); });
    } else if (others.length) {
      const rem = Math.max(0, 1 - next);
      others.forEach(p => { w[p] = rem / others.length; });
    }
    const total = TwoTier.POSITIONS.reduce((s, p) => s + w[p], 0);
    if (total > 1e-9) TwoTier.POSITIONS.forEach(p => { w[p] /= total; });
    positionWeights = w;
    refreshAfterWeightChange();
  }

  function resetPositionWeights() {
    positionWeights = null;
    refreshAfterWeightChange();
  }

  function resetAllWeights() {
    positionWeights = null;
    setBenchShareFraction(TwoTier.DEFAULT_BENCH_SHARE, false);
    refreshAfterWeightChange();
  }

  // Refit + redraw + republish after any weight change (position or bench).
  function refreshAfterWeightChange() {
    crossRank = null;
    liveCellsCache = null;
    syncPositionWeightControls();
    syncWeightsReadout();
    refitLiveCells();
    rebuildDomain();
    resetZoom();
    runRegressionGuards();
    draw();
    syncCurveStatus();
    publishShared();
  }

  function twoTierConfig() {
    const key = twoTierConfigKey();
    let entry = twoTierConfigCache.get(key);
    if (!entry) {
      entry = {lists: null, pool: null, pies: null, intervals: null, bounds: null, error: null};
      try {
        if (!data || !canonicalByKey.size) throw new Error("comparison data unavailable");
        const lists = espnProjectionsByPos();
        // Pool bench mix matches the pipeline legs (legacy mix scaled by
        // team count), so the 0.15 reference share reproduces the baked leg.
        const pool = TwoTier.buildPositionTiers(lists, {
          teams,
          slots: {...TwoTier.REF_SLOTS},
          flexCount: TwoTier.REF_FLEX_COUNT,
          flexEligible: [...TwoTier.REF_FLEX_ELIGIBLE],
          benchMix: TwoTier.legacyBenchMixFor(teams)
        });
        // Calibration pies are the tier SURPLUS measured from the live pool
        // (same as the pipeline legs). NOT the fixture's index_total (the
        // sum of indexed values) -- the pie's relative level across
        // positions sets the cross-position allocation, so it must match.
        const pies = {};
        TwoTier.POSITIONS.forEach(pos => {
          pies[pos] = Number(pool.tiers[pos]?.surplus);
        });
        // Slider bounds: with per-position feasible-share fallback (the
        // pipeline rule: highest feasible share <= requested), every share
        // in (0, 1) calibrates without breaking the economics, so the
        // slider offers a fixed sensible range. The old intersection logic
        // disabled the slider entirely whenever a thin position could not
        // support the 0.15 default (e.g. TE) -- that fail-closed was wrong;
        // the fallback is the correct graceful behavior, and truly
        // infeasible positions still withhold via the solver backstop.
        // The readout shows the actual per-position share used.
        const intervals = {};
        TwoTier.POSITIONS.forEach(pos => {
          const tier = pool.tiers[pos];
          const pie = pies[pos];
          intervals[pos] = tier && Number.isFinite(pie) && pie > 0
            ? TwoTier.feasibleBenchShareInterval(tier.aBench, tier.bBench, tier.aStart, tier.bStart, pie, pos)
            : null;
        });
        entry.lists = lists;
        entry.pool = pool;
        entry.pies = pies;
        entry.intervals = intervals;
        // Fixed sensible range (see comment above): 1% avoids the
        // degenerate near-zero share; 30% is already an extreme bench
        // allocation. The 0.15 default sits comfortably inside.
        entry.bounds = [0.01, 0.30];
      } catch (e) {
        entry.error = String((e && e.message) || e);
      }
      twoTierConfigCache.set(key, entry);
    }
    return entry;
  }

  function twoTierCalibration(share = benchShare) {
    const cfg = twoTierConfig();
    if (!cfg.pool) return null;
    const pies = activePies();
    const key = `${twoTierConfigKey()}@${Number(share).toFixed(6)}#${pieSignature(pies)}`;
    let cal = twoTierCalCache.get(key);
    if (!cal) {
      cal = {};
      // The slider writes one global share object; every skill position
      // reads through the shared default (per-position sliders would set
      // individual keys later).
      const shares = TwoTier.skillBenchShares(share);
      TwoTier.POSITIONS.forEach(pos => {
        // Feasible-share fallback (pipeline rule): a thin position uses
        // the highest feasible share <= requested instead of failing.
        cal[pos] = TwoTier.calibratePositionFeasible(cfg.pool.tiers[pos], pies[pos],
          TwoTier.skillBenchShare(shares, pos), pos);
      });
      if (twoTierCalCache.size > 64) twoTierCalCache.delete(twoTierCalCache.keys().next().value);
      twoTierCalCache.set(key, cal);
    }
    return cal;
  }

  // Live two-tier values: full-precision two-tier value per player at
  // the ACTIVE bench share against the frozen pool lines, times the single
  // shared 70/max(raw) scale. Rounding is display-only and never enters the
  // OLS fit below. Invalid positions contribute no targets (withheld).
  function ddfTwoTierValues() {
    const cfg = twoTierConfig();
    const cal = twoTierCalibration(benchShare);
    if (!cfg.pool || !cal) return null;
    const raw = new Map(), posOf = new Map();
    TwoTier.POSITIONS.forEach(pos => {
      const c = cal[pos];
      (cfg.lists[pos] || []).forEach(d => {
        posOf.set(d.id, pos);
        raw.set(d.id, TwoTier.priceForProjection(d.x, c));
      });
    });
    let mx = 0;
    raw.forEach(v => { if (v > mx) mx = v; });
    const scale = mx > 0 ? 70 / mx : 1;
    const values = new Map();
    raw.forEach((v, id) => values.set(id, v * scale));
    return {values, scale, posOf, starters: cfg.pool.starters, bench: cfg.pool.bench, calibration: cal};
  }

  // Per-source live two-tier values for two-tier-native sources (cbsros, razzball).
  // Same economics as ddfTwoTierValues, but the pool is the SOURCE's OWN
  // native per-game projections and the pies are the SOURCE's OWN
  // index_total targets -- never ESPN's pool. At the 0.15 reference share
  // this reproduces the source's baked leg values (pinned regression test).
  // Fail-closed: a position whose calibration is infeasible at the active
  // share contributes no values (withheld); invalidPositions names them for
  // the visible WITHHELD_FLAG readout.
  //
  // Bench mix: the LEGACY fixed mix (same as the pipeline legs), NOT the
  // dynamic benchMixFor. The legs were baked with BENCH_MIX_12 scaled by
  // teams/12; the live path must use the same mix to reproduce them at 0.15.
  function ddfTwoTierValuesForSource(sourceKey) {
    if (!["cbsros", "razzball"].includes(sourceKey)) return null;
    const native = buildNativeSourceMap(sourceKey);
    if (!native.size) return null;
    const lists = {QB: [], RB: [], WR: [], TE: []};
    native.forEach((ppg, playerKey) => {
      const player = canonicalByKey.get(playerKey);
      if (!player || !TwoTier.POSITIONS.includes(player.pos)) return;
      if (!Number.isFinite(ppg)) return;
      lists[player.pos].push({id: playerKey, x: ppg});
    });
    // Pies are the tier SURPLUS measured from the live pool (same as the
    // pipeline legs: pie = tier["surplus"]). NOT the fixture's index_total
    // (which is the sum of indexed values, a different quantity). Computed
    // after pool building below.
    // Legacy fixed bench mix, scaled by teams (matches pipeline
    // bench_mix_for_teams: round-half-up).
    const benchMix = TwoTier.legacyBenchMixFor(teams);
    let pool = null;
    try {
      pool = TwoTier.buildPositionTiers(lists, {
        teams,
        slots: {...TwoTier.REF_SLOTS},
        flexCount: TwoTier.REF_FLEX_COUNT,
        flexEligible: [...TwoTier.REF_FLEX_ELIGIBLE],
        benchMix,
      });
    } catch (e) {
      return null;
    }
    if (!pool) return null;
    const pies = {};
    TwoTier.POSITIONS.forEach(pos => {
      pies[pos] = Number(pool.tiers[pos]?.surplus);
    });
    const shares = TwoTier.skillBenchShares(benchShare);
    const cal = {}, invalidPositions = new Set();
    TwoTier.POSITIONS.forEach(pos => {
      try {
        // Feasible-share fallback (pipeline rule): a thin position uses
        // the highest feasible share <= requested instead of being
        // withheld. Only positions infeasible even at 0.01 withhold.
        const c = TwoTier.calibratePositionFeasible(pool.tiers[pos], pies[pos],
          TwoTier.skillBenchShare(shares, pos), pos);
        if (!c || c.invalid) {
          invalidPositions.add(pos);
          return;
        }
        cal[pos] = c;
      } catch (e) {
        invalidPositions.add(pos);
      }
    });
    const raw = new Map(), posOf = new Map();
    TwoTier.POSITIONS.forEach(pos => {
      if (invalidPositions.has(pos)) return; // withheld, never guessed
      const c = cal[pos];
      (lists[pos] || []).forEach(d => {
        posOf.set(d.id, pos);
        raw.set(d.id, TwoTier.priceForProjection(d.x, c));
      });
    });
    let mx = 0;
    raw.forEach(v => { if (v > mx) mx = v; });
    const scale = mx > 0 ? 70 / mx : 1;
    const values = new Map();
    raw.forEach((v, id) => values.set(id, v * scale));
    return {values, scale, posOf, starters: pool.starters, bench: pool.bench,
            calibration: cal, invalidPositions};
  }

  // Dispatch: two-tier-native sources re-price against their OWN live two-tier;
  // every other source (including the _adjusted family) targets the ESPN
  // two-tier leg, exactly as before.
  function ddfTwoTierValuesFor(sourceKey) {
    if (["cbsros", "razzball"].includes(sourceKey)) {
      return ddfTwoTierValuesForSource(sourceKey);
    }
    return ddfTwoTierValues();
  }

  // Browser-side refit of every eligible (source, position, tier) cell.
  // Independent input: the source's as-published fixture value for the
  // active scoring/teams combo. Target: the live two-tier model value --
  // the ESPN two-tier leg for the _adjusted family, each two-tier-native source's
  // OWN live two-tier for espn/cbsros/razzball (2026-10-01: the bench-share
  // slider re-prices all three two-tier-native curves).
  // OLS per cell: beta = cov(x, y) / var(x), alpha = mean(y) - beta*mean(x);
  // applied as adjusted = max(0, alpha + beta * published). A cell is
  // emitted only with >= 2 finite pairs and positive x variance; positions
  // withheld at the active share fit no cells. Recomputed whenever the
  // bench share or league config changes (cache key).
  function refitLiveCells() {
    // The roster signature is part of the key: published raw values are
    // derived per roster (league-settings-001), so cells fitted on one
    // roster's values must not be reused for another's.
    const key = `${twoTierConfigKey()}@${Number(benchShare).toFixed(6)}#${pieSignature(activePies())}|${rosterSignature()}`;
    if (liveCellsCache && liveCellsCache.key === key) return liveCellsCache.cells;
    const cells = [];
    const ddfBySource = {};
    const ddfEspn = ddfTwoTierValues();
    if (ddfEspn) {
      ["fantasycalc", "usatoday", "fantasypros", "cbs", "espn"].forEach(rawKey => {
        ddfBySource[rawKey] = ddfEspn;
      });
      ["cbsros", "razzball"].forEach(rawKey => {
        ddfBySource[rawKey] = ddfTwoTierValuesFor(rawKey);
      });
      ["fantasycalc", "usatoday", "fantasypros", "cbs", "espn", "cbsros", "razzball"].forEach(rawKey => {
        const ddf = ddfBySource[rawKey];
        if (!ddf) return;
        const published = buildPublishedSourceMap(rawKey);
        if (!published.size) return;
        TwoTier.POSITIONS.forEach(pos => {
          if (ddf.calibration[pos]?.invalid) return;
          ["starter", "bench"].forEach(tier => {
            const xs = [], ys = [];
            published.forEach((pub, playerKey) => {
              if (ddf.posOf.get(playerKey) !== pos) return;
              // Bench tier = the two-tier model's own bench partition only;
              // waiver-tier players are never adjusted.
              const inTier = tier === "starter"
                ? ddf.starters.has(playerKey)
                : ddf.bench.has(playerKey);
              if (!inTier) return;
              const y = ddf.values.get(playerKey);
              if (!Number.isFinite(pub) || !Number.isFinite(y)) return;
              xs.push(pub); ys.push(y);
            });
            if (xs.length < 2) return;
            const n = xs.length;
            const mx = xs.reduce((s, v) => s + v, 0) / n;
            const my = ys.reduce((s, v) => s + v, 0) / n;
            let sxx = 0, sxy = 0;
            for (let i = 0; i < n; i++) { sxx += (xs[i] - mx) * (xs[i] - mx); sxy += (xs[i] - mx) * (ys[i] - my); }
            if (!(sxx > 0)) return;
            const beta = sxy / sxx, alpha = my - beta * mx;
            if (!Number.isFinite(alpha) || !Number.isFinite(beta)) return;
            cells.push({source: rawKey, position: pos, tier, alpha, beta, n});
          });
        });
      });
    }
    liveCellsCache = {key, cells};
    return cells;
  }

  function tierPartitionComparison(rawKey) {
    const raw = buildPublishedSourceMap(rawKey);
    const ddf = ["cbsros", "razzball"].includes(rawKey) ? ddfTwoTierValuesFor(rawKey) : ddfTwoTierValues();
    if (!raw.size || !ddf) return {source:rawKey, compared:0, mismatches:0, byPosition:{}};
    const publishedRoles = roleMapForValues(raw);
    const byPosition = {};
    let compared = 0;
    let mismatches = 0;
    raw.forEach((value, playerKey) => {
      const player = canonicalByKey.get(playerKey);
      const pos = ddf.posOf.get(playerKey) || player?.pos;
      if (!POSITION_ORDER.includes(pos)) return;
      const ddfTier = ddf.starters.has(playerKey) ? "starter" : ddf.bench.has(playerKey) ? "bench" : null;
      const publishedTier = publishedRoles.get(playerKey) || null;
      if (!ddfTier || !publishedTier) return;
      compared += 1;
      if (!byPosition[pos]) byPosition[pos] = {compared:0, mismatches:0};
      byPosition[pos].compared += 1;
      if (ddfTier !== publishedTier) {
        mismatches += 1;
        byPosition[pos].mismatches += 1;
      }
    });
    return {source:rawKey, compared, mismatches, byPosition};
  }

  function benchSharePct(share) {
    return `${(share * 100).toFixed(1)}%`;
  }

  // Recompute slider bounds for the active config, clamp the current value
  // if a config change moved it outside the feasible interval, and refresh
  // the slider, the recommended tick, and the readout (feasible interval +
  // per-position rates, or the visible withheld flag).
  function syncBenchShareControl() {
    const block = $("#benchShareBlock");
    if (!block) return;
    const input = block.querySelector("input[type=range]");
    const valueEl = block.querySelector(".bench-share-value");
    const readout = block.querySelector(".bench-share-readout");
    const tick = block.querySelector(".bench-share-tick");
    const fill = block.querySelector(".fill");
    const resetBtn = block.querySelector(".bench-share-reset");
    const cfg = twoTierConfig();
    const failClosed = reason => {
      if (input) input.disabled = true;
      if (resetBtn) resetBtn.disabled = true;
      if (readout) readout.textContent = reason;
    };
    if (cfg.error || !cfg.bounds) {
      failClosed(cfg.error
        ? `Two-tier calibration unavailable: ${cfg.error}`
        : "The bench-share slider has no valid setting for this league setup: no bench share keeps every position's starter rate above its bench rate. No values are shown rather than wrong ones.");
      return;
    }
    let [lo, hi] = cfg.bounds;
    [lo, hi] = TwoTier.inwardBounds(lo, hi);
    if (!(hi > lo)) {
      failClosed("The bench-share slider has no valid setting for this league setup: the feasible interval is empty after rounding. No values are shown rather than wrong ones.");
      return;
    }
    if (benchShare < lo) benchShare = lo;
    if (benchShare > hi) benchShare = hi;
    if (input) {
      input.disabled = false;
      input.min = String(lo);
      input.max = String(hi);
      input.step = "0.001";
      input.value = String(benchShare);
      input.setAttribute("aria-label", `Bench share, feasible ${benchSharePct(lo)} to ${benchSharePct(hi)}, recommended 15 percent`);
    }
    if (resetBtn) {
      resetBtn.disabled = false;
      resetBtn.title = "Restore the recommended 15% bench share";
    }
    const frac = value => (value - lo) / (hi - lo);
    if (tick) tick.style.left = `calc(8px + ${frac(TwoTier.DEFAULT_BENCH_SHARE)} * (100% - 16px) - 1px)`;
    if (fill) {
      fill.style.left = "8px";
      fill.style.width = `calc(${frac(benchShare)} * (100% - 16px))`;
    }
    if (valueEl) valueEl.textContent = benchSharePct(benchShare);
    const cal = twoTierCalibration(benchShare);
    if (readout && cal) {
      const parts = TwoTier.POSITIONS.map(pos => {
        const c = cal[pos];
        if (!c || c.invalid) return `${pos} ${TwoTier.WITHHELD_FLAG}`;
        // When the feasible-share fallback engaged, show the actual share
        // used so the readout stays honest about what priced the curve.
        const usedNote = (Number.isFinite(c.bench_share_used) &&
          Math.abs(c.bench_share_used - benchShare) > 1e-9)
          ? ` @ ${benchSharePct(c.bench_share_used)} share`
          : "";
        return `${pos} starter ${c.ps.toFixed(2)} > bench ${c.pb.toFixed(2)}${usedNote}`;
      });
      readout.textContent = `Feasible ${benchSharePct(lo)}–${benchSharePct(hi)} · recommended 15%. ` + parts.join(" · ");
      readout.title = "Per-position marginal rates: each point above the starter line pays the starter rate; points between the waiver and starter lines pay the bench rate.";
    }
    refitLiveCells();
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
    TwoTier.POSITIONS.forEach(pos => {
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
    const raw = TwoTier.POSITIONS.map(pos => Math.max(0, Number(weights?.[pos]) || 0));
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
    TwoTier.POSITIONS.forEach((pos, idx) => {
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
    const parts = TwoTier.POSITIONS.map((pos, idx) => {
      const pct = (shown[idx] / 10).toFixed(1);
      const b = shownBaked ? ` (default ${(shownBaked[idx] / 10).toFixed(1)}%)` : "";
      return `${pos} ${pct}%${b}`;
    });
    const benchPct = (benchShare * 100).toFixed(1);
    readout.textContent = `Pie: ${parts.join(" · ")} — sums to 100%. Bench ${benchPct}% (default 15%). Values above recalibrate live from ESPN projections.`;
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
      input.min = key === "BENCH" ? "0" : "1";
      input.max = key === "BENCH" ? "14" : "5";
      input.step = "1";
      input.value = rosterShape[key];
      input.dataset.rosterKey = key;
      input.setAttribute("aria-label", `${label} roster spots`);
      input.addEventListener("change", () => setRosterSpot(key, input.value));
      wrapper.append(text, input);
      grid.appendChild(wrapper);
    });
    // Bench share: one global bounded slider (not a free input). It writes the
    // same share to all skill positions (each falls back to the shared
    // default); K/DST are excluded. Bounds are the maximal feasible interval
    // containing 0.15 where every position solves with starter rate above
    // bench rate, rounded inward; the tick marks the recommended 15%.
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
    shareReset.textContent = "Reset to 15%";
    shareReset.addEventListener("click", () => setBenchShareFraction(TwoTier.DEFAULT_BENCH_SHARE));
    shareHead.append(shareTitle, shareValue, shareReset);
    const slider = document.createElement("div");
    slider.className = "zslider bench-share-slider";
    const track = document.createElement("div");
    track.className = "track";
    const tick = document.createElement("div");
    tick.className = "bench-share-tick";
    tick.title = "Recommended 15% bench share";
    const fill = document.createElement("div");
    fill.className = "fill";
    const shareInput = document.createElement("input");
    shareInput.type = "range";
    shareInput.step = "0.001";
    shareInput.value = String(benchShare);
    shareInput.setAttribute("aria-label", "Bench share");
    shareInput.addEventListener("input", () => setBenchShareFraction(Number(shareInput.value), false));
    shareInput.addEventListener("change", () => { setBenchShareFraction(Number(shareInput.value), false); publishShared(); });
    shareInput.addEventListener("dblclick", () => setBenchShareFraction(TwoTier.DEFAULT_BENCH_SHARE));
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

  function adjustmentWeightRows() {
    return ADJUSTED_INDEXED_KEYS.flatMap(key => {
      const rawKey = rawKeyForAdjusted(key);
      const cells = adjustmentCellsFor(rawKey) || [];
      return cells.map(cell => ({
        key,
        rawKey,
        source: sourceLabel(key),
        position: String(cell.position || "").toUpperCase(),
        tier: String(cell.tier || "").toLowerCase(),
        alpha: Number(cell.alpha),
        beta: Number(cell.beta),
        n: Number(cell.n),
        xMean: Number(cell.x_mean),
        yMean: Number(cell.y_mean)
      })).filter(row => POSITION_ORDER.includes(row.position) &&
        ["starter", "bench"].includes(row.tier) &&
        Number.isFinite(row.alpha) && Number.isFinite(row.beta));
    }).sort((a, b) => (
      ADJUSTED_INDEXED_KEYS.indexOf(a.key) - ADJUSTED_INDEXED_KEYS.indexOf(b.key) ||
      POSITION_ORDER.indexOf(a.position) - POSITION_ORDER.indexOf(b.position) ||
      (a.tier === b.tier ? 0 : a.tier === "starter" ? -1 : 1)
    ));
  }

  function adjustmentAllocationRows() {
    const counts = allocationCountsFor([...canonicalByKey.values()], rosterShape);
    return POSITION_ORDER.map(pos => {
      const direct = counts.direct[pos] || 0;
      const lineup = counts.lineup[pos] || 0;
      const rostered = counts.rostered[pos] || 0;
      return {
        pos,
        direct,
        flex: Math.max(0, lineup - direct),
        bench: Math.max(0, rostered - lineup),
        lineup,
        rostered
      };
    });
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
    if (!container || !canonicalByKey.size) return;
    container.replaceChildren();

    const meta = document.createElement("p");
    meta.className = "adjustment-note";
    meta.textContent = `${scoreLabel()} · ${teams} teams · current flex and bench assignment from ESPN projections`;
    container.appendChild(meta);

    const allocWrap = document.createElement("div");
    allocWrap.className = "adjustment-table-wrap allocation-table-wrap";
    const allocTable = document.createElement("table");
    const allocHead = document.createElement("thead");
    const allocHeadRow = document.createElement("tr");
    ["Pos", "Dedicated", "Flex", "Bench", "Rostered"].forEach(label => appendCell(allocHeadRow, "th", label));
    allocHead.appendChild(allocHeadRow);
    const allocBody = document.createElement("tbody");
    adjustmentAllocationRows().forEach(row => {
      const tr = document.createElement("tr");
      appendCell(tr, "td", row.pos);
      appendCell(tr, "td", String(row.direct));
      appendCell(tr, "td", String(row.flex), row.flex > 0 ? "is-flex-hit" : "");
      appendCell(tr, "td", String(row.bench));
      appendCell(tr, "td", String(row.rostered));
      allocBody.appendChild(tr);
    });
    allocTable.append(allocHead, allocBody);
    allocWrap.appendChild(allocTable);
    container.appendChild(allocWrap);

    const rows = adjustmentWeightRows();
    const byKey = new Map(ADJUSTED_INDEXED_KEYS.map(key => [key, rows.filter(row => row.key === key)]));
    const cards = document.createElement("div");
    cards.className = "adjustment-card-grid";
    ADJUSTED_INDEXED_KEYS.forEach(key => {
      const card = document.createElement("section");
      card.className = "adjustment-card";
      const title = document.createElement("h3");
      title.textContent = sourceLabel(key);
      card.appendChild(title);
      const sourceRows = byKey.get(key) || [];
      if (!sourceRows.length) {
        const empty = document.createElement("p");
        empty.className = "adjustment-empty";
        empty.textContent = isAdjustedCurvePaused(key)
          ? "Paused until live adjustment cells are present."
          : "No live adjustment cells in the current artifact.";
        card.appendChild(empty);
      } else {
        const tableWrap = document.createElement("div");
        tableWrap.className = "adjustment-table-wrap";
        const table = document.createElement("table");
        const thead = document.createElement("thead");
        const headRow = document.createElement("tr");
        ["Pos", "Tier", "Intercept", "Multiplier", "Pairs", "Mean shift"].forEach(label => appendCell(headRow, "th", label));
        thead.appendChild(headRow);
        const tbody = document.createElement("tbody");
        sourceRows.forEach(row => {
          const tr = document.createElement("tr");
          appendCell(tr, "td", row.position);
          appendCell(tr, "td", row.tier);
          appendCell(tr, "td", formatTwo(row.alpha));
          appendCell(tr, "td", formatTwo(row.beta));
          appendCell(tr, "td", Number.isFinite(row.n) ? String(row.n) : "—");
          appendCell(tr, "td", `${formatOne(row.xMean)} → ${formatOne(row.yMean)}`);
          tbody.appendChild(tr);
        });
        table.append(thead, tbody);
        tableWrap.appendChild(table);
        card.appendChild(tableWrap);
      }
      cards.appendChild(card);
    });
    container.appendChild(cards);
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
      // Fixture-transition Option B: a paused adjusted curve stays listed
      // but greyed out until stage-2 adjustment cells land for its source.
      const paused = isAdjustedCurvePaused(key);
      const available = hasData && sourceComboExists(key) && !paused;
      input.checked = activeSources.has(key) && available;
      input.disabled = !available;
      input.dataset.source = key;
      input.setAttribute("aria-label", `Show ${sourceLabel(key)} curve`);
      if (key.startsWith("fantasycalc")) label.title = "FantasyCalc publisher basis: 1 QB";
      label.classList.toggle("is-stale", staleWeek && available);
      if (paused) {
        label.classList.add("is-disabled");
        label.title = `${sourceLabel(key)} is paused while it waits on fresh adjustment inputs. It will return automatically once they land.`;
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
      if (paused) {
        const meta = document.createElement("span");
        meta.className = "src-meta";
        meta.textContent = "paused · waiting on fresh adjustment inputs";
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
    note.textContent = [...SOURCE_KEYS, ...EXTRA_SOURCE_KEYS, ...PURE_VORP_KEYS].includes(lockOrder)
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
    const pausedKeys = ADJUSTED_INDEXED_KEYS.filter(isAdjustedCurvePaused);
    const defaultKeys = new Set(defaultIndexedSourceKeys(adjustmentInputs, firstLoadExcluded));
    const defaultAvailableAdjustedKeys = ADJUSTED_INDEXED_KEYS.filter(key => (
      defaultKeys.has(key) && sourceAvailable(key) && !isAdjustedCurvePaused(key)
    ));
    // JEG-432 R5: adjusted curves left off because their chart is a week
    // behind the newest one on the board.
    const olderWeekKeys = ADJUSTED_INDEXED_KEYS.filter(key => firstLoadExcluded.has(key) && sourceAvailable(key) && !isAdjustedCurvePaused(key));
    const olderWeekNote = olderWeekKeys.length
      ? ` ${olderWeekKeys.map(sourceLabel).join(", ")} ${olderWeekKeys.length === 1 ? "is" : "are"} from an older week and start${olderWeekKeys.length === 1 ? "s" : ""} off; turn ${olderWeekKeys.length === 1 ? "it" : "them"} on below.`
      : "";
    let adjustedStatus;
    if (pausedKeys.length) {
      adjustedStatus = `ESPN adjusted is shown by default. ${pausedKeys.length} adjusted source projections are paused while they wait on fresh adjustment inputs.`;
    } else if (defaultAvailableAdjustedKeys.length) {
      const liveCount = defaultAvailableAdjustedKeys.length === ADJUSTED_INDEXED_KEYS.length ? "four" : String(defaultAvailableAdjustedKeys.length);
      const projectionNoun = defaultAvailableAdjustedKeys.length === 1 ? "projection is" : "projections are";
      adjustedStatus = `ESPN live plus ${liveCount} adjusted source ${projectionNoun} shown by default.${olderWeekNote}`;
    } else if (olderWeekKeys.length) {
      adjustedStatus = `ESPN live is shown by default.${olderWeekNote}`;
    } else {
      adjustedStatus = "ESPN live is shown by default. Adjusted source projections are live for supported league setups, but this setup has no matching source combo.";
    }
    status.innerHTML = `<strong>Validated:</strong> ${adjustedStatus} Direct published charts are available but off by default. Raw ESPN VORP vs waivers can be enabled on the same chart.`;
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
    note.innerHTML = `<b>Note:</b> Player lock order was reset from "${prevLabel}" to "ESPN adjusted" (${reason} made "${prevLabel}" unavailable).`;
    // Remove any existing notice first
    status.querySelectorAll(".lock-revert-notice").forEach(n => n.remove());
    status.appendChild(note);
    // Auto-dismiss after 8 seconds
    setTimeout(() => note.remove(), 8000);
  }

  function publishShared() {
    const detail = {scoring, teams, position, model: "monday", lockOrder, rosterShape:{...rosterShape}, benchShare, absenceRate:benchShare, positionWeights: activePositionWeights()};
    window.TradeValueSharedState = detail;
    window.dispatchEvent(new CustomEvent("trade-value-shared-change", {detail}));
  }

  // Bench share is the two-tier calibration parameter: one global bounded
  // slider writing the same share to all skill positions (K/DST excluded).
  // The slider cannot leave the feasible interval, so the per-position
  // fail-closed guard in the solver stays as a backstop (defense in depth).
  // Displayed fallback curves are frozen at DISPLAY_BENCH_SHARE, so moving
  // the slider only reruns the live calibration and its readout.
  function setBenchShareFraction(share, publish = true) {
    const cfg = twoTierConfig();
    const bounds = cfg.bounds;
    let next = Number(share);
    if (!Number.isFinite(next) || !bounds) {
      syncBenchShareControl();
      return;
    }
    const [lo, hi] = TwoTier.inwardBounds(bounds[0], bounds[1]);
    next = Math.min(hi, Math.max(lo, next));
    if (Math.abs(next - benchShare) < 1e-9) {
      syncBenchShareControl();
      return;
    }
    benchShare = next;
    crossRank = null;
    syncBenchShareControl();
    // JEG-103: the slider's input/change/dblclick handlers used to call this
    // function without syncWeightsReadout(), so the Weights panel kept the
    // old "Bench 15.0% (default 15%)" label even after the slider moved.
    // Syncing from the central setter covers every path (slider, dblclick
    // reset, the "Reset to 15%" button, resetAllWeights, external callers).
    syncWeightsReadout();
    if (publish) publishShared();
  }

  // Backward-compatible entry: the retired free input passed an integer
  // percent; external callers may still do so.
  function setBenchShare(raw, publish = true) {
    setBenchShareFraction(Number(raw) / 100, publish);
  }

  function setRosterSpot(key, raw, publish = true) {
    if (!Object.prototype.hasOwnProperty.call(rosterShape, key)) return;
    const min = key === "BENCH" ? 0 : 1;
    const max = key === "BENCH" ? 14 : 5;
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
    if (!["disagreement"].includes(lockOrder) && !(sourceAvailable(lockOrder) && !isAdjustedCurvePaused(lockOrder))) {
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
    if (!["disagreement"].includes(lockOrder) && !(sourceAvailable(lockOrder) && !isAdjustedCurvePaused(lockOrder))) {
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

  window.TradeValueCurveControls = {
    setPosition,
    setScoring,
    setTeams,
    setBenchShare,
    setAbsenceRate: setBenchShare,
    setLockOrder,
    setModel: () => {},
    redraw: () => draw(),
    getState: () => ({position, scoring, teams, model: "monday", valueMode:"indexed", lockOrder, benchShare, absenceRate:benchShare, activeSources:activeSourceKeys()}),
    getLockedDomain: () => displayRows().map((row, index) => ({rank:index + 1, player_key:row.player_key, name:row.name})),
    getPlayerValues: query => {
      const needle = String(query || "").trim().toLowerCase();
      if (!needle) return [];
      return universe.filter(row => row.name.toLowerCase().includes(needle)).slice(0, 8).map(row => ({
        player_key: row.player_key,
        name: row.name,
        team: row.team,
        pos: row.pos,
        espnRole: row.espnRole,
        values: Object.fromEntries(visibleSourceKeys().map(key => [key, row.values[key] ?? null]))
      }));
    },
    // v2 front end (read-only): the ranked rows and source metadata the new
    // layout renders, straight from the same maps this chart draws.
    getRows: () => displayRows().map(row => ({...row, values: {...row.values}})),
    // Every priced player at every position (Compare a trade), ignoring the
    // position filter; the same value maps getRows reads.
    getAllRows: () => universe.map(row => ({...row, values: {...row.values}})),
    getRankSource: () => selectedRankSourceKey(),
    getActiveSources: () => activeSourceKeys(),
    getReferenceWeek: () => activeReferenceWeek(),
    getRosterShape: () => ({...rosterShape}),
    setRosterSpot,
    setBenchShareFraction,
    getBenchShare: () => benchShare,
    getBenchBounds: () => {
      const bounds = twoTierConfig().bounds;
      return bounds ? TwoTier.inwardBounds(bounds[0], bounds[1]) : null;
    },
    getPositionWeights: () => activePositionWeights(),
    getSourceInfo: () => visibleSourceKeys().map(key => ({
      key,
      label: sourceLabel(key),
      week: weekForSource(key),
      stale: sourceIsStale(key),
      available: sourceAvailable(key) && !isAdjustedCurvePaused(key),
      paused: isAdjustedCurvePaused(key),
      active: activeSources.has(key),
      color: SOURCE_STYLES[key]?.color || null,
      // V2-WAIVER-COVERAGE: set when this chart's values rest on a waiver
      // line extrapolated from the other charts (or on the end of its list).
      waiverNote: waiverNote(key),
      waiver: publishedWaiver(key)
    })),
    getAdjustmentWeights: () => ({allocation: adjustmentAllocationRows(), cells: adjustmentWeightRows()}),
    getZones: () => Object.fromEntries(boundaryMarkers().map(marker => [marker.key, marker.value]))
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

  function allocationCounts() {
    return allocationCountsFor(universe);
  }

  // Each boundary sits at the cutoff for the LAST player of its division
  // (2026-09-19, user directive): Starter = last startable player
  // (dedicated starters + flex share), Bench = last benchable player
  // (last rostered), Waiver = last waiver player shown on the chart.
  function rosterOrdinals() {
    const counts = allocationCounts();
    if (position === "ALL") return {
      starter: teams * (rosterShape.QB + rosterShape.RB + rosterShape.WR + rosterShape.TE + rosterShape.FLEX),
      bench: teams * (rosterShape.QB + rosterShape.RB + rosterShape.WR + rosterShape.TE + rosterShape.FLEX + rosterShape.BENCH)
    };
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

  // Checks the SHARED-set invariant, which is the one that decides whether two
  // curves are comparable: over the players a source and the anchor both
  // price, their totals must agree. The old check compared every source's
  // FULL total to one number, which a source passes no matter how far its
  // level drifts from the anchor's on the players they share.
  function fixedPieDiagnostics(sourceMapsForCheck = sourceMaps) {
    const tolerance = 2;
    const anchor = sourceMapsForCheck.get("espn");
    const checks = [];
    visibleSourceKeys().filter(sourceAvailable).forEach(key => {
      const values = sourceMapsForCheck.get(key);
      if (!values) return;
      // As-published sources are indexed by the pipeline via
      // proportional_scaling_vorp_overlap, which calibrates on the VORP>0
      // overlap set (not the full shared set). The browser does not re-scale
      // them, so this shared-total check does not apply. The pipeline's
      // fixed-pie invariant (overlap total = anchor overlap total) is verified
      // by pipeline tests, not by this client-side guard.
      if (AS_PUBLISHED_KEYS.has(key)) {
        checks.push({source:key, basis:"pipeline", shared:null, total:null, target:null, delta:null, ok:true});
        return;
      }
      if (key === "espn") {
        // The anchor is now priced per position against its own pie, so its
        // total is the SUM of the positional targets -- not the single common
        // pie figure. Checking it against the common total failed the guard
        // in every league config and blanked the chart.
        const pieSum = POSITION_ORDER.reduce((sum, pos) => {
          const t = Number(espnTargetTotal(pos, NaN));
          return sum + (Number.isFinite(t) && t > 0 ? t : 0);
        }, 0) || commonFixedPieTotal(0);
        const entries = [...values.entries()]
          .filter(([playerKey]) => POSITION_ORDER.includes(canonicalByKey.get(playerKey)?.pos));
        const total = entries
          .reduce((sum, [, value]) => sum + (Number.isFinite(value) ? value : 0), 0);
        // Scale-aware (2026-10-01): unscale the display-scaled anchor total
        // before comparing against the raw pie; see anchorScaleCorrectedCheck.
        const ddf = ddfTwoTierValues();
        const displayScale = ddf?.scale || 1;
        const check = anchorScaleCorrectedCheck(total, pieSum, displayScale, tolerance);
        // Deep diagnostics (2026-10-01): player count, live-cell usage, and
        // per-position totals to diagnose the -79.90 mismatch.
        const liveCells = liveCellsForSource("espn");
        const bakedCells = adjustmentCellsFor("espn");
        const perPos = {};
        POSITION_ORDER.forEach(pos => {
          const posTotal = entries
            .filter(([playerKey]) => canonicalByKey.get(playerKey)?.pos === pos)
            .reduce((sum, [, value]) => sum + (Number.isFinite(value) ? value : 0), 0);
          const posPie = Number(espnTargetTotal(pos, NaN)) || 0;
          perPos[pos] = {total: Number((posTotal / displayScale).toFixed(2)), pie: Number(posPie.toFixed(2)), n: entries.filter(([playerKey]) => canonicalByKey.get(playerKey)?.pos === pos).length};
        });
        checks.push({source:key, basis:"anchor", shared:null, total:check.total, target:check.target, delta:check.delta,
                     ok:check.ok, n:entries.length, rawTotal:Number(total.toFixed(2)), displayScale:Number(displayScale.toFixed(4)),
                     scaleIsNull:!ddf, liveCells:liveCells ? liveCells.length : 0, bakedCells:bakedCells ? bakedCells.length : 0,
                     perPos});
        return;
      }
      let sharedTotal = 0, sharedTarget = 0, shared = 0, fullTotal = 0;
      values.forEach((value, playerKey) => {
        if (!POSITION_ORDER.includes(canonicalByKey.get(playerKey)?.pos)) return;
        if (Number.isFinite(value)) fullTotal += value;
        const anchorValue = anchor?.get(playerKey);
        if (!Number.isFinite(anchorValue) || !Number.isFinite(value)) return;
        sharedTotal += value; sharedTarget += Math.max(0, anchorValue); shared += 1;
      });
      // Below MIN_SHARED_FOR_PIE the normalisation deliberately falls back to
      // the common pie rather than inventing a scale from a handful of
      // players. The diagnostic MUST check whichever basis was actually used:
      // demanding the shared basis regardless marked the fallback as failed,
      // which threw the regression guard and left "Curves unavailable" on the
      // live page for any league config with a thin overlap.
      const usedShared = shared >= MIN_SHARED_FOR_PIE && sharedTarget > 0;
      const total = usedShared ? sharedTotal : fullTotal;
      const target = usedShared ? sharedTarget : commonFixedPieTotal(fullTotal);
      checks.push({source:key, basis:usedShared ? "shared" : "fallback", shared, total, target,
                   delta:total - target, ok:Math.abs(total - target) <= tolerance});
    });
    return {tolerance, checks, ok:checks.every(check => check.ok)};
  }

  // Cross-source scale agreement. The band and the comparison live in the
  // shared value model so they can be tested against the numbers the defect
  // actually produced; this only supplies the peaks.
  //
  // Scope is the DIRECT published charts. The *_adjusted series are
  // deliberately re-weighted away from their source and the raw
  // value-above-waivers series is deliberately un-adjusted, so neither is
  // evidence about the anchor's shape.
  const DIRECT_CHART_KEYS = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
  // The adjusted series are deliberately re-weighted, so they get a wider
  // band and a warning rather than a failure. They still need to stay on one
  // readable trade-value scale with the ESPN anchor.
  const ADJUSTED_CHART_KEYS = ["fantasycalc_adjusted", "usatoday_adjusted",
                               "fantasypros_adjusted", "cbs_adjusted"];
  const ADJUSTED_AGREEMENT_LOW = 0.6;
  const ADJUSTED_AGREEMENT_HIGH = 1.4;

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

  function agreementFor(keys, low, high) {
    const sources = {};
    keys.filter(key => sourceMaps.get(key)?.size)
      .forEach(key => { sources[key] = positionalPeaks(indexedMapForAgreement(key)); });
    return ValueModel.peakAgreement({
      anchorPeaks: positionalPeaks(sourceMaps.get("espn")),
      sources, low, high, labelOf: sourceLabel
    });
  }

  // JEG-210: the anchor-band health checks validate indexed (published) values.
  // In a non-indexed view the as-published maps carry VORP/adjusted units, which
  // would false-fail the 0.8-1.25x anchor band; read the indexed builder instead.
  // The ESPN anchor never switches views, so it always reads the live map.
  // Re-restored 2026-10-04 (dropped by the JEG-325 refactor).
  function indexedMapForAgreement(key) {
    if (viewMode === "indexed" || !AS_PUBLISHED_KEYS.has(key)) return sourceMaps.get(key);
    return buildPublishedSourceMap(key);
  }

  function scaleAgreementDiagnostics() {
    return agreementFor(DIRECT_CHART_KEYS);
  }

  function adjustedAgreementDiagnostics() {
    return agreementFor(ADJUSTED_CHART_KEYS, ADJUSTED_AGREEMENT_LOW, ADJUSTED_AGREEMENT_HIGH);
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
    const head = `<tr><th>Rank</th><th>Player</th><th>ESPN tier</th>${keys.map(key => `<th>${sourceLabel(key)}</th>`).join("")}</tr>`;
    const body = rows.map(row => {
      const rank = displayRows().findIndex(candidate => candidate.player_key === row.player_key) + 1;
      return `<tr><td>${rank}</td><td><strong>${row.name}</strong><span>${row.pos} · ${row.team}</span></td><td>${row.espnRole}</td>${keys.map(key => `<td>${formatScore(row.values[key])}</td>`).join("")}</tr>`;
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
    // JEG-291: even on Indexed, the X/Y split is the anchor's MEASURED share
    // (lastDisplayShare, set at rebuild time), not the recommended 15% bench
    // share (DISPLAY_BENCH_SHARE) the subtitle slider shows.
    // JEG-225: compare via VIEW_MODE_ORDER — the "vorp" string literal may
    // only appear in the VIEW_MODE_ORDER declaration, never in code or copy.
    // Re-restored 2026-10-04 (dropped by the JEG-325 refactor).
    const footnoteMiddle = viewMode === VIEW_MODE_ORDER[1]
      ? "raw VORP vs waivers curves from each source's own per-game projections — same shared total as Indexed, no fixed-pie re-tiering"
      : viewMode === "adj"
      ? "adjusted curves under the shared 0–70 weighting model, with our position weighting applied"
      : `indexed charts are put on the ESPN leg’s pie and matched to its ${Math.round((1 - lastDisplayShare) * 100)}% starter / ${Math.round(lastDisplayShare * 100)}% measured split, waiver to 0`;
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
    return `<strong>${rank}. ${row.name}</strong>${zeroBadge}<span class="tip-meta">${row.pos} · ${row.team} · ESPN ${row.espnRole} · ${rankLabel}</span><span class="tip-grid">${values}</span>`;
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
    const scaleAgreement = scaleAgreementDiagnostics();
    const adjustedAgreement = adjustedAgreementDiagnostics();
    // JEG-30: record the fixed-pie guard in Chart Health with its structured
    // per-source diagnostics. The detail view renders on failure; the happy
    // path stays clean. The thrown error below keeps a plain-words summary.
    ChartHealth.record(
      "fixed-pie-indexed",
      "Curves hold their indexed scale",
      fixedPie.ok,
      fixedPie.ok
        ? `${fixedPie.checks.length} sources within ±${fixedPie.tolerance} of target`
        : `${fixedPie.checks.filter(c => !c.ok).length} source(s) outside ±${fixedPie.tolerance} of target — see diagnostics`,
      fixedPie
    );
    // Visible, not blocking: these curves are on by default, so a scale
    // problem in them has to be on the page rather than in a backlog only.
    if (adjustedAgreement.compared > 0 && !adjustedAgreement.ok) {
      ChartHealth.warn(
        "adjusted-scale-agreement",
        "Adjusted series agree with the anchor's scale",
        `positional peaks outside ${adjustedAgreement.band.join("-")}x of the anchor: ` +
        `${adjustedAgreement.offenders.join("; ")} -- open issue in the stage-2 adjustment cells`
      );
    } else {
      ChartHealth.record(
        "adjusted-scale-agreement",
        "Adjusted series agree with the anchor's scale",
        adjustedAgreement.ok,
        `${adjustedAgreement.compared} positional peaks within ${adjustedAgreement.band.join("-")}x of the anchor`
      );
    }
    // Visible, not failing: a direct-series scale disagreement is genuine
    // publisher shape disagreement -- the pipeline's scale-agreement monitor
    // verdicts fantasycalc/usatoday "genuine disagreement" (their published
    // shapes sit outside the band before any indexation) -- so it surfaces as
    // a warning like the adjusted family, never a red "numbers are wrong"
    // FAIL. The 0.8-1.25x band itself is unchanged.
    // Re-restored 2026-10-04 (dropped by the JEG-325 refactor).
    if (scaleAgreement.compared > 0 && !scaleAgreement.ok) {
      ChartHealth.warn(
        "source-scale-agreement",
        "Published charts agree with the anchor's scale",
        `positional peaks outside ${scaleAgreement.band.join("-")}x of the anchor: ` +
        `${scaleAgreement.offenders.join("; ")} -- genuine publisher shape disagreement, see scale-agreement monitor`
      );
    } else {
      ChartHealth.record(
        "source-scale-agreement",
        "Published charts agree with the anchor's scale",
        scaleAgreement.ok,
        `${scaleAgreement.compared} positional peaks within ${scaleAgreement.band.join("-")}x of the anchor`
      );
    }
    // JEG-392: in the Value-above-waivers / Adjusted views setViewMode()
    // deliberately swaps activeSources to the as-published view set and
    // parks the Indexed selection in savedActiveSourcesForView. Checking the
    // swapped set made every scoring/teams change in those views throw here
    // (before draw()), freezing the chart. Guard the Indexed selection the
    // user will return to instead -- same regression power, right set.
    const indexedSelection = viewMode === "indexed"
      ? activeSources : (savedActiveSourcesForView || activeSources);
    const defaultGroupedSources = defaultCurvesSatisfied(adjustmentInputs, indexedSelection, userDeselectedSources, firstLoadExcluded);
    const pureVorpAvailable = PURE_VORP_KEYS.some(key => sourceMaps.get(key)?.size > 0);
    const adjustableBenchShare = DEFAULT_BENCH_SHARE === 0.15 && Number.isFinite(benchShare) && typeof setBenchShare === "function";
    const tieredEspnValues = ["starter", "bench", "waiver"].every(role => [...espnRoleByKey.values()].includes(role));
    const diagnostics = {sourceMapCoverage, sourceToggles, noAggregate, stableDomain, validValues, distinctSourcePeaks, valuesAboveCollapseFloor, curveCollapseFloor:CURVE_COLLAPSE_FLOOR, dynamicAxisCoversData, sharedPlayerAxis, sourcePeaks, yAxisMax:scale.max, rosterTransitions, rosterMarkerAxis:"x", fixedPieIndexed:fixedPie.ok, fixedPie, sourceScaleAgreement:scaleAgreement.ok, scaleAgreement, adjustedAgreement, defaultGroupedSources, pureVorpAvailable, adjustableBenchShare, tieredEspnValues, valueMode:"indexed", viewMode, publishedView:JSON.parse(JSON.stringify(lastPublishedView)), lockOrder, rankSource:selectedRankSourceKey(), sourceCount:SOURCE_KEYS.length, activeCount:activeSourceKeys().length, curveCount:activeSourceKeys().length, firstLoadExcluded:[...firstLoadExcluded], adjustmentInputsVersion:adjustmentInputs?.version || null, savedSetup:onSavedSetup(), publishedDerivation:JSON.parse(JSON.stringify(lastPublishedDerivation)), adjustmentWeightRows:adjustmentWeightRows().length, adjustmentAllocation:adjustmentAllocationRows(), liveAdjustedSources:["fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted", "cbs_adjusted"].filter(key => adjustmentCellsFor(rawKeyForAdjusted(key)) !== null)};
    window.TradeValueCurveDiagnostics = Object.freeze(diagnostics);
    // sourceScaleAgreement is NOT blocking: genuine inter-source disagreements
    // (e.g., USA Today QB 0.51x of ESPN anchor) are surfaced via ChartHealth
    // as a warning, but must not blank the entire chart. The chart renders
    // with a visible disagreement notice instead.
    const failed = Object.entries(diagnostics).filter(([key, value]) => ["sourceMapCoverage", "sourceToggles", "noAggregate", "stableDomain", "validValues", "distinctSourcePeaks", "valuesAboveCollapseFloor", "dynamicAxisCoversData", "sharedPlayerAxis", "rosterTransitions", "fixedPieIndexed"].includes(key) && value !== true);
    // JEG-30: the per-source numbers live in the Chart Health detail view
    // (recorded above), not in the error string. The thrown error keeps a
    // plain-words summary; open Chart Health for the per-source breakdown.
    if (failed.length || !defaultGroupedSources || !pureVorpAvailable || !adjustableBenchShare || !tieredEspnValues) throw new Error(`Curve regression guard failed: ${failed.map(([key]) => key).concat(defaultGroupedSources ? [] : ["defaultGroupedSources"], pureVorpAvailable ? [] : ["pureVorpAvailable"], adjustableBenchShare ? [] : ["adjustableBenchShare"], tieredEspnValues ? [] : ["tieredEspnValues"]).join(", ")}. See Chart Health for per-source diagnostics.`);
    guardsPassed = true;
  }

  // JEG-210: view mode switching (restored 2026-10-03, wired to vorp_views).
  // Re-restored 2026-10-04 (dropped by the JEG-325 refactor).
  // The vorp/adj views only exist for the as-published sources with baked
  // vorp_views. Entering a non-indexed view activates those sources so the
  // tab visibly changes the chart (the default indexed selection is the
  // *_adjusted family, which carries no vorp views); returning to Indexed
  // restores the user's prior source selection.
  function setViewMode(mode, publish = true) {
    if (!VIEW_MODE_DEFS[mode]) mode = "indexed";
    viewMode = mode;
    const tabs = document.querySelectorAll("#viewModeTabs [data-view-mode]");
    tabs.forEach(tab => {
      const selected = tab.dataset.viewMode === mode;
      tab.setAttribute("aria-selected", selected ? "true" : "false");
    });
    if (mode === "indexed") {
      if (savedActiveSourcesForView) {
        activeSources = savedActiveSourcesForView;
        savedActiveSourcesForView = null;
        userDeselectedSources = new Set();
      }
    } else {
      if (!savedActiveSourcesForView) savedActiveSourcesForView = new Set(activeSources);
      const viewKeys = [...AS_PUBLISHED_KEYS].filter(key => sourceHasVorpView(key));
      if (viewKeys.length) {
        activeSources = new Set(viewKeys);
        userDeselectedSources = new Set();
      }
    }
    // Rebuild source maps with the new view's values, then redraw.
    rebuildDomain();
    makeSourceToggles();
    // JEG332-VORP-VIEWS: re-run the guards (and refresh the diagnostics) for
    // the view just entered, as every other control does. Skipped during
    // init, before the first guard run, when the toggles do not exist yet.
    if (guardsPassed) runRegressionGuards();
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
      adjustmentInputs = await loadAdjustmentInputs();
      // Fresh-load default: ESPN adjusted plus every *_adjusted curve with
      // live stage-2 cells (fixture-transition Option B auto-return). The
      // banner's "shown by default" copy is only true when this matches it.
      // JEG-432 R5: weekly charts older than the newest week on the board
      // start switched off (the reader can still turn them on).
      const freshness = window.TradeValueProductData?.getSourceFreshness?.() || null;
      firstLoadExcluded = new Set(freshness?.first_load_excluded || []);
      activeSources = new Set(defaultIndexedSourceKeys(adjustmentInputs, firstLoadExcluded));
      userDeselectedSources = new Set();
      canonicalByKey = buildCanonicalMap();
      if (!canonicalByKey.size) throw new Error("Canonical player records are unavailable.");
      const invalid = SOURCE_KEYS.filter(key => sourceValidationStatus(key) !== "live");
      if (invalid.length) throw new Error("One or more required comparison sources did not pass validation.");
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
      window.TradeValueTwoTierLive = {
        configKey: twoTierConfigKey,
        bounds: () => twoTierConfig().bounds,
        intervals: () => twoTierConfig().intervals,
        calibration: share => twoTierCalibration(share),
        benchShares: () => TwoTier.skillBenchShares(benchShare),
        ddfValues: ddfTwoTierValues,
        ddfValuesFor: ddfTwoTierValuesFor,
        liveCells: refitLiveCells,
        setBenchShareFraction,
        positionWeights: activePositionWeights,
        setPositionWeight,
        resetPositionWeights,
        resetAllWeights
      };
      window.TradeValueCurveHarness = {
        fixedPieDiagnostics,
        fixedPieDiagnosticsForMap: (sourceKey, values) => {
          const maps = new Map(sourceMaps);
          maps.set(sourceKey, applyRosterShape(values, sourceKey));
          return fixedPieDiagnostics(maps);
        },
        buildLiveAdjustedMap,
        refitLiveCells,
        espnTargetTotal,
        ddfTwoTierValues,
        anchorScaleCorrectedCheck,
        tierPartitionComparison,
        sourceMaps: () => new Map(sourceMaps),
        state: () => ({scoring, teams, benchShare, sourceCount:SOURCE_KEYS.length, activeCount:activeSourceKeys().length})
      };
    } catch (error) {
      $("#curve-status").innerHTML = `<strong>Curves unavailable:</strong> ${String(error.message)}`;
      console.error(error);
    }
  }

  init();
})();
