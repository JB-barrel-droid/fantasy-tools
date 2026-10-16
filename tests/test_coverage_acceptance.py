"""JEG-667: a recorded human decision lets a coverage hold pass, and only
that decision. Each hold case below is the bug the acceptance must NOT hide.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines"))
import test_review_coverage_churn as base  # noqa: E402

COMBO = base.COMBO
WEEK = 6


def entry(**kw):
    e = {"source": "fantasycalc", "combo": COMBO, "pos": "TE", "week": WEEK,
         "approved_by": "Jeremy", "approved_on": "2026-10-16", "reason": "rotation"}
    e.update(kw)
    return e


class CoverageAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def run_review(self, entries, **build_kw):
        paths = base.build(self.tmp, **build_kw)
        cand = json.loads(Path(paths["cand"]).read_text())
        cand["week_designated"] = f"Week {WEEK}"
        Path(paths["cand"]).write_text(json.dumps(cand))
        acc = self.tmp / "accepted.json"
        acc.write_text(json.dumps({"entries": entries}))
        rep = base.review(paths, coverage_accepted_path=str(acc))
        return rep, base.check(rep, f"coverage:{COMBO}/TE")

    def big_drop(self):
        tes = base._te_slugs(30)
        return dict(fx_te=30, cand_drop=tuple(tes[26:30])), tes[26:30]

    def test_unaccepted_big_drop_holds(self):
        kw, _ = self.big_drop()
        rep, cov = self.run_review([], **kw)
        self.assertEqual(cov["status"], "fail")
        self.assertEqual(rep["verdict"], "hold")

    def test_named_acceptance_passes_as_warn(self):
        kw, dropped = self.big_drop()
        rep, cov = self.run_review([entry(names=dropped)], **kw)
        self.assertEqual(cov["status"], "warn", cov)
        self.assertIn("accepted rotation", cov["detail"])
        self.assertEqual(rep["verdict"], "ready")

    def test_unnamed_extra_drop_still_holds(self):
        kw, dropped = self.big_drop()
        rep, cov = self.run_review([entry(names=dropped[:3])], **kw)
        self.assertEqual(cov["status"], "fail")

    def test_other_week_does_not_apply(self):
        kw, dropped = self.big_drop()
        _, cov = self.run_review([entry(names=dropped, week=WEEK - 1)], **kw)
        self.assertEqual(cov["status"], "fail")

    def test_other_position_does_not_apply(self):
        kw, dropped = self.big_drop()
        _, cov = self.run_review([entry(names=dropped, pos="WR")], **kw)
        self.assertEqual(cov["status"], "fail")

    def test_listed_but_unpriced_is_never_accepted_by_name(self):
        tes = base._te_slugs(30)
        kw = dict(fx_te=30, cand_drop=tuple(tes[26:30]), keep_listed=tuple(tes[26:30]))
        _, cov = self.run_review([entry(names=tes[26:30])], **kw)
        self.assertEqual(cov["status"], "fail")

    def test_floor_acceptance(self):
        kw, _ = self.big_drop()
        _, cov = self.run_review([entry(floor=26)], **kw)
        self.assertEqual(cov["status"], "warn", cov)
        self.assertIn("accepted floor", cov["detail"])

    def test_floor_below_candidate_count_holds(self):
        kw, _ = self.big_drop()
        _, cov = self.run_review([entry(floor=27)], **kw)  # candidate prices 26
        self.assertEqual(cov["status"], "fail")


if __name__ == "__main__":
    unittest.main()
