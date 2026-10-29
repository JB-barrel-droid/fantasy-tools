"""JEG-1232: saved column order for the league tables (app/v2/column-order.js), pure model.

The checks live in tests/node/column_order_check.cjs (pure Node). Each guard is proven: test_checks_fail_on_broken_builds copies
the modules, breaks one rule at a time and requires the named check to fail.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "v2"
CHECK = ROOT / "tests" / "node" / "column_order_check.cjs"
MODULES = ["column-order.js", "workspace.js", "opportunities.js", "team-summary.js", "table-sort.js", "finder.js"]

REQUIRED = [
    "test_untouched_keeps_baseline", "test_catalog_matches_table_columns", "test_move_save_reload", "test_boundaries_announce",
    "test_corrupt_and_legacy_saved_state", "test_required_columns_return_in_place", "test_catalog_change_new_column",
    "test_hidden_and_shown_columns", "test_reset_to_default", "test_no_mutation_of_inputs",
]

# name -> (old, new, the checks that must fail), all in column-order.js
MUTATIONS = {
    "duplicates kept": ("if (seen.has(id)) { issues.push(`duplicate:${id}`); return; }", "", {"test_corrupt_and_legacy_saved_state"}),
    "unknown ids kept": ("if (!knownSet.has(id)) { issues.push(`unknown:${id}`); return; }", "", {"test_corrupt_and_legacy_saved_state"}),
    "missing columns appended, not placed by neighbour": ("if (out.includes(id)) return;\n", "if (out.includes(id)) return;\n      out.push(id); return;\n",
        {"test_required_columns_return_in_place", "test_catalog_change_new_column", "test_corrupt_and_legacy_saved_state"}),
    "hidden columns forgotten": ("return {order: full.filter(id => shown.has(id)), full, explicit: true, issues: clean.issues};",
        "return {order: full.filter(id => shown.has(id)), full: full.filter(id => shown.has(id)), explicit: true, issues: clean.issues};", {"test_hidden_and_shown_columns"}),
    "reset keeps the saved order": ("if (value === null) delete next[table];", "if (value === null) return {columnOrder: next};", {"test_reset_to_default"}),
    "an untouched league gets a stored order": ("if (!clean.ids) return {order: baseline, full: null, explicit: false, issues: clean.issues};",
        "if (!clean.ids) return {order: baseline, full: baseline, explicit: true, issues: clean.issues};", {"test_untouched_keeps_baseline", "test_corrupt_and_legacy_saved_state"}),
    "Market perception split from Charts fair": ('sub: id === "market" ? ["market", "fair"] : null', "sub: null", {"test_catalog_matches_table_columns"}),
}


def run_check(modules_dir: Path) -> dict:
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    out = subprocess.run(["node", str(CHECK), str(modules_dir)], capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise AssertionError(f"check crashed: {out.stderr[-1500:]}")
    return json.loads(out.stdout)


class ColumnOrderModelTest(unittest.TestCase):
    def test_checks_pass(self):
        result = run_check(APP)
        self.assertEqual(result["failures"], [])
        self.assertEqual(sorted(set(REQUIRED) - set(result["ran"])), [], "every required check ran")

    def test_checks_fail_on_broken_builds(self):
        for name, (old, new, expect) in MUTATIONS.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                for module in MODULES:
                    shutil.copy2(APP / module, Path(tmp) / module)
                path = Path(tmp) / "column-order.js"
                text = path.read_text(encoding="utf-8")
                self.assertIn(old, text, f"mutation anchor is stale: {old[:70]!r}")
                path.write_text(text.replace(old, new, 1), encoding="utf-8")
                failed = {f["name"] for f in run_check(Path(tmp))["failures"]}
                self.assertTrue(expect <= failed, f"{name}: expected {sorted(expect)} to fail, got {sorted(failed)}")


if __name__ == "__main__":
    unittest.main()
