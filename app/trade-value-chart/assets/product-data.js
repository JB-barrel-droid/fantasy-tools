// JEG-363 (2026-10-04): FE adapter for the JEG-327 v1 read contract.
//
// This is the ONLY module in app/trade-value-chart/ that talks to the
// contract surfaces. Every other FE module (curve-widget.js,
// comparison-dashboard.js, future methodology renderer, etc.) calls into this
// module and never reads a legacy fixture path directly.
//
// Contract spec: docs/contract/fe-read-contract-v1.md §8
//   - Five semantic methods: getPlayerValues(), getPlayers(),
//     getPlayerContext(), getProductOptions(), getSnapshot().
//   - initProductData() is fail-closed (contract_version mismatch,
//     source_map_coverage failure, empty players, missing active snapshot).
//
// During the Phase D migration the api.* contract views are not yet
// materialised (Roman applies the DDL in sql/contract/api_v1.sql separately
// and runs `NOTIFY pgrst, 'reload schema'`). To keep the chart rendering
// during the strangler-fig window, this adapter reads the legacy fixtures
// (assets/comparison-sources-data.json, assets/player-news.json,
// assets/adjustment-inputs.json, the #players-data inline island) and
// projects them into the contract's frozen surface shapes. The fixture
// paths remain ONLY here; consumers call into the five semantic methods.
//
// Alignment with JEG-325 (consolidation-index.js): the per-cell value
// lookups that JEG-325 already indexes are reused via the
// window.TradeValueConsolidation.handle. This module owns the fixture
// fetch + projection; consolidation-index owns the per-cell O(1) lookup.
// When the contract api.* materialises, this module's reader swaps to PostgREST
// without changing the five public methods.

