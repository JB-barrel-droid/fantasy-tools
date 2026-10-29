"""JEG-1272: prove the roster-paste contracts catch real broken parsers.

tests/test_v2_roster_paste.js only re-checks the real parser in its
"discrimination" section. This harness copies app/v2/roster-paste.js into a
temp dir, applies each mutation in tests/fixtures/roster-paste-mutations/
manifest.json to its own copy, and runs every contract against the baseline
and each mutant in a separate Node process (no network).

A mutant counts as caught only when its named contract fails with an
AssertionError. A mutation whose find text does not apply, a mutant that
fails to load, or a contract that throws anything else fails the harness
instead of counting as detection. The real parser and the scrubbed samples in
tests/fixtures/roster_paste/ are read, never written.

Run: python3 -m unittest tests.test_roster_paste_mutation_proof
"""
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "app" / "v2" / "roster-paste.js"
SAMPLES = ROOT / "tests" / "fixtures" / "roster_paste"
MANIFEST = ROOT / "tests" / "fixtures" / "roster-paste-mutations" / "manifest.json"
SAMPLE_NAMES = ["espn-team.txt"]

# The Node driver: loads the parser at argv[2], reads samples from argv[3],
# runs every contract and prints one JSON line. Load failures are reported as
# load:error, never as a contract result.
DRIVER = r"""
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const out = {load: "ok", loadError: null, contracts: {}};
let P;
try {
  P = require(path.resolve(process.argv[2]));
  if (!P || typeof P.parse !== "function") throw new Error("module has no parse()");
} catch (e) {
  out.load = "error";
  out.loadError = String(e && e.stack || e);
  process.stdout.write(JSON.stringify(out) + "\n");
  process.exit(0);
}
const SAMPLES = process.argv[3];
const sample = (name) => fs.readFileSync(path.join(SAMPLES, name), "utf8");

// The roster rows in the scrubbed ESPN team sample, plus the trap player.
const ESPN_TEAM = [
  {player_key: "love_jo", name: "Jordan Love", pos: "QB", team: "GB"},
  {player_key: "b_robinson", name: "Bijan Robinson", pos: "RB", team: "ATL"},
  {player_key: "a_jones", name: "Aaron Jones Sr.", pos: "RB", team: "MIN"},
  {player_key: "higgins", name: "Tee Higgins", pos: "WR", team: "CIN"},
  {player_key: "london", name: "Drake London", pos: "WR", team: "ATL"},
  {player_key: "kraft", name: "Tucker Kraft", pos: "TE", team: "GB"},
  {player_key: "b_allen", name: "Braelon Allen", pos: "RB", team: "NYJ"},
  {player_key: "broncos", name: "Broncos", pos: "DEF", team: "DEN"},
  {player_key: "boswell", name: "Chris Boswell", pos: "K", team: "PIT"},
  {player_key: "burden", name: "Luther Burden III", pos: "WR", team: "CHI"},
  {player_key: "hall", name: "Breece Hall", pos: "RB", team: "NYJ"},
  {player_key: "jackson", name: "Lamar Jackson", pos: "QB", team: "BAL"},
  {player_key: "j_williams", name: "Jameson Williams", pos: "WR", team: "DET"},
  {player_key: "perine", name: "Samaje Perine", pos: "RB", team: "CIN"},
  {player_key: "charbonnet", name: "Zach Charbonnet", pos: "RB", team: "SEA"},
  {player_key: "beckham", name: "Odell Beckham Jr.", pos: "WR", team: "MIA"},
  {player_key: "noel", name: "Jaylin Noel", pos: "WR", team: "HOU"},
];
const TWO_ALLENS = [
  {player_key: "allen_j", name: "Josh Allen", pos: "QB", team: "BUF"},
  {player_key: "allen_b", name: "Josh Allen", pos: "DE", team: "JAC"},
];
const ESPN_ROWS = 15;

// Insert text just before the TOTALS line that closes the bench table.
function beforeBenchTotals(text, insert) {
  const lines = text.split("\n");
  const perine = lines.indexOf("Samaje Perine");
  assert.ok(perine > 0, "sample: Samaje Perine row present");
  const totals = lines.indexOf("TOTALS", perine);
  assert.ok(totals > perine, "sample: TOTALS after the bench rows");
  return lines.slice(0, totals).concat(insert.split("\n"), lines.slice(totals)).join("\n");
}
function perineRow(text) {
  const lines = text.split("\n");
  const start = lines.indexOf("Samaje PerineSamaje Perine") - 1;
  const end = lines.indexOf("TOTALS", start);
  assert.strictEqual(lines[start], "Bench", "sample: Perine row starts at its Bench slot");
  return lines.slice(start, end).join("\n");
}
function idsOf(result) { return result.players.map((p) => p.id); }

const CONTRACTS = {
  structural_team_pos: [
    ["slot + exact name with no team/position line does not match", () => {
      // Slot label and the player's exact (doubled) name, but no team or position line.
      const trap = "Bench\nOdell Beckham Jr.Odell Beckham Jr.\nOdell Beckham Jr.\n\nMOVE\n--";
      const r = P.parse(beforeBenchTotals(sample("espn-team.txt"), trap), ESPN_TEAM);
      assert.strictEqual(r.site, "espn");
      assert.strictEqual(r.mode, "team");
      assert.strictEqual(idsOf(r).indexOf("beckham"), -1, "trap row without team/position must not match");
      assert.strictEqual(r.matched, ESPN_ROWS, "still exactly the 15 real rows");
    }],
  ],
  duplicate_suppression: [
    ["matchCandidate refuses a second match as duplicate", () => {
      const index = P.buildIndex(ESPN_TEAM);
      const seen = {};
      const cand = {name: "Chris Boswell", posHint: "K", teamHint: "PIT", isDST: false};
      assert.ok(P.matchCandidate(cand, index, seen).match, "first match taken");
      const again = P.matchCandidate(cand, index, seen);
      assert.strictEqual(again.match, null, "second match refused");
      assert.strictEqual(again.reason, "duplicate");
    }],
    ["repeated ESPN roster row is counted once", () => {
      const base = sample("espn-team.txt");
      const r = P.parse(beforeBenchTotals(base, perineRow(base)), ESPN_TEAM);
      const ids = idsOf(r);
      assert.strictEqual(ids.filter((id) => id === "perine").length, 1, "repeated roster row counted once");
      assert.strictEqual(new Set(ids).size, ids.length, "no player listed twice");
      assert.strictEqual(r.matched, ESPN_ROWS);
    }],
    ["a name on two plain-list lines gives one player", () => {
      const r = P.parse("Jaylin Noel WR HOU\nJaylin Noel WR HOU", ESPN_TEAM);
      assert.strictEqual(r.mode, "extract");
      assert.deepStrictEqual(idsOf(r), ["noel"], "a name on two list lines gives one player");
    }],
  ],
  ambiguous_refusal: [
    ["matchCandidate refuses a shared name with no evidence", () => {
      const r = P.matchCandidate({name: "Josh Allen", posHint: null, teamHint: null, isDST: false}, P.buildIndex(TWO_ALLENS), {});
      assert.strictEqual(r.match, null, "matchCandidate refuses an ambiguous name");
    }],
    ["disambiguate refuses two hits with no evidence", () => {
      const hits = P.buildIndex(TWO_ALLENS).byName["josh allen"];
      assert.strictEqual(hits.length, 2);
      assert.strictEqual(P.disambiguate(hits, null, null), null, "disambiguate refuses without evidence");
    }],
    ["plain-list paste of a shared name matches nobody and says ambiguous", () => {
      const r = P.parse("Josh Allen", TWO_ALLENS);
      assert.strictEqual(r.mode, "extract");
      assert.strictEqual(r.matched, 0, "plain-list paste of an ambiguous name matches nobody");
      assert.ok(r.unmatched.some((u) => /^ambiguous/.test(u.reason)), "the line is reported as ambiguous");
    }],
  ],
};

// Every check runs even after an earlier one fails, so the report shows which
// parts of a contract a mutant breaks. A contract fails if any check fails and
// errors if any check throws something other than an AssertionError.
for (const id of Object.keys(CONTRACTS)) {
  const checks = {};
  let status = "pass";
  for (const [name, fn] of CONTRACTS[id]) {
    try {
      fn();
      checks[name] = "pass";
    } catch (e) {
      if (e instanceof assert.AssertionError) {
        checks[name] = "fail: " + e.message.split("\n")[0];
        if (status === "pass") status = "fail";
      } else {
        checks[name] = "error: " + String(e && e.stack || e);
        status = "error";
      }
    }
  }
  out.contracts[id] = {status: status, checks: checks};
}
process.stdout.write(JSON.stringify(out) + "\n");
"""


