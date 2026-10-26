// JEG-1115: the connector's fit label (Natural / Market supported / Force) and reason.
// Pure Node, deterministic. Run by tests/test_mcp_remote.py.
//
// Three things are checked:
//   (a) findTradesForPair output carries fit + fit_reason for every trade, and fit is null
//       when no fit context is supplied;
//   (b) parity: on the same trades the connector's label and reason equal the finder's own
//       tradeFit / fitText (the rule lives in app/v2/finder.js, JEG-1108) — the same inputs
//       tests/node/fit_diagnostic.cjs uses (the 20-team fixture league, team 0 = you);
//   (c) the check fails when the label is removed: find-trades.ts is mutated (the fit attach
//       stubbed out), bundled, and the same assertions must fail on its output.
//
// The connector's fit module is transpiled with esbuild (like tests/node/viability_check.mjs),
// so this runs on the repo's node without --experimental-strip-types.

import assert from "node:assert/strict";
import { execSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "../..");
const MCP = join(ROOT, "supabase/functions/mcp");
const OUT_DIR = join(__dirname, ".fit_build");
if (!existsSync(OUT_DIR)) mkdirSync(OUT_DIR, { recursive: true });

const bundle = (entry, out) =>
  execSync(`npx --yes esbuild "${entry}" --bundle --format=esm --outfile="${out}" --platform=node`, { stdio: "pipe" });

bundle(join(MCP, "fit.ts"), join(OUT_DIR, "fit.mjs"));
bundle(join(MCP, "find-trades.ts"), join(OUT_DIR, "find-trades.mjs"));

const { FIT_LABELS, fitForTrade, buildFitContext, benchWeightsFromPlayers } = await import(join(OUT_DIR, "fit.mjs"));
const { findTradesForPair } = await import(join(OUT_DIR, "find-trades.mjs"));

const require = createRequire(import.meta.url);
const F = require(join(ROOT, "app/v2/finder.js"));
const O = require(join(ROOT, "app/v2/opportunities.js"));
const fixture = JSON.parse(readFileSync(join(ROOT, "tests/fixtures/league/fixture-20team.json"), "utf8"));

// ---------------------------------------------------------------------------
// The fixture league, exactly as tests/node/fit_diagnostic.cjs builds it.
// ---------------------------------------------------------------------------

const CH = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
const SHAPE = { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0 };
const ALLOCATION = [{ pos: "QB", rostered: 30, lineup: 12, bench: 18 }, { pos: "RB", rostered: 60, lineup: 36, bench: 24 },
  { pos: "WR", rostered: 66, lineup: 36, bench: 30 }, { pos: "TE", rostered: 24, lineup: 12, bench: 12 }];
const WEIGHTS = { overall: 0.3, QB: 0.2, RB: 0.3, WR: 0.3, TE: 0.25 };

const hash = (text) => { let h = 2166136261; for (const c of String(text)) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619) >>> 0; } return h >>> 0; };
const unit = (key, salt) => (hash(`${key}:${salt}`) % 10000) / 10000;
function makeRows(players) {
  const map = new Map();
  players.forEach((p) => {
    if (String(p.key).startsWith("x:") || map.has(String(p.key))) return;
    const ddf = Math.round((4 + 36 * Math.pow(unit(p.key, "d"), 1.6)) * 10) / 10;
    const values = { ddf_value: ddf };
    const market = 0.62 + 0.76 * unit(p.key, "m");
    CH.forEach((k) => { values[k] = Math.round(ddf * market * (0.9 + 0.2 * unit(p.key, k)) * 10) / 10; });
    map.set(String(p.key), { player_key: String(p.key), name: p.name, pos: p.pos, team: p.team || "", values });
  });
  return map;
}

const rows = makeRows([].concat(...fixture.teams.map((t) => t.players)));
const teams = fixture.teams.map((t, i) => ({ id: `t${i}`, name: t.name, entries: t.players.map((p) => ({ key: String(p.key) })) }));
const mine = teams[0].entries.map((e) => rows.get(e.key)).filter(Boolean);

