"""JEG-1241: roster provenance transitions (app/v2/roster-provenance-transitions.js), node, no network.

The node runner checks every row of tests/fixtures/roster_provenance/transitions.json against the module with frozen
inputs, then reintroduces each demonstrated defect as a one-line source mutation and requires a row to catch it.
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "tests/fixtures/roster_provenance/transitions.json"
OPS = {"replaceFromSource", "appendFromSource", "reconcile", "localEdit", "clear"}
FIELDS = ["unresolved", "observedAt", "editedAt", "coverage", "settled"]
COVERAGE = {"unknown", "bench_omitted", "bench_shown", "whole_roster"}
REASONS = {"unresolved_unknown", "unresolved", "not_source_observed", "coverage_unproven"}


class RosterProvenanceTransitionsTests(unittest.TestCase):
    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_table_and_mutants(self):
        out = subprocess.run(
            ["node", str(ROOT / "tests/node/roster_provenance_transitions.cjs")],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.strip().endswith("ok"), out.stdout)
        self.assertNotIn("mutants not caught", out.stdout + out.stderr)

    def test_table_is_well_formed(self):
        # A malformed row would be skipped or misread by the runner; catch it here, independent of node.
        table = json.loads(TABLE.read_text())
        ids = [r["id"] for k in ("transitions", "coverage", "blockers") for r in table[k]]
        self.assertEqual(len(ids), len(set(ids)), "row ids are unique")
        for row in table["transitions"]:
            self.assertTrue(row["why"], row["id"])
            self.assertEqual(list(row["expect"]), FIELDS, row["id"])
            self.assertIn(row["expect"]["coverage"], COVERAGE, row["id"])
            for step in row["steps"]:
                self.assertIn(step["op"], OPS, row["id"])
            if row.get("same"):
                self.assertTrue(row["steps"], f"{row['id']}: a no-op row needs a step")
        for row in table["coverage"]:
            self.assertIn(row["expect"], COVERAGE, row["id"])
        for row in table["blockers"]:
            self.assertTrue(row["why"], row["id"])
            added = [r for r in row["expect"] if r not in row["existingReasons"]]
            self.assertTrue(set(added) <= REASONS, row["id"])

    def test_acceptance_cases_are_covered(self):
        # The ticket's acceptance list, by row: removing one of these rows fails here.
        table = json.loads(TABLE.read_text())
        ids = {r["id"] for k in ("transitions", "coverage", "blockers") for r in table[k]}
        required = {
            "T01": "unknown count after append", "T02": "unknown count after duplicate paste",
            "T03": "no-op paste keeps times", "T06": "replace is an observation", "T07": "replace without count stays unknown",
            "T09": "rejected reconciliation", "T10": "successful reconciliation once", "T14": "edit time is not observation time",
            "T15": "stored rosterAt is edit time", "B01": "whole roster with an empty bench",
            "B02": "starters-only input passing count checks", "B07": "duplicate owner", "B08": "stale by existing contract",
        }
        self.assertEqual(sorted(set(required) - ids), [])

    def test_module_is_pure(self):
        # No DOM, storage, network or clock: callers pass `now`.
        src = (ROOT / "app/v2/roster-provenance-transitions.js").read_text()
        code = "\n".join(line.split("//")[0] for line in src.splitlines())
        for word in ("document", "window", "localStorage", "fetch(", "Date.now", "new Date", "setTimeout"):
            self.assertFalse(word in code, f"{word} in the module's code")


if __name__ == "__main__":
    unittest.main()
