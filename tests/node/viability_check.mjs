// JEG-1038: unit tests for mcp/viability.ts.
// Each viability check is tested with a passing case AND a negative test
// against a simulated broken state (the check must fail when it should).
// Run: node tests/node/viability_check.mjs

import { strict as assert } from "node:assert";
import { execSync } from "node:child_process";
import { mkdirSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

// ---------------------------------------------------------------------------
// Transpile viability.ts with esbuild so we can import pure TS in node.
// ---------------------------------------------------------------------------

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "../..");
const SRC = join(ROOT, "supabase/functions/mcp/viability.ts");
const OUT_DIR = join(__dirname, ".viability_build");
const OUT = join(OUT_DIR, "viability.mjs");

if (!existsSync(OUT_DIR)) mkdirSync(OUT_DIR, { recursive: true });
execSync(`npx --yes esbuild "${SRC}" --bundle --format=esm --outfile="${OUT}" --platform=node`, { stdio: "pipe" });

const V = await import(OUT);
const {
  runViabilityChecks,
  scoreAndRankOffers,
  selectPackage,
  DEFAULT_CONFIG,
} = V;

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

const SHAPE = { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, SUPERFLEX: 0 };

function makePlayer(key, name, pos, ddf, charts = {}, opts = {}) {
  const values = { ddf_value: ddf, ...charts };
  return { player_key: key, name, pos, values, ddfTier: opts.tier || (ddf >= 5 ? "starter" : "bench"), status: opts.status, weeksOut: opts.weeksOut };
}

const c = (v) => ({ usatoday: v, fantasycalc: v, fantasypros: v, cbs: v });

// A basic roster: 1 QB, 3 RB, 4 WR, 1 TE, some bench
function makeRoster(prefix, ddfBase, marketBase) {
  const id = prefix.charCodeAt(0) * 100;
  return [
    makePlayer(id + 1, `${prefix}-QB1`, "QB", ddfBase + 20, c(marketBase + 20), { tier: "starter" }),
    makePlayer(id + 2, `${prefix}-RB1`, "RB", ddfBase + 15, c(marketBase + 15), { tier: "starter" }),
    makePlayer(id + 3, `${prefix}-RB2`, "RB", ddfBase + 10, c(marketBase + 10), { tier: "starter" }),
    makePlayer(id + 4, `${prefix}-RB3`, "RB", ddfBase + 3, c(marketBase + 3), { tier: "bench" }),
    makePlayer(id + 5, `${prefix}-WR1`, "WR", ddfBase + 14, c(marketBase + 14), { tier: "starter" }),
    makePlayer(id + 6, `${prefix}-WR2`, "WR", ddfBase + 11, c(marketBase + 11), { tier: "starter" }),
    makePlayer(id + 7, `${prefix}-WR3`, "WR", ddfBase + 8, c(marketBase + 8), { tier: "starter" }),
    makePlayer(id + 8, `${prefix}-WR4`, "WR", ddfBase + 2, c(marketBase + 2), { tier: "bench" }),
    makePlayer(id + 9, `${prefix}-TE1`, "TE", ddfBase + 6, c(marketBase + 6), { tier: "starter" }),
    makePlayer(id + 10, `${prefix}-BN1`, "RB", ddfBase + 1, c(marketBase + 1), { tier: "bench" }),
  ];
}

const userRoster = makeRoster("U", 10, 10);
const theirRoster = makeRoster("T", 8, 12);

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    passed++;
    console.log(`  PASS  ${name}`);
  } catch (e) {
    failed++;
    console.error(`  FAIL  ${name}: ${e.message}`);
  }
}

function findCheck(result, name) {
  return result.checks.find((ch) => ch.name === name);
}

// ---------------------------------------------------------------------------
// Check 1: Arbitrage
// ---------------------------------------------------------------------------
console.log("\n--- Check 1: Arbitrage ---");

