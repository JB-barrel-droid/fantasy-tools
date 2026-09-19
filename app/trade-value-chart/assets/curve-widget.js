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
    fantasypros_adjusted: "FP Adjusted"
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
    fantasypros_adjusted: {color: "#16815d", dash: [7, 4]}
  };
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
  let position = "QB";
  let scoring = "ppr";
  let teams = 12;
  let lockOrder = "preseason";
  let activeSources = new Set(SOURCE_KEYS);
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
  const isLockKey = key => ["preseason", "disagreement", ...SOURCE_KEYS].includes(key);

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
        preseasonRank: Number.isFinite(rank) && rank > 0 ? rank : null
      });
    });
    return map;
  }

  function preseasonComparator(a, b) {
    if (["ALL", "FLEX"].includes(position)) {
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
    const values = SOURCE_KEYS.map(key => row.values[key]).filter(Number.isFinite);
    return values.length >= 2 ? Math.max(...values) - Math.min(...values) : null;
  }

  function orderComparator(a, b) {
    if (lockOrder === "preseason") return preseasonComparator(a, b);
    const aValue = lockOrder === "disagreement" ? disagreement(a) : a.values[lockOrder];
    const bValue = lockOrder === "disagreement" ? disagreement(b) : b.values[lockOrder];
    const aMissing = !Number.isFinite(aValue);
    const bMissing = !Number.isFinite(bValue);
    if (aMissing !== bMissing) return aMissing ? 1 : -1;
    if (!aMissing && aValue !== bValue) return bValue - aValue;
    return preseasonComparator(a, b);
  }

  function rebuildDomain() {
    sourceMaps = new Map();
    SOURCE_KEYS.forEach(key => {
      const combo = data.sources?.[key]?.combos?.[comboKey(key)];
      const raw = combo?.values || combo?.reindexed || {};
      const native = combo?.native || {};
      const values = new Map();
      const pricedIds = key === "espn" ? new Set(data.sources?.espn?.espn_priced_pids || []) : null;
      Object.entries(raw).forEach(([sourceId, rawValue]) => {
        if (pricedIds && !pricedIds.has(sourceId)) return;
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

    const keys = new Set();
    sourceMaps.forEach(values => values.forEach((_, playerKey) => keys.add(playerKey)));
    universe = [...keys].map(playerKey => {
      const player = canonicalByKey.get(playerKey);
      if (!player) return null;
      const values = Object.fromEntries(SOURCE_KEYS.map(key => [key, sourceMaps.get(key)?.has(playerKey) ? sourceMaps.get(key).get(playerKey) : null]));
      return {...player, values};
    }).filter(Boolean);
    orderedRows = universe.filter(isPosition).sort(orderComparator);
    syncContext();
  }

  function displayRows() {
    if (!hideZeroTail) return orderedRows;
    let lastPriced = -1;
    orderedRows.forEach((row, index) => {
      if ([...activeSources].some(key => Number.isFinite(row.values[key]) && row.values[key] > 0)) lastPriced = index;
    });
    return lastPriced >= 0 ? orderedRows.slice(0, lastPriced + 1) : orderedRows.slice(0, 1);
  }

  function syncContext() {
    const context = $("#curveContext");
    if (!context) return;
    const positionLabel = position === "ALL" ? "All positions" : position === "FLEX" ? "RB / WR / TE" : position;
    context.textContent = `${scoreLabel()} · ${teams} teams · ${positionLabel} · locked to ${lockLabel(lockOrder)}`;
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

  function makeSourceToggles() {
    const container = $("#sourceToggles");
    if (!container) return;
    container.replaceChildren();
    SOURCE_KEYS.forEach(key => {
      const label = document.createElement("label");
      label.className = "src-toggle";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = activeSources.has(key);
      input.dataset.source = key;
      input.setAttribute("aria-label", `Show ${sourceLabel(key)} curve`);
      input.addEventListener("change", () => {
        if (input.checked) activeSources.add(key);
        else if (activeSources.size > 1) activeSources.delete(key);
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
      container.appendChild(label);
    });
  }

  function makeLockControl() {
    const select = $("#curveLockOrder");
    if (!select) return;
    const options = [
      ["preseason", "Preseason positional rank"],
      ["disagreement", "Largest disagreement"],
      ...SOURCE_KEYS.map(key => [key, sourceLabel(key)])
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
    note.textContent = SOURCE_KEYS.includes(lockOrder)
      ? `Every curve follows ${sourceLabel(lockOrder)}’s player order; players missing from that source sort last.`
      : lockOrder === "disagreement"
        ? "Players with the widest available cross-source spread appear first."
        : "Preseason ranks are positional, so All and Flex group players by position before rank.";
  }

  function publishShared() {
    const detail = {scoring, teams, position, model: "monday", lockOrder};
    window.DDF_SHARED_STATE = detail;
    window.dispatchEvent(new CustomEvent("ddf-shared-change", {detail}));
  }

  function setPosition(value, publish = true) {
    if (!POSITIONS.includes(value) || value === position) return;
    position = value;
    crossRank = null;
    rebuildDomain();
    syncTabs();
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
    getState: () => ({position, scoring, teams, model: "monday", lockOrder, activeSources:[...activeSources]}),
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
    const direct = {QB: teams * STARTERS.QB, RB: teams * STARTERS.RB, WR: teams * STARTERS.WR, TE: teams * STARTERS.TE};
    const lineup = {...direct};
    const rostered = {...direct};
    const ranked = universe.filter(player => Number.isFinite(player.preseasonRank)).sort((a, b) => {
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

  // Each boundary sits at the cutoff for the LAST player of its division
  // (2026-09-19, user directive): Starter = last startable player
  // (dedicated starters + flex share), Bench = last benchable player
  // (last rostered), Waiver = last waiver player shown on the chart.
  function rosterOrdinals() {
    const counts = allocationCounts();
    if (position === "ALL") return {
      starter: teams * (6 + FLEX_STARTERS),
      bench: teams * (6 + FLEX_STARTERS + BENCH_SPOTS),
      waiver: fullRankMax()
    };
    if (position === "FLEX") return {
      starter: counts.lineup.RB + counts.lineup.WR + counts.lineup.TE,
      bench: counts.rostered.RB + counts.rostered.WR + counts.rostered.TE,
      waiver: fullRankMax()
    };
    return {
      starter: counts.lineup[position],
      bench: counts.rostered[position],
      waiver: fullRankMax()
    };
  }

  function markerDefinitions() {
    const ordinals = rosterOrdinals();
    return [
      {key:"starter", ordinal:ordinals.starter, label:"Starter", color:"#238a52"},
      {key:"bench", ordinal:ordinals.bench, label:"Bench", color:"#d36a16"},
      {key:"waiver", ordinal:ordinals.waiver, label:"Waiver", color:"#c43d32", dotted:true}
    ];
  }

  // Vertical roster rank cutoffs under EVERY lock (2026-09-19, user
  // directive): Starter, Bench, and Waiver are always vertical lines at
  // the last player of their division -- last startable (dedicated +
  // flex), last benchable (last rostered), last waiver player shown.
  // No horizontal value thresholds under any lock.
  function boundaryMarkers() {
    return markerDefinitions().map(marker => ({
      ...marker,
      axis:"x",
      value:Math.max(1, Math.min(fullRankMax(), marker.ordinal))
    }));
  }

  function yAxisScale(rows) {
    const values = rows.flatMap(row => [...activeSources].map(key => row.values[key])).filter(Number.isFinite);
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
    SOURCE_KEYS.filter(key => activeSources.has(key)).forEach(key => {
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

    $("#legend").innerHTML = SOURCE_KEYS.filter(key => activeSources.has(key)).map(key => {
      const style = SOURCE_STYLES[key];
      const lineStyle = key.endsWith("_adjusted") ? "dashed" : "solid";
      return `<span><span class="sw" style="background:transparent;border-top:3px ${lineStyle} ${style.color}"></span>${sourceLabel(key)}</span>`;
    }).join("");
    const markerText = markers.map(marker => `${marker.label} rank ${marker.value}`).join(" · ");
    $("#curveFootnote").textContent = `${activeSources.size} of 8 sources shown · missing values break a line · vertical roster boundaries: ${markerText}.`;
    canvas.setAttribute("aria-label", "Eight independently toggleable trade value curves with player rank on the horizontal axis, trade value on the vertical axis, and vertical starter, bench, and waiver rank boundaries. Use Home or End, then the left and right arrow keys, to inspect each player.");
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
    const values = SOURCE_KEYS.filter(key => activeSources.has(key)).map(key => `<span class="tip-source"><i style="background:${SOURCE_STYLES[key].color}"></i>${sourceLabel(key)}</span><b>${Number.isFinite(row.values[key]) ? Number(row.values[key]).toFixed(1) : "—"}</b>`).join("");
    return `<strong>${rank}. ${row.name}</strong><span class="tip-meta">${row.pos} · ${row.team} · ${rankLabel}</span><span class="tip-grid">${values}</span>`;
  }

  function showTooltip(rank, clientX, clientY, above) {
    if (rank === null) return;
    crossRank = rank;
    tip.innerHTML = tooltipHtml(rank);
    tip.style.display = "block";
    const width = tip.offsetWidth, height = tip.offsetHeight;
    tip.style.left = `${Math.min(Math.max(clientX - width / 2, 8), window.innerWidth - width - 8)}px`;
    let top = above ? clientY - height - 24 : clientY + 16;
    if (top < 8) top = clientY + 18;
    if (top + height > window.innerHeight - 8) top = Math.max(8, window.innerHeight - height - 8);
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
    const visiblePeak = Math.max(...rows.flatMap(row => [...activeSources].map(key => row.values[key])).filter(Number.isFinite));
    const dynamicAxisCoversData = scale.max >= visiblePeak;
    const markers = boundaryMarkers();
    const rosterMarkers = markers.length === 3
      && markers.every((marker, index) => marker.axis === "x" && Number.isFinite(marker.value) && marker.label === ["Starter", "Bench", "Waiver"][index]);
    const diagnostics = {eightSources, eightToggles, noAggregate, stableDomain, validValues, distinctSourcePeaks, valuesAbove70, dynamicAxisCoversData, sourcePeaks, yAxisMax:scale.max, rosterMarkers, rosterMarkerAxis:"x", lockOrder, sourceCount:SOURCE_KEYS.length, activeCount:activeSources.size, curveCount:activeSources.size};
    window.DDFCurveDiagnostics = Object.freeze(diagnostics);
    const failed = Object.entries(diagnostics).filter(([key, value]) => ["eightSources", "eightToggles", "noAggregate", "stableDomain", "validValues", "distinctSourcePeaks", "valuesAbove70", "dynamicAxisCoversData", "rosterMarkers"].includes(key) && value !== true);
    if (failed.length) throw new Error(`Curve regression guard failed: ${failed.map(([key]) => key).join(", ")}`);
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
      makeSourceToggles();
      makeLockControl();
      bindZoom();
      resetZoom();
      runRegressionGuards();
      draw();
      $("#curve-status").classList.add("validated");
      $("#curve-status").innerHTML = "<strong>Validated:</strong> five independent source series plus three bias-corrected best-estimate series. FC Adjusted, USAT Adjusted, and FP Adjusted account for poor math by the other rankers. No median or blended composite line is plotted.";
      publishShared();
    } catch (error) {
      $("#curve-status").innerHTML = `<strong>Curves unavailable:</strong> ${String(error.message)}`;
      console.error(error);
    }
  }

  init();
})();