// The fit context the finder page builds: the league shape, the compared charts, the
// engine's bench weights and expected depth. The connector builds it in fitContextFor().
const expected = F.expectedDepth(ALLOCATION, 12);
const fitCtx = buildFitContext(F, { shape: SHAPE, chartKeys: CH, weights: WEIGHTS, expected, z: F.FIT_Z });
assert.ok(fitCtx, "the fit context builds from the fixture's shape and charts");
assert.equal(fitCtx.z, F.FIT_Z, "the noise floor multiplier is the finder's FIT_Z");
assert.equal(fitCtx.marketKey, F.MARKET_KEY);

const mineAvg = F.withChartAverage(mine, CH);

// ---------------------------------------------------------------------------
// (b) parity: connector label == the finder's own tradeFit on the same trades
// ---------------------------------------------------------------------------

let compared = 0;
const counts = { Natural: 0, "Market supported": 0, Force: 0 };
for (const opp of teams.slice(1)) {
  const theirs = opp.entries.map((e) => rows.get(e.key)).filter(Boolean);
  const theirAvg = F.withChartAverage(theirs, CH);
  const byKey = new Map([...mineAvg, ...theirAvg].map((r) => [String(r.player_key), r]));
  const wide = (list) => list.map((r) => byKey.get(String(r.player_key)) || r);
  // The trades tests/node/fit_diagnostic.cjs judges (same opts the opportunities table uses).
  const res = F.findTrades(mine, theirs, { chartKeys: CH, maxSize: 2, limit: F.LIMIT,
    sanity: { shape: SHAPE, mine, theirs, keepMine: true, keepTheirs: true } });
  for (const t of res.trades) {
    const give = wide(t.give);
    const recv = wide(t.receive);
    const reference = F.tradeFit({ mine: { roster: mineAvg, leaving: give, arriving: recv },
      theirs: { roster: theirAvg, leaving: recv, arriving: give } }, fitCtx);
    const got = fitForTrade(F, mine, theirs, t.give, t.receive, fitCtx);
    const id = `${opp.name}: ${t.give.map((r) => r.name).join("+")} for ${t.receive.map((r) => r.name).join("+")}`;
    assert.equal(got.fit, FIT_LABELS[reference.label], `label parity — ${id}`);
    assert.equal(got.fit_reason, F.fitText(reference), `reason parity — ${id}`);
    counts[got.fit] += 1;
    compared += 1;
  }
}
assert.ok(compared > 0, "the fixture league produced trades to judge");
assert.equal(counts.Natural + counts["Market supported"] + counts.Force, compared, "every trade got a label");
assert.ok(counts.Natural > 0 && counts["Market supported"] > 0 && counts.Force > 0,
  `the rule separates trades on the fixture: ${JSON.stringify(counts)}`);

// The same set tests/node/fit_diagnostic.cjs counts: the connector's label for each of its
// rows equals the label the diagnostic reports (its overall fit), row for row.
{
  const entries = (t) => t.players.map((p) => ({ key: String(p.key), name: p.name, pos: p.pos, team: p.team || "" }));
  const oppTeams = fixture.teams.map((t, i) => ({ id: `t${i}`, name: t.name, isMine: i === 0, entries: entries(t) }));
  const ctx = { rowsByKey: rows, shape: SHAPE, expected, weights: WEIGHTS, charts: CH.slice(), market: CH.slice(),
    chartKeys: CH.slice(), maxSize: 2, keepMine: true, keepTheirs: true };
  const out = await O.runAll(oppTeams[0], oppTeams.slice(1), ctx,
    { cache: O.createCache(), yieldFn: () => Promise.resolve(), budgetMs: 0 });
  assert.equal(out.rows.length, compared, "the diagnostic's rows are the same trades");
  const rosterOf = new Map(oppTeams.map((t) => [t.id, t.entries.map((e) => rows.get(e.key)).filter(Boolean)]));
  for (const row of out.rows) {
    const got = fitForTrade(F, mine, rosterOf.get(row.opponentId), row.give, row.receive, fitCtx);
    assert.equal(got.fit, FIT_LABELS[row.overall], `fit_diagnostic row parity — ${row.id}`);
  }
}