test("passes when user gains DDF value", () => {
  const result = runViabilityChecks(
    userRoster, theirRoster,
    [userRoster[3]], // U-RB3 ddf=13
    [theirRoster[1]], // T-RB1 ddf=23
    SHAPE,
  );
  assert.ok(findCheck(result, "arbitrage").passed, "arbitrage should pass");
});

test("NEGATIVE: fails when user loses DDF value", () => {
  const result = runViabilityChecks(
    userRoster, theirRoster,
    [userRoster[1]], // U-RB1 ddf=25
    [theirRoster[3]], // T-RB3 ddf=11
    SHAPE,
  );
  assert.ok(!findCheck(result, "arbitrage").passed, "arbitrage should fail when user loses value");
});

// ---------------------------------------------------------------------------
// Check 2: Perceived fairness
// ---------------------------------------------------------------------------
console.log("\n--- Check 2: Perceived fairness ---");

test("passes when other team gains on market value", () => {
  // User gives WR2(mkt=21), gets their RB3(mkt=15).
  // They give RB3(15 mkt), get WR2(21 mkt) -> they gain 6.
  const result = runViabilityChecks(
    userRoster, theirRoster,
    [userRoster[5]], // U-WR2 market=21
    [theirRoster[3]], // T-RB3 market=15
    SHAPE,
  );
  assert.ok(findCheck(result, "perceived_fairness").passed, "fairness should pass");
});

test("NEGATIVE: fails when trade looks lopsided to them", () => {
  // User gives BN1(mkt=11), gets their RB1(mkt=27). They give 27 get 11 = -16
  const result = runViabilityChecks(
    userRoster, theirRoster,
    [userRoster[9]], // U-BN1 market=11
    [theirRoster[1]], // T-RB1 market=27
    SHAPE,
  );
  assert.ok(!findCheck(result, "perceived_fairness").passed, "fairness should fail when lopsided");
});

// ---------------------------------------------------------------------------
// Check 3: User's starting lineup improves
// ---------------------------------------------------------------------------
console.log("\n--- Check 3: User lineup improves ---");

test("passes when user lineup gets stronger", () => {
  const result = runViabilityChecks(
    userRoster, theirRoster,
    [userRoster[3]], // U-RB3 ddf=13 (bench)
    [theirRoster[1]], // T-RB1 ddf=23
    SHAPE,
  );
  assert.ok(findCheck(result, "user_lineup_improves").passed, "user lineup should improve");
});

test("NEGATIVE: fails when user lineup gets weaker", () => {
  const result = runViabilityChecks(
    userRoster, theirRoster,
    [userRoster[1]], // U-RB1 ddf=25
    [theirRoster[9]], // T-BN1 ddf=9
    SHAPE,
  );
  assert.ok(!findCheck(result, "user_lineup_improves").passed, "user lineup should not improve");
});

// ---------------------------------------------------------------------------
// Check 4: Other team's starting lineup improves
// ---------------------------------------------------------------------------
console.log("\n--- Check 4: Their lineup improves ---");

test("passes when their lineup gets stronger on market value", () => {
  // User gives WR1(mkt=24), gets their WR4(mkt=14). They give WR4, get WR1 -> improves
  const result = runViabilityChecks(
    userRoster, theirRoster,
    [userRoster[4]], // U-WR1 market=24
    [theirRoster[7]], // T-WR4 market=14
    SHAPE,
  );
  assert.ok(findCheck(result, "their_lineup_improves").passed, "their lineup should improve");
});

test("NEGATIVE: fails when their lineup gets weaker on market value", () => {
  // User gives WR4(mkt=12), gets their WR1(mkt=26). They give WR1(26), get WR4(12)
  const result = runViabilityChecks(
    userRoster, theirRoster,
    [userRoster[7]], // U-WR4 market=12
    [theirRoster[4]], // T-WR1 market=26
    SHAPE,
  );
  assert.ok(!findCheck(result, "their_lineup_improves").passed, "their lineup should not improve");
});

// ---------------------------------------------------------------------------
// Check 5: Position protection (total starting lineup market value)
// ---------------------------------------------------------------------------
console.log("\n--- Check 5: Position protection (total lineup) ---");

