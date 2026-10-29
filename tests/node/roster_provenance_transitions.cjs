// JEG-1241: roster provenance transitions. Run by tests/test_roster_provenance_transitions.py.
// 1. The module passes every row of tests/fixtures/roster_provenance/transitions.json, with frozen inputs (the module
//    runs in strict mode, so any write to an input throws) and frozen, unchanged-input results.
// 2. Each mutant below (one source edit that reintroduces a demonstrated defect) fails at least one row.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.resolve(__dirname, "../..");
const MODULE = path.join(ROOT, "app/v2/roster-provenance-transitions.js");
const TABLE = JSON.parse(fs.readFileSync(path.join(ROOT, "tests/fixtures/roster_provenance/transitions.json"), "utf8"));
const SOURCE = fs.readFileSync(MODULE, "utf8");

function load(source) {
  const sandbox = {module: {exports: {}}};
  vm.runInNewContext(source, sandbox, {filename: MODULE});
  return sandbox.module.exports;
}

function deepFreeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.values(value).forEach(deepFreeze);
    Object.freeze(value);
  }
  return value;
}
const copy = value => JSON.parse(JSON.stringify(value === undefined ? null : value));
const plain = record => JSON.parse(JSON.stringify(record));

// Every row as a list of named checks; a check throws when the module disagrees with the table.
function checks(P) {
  const out = [];
  TABLE.transitions.forEach(row => out.push([row.id, () => {
    const start = deepFreeze(copy(row.start));
    const before = JSON.stringify(start);
    let current = start;
    let last = current;
    row.steps.forEach(step => {
      last = current;
      const args = deepFreeze(copy(step.args));
      current = P[step.op](current, args);
    });
    assert.equal(JSON.stringify(start), before, "start record unchanged");
    if (row.same) assert.equal(current, last, "the last step returns its input record (no-op)");
    const result = P.normalize(current);
    assert.deepEqual(plain(result), row.expect);
    if (row.steps.length && !row.same) {
      assert.ok(Object.isFrozen(current) && Object.isFrozen(current.settled), "results are frozen");
    }
    if ("freshness" in row) assert.equal(P.freshnessTime(current), row.freshness, "freshness reads the observation");
  }]));
  TABLE.coverage.forEach(row => out.push([row.id, () => {
    assert.equal(P.coverageFrom(deepFreeze(copy(row.evidence))), row.expect);
  }]));
  TABLE.blockers.forEach(row => out.push([row.id, () => {
    const input = deepFreeze({teams: copy(row.teams), existingReasons: copy(row.existingReasons)});
    assert.deepEqual(plain(P.inferenceBlockers(input)), row.expect);
    // Coverage is evidence about the source, not occupancy: dropping or emptying the players changes nothing.
    const bare = deepFreeze({teams: row.teams.map(t => ({id: t.id, provenance: copy(t.provenance)})), existingReasons: copy(row.existingReasons)});
    assert.deepEqual(plain(P.inferenceBlockers(bare)), row.expect, "occupancy does not change the verdict");
  }]));
  return out;
}

function failures(P) {
  return checks(P).map(([id, run]) => { try { run(); return null; } catch (error) { return `${id}: ${error.message.split("\n")[0]}`; } }).filter(Boolean);
}

// Positive: the module as written passes every row.
const real = load(SOURCE);
const realFailures = failures(real);
assert.deepEqual(realFailures, [], realFailures.join("\n"));
assert.deepEqual(plain(Object.keys(real.COVERAGE).map(k => real.COVERAGE[k]).sort()), ["bench_omitted", "bench_shown", "unknown", "whole_roster"]);

// Negative: each mutant reintroduces one defect and must fail a row. `find` must occur exactly once in the source,
// so a refactor that removes a mutation point fails here instead of leaving a mutant that tests nothing.
const MUTANTS = [
  ["append turns an unknown count into a known one", "cur.unresolved === null ? null : cur.unresolved + left", "(cur.unresolved || 0) + left"],
  ["append counts as a source observation", "make(unresolved, cur.observedAt, time(a.now) || cur.editedAt, cur.coverage, cur.settled);", "make(unresolved, time(a.now), time(a.now), cur.coverage, cur.settled);"],
  ["a no-op paste still records an edit", "if (!added && !left) return p;", ""],
  ["append forgets players already on another team", "nonNegative(a.missed) + nonNegative(a.rejected)", "nonNegative(a.missed)"],
  ["a rejected reconciliation decrements", "a.accepted !== true || ", ""],
  ["a repeated reconciliation decrements again", " || cur.settled.indexOf(key) !== -1", ""],
  ["reconciling on an unknown count makes it zero", "cur.unresolved === null ? null : Math.max(0, cur.unresolved - 1)", "Math.max(0, (cur.unresolved || 0) - 1)"],
  ["a local edit counts as a source observation", "make(cur.unresolved, cur.observedAt, now, cur.coverage, cur.settled)", "make(cur.unresolved, now, now, cur.coverage, cur.settled)"],
  ["a stored rosterAt is read as an observation", "time(r.observedAt), time(r.editedAt)", "time(r.observedAt) || time(r.rosterAt), time(r.editedAt)"],
  ["a replacing paste with no count reads as all matched", "make(count(a.unresolved), now, now", "make(count(a.unresolved) || 0, now, now"],
  ["a replacing paste keeps the old settled items", "coverageOf(a.coverage), []);", "coverageOf(a.coverage), normalize(p).settled);"],
  ["clearing keeps the old observation", "make(0, null,", "make(0, cur.observedAt,"],
  ["freshness reads edit time", "return normalize(p).observedAt;", "return normalize(p).editedAt;"],
  ["an omitted bench can still read as a whole roster", "if (e.benchIncluded === false) return COVERAGE.BENCH_OMITTED;", ""],
  ["coverage is not checked (counts alone pass)", "if (cur.coverage !== COVERAGE.WHOLE_ROSTER) found.coverage_unproven = true;", ""],
  ["an unknown count does not block", "if (cur.unresolved === null) found.unresolved_unknown = true;\n      else ", ""],
  ["a source never observed does not block", "if (cur.observedAt === null) found.not_source_observed = true;", ""],
  ["the existing check's reasons are dropped", "(i.existingReasons || []).forEach", "[].forEach"],
  ["no teams reads as a whole league", "if (!teams.length) found.not_source_observed = true;", ""],
  ["a transition writes to its input record", "if (!added && !left) return p;", "if (!added && !left) return p; if (p) p.editedAt = time(a.now);"],
  ["results are not frozen", "return Object.freeze({unresolved", "return ({unresolved"],
];
const survivors = [];
MUTANTS.forEach(([name, find, replace]) => {
  const at = SOURCE.split(find).length - 1;
  assert.equal(at, 1, `mutation point for "${name}" must occur once (found ${at})`);
  const caught = failures(load(SOURCE.replace(find, replace)));
  if (!caught.length) survivors.push(name);
  else console.log(`mutant killed: ${name} (by ${caught[0]})`);
});
assert.deepEqual(survivors, [], `mutants not caught: ${survivors.join("; ")}`);

console.log(`${checks(real).length} rows pass; ${MUTANTS.length} mutants killed`);
console.log("ok");
