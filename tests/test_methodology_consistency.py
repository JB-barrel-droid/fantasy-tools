"""Methodology-consistency checkpoint regression tests.

2026-10-01: the checkpoint builder hardcoded
EXPECTED_METHOD = "proportional_scaling_vorp_overlap", so Jeremy's intentional
flex-aware total-pie methodology change (d462942 + 6a824749, which writes
proportional_scaling_flex_aware_per_position) showed up as a bad checkpoint.
The expectation is now derived from the reindex pipeline itself. These tests
prove the check still catches genuine drift: a source silently keeping an OLD
method while the pipeline moved on must fail.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
import build_pipeline_checkpoints as bpc  # noqa: E402


def _fixture(method_by_combo, tmpdir):
    """Minimal comparison-sources-data.json shaped like the real fixture."""
    combos_fc = {
        cn: {"fit": {"flex_aware_pie": {"method": method_by_combo.get(("fantasycalc", cn)), "anchor": "espn_leg"}}}
        for cn in ("full_12_qb1", "half_12_qb1", "standard_12_qb1")
    }
    sources = {"fantasycalc": {"combos": combos_fc}}
    for src in ("fantasypros", "usatoday", "cbs"):
        sources[src] = {"combos": {
            cn: {"fit": {"flex_aware_pie": {"method": method_by_combo.get((src, cn)), "anchor": "espn_leg"}}}
            for cn in ("full_12", "half_12", "standard_12")
        }}
    p = Path(tmpdir) / "data" / "fixtures" / "current"
    p.mkdir(parents=True, exist_ok=True)
    (p / "comparison-sources-data.json").write_text(json.dumps({"sources": sources}))
    return tmpdir


class TestMethodologyConsistency(unittest.TestCase):
    def _run_with(self, method_by_combo):
        tmp = tempfile.mkdtemp()
        old_repo = bpc.REPO
        bpc.REPO = Path(_fixture(method_by_combo, tmp))
        try:
            return bpc.build_methodology_consistency()
        finally:
            bpc.REPO = old_repo

    def _all_current(self):
        current = bpc._reindex_pipeline_method()
        m = {}
        for cn in ("full_12_qb1", "half_12_qb1", "standard_12_qb1"):
            m[("fantasycalc", cn)] = current
        for src in ("fantasypros", "usatoday", "cbs"):
            for cn in ("full_12", "half_12", "standard_12"):
                m[(src, cn)] = current
        return m

    def test_expected_method_comes_from_pipeline(self):
        """The expectation must track the pipeline's actual fit metadata."""
        self.assertEqual(
            bpc._reindex_pipeline_method(),
            "proportional_scaling_flex_aware_per_position",
        )

    def test_all_sources_on_current_method_is_ok(self):
        """The intentional methodology change must not read as a failure."""
        res = self._run_with(self._all_current())
        self.assertEqual(res["status"], "ok", res.get("reason"))

    def test_one_source_on_old_method_is_bad(self):
        """A source silently keeping the pre-flex-aware method while the
        pipeline moved on is genuine drift and must fail.

        Proves the guard discriminates: this is the state the old hardcoded
        constant could not distinguish from the intentional migration."""
        m = self._all_current()
        m[("usatoday", "full_12")] = "proportional_scaling_vorp_overlap"
        res = self._run_with(m)
        self.assertEqual(res["status"], "bad", res.get("reason"))
        self.assertIn("usatoday/full_12", res["reason"])