test("passes when their total starting lineup holds or improves", () => {
  // They give their BN1 (RB, bench-tier, not a starter) and get a WR.
  // Their starting lineup is unchanged -> total value holds.
  const result = runViabilityChecks(
    userRoster, theirRoster,
    [userRoster[7]], // U-WR4 ddf=12, market=12
    [theirRoster[9]], // T-BN1 (RB, ddf=9, market=13) — their lowest, not a starter
    SHAPE,
  );
  assert.ok(findCheck(result, "position_protection").passed,
    "bench RB swap should not hurt their total lineup: " + findCheck(result, "position_protection").detail);
});

test("NEGATIVE: fails when trade creates an unfillable starting slot", () => {
  // Tiny roster: they have exactly 1 QB and we take it, giving them a WR.
  // After: 0 QBs -> unfillable QB slot.
  const tinyTheir = [
    makePlayer(8001, "T-QB1", "QB", 20, c(20)),
    makePlayer(8002, "T-RB1", "RB", 18, c(18)),
    makePlayer(8003, "T-RB2", "RB", 15, c(15)),
    makePlayer(8004, "T-RB3", "RB", 10, c(10)),
    makePlayer(8005, "T-WR1", "WR", 17, c(17)),
    makePlayer(8006, "T-WR2", "WR", 14, c(14)),
    makePlayer(8007, "T-WR3", "WR", 11, c(11)),
    makePlayer(8008, "T-WR4", "WR", 8, c(8)),
    makePlayer(8009, "T-TE1", "TE", 12, c(12)),
  ];
  const result = runViabilityChecks(
    userRoster, tinyTheir,
    [userRoster[7]], // U-WR4 (give them a WR)
    [tinyTheir[0]], // Take their only QB
    SHAPE,
  );
  const ch = findCheck(result, "position_protection");
  assert.ok(!ch.passed, "should fail when trade creates an unfillable starting slot: " + ch.detail);
  assert.ok(ch.detail.includes("unable to fill"), "detail should mention unfillable slots: " + ch.detail);
});

test("NEGATIVE: fails when their total starting lineup value drops", () => {
  // They give both RB1 and RB2 (their top starters), get only low-value WRs.
  // After: they still fill all slots but with much weaker players -> total drops.
  const bigUser = [...userRoster, makePlayer(9901, "X-WR5", "WR", 20, c(20))];
  const result = runViabilityChecks(
    bigUser, theirRoster,
    [bigUser[4], bigUser[5]], // U-WR1(mkt=24), U-WR2(mkt=21) — they get these
    [theirRoster[1], theirRoster[2]], // T-RB1(mkt=27), T-RB2(mkt=22) — they lose these
    SHAPE,
  );
  const ch = findCheck(result, "position_protection");
  assert.ok(!ch.passed, "should fail when their total starting lineup drops: " + ch.detail);
});

// ---------------------------------------------------------------------------
// Check 6: Depth
// ---------------------------------------------------------------------------
console.log("\n--- Check 6: Depth ---");

test("passes when both teams have adequate depth", () => {
  const result = runViabilityChecks(
    userRoster, theirRoster,
    [userRoster[7]], [theirRoster[7]],
    SHAPE,
  );
  assert.ok(findCheck(result, "depth").passed);
});

test("NEGATIVE: fails when trade leaves a team thin at RB", () => {
  const thinUser = [
    makePlayer(1, "QB1", "QB", 30, c(30)),
    makePlayer(2, "RB1", "RB", 25, c(25)),
    makePlayer(3, "RB2", "RB", 20, c(20)),
    makePlayer(4, "WR1", "WR", 24, c(24)),
    makePlayer(5, "WR2", "WR", 21, c(21)),
    makePlayer(6, "WR3", "WR", 18, c(18)),
    makePlayer(7, "TE1", "TE", 16, c(16)),
  ];
  const genTheir = [
    makePlayer(101, "T-QB1", "QB", 28, c(28)),
    makePlayer(102, "T-WR5", "WR", 22, c(22)),
    makePlayer(103, "T-WR6", "WR", 19, c(19)),
    makePlayer(104, "T-RB4", "RB", 15, c(15)),
    makePlayer(105, "T-RB5", "RB", 12, c(12)),
    makePlayer(106, "T-WR7", "WR", 10, c(10)),
    makePlayer(107, "T-TE2", "TE", 8, c(8)),
  ];
  const result = runViabilityChecks(
    thinUser, genTheir,
    [thinUser[1], thinUser[2]], // both RBs
    [genTheir[1], genTheir[2]], // two WRs
    SHAPE,
  );
  assert.ok(!findCheck(result, "depth").passed, "depth should fail when RBs are gone");
});

