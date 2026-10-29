"""Manager-aware trade recommendations (JEG-1217 stage 3): appeal, likelihood bands, ranking and stretch offers.

The checks live in tests/manager_recs_harness.cjs (pure Node, no browser). Every guard is proven:
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
HARNESS = ROOT / "tests" / "manager_recs_harness.cjs"
MODULES = ["manager-recs.js", "manager-profiles.js", "workspace.js"]

REQUIRED = [
    "test_draft_curve_positional", "test_unmarked_manager_uses_market", "test_blend_strong_counts_double",
    "test_doesnt_care_and_unknown_do_not_count", "test_names_and_other_change_words_only", "test_rankings_unavailable_falls_back",
    "test_missing_draft_rank_falls_back", "test_draft_gain_from_ranks", "test_band_boundaries", "test_rank_by_our_gain_not_appeal",
    "test_stretch_section", "test_excluded_and_my_team_left_out", "test_only_your_wins", "test_no_appeal_number_is_counted_not_shown",
    "test_values_untouched", "test_sources_labelled",
]


def run_harness(modules_dir: Path) -> dict:
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    out = subprocess.run(["node", str(HARNESS), str(modules_dir)], capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise AssertionError(f"harness crashed: {out.stderr[-1500:]}")
    return json.loads(out.stdout)


def mutated(old: str, new: str) -> tempfile.TemporaryDirectory:
    """A temp dir with the modules, manager-recs.js edited once; a stale anchor fails loudly."""
    tmp = tempfile.TemporaryDirectory()
    for name in MODULES:
        shutil.copy2(APP / name, Path(tmp.name) / name)
    path = Path(tmp.name) / "manager-recs.js"
    text = path.read_text(encoding="utf-8")
    if old not in text:
        tmp.cleanup()
        raise AssertionError(f"mutation anchor is stale: {old[:70]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return tmp


# (rule broken, anchor, replacement, a check that must fail)
MUTATIONS = [
    ("a lot counts the same as somewhat", "const WEIGHT = {strong: 2, some: 1};", "const WEIGHT = {strong: 1, some: 1};", "test_blend_strong_counts_double"),
    ("doesn't care counts", "const WEIGHT = {strong: 2, some: 1};", "const WEIGHT = {strong: 2, some: 1, none: 1};", "test_doesnt_care_and_unknown_do_not_count"),
    ("ranked by their appeal", "const order = (x, y) => y.ourGain - x.ourGain ||", "const order = (x, y) => y.theirGain - x.theirGain ||", "test_rank_by_our_gain_not_appeal"),
    ("likely line moved", "likely: 0.10,", "likely: 0.20,", "test_band_boundaries"),
    ("long shots in the main list", "(judged.band === \"longShot\" ? out.stretch : out.recommendations)", "out.recommendations", "test_stretch_section"),
    ("worse than long shot shown", "if (judged.band === \"hidden\") { out.counts.hidden += 1; return; }", "if (judged.band === \"hidden\") judged.band = \"longShot\";", "test_stretch_section"),
    ("excluded managers and my team recommended", "new Map(P.eligibleOpponents(opts.book, opts.ws).map", "new Map(P.roster(opts.book, opts.ws).map",
     "test_excluded_and_my_team_left_out"),
    ("losing trades recommended", "if (!isWin(row)) { out.counts.notWin += 1; return; }", "", "test_only_your_wins"),
    ("missing draft rank counted as zero", "if (!Number.isInteger(rank) || rank < 1) return null;", "if (!Number.isInteger(rank) || rank < 1) return 0;", "test_missing_draft_rank_falls_back"),
    ("draft rank read as overall", "const list = curve[row.pos];", "const list = Object.values(curve).flat().sort((a, b) => b - a);", "test_draft_curve_positional"),
    ("no fallback to the market", "return finite(gains.market) ? {gain: gains.market,", "return false ? {gain: gains.market,", "test_unmarked_manager_uses_market"),
    ("sources not labelled", "sources: a.basis.map(x => ({anchor: x.anchor, ...SOURCES[x.anchor]}))", "sources: []", "test_sources_labelled"),
    ("rows edited in place", "(opts.rows || []).forEach(row => {", "(opts.rows || []).forEach(row => { row.edge = row.edge;  row.give.forEach(p => { p.values.ddf_value += 0; p.recommended = true; });", "test_values_untouched"),
]


class ManagerRecs(unittest.TestCase):
    def test_all_checks_pass(self):
        result = run_harness(APP)
        self.assertEqual(result["failures"], [])
        missing = [name for name in REQUIRED if name not in result["ran"]]
        self.assertEqual(missing, [], "required checks did not run")

    def test_checks_fail_on_broken_builds(self):
        for label, old, new, expect in MUTATIONS:
            with self.subTest(label):
                tmp = mutated(old, new)
                try:
                    result = run_harness(Path(tmp.name))
                finally:
                    tmp.cleanup()
                failed = {f["name"] for f in result["failures"]}
                self.assertIn(expect, failed, f"{label}: {expect} did not catch it (failed: {sorted(failed)})")

    def test_module_has_no_dom_or_engine_dependency(self):
        text = (APP / "manager-recs.js").read_text(encoding="utf-8")
        for token in ("document.", "localStorage", "fetch("):
            self.assertNotIn(token, text, token)


if __name__ == "__main__":
    unittest.main()
