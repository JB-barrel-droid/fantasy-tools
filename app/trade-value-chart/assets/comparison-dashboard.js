(() => {
  "use strict";

  const POSITIONS = ["QB", "RB", "WR", "TE"];
  const SOURCE_KEYS = [
    "usatoday",
    "fantasycalc",
    "fantasypros",
    "cbs",
    "cbsros",
    "razzball",
    "cbs_adjusted",
    "fantasycalc_adjusted",
    "usatoday_adjusted",
    "fantasypros_adjusted",
    "espn",
    "espn_vorp",
    "cbsros_vorp",
    "razzball_vorp"
  ];
  const DEFAULT_FLEX_ELIGIBLE = Object.freeze(["RB", "WR", "TE"]);
  const DEFAULT_BENCH_SHARE = 0.15;
  const LABELS = {
    usatoday: "USA Today",
    fantasycalc: "FantasyCalc",
    fantasypros: "FantasyPros",
    cbs: "CBS",
    cbsros: "CBS ROS",
    razzball: "Razzball",
    cbs_adjusted: "CBS Adjusted",
    fantasycalc_adjusted: "FC Adjusted",
    usatoday_adjusted: "USAT Adjusted",
    fantasypros_adjusted: "FP Adjusted",
    espn: "ESPN adjusted",
    espn_vorp: "ESPN raw VORP vs waivers",
    cbsros_vorp: "CBS ROS raw VORP vs waivers",
    razzball_vorp: "Razzball raw VORP vs waivers"
  };
  const TIPS = {
    usatoday: "Editorial chart, as published and reindexed",
    fantasycalc: "Crowd-sourced values, as published and reindexed",
    fantasypros: "Analyst-consensus chart, as published and reindexed",
    cbs: "Editorial chart, as published and reindexed",
    cbsros: "CBS rest-of-season projections, computed like ESPN's VORP vs waivers leg",
    razzball: "Razzball rest-of-season projections, computed like ESPN's VORP vs waivers leg",
    cbs_adjusted: "Derived from CBS values and the current adjustment ratios, then rescaled to the common value pie",
    fantasycalc_adjusted: "Adjusted best estimate shifting the weighting to our view of value",
    usatoday_adjusted: "Adjusted best estimate shifting the weighting to our view of value",
    fantasypros_adjusted: "Adjusted best estimate shifting the weighting to our view of value",
    espn: "ESPN VORP vs waivers split by starter, bench, and waiver tier from the shared league settings",
    espn_vorp: "ESPN VORP vs waivers before starter/bench utilization",
    cbsros_vorp: "CBS ROS VORP vs waivers before starter/bench utilization",
    razzball_vorp: "Razzball VORP vs waivers before starter/bench utilization"
  };
  // Pure raw value-above-waivers columns (JEG-38): projection-minus-waiver
  // VORP from each source's own per-game projections. Mirrors the chart's
  // "Raw value above waivers" curve group.
  const VORP_SOURCE_DEFS = {
    espn_vorp: {ppgField: "espn_ppg", short: "ESPN", validationKey: "espn"},
    cbsros_vorp: {ppgField: "cbsros_ppg", short: "CBS ROS", validationKey: "cbsros"},
    razzball_vorp: {ppgField: "rz_ppg", short: "Razzball", validationKey: "razzball"},
  };
  const PURE_VORP_KEYS = ["espn_vorp", "cbsros_vorp", "razzball_vorp"];
  // The chart's default roster (curve-widget.js DEFAULT_ROSTER) and the saved
  // published setup (ValueModel.SAVED_SETUP_SHAPE). The table used to default
  // to WR2/FLEX2, so on first load it derived every published column instead
  // of showing the saved values the chart above it showed (JEG332-VORP-VIEWS).
  const DEFAULT_ROSTER_SHAPE = Object.freeze({QB:1, RB:2, WR:3, TE:1, FLEX:1, SUPERFLEX:0, BENCH:6});
  const state = {
    scoring: "full",
    teams: 12,
    rosterShape: {...DEFAULT_ROSTER_SHAPE},
    benchShare: DEFAULT_BENCH_SHARE,
    compareSource: "espn",
    combos: {},
    sort: {column: "espn", direction: "desc"},
    filters: {position: "ALL", search: ""},
    columns: null
  };
  const FIELD_COLUMNS = [
    {key:"pos", label:"Pos", badge:"field"},
    {key:"team", label:"Team", badge:"field"},
    {key:"espn_role", label:"ESPN tier", badge:"role"},
    {key:"disagreement", label:"Disagreement", badge:"spread"}
  ];

  const root = document.getElementById("comparisonDashboard");
  if (!root) return;
  const $ = selector => root.querySelector(selector);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  const scoreLabel = score => ({standard:"Standard", half:"Half PPR", full:"Full PPR"}[score] || score);
  const scoreField = () => state.scoring === "full" ? "ppr" : state.scoring === "half" ? "half_ppr" : "standard";
  const formatValue = value => value === null ? "—" : Number(value).toFixed(1);
  const WEEKED_SOURCE_KEYS = new Set(["usatoday", "fantasycalc", "fantasypros", "cbs", "cbsros", "razzball", "cbs_adjusted", "fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted"]);
  // GAP-043 / GAP-CHART-STALE-LABEL-CALENDAR: week labels and stale flags
  // read the one freshness record (product-data getSourceFreshness():
  // week_designated, then content_vintage, on the Tuesday-flip content
  // calendar). No global-week fallback: a series nothing dates gets no week.
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
    return label ? label(freshnessRow(key)).text : "content week unknown";
  }

  function weekForSource(key) {
    if (!WEEKED_SOURCE_KEYS.has(key)) return null;
    const week = freshnessRow(key)?.vintage_week;
    return Number.isFinite(week) ? week : null;
  }

  function activeReferenceWeek() {
    return sourceFreshness()?.current_content_week || null;
  }

  // Current unless the freshness record says the source is an older week.
  function isWeekCurrent(key) {
    return freshnessRow(key)?.status !== "older";
  }

  function sourceLabel(key) {
    const base = LABELS[key] || key;
    const week = weekForSource(key);
    return week && key !== "espn" ? `${base} Wk ${week}` : base;
  }
  const lockLabel = key => key === "disagreement" ? "Largest disagreement" : sourceLabel(key);
  const isLockKey = key => ["disagreement",...SOURCE_KEYS].includes(key);

  // JEG-363 (2026-10-04): all legacy fixture reads delegated to product-data.js.
  // product-data.js is the ONLY module that talks to the FE contract; this
  // dashboard calls into its five semantic methods and transitional helpers
  // instead of touching assets/* paths or the #players-data inline island.
  function loadComparisonData() {
    if (window.TradeValueProductData && window.TradeValueProductData.initProductData) {
      return window.TradeValueProductData.initProductData().then(() => {
        const snap = window.TradeValueProductData.getSnapshot();
        // Expose the snapshot under the legacy global name so any out-of-tree
        // consumer keeps working.
        window.TradeValueComparisonData = snap;
        return snap;
      });
    }
    return Promise.reject(new Error("product-data.js missing; render refused."));
  }

  let data = null;
  let canonicalByKey = new Map();
  let universeSize = 0;
  let renderKeys = [];
  let sourceMaps = new Map();
  let engineAvailableKeys = new Set();
  let valuesLoaded = false;
  let espnRoleByKey = new Map();
  let referenceSource = "usatoday";

  const flexEligiblePositions = () => DEFAULT_FLEX_ELIGIBLE;

  function comboKeyFor(key) {
    if (PURE_VORP_KEYS.includes(key)) return null;
    return ValueModel.sourceComboKey(key, state.scoring, state.teams, 1);
  }

  function sourceComboExists(key) {
    // Pure VORP columns are browser-computed from each source's per-game
    // projections on the player records; they exist when the source's
    // projections exist.
    if (PURE_VORP_KEYS.includes(key)) {
      const field = VORP_SOURCE_DEFS[key].ppgField;
      return [...canonicalByKey.values()].some(p => Number.isFinite(Number(p[field]?.[scoreField()])));
    }
    // league-settings-001: a published chart and its adjusted column exist at
    // every league setting when the saved 12-team setup for this scoring does.
    // (Self-contained on purpose: tests/test_source_combo_contract.py runs
    // this function extracted from the file.)
    const publishedBase = key === "cbs_adjusted" ? "cbs" : key.replace(/_adjusted$/, "");
    if (["usatoday", "fantasycalc", "fantasypros", "cbs"].includes(publishedBase)) {
      return Boolean((typeof window !== "undefined" && window.TradeValueProductData)
        ? window.TradeValueProductData.getPlayerValues({source: key === "cbs_adjusted" ? "cbs" : key,
            scoring: state.scoring, teams: ValueModel.SAVED_SETUP_TEAMS, qbVariant: "qb1", view: "combo_reindexed"})
        : null);
    }
    // JEG-363: sourceComboExists reads via product-data.js (api.player_values).
    if (key === "cbs_adjusted") {
      return Boolean((typeof window !== "undefined" && window.TradeValueProductData)
        ? window.TradeValueProductData.getPlayerValues({source: "cbs", scoring: state.scoring, teams: state.teams, qbVariant: "qb1", view: "combo_reindexed"})
        : null);
    }
    return Boolean((typeof window !== "undefined" && window.TradeValueProductData)
      ? window.TradeValueProductData.getPlayerValues({source: key, scoring: state.scoring, teams: state.teams, qbVariant: "qb1", view: "combo_reindexed"})
      : null);
  }

  const sourceIsStale = key => WEEKED_SOURCE_KEYS.has(key) && !isWeekCurrent(key);

  // GAP-MAIN-TABLE-ESPN-DRIFT (2026-10-08): every value in this table is the
  // chart engine's own value, read from TradeValueCurveControls.getAllRows()
  // -- the maps the chart draws and getRows() returns. The table used to
  // re-derive each column with a second copy of the value math. That copy
  // drifted from the engine (ESPN, published charts, CBS ROS / Razzball), and
  // its *_adjusted columns depended on which script finished loading first:
  // baked adjustment cells when the table built before the chart, the chart's
  // live refit cells when it built after. The table now renders only after the
  // engine reports a completed build, and re-reads it after every rebuild.
  const engine = () => window.TradeValueCurveControls || null;
  const engineReady = () => Boolean(engine()?.isReady?.());
  const ENGINE_SCORING = {ppr:"full", half_ppr:"half", standard:"standard"};

  // A column is available exactly when the chart can draw that series.
  function sourceAvailable(key) {
    return engineAvailableKeys.has(key);
  }

  function canonicalPlayers() {
    // JEG-363 (2026-10-04): canonical players come from product-data.js
    // (api.players surface). The inline #players-data island is read only by
    // product-data.js; this widget never touches it.
    const players = (typeof window !== "undefined" && window.TradeValueProductData)
      ? window.TradeValueProductData.getPlayers()
      : [];
    const next = new Map();
    players.forEach(player => {
      const key = Number(player.player_key);
      if (!Number.isInteger(key) || key <= 0) return;
      const name = String(player.canonical_name || player.full_name || player.name || "").trim();
      if (!name || !POSITIONS.includes(player.pos)) return;
      next.set(key, {
        player_key:key,
        name,
        pos:player.pos,
        team:String(player.team || "—"),
        espn_ppg:player.espn_ppg || null,
        // sourceComboExists reads each raw-VORP column's own projections.
        cbsros_ppg:player.cbsros_ppg || null,
        rz_ppg:player.rz_ppg || null,
        espn_projects_zero:player.espn_projects_zero === true
      });
    });
    return next;
  }

  function rebuildSourceMaps() {
    const controls = engine();
    const engineState = controls.getState();
    state.scoring = ENGINE_SCORING[engineState.scoring] || state.scoring;
    state.teams = Number(engineState.teams);
    state.benchShare = Number(engineState.benchShare);
    state.rosterShape = {...controls.getRosterShape()};
    // The chart's view (Indexed / VORP vs waivers / Adjusted values) decides
    // which values the published-chart columns carry; the badge says which.
    state.viewMode = engineState.viewMode || "indexed";
    state.viewTitle = engineState.viewTitle || null;
    SOURCE_KEYS.forEach(key => { state.combos[key] = comboKeyFor(key); });
    engineAvailableKeys = new Set(controls.getSourceInfo().filter(info => info.available).map(info => info.key));
    sourceMaps = new Map(SOURCE_KEYS.map(key => [key, new Map()]));
    espnRoleByKey = new Map();
    controls.getAllRows().forEach(row => {
      espnRoleByKey.set(row.player_key, row.espnRole);
      SOURCE_KEYS.forEach(key => {
        const value = row.values?.[key];
        if (typeof value === "number" && Number.isFinite(value)) sourceMaps.get(key).set(row.player_key, value);
      });
    });
    valuesLoaded = true;
  }

  function selectedCombo(key) {
    // JEG-363: returns the contract-shaped api.player_values row for the
    // active (scoring, teams) cell; downstream code reads .values / .index_total.
    if (typeof window === "undefined" || !window.TradeValueProductData) return null;
    return window.TradeValueProductData.getPlayerValues({
      source: key,
      scoring: state.scoring,
      teams: state.teams,
      qbVariant: "qb1",
      view: "combo_reindexed",
    });
  }

  function allColumnKeys() {
    return [...FIELD_COLUMNS.map(column => column.key), ...renderKeys.filter(sourceAvailable)];
  }

  function visibleColumns() {
    const allowed = new Set(allColumnKeys());
    const defaults = ["pos", "team", "espn_role", "disagreement", "espn", "espn_vorp", "cbsros_vorp", "razzball_vorp", "fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted", "cbs_adjusted"].filter(key => allowed.has(key));
    const cols = Array.isArray(state.columns) ? state.columns.filter(key => allowed.has(key)) : defaults;
    return cols.length ? cols : defaults;
  }

  // The engine's row value as-is: the ESPN-0 (GAP-025) and below-leg
  // (GAP-ESPN-BELOW-LEG) 0.0 rules live in curve-widget.js rowValue only.
  function sourceValue(key, playerKey) {
    if (!sourceAvailable(key)) return null;
    const map = sourceMaps.get(key);
    return map?.has(playerKey) ? map.get(playerKey) : null;
  }

  // Content week from the freshness record; adjusted series add their fit date.
  function sourceDate(key) {
    const text = freshnessText(key);
    if (!key.endsWith("_adjusted")) return text;
    const snap = window.TradeValueProductData?.getSnapshot?.() || null;
    const sources = (snap && snap.sources) || {};
    const source = sources[key] || (key === "cbs_adjusted" ? sources.cbs : null) || {};
    const match = String(source.fit_bake_id || "").match(/(\d{4})-?(\d{2})-?(\d{2})/);
    const fit = match ? `fit ${new Intl.DateTimeFormat("en-US", {month:"short", day:"numeric", timeZone:"UTC"}).format(new Date(`${match[1]}-${match[2]}-${match[3]}T00:00:00Z`))}` : "fit date unavailable";
    return `${text} · ${fit}`;
  }

  function sourceMeta(key) {
    const coverage = sourceMaps.get(key)?.size || 0;
    if (!sourceComboExists(key)) return `Not available for ${scoreLabel(state.scoring)} · ${state.teams} teams`;
    const basis = key.startsWith("fantasycalc") ? " · 1 QB" : "";
    return `${coverage}/${universeSize} · ${sourceDate(key)}${basis}`;
  }

  function columnLabel(key) {
    return FIELD_COLUMNS.find(column => column.key === key)?.label || sourceLabel(key);
  }

  function columnBadge(key) {
    if (SOURCE_KEYS.includes(key)) {
      if (key === "espn") return "utilization adjusted";
      if (PURE_VORP_KEYS.includes(key)) return "raw VORP vs waivers";
      if (key.endsWith("_adjusted")) return "bias adjusted";
      // DDF-methodology legs (razzball, cbsros) are computed from the
      // publisher's projections with our value-above-waivers method — they
      // are not the publisher's published values reindexed. Read the method
      // from the fixture, not the key name, so future DDF legs label honestly.
      if (data?.sources?.[key]?.method_group === "ddf-methodology") return "DDF methodology";
      return "as published · reindexed";
    }
    return FIELD_COLUMNS.find(column => column.key === key)?.badge || "field";
  }

  // Outside the Indexed view the chart (and so this table) carries that
  // view's values for the published charts; their badge names the view.
  function headerBadge(key) {
    const viewed = state.viewMode && state.viewMode !== "indexed" && state.viewTitle
      && ["usatoday", "fantasycalc", "fantasypros", "cbs"].includes(key);
    return viewed ? `as published · ${state.viewTitle}` : columnBadge(key);
  }

  function sortValue(row, column) {
    if (column === "name") return row.name;
    if (column === "espn_role") return row.espn_role;
    return row[column];
  }

  function displayValue(row, column) {
    if (column === "pos") return row.pos;
    if (column === "team") return row.team;
    if (column === "espn_role") return row.espn_role || "waiver";
    if (column === "disagreement") return formatValue(row.disagreement);
    return formatValue(row[column]);
  }

  function segments(container, options, active, onClick, className = "") {
    if (!container) return;
    container.className = `segments ${className}`.trim();
    container.innerHTML = options.map(([value, label, disabled, title]) => `<button type="button" data-value="${esc(value)}" aria-pressed="${String(value) === String(active)}"${disabled ? " disabled" : ""}${title ? ` title="${esc(title)}"` : ""}>${esc(label)}</button>`).join("");
    container.querySelectorAll("button").forEach(button => button.addEventListener("click", () => {
      if (!button.disabled) onClick(button.dataset.value);
    }));
  }

  function renderLeagueControls() {
    if ($("#ourContext")) $("#ourContext").textContent = `${scoreLabel(state.scoring)} · ${state.teams} teams · common source scale`;
    if ($("#leagueSummary")) $("#leagueSummary").textContent = `League settings: ${scoreLabel(state.scoring)} · ${state.teams} teams`;
  }

  function renderSourceCards() {
    const container = $("#sourceCards");
    if (!container) return;
    container.innerHTML = renderKeys.map(key => {
      const available = sourceAvailable(key);
      const stale = sourceIsStale(key) && available;
      return `<article class="source-card${available ? "" : " is-disabled"}${stale ? " is-stale" : ""}" title="${esc(available ? TIPS[key] : sourceMeta(key))}"><div><h2 class="source-title">${esc(sourceLabel(key))}</h2><p class="source-kind">${esc(sourceMeta(key))}</p></div></article>`;
    }).join("");
  }

  function renderColumnToggles() {
    const container = $("#columnToggles");
    if (!container) return;
    const visible = visibleColumns();
    const columns = allColumnKeys();
    container.innerHTML = columns.map(key => `<button type="button" class="column-chip" data-column="${esc(key)}" aria-pressed="${String(visible.includes(key))}" title="${esc(TIPS[key] || `Show ${columnLabel(key)} in the player table`)}">${esc(columnLabel(key))}</button>`).join("");
    container.querySelectorAll("[data-column]").forEach(button => button.addEventListener("click", () => {
      const key = button.dataset.column;
      let next = visibleColumns().filter(item => item !== key);
      if (!visible.includes(key)) next = [...visibleColumns(), key].filter((item, index, all) => all.indexOf(item) === index);
      next = columns.filter(item => next.includes(item));
      if (!next.length) return;
      state.columns = next;
      renderColumnToggles();
      renderTable();
    }));
  }

  function setLockOrder(value, publish = true) {
    if (!isLockKey(value)) return;
    if (SOURCE_KEYS.includes(value) && !sourceAvailable(value)) return;
    if (SOURCE_KEYS.includes(value)) {
      referenceSource = value;
      window.TradeValueReferenceSource = referenceSource;
      if (publish) window.dispatchEvent(new CustomEvent("trade-value-reference-source-change", {detail:{source:referenceSource}}));
    }
    if (value === state.compareSource) return;
    state.compareSource = value;
    state.sort = {column:value, direction:"desc"};
    renderViewControls();
    renderTable();
    if (publish) {
      window.TradeValueLockOrder = value;
      window.TradeValueCurveControls?.setLockOrder(value, false);
    }
  }

  function renderViewControls() {
  }

  function renderFilters() {
    segments($("#positionFilter"), [["ALL","All"],["QB","QB"],["RB","RB"],["WR","WR"],["TE","TE"],["FLEX","Flex"]], state.filters.position, value => {
      state.filters.position = value;
      renderFilters();
      renderTable();
      window.TradeValueCurveControls?.setPosition(value);
    }, "six");
    $("#directionField")?.classList.add("is-hidden");
    $("#minDeltaField")?.classList.add("is-hidden");
    $("#filtersGrid")?.classList.add("filters-simple");
    if ($("#playerSearch")) $("#playerSearch").value = state.filters.search;
  }

  function rows() {
    const ids = new Set();
    renderKeys.filter(sourceAvailable).forEach(sourceKey => sourceMaps.get(sourceKey)?.forEach((_, key) => ids.add(key)));
    return [...ids].map(playerKey => {
      const player = canonicalByKey.get(playerKey);
      if (!player?.name || !POSITIONS.includes(player.pos)) return null;
      const values = Object.fromEntries(renderKeys.map(key => [key, sourceValue(key, playerKey)]));
      // Frame 22: VORP vs waivers columns are a different unit from the
      // trade-value point scale; the spread covers only the point-scale series.
      const priced = renderKeys.filter(key => !PURE_VORP_KEYS.includes(key)).map(key => values[key]).filter(Number.isFinite);
      return {...player, espn_role:espnRoleByKey.get(playerKey) || "waiver", ...values, disagreement:priced.length >= 2 ? Math.max(...priced) - Math.min(...priced) : null};
    }).filter(Boolean);
  }

  function filteredRows() {
    const query = state.filters.search.trim().toLowerCase();
    const list = rows().filter(row => state.filters.position === "ALL" || (state.filters.position === "FLEX" ? flexEligiblePositions().includes(row.pos) : row.pos === state.filters.position)).filter(row => !query || row.name.toLowerCase().includes(query));
    const {column, direction} = state.sort;
    const sign = direction === "asc" ? 1 : -1;
    return list.sort((a, b) => {
      const av = sortValue(a, column);
      const bv = sortValue(b, column);
      const aMissing = av === null || av === undefined || (typeof av === "number" && !Number.isFinite(av));
      const bMissing = bv === null || bv === undefined || (typeof bv === "number" && !Number.isFinite(bv));
      if (aMissing && bMissing) return a.name.localeCompare(b.name);
      if (aMissing) return 1;
      if (bMissing) return -1;
      const compared = typeof av === "string" ? av.localeCompare(bv) : Number(av) - Number(bv);
      return compared * sign || a.name.localeCompare(b.name);
    });
  }

  function sortHeader(key, label) {
    const active = state.sort.column === key;
    const aria = active ? state.sort.direction === "asc" ? "ascending" : "descending" : "none";
    return `<th aria-sort="${aria}"><button class="sortable ${key === "name" ? "left" : ""}" type="button" data-sort="${esc(key)}" title="Sort table by ${esc(label)}"><span class="sort-label">${esc(label)}</span>${key === "name" ? "" : `<span class="source-badge">${esc(headerBadge(key))}</span>`}</button></th>`;
  }

  function nextSortDirection(key) {
    if (state.sort.column === key) return state.sort.direction === "asc" ? "desc" : "asc";
    return ["name", "pos", "team"].includes(key) ? "asc" : "desc";
  }

  function setTableSort(key) {
    if (!["name", ...allColumnKeys()].includes(key)) return;
    if (SOURCE_KEYS.includes(key) && !sourceAvailable(key)) return;
    if (SOURCE_KEYS.includes(key)) {
      referenceSource = key;
      window.TradeValueReferenceSource = key;
      window.dispatchEvent(new CustomEvent("trade-value-reference-source-change", {detail:{source:key}}));
      window.TradeValueLockOrder = key;
      window.TradeValueCurveControls?.setLockOrder(key, false);
    }
    if (["disagreement", ...SOURCE_KEYS].includes(key)) state.compareSource = key;
    state.sort = {column:key, direction:nextSortDirection(key)};
    renderViewControls();
    renderTable();
  }

  function renderTable() {
    const list = filteredRows();
    if ($("#boardTitle")) $("#boardTitle").textContent = "Compare player values";
    if ($("#boardDescription")) $("#boardDescription").textContent = "Search and sort players using the graph's league settings.";
    if ($("#consensusNote")) $("#consensusNote").textContent = "Missing source values show —, never zero.";
    if ($("#resultCount")) $("#resultCount").textContent = `${list.length} player${list.length === 1 ? "" : "s"}`;
    if ($("#sortNote")) {
      $("#sortNote").textContent = state.sort.column === "disagreement"
          ? "Locked by widest cross-source spread first"
          : state.sort.column === "name"
            ? `Sorted by player, ${state.sort.direction === "asc" ? "A to Z" : "Z to A"}`
            : SOURCE_KEYS.includes(state.sort.column)
              ? `Locked to ${sourceLabel(state.sort.column)} value, ${state.sort.direction === "asc" ? "low to high" : "high to low"}; missing values last`
              : `Sorted by ${columnLabel(state.sort.column)}, ${state.sort.direction === "asc" ? "ascending" : "descending"}; missing values last`;
    }
    const wrap = $("#tableWrap");
    if (!valuesLoaded) {
      wrap.innerHTML = '<div class="empty">Loading values from the chart.</div>';
      return;
    }
    if (!list.length) {
      wrap.innerHTML = '<div class="empty">No players match these filters.</div>';
      return;
    }
    const keys = visibleColumns();
    const head = `<tr>${sortHeader("name", "Player")}${keys.map(key => sortHeader(key, columnLabel(key))).join("")}</tr>`;
    const body = list.map(row => {
      // GAP-025 (was JEG-50): badge players ESPN projects at 0 (injured/out),
      // from the player's own ESPN fields; published values stay as published.
      // A player ESPN has no row for is missing, not 0, and gets no badge.
      const zero = row.espn_projects_zero ? window.TradeValueProductData?.ESPN_ZERO_BADGE : null;
      const zeroBadge = zero ? ` <span class="espn-zero-badge" data-espn-zero title="${esc(zero.title)}"><span aria-hidden="true">${zero.symbol}</span> ${esc(zero.label)}</span>` : "";
      const nameCell = `<strong>${esc(row.name)}</strong>${zeroBadge}`;
      return `<tr class="row-main" data-player-key="${row.player_key}"><td data-label="Player">${nameCell}<span class="name-sub">${esc(row.pos)} · ${esc(row.team)}</span></td>${keys.map(key => `<td data-label="${esc(columnLabel(key))}">${esc(displayValue(row, key))}</td>`).join("")}</tr>`;
    }).join("");
    wrap.innerHTML = `<table class="all-table"><thead>${head}</thead><tbody>${body}</tbody></table>`;
    wrap.querySelectorAll("[data-sort]").forEach(button => button.addEventListener("click", () => {
      setTableSort(button.dataset.sort);
    }));
  }

  function renderDataNotes() {
    if ($("#freshness")) {
      // GAP-043: name each source on an older content week, with its own
      // week, against the reader's current content week.
      const staleKeys = renderKeys.filter(sourceIsStale);
      const currentWeek = activeReferenceWeek();
      const staleLabel = staleKeys.length
        ? `${staleKeys.length} source${staleKeys.length === 1 ? "" : "s"} older than Week ${currentWeek}: ${staleKeys.map(key => `${LABELS[key] || key} ${weekForSource(key) ? `Week ${weekForSource(key)}` : "undated"}`).join(", ")}`
        : (currentWeek ? `all sources on Week ${currentWeek}` : "content week unknown");
      $("#freshness").textContent = `${scoreLabel(state.scoring)} · ${state.teams} teams · ${staleLabel}`;
    }
  }

  function ensureAvailableSelection() {
    if (SOURCE_KEYS.includes(state.sort.column) && !sourceAvailable(state.sort.column)) {
      state.sort = {column:"espn", direction:"desc"};
      state.compareSource = "espn";
    }
    if (SOURCE_KEYS.includes(state.compareSource) && !sourceAvailable(state.compareSource)) state.compareSource = "espn";
    if (SOURCE_KEYS.includes(referenceSource) && !sourceAvailable(referenceSource)) {
      referenceSource = renderKeys.find(sourceAvailable) || "espn";
      window.TradeValueReferenceSource = referenceSource;
    }
    // NOTE (2026-10-01): state.columns is intentionally NOT pruned here.
    // visibleColumns() already filters the user's selection against the
    // currently-available keys at render time. Pruning state.columns
    // destructively here would permanently lose the user's column picks
    // when cycling through a scoring/teams combo where those columns are
    // unavailable (e.g. a paused *_adjusted combo) and back again.
  }

  function exportState() {
    return {version:8, settings:{scoring:state.scoring, teams:state.teams, benchShare:state.benchShare}, sort:{...state.sort}, filters:{...state.filters}, columns:[...visibleColumns()]};
  }

  function applyImport(raw) {
    if (!raw || typeof raw !== "object") throw new Error("That file is not a dashboard state object.");
    const scoring = raw.settings?.scoring;
    const teams = Number(raw.settings?.teams);
    if (!["standard","half","full"].includes(scoring) || ![8,10,12,14].includes(teams)) throw new Error("League scoring or team count is not valid.");
    const importedBenchShare = Number(raw.settings?.benchShare ?? raw.settings?.absenceRate);
    if (["ALL","QB","RB","WR","TE","FLEX"].includes(raw.filters?.position)) state.filters.position = raw.filters.position;
    state.filters.search = String(raw.filters?.search || "").slice(0, 80);
    if (["name","pos","team","espn_role","disagreement",...renderKeys].includes(raw.sort?.column)) {
      state.sort.column = raw.sort.column;
      state.compareSource = raw.sort.column;
      state.sort.direction = raw.sort.direction === "asc" ? "asc" : "desc";
    }
    const allowed = new Set(allColumnKeys());
    const columns = Array.isArray(raw.columns) ? raw.columns.filter(key => allowed.has(key)) : null;
    state.columns = columns && columns.length ? columns : visibleColumns();
    // League settings belong to the chart engine; each setter rebuilds it and
    // the table re-reads the result (trade-value-rows-change).
    const controls = engine();
    controls?.setScoring(scoring);
    controls?.setTeams(teams);
    if (Number.isFinite(importedBenchShare)) controls?.setBenchShareFraction(importedBenchShare);
    syncFromEngine();
  }

  function bindStatic() {
    $("#playerSearch")?.addEventListener("input", event => { state.filters.search = event.target.value; renderTable(); });
    $("#exportButton")?.addEventListener("click", () => {
      const blob = new Blob([JSON.stringify(exportState(), null, 2)], {type:"application/json"});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `published-trade-charts-${String((typeof window !== "undefined" && window.TradeValueProductData ? window.TradeValueProductData.getSnapshot().built_at : null) || "snapshot").slice(0,10)}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      $("#stateStatus").textContent = "Exported comparison settings.";
    });
    $("#toggleImport")?.addEventListener("click", () => {
      const open = !$("#importBox").classList.contains("open");
      $("#importBox").classList.toggle("open", open);
      $("#toggleImport").setAttribute("aria-expanded", String(open));
    });
    $("#applyImport")?.addEventListener("click", () => {
      try {
        applyImport(JSON.parse($("#importText").value));
        $("#stateStatus").className = "status ok";
        $("#stateStatus").textContent = "Imported comparison settings.";
      } catch (error) {
        $("#stateStatus").className = "status warn";
        $("#stateStatus").textContent = error.message;
      }
    });
  }

  function renderAll() {
    ensureAvailableSelection();
    renderLeagueControls();
    renderSourceCards();
    renderColumnToggles();
    renderViewControls();
    renderFilters();
    renderDataNotes();
    renderTable();
  }

  // Re-read the engine and re-render. Called once the engine has finished
  // its first build and after every engine rebuild; a no-op until both this
  // table's own data and the engine are ready, whichever lands last.
  function syncFromEngine() {
    if (!data || !engineReady()) return;
    rebuildSourceMaps();
    renderAll();
    runRegressionGuards();
  }

  window.TradeValueComparisonControls = {
    refresh: () => data && renderAll(),
    setLockOrder: value => data && setLockOrder(value, false),
    // League settings, roster, bench share and weights arrive with the
    // engine's own rebuild (trade-value-rows-change); only view state is
    // taken from the shared record.
    applyShared: shared => {
      if (["ALL","QB","RB","WR","TE","FLEX"].includes(shared?.position)) {
        state.filters.position = shared.position;
        renderFilters();
        renderTable();
      }
      if (isLockKey(shared?.lockOrder)) setLockOrder(shared.lockOrder, false);
    }
  };
  window.addEventListener("trade-value-shared-change", event => window.TradeValueComparisonControls.applyShared(event.detail));
  window.addEventListener("trade-value-rows-change", () => syncFromEngine());
  window.addEventListener("trade-value-lock-order-change", event => window.TradeValueComparisonControls.setLockOrder(event.detail?.lockOrder));
  window.addEventListener("trade-value-reference-source-change", event => {
    if (SOURCE_KEYS.includes(event.detail?.source)) referenceSource = event.detail.source;
  });

  function runRegressionGuards() {
    const allSources = renderKeys.length === SOURCE_KEYS.length && SOURCE_KEYS.every(key => renderKeys.includes(key));
    const fullPpr12TeamQbs = state.scoring === "full" && state.teams === 12 && rows().filter(row => row.pos === "QB").length;
    const fullPpr12TeamQbsAvailable = state.scoring !== "full" || state.teams !== 12 || fullPpr12TeamQbs > 0;
    const availableSources = renderKeys.filter(sourceAvailable);
    const configurableColumns = FIELD_COLUMNS.every(column => allColumnKeys().includes(column.key)) && availableSources.every(key => allColumnKeys().includes(key));
    // Current vintage does not imply a chart exists for every league size.
    // league-settings-001 (JEG-332): a published chart's data for any league
    // size is its saved 12-team setup (other sizes are derived from it), so
    // that is the cell that must exist; every other source needs its own cell.
    const savedBaseCell = key => window.TradeValueProductData.getPlayerValues({
      source: key, scoring: state.scoring, teams: ValueModel.SAVED_SETUP_TEAMS, qbVariant: "qb1", view: "combo_reindexed"});
    const rolloverAware = renderKeys.every(key => !sourceComboExists(key)
      ? !allColumnKeys().includes(key)
      : PURE_VORP_KEYS.includes(key)
        || (["usatoday", "fantasycalc", "fantasypros", "cbs"].includes(key === "cbs_adjusted" ? "cbs" : key.replace(/_adjusted$/, ""))
          ? Boolean(savedBaseCell(key === "cbs_adjusted" ? "cbs" : key))
          : Boolean(selectedCombo(key === "cbs_adjusted" ? "cbs" : key))));
    const diagnostics = {allSources, fullPpr12TeamQbsAvailable, fullPpr12TeamQbs, configurableColumns, rolloverAware, scoring:state.scoring, teams:state.teams, sourceCount:renderKeys.length, availableSourceCount:availableSources.length, activeReferenceWeek:activeReferenceWeek()};
    window.TradeValueComparisonDiagnostics = Object.freeze(diagnostics);
    const failed = Object.entries(diagnostics).filter(([key, value]) => ["allSources", "fullPpr12TeamQbsAvailable", "configurableColumns", "rolloverAware"].includes(key) && value !== true);
    if (failed.length) throw new Error(`Comparison regression guard failed: ${failed.map(([key]) => key).join(", ")}`);
  }

  async function init() {
    try {
      const loaded = await loadComparisonData();
      universeSize = (typeof window !== "undefined" && window.TradeValueProductData)
        ? window.TradeValueProductData.getPlayers().length
        : 0;
      canonicalByKey = canonicalPlayers();
      if (!canonicalByKey.size) throw new Error("Canonical player records are unavailable.");
      // Pure VORP columns validate against their own source's projections
      // (each VORP curve is computed from that source's per-game numbers).
      const validationKeyFor = key => PURE_VORP_KEYS.includes(key) ? VORP_SOURCE_DEFS[key].validationKey : (key === "cbs_adjusted" ? "cbs" : key);
      // JEG-363: source_validation via api.product_snapshot.source_validation.
      const srcValidation = (typeof window !== "undefined" && window.TradeValueProductData)
        ? window.TradeValueProductData.getSnapshot().source_validation || {}
        : {};
      renderKeys = SOURCE_KEYS.filter(key => srcValidation[validationKeyFor(key)] === "live");
      if (renderKeys.length !== SOURCE_KEYS.length) throw new Error("One or more required comparison sources did not pass validation.");
      if (SOURCE_KEYS.includes(window.TradeValueReferenceSource)) referenceSource = window.TradeValueReferenceSource;
      window.TradeValueReferenceSource = referenceSource;
      bindStatic();
      // Values come from the engine; until it has built, the table says so.
      data = loaded;
      if (engineReady()) syncFromEngine();
      else renderTable();
      if (window.TradeValueSharedState) window.TradeValueComparisonControls.applyShared(window.TradeValueSharedState);
      if (isLockKey(window.TradeValueLockOrder)) setLockOrder(window.TradeValueLockOrder, false);
    } catch (error) {
      const message = `Source dates unavailable · ${error.message}`;
      if ($("#freshness")) $("#freshness").textContent = message;
      if ($("#resultCount")) $("#resultCount").textContent = "Unavailable";
      $("#tableWrap").innerHTML = `<div class="empty">The comparison data could not be loaded. ${esc(error.message)}</div>`;
      console.error(error);
    }
  }

  init();
})();