// ---------------------------------------------------------------------------
// Check 7: Roster space
// ---------------------------------------------------------------------------
console.log("\n--- Check 7: Roster space ---");

test("passes for equal-sized trade", () => {
  const result = runViabilityChecks(
    userRoster, theirRoster,
    [userRoster[7]], [theirRoster[7]],
    SHAPE,
  );
  assert.ok(findCheck(result, "roster_space").passed);
});

test("NEGATIVE: fails when taking more players with no dead weight", () => {
  // All roster players have value well above the cutoff. After getting 2 for 1,
  // the new arrivals also have high value, so there is no dead weight to drop.
  const stacked = Array.from({ length: 10 }, (_, i) =>
    makePlayer(i + 1, `Star${i}`, i < 1 ? "QB" : i < 3 ? "RB" : i < 6 ? "WR" : i < 7 ? "TE" : "RB", 20 + i, c(20 + i)),
  );
  // Two high-value players received (above cutoff=15)
  const highGet1 = makePlayer(9010, "HiGet1", "WR", 22, c(22));
  const highGet2 = makePlayer(9011, "HiGet2", "RB", 18, c(18));
  const expandedTheir = [...theirRoster, highGet1, highGet2];
  const result = runViabilityChecks(
    stacked, expandedTheir,
    [stacked[9]], // give 1
    [highGet1, highGet2], // get 2 high-value
    SHAPE,
    { ...DEFAULT_CONFIG, deadWeightCutoff: 15 },
  );
  assert.ok(!findCheck(result, "roster_space").passed,
    "should fail: no dead weight to drop, got: " + findCheck(result, "roster_space").detail);
});

// ---------------------------------------------------------------------------
// Check 8: Both teams keep a QB
// ---------------------------------------------------------------------------
console.log("\n--- Check 8: QB kept ---");

test("passes when both teams keep a QB", () => {
  const result = runViabilityChecks(
    userRoster, theirRoster,
    [userRoster[3]], [theirRoster[3]],
    SHAPE,
  );
  assert.ok(findCheck(result, "qb_kept").passed);
});

test("NEGATIVE: fails when a team would have no QB", () => {
  const result = runViabilityChecks(
    userRoster, theirRoster,
    [userRoster[0]], // only QB
    [theirRoster[3]], // not a QB
    SHAPE,
  );
  assert.ok(!findCheck(result, "qb_kept").passed, "should fail when user loses only QB");
});

// ---------------------------------------------------------------------------
// Check 9: User guardrails
// ---------------------------------------------------------------------------
console.log("\n--- Check 9: User guardrails ---");

test("passes when guardrails are satisfied", () => {
  const config = { ...DEFAULT_CONFIG, guardrails: [{ pos: "RB", neverWeaker: true }] };
  const result = runViabilityChecks(
    userRoster, theirRoster,
    [userRoster[7]], // bench WR
    [theirRoster[3]], // bench RB
    SHAPE,
    config,
  );
  assert.ok(findCheck(result, "user_guardrails").passed);
});

test("NEGATIVE: fails when guardrail position gets weaker", () => {
  const config = { ...DEFAULT_CONFIG, guardrails: [{ pos: "RB", neverWeaker: true }] };
  const result = runViabilityChecks(
    userRoster, theirRoster,
    [userRoster[1]], // U-RB1 (top starter)
    [theirRoster[7]], // bench WR
    SHAPE,
    config,
  );
  assert.ok(!findCheck(result, "user_guardrails").passed, "should fail when RB group weakens");
});

