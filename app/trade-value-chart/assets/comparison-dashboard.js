(() => {
  "use strict";

  const POSITIONS = ["QB", "RB", "WR", "TE"];
  const POSITION_ORDER = ["QB", "RB", "WR", "TE"];
  const SOURCE_KEYS = [
    "usatoday",
    "fantasycalc",
    "fantasypros",
    "cbs",
    "fantasycalc_adjusted",
    "usatoday_adjusted",
    "fantasypros_adjusted",
    "espn"
  ];
  const LABELS = {
    usatoday: "USA Today",
    fantasycalc: "FantasyCalc",
    fantasypros: "FantasyPros",
    cbs: "CBS",
    fantasycalc_adjusted: "FC Adjusted",
    usatoday_adjusted: "USAT Adjusted",
    fantasypros_adjusted: "FP Adjusted",
    espn: "ESPN"
  };
  const TIPS = {
    usatoday: "Editorial chart, as published and reindexed",
    fantasycalc: "Crowd-sourced values, as published and reindexed",
    fantasypros: "Analyst-consensus chart, as published and reindexed",
    cbs: "Editorial chart, as published and reindexed",
    fantasycalc_adjusted: "Bias-corrected best estimate accounting for poor math by the other rankers",
    usatoday_adjusted: "Bias-corrected best estimate accounting for poor math by the other rankers",
    fantasypros_adjusted: "Bias-corrected best estimate accounting for poor math by the other rankers",
    espn: "ESPN projections translated to the common scale"
  };
  const state = {
    scoring: "full",
    teams: 12,
    compareSource: "preseason",
    combos: {},
    sort: {column: "preseason", direction: "asc"},
    filters: {position: "ALL", search: ""},
    columns: null
  };

  const root = document.getElementById("comparisonDashboard");
  if (!root) return;
  const $ = selector => root.querySelector(selector);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  const has = (object, key) => Object.prototype.hasOwnProperty.call(object || {}, key);
  const scoreLabel = score => ({standard:"Standard", half:"Half PPR", full:"Full PPR"}[score] || score);
  const clampValue = value => {
    if (value === null || value === undefined || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? Math.max(0, number) : null;
  };
  const formatValue = value => value === null ? "—" : Number(value).toFixed(1);
  const sourceLabel = key => LABELS[key] || key;
  const lockLabel = key => key === "preseason" ? "Preseason rank" : key === "disagreement" ? "Largest disagreement" : sourceLabel(key);
  const isLockKey = key => ["preseason","disagreement",...SOURCE_KEYS].includes(key);

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
  let universeSize = 0;
  let renderKeys = [];
  let sourceMaps = new Map();
  let referenceSource = "usatoday";

  function comboKeyFor(key) {
    const score = (key.endsWith("_adjusted") && state.scoring === "standard") ? "std" : state.scoring;
    if (key === "fantasycalc") return `${score}_${state.teams}_qb1`;
    if (key === "espn") return `${score}_${state.teams}`;
    if (key === "fantasycalc_adjusted") return `${score}_12_qb1`;
    return `${score}_12`;
  }

  function canonicalPlayers() {
    const payload = JSON.parse(document.getElementById("players-data")?.textContent || "{}");
    const players = Array.isArray(payload.players) ? payload.players : [];
    const next = new Map();
    players.forEach(player => {
      const key = Number(player.player_key);
      if (!Number.isInteger(key) || key <= 0) return;
      const name = String(player.full_name || player.name || "").trim();
      if (!name || !POSITIONS.includes(player.pos)) return;
      const preseasonRank = Number(player.preseasonRank ?? player.preseason_ecr_rank);
      const ros = player.ecr_ros || {};
      next.set(key, {player_key:key, name, pos:player.pos, team:String(player.team || "—"), preseasonRank:Number.isFinite(preseasonRank) && preseasonRank > 0 ? preseasonRank : null, preseasonValue:{standard:Number(ros.standard), half_ppr:Number(ros.half_ppr), ppr:Number(ros.ppr)}});
    });
    return next;
  }

  function selectedCombo(key) {
    const comboKey = state.combos[key] || comboKeyFor(key);
    return data.sources?.[key]?.combos?.[comboKey] || null;
  }

  function buildSourceMap(key) {
    const combo = selectedCombo(key);
    const raw = combo?.values || combo?.reindexed || {};
    const native = combo?.native || {};
    const values = new Map();
    Object.entries(raw).forEach(([sourceId, rawValue]) => {
      if (["fantasypros","fantasypros_adjusted"].includes(key) && !has(native,sourceId)) return;
      const mapped = data.player_keys?.[sourceId];
      const playerKey = Number(mapped);
      if (!Number.isInteger(playerKey) || !canonicalByKey.has(playerKey)) return;
      const value = clampValue(rawValue);
      if (value === null) return;
      if (values.has(playerKey) && values.get(playerKey) !== value) {
        throw new Error(`Conflicting values for canonical player ${playerKey} in ${sourceLabel(key)}.`);
      }
      values.set(playerKey, value);
    });
    return values;
  }

  function rebuildSourceMaps() {
    sourceMaps = new Map(renderKeys.map(key => [key, buildSourceMap(key)]));
  }

  function visibleKeys() {
    const cols = Array.isArray(state.columns) ? state.columns.filter(key => renderKeys.includes(key)) : renderKeys;
    return cols.length ? cols : renderKeys;
  }

  function sourceValue(key, playerKey) {
    return sourceMaps.get(key)?.has(playerKey) ? sourceMaps.get(key).get(playerKey) : null;
  }

  function sourceDate(key) {
    const source = data.sources[key] || {};
    if (key.endsWith("_adjusted")) {
      const match = String(source.fit_bake_id || "").match(/(\d{4}-\d{2}-\d{2})/);
      return match ? `fit ${new Intl.DateTimeFormat("en-US", {month:"short", day:"numeric", timeZone:"UTC"}).format(new Date(`${match[1]}T00:00:00Z`))}` : "fit date unavailable";
    }
    const raw = source.published || source.espn_snapshot || source.fetched_at;
    if (!raw) return "date unavailable";
    const date = new Date(String(raw).slice(0, 10) + "T00:00:00Z");
    return Number.isNaN(date.getTime()) ? "date unavailable" : `content ${new Intl.DateTimeFormat("en-US", {month:"short", day:"numeric", timeZone:"UTC"}).format(date)}`;
  }

  function sourceMeta(key) {
    const coverage = sourceMaps.get(key)?.size || 0;
    return `${coverage}/${universeSize} · ${sourceDate(key)}`;
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
    segments($("#ourScoring"), [["standard","Standard"],["half","Half PPR"],["full","Full PPR"]], state.scoring, value => {
      state.scoring = value;
      SOURCE_KEYS.forEach(key => { state.combos[key] = comboKeyFor(key); });
      rebuildSourceMaps();
      renderAll();
      window.DDFCurveControls?.setScoring(value);
    }, "three");
    segments($("#ourTeams"), [[8,"8"],[10,"10"],[12,"12"],[14,"14"]], state.teams, value => {
      state.teams = Number(value);
      state.combos.fantasycalc = comboKeyFor("fantasycalc");
      state.combos.espn = comboKeyFor("espn");
      rebuildSourceMaps();
      renderAll();
      window.DDFCurveControls?.setTeams(value);
    }, "four");
    if ($("#ourContext")) $("#ourContext").textContent = `${scoreLabel(state.scoring)} · ${state.teams} teams · common source scale`;
    if ($("#leagueSummary")) $("#leagueSummary").textContent = `League settings: ${scoreLabel(state.scoring)} · ${state.teams} teams`;
  }

  function renderSourceCards() {
    const container = $("#sourceCards");
    if (!container) return;
    container.innerHTML = renderKeys.map(key => `<article class="source-card" title="${esc(TIPS[key])}"><div><h2 class="source-title">${esc(sourceLabel(key))}</h2><p class="source-kind">${esc(sourceMeta(key))}</p></div></article>`).join("");
  }

  function renderColumnToggles() {
    const container = $("#columnToggles");
    if (!container) return;
    const visible = visibleKeys();
    container.innerHTML = renderKeys.map(key => `<button type="button" class="column-chip" data-column="${esc(key)}" aria-pressed="${String(visible.includes(key))}" title="${esc(TIPS[key])}">${esc(sourceLabel(key))}</button>`).join("");
    container.querySelectorAll("[data-column]").forEach(button => button.addEventListener("click", () => {
      const key = button.dataset.column;
      let next = visibleKeys().filter(item => item !== key);
      if (!visible.includes(key)) next = [...visibleKeys(), key].filter((item, index, all) => all.indexOf(item) === index);
      next = renderKeys.filter(item => next.includes(item));
      if (!next.length) return;
      state.columns = next;
      renderColumnToggles();
      renderTable();
    }));
  }

  function setLockOrder(value, publish = true) {
    if (!isLockKey(value)) return;
    if (SOURCE_KEYS.includes(value)) {
      referenceSource = value;
      window.DDF_REFERENCE_SOURCE = referenceSource;
      if (publish) window.dispatchEvent(new CustomEvent("ddf-reference-source-change", {detail:{source:referenceSource}}));
    }
    if (value === state.compareSource) return;
    state.compareSource = value;
    state.sort = {column:value, direction:value === "preseason" ? "asc" : "desc"};
    renderViewControls();
    renderTable();
    if (publish) {
      window.DDF_LOCK_ORDER = value;
      window.DDFCurveControls?.setLockOrder(value, false);
    }
  }

  function renderViewControls() {
    segments($("#viewTabs"), [["all","Source series"],["source","DDF comparison — start of season only",true,"Only available at start of season"]], "all", () => {}, "two");
    $("#sourcePickerWrap")?.classList.add("active");
    const options = [
      ["preseason","Preseason rank",false,"Position-grouped preseason rank; unranked players last within each position"],
      ["disagreement","Largest disagreement",false,"Widest spread across all available source values first"],
      ...SOURCE_KEYS.filter(key => renderKeys.includes(key)).map(key => [key, sourceLabel(key), false, TIPS[key]])
    ];
    segments($("#sourcePicker"), options, state.compareSource, value => setLockOrder(value), "lock-options");
  }

  function renderFilters() {
    segments($("#positionFilter"), [["ALL","All"],["QB","QB"],["RB","RB"],["WR","WR"],["TE","TE"],["FLEX","Flex"]], state.filters.position, value => {
      state.filters.position = value;
      renderFilters();
      renderTable();
      window.DDFCurveControls?.setPosition(value);
    }, "six");
    $("#directionField")?.classList.add("is-hidden");
    $("#minDeltaField")?.classList.add("is-hidden");
    $("#filtersGrid")?.classList.add("filters-simple");
    if ($("#playerSearch")) $("#playerSearch").value = state.filters.search;
  }

  function rows() {
    const ids = new Set();
    sourceMaps.forEach(map => map.forEach((_, key) => ids.add(key)));
    return [...ids].map(playerKey => {
      const player = canonicalByKey.get(playerKey);
      if (!player?.name || !POSITIONS.includes(player.pos)) return null;
      const values = Object.fromEntries(renderKeys.map(key => [key, sourceValue(key, playerKey)]));
      const priced = renderKeys.map(key => values[key]).filter(Number.isFinite);
      return {...player, ...values, disagreement:priced.length >= 2 ? Math.max(...priced) - Math.min(...priced) : null};
    }).filter(Boolean);
  }

  function filteredRows() {
    const query = state.filters.search.trim().toLowerCase();
    const list = rows().filter(row => state.filters.position === "ALL" || (state.filters.position === "FLEX" ? ["RB","WR","TE"].includes(row.pos) : row.pos === state.filters.position)).filter(row => !query || row.name.toLowerCase().includes(query));
    const {column, direction} = state.sort;
    const sign = direction === "asc" ? 1 : -1;
    return list.sort((a, b) => {
      if (column === "preseason") {
        if (["ALL","FLEX"].includes(state.filters.position)) {
          const posDifference = POSITION_ORDER.indexOf(a.pos) - POSITION_ORDER.indexOf(b.pos);
          if (posDifference) return posDifference;
        }
        const av = a.preseasonRank, bv = b.preseasonRank;
        const aMissing = !Number.isFinite(av), bMissing = !Number.isFinite(bv);
        if (aMissing !== bMissing) return aMissing ? 1 : -1;
        if (!aMissing && av !== bv) return av - bv;
        return POSITION_ORDER.indexOf(a.pos) - POSITION_ORDER.indexOf(b.pos) || a.name.localeCompare(b.name) || a.player_key - b.player_key;
      }
      const av = column === "name" ? a.name : a[column];
      const bv = column === "name" ? b.name : b[column];
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
    if (key === "name") return `<th><span class="sort-label">${esc(label)}</span></th>`;
    const active = state.sort.column === key;
    const aria = active ? state.sort.direction === "asc" ? "ascending" : "descending" : "none";
    const badge = key === "espn" ? "projection-derived" : (key.endsWith("_adjusted") ? "bias adjusted" : "as published · reindexed");
    return `<th aria-sort="${aria}"><button class="sortable" type="button" data-sort="${esc(key)}" title="Lock order to ${esc(sourceLabel(key))} values, highest first"><span class="sort-label">${esc(label)}</span><span class="source-badge">${esc(badge)}</span></button></th>`;
  }

  function renderTable() {
    const list = filteredRows();
    if ($("#boardTitle")) $("#boardTitle").textContent = "Eight-source trade value board";
    if ($("#boardDescription")) $("#boardDescription").textContent = "A source comparison with five independent series and three bias-corrected best-estimate series. FC Adjusted, USAT Adjusted, and FP Adjusted account for poor math by the other rankers.";
    if ($("#consensusNote")) $("#consensusNote").textContent = "No median or blended composite is shown. Missing values show as —, never zero.";
    if ($("#resultCount")) $("#resultCount").textContent = `${list.length} player${list.length === 1 ? "" : "s"}`;
    if ($("#sortNote")) {
      $("#sortNote").textContent = state.sort.column === "preseason"
        ? (["ALL","FLEX"].includes(state.filters.position) ? "Grouped by position, then preseason rank (unranked players last)" : "Locked to preseason positional rank, ascending (unranked players last)")
        : state.sort.column === "disagreement"
          ? "Locked by widest cross-source spread first"
          : state.sort.column === "name"
            ? `Sorted by player, ${state.sort.direction === "asc" ? "A to Z" : "Z to A"}`
            : `Locked to ${sourceLabel(state.sort.column)} value, high to low; missing values last`;
    }
    const wrap = $("#tableWrap");
    if (!list.length) {
      wrap.innerHTML = '<div class="empty">No players match these filters.</div>';
      return;
    }
    const keys = visibleKeys();
    const head = `<tr>${sortHeader("name", "Player")}${keys.map(key => sortHeader(key, sourceLabel(key))).join("")}</tr>`;
    const body = list.map(row => `<tr class="row-main"><td data-label="Player"><strong>${esc(row.name)}</strong><span class="name-sub">${esc(row.pos)} · ${esc(row.team)}${Number.isFinite(row.preseasonRank) ? ` · preseason rank ${row.preseasonRank}` : " · preseason unranked"}</span></td>${keys.map(key => `<td data-label="${esc(sourceLabel(key))}">${formatValue(row[key])}</td>`).join("")}</tr>`).join("");
    wrap.innerHTML = `<table class="all-table"><thead>${head}</thead><tbody>${body}</tbody></table>`;
    wrap.querySelectorAll("[data-sort]").forEach(button => button.addEventListener("click", () => {
      const key = button.dataset.sort;
      if (key !== "name") {
        setLockOrder(key);
        return;
      }
      if (state.sort.column === key) state.sort.direction = state.sort.direction === "asc" ? "desc" : "asc";
      else state.sort = {column:key, direction:"asc"};
      renderViewControls();
      renderTable();
    }));
  }

  function renderDataNotes() {
    if ($("#freshness")) $("#freshness").textContent = `Full PPR default · ${renderKeys.map(key => `${sourceLabel(key)} ${sourceMeta(key)}`).join(" · ")}`;
  }

  function exportState() {
    return {version:5, settings:{scoring:state.scoring, teams:state.teams}, sort:{...state.sort}, filters:{...state.filters}, columns:[...visibleKeys()]};
  }

  function applyImport(raw) {
    if (!raw || typeof raw !== "object") throw new Error("That file is not a dashboard state object.");
    const scoring = raw.settings?.scoring;
    const teams = Number(raw.settings?.teams);
    if (!["standard","half","full"].includes(scoring) || ![8,10,12,14].includes(teams)) throw new Error("League scoring or team count is not valid.");
    state.scoring = scoring;
    state.teams = teams;
    if (["ALL","QB","RB","WR","TE","FLEX"].includes(raw.filters?.position)) state.filters.position = raw.filters.position;
    state.filters.search = String(raw.filters?.search || "").slice(0, 80);
    if (["preseason","disagreement",...renderKeys].includes(raw.sort?.column)) {
      state.sort.column = raw.sort.column;
      state.compareSource = raw.sort.column;
      state.sort.direction = raw.sort.column === "preseason" ? "asc" : "desc";
    }
    const columns = Array.isArray(raw.columns) ? raw.columns.filter(key => renderKeys.includes(key)) : null;
    state.columns = columns && columns.length ? columns : [...renderKeys];
    SOURCE_KEYS.forEach(key => { state.combos[key] = comboKeyFor(key); });
    rebuildSourceMaps();
    renderAll();
  }

  function bindStatic() {
    $("#playerSearch")?.addEventListener("input", event => { state.filters.search = event.target.value; renderTable(); });
    $("#exportButton")?.addEventListener("click", () => {
      const blob = new Blob([JSON.stringify(exportState(), null, 2)], {type:"application/json"});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `published-trade-charts-${String(data.built_at || "snapshot").slice(0,10)}.json`;
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
    renderLeagueControls();
    renderSourceCards();
    renderColumnToggles();
    renderViewControls();
    renderFilters();
    renderDataNotes();
    renderTable();
  }

  window.DDFComparisonControls = {
    refresh: () => data && renderAll(),
    setLockOrder: value => data && setLockOrder(value, false),
    applyShared: shared => {
      const scoring = ({standard:"standard", half_ppr:"half", ppr:"full", half:"half", full:"full"})[shared?.scoring];
      if (scoring && scoring !== state.scoring) {
        state.scoring = scoring;
        SOURCE_KEYS.forEach(key => { state.combos[key] = comboKeyFor(key); });
        rebuildSourceMaps();
        renderAll();
      }
      const sharedTeams = Number(shared?.teams);
      if ([8,10,12,14].includes(sharedTeams) && sharedTeams !== state.teams) {
        state.teams = sharedTeams;
        SOURCE_KEYS.forEach(key => { state.combos[key] = comboKeyFor(key); });
        rebuildSourceMaps();
        renderAll();
      }
      if (["ALL","QB","RB","WR","TE","FLEX"].includes(shared?.position)) {
        state.filters.position = shared.position;
        renderFilters();
        renderTable();
      }
      if (isLockKey(shared?.lockOrder)) setLockOrder(shared.lockOrder, false);
    }
  };
  window.addEventListener("ddf-shared-change", event => window.DDFComparisonControls.applyShared(event.detail));
  window.addEventListener("ddf-lock-order-change", event => window.DDFComparisonControls.setLockOrder(event.detail?.lockOrder));
  window.addEventListener("ddf-reference-source-change", event => {
    if (SOURCE_KEYS.includes(event.detail?.source)) referenceSource = event.detail.source;
  });

  function runRegressionGuards() {
    const list = filteredRows();
    const groups = ["ALL","FLEX"].includes(state.filters.position)
      ? POSITION_ORDER.map(pos => list.filter(row => row.pos === pos)).filter(group => group.length)
      : [list];
    const ranksAscending = groups.every(group => {
      const ranked = group.filter(row => Number.isFinite(row.preseasonRank));
      return ranked.every((row, index) => index === 0 || ranked[index - 1].preseasonRank <= row.preseasonRank);
    });
    const missingLast = groups.every(group => {
      const firstMissing = group.findIndex(row => !Number.isFinite(row.preseasonRank));
      return firstMissing === -1 || group.slice(firstMissing).every(row => !Number.isFinite(row.preseasonRank));
    });
    const positionGrouped = !["ALL","FLEX"].includes(state.filters.position) || list.every((row, index) => index === 0 || POSITION_ORDER.indexOf(list[index - 1].pos) <= POSITION_ORDER.indexOf(row.pos));
    const eightSources = renderKeys.length === 8 && SOURCE_KEYS.every(key => renderKeys.includes(key));
    const fullPpr12TeamQbs = state.scoring === "full" && state.teams === 12 && rows().filter(row => row.pos === "QB").length;
    const fullPpr12TeamQbsAvailable = fullPpr12TeamQbs > 0;
    const diagnostics = {ranksAscending, missingLast, positionGrouped, eightSources, fullPpr12TeamQbsAvailable, fullPpr12TeamQbs, sourceCount:renderKeys.length};
    window.DDFComparisonDiagnostics = Object.freeze(diagnostics);
    if (!ranksAscending || !missingLast || !positionGrouped || !eightSources || !fullPpr12TeamQbsAvailable) throw new Error("Comparison regression guard failed.");
  }

  async function init() {
    try {
      data = await loadComparisonData();
      universeSize = Object.keys(data.player_keys || {}).length;
      canonicalByKey = canonicalPlayers();
      if (!canonicalByKey.size) throw new Error("Canonical player records are unavailable.");
      renderKeys = SOURCE_KEYS.filter(key => data.source_validation?.[key] === "live");
      if (renderKeys.length !== SOURCE_KEYS.length) throw new Error("One or more required comparison sources did not pass validation.");
      if (!Array.isArray(state.columns)) state.columns = [...renderKeys];
      if (SOURCE_KEYS.includes(window.DDF_REFERENCE_SOURCE)) referenceSource = window.DDF_REFERENCE_SOURCE;
      window.DDF_REFERENCE_SOURCE = referenceSource;
      SOURCE_KEYS.forEach(key => { state.combos[key] = comboKeyFor(key); });
      rebuildSourceMaps();
      bindStatic();
      renderAll();
      runRegressionGuards();
      if (isLockKey(window.DDF_LOCK_ORDER)) setLockOrder(window.DDF_LOCK_ORDER, false);
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
