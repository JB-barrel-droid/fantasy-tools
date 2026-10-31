// Harness for tests/test_fractional_seats_engine.py: runs the engine's own
// copy of the seat functions (value-model.js, ValueModel.seatFunctions) on
// cases from stdin.
//
//   node tests/fractional_seats_engine_harness.cjs select < {"cases": [{items, n}]}
//   node tests/fractional_seats_engine_harness.cjs decompose < {"fracs": [...]}
//   node tests/fractional_seats_engine_harness.cjs mix < {"cases": [...]}
"use strict";

const path = require("path");
const VM = require(path.join(__dirname, "..", "app", "trade-value-chart", "assets", "value-model.js"));
const S = VM.seatFunctions;

function main() {
  const cmd = process.argv[2];
  const input = JSON.parse(require("fs").readFileSync(0, "utf8"));
  let out;
  if (cmd === "select") {
    out = input.cases.map(function (c) { return S.softSelect(c.items, c.n); });
  } else if (cmd === "decompose") {
    out = input.fracs.map(function (f) { return S.decompose(f); });
  } else if (cmd === "mix") {
    out = input.cases.map(function (c) {
      return S.seatMix({
        teams: c.teams, dedicated: c.dedicated, superflex: c.superflex,
        flexEligible: c.flex_eligible, flexSeats: c.flex_seats, benchSeats: c.bench_seats,
        order: c.order, score: c.score, sigma: c.sigma, softBench: c.soft_bench
      });
    });
  } else {
    throw new Error("unknown command " + cmd);
  }
  process.stdout.write(JSON.stringify(out));
}

main();
