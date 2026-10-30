// JEG-1320: one stored record for the trade finders' discovery controls (slice 1 of docs/specs/trade-page-parity.md).
//
// Jeremy's 5A (JEG-1220, 2026-10-29): common preferences are shared across the trade pages; page-specific controls stay
// separate. The locked three-screen plan (2026-10-29) has one finder, so its discovery controls are one record whichever
// scope runs it:
//
//   maxSize              package size, 1 to 4                                   default 2
//   keepMine, keepTheirs keep my / their starting lineup filled                 default on
//   protectedPositions, minBackups, minDdfEdge, minUserLineupGain, minTheirLineupGain
//                        guardrails                                             default off
//   viableOnly           show only viable trades (session only, never saved)   default off
//   filters              {fit, opponent, minCapture, minCharts}                 default all / all / 0 / 0
//   hideForce            hide force fits                                        default off
//
// Today the two finders store parts of this in two places (workspace ui): the your-team finder keeps ui.finderSettings
// (size 1 to 4, keep flags, guardrails), the league finder keeps ui.maxSize (2 to 4), ui.filters and ui.hideForce, and
// always searches with both keep flags on and no guardrails. fromPair and fromLeague read each route's stored shape and
// give exactly the values that route uses today. fromWorkspace is the D3 migration (pick A, 2026-10-29, Claude's
// reversible pick): the your-team finder's finderSettings.maxSize wins and the league's ui.maxSize is dropped.
//
// Pure: no DOM, no storage writes, no engine values. Nothing here changes a default, a value or a listing rule. The
// size, keep and guardrail fields go through workspace.js's normalizeFinderSettings, so this record and the saved
// finder settings cannot disagree. No route reads this yet: JEG-1321 (league) and JEG-1322 (your team) wire it in.
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(() => require("./workspace.js"));
  else root.TradeValueDiscoveryControls = factory(() => root.TradeValueWorkspace);
})(typeof window !== "undefined" ? window : globalThis, function (workspaceApi) {
  "use strict";

  const VERSION = 1;
  const SIZES = [1, 2, 3, 4];
  // The sizes the league finder's Package size menu offers today (league.js); 1-for-1 arrives with JEG-1321.
  const LEAGUE_SIZES = [2, 3, 4];
  // opportunities.js filterRows: all / natural / naturalMarket; an older saved "naturalValue" means naturalMarket.
  const FITS = ["all", "natural", "naturalMarket"];
  const GUARDRAIL_KEYS = ["protectedPositions", "minBackups", "minDdfEdge", "minUserLineupGain", "minTheirLineupGain"];

  const isObject = v => Boolean(v) && typeof v === "object" && !Array.isArray(v);
  const finite = n => typeof n === "number" && Number.isFinite(n);
  function deepFreeze(value) {
    if (value && typeof value === "object" && !Object.isFrozen(value)) {
      Object.freeze(value);
      Object.values(value).forEach(deepFreeze);
    }
    return value;
  }

  // Same rules trade-context.js applies to the league finder's saved filters (routeControls), so both read one way.
  function normalizeFilters(raw) {
    const f = isObject(raw) ? raw : {};
    const nonNeg = v => (finite(Number(v)) && Number(v) >= 0 ? Number(v) : 0);
    return {fit: f.fit === "naturalValue" ? "naturalMarket" : FITS.includes(f.fit) ? f.fit : "all",
      opponent: f.opponent === undefined || f.opponent === null ? "all" : String(f.opponent),
      minCapture: nonNeg(f.minCapture), minCharts: nonNeg(f.minCharts)};
  }

  // raw: a record in this module's own shape (or part of one). Anything missing or invalid takes its default.
  function normalize(raw) {
    const r = isObject(raw) ? raw : {};
    const finder = workspaceApi().normalizeFinderSettings(r);
    return deepFreeze({version: VERSION, maxSize: finder.maxSize, keepMine: finder.keepMine, keepTheirs: finder.keepTheirs,
      protectedPositions: finder.protectedPositions, minBackups: finder.minBackups, minDdfEdge: finder.minDdfEdge,
      minUserLineupGain: finder.minUserLineupGain, minTheirLineupGain: finder.minTheirLineupGain,
      viableOnly: Boolean(r.viableOnly), filters: normalizeFilters(r.filters), hideForce: Boolean(r.hideForce)});
  }
  const DEFAULTS = normalize(null);

  // ---------- each route's stored shape in, one record out ----------
  // Your-team finder (finder.js): settings is ws.ui.finderSettings; session is the page's unsaved state ({viableOnly}).
  // It has no fit, opponent, capture, charts or force filters today, so those stay at their defaults.
  function fromPair(settings, session) {
    const s = isObject(settings) ? settings : {};
    const v = isObject(session) ? session : {};
    const picked = {};
    ["maxSize", "keepMine", "keepTheirs"].concat(GUARDRAIL_KEYS).forEach(key => { if (key in s) picked[key] = s[key]; });
    return normalize({...picked, viableOnly: v.viableOnly});
  }
  // League finder (league.js): ui is the workspace ui. It reads ui.maxSize || 2 from a 2-to-4 menu, ui.filters and
  // ui.hideForce, and searches with both keep flags on and no guardrails (it never reads ui.finderSettings).
  function fromLeague(ui) {
    const u = isObject(ui) ? ui : {};
    return normalize({maxSize: LEAGUE_SIZES.includes(Number(u.maxSize)) ? Number(u.maxSize) : 2, keepMine: true, keepTheirs: true,
      filters: u.filters, hideForce: u.hideForce});
  }
  // D3 pick A: one record from a workspace ui holding both stored shapes. Size, keep flags and guardrails come from
  // ui.finderSettings; ui.maxSize is dropped (droppedOnMigration says when that loses a different value). The filters
  // and hideForce come from ui, the only place they are stored. viableOnly is never saved, so it starts off.
  function fromWorkspace(ui, session) {
    const u = isObject(ui) ? ui : {};
    const pair = fromPair(u.finderSettings, session);
    return normalize({...pair, filters: u.filters, hideForce: u.hideForce});
  }
  // The stored values the D3 migration does not keep. [] when nothing is lost.
  function droppedOnMigration(ui) {
    const u = isObject(ui) ? ui : {};
    if (!("maxSize" in u)) return [];
    const league = fromLeague(u).maxSize;
    const kept = fromWorkspace(u).maxSize;
    return league === kept ? [] : deepFreeze([{field: "maxSize", from: "ui.maxSize", value: league, kept, keptFrom: "ui.finderSettings.maxSize"}]);
  }

  // ---------- one record out, in the shapes the routes consume ----------
  // What changes the set of trades found: findTrades' maxSize, sanity keep flags and guardrails (finder.js).
  function searchOf(record) {
    const c = normalize(record);
    return deepFreeze({maxSize: c.maxSize, keepMine: c.keepMine, keepTheirs: c.keepTheirs,
      guardrails: Object.fromEntries(GUARDRAIL_KEYS.map(key => [key, c[key]]))});
  }
  // What only narrows the list after the search: filterRows' filters and hideForce (opportunities.js), and viable only.
  function listingOf(record) {
    const c = normalize(record);
    return deepFreeze({filters: c.filters, hideForce: c.hideForce, viableOnly: c.viableOnly});
  }
  // The patch for TradeValueWorkspace.ops.setUi that saves a record. ui.maxSize is not written (D3 A drops it), and
  // viableOnly is not saved (it is session state today).
  function toUiPatch(record) {
    const c = normalize(record);
    return deepFreeze({finderSettings: workspaceApi().normalizeFinderSettings(c), filters: c.filters, hideForce: c.hideForce});
  }

  return {VERSION, SIZES, LEAGUE_SIZES, FITS, GUARDRAIL_KEYS, DEFAULTS, normalize, normalizeFilters, fromPair, fromLeague,
    fromWorkspace, droppedOnMigration, searchOf, listingOf, toUiPatch};
});
