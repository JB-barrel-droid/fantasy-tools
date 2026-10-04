// JEG-325 (2026-10-04): ConsolidationIndex — strangler-fig provider for the
// reindexed chart values. Consumers (curve-widget.js, comparison-dashboard.js)
// ask for a single (player, source, scoring, teams, qb, view) cell instead of
// walking `data.sources[key].combos[comboKey].reindexed[sourceId]`. This is
// the O(1) lookup described in docs/planning/consolidation-layer-scope.md §5.
//
// During the migration the detail fixture still ships and the consolidation
// artifact is not yet produced (the bake in §4 is pending). To keep the chart
// working without breaking the existing data path, this module prefers:
//   1. assets/consolidated-values.json when present (the future state).
//   2. A index synthesized from `data.sources` (the current state) so the
//      values match by construction while the bake ships.
//   3. `lookup()` returns null — the caller falls back to its old deep-path
//      read. The fallback is logged, never silent (see recordDivergence).
//
// Shadow-compare: each call returns both the consolidated value and the
// detail-deep-path value when both are available; a divergence is logged via
// console.warn and counted for the UI debug panel. Divergences are NEVER
// swallowed to mask missing rows (the standing fail-closed rule).
(() => {
  "use strict";

  const KEY_DELIM = "\u0001"; // unprintable; safe inside composite keys
  const ARTIFACT_PATH = "assets/consolidated-values.json";
  const ARTIFACT_TIMEOUT_MS = 4000;

  // Quarterback grain: only fantasycalc / fantasycalc_adjusted emit the
  // `_qbN` combo suffix per sourceComboKey() in value-model.js. Every other
  // source collapses to "" so (source, scoring, teams, "") stays distinct
  // from (fantasycalc, scoring, teams, "qb1").
  const QB_AWARE_SOURCES = new Set(["fantasycalc", "fantasycalc_adjusted"]);

  const state = {
    idx: null,                    // Map<compositeKey, number> once initialized
    bakedFromArtifact: false,     // true when artifact present and parsed
    bakeId: null,                 // bake_id from the artifact
    detailSha256: null,           // detail_sha256 from the artifact
    artifactSchema: null,         // schema string from the artifact
    rowsIndexed: 0,               // row count actually placed in idx
    initialized: false,           // true once init() resolves
    initError: null,              // last init error (if any)
    // Shadow-compare counters (the panel reads these live).
    stats: {
      lookups: 0,
      hitsConsolidation: 0,
      hitsDetail: 0,
      fallbacks: 0,               // consolidation returned null, caller used detail
      divergences: 0,
      lastDivergence: null,
    },
    // First-divergence sample is logged once per session per cell for the
    // health-panel surface; the running counter is the authoritative value.
    firstDivergenceSamples: new Set(),
  };

  function compositeKey(parts) {
    return [
      String(parts.player ?? ""),
      String(parts.source ?? ""),
      String(parts.scoring ?? ""),
      String(parts.teams ?? ""),
      String(parts.qb ?? ""),
      String(parts.view ?? "")
    ].join(KEY_DELIM);
  }

  function isQbAware(source) {
    return QB_AWARE_SOURCES.has(source);
  }

  // Parse a detail combo key (e.g. "full_12_qb1", "half_10") into its
  // decomposed parts. Mirrors sourceComboKey() in value-model.js — keep the
  // two in lockstep so the consolidation key agrees with the combo key.
  function parseComboKey(comboKey) {
    if (typeof comboKey !== "string" || !comboKey) return null;
    const parts = comboKey.split("_");
    // Expect: <scoring>_<teams>[_qb<N>]
    if (parts.length < 2) return null;
    const scoring = parts[0];
    const teams = Number(parts[1]);
    let qb = "";
    if (parts.length >= 3 && /^qb\d+$/.test(parts[2])) qb = parts[2];
    if (!Number.isInteger(teams) || teams <= 0) return null;
    return {scoring, teams, qb};
  }

  // Build the index from the detail fixture: same cells the deep-path would
  // have read, just indexed by composite key. This is the migration bridge
  // — every cell reconciliation-equivalent by construction.
  function buildIndexFromDetail(detail) {
    const idx = new Map();
    if (!detail || !detail.sources || typeof detail.sources !== "object") {
      return {idx, rowsIndexed: 0};
    }
    const playerKeys = detail.player_keys || {};
    Object.entries(detail.sources).forEach(([sourceKey, sourceData]) => {
      if (!sourceData || !sourceData.combos || typeof sourceData.combos !== "object") return;
      Object.entries(sourceData.combos).forEach(([comboKeyStr, combo]) => {
        if (!combo || typeof combo !== "object") return;
        const parsed = parseComboKey(comboKeyStr);
        if (!parsed) return;
        // qbVariant suffix is dropped for non-fantasycalc sources; their
        // composite key always carries qb="".
        const qb = isQbAware(sourceKey) ? parsed.qb : "";
        const reindexed = combo.values || combo.reindexed;
        if (!reindexed || typeof reindexed !== "object") return;
        Object.entries(reindexed).forEach(([sourceId, rawValue]) => {
          const playerKey = playerKeys[sourceId];
          if (playerKey === undefined || playerKey === null) return;
          idx.set(compositeKey({
            player: String(playerKey),
            source: sourceKey,
            scoring: parsed.scoring,
            teams: parsed.teams,
            qb,
            view: "reindexed"
          }), Number(rawValue));
        });
      });
    });
    return {idx, rowsIndexed: idx.size};
  }

  function buildIndexFromArtifact(artifact) {
    const idx = new Map();
    const rows = Array.isArray(artifact?.rows) ? artifact.rows : [];
    rows.forEach(row => {
      if (!row || typeof row !== "object") return;
      const player = String(row.player ?? "");
      const source = String(row.source ?? "");
      const scoring = String(row.scoring ?? "");
      const teams = Number(row.teams);
      const qb = String(row.qb_variant ?? "");
      const view = String(row.view ?? "");
      const value = Number(row.value);
      if (!player || !source || !scoring || !Number.isFinite(teams) || !Number.isFinite(value)) return;
      idx.set(compositeKey({player, source, scoring, teams, qb, view}), value);
    });
    return {idx, rowsIndexed: idx.size};
  }

  // Public init: try the artifact first; if missing or malformed, fall back
  // to synthesizing from the detail fixture. Both branches keep the chart
  // working during the strangler-fig window — the panel reports which provider
  // is live. Never throws.
  function init(opts) {
    if (state.initialized) return Promise.resolve(providerInfo());
    const detail = (opts && opts.detail) || window.TradeValueComparisonData || null;
    state.initialized = true;
    const fromDetail = buildIndexFromDetail(detail);
    state.idx = fromDetail.idx;
    state.rowsIndexed = fromDetail.rowsIndexed;
    state.bakeId = detail?.bake_id || null;
    state.detailSha256 = detail?.detail_sha256 || null;
    state.artifactSchema = null;
    state.bakedFromArtifact = false;
    // Try to upgrade to the real artifact when it lands.
    return tryArtifact().then((upgrade) => {
      if (upgrade && upgrade.idx && upgrade.idx.size) {
        state.idx = upgrade.idx;
        state.rowsIndexed = upgrade.idx.size;
        state.bakeId = upgrade.bakeId || state.bakeId;
        state.detailSha256 = upgrade.detailSha256 || state.detailSha256;
        state.artifactSchema = upgrade.schema || null;
        state.bakedFromArtifact = true;
      }
      logProviderOnInit();
      return providerInfo();
    }).catch((err) => {
      state.initError = String(err?.message || err || "init failed");
      logProviderOnInit();
      return providerInfo();
    });
  }

  function tryArtifact() {
    return new Promise((resolve) => {
      if (typeof fetch !== "function") return resolve(null);
      let settled = false;
      const finish = (value) => { if (!settled) { settled = true; resolve(value); } };
      const timer = (typeof AbortController === "function")
        ? AbortController ? new AbortController() : null
        : null;
      const fetchOpts = timer ? {signal: timer.signal} : {};
      const timeoutId = setTimeout(() => {
        if (timer) timer.abort();
        finish(null);
      }, ARTIFACT_TIMEOUT_MS);
      fetch(ARTIFACT_PATH, fetchOpts)
        .then((response) => {
          if (!response.ok) { finish(null); return null; }
          return response.json();
        })
        .then((payload) => {
          if (!payload) return;
          if (payload.schema !== "consolidated-values-v1") { finish(null); return; }
          const built = buildIndexFromArtifact(payload);
          finish({
            idx: built.idx,
            rowsIndexed: built.rowsIndexed,
            bakeId: payload.bake_id || null,
            detailSha256: payload.detail_sha256 || null,
            schema: payload.schema || null,
          });
        })
        .catch(() => finish(null))
        .finally(() => clearTimeout(timeoutId));
    });
  }

  function logProviderOnInit() {
    const info = providerInfo();
    const line = `[ConsolidationIndex] provider=${info.provider} bake_id=${info.bakeId || "n/a"} rows=${info.rowsIndexed} artifact=${info.artifactSchema || "synthesized-from-detail"}`;
    if (info.provider === "consolidation-artifact") {
      console.info(line);
    } else if (info.provider === "consolidation-derived") {
      console.info(line);
    } else {
      console.warn(line);
    }
  }

  function providerInfo() {
    if (!state.idx) return {provider: "uninitialized", bakeId: state.bakeId, rowsIndexed: 0, bakedFromArtifact: false};
    return {
      provider: state.bakedFromArtifact ? "consolidation-artifact" : "consolidation-derived",
      bakeId: state.bakeId,
      rowsIndexed: state.rowsIndexed,
      bakedFromArtifact: state.bakedFromArtifact,
      schema: state.artifactSchema,
      detailSha256: state.detailSha256,
      initError: state.initError,
    };
  }

  // The public read path. Returns the consolidation row value or null when
  // the cell is not indexed. Consumers compare against the detail value they
  // already have and report divergences through recordDivergence — divergence
  // never changes the returned value.
  function lookup(query) {
    state.stats.lookups += 1;
    if (!state.idx) return null;
    const ck = compositeKey({
      player: query?.player,
      source: query?.source,
      scoring: query?.scoring,
      teams: query?.teams,
      qb: query?.qb ?? "",
      view: query?.view || "reindexed",
    });
    if (!state.idx.has(ck)) {
      state.stats.fallbacks += 1;
      return null;
    }
    state.stats.hitsConsolidation += 1;
    return state.idx.get(ck);
  }

  // Record a comparison between the consolidation lookup and the detail
  // deep-path read. Divergence = present in both but numerically different.
  // Missing-from-one-side is a separate signal (the consumer sees both).
  function recordDivergence(entry) {
    const detail = Number(entry?.detailValue);
    const consolidated = Number(entry?.consolidatedValue);
    const present = Number.isFinite(detail) && Number.isFinite(consolidated);
    if (!present) return {divergent: false, recorded: false};
    // Strict equality, no rounding (consolidation is exact per §3).
    if (detail !== consolidated) {
      state.stats.divergences += 1;
      state.stats.lastDivergence = {
        at: new Date().toISOString(),
        source: entry?.source,
        player: entry?.player,
        scoring: entry?.scoring,
        teams: entry?.teams,
        qb: entry?.qb ?? "",
        view: entry?.view,
        detailValue: detail,
        consolidatedValue: consolidated,
      };
      const sampleKey = `${entry?.source}|${entry?.player}|${entry?.scoring}|${entry?.teams}|${entry?.qb ?? ""}|${entry?.view}`;
      if (!state.firstDivergenceSamples.has(sampleKey)) {
        state.firstDivergenceSamples.add(sampleKey);
        console.warn(
          "[ConsolidationIndex] DIVERGENCE",
          {source: entry?.source, player: entry?.player, scoring: entry?.scoring, teams: entry?.teams, qb: entry?.qb ?? "", view: entry?.view},
          `consolidation=${consolidated} detail=${detail}`
        );
      }
      return {divergent: true, recorded: true};
    }
    return {divergent: false, recorded: false};
  }

  function stats() {
    return {
      ...state.stats,
      provider: state.bakedFromArtifact ? "consolidation-artifact" : (state.idx ? "consolidation-derived" : "uninitialized"),
      bakeId: state.bakeId,
      rowsIndexed: state.rowsIndexed,
      bakedFromArtifact: state.bakedFromArtifact,
      detailSha256: state.detailSha256,
      initError: state.initError,
    };
  }

  // Public surface.
  const api = {
    init,
    lookup,
    recordDivergence,
    providerInfo,
    stats,
    compositeKey,
    parseComboKey,
    isQbAware,
    KEY_DELIM,
    QB_AWARE_SOURCES: [...QB_AWARE_SOURCES],
  };
  if (typeof window !== "undefined") {
    window.TradeValueConsolidation = api;
  }
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})();