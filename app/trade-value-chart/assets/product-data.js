// JEG-327 Phase D, Step 0 — PostgREST reader for the api.* contract views.
//
// This is the ONLY module in app/trade-value-chart/ that talks to the contract
// surfaces. Every other FE module (curve-widget.js, comparison-dashboard.js,
// future methodology renderer, etc.) calls into the five semantic methods
// exposed below and never reads from PostgREST or from a legacy fixture path.
//
// Contract spec: docs/contract/fe-read-contract-v1.md §3, §7, §8.
//   - Reads api.player_values, api.players, api.player_context,
//     api.product_options, api.product_snapshot.
//   - PostgREST base URL + anon key are injected at runtime as
//     window.TRADE_VALUE_SUPABASE_URL / window.TRADE_VALUE_SUPABASE_ANON_KEY
//     (NEVER hardcoded).
//   - Fail-closed per §8.2: contract_version mismatch, source_map_coverage
//     failure, empty players, missing active snapshot, stale pie_vintage,
//     stale tier_price_vintage → THROW. No silent fallback to fixtures.

(() => {
  "use strict";

  // ---------- Configuration ----------

  const CONTRACT_VERSION = "1.0.0";

  // PostgREST view names per contract §3.
  const VIEWS = Object.freeze({
    playerValues: "api.player_values",
    players: "api.players",
    playerContext: "api.player_context",
    productOptions: "api.product_options",
    productSnapshot: "api.product_snapshot",
  });

  const FETCH_TIMEOUT_MS = 2000;
  const PAGE_SIZE = 1000;
  const CACHE_PREFIX = "tvc::";

  // Source keys verbatim from contract §3.4.2 (api.product_options.source_keys).
  // Re-exported for consumers; the runtime source of truth is the row fetched
  // from api.product_options during init.
  const SOURCE_KEYS = Object.freeze([
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
    "cbs_adjusted",
    // Pure VORP keys (browser computes these from per-game projections; no
    // per-cell rows on api.player_values).
    "espn_vorp",
    "cbsros_vorp",
    "razzball_vorp",
  ]);

  const ADJUSTED_INDEXED_KEYS = Object.freeze([
    "fantasycalc_adjusted",
    "usatoday_adjusted",
    "fantasypros_adjusted",
    "cbs_adjusted",
  ]);

  const PURE_VORP_KEYS = Object.freeze(["espn_vorp", "cbsros_vorp", "razzball_vorp"]);

  const AS_PUBLISHED_KEYS = Object.freeze(["usatoday", "fantasycalc", "fantasypros", "cbs"]);

  // FantasyCalc family emits _qbN combo suffix; every other source collapses
  // to qb1. Mirrors consolidation-index.js QB_AWARE_SOURCES so the two stay
  // in sync (consumers use this constant to pick the right qbVariant).
  const QB_AWARE_SOURCES = new Set(["fantasycalc", "fantasycalc_adjusted"]);

  // ---------- Internal state ----------

  const state = {
    initialized: false,
    initError: null,
    snapshot: null,                 // frozen api.product_snapshot row
    options: null,                  // frozen api.product_options singleton
    activeSnapshotId: null,
    sourcesMap: {},                 // mirror of snapshot.sources for sourceMeta
    players: [],                    // frozen array of api.players rows
    playerByKey: new Map(),         // player_key -> player row
    // cellKey -> {values, valueProvenance, modelVsPublished, tierPriceVector,
    //   pieVintage, bakeId, detailLocator, indexTotal, hasAnyRow}
    // cellKey shape: `${source}|${scoring}|${teams}|${qbVariant}|${view}`
    valuesByCell: new Map(),
    contextByKey: new Map(),        // player_key (number) -> {news, adjustments, asOf}
  };

  // ---------- Cache helpers (ChatGPT cutover plan) ----------

  // Kill switch: ?dataSource=fixtures or localStorage override.
  // Checks both "tvc::dataSource" (namespaced) and "dataSource" (plan's key).
  function isFixturesOverride() {
    try {
      if (typeof window === "undefined") return false;
      const params = new URLSearchParams(window.location.search);
      if (params.get("dataSource") === "fixtures") return true;
      if (window.localStorage) {
        if (window.localStorage.getItem("tvc::dataSource") === "fixtures") return true;
        if (window.localStorage.getItem("dataSource") === "fixtures") return true;
      }
    } catch (e) { /* ignore */ }
    return false;
  }

  function cacheKey(name, snapshotId) {
    return `${CACHE_PREFIX}${name}::${snapshotId || "unknown"}`;
  }

  function readCache(key) {
    try {
      if (typeof window === "undefined" || !window.localStorage) return null;
      const raw = window.localStorage.getItem(key);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch (e) {
      return null;
    }
  }

  function writeCache(key, value) {
    try {
      if (typeof window === "undefined" || !window.localStorage) return;
      window.localStorage.setItem(key, JSON.stringify({ data: value, fetchedAt: new Date().toISOString() }));
    } catch (e) {
      // Quota exceeded or unavailable — non-fatal
      console.warn("[product-data] cache write failed:", e.message);
    }
  }

  function showDegradedBanner(message) {
    try {
      if (typeof window === "undefined" || !window.document) return;
      let banner = window.document.getElementById("tvc-status-banner");
      if (!banner) {
        banner = window.document.createElement("div");
        banner.id = "tvc-status-banner";
        banner.style.cssText = "display:none; padding:8px 16px; background:#fff3cd; color:#856404; border-bottom:1px solid #ffeaa7; font-size:14px; text-align:center;";
        window.document.body.insertBefore(banner, window.document.body.firstChild);
      }
      banner.textContent = message;
      banner.style.display = "block";
    } catch (e) { /* ignore */ }
  }

  // ---------- PostgREST fetch helpers ----------

  // Resolve PostgREST base URL + anon key from the runtime window. Throws
  // when either is missing — fail-closed before any network round-trip.
  function getPostgrestConfig() {
    if (typeof window === "undefined") {
      throw new Error("product-data.js: window scope unavailable; cannot resolve PostgREST URL/key. Render refused.");
    }
    const baseUrl = window.TRADE_VALUE_SUPABASE_URL;
    const anonKey = window.TRADE_VALUE_SUPABASE_ANON_KEY;
    if (!baseUrl || typeof baseUrl !== "string") {
      throw new Error("product-data.js: window.TRADE_VALUE_SUPABASE_URL is not set. Render refused.");
    }
    if (!anonKey || typeof anonKey !== "string") {
      throw new Error("product-data.js: window.TRADE_VALUE_SUPABASE_ANON_KEY is not set. Render refused.");
    }
    return { baseUrl: baseUrl.replace(/\/+$/, ""), anonKey };
  }

  // fetch() with an AbortController-backed timeout. Returns the raw Response.
  function fetchWithTimeout(url, opts, timeoutMs) {
    if (typeof fetch !== "function") {
      return Promise.reject(new Error("fetch unavailable"));
    }
    let controller = null;
    let timer = null;
    try {
      controller = typeof AbortController === "function" ? new AbortController() : null;
    } catch (e) {
      controller = null;
    }
    const fetchOpts = Object.assign({}, opts || {});
    if (controller) fetchOpts.signal = controller.signal;
    return new Promise((resolve, reject) => {
      timer = setTimeout(() => {
        if (controller) controller.abort();
        reject(new Error(`timed out after ${timeoutMs}ms`));
      }, timeoutMs);
      fetch(url, fetchOpts)
        .then(response => {
          clearTimeout(timer);
          resolve(response);
        })
        .catch(err => {
          clearTimeout(timer);
          reject(err);
        });
    });
  }

  // Fetch every row of a PostgREST view, paginating via Range headers until
  // the Content-Range total is exhausted or a short page is returned.
  // Throws on any HTTP error, parse error, or non-array payload.
  async function fetchViewAll(viewName) {
    const { baseUrl, anonKey } = getPostgrestConfig();
    // viewName is "api.player_values" per contract; PostgREST needs the bare
    // view name in the URL path plus Accept-Profile for the api schema.
    const bareView = viewName.replace(/^api\./, "");
    const url = `${baseUrl}/rest/v1/${bareView}`;
    const allRows = [];
    let offset = 0;
    while (true) {
      const headers = {
        "apikey": anonKey,
        "Authorization": `Bearer ${anonKey}`,
        "Accept-Profile": "api",
        "Range": `${offset}-${offset + PAGE_SIZE - 1}`,
        // count=none avoids the PostgREST count(*) overhead on 20k-row
        // views; pagination terminates on the short-page break below.
        "Prefer": "count=none",
        "Accept": "application/json",
      };
      let response;
      try {
        response = await fetchWithTimeout(url, { method: "GET", headers }, FETCH_TIMEOUT_MS);
      } catch (err) {
        const reason = err && err.message ? err.message : err;
        throw new Error(`${viewName} fetch failed: ${reason}. Render refused.`);
      }
      if (!response.ok) {
        let body = "";
        try { body = await response.text(); } catch (e) { /* ignore */ }
        throw new Error(`${viewName} request failed (status=${response.status}${body ? ", body=" + body : ""}). Render refused.`);
      }
      let rows;
      try {
        rows = await response.json();
      } catch (e) {
        throw new Error(`${viewName} parse failed (invalid JSON). Render refused.`);
      }
      if (!Array.isArray(rows)) {
        throw new Error(`${viewName} returned a non-array payload. Render refused.`);
      }
      allRows.push(...rows);
      if (rows.length < PAGE_SIZE) break;
      const contentRange = response.headers.get("content-range");
      let totalKnown = null;
      if (contentRange) {
        const m = /\/(\d+|\*)/.exec(contentRange);
        if (m && m[1] !== "*") totalKnown = parseInt(m[1], 10);
      }
      offset += PAGE_SIZE;
      if (totalKnown !== null && offset >= totalKnown) break;
    }
    return allRows;
  }

  // ---------- Numeric / shape helpers ----------

  // Parse a wire numeric (PostgREST serializes numeric/bigint as strings).
  // Returns null when the cell is null/missing/non-numeric.
  function parseNum(v) {
    if (v === null || v === undefined || v === "") return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  function parseIntStrict(v) {
    if (v === null || v === undefined || v === "") return null;
    const n = parseInt(v, 10);
    return Number.isInteger(n) ? n : null;
  }

  // cellKey shape — used as the Map key for the per-cell value index.
  function cellKeyFor(source, scoring, teams, qbVariant, view) {
    return `${source}|${scoring}|${teams}|${qbVariant}|${view}`;
  }

  // ---------- Fail-closed guards (§5.1, §6.1, §3.1.2) ----------

  // pie_vintage guard: for combo_reindexed rows with indexed/ddf-translated
  // provenance, pie_vintage must equal bake_id (or be NULL for passthrough).
  // Any violation throws — the snapshot is refused, the chart must not
  // render partial.
  function verifyPieVintageGuard(rows, snapshotId) {
    const guardedProvenances = new Set(["indexed", "vorp_indexed", "ddf_translated"]);
    for (const row of rows) {
      if (row.view !== "combo_reindexed") continue;
      if (!guardedProvenances.has(row.value_provenance)) continue;
      const pieVintage = row.pie_vintage;
      const bakeId = row.bake_id;
      if (pieVintage == null) continue; // passthrough sources not on the pie
      if (bakeId == null || String(pieVintage) !== String(bakeId)) {
        throw new Error(
          `${VIEWS.playerValues} pie_vintage guard failed (snapshot=${snapshotId}): ` +
          `source=${row.source} scoring=${row.scoring} teams=${row.teams} ` +
          `qb_variant=${row.qb_variant} view=${row.view} ` +
          `value_provenance=${row.value_provenance} ` +
          `pie_vintage=${pieVintage} bake_id=${bakeId}. Render refused.`
        );
      }
    }
  }

  // tier_price_vintage guard: whenever tier_price_vector is set,
  // tier_price_vintage must equal bake_id.
  function verifyTierPriceVintageGuard(rows, snapshotId) {
    for (const row of rows) {
      if (row.tier_price_vector == null) continue;
      const tier = row.tier_price_vintage;
      const bakeId = row.bake_id;
      if (tier == null) continue; // backend may leave NULL when vector is unset
      if (bakeId == null || String(tier) !== String(bakeId)) {
        throw new Error(
          `${VIEWS.playerValues} tier_price_vintage guard failed (snapshot=${snapshotId}): ` +
          `source=${row.source} scoring=${row.scoring} teams=${row.teams} ` +
          `qb_variant=${row.qb_variant} view=${row.view} ` +
          `tier_price_vintage=${tier} bake_id=${bakeId}. Render refused.`
        );
      }
    }
  }

  // sourceMapCoverage on api.player_values: every key in options.source_keys
  // (except pure VORP, which has no per-cell rows) must appear at least once.
  function verifyPlayerValuesSourceMap(rows, options) {
    const present = new Set();
    for (const row of rows) {
      const source = String(row.source || "");
      if (source) present.add(source);
    }
    const missing = [];
    for (const key of options.source_keys) {
      if (PURE_VORP_KEYS.includes(key)) continue;
      if (key === "cbs_adjusted") {
        if (!present.has("cbs")) missing.push(key);
        continue;
      }
      if (!present.has(key)) missing.push(key);
    }
    if (missing.length) {
      throw new Error(`${VIEWS.playerValues} sourceMapCoverage failed: missing ${missing.join(", ")}. Render refused.`);
    }
  }

  // ---------- Indexers ----------

  // Build the per-cell index from api.player_values rows. All rows of a cell
  // share (source, scoring, teams, qb_variant, view); we aggregate values
  // into a Map<playerKey, number>, and capture the per-row metadata that
  // applies to the cell (value_provenance, model_vs_published,
  // tier_price_vector, pie_vintage, bake_id, detail_locator, index_total).
  function indexPlayerValues(rows) {
    const cellMap = new Map();
    for (const row of rows) {
      const source = String(row.source || "");
      const scoring = String(row.scoring || "");
      const teamsNum = parseIntStrict(row.teams);
      const qbVariant = String(row.qb_variant || "");
      const view = String(row.view || "");
      if (!source || !scoring || teamsNum === null || !view) continue;
      const key = cellKeyFor(source, scoring, teamsNum, qbVariant, view);
      let cell = cellMap.get(key);
      if (!cell) {
        cell = {
          values: new Map(),
          valueProvenance: row.value_provenance != null ? String(row.value_provenance) : null,
          modelVsPublished: row.model_vs_published != null ? String(row.model_vs_published) : null,
          tierPriceVector: row.tier_price_vector && typeof row.tier_price_vector === "object"
            ? JSON.parse(JSON.stringify(row.tier_price_vector))
            : null,
          pieVintage: row.pie_vintage != null ? String(row.pie_vintage) : null,
          bakeId: row.bake_id != null ? String(row.bake_id) : null,
          detailLocator: row.detail_locator != null ? String(row.detail_locator) : null,
          indexTotal: parseNum(row.index_total),
          hasAnyRow: false,
        };
        cellMap.set(key, cell);
      }
      cell.hasAnyRow = true;
      const playerKey = Number(row.player_key);
      if (!Number.isInteger(playerKey)) continue;
      const value = parseNum(row.value);
      if (value === null) continue;
      cell.values.set(playerKey, value);
    }
    return cellMap;
  }

  // Build the api.players frozen array. Field shape per contract §3.2.2.
  // canonical_name is the ONLY name source (Jeremy 2026-10-04): the
  // full_name ‖ name ‖ "" fallback chain is dead. The view guarantees
  // canonical_name from the canonical identity table.
  function buildPlayers(rows) {
    return Object.freeze(rows.map(raw => {
      const playerKey = Number(raw.player_key);
      const pos = String(raw.pos || "");
      const isKdst = pos === "K" || pos === "DST";
      const canonicalName = String(raw.canonical_name || "").trim();
      const teamRaw = raw.team;
      const team = (teamRaw != null && String(teamRaw) !== "") ? String(teamRaw) : "—";
      return Object.freeze({
        player_key: playerKey,
        canonical_name: canonicalName,
        pos,
        team,
        ir_zeroed: Boolean(raw.ir_zeroed),
        kdst_excluded_from_chart: raw.kdst_excluded_from_chart === true ? true : isKdst,
        espn_ppg: raw.espn_ppg && typeof raw.espn_ppg === "object" ? JSON.parse(JSON.stringify(raw.espn_ppg)) : null,
        rz_ppg: raw.rz_ppg && typeof raw.rz_ppg === "object" ? JSON.parse(JSON.stringify(raw.rz_ppg)) : null,
        cbsros_ppg: raw.cbsros_ppg && typeof raw.cbsros_ppg === "object" ? JSON.parse(JSON.stringify(raw.cbsros_ppg)) : null,
        ecr_ppg: raw.ecr_ppg && typeof raw.ecr_ppg === "object" ? JSON.parse(JSON.stringify(raw.ecr_ppg)) : null,
        agent_ranking_ppg: raw.agent_ranking_ppg && typeof raw.agent_ranking_ppg === "object" ? JSON.parse(JSON.stringify(raw.agent_ranking_ppg)) : null,
        blend_ppg: raw.blend_ppg && typeof raw.blend_ppg === "object" ? JSON.parse(JSON.stringify(raw.blend_ppg)) : null,
        games_remaining: parseNum(raw.games_remaining),
        // Legacy aliases — pure copies of the canonical name (NOT a
        // fallback chain: the name always comes from the canonical
        // identity table via canonical_name). Kept so W2-era consumers
        // reading row.name / row.full_name keep working during the
        // strangler-fig; migrate them to canonical_name next.
        full_name: canonicalName,
        name: canonicalName,
      });
    }));
  }

  // Build the api.player_context index (player_key -> frozen {news[],
  // adjustments[], asOf}). Per §3.3.1 the view omits players with neither
  // news nor adjustments; getPlayerContext() returns null for those keys.
  function indexPlayerContext(rows) {
    const ctxMap = new Map();
    for (const row of rows) {
      const playerKey = Number(row.player_key);
      if (!Number.isInteger(playerKey)) continue;
      const news = Array.isArray(row.news)
        ? Object.freeze(row.news.map(n => Object.freeze(Object.assign({}, n))))
        : Object.freeze([]);
      const adjustments = Array.isArray(row.adjustments)
        ? Object.freeze(row.adjustments.map(a => Object.freeze(Object.assign({}, a))))
        : Object.freeze([]);
      ctxMap.set(playerKey, Object.freeze({
        news,
        adjustments,
        as_of: row.as_of != null ? String(row.as_of) : null,
      }));
    }
    return ctxMap;
  }

  // Build the frozen api.product_options singleton from the view response.
  // The row is already shaped; we deep-clone jsonb fields so consumers can
  // mutate without affecting state.
  function buildOptions(row) {
    if (!row || typeof row !== "object") {
      throw new Error(`${VIEWS.productOptions} returned a non-object payload. Render refused.`);
    }
    const benchShare = row.bench_share && typeof row.bench_share === "object" ? row.bench_share : {};
    return Object.freeze({
      product_key: String(row.product_key || "default"),
      contract_version: String(row.contract_version || ""),
      bench_share: Object.freeze({
        default: parseNum(benchShare.default) != null ? parseNum(benchShare.default) : 0.15,
        min: parseNum(benchShare.min) != null ? parseNum(benchShare.min) : 0.01,
        max: parseNum(benchShare.max) != null ? parseNum(benchShare.max) : 0.30,
        user_settable: benchShare.user_settable !== false,
      }),
      bench_share_default: parseNum(row.bench_share_default) != null ? parseNum(row.bench_share_default) : 0.15,
      bench_share_min: parseNum(row.bench_share_min) != null ? parseNum(row.bench_share_min) : 0.01,
      bench_share_max: parseNum(row.bench_share_max) != null ? parseNum(row.bench_share_max) : 0.30,
      bench_share_user_settable: row.bench_share_user_settable !== false,
      default_scoring: String(row.default_scoring || "full"),
      default_teams: parseNum(row.default_teams) != null ? parseNum(row.default_teams) : 12,
      default_roster_shape: Object.freeze(row.default_roster_shape && typeof row.default_roster_shape === "object"
        ? Object.assign({}, row.default_roster_shape)
        : { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, BENCH: 6 }),
      default_lock_order: String(row.default_lock_order || "espn"),
      default_view_mode: String(row.default_view_mode || "indexed"),
      default_reference_source: String(row.default_reference_source || "usatoday"),
      default_position_weights: row.default_position_weights && typeof row.default_position_weights === "object"
        ? JSON.parse(JSON.stringify(row.default_position_weights))
        : null,
      min_shared_for_pie: parseNum(row.min_shared_for_pie) != null ? parseNum(row.min_shared_for_pie) : 40,
      starter_markup_sane_band: Object.freeze(Array.isArray(row.starter_markup_sane_band)
        ? row.starter_markup_sane_band.map(Number)
        : [0.98, 1.6]),
      peak_agreement_band: Object.freeze(Array.isArray(row.peak_agreement_band)
        ? row.peak_agreement_band.map(Number)
        : [0.80, 1.25]),
      source_keys: Object.freeze(Array.isArray(row.source_keys) && row.source_keys.length
        ? row.source_keys.slice()
        : SOURCE_KEYS.slice()),
      adjusted_indexed_keys: Object.freeze(Array.isArray(row.adjusted_indexed_keys)
        ? row.adjusted_indexed_keys.slice()
        : ADJUSTED_INDEXED_KEYS.slice()),
      pure_vorp_keys: Object.freeze(Array.isArray(row.pure_vorp_keys)
        ? row.pure_vorp_keys.slice()
        : PURE_VORP_KEYS.slice()),
      as_published_keys: Object.freeze(Array.isArray(row.as_published_keys)
        ? row.as_published_keys.slice()
        : AS_PUBLISHED_KEYS.slice()),
    });
  }

  // Build the frozen api.product_snapshot from the active row. The view
  // filters to is_active=true AND publishable=true; if multiple rows come
  // back (defense in depth), prefer is_active=true.
  function buildSnapshot(rows) {
    if (!rows.length) {
      throw new Error(`${VIEWS.productSnapshot} returned 0 rows (no active snapshot). Render refused.`);
    }
    const row = rows.find(r => r.is_active !== false) || rows[0];
    return Object.freeze({
      snapshot_id: String(row.snapshot_id),
      contract_version: String(row.contract_version || ""),
      built_at: row.built_at != null ? String(row.built_at) : null,
      value_weeks: row.value_weeks && typeof row.value_weeks === "object"
        ? Object.freeze(Object.assign({}, row.value_weeks))
        : Object.freeze({}),
      sources: row.sources && typeof row.sources === "object"
        ? Object.freeze(JSON.parse(JSON.stringify(row.sources)))
        : Object.freeze({}),
      source_validation: row.source_validation && typeof row.source_validation === "object"
        ? Object.freeze(Object.assign({}, row.source_validation))
        : Object.freeze({}),
      espn_zeroed: Array.isArray(row.espn_zeroed)
        ? Object.freeze(row.espn_zeroed.slice())
        : Object.freeze([]),
      methodology_combos: row.methodology_combos && typeof row.methodology_combos === "object"
        ? JSON.parse(JSON.stringify(row.methodology_combos))
        : null,
      reference_freshness: row.reference_freshness && typeof row.reference_freshness === "object"
        ? JSON.parse(JSON.stringify(row.reference_freshness))
        : null,
      health: row.health && typeof row.health === "object"
        ? JSON.parse(JSON.stringify(row.health))
        : null,
      is_active: row.is_active !== false,
      publishable: row.publishable !== false,
      generated_at: row.generated_at != null ? String(row.generated_at) : null,
      bake_ids: row.bake_ids && typeof row.bake_ids === "object"
        ? JSON.parse(JSON.stringify(row.bake_ids))
        : null,
      pie_vintage_per_source: row.pie_vintage_per_source && typeof row.pie_vintage_per_source === "object"
        ? Object.freeze(Object.assign({}, row.pie_vintage_per_source))
        : null,
      players_snapshot_at: row.players_snapshot_at != null ? String(row.players_snapshot_at) : null,
      context_meta: row.context_meta && typeof row.context_meta === "object"
        ? JSON.parse(JSON.stringify(row.context_meta))
        : null,
    });
  }

  // sourceMapCoverage on the snapshot: every key in options.source_keys
  // (except pure VORP, cbs_adjusted) must have a snapshot.sources entry.
  function verifySourceMapCoverage(options, snapshot) {
    const sourcesMap = snapshot.sources || {};
    const missing = [];
    for (const key of options.source_keys) {
      if (PURE_VORP_KEYS.includes(key)) continue;
      if (key === "cbs_adjusted") {
        if (!sourcesMap.cbs) missing.push(key);
        continue;
      }
      if (!sourcesMap[key]) missing.push(key);
    }
    if (missing.length) {
      throw new Error(`sourceMapCoverage failed: missing ${missing.join(", ")}. Render refused.`);
    }
  }

  // ---------- Public surface (the five semantic methods) ----------

  // getPlayerValues({source, scoring, teams, qbVariant, view}) — contract §8.1.
  // Returns a frozen per-cell object, or null when the cell is absent.
  function getPlayerValues(query) {
    if (!state.initialized) {
      throw new Error("product-data.js: getPlayerValues() called before initProductData() resolved. Render refused.");
    }
    if (!query || typeof query !== "object") {
      throw new Error("product-data.js: getPlayerValues() requires a query object. Render refused.");
    }
    const { source, scoring, teams, qbVariant = "qb1", view = "combo_reindexed" } = query;
    if (!source || !scoring || !Number.isFinite(Number(teams))) {
      throw new Error(`product-data.js: getPlayerValues() missing required keys (source=${source} scoring=${scoring} teams=${teams}). Render refused.`);
    }

    // Pure VORP sources have no per-cell rows on api.player_values (the
    // browser computes them from per-game projections via getPlayers()).
    if (PURE_VORP_KEYS.includes(source)) return null;

    const teamsNum = parseIntStrict(teams);

    // Fixtures mode: build the cell from the inline island (best effort).
    if (state.fixturesMode) {
      const fcell = getFixtureCell(source, scoring, teamsNum, qbVariant, view);
      if (!fcell || !fcell.hasAnyRow) return null;
      const fvalues = new Map(fcell.values);
      return Object.freeze({
        values: fvalues,
        tier_price_vector: null,
        pie_vintage: null,
        bake_id: null,
        coverage_class: fvalues.size ? "full" : "view_limited_source",
        value_provenance: "fixtures",
        model_vs_published: null,
        detail_locator: null,
        source_meta: null,
        index_total: null,
      });
    }

    const key = cellKeyFor(source, scoring, teamsNum, qbVariant, view);
    const cell = state.valuesByCell.get(key);
    if (!cell || !cell.hasAnyRow) return null;

    // Copy the values map so callers can mutate without affecting state.
    const values = new Map(cell.values);
    const coverageClass = values.size ? "full" : "view_limited_source";

    // Frozen per-cell object per contract §8.1.
    return Object.freeze({
      values,
      tier_price_vector: cell.tierPriceVector,
      pie_vintage: cell.pieVintage,
      bake_id: cell.bakeId,
      coverage_class: coverageClass,
      value_provenance: cell.valueProvenance,
      model_vs_published: cell.modelVsPublished,
      detail_locator: cell.detailLocator,
      source_meta: state.snapshot?.sources?.[source] || null,
      index_total: cell.indexTotal,
    });
  }

  // getPlayers() — contract §8.1. Returns the frozen array of api.players.
  function getPlayers() {
    if (!state.initialized) {
      throw new Error("product-data.js: getPlayers() called before initProductData() resolved. Render refused.");
    }
    return state.players;
  }

  // getPlayerContext(playerKey) — contract §8.1. Returns a frozen
  // {news[], adjustments[], asOf} or null when the player has no context.
  function getPlayerContext(playerKey) {
    if (!state.initialized) {
      throw new Error("product-data.js: getPlayerContext() called before initProductData() resolved. Render refused.");
    }
    const key = Number(playerKey);
    if (!Number.isInteger(key)) return null;
    return state.contextByKey.get(key) || null;
  }

  // getProductOptions() — contract §8.1. Returns the singleton frozen.
  function getProductOptions() {
    if (!state.initialized) {
      throw new Error("product-data.js: getProductOptions() called before initProductData() resolved. Render refused.");
    }
    return state.options;
  }

  // getSnapshot() — contract §8.1. Returns the active api.product_snapshot.
  function getSnapshot() {
    if (!state.initialized) {
      throw new Error("product-data.js: getSnapshot() called before initProductData() resolved. Render refused.");
    }
    return state.snapshot;
  }

  // ---------- Transitional helpers (not contract surfaces) ----------
  //
  // These keep the previous public API alive for consumers that still depend
  // on them. New consumers should use the five semantic methods only.

  // getAdjustmentInputs(): the raw adjustment-inputs.json payload. The
  // contract does not yet have a surface for the stage-2 alpha/beta cells
  // (the JEG-322 publish gate will land them in api.player_values). Until
  // then we return null — consumers that previously read this fixture
  // continue to render with their default fallback (per §5.2 fail-open for
  // adjustment-inputs.json fetch/schema fail).
  function getAdjustmentInputs() {
    return null;
  }

  // getPlayerByKey(playerKey): convenience accessor so consumers don't have
  // to iterate getPlayers() on every chart tick.
  function getPlayerByKey(playerKey) {
    if (!state.initialized) return null;
    const key = Number(playerKey);
    return state.playerByKey.get(key) || null;
  }

  // getPlayerKeysBySourceId(): the legacy fixture's sourceId -> playerKey
  // map. With the PostgREST cutover, rows are keyed on player_key directly;
  // consumers should iterate getPlayers() or call getPlayerByKey(). Returning
  // null signals "no legacy map; use the canonical identity path".
  function getPlayerKeysBySourceId() {
    return null;
  }

  // getProviderInfo(): debug surface for the chart health panel.
  function getProviderInfo() {
    if (!state.initialized) {
      return { provider: "uninitialized", initError: state.initError };
    }
    return {
      provider: state.fixturesMode ? "fixtures-override" : state.fromCache ? "postgrest-api-contract-cached" : "postgrest-api-contract",
      contractVersion: state.options?.contract_version || CONTRACT_VERSION,
      snapshotId: state.snapshot?.snapshot_id || null,
      bakeId: state.snapshot?.bake_ids?.primary || state.snapshot?.snapshot_id || null,
      playersLoaded: state.players.length,
      valuesLoaded: state.valuesByCell.size,
      contextLoaded: state.contextByKey.size,
      initError: state.initError,
      fixturesMode: !!state.fixturesMode,
      fromCache: !!state.fromCache,
    };
  }

  // ---------- Fail-closed init with cached fallback (ChatGPT cutover plan) ----------

  // initProductData({contractVersion="1.0.0"} = {})
  //
  // Resolution order:
  //   1. ?clearCache=1 → wipe all tvc:: keys, continue to live init
  //   2. Kill switch (?dataSource=fixtures or localStorage) → fixtures adapter,
  //      bypass network entirely
  //   3. Live API with 2s timeout → on success, write snapshot-keyed cache
  //   4. On NETWORK failure → cached bundle fallback with degraded banner
  //   5. No cache → throw with actionable message
  //
  // Contract violations (version mismatch, sourceMapCoverage, pie_vintage
  // guards) ALWAYS throw — fallback is for network failures only.
  async function initProductData(opts) {
    if (state.initialized) {
      return publicHandle;
    }

    // ?clearCache=1 → wipe all tvc:: keys (rollback plan)
    try {
      if (typeof window !== "undefined" && window.location) {
        const params = new URLSearchParams(window.location.search);
        if (params.get("clearCache") === "1") {
          clearAllCache();
          console.info("[product-data] cache cleared via ?clearCache=1");
        }
      }
    } catch (e) { /* ignore */ }

    // Kill switch: fixtures adapter, bypass network entirely
    if (isFixturesOverride()) {
      return initFromFixtures();
    }

    const options = opts || {};
    const expectedVersion = options.contractVersion || CONTRACT_VERSION;
    if (expectedVersion !== CONTRACT_VERSION) {
      throw new Error(`Unknown contract version ${expectedVersion}. Render refused.`);
    }

    // Validate URL/key presence before any network round-trip.
    try {
      getPostgrestConfig();
    } catch (err) {
      // Config missing = fail-closed (not a network failure). But if we have
      // a cached bundle, use it — the user has seen this data before.
      const bundle = readLatestBundle();
      if (bundle) {
        showDegradedBanner("Using cached data. Live API unavailable.");
        return loadFromCache(bundle.data, bundle.fetchedAt);
      }
      throw err;
    }

    try {
      return await initFromLive(expectedVersion);
    } catch (err) {
      // Distinguish contract violations (always throw) from network failures
      // (fall back to cache). Contract violations contain "Render refused".
      const isContractViolation = err && err.message && err.message.includes("Render refused");
      if (isContractViolation) {
        throw err;
      }
      console.warn("[product-data] live init failed (network):", err.message);
      const bundle = readLatestBundle();
      if (bundle) {
        showDegradedBanner(`Using cached data from ${bundle.fetchedAt}. Live data unavailable. Retry.`);
        return loadFromCache(bundle.data, bundle.fetchedAt);
      }
      throw new Error(
        `Live API unavailable and no cached data: ${err.message}. ` +
        `Try ?dataSource=fixtures for the static fallback, or retry.`
      );
    }
  }

  // Read the latest cached bundle (via the tvc::latest pointer).
  function readLatestBundle() {
    try {
      const latest = readCache(cacheKey("latest", "pointer"));
      if (!latest || !latest.data || !latest.data.snapshotId) return null;
      const bundle = readCache(cacheKey("bundle", latest.data.snapshotId));
      if (!bundle || !bundle.data) return null;
      return { data: bundle.data, fetchedAt: bundle.fetchedAt };
    } catch (e) {
      return null;
    }
  }

  // Wipe all tvc:: keys from localStorage.
  function clearAllCache() {
    try {
      if (typeof window === "undefined" || !window.localStorage) return;
      const toRemove = [];
      for (let i = 0; i < window.localStorage.length; i++) {
        const k = window.localStorage.key(i);
        if (k && k.indexOf(CACHE_PREFIX) === 0) toRemove.push(k);
      }
      toRemove.forEach(k => window.localStorage.removeItem(k));
    } catch (e) { /* ignore */ }
  }

  // Serialize the valuesByCell Map into a JSON-safe bundle.
  function serializeBundle(snapshotRow, optionsRow, playerRows, contextRows, valuesByCell) {
    const cells = [];
    valuesByCell.forEach((cell, key) => {
      const valuesObj = {};
      cell.values.forEach((v, playerKey) => { valuesObj[playerKey] = v; });
      cells.push({
        key,
        values: valuesObj,
        valueProvenance: cell.valueProvenance,
        modelVsPublished: cell.modelVsPublished,
        tierPriceVector: cell.tierPriceVector,
        pieVintage: cell.pieVintage,
        bakeId: cell.bakeId,
        detailLocator: cell.detailLocator,
        indexTotal: cell.indexTotal,
        hasAnyRow: cell.hasAnyRow,
      });
    });
    return { snapshotRow, optionsRow, playerRows, contextRows, cells };
  }

  // Write the successful live result to the snapshot-keyed cache.
  function writeBundleCache(snapshotId, bundle) {
    try {
      writeCache(cacheKey("bundle", snapshotId), bundle);
      writeCache(cacheKey("latest", "pointer"), { snapshotId });
    } catch (e) {
      console.warn("[product-data] bundle cache write failed:", e.message);
    }
  }

  // Load state from a cached bundle. Re-runs the fail-closed guards on the
  // cached cells (defense in depth — cached data was verified when stored,
  // but we verify again).
  function loadFromCache(bundle, fetchedAt) {
    if (!bundle || !bundle.snapshotRow || !bundle.optionsRow) {
      throw new Error("Cached bundle is corrupt. Render refused.");
    }
    console.info(`[product-data] loading from cache (fetched ${fetchedAt})`);

    // Rebuild snapshot + options (guards re-run via buildSnapshot/buildOptions)
    state.snapshot = buildSnapshot([bundle.snapshotRow]);
    state.activeSnapshotId = state.snapshot.snapshot_id;
    state.sourcesMap = state.snapshot.sources || {};
    state.options = buildOptions(bundle.optionsRow);

    // Contract version must still match (fail-closed even on cached data)
    if (state.snapshot.contract_version !== CONTRACT_VERSION ||
        state.options.contract_version !== CONTRACT_VERSION) {
      throw new Error("Cached bundle contract_version mismatch. Render refused.");
    }
    verifySourceMapCoverage(state.options, state.snapshot);

    // Rebuild players
    state.players = buildPlayers(bundle.playerRows || []);
    if (!state.players.length) {
      throw new Error("Cached bundle has 0 players. Render refused.");
    }
    state.playerByKey = new Map();
    state.players.forEach(p => state.playerByKey.set(p.player_key, p));

    // Rebuild valuesByCell from serialized cells
    const cellMap = new Map();
    (bundle.cells || []).forEach(c => {
      const values = new Map();
      Object.keys(c.values || {}).forEach(k => {
        const playerKey = Number(k);
        const v = Number(c.values[k]);
        if (Number.isInteger(playerKey) && Number.isFinite(v)) values.set(playerKey, v);
      });
      cellMap.set(c.key, {
        values,
        valueProvenance: c.valueProvenance,
        modelVsPublished: c.modelVsPublished,
        tierPriceVector: c.tierPriceVector,
        pieVintage: c.pieVintage,
        bakeId: c.bakeId,
        detailLocator: c.detailLocator,
        indexTotal: c.indexTotal,
        hasAnyRow: !!c.hasAnyRow,
      });
      // Guard: pie_vintage must equal bake_id (cell-level equivalent of
      // verifyPieVintageGuard for the indexed provenances)
      if (c.pieVintage != null && c.bakeId != null &&
          ["indexed", "vorp_indexed", "ddf_translated"].includes(c.valueProvenance) &&
          String(c.pieVintage) !== String(c.bakeId)) {
        throw new Error(`Cached bundle pie_vintage guard failed for cell ${c.key}. Render refused.`);
      }
    });
    if (!cellMap.size) {
      throw new Error("Cached bundle has 0 value cells. Render refused.");
    }
    state.valuesByCell = cellMap;

    // Rebuild context (fail-open: empty on corrupt)
    try {
      state.contextByKey = indexPlayerContext(bundle.contextRows || []);
    } catch (e) {
      console.warn("[product-data] cached context corrupt; using empty.");
      state.contextByKey = new Map();
    }

    state.initialized = true;
    state.fromCache = true;
    console.info(
      `[product-data] ready from cache snapshot=${state.snapshot.snapshot_id} ` +
      `players=${state.players.length} cells=${state.valuesByCell.size}`
    );
    return publicHandle;
  }

  // ---------- Fixtures adapter (kill switch) ----------

  // When ?dataSource=fixtures is set, bypass the network entirely and build
  // the 5-method API from the inline #players-data / #methodology-data
  // islands. Best-effort: values come from the fixture's ROS fields, marked
  // with value_provenance="fixtures" so consumers know it's static data.
  function initFromFixtures() {
    if (state.initialized) return publicHandle;
    console.warn("[product-data] FIXTURES MODE: bypassing API, reading inline islands.");
    showDegradedBanner("Using fixtures (override). Live data bypassed.");

    let fixture = null;
    try {
      const el = window.document.getElementById("players-data");
      if (!el) throw new Error("#players-data island not found");
      fixture = JSON.parse(el.textContent);
    } catch (err) {
      throw new Error(`Fixtures override requested but #players-data island unreadable: ${err.message}. Remove ?dataSource=fixtures to use live API.`);
    }

    const fixturePlayers = Array.isArray(fixture.players) ? fixture.players : [];
    if (!fixturePlayers.length) {
      throw new Error("Fixtures override requested but #players-data has 0 players. Remove ?dataSource=fixtures to use live API.");
    }
    const meta = fixture.meta || {};

    // Build synthetic snapshot from fixture meta
    const snapshotId = `fixtures-${meta.as_of || "unknown"}`;
    state.snapshot = Object.freeze({
      snapshot_id: snapshotId,
      contract_version: CONTRACT_VERSION,
      built_at: meta.as_of || null,
      value_weeks: Object.freeze({}),
      sources: Object.freeze({}),
      source_validation: Object.freeze({}),
      espn_zeroed: Object.freeze([]),
      methodology_combos: null,
      reference_freshness: null,
      health: null,
      is_active: true,
      publishable: true,
      generated_at: null,
      bake_ids: null,
      pie_vintage_per_source: null,
      players_snapshot_at: null,
      context_meta: Object.freeze({ note: "Fixtures mode: no live context." }),
    });
    state.activeSnapshotId = snapshotId;
    state.sourcesMap = {};

    // Synthetic options (defaults from buildOptions)
    state.options = buildOptions({});

    // Map fixture players to api.players shape.
    // canonical_name is the ONLY name source — fixture `name` is the
    // canonical spelling in the baked island (no fallback chain).
    state.players = Object.freeze(fixturePlayers.map(fp => {
      const playerKey = Number(fp.player_key);
      const canonicalName = String(fp.name || "").trim();
      const pos = String(fp.pos || "");
      const team = fp.team != null && String(fp.team) !== "" ? String(fp.team) : "—";
      const ppgObj = v => (v && typeof v === "object" ? JSON.parse(JSON.stringify(v)) : null);
      return Object.freeze({
        player_key: playerKey,
        canonical_name: canonicalName,
        pos,
        team,
        ir_zeroed: false,
        kdst_excluded_from_chart: pos === "K" || pos === "DST",
        espn_ppg: ppgObj(fp.espn_ppg),
        rz_ppg: ppgObj(fp.rz_ppg),
        cbsros_ppg: ppgObj(fp.cbsros_ppg),
        ecr_ppg: ppgObj(fp.ecr_ppg),
        agent_ranking_ppg: null,
        blend_ppg: ppgObj(fp.blend_ppg),
        games_remaining: parseNum(fp.games_remaining),
        full_name: canonicalName,
        name: canonicalName,
      });
    }));
    state.playerByKey = new Map();
    state.players.forEach(p => state.playerByKey.set(p.player_key, p));

    // Build synthetic value cells from fixture ROS fields.
    // Field priority per source; falls back to blend_ros (the DDF value).
    const fixtureRows = fixturePlayers;
    state._fixtureRows = fixtureRows;
    state.valuesByCell = new Map(); // built lazily by getPlayerValues
    state.contextByKey = new Map(); // fixtures have no news context

    state.initialized = true;
    state.fixturesMode = true;
    console.info(`[product-data] fixtures mode ready players=${state.players.length} snapshot=${snapshotId}`);
    return publicHandle;
  }

  // Fixture field priority for getPlayerValues in fixtures mode.
  // Each entry: list of fixture ROS field names to try (first hit wins).
  // Scoring dimension: fixture ROS objects are keyed by scoring
  // (standard/half_ppr/ppr).
  const FIXTURE_VALUE_FIELDS = Object.freeze({
    espn: ["espn_filled_ros", "espn_ros"],
    cbsros: ["cbsros_ros"],
    razzball: ["rz_filled_ros", "rz_ros"],
    // All other sources fall back to the DDF blend (best effort).
    __default: ["blend_ros"],
  });

  function fixtureFieldFor(source) {
    return FIXTURE_VALUE_FIELDS[source] || FIXTURE_VALUE_FIELDS.__default;
  }

  // Build (and memoize) a synthetic cell from fixture rows.
  function getFixtureCell(source, scoring, teams, qbVariant, view) {
    const key = cellKeyFor(source, scoring, teams, qbVariant, view) + "|fixtures";
    let cell = state.valuesByCell.get(key);
    if (cell) return cell;
    const fields = fixtureFieldFor(source);
    const values = new Map();
    for (const fp of (state._fixtureRows || [])) {
      const playerKey = Number(fp.player_key);
      if (!Number.isInteger(playerKey)) continue;
      let v = null;
      for (const f of fields) {
        const ros = fp[f];
        if (ros && typeof ros === "object" && ros[scoring] != null) {
          const n = Number(ros[scoring]);
          if (Number.isFinite(n)) { v = n; break; }
        }
      }
      if (v !== null) values.set(playerKey, v);
    }
    cell = {
      values,
      valueProvenance: "fixtures",
      modelVsPublished: null,
      tierPriceVector: null,
      pieVintage: null,
      bakeId: null,
      detailLocator: null,
      indexTotal: null,
      hasAnyRow: values.size > 0,
    };
    state.valuesByCell.set(key, cell);
    return cell;
  }

  // Original init logic, now called initFromLive
  async function initFromLive(expectedVersion) {

    // 1. Fetch api.product_snapshot. The view filters to is_active=true AND
    // publishable=true; empty → no active snapshot → fail-closed.
    const snapshotRows = await fetchViewAll(VIEWS.productSnapshot);
    if (!snapshotRows.length) {
      throw new Error(`${VIEWS.productSnapshot} returned 0 rows (no active snapshot). Render refused.`);
    }
    const activeSnapshotRow = snapshotRows.find(r => r.is_active !== false) || snapshotRows[0];
    const snapshotContractVersion = String(activeSnapshotRow.contract_version || "");
    if (snapshotContractVersion !== CONTRACT_VERSION) {
      throw new Error(`${VIEWS.productSnapshot} contract_version mismatch (snapshot=${snapshotContractVersion || "<missing>"}, expected=${CONTRACT_VERSION}). Render refused.`);
    }
    state.snapshot = buildSnapshot([activeSnapshotRow]);
    state.activeSnapshotId = state.snapshot.snapshot_id;
    state.sourcesMap = state.snapshot.sources || {};

    // 2. Fetch api.product_options (singleton). verify its contract_version
    // matches the snapshot's contract_version (§7.5).
    const optionsRows = await fetchViewAll(VIEWS.productOptions);
    if (!optionsRows.length) {
      throw new Error(`${VIEWS.productOptions} returned 0 rows. Render refused.`);
    }
    state.options = buildOptions(optionsRows[0]);
    if (state.options.contract_version !== CONTRACT_VERSION) {
      throw new Error(`${VIEWS.productOptions} contract_version mismatch (options=${state.options.contract_version || "<missing>"}, snapshot=${snapshotContractVersion}). Render refused.`);
    }
    if (state.options.contract_version !== snapshotContractVersion) {
      throw new Error(`${VIEWS.productOptions} contract_version mismatch (options=${state.options.contract_version}, snapshot=${snapshotContractVersion}). Render refused.`);
    }

    // 3. sourceMapCoverage on the snapshot (§8.2).
    verifySourceMapCoverage(state.options, state.snapshot);

    // 4. Fetch api.players (single batch).
    const playerRows = await fetchViewAll(VIEWS.players);
    if (!playerRows.length) {
      throw new Error(`${VIEWS.players} returned 0 rows. Render refused.`);
    }
    state.players = buildPlayers(playerRows);
    state.playerByKey = new Map();
    state.players.forEach(p => state.playerByKey.set(p.player_key, p));

    // 5. Fetch api.player_values (paginated; ~20k rows today).
    const valueRows = await fetchViewAll(VIEWS.playerValues);
    if (!valueRows.length) {
      throw new Error(`${VIEWS.playerValues} returned 0 rows. Render refused.`);
    }

    // 6. Fail-closed guards (§5.1, §6.1, §3.1.2).
    verifyPieVintageGuard(valueRows, state.snapshot.snapshot_id);
    verifyTierPriceVintageGuard(valueRows, state.snapshot.snapshot_id);
    verifyPlayerValuesSourceMap(valueRows, state.options);

    // 7. Index by cell.
    state.valuesByCell = indexPlayerValues(valueRows);

    // 8. Fetch api.player_context. Missing context is a known fail-open path
    // (§5.2: player-news fetch fail → context empty). We don't throw on
    // empty result; getPlayerContext() returns null for unknown keys.
    let contextRows = [];
    try {
      contextRows = await fetchViewAll(VIEWS.playerContext);
    } catch (err) {
      console.warn(`[product-data] ${VIEWS.playerContext} fetch failed; news columns will render empty.`);
      contextRows = [];
    }
    state.contextByKey = indexPlayerContext(contextRows);

    state.initialized = true;

    // Write the snapshot-keyed cache bundle for offline fallback.
    // Best-effort: quota failures warn and continue (no cache available).
    try {
      const bundle = serializeBundle(
        activeSnapshotRow, optionsRows[0], playerRows, contextRows, state.valuesByCell
      );
      writeBundleCache(state.snapshot.snapshot_id, bundle);
    } catch (e) {
      console.warn("[product-data] cache bundle serialize/write failed:", e.message);
    }

    console.info(
      `[product-data] ready contract=${CONTRACT_VERSION} ` +
      `snapshot=${state.snapshot.snapshot_id} ` +
      `players=${state.players.length} ` +
      `cells=${state.valuesByCell.size} ` +
      `context=${state.contextByKey.size}`
    );
    return publicHandle;
  }

  // ---------- Public handle (frozen) ----------

  // The five semantic methods + transitional helpers. Consumers hold this
  // handle and never read window.TradeValueProductData internals.
  const publicHandle = Object.freeze({
    // The five contract surfaces (spec §8.1).
    getPlayerValues,
    getPlayers,
    getPlayerContext,
    getProductOptions,
    getSnapshot,
    // Transitional helpers (not contract surfaces).
    getAdjustmentInputs,
    getPlayerByKey,
    getPlayerKeysBySourceId,
    getProviderInfo,
    // Constants exported so consumers stop redefining them locally.
    SOURCE_KEYS,
    ADJUSTED_INDEXED_KEYS,
    PURE_VORP_KEYS,
    AS_PUBLISHED_KEYS,
    QB_AWARE_SOURCES,
    CONTRACT_VERSION,
  });

  // ---------- Export ----------

  const api = {
    initProductData,
    // Re-export the five semantic methods at the top level so callers can
    // import the module as a flat namespace without the handle.
    getPlayerValues,
    getPlayers,
    getPlayerContext,
    getProductOptions,
    getSnapshot,
    // Transitional + meta.
    getAdjustmentInputs,
    getPlayerByKey,
    getPlayerKeysBySourceId,
    getProviderInfo,
    handle: () => publicHandle,
    SOURCE_KEYS,
    ADJUSTED_INDEXED_KEYS,
    PURE_VORP_KEYS,
    AS_PUBLISHED_KEYS,
    QB_AWARE_SOURCES,
    CONTRACT_VERSION,
  };
  if (typeof window !== "undefined") {
    window.TradeValueProductData = api;
  }
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})();