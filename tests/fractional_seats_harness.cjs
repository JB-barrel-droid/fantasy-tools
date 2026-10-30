// Harness for tests/test_fractional_seats.py: runs the JS twin
// (app/trade-value-chart/assets/fractional-seats.js) on cases from stdin.
//
//   node tests/fractional_seats_harness.cjs mix < {"cases": [...]}
//   node tests/fractional_seats_harness.cjs phi < {"z": [...]}
"use strict";

const path = require("path");
const FS = require(path.join(__dirname, "..", "app", "trade-value-chart", "assets", "fractional-seats.js"));

// Python's round(): halves go to the even neighbour.
function pyRound(x) {
  const f = Math.floor(x), d = x - f;
  if (d > 0.5) return f + 1;
  if (d < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}

// The bench usage discount of roster_convention.vorp_bench_allocate, with
// bye + miss rate per position passed in by the test.
function discountFor(rates) {
  return function (starters, teams) {
    const c = {}, t1 = {};
    Object.keys(rates).forEach(function (p) {
      c[p] = ((starters[p] || 0) / teams) * rates[p];
      t1[p] = Math.max(1, pyRound(2.0 * c[p] * teams));
    });
    return function (p, k) { return Math.pow(c[p], 1 + Math.floor(k / t1[p])); };
  };
}

function main() {
  const cmd = process.argv[2];
  const input = JSON.parse(require("fs").readFileSync(0, "utf8"));
  let out;
  if (cmd === "phi") {
    out = input.z.map(FS.phi);
  } else if (cmd === "mix") {
    out = input.cases.map(function (c) {
      return FS.allocationMix({
        teams: c.teams, dedicated: c.dedicated, superflex: c.superflex,
        flexEligible: c.flex_eligible, flexSeats: c.flex_seats, benchSeats: c.bench_seats,
        order: c.order, score: c.score, sigma: c.sigma, softBench: c.soft_bench,
        benchDiscount: discountFor(c.rates)
      });
    });
  } else if (cmd === "decompose") {
    out = input.fracs.map(function (f) { return FS.decompose(f); });
  } else {
    throw new Error("unknown command " + cmd);
  }
  process.stdout.write(JSON.stringify(out));
}

main();