class MutationNotApplied(AssertionError):
    """A manifest edit's find text did not appear the expected number of times."""


class NotDetected(AssertionError):
    """A mutant was not caught by its named contract (or the run proved nothing)."""


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def apply_mutation(source, mutation):
    """Return source with every edit applied. Raise MutationNotApplied if any edit misses."""
    out = source
    for n, edit in enumerate(mutation["edits"]):
        found = out.count(edit["find"])
        if found != edit["count"]:
            raise MutationNotApplied(
                "%s edit %d: find text appears %d times, expected %d"
                % (mutation["id"], n, found, edit["count"]))
        out = out.replace(edit["find"], edit["replace"])
    if out == source:
        raise MutationNotApplied("%s: edits left the source unchanged" % mutation["id"])
    return out


def run_driver(workdir, module_path):
    """Run the Node driver on one parser copy and return its parsed JSON."""
    node = shutil.which("node")
    if node is None:
        raise AssertionError("node is required for this harness (no skips)")
    proc = subprocess.run(
        [node, str(workdir / "driver.cjs"), str(module_path), str(workdir / "samples")],
        cwd=str(workdir), capture_output=True, text=True, timeout=120,
        env={"PATH": str(Path(node).parent), "NODE_OPTIONS": ""})
    if proc.returncode != 0:
        raise AssertionError("driver exited %d: %s" % (proc.returncode, proc.stderr[-2000:]))
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    return json.loads(lines[-1])


