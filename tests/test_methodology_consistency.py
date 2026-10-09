"""Methodology-consistency checkpoint regression tests.

2026-10-01: the checkpoint builder hardcoded
EXPECTED_METHOD = "proportional_scaling_vorp_overlap", so Jeremy's intentional
flex-aware total-pie methodology change (d462942 + 6a824749, which writes
proportional_scaling_flex_aware_per_position) showed up as a bad checkpoint.
The expectation is now derived from the reindex pipeline itself. These tests
prove the check still catches genuine drift: a source silently keeping an OLD
method while the pipeline moved on must fail.

2026-10-08 (JEG-482, Jeremy): the reindex method is now the one-factor
order_preserving_rescale, under fit key "order_preserving_rescale"; the
flex-aware bucket method is the OLD method a drifted source would carry.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
import build_pipeline_checkpoints as bpc  # noqa: E402


def _fixture(method_by_combo, tmpdir, extra_fit=None):
    """Minimal comparison-sources-data.json shaped like the real fixture.

    extra_fit: optional dict merged into every combo's fit block (e.g. a
    retired vorp_translation step a pre-JEG-482 fixture carries).
    """
    def _combo(src, cn):
        fit = {bpc._reindex_pipeline_fit_key(): {"method": method_by_combo.get((src, cn)), "anchor": "espn_leg"}}
        if extra_fit:
            fit.update(extra_fit)
        return {"fit": fit}
    combos_fc = {
        cn: _combo("fantasycalc", cn)
        for cn in ("full_12_qb1", "half_12_qb1", "standard_12_qb1")
    }
    sources = {"fantasycalc": {"combos": combos_fc}}
    for src in ("fantasypros", "usatoday", "cbs"):
        sources[src] = {"combos": {
            cn: _combo(src, cn)
            for cn in ("full_12", "half_12", "standard_12")
        }}
    p = Path(tmpdir) / "data" / "fixtures" / "current"
    p.mkdir(parents=True, exist_ok=True)
    (p / "comparison-sources-data.json").write_text(json.dumps({"sources": sources}))
    return tmpdir


class TestMethodologyConsistency(unittest.TestCase):
    def _run_with(self, method_by_combo, extra_fit=None):
        tmp = tempfile.mkdtemp()
        old_repo = bpc.REPO
        bpc.REPO = Path(_fixture(method_by_combo, tmp, extra_fit=extra_fit))
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
            "order_preserving_rescale",
        )
        self.assertEqual(bpc._reindex_pipeline_fit_key(), "order_preserving_rescale")

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
        m[("usatoday", "full_12")] = "proportional_scaling_flex_aware_per_position"
        res = self._run_with(m)
        self.assertEqual(res["status"], "bad", res.get("reason"))
        self.assertIn("usatoday/full_12", res["reason"])

    def test_vorp_translation_fit_key_is_not_held_to_reindex_method(self):
        """A fit key other than the reindex one (here the retired
        vorp_translation record a pre-JEG-482 fixture carries) is not held
        to the reindex method: the check scopes its method/anchor
        expectation to the reindex fit key only.

        Discrimination: the pre-fix loop iterated every fit key, so this
        fixture -- which mirrors the real production fixture -- returned
        "bad" with 12 vorp-supabase inconsistencies. Post-fix it is "ok".
        """
        extra = {"vorp_translation": {"method": "vorp-supabase", "n_translated": 176}}
        res = self._run_with(self._all_current(), extra_fit=extra)
        self.assertEqual(res["status"], "ok", res.get("reason"))
        self.assertIn("reindex fit", res.get("reason", ""))

    def test_missing_reindex_fit_is_bad(self):
        """A combo present in the fixture but missing the reindex fit means
        the reindex step never stamped it -- fail closed rather than passing
        a combo the check cannot verify."""
        tmp = tempfile.mkdtemp()
        m = self._all_current()
        old_repo = bpc.REPO
        bpc.REPO = Path(_fixture(m, tmp))
        try:
            p = bpc.REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
            d = json.loads(p.read_text(encoding="utf-8"))
            del d["sources"]["cbs"]["combos"]["full_12"]["fit"][bpc._reindex_pipeline_fit_key()]
            p.write_text(json.dumps(d))
            res = bpc.build_methodology_consistency()
        finally:
            bpc.REPO = old_repo
        self.assertEqual(res["status"], "bad", res.get("reason"))
        self.assertIn("cbs/full_12", res["reason"])
