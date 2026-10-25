// JEG-1031: the league -> engine-input mapping (supabase/functions/get-values/league.ts), no network.
// Run by tests/test_league_mapping.py. The page-vs-endpoint value parity is tests/test_endpoint_parity.py.
import assert from "node:assert/strict";
import { leagueKey, mapLeague } from "../../supabase/functions/get-values/league.ts";

const cfg = { content_week: 6, defaults: { objective: "season", injury_history: "recent",
  league_weeks: { regular_season_end: 14, playoff_weeks: [15, 17] }, projection_confidence: 1 } };

// The default league maps to exactly what get-values hard-coded before JEG-1031.
const d = mapLeague({ scoring: "ppr", teams: 12 }, cfg);
assert.deepEqual(d.setting, { teams: 12, slots: { QB: 1, RB: 2, WR: 2, TE: 1 }, flex: 1, superflex: 0,
  bench_per_team: 7, bench_share: 0.15, bench_share_override: null, position_shares: null });
assert.deepEqual(d.lineupArgs, { objective: "season", injury_history: "recent",
  league_weeks: { regular_season_end: 14, playoff_weeks: [15, 17] }, projection_confidence: 1, content_week: null });
assert.deepEqual(d.custom, []);

// A custom league: roster, shares, bench override, advanced and weeks all map.
const c = mapLeague({ scoring: "half_ppr", teams: 10, roster: { WR: 3, BENCH: 6, SUPERFLEX: 1, K: 1 },
  shares: { QB: 0.2, RB: 0.4, WR: 0.3, TE: 0.1 }, bso: 0.2, inj: "all", conf: 1.5,
  weeks: { regend: 13, playoffs: [14, 16], optimize: "playoffs", week: 9 } }, cfg);
assert.equal(c.teams, 10);
assert.equal(c.setting.slots.WR, 3);
assert.equal(c.setting.bench_per_team, 6);
assert.equal(c.setting.superflex, 1);
assert.equal(c.setting.bench_share_override, 0.2);
assert.equal(c.setting.bench_share, 0.2);
assert.deepEqual(c.setting.position_shares, { QB: 0.2, RB: 0.4, WR: 0.3, TE: 0.1 });
assert.deepEqual(c.lineupArgs, { objective: "playoffs", injury_history: "all",
  league_weeks: { regular_season_end: 13, playoff_weeks: [14, 16] }, projection_confidence: 1.5, content_week: 9 });
assert.deepEqual(c.custom.sort(), ["bso", "conf", "inj", "optimize", "roster", "shares", "week", "weeks"]);

// Clamps are the page's: FLEX/WR 0 -> 1, BENCH 99 -> 14, bso 0.9 -> 0.30, shares floor at 0.01.
const k = mapLeague({ scoring: "ppr", teams: 12, roster: { FLEX: 0, BENCH: 99, QB: 9 }, bso: 0.9,
  shares: { QB: 0, RB: 0.5, WR: 0.5, TE: 0 } }, cfg);
assert.equal(k.setting.flex, 1);
assert.equal(k.setting.bench_per_team, 14);
assert.equal(k.setting.slots.QB, 5);
assert.equal(k.setting.bench_share_override, 0.3);
const sh = k.setting.position_shares;
assert.ok(sh.QB >= 0.01 - 1e-9 && sh.TE >= 0.01 - 1e-9);
assert.ok(Math.abs(Object.values(sh).reduce((a, b) => a + b, 0) - 1) < 1e-9);

// What the page would reject falls back to the default; the build's own week is no override.
const r = mapLeague({ scoring: "ppr", teams: 12, weeks: { regend: 15, playoffs: [14, 17], week: 6 }, conf: 2, inj: "x" }, cfg);
assert.deepEqual(r.lineupArgs.league_weeks, { regular_season_end: 14, playoff_weeks: [15, 17] });
assert.equal(r.lineupArgs.content_week, null);
assert.equal(r.lineupArgs.projection_confidence, 1);
assert.deepEqual(r.custom, []);

// Equal leagues share a cache key; a changed field does not. Garbage input never throws.
assert.equal(leagueKey(d), leagueKey(mapLeague({ scoring: "ppr", teams: 12, roster: { WR: 2 } }, cfg)));
assert.notEqual(leagueKey(d), leagueKey(mapLeague({ scoring: "ppr", teams: 12, roster: { WR: 3 } }, cfg)));
mapLeague(null, null); mapLeague("x", cfg); mapLeague({ roster: "x", shares: 5, weeks: [] }, cfg);
console.log("ok");