(() => {
  "use strict";

  // ---------- Configuration ----------

  const CONTRACT_VERSION = "1.0.0";

  // Legacy fixture paths. v1 contract backs these with api.* views; until
  // those views are published we read the fixtures and project them. These
  // strings must NOT appear anywhere in app/trade-value-chart/ except here.
  const LEGACY_PATHS = Object.freeze({
    detail: "assets/comparison-sources-data.json",
    news: "assets/player-news.json",
    adjustments: "assets/adjustment-inputs.json",
    playersInlineId: "players-data",
  });

  const FETCH_TIMEOUT_MS = 4000;

  // Source keys verbatim from contract §3.4.2 (api.product_options.source_keys).
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
    // Pure VORP keys (raw value-above-waivers curves).
    "espn_vorp",
    "cbsros_vorp",
    "razzball_vorp",
  ]);

  // Adjusted indexed keys (drive the pause logic in §3.4.2).
  const ADJUSTED_INDEXED_KEYS = Object.freeze([
    "fantasycalc_adjusted",
    "usatoday_adjusted",
    "fantasypros_adjusted",
    "cbs_adjusted",
  ]);

  // Pure VORP keys (browser-computed from per-game projections).
  const PURE_VORP_KEYS = Object.freeze(["espn_vorp", "cbsros_vorp", "razzball_vorp"]);

  // As-published sources (singleScale: true in normalizeToFixedPie).
  const AS_PUBLISHED_KEYS = Object.freeze(["usatoday", "fantasycalc", "fantasypros", "cbs"]);

  // FantasyCalc family emits _qbN combo suffix; every other source collapses.
  // Mirrors consolidation-index.js QB_AWARE_SOURCES so the two stay in sync.
  const QB_AWARE_SOURCES = new Set(["fantasycalc", "fantasycalc_adjusted"]);

  // ---------- Internal state ----------

  const state = {
    initialized: false,
    initError: null,
    detail: null,            // raw legacy comparison-sources-data.json
    news: null,              // raw legacy player-news.json
    adjustments: null,       // raw legacy adjustment-inputs.json
    players: [],             // canonical players from inline island
    playerByKey: new Map(),  // player_key -> player record
    playerKeysBySourceId: new Map(), // sourceId -> playerKey (legacy fixture)
    consolidation: null,     // reference to window.TradeValueConsolidation
    snapshot: null,          // contract-shaped api.product_snapshot
    options: null,           // contract-shaped api.product_options
    activeSnapshotId: null,
  };

  // ---------- Fetch helpers ----------

  function fetchJSON(path, timeoutMs) {
    if (typeof fetch !== "function") return Promise.reject(new Error("fetch unavailable"));
    let controller = null;
    let timer = null;
    if (typeof AbortController === "function") {
      try {
        controller = new AbortController();
      } catch (e) {
        controller = null;
      }
    }
    const opts = controller ? { signal: controller.signal } : {};
    return new Promise((resolve, reject) => {
      timer = setTimeout(() => {
        if (controller) controller.abort();
        reject(new Error(`${path} fetch timed out after ${timeoutMs}ms`));
      }, timeoutMs);
      fetch(path, opts)
        .then(response => {
          if (!response.ok) {
            reject(new Error(`${path} request failed (${response.status})`));
            return null;
          }
          return response.json();
        })
        .then(payload => {
          clearTimeout(timer);
          resolve(payload);
        })
        .catch(err => {
          clearTimeout(timer);
          reject(err);
        });
    });
  }

  function loadPlayersInline() {
    if (typeof document === "undefined") return {};
    try {
      const el = document.getElementById(LEGACY_PATHS.playersInlineId);
      return el ? JSON.parse(el.textContent || "{}") : {};
    } catch (e) {
      return {};
    }
  }

  // ---------- Contract-shape projection ----------

  // Build api.product_snapshot (frozen). Field shape per contract §3.5.2.
  function buildSnapshot(detail, news) {
    const sources = detail && typeof detail.sources === "object" ? detail.sources : {};
    return Object.freeze({
      snapshot_id: String(detail?.bake_id || "legacy-fixture"),
      contract_version: CONTRACT_VERSION,
      built_at: detail?.built_at || null,
      value_weeks: detail?.value_weeks || {},
      sources,
      source_validation: detail?.source_validation || {},
      espn_zeroed: Array.isArray(detail?.espn_zeroed) ? [...detail.espn_zeroed] : [],
      methodology_combos: detail?.methodology_combos || null,
      reference_freshness: detail?.reference_freshness || null,
      // pie_vintage_per_source: contract §3.5.2 — bake_id keyed map. Legacy
      // fixture collapses to bake_id globally; consumers should treat a null
      // here as "not published yet, fall back to bake_id".
      pie_vintage_per_source: detail?.pie_vintage_per_source || null,
      players_snapshot_at: detail?.built_at || null,
      context_meta: news?.meta || null,
      bake_id: detail?.bake_id || null,
      // Marker so callers can tell the v1-fixture projection from a real
      // api.* surface (the v1 cutover will flip it false).
      _isLegacyProjection: true,
    });
  }

  // Build api.product_options (frozen). Field shape per contract §3.4.2.
  function buildOptions() {
    return Object.freeze({
      product_key: "default",
      contract_version: CONTRACT_VERSION,
      bench_share: Object.freeze({
        default: 0.15,
        min: 0.01,
        max: 0.30,
        user_settable: true,
      }),
      bench_share_default: 0.15,
      bench_share_min: 0.01,
      bench_share_max: 0.30,
      bench_share_user_settable: true,
      default_scoring: "full",
      default_teams: 12,
      default_roster_shape: Object.freeze({ QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, BENCH: 6 }),
      default_lock_order: "espn",
      default_view_mode: "indexed",
      default_reference_source: "usatoday",
      default_position_weights: null,
      min_shared_for_pie: 40,
      starter_markup_sane_band: Object.freeze([0.98, 1.6]),
      peak_agreement_band: Object.freeze([0.80, 1.25]),
      source_keys: SOURCE_KEYS,
      adjusted_indexed_keys: ADJUSTED_INDEXED_KEYS,
      pure_vorp_keys: PURE_VORP_KEYS,
      as_published_keys: AS_PUBLISHED_KEYS,
      _isLegacyProjection: true,
    });
  }

  // Build api.players (frozen array). Field shape per contract §3.2.2.
  // The legacy inline island exposes {player_key, full_name, name, pos,
  // team, espn_ppg, rz_ppg, cbsros_ppg, ecr_ppg, blend_ppg, games_remaining,
  // ir_zeroed}. We forward the fields consumers already read (full_name,
  // espn_ppg, rz_ppg, cbsros_ppg) and add the contract-mandated
  // canonical_name + kdst_excluded_from_chart + ir_zeroed so the cutover
  // does not change downstream semantics.
  function buildPlayers(playersPayload) {
    const raw = Array.isArray(playersPayload?.players) ? playersPayload.players : [];
    return Object.freeze(raw.map(player => {
      const playerKey = Number(player.player_key);
      const canonicalName = String(player.full_name || player.name || "").trim();
      const pos = String(player.pos || "");
      const isKdst = pos === "K" || pos === "DST";
      return Object.freeze({
        player_key: playerKey,
        canonical_name: canonicalName,
        pos,
        team: String(player.team || "—"),
        ir_zeroed: Boolean(player.ir_zeroed),
        kdst_excluded_from_chart: isKdst,
        espn_ppg: player.espn_ppg || null,
        rz_ppg: player.rz_ppg || null,
        cbsros_ppg: player.cbsros_ppg || null,
        ecr_ppg: player.ecr_ppg || null,
        blend_ppg: player.blend_ppg || null,
        games_remaining: Number.isFinite(Number(player.games_remaining)) ? Number(player.games_remaining) : null,
        // Legacy aliases (removed by the v1 contract cutover).
        full_name: canonicalName,
        name: canonicalName,
        _isLegacyProjection: true,
      });
    }));
  }

  // Build the per-cell composite key (matches consolidation-index.js exactly).
  // Mirrors ValueModel.sourceComboKey for the suffix logic.
  function comboKeyFor(source, scoring, teams, qbVariant) {
    const needsQb = QB_AWARE_SOURCES.has(source);
    const qbSuffix = needsQb ? `_${qbVariant || "qb1"}` : "";
    return `${scoring}_${teams}${qbSuffix}`;
  }

  // ---------- Public surface (the five semantic methods) ----------

  // getPlayerValues({source, scoring, teams, qbVariant, view}) — contract §8.1.
  // Returns a frozen per-cell object, or null when the cell is not on the
  // shipped snapshot. The returned Map<playerKey, number> is the FE's only
  // read for per-cell values; legacy deep-path reads are eliminated.
  function getPlayerValues(query) {
    if (!state.initialized || !state.detail) {
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
    // browser computes them from per-game projections); return null and let
    // the consumer read api.players via getPlayers() for the projection.
    if (PURE_VORP_KEYS.includes(source)) return null;

    const detail = state.detail;
    const sourceKey = source === "cbs_adjusted" ? "cbs" : source;
    const comboKeyStr = comboKeyFor(sourceKey, scoring, teams, qbVariant);
    const combo = detail.sources?.[sourceKey]?.combos?.[comboKeyStr];
    if (!combo) return null;

    // Reindexed values are the default for combo_reindexed; native comes
    // from combo.native; passthrough view has its own field (not in legacy).
    let cellField = null;
    if (view === "combo_reindexed") cellField = combo.values || combo.reindexed || null;
    else if (view === "native") cellField = combo.native || null;
    else if (view === "vorp" || view === "vorp_indexed" || view === "adj_values") {
      // Legacy fixture does not yet separate these views; collapse to the
      // reindexed cell until the bake ships them.
      cellField = combo.values || combo.reindexed || null;
    }
    if (!cellField) return null;

    const values = new Map();
    Object.entries(cellField).forEach(([sourceId, rawValue]) => {
      const playerKey = state.playerKeysBySourceId.get(sourceId);
      if (!Number.isInteger(playerKey)) return;
      const num = Number(rawValue);
      if (!Number.isFinite(num)) return;
      values.set(playerKey, num);
    });

    // pie_vintage: bake_id for combo_reindexed / ddf_translated; null for
    // passthrough. Legacy projection: bake_id globally.
    const pieVintage = (view === "combo_reindexed") ? (state.snapshot?.bake_id || null) : null;

    // value_provenance: legacy projection cannot enumerate all six enum
    // values; infer from source and view.
    let valueProvenance = "native";
    if (view === "combo_reindexed") {
      valueProvenance = QB_AWARE_SOURCES.has(sourceKey) ? "indexed" : "indexed";
    } else if (view === "vorp") valueProvenance = "vorp";
    else if (view === "vorp_indexed") valueProvenance = "vorp_indexed";
    else if (view === "adj_values") valueProvenance = "adj";

    let modelVsPublished = "published";
    if (["espn", "cbsros", "razzball"].includes(sourceKey)) modelVsPublished = "model";

    const detailLocator = `sources.${sourceKey}.combos.${comboKeyStr}.${cellField === combo.native ? "native" : "values"}`;

    return Object.freeze({
      values,
      tier_price_vector: null, // not in legacy; v1 ships per §3.1.2 once bake lands
      pie_vintage: pieVintage,
      bake_id: state.snapshot?.bake_id || null,
      coverage_class: values.size ? "full" : "view_limited_source",
      value_provenance: valueProvenance,
      model_vs_published: modelVsPublished,
      detail_locator: detailLocator,
      // Legacy alias so the comparator + dashboard row can show source
      // metadata without re-reading the snapshot.
      source_meta: state.snapshot?.sources?.[sourceKey] || null,
      index_total: combo.index_total || null,
      _isLegacyProjection: true,
    });
  }

  // getPlayers() — contract §8.1. Returns a frozen array of api.players.
  function getPlayers() {
    if (!state.initialized) {
      throw new Error("product-data.js: getPlayers() called before initProductData() resolved. Render refused.");
    }
    return state.players;
  }

  // getPlayerContext(playerKey) — contract §8.1. Returns a frozen
  // {news[], adjustments[], as_of} or null when the player has no context.
  function getPlayerContext(playerKey) {
    if (!state.initialized) {
      throw new Error("product-data.js: getPlayerContext() called before initProductData() resolved. Render refused.");
    }
    if (!state.news) return null;
    const key = String(playerKey);
    const news = state.news.news_by_player_key?.[key] || [];
    const adjustments = state.news.adjustments_by_player_key?.[key] || [];
    if (!news.length && !adjustments.length) return null;
    return Object.freeze({
      news: Object.freeze([...news]),
      adjustments: Object.freeze([...adjustments]),
      as_of: state.news.meta?.trade_values_published_at || null,
    });
  }

  // getProductOptions() — contract §8.1. Returns the singleton.
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

  // getAdjustmentInputs(): the raw adjustment-inputs.json payload. The
  // contract does not yet have a surface for the stage-2 alpha/beta cells
  // (the JEG-322 publish gate will land them in api.player_values eventually).
  // Returning the legacy payload from a single module keeps the deep-path
  // reads out of consumers. Returns null when inputs absent/malformed.
  function getAdjustmentInputs() {
    if (!state.initialized) return null;
    return state.adjustments;
  }

  // getPlayerByKey(playerKey): convenience accessor so consumers don't have
  // to iterate getPlayers() on every chart tick.
  function getPlayerByKey(playerKey) {
    if (!state.initialized) return null;
    const key = Number(playerKey);
    return state.playerByKey.get(key) || null;
  }

  // getPlayerKeysBySourceId(): the legacy fixture's sourceId -> playerKey
  // map (used to build the values map for non-anchor sources during the
  // strangler-fig window). Returns null when no detail loaded.
  function getPlayerKeysBySourceId() {
    if (!state.initialized) return null;
    return state.playerKeysBySourceId;
  }

  // getProviderInfo(): debug surface for the chart health panel.
  function getProviderInfo() {
    if (!state.initialized) {
      return { provider: "uninitialized", initError: state.initError };
    }
    return {
      provider: "legacy-fixture-projection",
      contractVersion: CONTRACT_VERSION,
      bakeId: state.snapshot?.bake_id || null,
      playersLoaded: state.players.length,
      newsLoaded: !!state.news,
      adjustmentsLoaded: !!state.adjustments,
      consolidationProvider: state.consolidation?.providerInfo?.() || null,
      initError: state.initError,
    };
  }

  // ---------- Fail-closed init ----------

  // initProductData({contractVersion="1.0.0"} = {})
  // Contract §8.2 fail-closed semantics:
  //   - detail fetch fails → throws
  //   - contract_version mismatch → throws
  //   - players empty → throws
  //   - source_map_coverage failed → throws
  //   - consolidation init threw → throws (defense in depth; the index is
  //     used by every per-cell lookup so its absence is fail-closed).
  async function initProductData(opts) {
    if (state.initialized) {
      return publicHandle;
    }
    const options = opts || {};
    const expectedVersion = options.contractVersion || CONTRACT_VERSION;
    if (expectedVersion !== CONTRACT_VERSION) {
      throw new Error(`Unknown contract version ${expectedVersion}. Render refused.`);
    }

    // Detail is mandatory (the chart's primary data is here).
    let detail;
    try {
      detail = await fetchJSON(LEGACY_PATHS.detail, FETCH_TIMEOUT_MS);
    } catch (err) {
      throw new Error(`Data contract fetch failed (${LEGACY_PATHS.detail}): ${err && err.message ? err.message : err}. Render refused.`);
    }
    if (!detail || typeof detail !== "object") {
      throw new Error("Data contract payload is empty. Render refused.");
    }

    // News + adjustment inputs are best-effort: contract §5.2 fail-open
    // semantics. We log a warning when they are absent and continue.
    const newsP = fetchJSON(LEGACY_PATHS.news, FETCH_TIMEOUT_MS).catch(() => null);
    const adjustmentsP = fetchJSON(LEGACY_PATHS.adjustments, FETCH_TIMEOUT_MS).catch(() => null);
    const [news, adjustments] = await Promise.all([newsP, adjustmentsP]);
    if (!news) {
      console.warn("[product-data] assets/player-news.json absent; news columns will render empty.");
    }
    if (!adjustments) {
      console.warn("[product-data] assets/adjustment-inputs.json absent; *_adjusted columns will pause per runRegressionGuards.");
    }

    state.detail = detail;
    state.news = news;
    state.adjustments = adjustments;

    // Players from the inline island; throw on missing (contract §8.2).
    const playersPayload = loadPlayersInline();
    state.players = buildPlayers(playersPayload);
    state.playerByKey = new Map();
    state.players.forEach(p => state.playerByKey.set(p.player_key, p));

    // sourceId -> player_key map (legacy fixture uses string IDs; the
    // canonical identity is the player_key integer).
    state.playerKeysBySourceId = new Map();
    const detailPlayerKeys = detail?.player_keys || {};
    Object.entries(detailPlayerKeys).forEach(([sourceId, playerKey]) => {
      const num = Number(playerKey);
      if (Number.isInteger(num)) state.playerKeysBySourceId.set(sourceId, num);
    });

    // Build contract-shaped snapshot + options.
    state.snapshot = buildSnapshot(detail, news);
    state.options = buildOptions();
    state.activeSnapshotId = state.snapshot.snapshot_id;

    // Source map coverage: every key in api.product_options.source_keys must
    // have a snapshot entry. cbs_adjusted is a derived column on cbs.
    const sourcesMap = state.snapshot.sources || {};
    const missing = SOURCE_KEYS.filter(k => {
      if (PURE_VORP_KEYS.includes(k)) return false; // pure VORP has no fixture entry
      if (k === "cbs_adjusted") return !sourcesMap.cbs;
      return !sourcesMap[k];
    });
    if (missing.length) {
      throw new Error(`sourceMapCoverage failed: missing ${missing.join(", ")}. Render refused.`);
    }

    // Wire up the consolidation index (JEG-325 bridge) for per-cell O(1) lookups.
    // We pass the already-fetched detail so it does not refetch.
    if (typeof window !== "undefined" && window.TradeValueConsolidation) {
      try {
        await window.TradeValueConsolidation.init({ detail });
        state.consolidation = window.TradeValueConsolidation;
      } catch (err) {
        throw new Error(`ConsolidationIndex init failed: ${err && err.message ? err.message : err}. Render refused.`);
      }
    }

    state.initialized = true;
    console.info(`[product-data] ready contract=${CONTRACT_VERSION} bake=${state.snapshot.bake_id || "n/a"} players=${state.players.length}`);
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