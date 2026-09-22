(() => {
  "use strict";

  const POSITIONS = ["QB", "RB", "WR", "TE"];
  const POSITION_ORDER = ["QB", "RB", "WR", "TE"];
  const SOURCE_KEYS = [
    "usatoday",
    "fantasycalc",
    "fantasypros",
    "cbs",
    "cbs_adjusted",
    "fantasycalc_adjusted",
    "usatoday_adjusted",
    "fantasypros_adjusted",
    "espn",
    "espn_vorp"
  ];
  const DEFAULT_FLEX_ELIGIBLE = Object.freeze(["RB", "WR", "TE"]);
  const DEFAULT_BENCH_SHARE = 0.15;
  const LABELS = {
    usatoday: "USA Today (Week 2)",
    fantasycalc: "FantasyCalc (Week 2)",
    fantasypros: "FantasyPros (Week 2)",
    cbs: "CBS (Week 2)",
    cbs_adjusted: "CBS Adjusted (Week 2)",
    fantasycalc_adjusted: "FC Adjusted (Week 2)",
    usatoday_adjusted: "USAT Adjusted (Week 2)",
    fantasypros_adjusted: "FP Adjusted (Week 2)",
    espn: "ESPN adjusted",
    espn_vorp: "ESPN raw value above waivers"
  };
  const TIPS = {
    usatoday: "Editorial chart, as published and reindexed",
    fantasycalc: "Crowd-sourced values, as published and reindexed",
    fantasypros: "Analyst-consensus chart, as published and reindexed",
    cbs: "Editorial chart, as published and reindexed",
    cbs_adjusted: "Derived from CBS values and the current adjustment ratios, then rescaled to the common value pie",
    fantasycalc_adjusted: "Adjusted best estimate shifting the weighting to our view of value",
    usatoday_adjusted: "Adjusted best estimate shifting the weighting to our view of value",
    fantasypros_adjusted: "Adjusted best estimate shifting the weighting to our view of value",
    espn: "ESPN value above waivers split by starter, bench, and waiver tier from the shared league settings",
    espn_vorp: "ESPN value above waivers before starter/bench utilization"
  };
  const state = {
    scoring: "full",
    teams: 12,
    rosterShape: {QB:1, RB:2, WR:2, TE:1, FLEX:2, BENCH:6},
    benchShare: DEFAULT_BENCH_SHARE,
    compareSource: "espn",
    combos: {},
    sort: {column: "espn", direction: "desc"},
    filters: {position: "ALL", search: ""},
    columns: null,
    expanded: new Set()
  };
  const FIELD_COLUMNS = [
    {key:"pos", label:"Pos", badge:"field"},
    {key:"team", label:"Team", badge:"field"},
    {key:"espn_role", label:"ESPN tier", badge:"role"},
    {key:"disagreement", label:"Disagreement", badge:"spread"},
    {key:"latest_news", label:"Latest news", badge:"context"}
  ];

  const root = document.getElementById("comparisonDashboard");
  if (!root) return;
  const $ = selector => root.querySelector(selector);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  const has = (object, key) => Object.prototype.hasOwnProperty.call(object || {}, key);
  const scoreLabel = score => ({standard:"Standard", half:"Half PPR", full:"Full PPR"}[score] || score);
  const scoreField = () => state.scoring === "full" ? "ppr" : state.scoring === "half" ? "half_ppr" : "standard";
  const clampValue = value => {
    if (value === null || value === undefined || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? Math.max(0, number) : null;
  };
  const formatValue = value => value === null ? "—" : Number(value).toFixed(1);
  const WEEKED_SOURCE_KEYS = new Set(["usatoday", "fantasycalc", "fantasypros", "cbs", "cbs_adjusted", "fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted"]);
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
    const base = LABELS[key] || key;
    const week = weekForSource(key);
    return week && key !== "espn" ? `${base} Wk ${week}` : base;
  }
  const lockLabel = key => key === "disagreement" ? "Largest disagreement" : sourceLabel(key);
  const isLockKey = key => ["disagreement",...SOURCE_KEYS].includes(key);

  function loadComparisonData() {
    if (window.TradeValueComparisonData) return Promise.resolve(window.TradeValueComparisonData);
    if (!window.TradeValueComparisonDataPromise) {
      window.TradeValueComparisonDataPromise = fetch("assets/comparison-sources-data.json")
        .then(response => {
          if (!response.ok) throw new Error(`Data request failed (${response.status})`);
          return response.json();
        })
        .then(payload => {
          window.TradeValueComparisonData = payload;
          return payload;
        });
    }
    return window.TradeValueComparisonDataPromise;
  }

  function loadPlayerNews() {
    if (window.TradeValuePlayerNews) return Promise.resolve(window.TradeValuePlayerNews);
    if (!window.TradeValuePlayerNewsPromise) {
      window.TradeValuePlayerNewsPromise = fetch("assets/player-news.json")
        .then(response => response.ok ? response.json() : {meta:{}, news_by_player_key:{}, adjustments_by_player_key:{}})
        .catch(() => ({meta:{}, news_by_player_key:{}, adjustments_by_player_key:{}}))
        .then(payload => {
          window.TradeValuePlayerNews = payload;
          return payload;
        });
    }
    return window.TradeValuePlayerNewsPromise;
  }

  let data = null;
  let canonicalByKey = new Map();
  let universeSize = 0;
  let renderKeys = [];
  let sourceMaps = new Map();
  let espnRowsCache = null;
  let espnRoleByKey = new Map();
  let referenceSource = "usatoday";
  let newsMeta = {};
  let newsByPlayerKey = new Map();
  let adjustmentsByPlayerKey = new Map();

  function comboKeyFor(key) {
    const score = (key.endsWith("_adjusted") && state.scoring === "standard") ? "std" : state.scoring;
    if (key === "fantasycalc" || key === "fantasycalc_adjusted") return `${score}_${state.teams}_qb1`;
    if (key === "espn") return `${score}_${state.teams}`;
    if (key === "espn_vorp") return null;
    if (key === "cbs_adjusted") return comboKeyFor("cbs");
    return `${score}_${state.teams}`;
  }

  function sourceComboExists(key) {
    if (key === "espn_vorp") return Boolean(data?.sources?.espn?.combos?.[comboKeyFor("espn")]);
    if (key === "cbs_adjusted") return Boolean(data?.sources?.cbs?.combos?.[comboKeyFor("cbs")]);
    return Boolean(data?.sources?.[key]?.combos?.[comboKeyFor(key)]);
  }

  const sourceIsStale = key => WEEKED_SOURCE_KEYS.has(key) && !isWeekCurrent(key);

  function sourceAvailable(key) {
    return sourceComboExists(key);
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
      const ros = player.ecr_ros || {};
      next.set(key, {
        player_key:key,
        name,
        pos:player.pos,
        team:String(player.team || "—"),
        espn_ppg:player.espn_ppg || null
      });
    });
    return next;
  }

  const flexEligiblePositions = (shape = state.rosterShape) => shape.SUPERFLEX ? ["QB", ...DEFAULT_FLEX_ELIGIBLE] : [...DEFAULT_FLEX_ELIGIBLE];

  // Ranked by ESPN projected points, not a preseason positional rank.
  function allocationCountsFor(pool, shape = state.rosterShape) {
    const field = scoreField();
    return ValueModel.allocationCounts({
      pool,
      teams: state.teams,
      shape,
      rankOf: player => Number(player.espn_ppg?.[field])
    });
  }

  function rosterIsDefault() {
    const base = {QB:1, RB:2, WR:2, TE:1, FLEX:2, BENCH:6};
    return Object.keys(base).every(key => Number(state.rosterShape[key]) === base[key]);
  }

  function applyRosterShape(values, key) {
    if (rosterIsDefault() || key === "espn" || key === "espn_vorp") return values;
    const shaped = new Map(values);
    const defaultCounts = allocationCountsFor([...canonicalByKey.values()], {QB:1, RB:2, WR:3, TE:1, FLEX:1, BENCH:6});
    const customCounts = allocationCountsFor([...canonicalByKey.values()], state.rosterShape);
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
    const scale = totalBefore > 0 && totalAfter > 0 ? totalBefore / totalAfter : 1;
    shaped.forEach((value, playerKey) => shaped.set(playerKey, value * scale));
    return shaped;
  }

  function espnTargetTotal(pos, fallback) {
    const combo = data.sources?.espn?.combos?.[comboKeyFor("espn")];
    const target = Number(combo?.index_total?.[pos]?.target_total);
    return Number.isFinite(target) && target > 0 ? target : fallback;
  }

  function sourceTargetTotal(key) {
    const sourceKey = key === "cbs_adjusted" ? "cbs" : key;
    const combo = data.sources?.[sourceKey]?.combos?.[comboKeyFor(sourceKey)];
    const totals = Object.values(combo?.index_total || {}).map(item => Number(item?.target_total)).filter(Number.isFinite);
    return totals.reduce((sum, value) => sum + value, 0);
  }

  function commonFixedPieTotal(fallback) {
    const totals = SOURCE_KEYS
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

  function buildPublishedSourceMap(key) {
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

  // Shared with the curve widget via ValueModel -- one implementation only.
  function roleMapForValues(values) {
    return ValueModel.roleMap({
      values,
      playerOf: playerKey => canonicalByKey.get(playerKey),
      teams: state.teams,
      shape: state.rosterShape
    });
  }

  function normalizeTradeChartToFixedPie(values, anchor = null) {
    return ValueModel.normalizeToFixedPie({
      values,
      anchor,
      share: state.benchShare,
      playerOf: playerKey => canonicalByKey.get(playerKey),
      teams: state.teams,
      shape: state.rosterShape,
      fallbackTarget: commonFixedPieTotal
    });
  }

  function compareEspnPlayers(a, b) {
    return b.ppg - a.ppg || ValueModel.stableTiebreak(a.player, b.player);
  }

  function espnPricedRows() {
    const field = scoreField();
    return [...canonicalByKey.values()]
      .filter(player => POSITION_ORDER.includes(player.pos))
      .map(player => ({player, ppg:Number(player.espn_ppg?.[field])}))
      .filter(item => Number.isFinite(item.ppg))
      .sort(compareEspnPlayers);
  }

  function buildEspnRows() {
    if (espnRowsCache) return espnRowsCache;
    const priced = espnPricedRows();
    // Roles come from the shared model, ranked on surplus over each
    // position's dedicated-starter baseline. Assigning them here by raw
    // per-game points filled the bench with quarterbacks, collapsed the QB
    // waiver line and made Josh Allen the most valuable asset in a 1QB league.
    const ppgByKey = new Map(priced.map(row => [row.player.player_key, row.ppg]));
    const assigned = ValueModel.projectionRoles({
      pool: priced.map(row => row.player),
      teams: state.teams,
      shape: state.rosterShape,
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
    // Raw projection-minus-waiver VORP only. The published "ESPN-implied"
    // combo values are already run through a valuation model and carry a ~91%
    // starter share, which INVERTS the 85/15 fixed pie -- starters get marked
    // down instead of up. The curve widget was fixed for this; the table kept
    // the bug, which is why the same source read 76.5 here and 69.5 there.
    const withVorp = withRaw.map(row => ({
      ...row,
      rawVorp: row.role === "waiver" ? 0 : Math.max(0, row.rawProjectionVorp)
    }));
    const starterRaw = withVorp.filter(row => row.role === "starter").reduce((sum, row) => sum + row.rawVorp, 0);
    const benchRaw = withVorp.filter(row => row.role === "bench").reduce((sum, row) => sum + row.rawVorp, 0);
    const rawTotal = starterRaw + benchRaw;
    const targetTotal = espnTargetPool(rawTotal);
    const starterShare = Math.max(0, Math.min(1, 1 - state.benchShare));
    const normalizedBenchShare = Math.max(0, Math.min(1, state.benchShare));
    const rawScale = rawTotal > 0 && targetTotal > 0 ? targetTotal / rawTotal : 1;
    const starterScale = starterRaw > 0 && targetTotal > 0 ? (targetTotal * starterShare) / starterRaw : 0;
    const benchScale = benchRaw > 0 && targetTotal > 0 ? (targetTotal * normalizedBenchShare) / benchRaw : 0;
    // Per-position, per-tier scales: each position lands on its own pie and
    // splits state.benchShare the same way, so the pool-level identity holds too.
    // A single global pair of scales cannot do both, and skipping the pie is
    // what left quarterbacks at roughly double the published charts.
    const tierScales = ValueModel.positionalTierScales(
      withVorp.map(row => ({pos: row.player.pos, role: row.role, value: row.rawVorp})),
      pos => espnTargetTotal(pos, NaN),
      state.benchShare
    );
    espnRowsCache = withVorp.map(row => ({
      ...row,
      pure: row.rawVorp * rawScale,
      adjusted: row.role === "starter" ? row.rawVorp * (tierScales.starter[row.player.pos] || 0)
        : row.role === "bench" ? row.rawVorp * (tierScales.bench[row.player.pos] || 0) : 0
    }));
    espnRoleByKey = new Map(espnRowsCache.map(row => [row.player.player_key, row.role]));
    return espnRowsCache;
  }

  function espnVorpRows(pos) {
    return buildEspnRows().filter(row => row.player.pos === pos);
  }

  function buildEspnVorpMap() {
    const values = new Map();
    buildEspnRows().forEach(row => values.set(row.player.player_key, row.pure));
    return values;
  }

  function buildEspnIndexedMap() {
    const values = new Map();
    buildEspnRows().forEach(row => values.set(row.player.player_key, row.adjusted));
    return values;
  }

  function selectedCombo(key) {
    const comboKey = state.combos[key] || comboKeyFor(key);
    return data.sources?.[key]?.combos?.[comboKey] || null;
  }

  function buildSourceMap(key) {
    if (key === "espn") return buildEspnIndexedMap();
    if (key === "espn_vorp") return buildEspnVorpMap();
    if (key === "cbs_adjusted") return buildCbsAdjustedMap();
    return buildPublishedSourceMap(key);
  }

  function buildCbsAdjustedMap() {
    const direct = buildSourceMap("cbs");
    if (!direct.size) return new Map();
    const pairs = [
      ["fantasycalc", "fantasycalc_adjusted"],
      ["usatoday", "usatoday_adjusted"],
      ["fantasypros", "fantasypros_adjusted"]
    ];
    const existingMaps = new Map();
    pairs.flat().forEach(key => existingMaps.set(key, buildSourceMap(key)));
    const adjusted = new Map();
    direct.forEach((directValue, playerKey) => {
      const ratios = pairs.map(([rawKey, adjustedKey]) => {
        const raw = existingMaps.get(rawKey)?.get(playerKey);
        const adj = existingMaps.get(adjustedKey)?.get(playerKey);
        return Number.isFinite(raw) && raw > 0 && Number.isFinite(adj) ? adj / raw : null;
      }).filter(Number.isFinite);
      const ratio = ratios.length ? ratios.reduce((sum, value) => sum + value, 0) / ratios.length : 1;
      adjusted.set(playerKey, Math.max(0, directValue * ratio));
    });
    const targetCombo = data.sources?.cbs?.combos?.[comboKeyFor("cbs")];
    POSITION_ORDER.forEach(pos => {
      const rows = [...adjusted.entries()].filter(([playerKey]) => canonicalByKey.get(playerKey)?.pos === pos);
      const total = rows.reduce((sum, [, value]) => sum + value, 0);
      const target = Number(targetCombo?.index_total?.[pos]?.target_total);
      const scale = total > 0 && Number.isFinite(target) && target > 0 ? target / total : 1;
      rows.forEach(([playerKey, value]) => adjusted.set(playerKey, value * scale));
    });
    return adjusted;
  }

  function rebuildSourceMaps() {
    espnRowsCache = null;
    espnRoleByKey = new Map();
    sourceMaps = new Map();
    // The anchor must exist before anything normalises against it. A source
    // normalised with no anchor silently falls back to the full-total basis,
    // which is what made a 124-player chart sit 30% above the anchor.
    const anchorMap = buildSourceMap("espn");
    sourceMaps.set("espn", anchorMap);
    renderKeys.filter(key => key !== "espn").forEach(key => {
      sourceMaps.set(key, key === "espn_vorp"
        ? buildSourceMap(key)
        : normalizeTradeChartToFixedPie(applyRosterShape(buildSourceMap(key), key), anchorMap));
    });
  }

  function allColumnKeys() {
    return [...FIELD_COLUMNS.map(column => column.key), ...renderKeys.filter(sourceAvailable)];
  }

  function visibleColumns() {
    const allowed = new Set(allColumnKeys());
    const defaults = ["pos", "team", "espn_role", "disagreement", "latest_news", "espn", "espn_vorp", "fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted", "cbs_adjusted"].filter(key => allowed.has(key));
    const cols = Array.isArray(state.columns) ? state.columns.filter(key => allowed.has(key)) : defaults;
    return cols.length ? cols : defaults;
  }

  function sourceValue(key, playerKey) {
    if (!sourceAvailable(key)) return null;
    return sourceMaps.get(key)?.has(playerKey) ? sourceMaps.get(key).get(playerKey) : null;
  }

  function sourceDate(key) {
    const source = data.sources[key] || (key === "cbs_adjusted" ? data.sources.cbs : key === "espn_vorp" ? data.sources.espn : {}) || {};
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
    if (!sourceComboExists(key)) return `Not available for ${scoreLabel(state.scoring)} · ${state.teams} teams`;
    const stale = sourceIsStale(key) ? ` · stale, waiting Week ${activeReferenceWeek()}` : "";
    if (sourceIsStale(key)) return `${coverage}/${universeSize} · ${sourceDate(key)}${stale}`;
    return `${coverage}/${universeSize} · ${sourceDate(key)}`;
  }

  function columnLabel(key) {
    return FIELD_COLUMNS.find(column => column.key === key)?.label || sourceLabel(key);
  }

  function columnBadge(key) {
    if (SOURCE_KEYS.includes(key)) return key === "espn" ? "utilization adjusted" : key === "espn_vorp" ? "raw value above waivers" : (key.endsWith("_adjusted") ? "bias adjusted" : "as published · reindexed");
    return FIELD_COLUMNS.find(column => column.key === key)?.badge || "field";
  }

  function tradePublishedAt() {
    const raw = newsMeta.trade_values_published_at || data?.built_at || "";
    const parsed = new Date(raw);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  function normalizeNewsEntry(entry) {
    if (!entry || typeof entry !== "object") return null;
    const title = String(entry.title || entry.headline || "").trim();
    if (!title) return null;
    const tags = [
      ...(Array.isArray(entry.tags) ? entry.tags : []),
      entry.category,
      entry.topic
    ].map(value => String(value || "").toLowerCase());
    const valueWords = /\b(injury|injured|practice|limited|out|questionable|doubtful|suspend|suspension|discipline|snap|role|starter|backup|depth|target|touch|carry|route|usage|trade|contract|holdout|return|active|inactive|bench|waiver|fantasy|value)\b/i;
    const personalOnly = /\b(birthday|wedding|charity|family|vacation|podcast|interview only)\b/i;
    const valueRelated = tags.some(tag => ["injury","availability","role","usage","depth","discipline","suspension","transaction","fantasy","player_value"].includes(tag)) || valueWords.test(title) || valueWords.test(String(entry.summary || ""));
    if (!valueRelated || personalOnly.test(title)) return null;
    const published = new Date(entry.published_at || entry.published || "");
    const publishedAt = Number.isNaN(published.getTime()) ? null : published;
    const valueDate = tradePublishedAt();
    const timing = publishedAt && valueDate ? (publishedAt > valueDate ? "fresher than values" : "older than values") : "timing unavailable";
    return {
      type: "news",
      title,
      url: String(entry.url || "").trim(),
      source: String(entry.source || "News").trim(),
      publishedAt,
      timing,
      summary: String(entry.summary || "").trim()
    };
  }

  function normalizeAdjustmentEntry(entry) {
    if (!entry || typeof entry !== "object") return null;
    const kind = String(entry.kind || "adjustment").trim();
    const status = String(entry.status || "").trim();
    const injury = String(entry.injury || "").trim();
    const title = `${kind.charAt(0).toUpperCase()}${kind.slice(1)} adjustment${status ? ` · ${status}` : ""}${injury ? ` · ${injury}` : ""}`;
    const published = new Date(entry.date || "");
    const publishedAt = Number.isNaN(published.getTime()) ? null : published;
    const valueDate = tradePublishedAt();
    const timing = publishedAt && valueDate ? (publishedAt > valueDate ? "pending after current values" : "priced or older than values") : "timing unavailable";
    const weeks = Array.isArray(entry.weeks_out_range) ? entry.weeks_out_range.filter(value => value !== null && value !== undefined).join("-") : "";
    const detail = [
      entry.note,
      weeks ? `Missed-games estimate: ${weeks}` : (entry.weeks_out !== null && entry.weeks_out !== undefined ? `Missed-games estimate: ${entry.weeks_out}` : ""),
      entry.skip_form ? "Skip most recent game form when pricing." : "",
      entry.beneficiary_review ? `Beneficiary review: ${entry.beneficiary_review}` : ""
    ].filter(Boolean).join(" ");
    return {
      type: "adjustment",
      title,
      url: "",
      source: String(entry.source || "Adjustment log").trim(),
      publishedAt,
      timing,
      summary: detail,
      consumed: Boolean(entry.consumed)
    };
  }

  function playerNews(playerKey) {
    return (newsByPlayerKey.get(Number(playerKey)) || []).map(normalizeNewsEntry).filter(Boolean);
  }

  function playerAdjustments(playerKey) {
    return (adjustmentsByPlayerKey.get(Number(playerKey)) || []).map(normalizeAdjustmentEntry).filter(Boolean);
  }

  function playerContext(playerKey) {
    return [...playerAdjustments(playerKey), ...playerNews(playerKey)].sort((a, b) => (b.publishedAt?.getTime() || 0) - (a.publishedAt?.getTime() || 0));
  }

  function latestNews(row) {
    return playerContext(row.player_key)[0] || null;
  }

  function formatDate(value) {
    if (!(value instanceof Date) || Number.isNaN(value.getTime())) return "date unavailable";
    return new Intl.DateTimeFormat("en-US", {month:"short", day:"numeric", timeZone:"UTC"}).format(value);
  }

  function sortValue(row, column) {
    if (column === "name") return row.name;
    if (column === "espn_role") return row.espn_role;
    if (column === "latest_news") return latestNews(row)?.publishedAt?.getTime() ?? null;
    return row[column];
  }

  function displayValue(row, column) {
    if (column === "pos") return row.pos;
    if (column === "team") return row.team;
    if (column === "espn_role") return row.espn_role || "waiver";
    if (column === "disagreement") return formatValue(row.disagreement);
    if (column === "latest_news") {
      const latest = latestNews(row);
      return latest ? `${formatDate(latest.publishedAt)} · ${latest.timing}` : "—";
    }
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
      const priced = renderKeys.map(key => values[key]).filter(Number.isFinite);
      return {...player, espn_role:espnRoleByKey.get(playerKey) || "waiver", ...values, disagreement:priced.length >= 2 ? Math.max(...priced) - Math.min(...priced) : null, newsCount:playerContext(playerKey).length};
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
    return `<th aria-sort="${aria}"><button class="sortable ${key === "name" ? "left" : ""}" type="button" data-sort="${esc(key)}" title="Sort table by ${esc(label)}"><span class="sort-label">${esc(label)}</span>${key === "name" ? "" : `<span class="source-badge">${esc(columnBadge(key))}</span>`}</button></th>`;
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

  function renderNewsList(row) {
    const items = playerNews(row.player_key);
    if (!items.length) return '<p class="news-empty">No player-value news is loaded for this player yet.</p>';
    // Very brief: max 3 items, truncated summaries, pre/post-values timing prominent.
    return `<ul class="news-list">${items.slice(0, 3).map(item => {
      const brief = item.summary ? (item.summary.length > 120 ? item.summary.slice(0, 117) + "…" : item.summary) : "";
      const timingBadge = item.timing === "fresher than values" ? "post-values" : item.timing === "older than values" ? "pre-values" : "timing n/a";
      return `<li><a href="${esc(item.url || "#")}"${item.url ? ' target="_blank" rel="noopener noreferrer"' : ""}>${esc(item.title)}</a>${brief ? `<p>${esc(brief)}</p>` : ""}<span>${esc(item.source)} · ${esc(formatDate(item.publishedAt))} · <strong>${esc(timingBadge)}</strong></span></li>`;
    }).join("")}</ul>`;
  }

  function renderAdjustmentList(row) {
    const items = playerAdjustments(row.player_key);
    if (!items.length) return "";
    return `<div class="adjustment-block"><h4>Valuation adjustments</h4><ul class="news-list adjustment-list">${items.slice(0, 4).map(item => `<li><strong>${esc(item.title)}</strong>${item.summary ? `<p>${esc(item.summary)}</p>` : ""}<span>${esc(item.source)} · ${esc(formatDate(item.publishedAt))} · ${esc(item.timing)}${item.consumed ? " · consumed" : " · pending"}</span></li>`).join("")}</ul></div>`;
  }

  function renderExpandedRow(row, colSpan) {
    const open = state.expanded.has(row.player_key);
    return `<tr class="expand-row ${open ? "open" : ""}" data-expand-for="${row.player_key}"><td id="player-detail-${row.player_key}" colspan="${colSpan}"><div class="player-news-detail"><h3>Recent player-value news</h3>${renderAdjustmentList(row)}${renderNewsList(row)}</div></td></tr>`;
  }

  function renderTable() {
    const list = filteredRows();
    if ($("#boardTitle")) $("#boardTitle").textContent = "Compare player values";
    if ($("#boardDescription")) $("#boardDescription").textContent = "Search, sort, and expand players using the graph's league settings.";
    if ($("#consensusNote")) $("#consensusNote").textContent = "Missing source values stay blank.";
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
    if (!list.length) {
      wrap.innerHTML = '<div class="empty">No players match these filters.</div>';
      return;
    }
    const keys = visibleColumns();
    const head = `<tr>${sortHeader("name", "Player")}${keys.map(key => sortHeader(key, columnLabel(key))).join("")}</tr>`;
    const colSpan = keys.length + 1;
    const body = list.map(row => {
      const open = state.expanded.has(row.player_key);
      const main = `<tr class="row-main ${open ? "open" : ""}" data-player-key="${row.player_key}"><td data-label="Player"><button class="player-button" type="button" aria-expanded="${String(open)}" aria-controls="player-detail-${row.player_key}" data-expand="${row.player_key}"><strong>${esc(row.name)}</strong></button><span class="name-sub">${esc(row.pos)} · ${esc(row.team)}</span></td>${keys.map(key => `<td data-label="${esc(columnLabel(key))}">${esc(displayValue(row, key))}</td>`).join("")}</tr>`;
      return main + renderExpandedRow(row, colSpan);
    }).join("");
    wrap.innerHTML = `<table class="all-table"><thead>${head}</thead><tbody>${body}</tbody></table>`;
    wrap.querySelectorAll("[data-sort]").forEach(button => button.addEventListener("click", () => {
      setTableSort(button.dataset.sort);
    }));
    wrap.querySelectorAll("[data-expand]").forEach(button => button.addEventListener("click", event => {
      event.stopPropagation();
      const key = Number(button.dataset.expand);
      if (state.expanded.has(key)) state.expanded.delete(key);
      else state.expanded.add(key);
      renderTable();
    }));
  }

  function renderDataNotes() {
    if ($("#freshness")) {
      const staleKeys = renderKeys.filter(sourceIsStale);
      const staleWeeks = [...new Set(staleKeys.map(weekForSource).filter(Boolean))].sort((a, b) => a - b);
      const staleLabel = staleKeys.length
        ? `${staleKeys.length} stale ${staleWeeks.map(week => `Week ${week}`).join("/")} source${staleKeys.length === 1 ? "" : "s"} shown until Week ${activeReferenceWeek()} arrives`
        : "sources current";
      $("#freshness").textContent = `${scoreLabel(state.scoring)} · ${state.teams} teams · ${staleLabel}`;
    }
  }

  // The board's default follows the chart's default lock.
  function defaultBoardSource() {
    return SOURCE_KEYS.includes("espn") ? "espn" : (renderKeys.find(sourceAvailable) || "espn");
  }

  function ensureAvailableSelection() {
    if (SOURCE_KEYS.includes(state.sort.column) && !sourceAvailable(state.sort.column)) {
      state.sort = {column:defaultBoardSource(), direction:"desc"};
      state.compareSource = defaultBoardSource();
    }
    if (SOURCE_KEYS.includes(state.compareSource) && !sourceAvailable(state.compareSource)) state.compareSource = defaultBoardSource();
    if (SOURCE_KEYS.includes(referenceSource) && !sourceAvailable(referenceSource)) {
      referenceSource = renderKeys.find(sourceAvailable) || "espn";
      window.TradeValueReferenceSource = referenceSource;
    }
    if (Array.isArray(state.columns)) {
      const allowed = new Set(allColumnKeys());
      state.columns = state.columns.filter(key => allowed.has(key));
    }
  }

  function exportState() {
    return {version:8, settings:{scoring:state.scoring, teams:state.teams, benchShare:state.benchShare}, sort:{...state.sort}, filters:{...state.filters}, columns:[...visibleColumns()]};
  }

  function applyImport(raw) {
    if (!raw || typeof raw !== "object") throw new Error("That file is not a dashboard state object.");
    const scoring = raw.settings?.scoring;
    const teams = Number(raw.settings?.teams);
    if (!["standard","half","full"].includes(scoring) || ![8,10,12,14].includes(teams)) throw new Error("League scoring or team count is not valid.");
    state.scoring = scoring;
    state.teams = teams;
    const importedBenchShare = Number(raw.settings?.benchShare ?? raw.settings?.absenceRate);
    if (Number.isFinite(importedBenchShare)) state.benchShare = Math.max(0, Math.min(0.5, importedBenchShare));
    if (["ALL","QB","RB","WR","TE","FLEX"].includes(raw.filters?.position)) state.filters.position = raw.filters.position;
    state.filters.search = String(raw.filters?.search || "").slice(0, 80);
    if (["name","pos","team","espn_role","disagreement","latest_news",...renderKeys].includes(raw.sort?.column)) {
      state.sort.column = raw.sort.column;
      state.compareSource = raw.sort.column;
      state.sort.direction = raw.sort.direction === "asc" ? "asc" : "desc";
    }
    const allowed = new Set(allColumnKeys());
    const columns = Array.isArray(raw.columns) ? raw.columns.filter(key => allowed.has(key)) : null;
    state.columns = columns && columns.length ? columns : visibleColumns();
    SOURCE_KEYS.forEach(key => { state.combos[key] = comboKeyFor(key); });
    rebuildSourceMaps();
    renderAll();
  }

  function normalizeRosterShape(shape) {
    if (!shape || typeof shape !== "object") return null;
    const next = {};
    const limits = {
      QB:[1, 5],
      RB:[1, 5],
      WR:[1, 5],
      TE:[1, 5],
      FLEX:[1, 5],
      BENCH:[0, 14]
    };
    Object.entries(limits).forEach(([key, [min, max]]) => {
      const value = Math.round(Number(shape[key]));
      next[key] = Number.isFinite(value) ? Math.max(min, Math.min(max, value)) : state.rosterShape[key];
    });
    return next;
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
    ensureAvailableSelection();
    renderLeagueControls();
    renderSourceCards();
    renderColumnToggles();
    renderViewControls();
    renderFilters();
    renderDataNotes();
    renderTable();
  }

  window.TradeValueComparisonControls = {
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
      const rosterShape = normalizeRosterShape(shared?.rosterShape);
      if (rosterShape && Object.keys(rosterShape).some(key => rosterShape[key] !== state.rosterShape[key])) {
        state.rosterShape = rosterShape;
        rebuildSourceMaps();
        renderAll();
      }
      const sharedBenchShare = Number(shared?.benchShare ?? shared?.absenceRate);
      if (Number.isFinite(sharedBenchShare)) {
        const nextBenchShare = Math.max(0, Math.min(0.5, sharedBenchShare));
        if (Math.abs(nextBenchShare - state.benchShare) > 0.0001) {
          state.benchShare = nextBenchShare;
          rebuildSourceMaps();
          renderAll();
        }
      }
      if (isLockKey(shared?.lockOrder)) setLockOrder(shared.lockOrder, false);
    }
  };
  window.addEventListener("trade-value-shared-change", event => window.TradeValueComparisonControls.applyShared(event.detail));
  window.addEventListener("trade-value-lock-order-change", event => window.TradeValueComparisonControls.setLockOrder(event.detail?.lockOrder));
  window.addEventListener("trade-value-reference-source-change", event => {
    if (SOURCE_KEYS.includes(event.detail?.source)) referenceSource = event.detail.source;
  });

  function runRegressionGuards() {
    const list = filteredRows();
    // Rank follows the ACTIVE LOCK. These replace the old preseason-sort
    // guards: a positional rank is not an overall order (four players share
    // rank 1), so ordering by it put the QB1 ahead of the RB1 at x=1.
    const lockSort = SOURCE_KEYS.includes(state.sort.column);
    const lockDescending = !lockSort || list.every((row, index) => {
      if (index === 0) return true;
      const prev = Number(list[index - 1].values?.[state.sort.column]);
      const here = Number(row.values?.[state.sort.column]);
      if (!Number.isFinite(prev) || !Number.isFinite(here)) return true;
      return prev >= here;
    });
    const missingLast = !lockSort || (() => {
      const firstMissing = list.findIndex(row => !Number.isFinite(Number(row.values?.[state.sort.column])));
      return firstMissing === -1 || list.slice(firstMissing).every(row => !Number.isFinite(Number(row.values?.[state.sort.column])));
    })();
    const allSources = renderKeys.length === SOURCE_KEYS.length && SOURCE_KEYS.every(key => renderKeys.includes(key));
    const fullPpr12TeamQbs = state.scoring === "full" && state.teams === 12 && rows().filter(row => row.pos === "QB").length;
    const fullPpr12TeamQbsAvailable = fullPpr12TeamQbs > 0;
    const availableSources = renderKeys.filter(sourceAvailable);
    const configurableColumns = allColumnKeys().includes("latest_news") && allColumnKeys().includes("disagreement") && availableSources.every(key => allColumnKeys().includes(key));
    const rolloverAware = renderKeys.every(key => !isWeekCurrent(key) || sourceAvailable(key));
    const diagnostics = {lockSort, lockDescending, missingLast, allSources, fullPpr12TeamQbsAvailable, fullPpr12TeamQbs, configurableColumns, rolloverAware, sourceCount:renderKeys.length, availableSourceCount:availableSources.length, activeReferenceWeek:activeReferenceWeek()};
    window.TradeValueComparisonDiagnostics = Object.freeze(diagnostics);
    const failed = Object.entries(diagnostics).filter(([key, value]) => ["ranksAscending", "missingLast", "positionGrouped", "allSources", "fullPpr12TeamQbsAvailable", "configurableColumns", "rolloverAware"].includes(key) && value !== true);
    if (failed.length) throw new Error(`Comparison regression guard failed: ${failed.map(([key]) => key).join(", ")}`);
  }

  async function init() {
    try {
      [data, window.TradeValuePlayerNews] = await Promise.all([loadComparisonData(), loadPlayerNews()]);
      newsMeta = window.TradeValuePlayerNews?.meta || {};
      newsByPlayerKey = new Map(Object.entries(window.TradeValuePlayerNews?.news_by_player_key || {}).map(([key, entries]) => [Number(key), Array.isArray(entries) ? entries : []]));
      adjustmentsByPlayerKey = new Map(Object.entries(window.TradeValuePlayerNews?.adjustments_by_player_key || {}).map(([key, entries]) => [Number(key), Array.isArray(entries) ? entries : []]));
      universeSize = Object.keys(data.player_keys || {}).length;
      canonicalByKey = canonicalPlayers();
      if (!canonicalByKey.size) throw new Error("Canonical player records are unavailable.");
      renderKeys = SOURCE_KEYS.filter(key => key === "cbs_adjusted" ? data.source_validation?.cbs === "live" : key === "espn_vorp" ? data.source_validation?.espn === "live" : data.source_validation?.[key] === "live");
      if (renderKeys.length !== SOURCE_KEYS.length) throw new Error("One or more required comparison sources did not pass validation.");
      if (!Array.isArray(state.columns)) state.columns = visibleColumns();
      if (SOURCE_KEYS.includes(window.TradeValueReferenceSource)) referenceSource = window.TradeValueReferenceSource;
      window.TradeValueReferenceSource = referenceSource;
      SOURCE_KEYS.forEach(key => { state.combos[key] = comboKeyFor(key); });
      rebuildSourceMaps();
      bindStatic();
      renderAll();
      if (window.TradeValueSharedState) window.TradeValueComparisonControls.applyShared(window.TradeValueSharedState);
      runRegressionGuards();
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
