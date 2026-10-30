"""Values page Fieldnotes view (JEG-1265): parity with the unchanged page, states, missing-is-not-zero and the horizon guard.

The checks live in tests/values_fieldnotes_harness.cjs (pure Node, no browser). It reads fmt(), sortedRows(), the header
click rule, aria-sort, TABLE_GROUPS and the SERIES_GROUPS notes out of app/v2/v2.js and runs them beside the component on
the synthetic fixture. Every guard is proven: test_checks_fail_on_broken_builds copies the modules, breaks one rule at a
time, and requires the harness to name the check that catches it.
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
HARNESS = ROOT / "tests" / "values_fieldnotes_harness.cjs"
MODULES = ["values-fieldnotes.js", "source-views.js", "v2.js"]

REQUIRED = [
    "test_page_code_found", "test_fmt_matches_page", "test_every_number_displayed_as_page", "test_missing_is_not_zero",
    "test_sort_matches_page", "test_next_sort_matches_page", "test_aria_sort_matches_page", "test_groups_match_page",
    "test_source_categories_stay_distinct", "test_unavailable_source_column", "test_states", "test_weekly_never_blended",
    "test_shown_and_meta", "test_ranking_and_labels", "test_context_not_mutated", "test_fixture_labelled",
    "test_module_writes_nothing",
]

# (what is broken, old text, new text, the check that must catch it)
MUTATIONS = [
    ("own number format", 'const text = v.toFixed(1); return text === "-0.0" ? "0.0" : text.replace("-", "−");',
     'const text = v.toFixed(2); return text;', "test_fmt_matches_page"),
    ("hyphen for minus", 'text.replace("-", "−")', 'text', "test_fmt_matches_page"),
    ("missing drawn as zero", 'if (Number.isFinite(v)) return {col: col.id, text: fmt(v)',
     'if (Number.isFinite(v) || v === null) return {col: col.id, text: fmt(v || 0)', "test_every_number_displayed_as_page"),
    ("missing sorts as zero", 'if (!fa) return 1;', 'if (!fa) return dir * (0 - vb);', "test_missing_is_not_zero"),
    ("ties not by rank", 'return dir * (va - vb) || a.rank - b.rank;', 'return dir * (va - vb);', "test_sort_matches_page"),
    ("text sorted as numbers", 'if (col.text) return dir * String(va).localeCompare(String(vb));', '', "test_sort_matches_page"),
    ("tier order ignored", 'if (order) return dir * (order(a) - order(b)) || a.rank - b.rank;', '', "test_sort_matches_page"),
    ("new text column descends", 'col.text && current !== col.id ? "asc" : dir', 'dir', "test_next_sort_matches_page"),
    ("aria-sort on the wrong column", 'const key = sort ? sort.key : rankKey;', 'const key = sort ? sort.key : null;', "test_aria_sort_matches_page"),
    ("groups reordered", 'const GROUP_ORDER = ["ddf", "projections", "published", "observed", "vorp", "spread"];',
     'const GROUP_ORDER = ["ddf", "published", "projections", "observed", "vorp", "spread"];', "test_groups_match_page"),
    ("observed folded into published", 'cols: cols.filter(col => (col.kind === "value" || col.kind === "spread") && col.group === g.id)',
     'cols: cols.filter(col => (col.kind === "value" || col.kind === "spread") && (col.group === g.id || (g.id === "published" && col.group === "observed")))',
     "test_source_categories_stay_distinct"),
    ("unavailable column reason dropped", 'unavailable: col.unavailable || null,', 'unavailable: null,', "test_unavailable_source_column"),
    ("unavailable treated as ready", 'if (c.status !== "ready") {', 'if (c.status === "unavailable") {', "test_states"),
    ("weekly mixed with rest of season", 'if (horizons.length > 1) {', 'if (false) {', "test_weekly_never_blended"),
    ("every row shown", 'base.rows = sorted.slice(0, shown).map(', 'base.rows = sorted.map(', "test_shown_and_meta"),
    ("context mutated", 'const out = rows.slice();', 'const out = rows;', "test_context_not_mutated"),
    ("fixture label dropped", 'fixture: c.fixture ? {kind: c.fixture.kind, label: c.fixture.label} : null', 'fixture: null', "test_fixture_labelled"),
    ("notes dropped", 'const notes = (row.notes && row.notes[col.id]) || [];', 'const notes = [];', "test_ranking_and_labels"),
]


def run_harness(modules_dir: Path) -> dict:
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    out = subprocess.run(["node", str(HARNESS), str(modules_dir)], capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise AssertionError(f"harness crashed: {out.stderr[-1500:]}")
    return json.loads(out.stdout)


class ValuesFieldnotesLogicTest(unittest.TestCase):
    def test_every_check_passes(self):
        result = run_harness(APP)
        self.assertEqual(sorted(result), sorted(REQUIRED), "harness checks and REQUIRED drifted")
        failed = {k: v for k, v in result.items() if v is not True}
        self.assertEqual(failed, {})

    def test_page_does_not_load_it_yet(self):
        # Isolated until JEG-1137's owner wires it: no shared file names it.
        for name in ("shell.html", "v2.js", "league.js"):
            self.assertNotIn("values-fieldnotes", (APP / name).read_text(encoding="utf-8"), name)

    def test_checks_fail_on_broken_builds(self):
        source = (APP / "values-fieldnotes.js").read_text(encoding="utf-8")
        for what, old, new, check in MUTATIONS:
            with self.subTest(what):
                self.assertEqual(source.count(old), 1, f"mutation anchor is stale or not unique: {old}")
                with tempfile.TemporaryDirectory() as tmp:
                    for name in MODULES:
                        shutil.copy2(APP / name, Path(tmp) / name)
                    (Path(tmp) / "values-fieldnotes.js").write_text(source.replace(old, new), encoding="utf-8")
                    result = run_harness(Path(tmp))
                self.assertIsNot(result.get(check), True, f"{check} did not catch: {what}")


if __name__ == "__main__":
    unittest.main()
