"""Simplified site section (JEG-1263): route contract, states, withholding, parity with the dashboard and the live adapter.

The checks live in tests/simplified_site_harness.cjs (pure Node, no browser). Every guard is proven:
test_checks_fail_on_broken_builds copies the modules, breaks one rule at a time, and requires the harness to name the
check that catches it.
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
HARNESS = ROOT / "tests" / "simplified_site_harness.cjs"
MODULES = ["simplified-site.js", "opportunities.js", "finder.js", "league.js"]

REQUIRED = [
    "test_name_and_route_are_exact", "test_route_contract", "test_answer_leads_with_the_top_idea", "test_order_is_the_given_ranking",
    "test_values_match_dashboard", "test_context_not_mutated", "test_loading_and_error", "test_empty_without_league_or_team",
    "test_incomplete_withholds", "test_weekly_never_blended", "test_no_qualifying_result", "test_detail_view",
    "test_fixture_labelled", "test_live_adapter_withholds_until_gates", "test_live_adapter_no_league",
]

# (what is broken, old text, new text, the check that must catch it)
MUTATIONS = [
    ("weekly basis accepted", 'else if (horizon !== HORIZON)', 'else if (false)', "test_weekly_never_blended"),
    ("weekly idea accepted", '(!rec.horizon || rec.horizon === HORIZON)', 'true', "test_weekly_never_blended"),
    ("ideas re-ranked", 'const recs = c.ideas.recommendations || [];',
     'const recs = (c.ideas.recommendations || []).slice().sort((a, b) => a.share - b.share);', "test_order_is_the_given_ranking"),
    ("own number format", 'const gainText = O.fmt(rec.ourGain);', 'const gainText = "+" + rec.ourGain.toFixed(2);', "test_values_match_dashboard"),
    ("context mutated", 'vm.stretch = stretch.map(', 'vm.stretch = stretch.reverse().map(', "test_context_not_mutated"),
    ("gates ignored", 'gates[key] !== true', 'false', "test_live_adapter_withholds_until_gates"),
    ("no team still answers", 'if (!c.league || !c.league.myTeam) {', 'if (!c.league) {', "test_empty_without_league_or_team"),
    ("bad idea dropped silently", 'if (bad) out.push(', 'if (false) out.push(', "test_incomplete_withholds"),
    ("missing list ignored", 'const out = (ctx.missing || []).map(', 'const out = [].map(', "test_incomplete_withholds"),
    ("fixture label dropped", 'fixture: c.fixture ? {kind: c.fixture.kind, label: c.fixture.label} : null', 'fixture: null', "test_fixture_labelled"),
    ("stretch mixed into the list", 'vm.more = all.slice(1);', 'vm.more = all.slice(1).concat(vm.stretch);', "test_answer_leads_with_the_top_idea"),
    ("unknown deep link opens the answer", 'else vm.detailGone = true;', 'else vm.detail = vm.answer;', "test_detail_view"),
]


def run_harness(modules_dir: Path) -> dict:
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    out = subprocess.run(["node", str(HARNESS), str(modules_dir)], capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise AssertionError(f"harness crashed: {out.stderr[-1500:]}")
    return json.loads(out.stdout)


class SimplifiedSiteLogicTest(unittest.TestCase):
    def test_every_check_passes(self):
        result = run_harness(APP)
        self.assertEqual(sorted(result), sorted(REQUIRED), "harness checks and REQUIRED drifted")
        failed = {k: v for k, v in result.items() if v is not True}
        self.assertEqual(failed, {})

    def test_section_never_writes_storage(self):
        # Opening the section must not change saved rosters or settings: it has no storage or store-writing calls at all.
        source = (APP / "simplified-site.js").read_text(encoding="utf-8")
        for needle in ("localStorage", "sessionStorage", "indexedDB", "store.replace", "store.set", "store.update", "ops."):
            self.assertNotIn(needle, source)

    def test_checks_fail_on_broken_builds(self):
        source = (APP / "simplified-site.js").read_text(encoding="utf-8")
        for what, old, new, check in MUTATIONS:
            with self.subTest(what):
                self.assertEqual(source.count(old), 1, f"mutation anchor is stale or not unique: {old}")
                with tempfile.TemporaryDirectory() as tmp:
                    for name in MODULES:
                        shutil.copy2(APP / name, Path(tmp) / name)
                    (Path(tmp) / "simplified-site.js").write_text(source.replace(old, new), encoding="utf-8")
                    result = run_harness(Path(tmp))
                self.assertIsNot(result.get(check), True, f"{check} did not catch: {what}")


if __name__ == "__main__":
    unittest.main()
