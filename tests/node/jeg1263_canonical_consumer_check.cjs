// Read-only integration with an already-fetched canonical owner checkout. No fetch, search or policy implementation.
// node tests/node/jeg1263_canonical_consumer_check.cjs /path/to/PR1302-checkout
"use strict";
const assert = require("node:assert/strict"), fs = require("node:fs"), path = require("node:path");
const root = path.resolve(process.argv[2]);
const S = require("../../app/v2/simplified-site.js"), R = require(path.join(root, "app/v2/trade-readout.js"));
const witness = JSON.parse(fs.readFileSync(path.join(root, "tests/fixtures/jeg1483-starter-real-witness.json")));
const clone = x => JSON.parse(JSON.stringify(x)), outputs = [];
const options = {league: {name: "Historical contract witness", myTeam: "Witness us"},
  fixture: {kind: "historical", label: "Owner-pinned Week 8 values; explicit test team IDs, not a live league."}};
function check(input, name) {
  input = clone(input);
  input.mine.id = "witness-us"; input.theirs.id = input.partnerKind === "waivers" ? "witness-waivers" : "witness-them";
  const readout = R.build(input), record = readout.decision;
  const byKey = new Map(input.mine.rows.concat(input.theirs.rows).map(row => [String(row.player_key), row]));
  const row = {id: `${input.theirs.id}|${input.give}|${input.receive}`, opponentId: input.theirs.id,
    opponent: input.partnerKind === "waivers" ? "Waivers" : "Witness them", give: input.give.map(k => byKey.get(String(k))),
    receive: input.receive.map(k => byKey.get(String(k))), edge: 999999, record};
  const result = {status: "ready", rows: [row], evaluated: 1, total: 1, counts: {}, hasMore: false, bounded: false};
  const before = JSON.stringify({input, result});
  const context = S.canonicalContext(result, {...options, detailId: row.id, readoutFor: original => {
    assert.equal(original, row); return readout;
  }});
  const vm = S.viewModel(context, {detail: row.id});
  assert.equal(vm.state, "answer", JSON.stringify(vm.reasons));
  assert.equal(vm.detail.fitWord, record.label);
  assert.equal(vm.readout, readout);
  assert.deepEqual(vm.detail.questions.map(q => q.status), record.questions.map(q => q.status));
  assert.equal(vm.detail.gainText, record.questions[0].status === "known" ? require("../../app/v2/opportunities.js").fmt(record.questions[0].value) : "Unavailable");
  assert.equal(JSON.stringify({input, result}), before);
  outputs.push({case: name, label: record.label, headline: vm.detail.gainLine,
    questions: vm.detail.questions.map(q => ({id: q.id, value: q.value, status: q.status})), evidence: vm.detail.evidence});
}
for (const c of witness.cases) check(c.input, c.name);
const unknown = clone(witness.cases[0].input); unknown.chartKeys = ["usatoday", "fantasycalc"];
check(unknown, "one published source: canonical unknown judgment");
const pickup = clone(witness.cases[0].input); pickup.partnerKind = "waivers"; pickup.give = [];
check(pickup, "explicit virtual partner: add-only Pickup");
console.log(JSON.stringify({passed: true, cases: outputs.length, outputs}, null, 2));