// ---------------------------------------------------------------------------
// Temporary gap flag
// ---------------------------------------------------------------------------
console.log("\n--- Temporary gap flag ---");

test("flags temporary gap when injured players leave team short", () => {
  const injuredRoster = [
    makePlayer(1, "QB1", "QB", 30, c(30)),
    makePlayer(2, "RB1", "RB", 25, c(25), { status: "injured", weeksOut: 3 }),
    makePlayer(3, "RB2", "RB", 20, c(20)),
    makePlayer(4, "RB3", "RB", 10, c(10)),
    makePlayer(5, "WR1", "WR", 24, c(24)),
    makePlayer(6, "WR2", "WR", 21, c(21)),
    makePlayer(7, "WR3", "WR", 18, c(18)),
    makePlayer(8, "WR4", "WR", 12, c(12)),
    makePlayer(9, "TE1", "TE", 16, c(16)),
  ];
  // Trade away RB2 (healthy) + RB3 (healthy) -> only 1 healthy RB (injured) for 2 slots + flex
  const result = runViabilityChecks(
    injuredRoster, theirRoster,
    [injuredRoster[2], injuredRoster[3]], // RB2, RB3 (healthy)
    [theirRoster[7], theirRoster[9]], // two bench players
    SHAPE,
  );
  assert.ok(result.temporaryGap, "should flag temporary gap");
});

// ---------------------------------------------------------------------------
// Deduplication
// ---------------------------------------------------------------------------
console.log("\n--- Deduplication ---");

test("deduplicates offers receiving the same players", () => {
  const offers = [
    { team: "A", userGives: [userRoster[7]], userGets: [theirRoster[3]], userRoster, theirRoster },
    { team: "B", userGives: [userRoster[9]], userGets: [theirRoster[3]], userRoster, theirRoster },
  ];
  const ranked = scoreAndRankOffers(offers, SHAPE);
  const receiveSets = ranked.map((o) => o.userGets.map((p) => p.player_key).sort().join(","));
  const unique = new Set(receiveSets);
  assert.equal(unique.size, receiveSets.length, "no duplicate receives");
});

// ---------------------------------------------------------------------------
// Ordering
// ---------------------------------------------------------------------------
console.log("\n--- Ordering ---");

test("viable offers come before non-viable", () => {
  const offers = [
    {
      team: "A",
      userGives: [userRoster[7]], // WR4 ddf=12
      userGets: [makePlayer(9001, "New-WR", "WR", 14, c(14))],
      userRoster,
      theirRoster: [...theirRoster, makePlayer(9001, "New-WR", "WR", 14, c(14))],
    },
    {
      team: "B",
      userGives: [userRoster[1]], // RB1 ddf=25
      userGets: [makePlayer(9002, "Bad-RB", "RB", 5, c(5))],
      userRoster,
      theirRoster: [...theirRoster, makePlayer(9002, "Bad-RB", "RB", 5, c(5))],
    },
  ];
  const ranked = scoreAndRankOffers(offers, SHAPE);
  const firstViable = ranked.findIndex((o) => o.viable);
  const firstNonViable = ranked.findIndex((o) => !o.viable);
  if (firstViable >= 0 && firstNonViable >= 0) {
    assert.ok(firstViable < firstNonViable, "viable before non-viable");
  }
});

// ---------------------------------------------------------------------------
// Package selection
// ---------------------------------------------------------------------------
console.log("\n--- Package selection ---");

