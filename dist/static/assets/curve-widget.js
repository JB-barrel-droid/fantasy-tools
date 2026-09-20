(() => {
  "use strict";

  const POSITIONS = ["ALL", "QB", "RB", "WR", "TE", "FLEX", "K", "DST"];
  const SCORINGS = [["standard", "Standard"], ["half_ppr", "Half PPR"], ["ppr", "Full PPR"]];
  const SOURCE_LABELS = {
    usatoday: "USA Today",
    fantasycalc: "FantasyCalc",
    fantasypros: "FantasyPros",
    cbs: "CBS",
    espn: "ESPN live",
    fantasycalc_adjusted: "FC Adjusted",
    usatoday_adjusted: "USAT Adjusted",
    fantasypros_adjusted: "FP Adjusted",
    cbs_adjusted: "CBS Adjusted",
    espn_vorp: "ESPN pure VORP"
  };
  const WEEKED_SOURCE_KEYS = new Set(["usatoday", "fantasycalc", "fantasypros", "cbs", "fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted", "cbs_adjusted"]);
  const SOURCE_KEYS = [
    "usatoday",
    "fantasycalc",
    "fantasypros",
    "cbs",
    "espn",
    "fantasycalc_adjusted",
    "usatoday_adjusted",
    "fantasypros_adjusted"
  ];
  const SOURCE_STYLES = {
    usatoday: {color: "#d5531d", dash: []},
    fantasycalc: {color: "#236a96", dash: []},
    fantasypros: {color: "#16815d", dash: []},
    cbs: {color: "#b83e45", dash: []},
    espn: {color: "#6b55a3", dash: []},
    fantasycalc_adjusted: {color: "#236a96", dash: [7, 4]},
    usatoday_adjusted: {color: "#d5531d", dash: [7, 4]},
    fantasypros_adjusted: {color: "#16815d", dash: [7, 4]},
    cbs_adjusted: {color: "#b83e45", dash: [7, 4]},
    espn_vorp: {color: "#6b55a3", dash: []}
  };
  const SOURCE_GROUPS = [
    {label:"Bottom-up indexed", keys:["espn"]},
    {label:"Adjusted source projects", keys:["fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted", "cbs_adjusted"]},
    {label:"Pure VORP", keys:["espn_vorp"]},
    {label:"Direct published charts", keys:["usatoday", "fantasycalc", "fantasypros", "cbs"]}
  ];
  const PURE_VORP_KEYS = ["espn_vorp"];
  const EXTRA_SOURCE_KEYS = ["cbs_adjusted"];
  const DEFAULT_INDEXED_SOURCES = ["espn", "fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted", "cbs_adjusted"];
  const POSITION_ORDER = ["QB", "RB", "WR", "TE"];
  const SPECIALIST_POSITIONS = ["K", "DST"];
  const CHART_POSITIONS = [...POSITION_ORDER, ...SPECIALIST_POSITIONS];
  const DEFAULT_ROSTER = Object.freeze({QB:1, RB:2, WR:2, TE:1, FLEX:2, BENCH:6, K:0, DST:0});
  const VALUE_BANDS = {
    all: {label:"Full", min:0, max:null},
    elite: {label:"Elite", min:40, max:null},
    starter: {label:"Starter value", min:15, max:45},
    bench: {label:"Bench value", min:0, max:18}
  };

  const root = document.getElementById("curve-widget");
  if (!root) return;
  const $ = selector => root.querySelector(selector);
  const canvas = $("#chart");
  const tip = $("#tip");

  function loadComparisonData() {
    if (window.DDFComparisonData) return Promise.resolve(window.DDFComparisonData);
    if (!window.DDFComparisonDataPromise) {
      window.DDFComparisonDataPromise = fetch("assets/comparison-sources-data.json")
        .then(response => {
          if (!response.ok) throw new Error(`Data request failed (${response.status})`);
          return response.json();
        })
        .then(payload => {
          window.DDFComparisonData = payload;
          return payload;
        });
    }
    return window.DDFComparisonDataPromise;
  }

  let data = null;
  let canonicalByKey = new Map();
  let sourceMaps = new Map();
  let universe = [];
  let orderedRows = [];
  let position = "ALL";
  let scoring = "ppr";
  let teams = 12;
  let rosterShape = {...DEFAULT_ROSTER};
  let valueBand = "all";
  let includeSpecialists = false;
  let lockOrder = "espn";
  let activeSources = new Set(DEFAULT_INDEXED_SOURCES);
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
  function weekForSource(key) {
    if (!WEEKED_SOURCE_KEYS.has(key)) return null;
    const source = data?.sources?.[key] || (key === "cbs_adjusted" ? data?.sources?.cbs : null) || {};
    const fitWeek = String(source.fit_bake_id || "").match(/fitwk(\d+)/i);
    if (fitWeek) return Number(fitWeek[1]);
    return Number(data?.value_weeks?.monday) || null;
  }

  function rolloverDate() {
    const built = new Date(data?.built_at || "");
    if (Number.isNaN(built.getTime())) return null;
    const next = new Date(Date.UTC(built.getUTCFullYear(), built.getUTCMonth(), built.getUTCDate()));
    const daysUntilMonday = (8 - next.getUTCDay()) % 7 || 7;
    next.setUTCDate(next.getUTCDate() + daysUntilMonday);
    return next;
  }

  function todayDate() {
    const override = window.TRADE_VALUE_TODAY;
    const raw = override ? new Date(`${String(override).slice(0, 10)}T00:00:00Z`) : new Date();
    return Number.isNaN(raw.getTime()) ? new Date() : raw;
  }

  function activeReferenceWeek() {
    const base = Number(data?.value_weeks?.monday);
    if (!Number.isFinite(base)) return null;
    const rollover = rolloverDate();
    if (!rollover) return base;
    return todayDate() >= rollover ? base + 1 : base;
  }

  function isWeekCurrent(key) {
    const week = weekForSource(key);
    const activeWeek = activeReferenceWeek();
    return !week || !activeWeek || week >= activeWeek;
  }

  function sourceLabel(key) {
    const base = SOURCE_LABELS[key] || key;
    const week = weekForSource(key);
    if (!week || key === "espn") return base;
    return `${base} Wk ${week}`;
  }
  const lockLabel = key => key === "preseason" ? "Preseason positional rank" : key === "disagreement" ? "Largest disagreement" : `${sourceLabel(key)} value`;
  const isPosition = player => position === "ALL" || (position === "FLEX" ? ["RB", "WR", "TE"].includes(player.pos) : player.pos === position);
  const visibleSourceKeys = () => [...SOURCE_KEYS, ...EXTRA_SOURCE_KEYS, ...PURE_VORP_KEYS];
  const sourceAvailable = key => sourceMaps.get(key)?.size > 0 && isWeekCurrent(key) && sourceComboExists(key);
  const activeSourceKeys = () => visibleSourceKeys().filter(key => activeSources.has(key) && sourceAvailable(key));
  const isLockKey = key => ["preseason", "disagreement", ...SOURCE_KEYS, ...EXTRA_SOURCE_KEYS, ...PURE_VORP_KEYS].includes(key);
  const defaultValueLock = () => "espn";
  const sourceComboExists = key => {
    if (key === "espn_vorp") return true;
    if (key === "cbs_adjusted") return Boolean(data?.sources?.cbs?.combos?.[comboKey("cbs")]);
    return Boolean(data?.sources?.[key]?.combos?.[comboKey(key)]);
  };

  function comboKey(key) {
    const compact = scoring === "ppr" ? "full" : scoring === "half_ppr" ? "half" : "standard";
    const score = key.endsWith("_adjusted") && compact === "standard" ? "std" : compact;
    if (key === "fantasycalc" || key === "fantasycalc_adjusted") return `${score}_${teams}_qb1`;
    if (key === "espn") return `${score}_${teams}`;
    if (key === "espn_vorp") return null;
    return `${score}_${teams}`;
  }

  function buildCanonicalMap() {
    const payload = JSON.parse(document.getElementById("players-data")?.textContent || "{}");
    const map = new Map();
    (payload.players || []).forEach(player => {
      const playerKey = Number(player.player_key);
      const name = String(player.full_name || player.name || "").trim();
      if (!Number.isInteger(playerKey) || !name || !CHART_POSITIONS.includes(player.pos)) return;
      const rankValue = player.preseasonRank ?? player.preseason_ecr_rank;
      const rank = Number(rankValue);
      const specialistProjection = SPECIALIST_POSITIONS.includes(player.pos)
        ? (player.espn_ppg || player.kdst_ppg || player.blend_ppg || player.ecr_ppg || null)
        : null;
      map.set(playerKey, {
        player_key: playerKey,
        name,
        team: String(player.team || "—"),
        pos: player.pos,
        preseasonRank: Number.isFinite(rank) && rank > 0 ? rank : null,
        espn_ppg: player.espn_ppg || specialistProjection,
        projectionSource: player.espn_ppg ? "ESPN" : (specialistProjection ? "K/DST projection artifact" : null)
      });
    });
    return map;
  }

  function preseasonComparator(a, b) {
    if (position === "FLEX") {
      const posDifference = POSITION_ORDER.indexOf(a.pos) - POSITION_ORDER.indexOf(b.pos);
      if (posDifference) return posDifference;
    }
    const aMissing = !Number.isFinite(a.preseasonRank);
    const bMissing = !Number.isFinite(b.preseasonRank);
    if (aMissing !== bMissing) return aMissing ? 1 : -1;
    if (!aMissing && a.preseasonRank !== b.preseasonRank) return a.preseasonRank - b.preseasonRank;
    return [...POSITION_ORDER, ...SPECIALIST_POSITIONS].indexOf(a.pos) - [...POSITION_ORDER, ...SPECIALIST_POSITIONS].indexOf(b.pos) || a.name.localeCompare(b.name) || a.player_key - b.player_key;
  }

  function disagreement(row) {
    const values = visibleSourceKeys().map(key => row.values[key]).filter(Number.isFinite);
    return values.length >= 2 ? Math.max(...values) - Math.min(...values) : null;
  }

  function orderComparator(a, b) {
    if (lockOrder === "preseason" && position === "ALL") {
      const aBest = Math.max(...activeSourceKeys().map(key => a.values[key]).filter(Number.isFinite), -Infinity);
      const bBest = Math.max(...activeSourceKeys().map(key => b.values[key]).filter(Number.isFinite), -Infinity);
      if (aBest !== bBest) return bBest - aBest;
      return preseasonComparator(a, b);
    }
    if (lockOrder === "preseason") return preseasonComparator(a, b);
    const aValue = lockOrder === "disagreement" ? disagreement(a) : a.values[lockOrder];
    const bValue = lockOrder === "disagreement" ? disagreement(b) : b.values[lockOrder];
    const aMissing = !Number.isFinite(aValue);
    const bMissing = !Number.isFinite(bValue);
    if (aMissing !== bMissing) return aMissing ? 1 : -1;
    if (!aMissing && aValue !== bValue) return bValue - aValue;
    return preseasonComparator(a, b);
  }

  function scoringField() {
    return scoring === "ppr" ? "ppr" : scoring === "half_ppr" ? "half_ppr" : "standard";
  }

  function rosterIsDefault() {
    return Object.keys(DEFAULT_ROSTER).every(key => Number(rosterShape[key]) === Number(DEFAULT_ROSTER[key]));
  }

  function allocationCountsFor(pool, shape = rosterShape) {
    const direct = {QB: teams * shape.QB, RB: teams * shape.RB, WR: teams * shape.WR, TE: teams * shape.TE};
    const lineup = {...direct};
    const rostered = {...direct};
    const ranked = pool.filter(player => POSITION_ORDER.includes(player.pos) && Number.isFinite(player.preseasonRank)).sort((a, b) => {
      const aMissing = !Number.isFinite(a.preseasonRank), bMissing = !Number.isFinite(b.preseasonRank);
      if (aMissing !== bMissing) return aMissing ? 1 : -1;
      return (a.preseasonRank || 0) - (b.preseasonRank || 0) || POSITION_ORDER.indexOf(a.pos) - POSITION_ORDER.indexOf(b.pos);
    });
    const used = new Set();
    Object.entries(direct).forEach(([pos, count]) => {
      ranked.filter(player => player.pos === pos).slice(0, count).forEach(player => used.add(player.player_key));
    });
    ranked.filter(player => ["RB", "WR", "TE"].includes(player.pos) && !used.has(player.player_key)).slice(0, teams * shape.FLEX).forEach(player => {
      used.add(player.player_key);
      lineup[player.pos] += 1;
      rostered[player.pos] += 1;
    });
    ranked.filter(player => !used.has(player.player_key)).slice(0, teams * shape.BENCH).forEach(player => {
      used.add(player.player_key);
      rostered[player.pos] += 1;
    });
    SPECIALIST_POSITIONS.forEach(pos => {
      direct[pos] = teams * Number(shape[pos] || 0);
      lineup[pos] = direct[pos];
      rostered[pos] = direct[pos];
    });
    return {direct, lineup, rostered};
  }

  function buildEspnVorpMap() {
    const values = new Map();
    const field = scoringField();
    const counts = allocationCountsFor([...canonicalByKey.values()]);
    const targetCombo = data.sources?.espn?.combos?.[comboKey("espn")];
    CHART_POSITIONS.forEach(pos => {
      const priced = [...canonicalByKey.values()]
        .filter(player => player.pos === pos)
        .map(player => ({player, ppg:Number(player.espn_ppg?.[field])}))
        .filter(item => Number.isFinite(item.ppg))
        .sort((a, b) => b.ppg - a.ppg || preseasonComparator(a.player, b.player));
      if (!priced.length) return;
      const baselineIndex = Math.max(0, Math.min(priced.length - 1, counts.rostered[pos]));
      const baseline = priced[baselineIndex].ppg;
      const rawRows = priced.map(({player, ppg}) => ({player, value:Math.max(0, ppg - baseline)}));
      const rawTotal = rawRows.reduce((sum, row) => sum + row.value, 0);
      const espnMap = sourceMaps.get("espn");
      const espnTotal = espnMap
        ? [...espnMap.entries()].filter(([playerKey]) => canonicalByKey.get(playerKey)?.pos === pos).reduce((sum, [, value]) => sum + value, 0)
        : 0;
      const targetTotal = Number(targetCombo?.index_total?.[pos]?.target_total) || espnTotal || rawTotal;
      const scale = rawTotal > 0 && targetTotal > 0 ? targetTotal / rawTotal : 1;
      rawRows.forEach(({player, value}) => {
        values.set(player.player_key, value * scale);
      });
    });
    return values;
  }

  function buildSourceMap(key) {
    const combo = data.sources?.[key]?.combos?.[comboKey(key)];
    const raw = combo?.values || combo?.reindexed || {};
    const native = combo?.native || {};
    const values = new Map();
    Object.entries(raw).forEach(([sourceId, rawValue]) => {
      if (["fantasypros", "fantasypros_adjusted"].includes(key) && !Object.prototype.hasOwnProperty.call(native, sourceId)) return;
      const playerKey = Number(data.player_keys?.[sourceId]);
      const player = canonicalByKey.get(playerKey);
      const value = clampValue(rawValue);
      if (!player || value === null) return;
      if (values.has(playerKey) && values.get(playerKey) !== value) throw new Error(`Conflicting canonical identity ${playerKey} in ${sourceLabel(key)}.`);
      values.set(playerKey, value);
    });
    return values;
  }

  function applyRosterShape(values, key) {
    if (rosterIsDefault() || key === "espn_vorp") return values;
    const shaped = new Map(values);
    const defaultCounts = allocationCountsFor([...canonicalByKey.values()], DEFAULT_ROSTER);
    const customCounts = allocationCountsFor([...canonicalByKey.values()], rosterShape);
    const totalBefore = [...values.values()].reduce((sum, value) => sum + value, 0);
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
    const totalAfter = [...shaped.values()].reduce((sum, value) => sum + value, 0);
    const fixedPieScale = totalBefore > 0 && totalAfter > 0 ? totalBefore / totalAfter : 1;
    shaped.forEach((value, playerKey) => shaped.set(playerKey, value * fixedPieScale));
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
    const targetCombo = data.sources?.cbs?.combos?.[comboKey("cbs")];
    POSITION_ORDER.forEach(pos => {
      const rows = [...multipliers.entries()].filter(([playerKey]) => canonicalByKey.get(playerKey)?.pos === pos);
      const total = rows.reduce((sum, [, value]) => sum + value, 0);
      const target = Number(targetCombo?.index_total?.[pos]?.target_total);
      const scale = total > 0 && Number.isFinite(target) && target > 0 ? target / total : 1;
      rows.forEach(([playerKey, value]) => multipliers.set(playerKey, value * scale));
    });
    return multipliers;
  }

  function rebuildDomain() {
    sourceMaps = new Map();
    SOURCE_KEYS.forEach(key => sourceMaps.set(key, applyRosterShape(buildSourceMap(key), key)));
    sourceMaps.set("cbs_adjusted", applyRosterShape(buildCbsAdjustedMap(), "cbs_adjusted"));
    sourceMaps.set("espn_vorp", buildEspnVorpMap());

    const keys = new Set();
    visibleSourceKeys().forEach(key => sourceMaps.get(key)?.forEach((_, playerKey) => keys.add(playerKey)));
    universe = [...keys].map(playerKey => {
      const player = canonicalByKey.get(playerKey);
      if (!player) return null;
      const values = Object.fromEntries(visibleSourceKeys().map(key => [key, sourceMaps.get(key)?.has(playerKey) ? sourceMaps.get(key).get(playerKey) : null]));
      return {...player, values};
    }).filter(Boolean);
    orderedRows = universe.filter(row => (includeSpecialists || !SPECIALIST_POSITIONS.includes(row.pos)) && isPosition(row)).sort(orderComparator);
    syncContext();
  }

  function displayRows() {
    if (!hideZeroTail) return orderedRows;
    let lastPriced = -1;
    orderedRows.forEach((row, index) => {
      if (Number.isFinite(row.values.espn_vorp) && row.values.espn_vorp > 0) lastPriced = index;
    });
    return lastPriced >= 0 ? orderedRows.slice(0, lastPriced + 1) : orderedRows.slice(0, 1);
  }

  function syncContext() {
    const context = $("#curveContext");
    if (!context) return;
    const positionLabel = position === "ALL" ? "All positions" : position === "FLEX" ? "RB / WR / TE" : position;
    const week = activeReferenceWeek();
    const weekLabel = week ? `Week ${week} references` : "current references";
    const rosterLabel = `${rosterShape.QB}QB/${rosterShape.RB}RB/${rosterShape.WR}WR/${rosterShape.TE}TE/${rosterShape.FLEX}FLEX/${rosterShape.BENCH}BN`;
    const band = VALUE_BANDS[valueBand]?.label || "Full";
    context.textContent = `${scoreLabel()} · ${teams} teams · ${rosterLabel} · ${positionLabel} · ${band} y-axis · ${weekLabel} plus ESPN live · locked to ${lockLabel(lockOrder)}`;
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
      if (SPECIALIST_POSITIONS.includes(key) && !includeSpecialists) {
        button.disabled = true;
        button.title = "K/DST need ESPN projection-derived values before they can be charted.";
      }
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
        button.textContent = label;
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

  function makeRosterControls() {
    const grid = $("#rosterShapeControls");
    if (!grid) return;
    const controls = [
      ["QB", "QB"],
      ["RB", "RB"],
      ["WR", "WR"],
      ["TE", "TE"],
      ["FLEX", "Flex"],
      ["BENCH", "Bench"],
      ["K", "K"],
      ["DST", "DST"]
    ];
    grid.replaceChildren();
    controls.forEach(([key, label]) => {
      const wrapper = document.createElement("label");
      wrapper.className = "roster-step";
      const text = document.createElement("span");
      text.textContent = label;
      const input = document.createElement("input");
      input.type = "number";
      input.min = ["BENCH", "K", "DST"].includes(key) ? "0" : "1";
      input.max = key === "BENCH" ? "14" : key === "K" || key === "DST" ? "3" : "5";
      input.step = "1";
      input.value = rosterShape[key];
      input.dataset.rosterKey = key;
      input.setAttribute("aria-label", `${label} roster spots`);
      input.addEventListener("change", () => setRosterSpot(key, input.value));
      wrapper.append(text, input);
      grid.appendChild(wrapper);
    });
    const specialistToggle = $("#includeSpecialists");
    const specialistNote = $("#specialistNote");
    const specialistPlayers = [...canonicalByKey.values()].filter(player => SPECIALIST_POSITIONS.includes(player.pos));
    const hasSpecialists = specialistPlayers.some(player => player.espn_ppg && Object.values(player.espn_ppg).some(Number.isFinite));
    const hasTrueEspnSpecialists = specialistPlayers.some(player => player.projectionSource === "ESPN");
    if (specialistToggle) {
      specialistToggle.checked = includeSpecialists && hasSpecialists;
      specialistToggle.disabled = !hasSpecialists;
      specialistToggle.onchange = event => {
        includeSpecialists = event.target.checked && hasSpecialists;
        if (includeSpecialists) {
          if (!rosterShape.K) rosterShape.K = 1;
          if (!rosterShape.DST) rosterShape.DST = 1;
        }
        if (!includeSpecialists && SPECIALIST_POSITIONS.includes(position)) position = "ALL";
        rebuildDomain();
        makeTabs();
        resetZoom();
        draw();
      };
    }
    if (specialistNote) {
      specialistNote.textContent = hasSpecialists
        ? (hasTrueEspnSpecialists
          ? "K/DST use ESPN projection-derived values only."
          : "K/DST use the dedicated specialist projection artifact until ESPN K/DST fields are present.")
        : "K/DST are waiting for projection-derived values in the artifact; preseason ranks are not used.";
    }
  }

  function makeValueBandControl() {
    const container = $("#valueBandSeg");
    if (!container) return;
    container.replaceChildren();
    Object.entries(VALUE_BANDS).forEach(([key, config]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = config.label;
      button.classList.toggle("active", valueBand === key);
      button.setAttribute("aria-pressed", String(valueBand === key));
      button.addEventListener("click", () => setValueBand(key));
      container.appendChild(button);
    });
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
      const freshWeek = isWeekCurrent(key);
      const available = hasData && freshWeek;
      input.checked = activeSources.has(key) && available;
      input.disabled = !available;
      input.dataset.source = key;
      input.setAttribute("aria-label", `Show ${sourceLabel(key)} curve`);
      if (!available) {
        label.classList.add("is-disabled");
        label.title = hasData && !freshWeek
          ? `${sourceLabel(key)} is past the active Week ${activeReferenceWeek()} reference window; waiting for a refreshed artifact.`
          : `${sourceLabel(key)} is not available for ${scoreLabel()} / ${teams} teams in the current artifact.`;
      }
      input.addEventListener("change", () => {
        if (input.checked) activeSources.add(key);
        else if (activeSourceKeys().length > 1) activeSources.delete(key);
        else input.checked = true;
        crossRank = null;
        syncZoom();
        makeSourceToggles();
        draw();
      });
      const swatch = document.createElement("span");
      swatch.className = "source-line";
      swatch.style.borderTopColor = SOURCE_STYLES[key].color;
      swatch.style.borderTopStyle = key.endsWith("_adjusted") ? "dashed" : "solid";
      const text = document.createElement("span");
      text.textContent = sourceLabel(key);
      if (!freshWeek && hasData) {
        const meta = document.createElement("span");
        meta.className = "src-meta";
        meta.textContent = `waiting Wk ${activeReferenceWeek()}`;
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
      ["preseason", "Preseason positional rank"],
      ["disagreement", "Largest disagreement"],
      ...visibleSourceKeys().filter(sourceAvailable).map(key => [key, sourceLabel(key)])
    ];
    select.innerHTML = options.map(([value, label]) => `<option value="${value}">${label}</option>`).join("");
    select.value = lockOrder;
    select.addEventListener("change", event => setLockOrder(event.target.value));
    syncLockNote();
  }

  function syncLockNote() {
    const select = $("#curveLockOrder");
    if (select) select.value = lockOrder;
    const note = $("#curveLockNote");
    if (!note) return;
    note.textContent = [...SOURCE_KEYS, ...EXTRA_SOURCE_KEYS, ...PURE_VORP_KEYS].includes(lockOrder)
      ? `Every curve follows ${sourceLabel(lockOrder)}’s player order; players missing from that source sort last.`
      : lockOrder === "disagreement"
        ? "Players with the widest available cross-source spread appear first."
        : position === "ALL"
          ? "All positions use one mixed overall curve, sorted by the best visible value when preseason is selected."
          : "Preseason ranks are positional, so Flex groups players by position before rank.";
  }

  function publishShared() {
    const detail = {scoring, teams, position, model: "monday", lockOrder, rosterShape:{...rosterShape}};
    window.DDF_SHARED_STATE = detail;
    window.dispatchEvent(new CustomEvent("ddf-shared-change", {detail}));
  }

  function setRosterSpot(key, raw, publish = true) {
    if (!Object.prototype.hasOwnProperty.call(rosterShape, key)) return;
    const min = ["BENCH", "K", "DST"].includes(key) ? 0 : 1;
    const max = key === "BENCH" ? 14 : key === "K" || key === "DST" ? 3 : 5;
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
    resetZoom();
    draw();
    if (publish) publishShared();
  }

  function setValueBand(key) {
    if (!Object.prototype.hasOwnProperty.call(VALUE_BANDS, key) || key === valueBand) return;
    valueBand = key;
    crossRank = null;
    makeValueBandControl();
    syncContext();
    draw();
  }

  function setPosition(value, publish = true) {
    if (!POSITIONS.includes(value) || value === position) return;
    position = value;
    if (position === "ALL" && lockOrder === "preseason") lockOrder = defaultValueLock();
    crossRank = null;
    rebuildDomain();
    syncTabs();
    makeLockControl();
    resetZoom();
    draw();
    if (publish) publishShared();
  }

  function setScoring(value, publish = true) {
    const normalized = value === "half" ? "half_ppr" : value === "full" ? "ppr" : value;
    if (!SCORINGS.some(([key]) => key === normalized) || normalized === scoring) return;
    scoring = normalized;
    crossRank = null;
    rebuildDomain();
    if (![ "preseason", "disagreement" ].includes(lockOrder) && !sourceAvailable(lockOrder)) lockOrder = defaultValueLock();
    makeLeagueControls();
    makeRosterControls();
    makeValueBandControl();
    makeSourceToggles();
    makeLockControl();
    resetZoom();
    draw();
    if (publish) publishShared();
  }

  function setTeams(value, publish = true) {
    const normalized = Number(value);
    if (![8, 10, 12, 14].includes(normalized) || normalized === teams) return;
    teams = normalized;
    crossRank = null;
    rebuildDomain();
    if (![ "preseason", "disagreement" ].includes(lockOrder) && !sourceAvailable(lockOrder)) lockOrder = defaultValueLock();
    makeLeagueControls();
    makeRosterControls();
    makeValueBandControl();
    makeSourceToggles();
    makeLockControl();
    resetZoom();
    draw();
    if (publish) publishShared();
  }

  function setLockOrder(value, publish = true) {
    if (!isLockKey(value) || value === lockOrder) return;
    lockOrder = value;
    window.DDF_LOCK_ORDER = value;
    crossRank = null;
    rebuildDomain();
    syncLockNote();
    resetZoom();
    draw();
    if (publish) window.dispatchEvent(new CustomEvent("ddf-lock-order-change", {detail: {lockOrder:value}}));
  }

  window.DDFCurveControls = {
    setPosition,
    setScoring,
    setTeams,
    setLockOrder,
    setModel: () => {},
    redraw: () => draw(),
    getState: () => ({position, scoring, teams, model: "monday", valueMode:"indexed", lockOrder, activeSources:activeSourceKeys()}),
    getLockedDomain: () => displayRows().map((row, index) => ({rank:index + 1, player_key:row.player_key, name:row.name})),
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
    renderVisiblePlayers();
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
      starter: teams * (rosterShape.QB + rosterShape.RB + rosterShape.WR + rosterShape.TE + rosterShape.FLEX + (includeSpecialists ? rosterShape.K + rosterShape.DST : 0)),
      bench: teams * (rosterShape.QB + rosterShape.RB + rosterShape.WR + rosterShape.TE + rosterShape.FLEX + rosterShape.BENCH + (includeSpecialists ? rosterShape.K + rosterShape.DST : 0))
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
    const rows = orderedRows;
    const lastPositive = rows.reduce((last, row, index) => {
      const hasPositiveValue = Number.isFinite(row.values.espn_vorp) && row.values.espn_vorp > 0;
      return hasPositiveValue ? index + 1 : last;
    }, 1);
    return [
      {key:"starter_to_bench", ordinal:ordinals.starter, value:ordinals.starter + 0.5, label:"Starter → Bench", color:"#238a52"},
      {key:"bench_to_waiver", ordinal:lastPositive, value:lastPositive + 0.5, label:"Bench → Waiver", color:"#c43d32", dotted:true}
    ];
  }

  // Vertical roster rank cutoffs under EVERY lock (2026-09-19, user
  // directive): show the transitions between roster zones. Starter-to-
  // Bench sits after the last startable player; Bench-to-Waiver sits after
  // the last player with any positive indexed value, so waiver territory is
  // the zero-value pool to the right of the second line. No horizontal value
  // thresholds under any lock.
  function boundaryMarkers() {
    const maximum = fullRankMax();
    return markerDefinitions().map(marker => ({
      ...marker,
      axis:"x",
      value:Math.max(1, Math.min(maximum, marker.value))
    }));
  }

  function fixedPieDiagnostics() {
    const tolerance = 2;
    const checks = [];
    SOURCE_KEYS.forEach(key => {
      const combo = data.sources?.[key]?.combos?.[comboKey(key)];
      const targets = combo?.index_total || {};
      POSITION_ORDER.forEach(pos => {
        const target = Number(targets[pos]?.target_total);
        if (!Number.isFinite(target)) return;
        const total = [...sourceMaps.get(key).entries()]
          .filter(([playerKey]) => canonicalByKey.get(playerKey)?.pos === pos)
          .reduce((sum, [, value]) => sum + value, 0);
        checks.push({source:key, pos, total, target, delta:total - target, ok:Math.abs(total - target) <= tolerance});
      });
    });
    return {tolerance, checks, ok:checks.every(check => check.ok)};
  }

  function yAxisScale(rows) {
    const band = VALUE_BANDS[valueBand] || VALUE_BANDS.all;
    const values = rows
      .slice(Math.max(0, zoomLow - 1), Math.max(zoomLow, zoomHigh))
      .flatMap(row => activeSourceKeys().map(key => row.values[key]))
      .filter(Number.isFinite);
    const dataMax = values.length ? Math.max(...values) : 0;
    const bandMin = Number(band.min) || 0;
    const cappedMax = band.max !== null && band.max !== undefined && Number.isFinite(Number(band.max)) ? Number(band.max) : dataMax;
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
    const rows = displayRows().slice(Math.max(0, zoomLow - 1), zoomHigh);
    const keys = activeSourceKeys();
    if (!rows.length || !keys.length) {
      container.innerHTML = `<p class="visible-empty">No players or active scores in the current view.</p>`;
      return;
    }
    const head = `<tr><th>Rank</th><th>Player</th>${keys.map(key => `<th>${sourceLabel(key)}</th>`).join("")}</tr>`;
    const body = rows.map((row, index) => `<tr><td>${zoomLow + index}</td><td><strong>${row.name}</strong><span>${row.pos} · ${row.team}</span></td>${keys.map(key => `<td>${formatScore(row.values[key])}</td>`).join("")}</tr>`).join("");
    container.innerHTML = `<p class="visible-note">Shown scores follow the active source toggles. Player order follows ${lockLabel(lockOrder)}.</p><div class="visible-table-wrap"><table><thead>${head}</thead><tbody>${body}</tbody></table></div>`;
  }

  function draw() {
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
      rows.forEach((row, index) => {
        const rank = index + 1;
        const value = row.values[key];
        if (rank < zoomLow || rank > zoomHigh || !Number.isFinite(value)) {
          drawing = false;
          return;
        }
        const px = x(rank), py = y(value);
        if (!drawing) context.moveTo(px, py);
        else context.lineTo(px, py);
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
    $("#curveFootnote").textContent = `${activeSourceKeys().length} active league-compatible series shown · fixed-pie indexed values; pure VORP uses ESPN PPG above waiver when enabled · missing values break a line · roster transitions: ${markerText}.`;
    renderVisiblePlayers();
    canvas.setAttribute("aria-label", "Trade value curves with player rank on the horizontal axis, value on the vertical axis, and vertical roster transition lines from starter to bench and bench to waiver. Use Home or End, then the left and right arrow keys, to inspect each player.");
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
    return `<strong>${rank}. ${row.name}</strong><span class="tip-meta">${row.pos} · ${row.team} · ${rankLabel}</span><span class="tip-grid">${values}</span>`;
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
    const eightSources = SOURCE_KEYS.length === 8 && SOURCE_KEYS.every(key => sourceMaps.has(key));
    const expectedToggleCount = SOURCE_GROUPS.reduce((sum, group) => sum + group.keys.length, 0);
    const sourceToggles = $("#sourceToggles")?.querySelectorAll("input[type=checkbox]").length === expectedToggleCount;
    const noAggregate = !Object.prototype.hasOwnProperty.call(window, "DDFCurveMedian");
    const stableDomain = rows.every((row, index) => index === 0 || row.player_key !== rows[index - 1].player_key);
    const validValues = SOURCE_KEYS.every(key => [...sourceMaps.get(key).values()].every(value => Number.isFinite(value) && value >= 0));
    const sourcePeaks = Object.fromEntries(SOURCE_KEYS.map(key => [key, Math.max(...sourceMaps.get(key).values())]));
    const distinctSourcePeaks = new Set(Object.values(sourcePeaks).map(value => value.toFixed(1))).size > 1;
    const valuesAbove70 = Object.values(sourcePeaks).every(value => value > 70);
    const scale = yAxisScale(rows);
    const visiblePeak = Math.max(...rows.flatMap(row => activeSourceKeys().map(key => row.values[key])).filter(Number.isFinite));
    const dynamicAxisCoversData = scale.max >= visiblePeak;
    const markers = boundaryMarkers();
    const rosterTransitions = markers.length === 2
      && markers.every((marker, index) => marker.axis === "x" && Number.isFinite(marker.value) && marker.label === ["Starter → Bench", "Bench → Waiver"][index]);
    const fixedPie = fixedPieDiagnostics();
    const defaultGroupedSources = DEFAULT_INDEXED_SOURCES.every(key => activeSources.has(key));
    const pureVorpAvailable = sourceMaps.get("espn_vorp")?.size > 0;
    const diagnostics = {eightSources, sourceToggles, noAggregate, stableDomain, validValues, distinctSourcePeaks, valuesAbove70, dynamicAxisCoversData, sourcePeaks, yAxisMax:scale.max, rosterTransitions, rosterMarkerAxis:"x", fixedPieIndexed:fixedPie.ok, fixedPie, defaultGroupedSources, pureVorpAvailable, valueMode:"indexed", lockOrder, sourceCount:SOURCE_KEYS.length, activeCount:activeSourceKeys().length, curveCount:activeSourceKeys().length};
    window.TradeValueCurveDiagnostics = Object.freeze(diagnostics);
    window.DDFCurveDiagnostics = window.TradeValueCurveDiagnostics;
    const failed = Object.entries(diagnostics).filter(([key, value]) => ["eightSources", "sourceToggles", "noAggregate", "stableDomain", "validValues", "distinctSourcePeaks", "valuesAbove70", "dynamicAxisCoversData", "rosterTransitions", "fixedPieIndexed"].includes(key) && value !== true);
    if (failed.length || !defaultGroupedSources || !pureVorpAvailable) throw new Error(`Curve regression guard failed: ${failed.map(([key]) => key).concat(defaultGroupedSources ? [] : ["defaultGroupedSources"], pureVorpAvailable ? [] : ["pureVorpAvailable"]).join(", ")}`);
  }

  async function init() {
    try {
      data = await loadComparisonData();
      canonicalByKey = buildCanonicalMap();
      if (!canonicalByKey.size) throw new Error("Canonical player records are unavailable.");
      const invalid = SOURCE_KEYS.filter(key => data.source_validation?.[key] !== "live");
      if (invalid.length) throw new Error("One or more required comparison sources did not pass validation.");
      if (isLockKey(window.DDF_LOCK_ORDER)) lockOrder = window.DDF_LOCK_ORDER;
      rebuildDomain();
      makeLeagueControls();
      makeRosterControls();
      makeTabs();
      makeValueModeControl();
      makeValueBandControl();
      makeSourceToggles();
      makeLockControl();
      bindZoom();
      resetZoom();
      runRegressionGuards();
      draw();
      $("#curve-status").classList.add("validated");
      $("#curve-status").innerHTML = "<strong>Validated:</strong> ESPN live plus four adjusted source projects are shown by default. Direct published charts are available but off by default. Pure ESPN VORP can be enabled on the same chart.";
      publishShared();
    } catch (error) {
      $("#curve-status").innerHTML = `<strong>Curves unavailable:</strong> ${String(error.message)}`;
      console.error(error);
    }
  }

  init();
})();
