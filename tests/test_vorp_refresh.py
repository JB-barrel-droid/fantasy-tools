"""JEG-70: the weekly VORP translation refresh covers all 21 grains and the
freshness checkpoint fails closed on missing/stale grains.

The 21 grains are: usatoday/fantasypros/cbs x 12-team x {standard, half_ppr,
ppr} (9) + fantasycalc x {8,10,12,14}-team x {standard, half_ppr, ppr} (12).
FantasyCalc qb2 combos are intentionally excluded (no qb grain dimension;
qb2 natives diverge -- they stay on reindex-fallback per the JEG-64 guard).
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import refresh_vorp_translation as refresh


class RefreshGrainsTest(unittest.TestCase):
    def test_grain_enumeration_is_21(self):
        grains = refresh.GRAINS
        self.assertEqual(len(grains), 7)  # (source, teams) pairs
        combos = [(s, t, sc) for s, t in grains for sc in refresh.SCORINGS]
        self.assertEqual(len(combos), 21)
        # 12-team only for the three 12t sources; 8/10/12/14 for fantasycalc
        for source, teams in grains:
            if source in ("usatoday", "fantasypros", "cbs"):
                self.assertEqual(teams, 12, source)
            elif source == "fantasycalc":
                self.assertIn(teams, (8, 10, 12, 14))
            else:
                self.fail(f"unexpected source {source}")

    def test_no_qb2_grains(self):
        # The refresh must never write a qb2 grain (no qb dimension in the
        # JEG-62 schema; qb2 combos stay on reindex-fallback).
        for source, teams in refresh.GRAINS:
            self.assertNotIn("qb2", source)

    def test_freshness_checkpoint_fails_on_stale_grain(self):
        rows = []
        for source, teams in refresh.GRAINS:
            for scoring in refresh.SCORINGS:
                week = 4
                if (source, teams, scoring) == ("cbs", 12, "ppr"):
                    week = 3  # one stale grain
                rows.append({"source": source, "scoring": scoring,
                             "league_teams": teams, "week": week, "season": 2026})
        fake_sb = type("FakeSB", (), {"get_all": staticmethod(lambda *a, **k: rows)})()
        with patch.object(refresh, "_sb", return_value=fake_sb):
            with self.assertRaises(SystemExit) as ctx:
                refresh.freshness_checkpoint(4)
        self.assertIn("cbs/ppr/12t", str(ctx.exception))

    def test_freshness_checkpoint_fails_on_missing_grain(self):
        rows = []  # empty table
        fake_sb = type("FakeSB", (), {"get_all": staticmethod(lambda *a, **k: rows)})()
        with patch.object(refresh, "_sb", return_value=fake_sb):
            with self.assertRaises(SystemExit):
                refresh.freshness_checkpoint(4)

    def test_freshness_checkpoint_passes_when_all_current(self):
        rows = []
        for source, teams in refresh.GRAINS:
            for scoring in refresh.SCORINGS:
                rows.append({"source": source, "scoring": scoring,
                             "league_teams": teams, "week": 4, "season": 2026})
        fake_sb = type("FakeSB", (), {"get_all": staticmethod(lambda *a, **k: rows)})()
        with patch.object(refresh, "_sb", return_value=fake_sb):
            refresh.freshness_checkpoint(4)  # must not raise


if __name__ == "__main__":
    unittest.main()