// ---------------------------------------------------------------------------
// (a) the connector's trade output carries the label and a plain-English reason
// ---------------------------------------------------------------------------

/** Every trade must carry one of the three labels and a non-empty reason. */
function assertTradesCarryFit(result) {
  assert.ok(Array.isArray(result.trades) && result.trades.length > 0, "trades to check");
  for (const t of result.trades) {
    assert.ok(["Natural", "Market supported", "Force"].includes(t.fit),
      `trade carries a fit label (got ${JSON.stringify(t.fit)})`);
    assert.equal(typeof t.fit_reason, "string", "trade carries a fit_reason string");
    assert.ok(t.fit_reason.length > 20, "the reason is a plain-English sentence");
  }
}

const theirs1 = teams[1].entries.map((e) => rows.get(e.key)).filter(Boolean);
const wired = findTradesForPair(F, mine, theirs1, { maxSize: 2, limit: 50, fit: fitCtx });
assertTradesCarryFit(wired);
// The label sits next to the existing viability fields.
assert.equal(typeof wired.trades[0].edge, "number");
assert.ok(Array.isArray(wired.trades[0].charts));

// Without a fit context the field is present and null (the rule was not judged).
const bare = findTradesForPair(F, mine, theirs1, { maxSize: 2, limit: 50 });
assert.ok(bare.trades.length > 0);
assert.ok(bare.trades.every((t) => t.fit === null && t.fit_reason === null), "no context, no label");

// ---------------------------------------------------------------------------
// (c) mutant: with the label stubbed out of find-trades.ts, the check must fail
// ---------------------------------------------------------------------------

const ATTACH = `      const fit = opts?.fit
        ? fitForTrade(finder, mine, theirs, t.give, t.receive, opts.fit)
        : { fit: null, fit_reason: null };`;
const src = readFileSync(join(MCP, "find-trades.ts"), "utf8");
assert.ok(src.includes(ATTACH), "the mutant anchor is still in find-trades.ts");
writeFileSync(join(OUT_DIR, "fit.ts"), readFileSync(join(MCP, "fit.ts")));
writeFileSync(join(OUT_DIR, "find-trades.mutant.ts"),
  src.replace(ATTACH, "      const fit = { fit: null, fit_reason: null };"));
bundle(join(OUT_DIR, "find-trades.mutant.ts"), join(OUT_DIR, "find-trades.mutant.mjs"));
const { findTradesForPair: mutant } = await import(join(OUT_DIR, "find-trades.mutant.mjs"));
const broken = mutant(F, mine, theirs1, { maxSize: 2, limit: 50, fit: fitCtx });
assert.ok(broken.trades.length > 0, "the mutant still finds trades");
assert.throws(() => assertTradesCarryFit(broken), /fit label/, "the check catches a removed label");

// ---------------------------------------------------------------------------
// The bench-share weights (the engine's readout, read back from published values + tiers)
// ---------------------------------------------------------------------------

{
  const players = [
    { player_key: 1, pos: "RB", value: 30, tier: "starter" },
    { player_key: 2, pos: "RB", value: 10, tier: "bench" },
    { player_key: 3, pos: "RB", value: 10, tier: "waiver" },
    { player_key: 4, pos: "QB", value: 20, tier: "starter" },
    { player_key: 5, pos: "QB", value: 20, tier: "bench" },
  ];
  const w = benchWeightsFromPlayers(players);
  assert.equal(w.RB, 10 / 50, "RB bench tier as a share of RB value");
  assert.equal(w.QB, 0.5, "QB bench tier as a share of QB value");
  assert.equal(w.WR, 0, "a position with no priced players reads 0");
  assert.equal(w.overall, (10 + 20) / (50 + 40), "overall share over every position");
}

console.log("ok");