test("package never sends the same player twice", () => {
  const roster2 = makeRoster("V", 6, 14);
  const offers = [
    {
      team: "A",
      userGives: [userRoster[7]],
      userGets: [makePlayer(9003, "A-Get", "WR", 14, c(14))],
      userRoster,
      theirRoster: [...theirRoster, makePlayer(9003, "A-Get", "WR", 14, c(14))],
    },
    {
      team: "B",
      userGives: [userRoster[7]], // same player!
      userGets: [makePlayer(9004, "B-Get", "WR", 15, c(15))],
      userRoster,
      theirRoster: [...roster2, makePlayer(9004, "B-Get", "WR", 15, c(15))],
    },
  ];
  const ranked = scoreAndRankOffers(offers, SHAPE);
  const pkg = selectPackage(ranked, userRoster, SHAPE);
  const sentKeys = pkg.offers.flatMap((o) => o.userGives.map((p) => p.player_key));
  const uniqueSent = new Set(sentKeys);
  assert.equal(sentKeys.length, uniqueSent.size, "never send the same player twice");
});

test("package uses each team at most once", () => {
  const offers = [
    {
      team: "A",
      userGives: [userRoster[7]],
      userGets: [makePlayer(9005, "A-Get1", "WR", 14, c(14))],
      userRoster,
      theirRoster: [...theirRoster, makePlayer(9005, "A-Get1", "WR", 14, c(14))],
    },
    {
      team: "A", // same team!
      userGives: [userRoster[9]],
      userGets: [makePlayer(9006, "A-Get2", "RB", 13, c(13))],
      userRoster,
      theirRoster: [...theirRoster, makePlayer(9006, "A-Get2", "RB", 13, c(13))],
    },
  ];
  const ranked = scoreAndRankOffers(offers, SHAPE);
  const pkg = selectPackage(ranked, userRoster, SHAPE);
  const teams = pkg.offers.map((o) => o.team);
  const uniqueTeams = new Set(teams);
  assert.equal(teams.length, uniqueTeams.size, "each team at most once");
});

// ---------------------------------------------------------------------------
// Labels
// ---------------------------------------------------------------------------
console.log("\n--- Labels ---");

test("viable offers get a label, non-viable get null", () => {
  const result = runViabilityChecks(
    userRoster, theirRoster,
    [userRoster[7]], [theirRoster[7]],
    SHAPE,
  );
  if (result.viable) {
    assert.ok(["High", "Med-High", "Medium"].includes(result.label), `got ${result.label}`);
  }

  const bad = runViabilityChecks(
    userRoster, theirRoster,
    [userRoster[1]], [theirRoster[9]],
    SHAPE,
  );
  if (!bad.viable) {
    assert.equal(bad.label, null, "non-viable should have null label");
  }
});

// ---------------------------------------------------------------------------
// All checks recorded
// ---------------------------------------------------------------------------
console.log("\n--- All checks recorded ---");

test("every offer records all 9 checks", () => {
  const result = runViabilityChecks(
    userRoster, theirRoster,
    [userRoster[3]], [theirRoster[3]],
    SHAPE,
  );
  const names = result.checks.map((ch) => ch.name);
  const expected = [
    "arbitrage", "perceived_fairness", "user_lineup_improves",
    "their_lineup_improves", "position_protection", "depth",
    "roster_space", "qb_kept", "user_guardrails",
  ];
  for (const e of expected) {
    assert.ok(names.includes(e), `check ${e} should be recorded`);
  }
  assert.equal(names.length, expected.length);
});

test("temporary gap is false when both rosters are healthy and complete", () => {
  const give = [userRoster.find((r) => r.name === "U-RB3")];
  const get = [theirRoster.find((r) => r.name === "T-RB3")];
  const r = runViabilityChecks(userRoster, theirRoster, give, get, SHAPE, DEFAULT_CONFIG);
  assert.equal(r.temporaryGap, false);
});

test("NEGATIVE: temporary gap is true when their only QB is out", () => {
  const hurt = theirRoster.map((p) => (p.pos === "QB" ? { ...p, status: "out" } : p));
  const give = [userRoster.find((r) => r.name === "U-RB3")];
  const get = [hurt.find((r) => r.name === "T-RB3")];
  const r = runViabilityChecks(userRoster, hurt, give, get, SHAPE, DEFAULT_CONFIG);
  assert.equal(r.temporaryGap, true);
});

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------
console.log(`\n${"=".repeat(40)}`);
console.log(`Results: ${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
console.log("All viability tests passed.");
