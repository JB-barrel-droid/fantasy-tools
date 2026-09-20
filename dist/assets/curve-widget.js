(() => {
  "use strict";

  const POSITIONS = ["ALL", "QB", "RB", "WR", "TE", "FLEX"];
  const SCORINGS = [["standard", "Standard"], ["half_ppr", "Half PPR"], ["ppr", "Full PPR"]];
  const SOURCE_LABELS = {
    usatoday: "USA Today",
    fantasycalc: "FantasyCalc",
    fantasypros: "FantasyPros",
    cbs: "CBS",
    espn: "ESPN",
    fantasycalc_adjusted: "FC Adjusted",
    usatoday_adjusted: "USAT Adjusted",
    fantasypros_adjusted: "FP Adjusted",
    espn_vorp: "ESPN pure VORP"
  };
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
    espn_vorp: {color: "#6b55a3", dash: []}
  };
  const SOURCE_GROUPS = [
    {label:"Bottom-up indexed", keys:["espn"]},
    {label:"Adjusted source projects", keys:["fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted"]},
    {label:"Direct published charts", keys:["usatoday", "fantasycalc", "fantasypros", "cbs"]}
  ];
  const PURE_VORP_KEYS = ["espn_vorp"];
  const DEFAULT_INDEXED_SOURCES = ["espn", "fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted"];
  const POSITION_ORDER = ["QB", "RB", "WR", "TE"];
  const STARTERS = {QB: 1, RB: 2, WR: 2, TE: 1};
  const FLEX_STARTERS = 2;
  const BENCH_SPOTS = 6;

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
  let valueMode = "indexed";
  let lockOrder = "espn";
  let activeSources = new Set([...DEFAULT_INDEXED_SOURCES, ...PURE_VORP_KEYS]);
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
  const sourceLabel = key => SOURCE_LABELS[key] || key;
  const lockLabel = key => key === "preseason" ? "Preseason positional rank" : key === "disagreement" ? "Largest disagreement" : `${sourceLabel(key)} value`;
  const isPosition = player => position === "ALL" || (position === "FLEX" ? ["RB", "WR", "TE"].includes(player.pos) : player.pos === position);
  const visibleSourceKeys = () => valueMode === "pure_vorp" ? PURE_VORP_KEYS : SOURCE_KEYS;
  const activeSourceKeys = () => visibleSourceKeys().filter(key => activeSources.has(key));
  const isLockKey = key => ["preseason", "disagreement", ...SOURCE_KEYS, ...PURE_VORP_KEYS].includes(key);
  const defaultValueLock = () => valueMode === "pure_vorp" ? "espn_vorp" : "espn";

  function comboKey(key) {
    const compact = scoring === "ppr" ? "full" : scoring === "half_ppr" ? "half" : "standard";
    const score = key.endsWith("_adjusted") && compact === "standard" ? "std" : compact;
    if (key === "fantasycalc") return `${score}_${teams}_qb1`;
    if (key === "espn") return `${score}_${teams}`;
    if (key === "fantasycalc_adjusted") return `${score}_12_qb1`;
    return `${score}_12`;
  }

  function buildCanonicalMap() {
    const payload = JSON.parse(document.getElementById("players-data")?.textContent || "{}");
    const map = new Map();
    (payload.players || []).forEach(player => {
      const playerKey = Number(player.player_key);
      const name = String(player.full_name || player.name || "").trim();
      if (!Number.isInteger(playerKey) || !name || !POSITION_ORDER.includes(player.pos)) return;
      const rankValue = player.preseasonRank ?? player.preseason_ecr_rank;
      const rank = Number(rankValue);
      map.set(playerKey, {
        player_key: playerKey,
        name,
        team: String(player.team || "—"),
        pos: player.pos,
        preseasonRank: Number.isFinite(rank) && rank > 0 ? rank : null,
        espn_ppg: player.espn_ppg || null
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
    return POSITION_ORDER.indexOf(a.pos) - POSITION_ORDER.indexOf(b.pos) || a.name.localeCompare(b.name) || a.player_key - b.player_key;
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

  function allocationCountsFor(pool) {
    const direct = {QB: teams * STARTERS.QB, RB: teams * STARTERS.RB, WR: teams * STARTERS.WR, TE: teams * STARTERS.TE};
    const lineup = {...direct};
    const rostered = {...direct};
    const ranked = pool.filter(player => Number.isFinite(player.preseasonRank)).sort((a, b) => {
      const aMissing = !Number.isFinite(a.preseasonRank), bMissing = !Number.isFinite(b.preseasonRank);
      if (aMissing !== bMissing) return aMissing ? 1 : -1;
      return (a.preseasonRank || 0) - (b.preseasonRank || 0) || POSITION_ORDER.indexOf(a.pos) - POSITION_ORDER.indexOf(b.pos);
    });
    const used = new Set();
    Object.entries(direct).forEach(([pos, count]) => {
      ranked.filter(player => player.pos === pos).slice(0, count).forEach(player => used.add(player.player_key));
    });
    ranked.filter(player => ["RB", "WR", "TE"].includes(player.pos) && !used.has(player.player_key)).slice(0, teams * FLEX_STARTERS).forEach(player => {
      used.add(player.player_key);
      lineup[player.pos] += 1;
      rostered[player.pos] += 1;
    });
    ranked.filter(player => !used.has(player.player_key)).slice(0, teams * BENCH_SPOTS).forEach(player => {
      used.add(player.player_key);
      rostered[player.pos] += 1;
    });
    return {direct, lineup, rostered};
  }

  function buildEspnVorpMap() {
    const values = new Map();
    const field = scoringField();
    const counts = allocationCountsFor([...canonicalByKey.values()]);
    POSITION_ORDER.forEach(pos => {
      const priced = [...canonicalByKey.values()]
        .filter(player => player.pos === pos)
        .map(player => ({player, ppg:Number(player.espn_ppg?.[field])}))
        .filter(item => Number.isFinite(item.ppg))
        .sort((a, b) => b.ppg - a.ppg || preseasonComparator(a.player, b.player));
      if (!priced.length) return;
      const baselineIndex = Math.max(0, Math.min(priced.length - 1, counts.rostered[pos]));
      const baseline = priced[baselineIndex].ppg;
      priced.forEach(({player, ppg}) => {
        values.set(player.player_key, Math.max(0, ppg - baseline));
      });
    });
    return values;
  }

  function rebuildDomain() {
    sourceMaps = new Map();
    SOURCE_KEYS.forEach(key => {
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
      sourceMaps.set(key, values);
    });
    sourceMaps.set("espn_vorp", buildEspnVorpMap());

    const keys = new Set();
    visibleSourceKeys().forEach(key => sourceMaps.get(key)?.forEach((_, playerKey) => keys.add(playerKey)));
    universe = [...keys].map(playerKey => {
      const player = canonicalByKey.get(playerKey);
      if (!player) return null;
      const values = Object.fromEntries([...SOURCE_KEYS, ...PURE_VORP_KEYS].map(key => [key, sourceMaps.get(key)?.has(playerKey) ? sourceMaps.get(key).get(playerKey) : null]));
      return {...player, values};
    }).filter(Boolean);
    orderedRows = universe.filter(isPosition).sort(orderComparator);
    syncContext();
  }

  function displayRows() {
    if (!hideZeroTail) return orderedRows;
    let lastPriced = -1;
    orderedRows.forEach((row, index) => {
      if (activeSourceKeys().some(key => Number.isFinite(row.values[key]) && row.values[key] > 0)) lastPriced = index;
    });
    return lastPriced >= 0 ? orderedRows.slice(0, lastPriced + 1) : orderedRows.slice(0, 1);
  }

  function syncContext() {
    const context = $("#curveContext");
    if (!context) return;
    const positionLabel = position === "ALL" ? "All positions" : position === "FLEX" ? "RB / WR / TE" : position;
    const basis = valueMode === "pure_vorp" ? "pure ESPN VORP" : "fixed-pie indexed values";
    context.textContent = `${scoreLabel()} · ${teams} teams · ${positionLabel} · ${basis} · locked to ${lockLabel(lockOrder)}`;
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
    container.replaceChildren();
    [["indexed", "Indexed values"], ["pure_vorp", "Pure VORP"]].forEach(([key, label]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.classList.toggle("active", valueMode === key);
      button.addEventListener("click", () => {
        if (valueMode === key) return;
        valueMode = key;
        if (!visibleSourceKeys().includes(lockOrder) || (position === "ALL" && lockOrder === "preseason")) lockOrder = defaultValueLock();
        crossRank = null;
        rebuildDomain();
        makeValueModeControl();
        makeSourceToggles();
        makeLockControl();
        resetZoom();
        draw();
        publishShared();
      });
      container.appendChild(button);
    });
  }

  function makeSourceToggles() {
    const container = $("#sourceToggles");
    if (!container) return;
    container.replaceChildren();
    const groups = valueMode === "pure_vorp" ? [{label:"Pure VORP", keys:PURE_VORP_KEYS}] : SOURCE_GROUPS;
    groups.forEach(group => {
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
      input.checked = activeSources.has(key);
      input.dataset.source = key;
      input.setAttribute("aria-label", `Show ${sourceLabel(key)} curve`);
      input.addEventListener("change", () => {
        if (input.checked) activeSources.add(key);
        else if (activeSourceKeys().length > 1) activeSources.delete(key);
        else input.checked = true;
        crossRank = null;
        resetZoom();
        makeSourceToggles();
        draw();
      });
      const swatch = document.createElement("span");
      swatch.className = "source-line";
      swatch.style.borderTopColor = SOURCE_STYLES[key].color;
      swatch.style.borderTopStyle = key.endsWith("_adjusted") ? "dashed" : "solid";
      const text = document.createElement("span");
      text.textContent = sourceLabel(key);
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
      ...(valueMode === "pure_vorp" ? PURE_VORP_KEYS : SOURCE_KEYS).map(key => [key, sourceLabel(key)])
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
    note.textContent = [...SOURCE_KEYS, ...PURE_VORP_KEYS].includes(lockOrder)
      ? `Every curve follows ${sourceLabel(lockOrder)}’s player order; players missing from that source sort last.`
      : lockOrder === "disagreement"
        ? "Players with the widest available cross-source spread appear first."
        : position === "ALL"
          ? "All positions use one mixed overall curve, sorted by the best visible value when preseason is selected."
          : "Preseason ranks are positional, so Flex groups players by position before rank.";
  }

  function publishShared() {
    const detail = {scoring, teams, position, model: "monday", lockOrder};
    window.DDF_SHARED_STATE = detail;
    window.dispatchEvent(new CustomEvent("ddf-shared-change", {detail}));
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
    getState: () => ({position, scoring, teams, model: "monday", valueMode, lockOrder, activeSources:activeSourceKeys()}),
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
    [["Full", 1, maximum], ["Top 25", 1, Math.min(25, maximum)], ["Top 50", 1, Math.min(50, maximum)]].forEach(([label, low, high]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
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
      starter: teams * (6 + FLEX_STARTERS),
      bench: teams * (6 + FLEX_STARTERS + BENCH_SPOTS)
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
    const rows = displayRows();
    const lastPositive = rows.reduce((last, row, index) => {
      const hasPositiveValue = visibleSourceKeys().some(key => Number.isFinite(row.values[key]) && row.values[key] > 0);
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
    const values = rows
      .slice(Math.max(0, zoomLow - 1), Math.max(zoomLow, zoomHigh))
      .flatMap(row => activeSourceKeys().map(key => row.values[key]))
      .filter(Number.isFinite);
    const dataMax = values.length ? Math.max(...values) : 0;
    if (dataMax <= 0) return {max: 10, step: 1};
    const roughStep = dataMax / 9;
    const magnitude = 10 ** Math.floor(Math.log10(roughStep));
    const normalized = roughStep / magnitude;
    const niceFactor = [1, 2, 2.5, 5, 10].find(candidate => candidate >= normalized) || 10;
    const step = niceFactor * magnitude;
    return {max: Math.ceil(dataMax / step) * step, step};
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
    const y = value => pad.top + innerHeight - clampValue(value) / axis.max * innerHeight;
    geometry = {width, height, pad, innerWidth, innerHeight, zoomLow, zoomHigh, yMax:axis.max};

    context.font = '9px "IBM Plex Mono", monospace';
    context.textAlign = "right";
    context.strokeStyle = grid;
    context.fillStyle = text;
    context.lineWidth = 1;
    for (let value = 0; value <= axis.max + axis.step / 2; value += axis.step) {
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
    context.fillText(valueMode === "pure_vorp" ? "VORP" : "Value", 0, 0);
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
    const basis = valueMode === "pure_vorp" ? "pure ESPN PPG above waiver" : "fixed-pie indexed values";
    $("#curveFootnote").textContent = `${activeSourceKeys().length} of ${visibleSourceKeys().length} visible series shown · ${basis} · missing values break a line · roster transitions: ${markerText}.`;
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
    const rankLabel = Number.isFinite(row.preseasonRank) ? `preseason ${row.pos}${row.preseasonRank}` : "preseason unranked";
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

  canvas.addEventListener("pointermove", event => {
    if (event.pointerType === "touch") return;
    showTooltip(nearestRank(event.clientX), event.clientX, event.clientY, false);
  });
  canvas.addEventListener("pointerleave", event => {
    if (event.pointerType === "touch") return;
    crossRank = null;
    tip.style.display = "none";
    draw();
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
    const eightToggles = $("#sourceToggles")?.querySelectorAll("input[type=checkbox]").length === 8;
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
    const defaultGroupedSources = valueMode === "indexed" && DEFAULT_INDEXED_SOURCES.every(key => activeSources.has(key));
    const pureVorpAvailable = sourceMaps.get("espn_vorp")?.size > 0;
    const diagnostics = {eightSources, eightToggles, noAggregate, stableDomain, validValues, distinctSourcePeaks, valuesAbove70, dynamicAxisCoversData, sourcePeaks, yAxisMax:scale.max, rosterTransitions, rosterMarkerAxis:"x", fixedPieIndexed:fixedPie.ok, fixedPie, defaultGroupedSources, pureVorpAvailable, valueMode, lockOrder, sourceCount:SOURCE_KEYS.length, activeCount:activeSourceKeys().length, curveCount:activeSourceKeys().length};
    window.TradeValueCurveDiagnostics = Object.freeze(diagnostics);
    window.DDFCurveDiagnostics = window.TradeValueCurveDiagnostics;
    const failed = Object.entries(diagnostics).filter(([key, value]) => ["eightSources", "eightToggles", "noAggregate", "stableDomain", "validValues", "distinctSourcePeaks", "valuesAbove70", "dynamicAxisCoversData", "rosterTransitions", "fixedPieIndexed"].includes(key) && value !== true);
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
      makeTabs();
      makeValueModeControl();
      makeSourceToggles();
      makeLockControl();
      bindZoom();
      resetZoom();
      runRegressionGuards();
      draw();
      $("#curve-status").classList.add("validated");
      $("#curve-status").innerHTML = "<strong>Validated:</strong> bottom-up ESPN indexed values plus three bias-adjusted source projects are shown by default. Direct published charts are available but off by default. Pure ESPN VORP is available as a separate basis.";
      publishShared();
    } catch (error) {
      $("#curve-status").innerHTML = `<strong>Curves unavailable:</strong> ${String(error.message)}`;
      console.error(error);
    }
  }

  init();
})();