def assert_detected(result, mutation, contract_ids):
    """The mutant loaded, and its named contract failed with an AssertionError."""
    if result["load"] != "ok":
        raise NotDetected("%s: mutant failed to load, which is not detection: %s"
                          % (mutation["id"], result["loadError"]))
    target = mutation["contract"]
    if target not in contract_ids:
        raise NotDetected("%s: names unknown contract %r" % (mutation["id"], target))
    got = result["contracts"].get(target)
    if got is None or got["status"] != "fail":
        raise NotDetected("%s: contract %s was %r, expected an assertion failure"
                          % (mutation["id"], target, got))


class Workspace:
    """Isolated temp dir holding the driver, the samples and each parser copy."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jeg1272-")
        self.dir = Path(self.tmp.name)
        (self.dir / "driver.cjs").write_text(DRIVER, encoding="utf-8")
        (self.dir / "samples").mkdir()
        for name in SAMPLE_NAMES:
            shutil.copyfile(SAMPLES / name, self.dir / "samples" / name)

    def run(self, label, source):
        mod_dir = self.dir / label
        mod_dir.mkdir()
        module = mod_dir / "roster-paste.js"
        module.write_text(source, encoding="utf-8")
        return run_driver(self.dir, module)

    def close(self):
        self.tmp.cleanup()


class RosterPasteMutationProof(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_manifest()
        cls.source = TARGET.read_text(encoding="utf-8")
        cls.before = {p: sha256(p) for p in [TARGET, MANIFEST] + [SAMPLES / n for n in SAMPLE_NAMES]}
        cls.ws = Workspace()
        cls.baseline = cls.ws.run("baseline", cls.source)
        cls.results = {}
        for m in cls.manifest["mutations"]:
            try:
                mutated = apply_mutation(cls.source, m)
            except MutationNotApplied as e:
                cls.results[m["id"]] = e
                continue
            cls.results[m["id"]] = cls.ws.run(m["id"], mutated)

    @classmethod
    def tearDownClass(cls):
        cls.ws.close()

    def contract_ids(self):
        return set(self.manifest["contracts"])

    def test_manifest_covers_the_three_required_mutations(self):
        self.assertEqual(self.manifest["target"], "app/v2/roster-paste.js")
        self.assertEqual(self.contract_ids(), {"structural_team_pos", "duplicate_suppression", "ambiguous_refusal"})
        named = sorted(m["contract"] for m in self.manifest["mutations"])
        self.assertEqual(named, sorted(self.contract_ids()), "one mutation per contract")
        ids = [m["id"] for m in self.manifest["mutations"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_driver_runs_exactly_the_manifest_contracts(self):
        self.assertEqual(self.baseline["load"], "ok", self.baseline.get("loadError"))
        self.assertEqual(set(self.baseline["contracts"]), self.contract_ids())

    def test_baseline_passes_every_contract(self):
        for cid, got in self.baseline["contracts"].items():
            self.assertEqual(got["status"], "pass", "%s on the real parser: %s" % (cid, got))

    def test_each_mutation_applies(self):
        for m in self.manifest["mutations"]:
            with self.subTest(mutation=m["id"]):
                res = self.results[m["id"]]
                if isinstance(res, Exception):
                    self.fail(str(res))

    def test_each_mutant_fails_its_named_contract(self):
        for m in self.manifest["mutations"]:
            with self.subTest(mutation=m["id"]):
                res = self.results[m["id"]]
                if isinstance(res, Exception):
                    self.fail("not applied, so not proven: %s" % res)
                assert_detected(res, m, self.contract_ids())

    def test_mutants_raise_no_unexpected_errors(self):
        # A crash anywhere in a mutant run means the mutation broke more than its contract.
        for m in self.manifest["mutations"]:
            res = self.results[m["id"]]
            if isinstance(res, Exception):
                continue
            for cid, got in res["contracts"].items():
                with self.subTest(mutation=m["id"], contract=cid):
                    self.assertNotEqual(got["status"], "error", got["checks"])

    def test_every_check_of_the_named_contract_catches_its_mutant(self):
        # Each check is itself proven: none passes on the mutant it guards against.
        for m in self.manifest["mutations"]:
            res = self.results[m["id"]]
            if isinstance(res, Exception):
                self.fail("not applied, so not proven: %s" % res)
            for check, outcome in res["contracts"][m["contract"]]["checks"].items():
                with self.subTest(mutation=m["id"], check=check):
                    self.assertTrue(outcome.startswith("fail: "), outcome)

    def test_mutants_leave_the_other_contracts_passing(self):
        # Each mutation breaks only what it names, so a catch is not a side effect.
        for m in self.manifest["mutations"]:
            res = self.results[m["id"]]
            if isinstance(res, Exception):
                self.fail("not applied, so not proven: %s" % res)
            for cid, got in res["contracts"].items():
                if cid != m["contract"]:
                    with self.subTest(mutation=m["id"], contract=cid):
                        self.assertEqual(got["status"], "pass", got["checks"])

    def test_real_files_untouched(self):
        for path, digest in self.before.items():
            self.assertEqual(sha256(path), digest, "%s changed during the run" % path)

    # ---- the harness refuses to count things that prove nothing ----

    def test_unapplied_mutation_fails_the_harness(self):
        missing = {"id": "missing", "edits": [{"find": "no such text in the parser", "replace": "x", "count": 1}]}
        with self.assertRaises(MutationNotApplied):
            apply_mutation(self.source, missing)
        real = self.manifest["mutations"][0]["edits"][0]
        wrong_count = {"id": "wrong_count", "edits": [dict(real, count=2)]}
        with self.assertRaises(MutationNotApplied):
            apply_mutation(self.source, wrong_count)
        no_op = {"id": "no_op", "edits": [{"find": real["find"], "replace": real["find"], "count": 1}]}
        with self.assertRaises(MutationNotApplied):
            apply_mutation(self.source, no_op)

    def test_startup_error_is_not_detection(self):
        broken = self.source.replace("function parse(text, playerIndex) {", "function parse(text, playerIndex) {{", 1)
        self.assertNotEqual(broken, self.source)
        res = self.ws.run("syntax_error", broken)
        self.assertEqual(res["load"], "error")
        with self.assertRaises(NotDetected):
            assert_detected(res, {"id": "syntax_error", "contract": "structural_team_pos"}, self.contract_ids())

    def test_runtime_error_is_not_detection(self):
        # parse() throws a TypeError: the contract reports "error", which is not a caught mutant.
        throws = self.source.replace("function parse(text, playerIndex) {",
                                     "function parse(text, playerIndex) { null.x;", 1)
        res = self.ws.run("runtime_error", throws)
        self.assertEqual(res["load"], "ok")
        self.assertEqual(res["contracts"]["structural_team_pos"]["status"], "error")
        with self.assertRaises(NotDetected):
            assert_detected(res, {"id": "runtime_error", "contract": "structural_team_pos"}, self.contract_ids())

    def test_baseline_itself_is_not_detected(self):
        with self.assertRaises(NotDetected):
            assert_detected(self.baseline, {"id": "baseline", "contract": "duplicate_suppression"}, self.contract_ids())


if __name__ == "__main__":
    unittest.main()
