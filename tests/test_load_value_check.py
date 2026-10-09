"""JEG-479 item 5: the rows the chain stores in public.value_check_values.

Both sides of every compared value, keyed (season, week, scoring, teams,
roster, view, series, player_key); `agrees` uses the report's tolerance with
exact presence; `held` marks every series of a held root; the DDF Value's
prior-week sides are stored as series <version>_prior.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
import load_value_check as lv  # noqa: E402


def _setting(engine_vals, ref_vals, prior_e=None, prior_r=None):
    spec = {"scoring": "half_ppr", "teams": 10, "superflex": 1}
    reference = {"half_ppr/10/sf1": {"setting": spec, "views": {"indexed": {"7": ref_vals}, "vorp": {}, "adj": {}},
                                     "prior": {"indexed": {"ddf_value": {"values": prior_r or {}}}}}}
    engine = {"half_ppr/10/sf1": {"views": {"indexed": {"7": engine_vals}, "vorp": {}, "adj": {}},
                                  "prior": {"indexed": {"ddf_value": {"values": prior_e or {}}}}}}
    return engine, reference


class LoadValueCheckRows(unittest.TestCase):
    def test_rows(self):
        engine, reference = _setting({"espn": 10.0, "cbs": 5.0, "ddf_value": 7.0, "razzball": None},
                                     {"espn": 10.04, "cbs": 5.2, "ddf_value": 7.0, "razzball": 3.0},
                                     {"7": 6.0}, {"7": 6.0})
        rows = lv.build_rows({"tolerance": 0.05}, engine, reference, 2026, 5, {7: "some player"},
                             {"cbs", "cbs_adjusted"})
        by = {r["series"]: r for r in rows}
        self.assertEqual(set(by), {"espn", "cbs", "ddf_value", "razzball", "ddf_value_prior"})
        self.assertTrue(by["espn"]["agrees"])
        self.assertFalse(by["cbs"]["agrees"])
        self.assertTrue(by["cbs"]["held"])
        self.assertFalse(by["espn"]["held"])
        self.assertFalse(by["razzball"]["agrees"], "presence must match exactly")
        self.assertIsNone(by["razzball"]["engine_value"])
        self.assertEqual(by["ddf_value_prior"]["engine_value"], 6.0)
        r = by["espn"]
        self.assertEqual((r["season"], r["week"], r["scoring"], r["teams"], r["roster"], r["view"], r["player"]),
                         (2026, 5, "half", 10, "superflex", "indexed", "some player"))

    def test_player_names_prefer_the_lowercased_name(self):
        fixture = {"player_keys": {"ja'marr chase": 1, "jamarr chase": 1, "x": 2}}
        players = {1: {"name": "Ja'Marr Chase"}, 2: {"name": "Somebody"}, 3: {"name": "No Slug"}}
        self.assertEqual(lv.player_names(fixture, players), {1: "ja'marr chase", 2: "x", 3: "no slug"})


if __name__ == "__main__":
    unittest.main()
