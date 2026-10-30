"""JEG-1231: opponent inclusion state and the league search adapter.

The checks live in tests/node/opponent_inclusion_check.cjs (pure Node, real workspace.js and opportunities.js, the frozen
4-team fixture). test_checks_fail_on_broken_builds breaks one rule at a time in a copy of the module and requires the
harness to name the check that catches it.
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
HARNESS = ROOT / "tests" / "node" / "opponent_inclusion_check.cjs"
MODULES = ["opponent-inclusion.js", "workspace.js", "roster-provenance-transitions.js", "opportunities.js", "finder.js"]

REQUIRED = [
    "test_baseline_every_opponent_included", "test_explicit_exclude_and_include", "test_duplicate_names_keyed_by_id",
    "test_rename_keeps_choice", "test_removal_and_import_collision", "test_no_opponents_and_all_excluded",
    "test_profile_exclusion_is_preserved", "test_view_selection_writes_nothing_else", "test_star_moves",
    "test_saved_with_the_workspace", "test_filters_and_selection_key", "test_search_excludes_offers_without_changing_values",
]

# (old, new, check that must catch it)
MUTATIONS = [
    ("const included = !viewExcluded && !profileExcluded;", "const included = !viewExcluded;", "test_profile_exclusion_is_preserved"),
    ("const clean = {v: VERSION, excluded: teamsOf(ws).map(idOf).filter(id => seen.has(id))};",
     "const clean = {v: VERSION, excluded: raw.excluded.map(String)};", "test_removal_and_import_collision"),
    ("const ids = new Set(describe(ws, rawState, opts).rows.filter(r => r.included).map(r => r.id));\n    return opponents(ws).filter(t => ids.has(idOf(t)));",
     "return opponents(ws);", "test_search_excludes_offers_without_changing_values"),
    ("label: duplicate ? `${name} · team ${position}` : name", "label: name", "test_duplicate_names_keyed_by_id"),
    ("const opponents = ws => teamsOf(ws).filter(t => idOf(t) !== String(ws && ws.myTeamId));", "const opponents = ws => teamsOf(ws);",
     "test_baseline_every_opponent_included"),
    ("return state.excluded.length ? emptyState() : state;", "return emptyState();", "test_no_opponents_and_all_excluded"),
    ("      const players = countOf(t);\n", "      const players = 0;\n", "test_baseline_every_opponent_included"),
]


def run_harness(modules_dir: Path) -> dict:
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    out = subprocess.run(["node", str(HARNESS), str(modules_dir)], capture_output=True, text=True, timeout=300)
    if out.returncode != 0:
        raise AssertionError(f"harness crashed: {out.stderr[-1500:]}")
    return json.loads(out.stdout)


class OpponentInclusionTest(unittest.TestCase):
    def test_checks_pass(self):
        result = run_harness(APP)
        self.assertEqual(result["failures"], [])
        missing = [name for name in REQUIRED if name not in result["ran"]]
        self.assertEqual(missing, [], "a required check did not run")

    def test_checks_fail_on_broken_builds(self):
        for old, new, check in MUTATIONS:
            with self.subTest(check=check, old=old[:60]):
                with tempfile.TemporaryDirectory() as tmp:
                    for name in MODULES:
                        shutil.copy2(APP / name, Path(tmp) / name)
                    path = Path(tmp) / "opponent-inclusion.js"
                    text = path.read_text(encoding="utf-8")
                    self.assertIn(old, text, "mutation anchor is stale")
                    path.write_text(text.replace(old, new, 1), encoding="utf-8")
                    result = run_harness(Path(tmp))
                    self.assertIn(check, [f["name"] for f in result["failures"]], f"{check} did not catch the broken build")


if __name__ == "__main__":
    unittest.main()
