"""JEG-70: the weekly VORP translation refresh covers all 12 grains and the
freshness checkpoint fails closed on missing/stale grains.

The 12 grains are: usatoday/fantasypros/cbs/fantasycalc x 12-team x
{standard, half_ppr, ppr}. FantasyCalc 8/10/14-team grains are retired
(league-settings-001; translate_source raises SystemExit for them).
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
    def test_grain_enumeration_is_12(self):
        grains = refresh.GRAINS
        self.assertEqual(len(grains), 4)  # (source, teams) pairs
        combos = [(s, t, sc) for s, t in grains for sc in refresh.SCORINGS]
        self.assertEqual(len(combos), 12)
        for source, teams in grains:
            self.assertIn(source, ("usatoday", "fantasypros", "cbs", "fantasycalc"))
            self.assertEqual(teams, 12, source)

    def test_every_grain_is_translatable(self):
        """The retired 8/10/14-team FantasyCalc grains made translate_source
        raise SystemExit (not an Exception), aborting the whole refresh. Every
        listed grain must resolve to a fixture combo."""
        import json
        sys.path.insert(0, str(ROOT / "pipelines" / "vorp_translation"))
        from unified import resolve_combo_key
        fx = json.loads((ROOT / "data/fixtures/current/comparison-sources-data.json").read_text())
        for source, teams in refresh.GRAINS:
            for scoring in refresh.SCORINGS:
                resolve_combo_key(fx["sources"][source], scoring, teams)  # SystemExit if retired

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
                refresh.freshness_checkpoint({s: 4 for s, _ in refresh.GRAINS})
        self.assertIn("cbs/ppr/12t", str(ctx.exception))

    def test_freshness_checkpoint_fails_on_missing_grain(self):
        rows = []  # empty table
        fake_sb = type("FakeSB", (), {"get_all": staticmethod(lambda *a, **k: rows)})()
        with patch.object(refresh, "_sb", return_value=fake_sb):
            with self.assertRaises(SystemExit):
                refresh.freshness_checkpoint({s: 4 for s, _ in refresh.GRAINS})

    def test_freshness_checkpoint_passes_when_all_current(self):
        rows = []
        for source, teams in refresh.GRAINS:
            for scoring in refresh.SCORINGS:
                rows.append({"source": source, "scoring": scoring,
                             "league_teams": teams, "week": 4, "season": 2026})
        fake_sb = type("FakeSB", (), {"get_all": staticmethod(lambda *a, **k: rows)})()
        with patch.object(refresh, "_sb", return_value=fake_sb):
            refresh.freshness_checkpoint({s: 4 for s, _ in refresh.GRAINS})  # must not raise

    def test_grains_take_each_sources_content_week(self):
        # GAP-VORP-GRAIN-WEEK-LABEL: a lagging CBS section (Week 4) is
        # refreshed and checked at week 4 while the others are at week 5.
        fixture = {"sources": {s: {"week_designated": "Week 5"} for s, _ in refresh.GRAINS}}
        fixture["sources"]["cbs"] = {"source_provenance": {"week_designated": 4}}
        weeks = refresh.source_content_weeks(fixture)
        self.assertEqual(weeks["cbs"], 4)
        self.assertEqual(weeks["usatoday"], 5)
        rows = [{"source": s, "scoring": sc, "league_teams": t, "week": weeks[s], "season": 2026}
                for s, t in refresh.GRAINS for sc in refresh.SCORINGS]
        fake_sb = type("FakeSB", (), {"get_all": staticmethod(lambda *a, **k: rows)})()
        with patch.object(refresh, "_sb", return_value=fake_sb):
            refresh.freshness_checkpoint(weeks)  # CBS at 4 is fresh
            with self.assertRaises(SystemExit):  # the old chain-week rule would demand 5
                refresh.freshness_checkpoint({s: 5 for s, _ in refresh.GRAINS})
        written = []
        with patch.object(refresh, "source_content_weeks", return_value=weeks), \
                patch.object(refresh, "refresh_grain", lambda s, sc, t, w: written.append((s, w))), \
                patch.object(refresh, "freshness_checkpoint", lambda w: None), \
                patch.object(sys, "argv", ["x", "--week", "5"]):
            refresh.main()
        self.assertEqual({w for s, w in written if s == "cbs"}, {4})
        self.assertEqual({w for s, w in written if s != "cbs"}, {5})

    def test_unreadable_content_week_fails_closed(self):
        weeks = refresh.source_content_weeks({"sources": {}})
        self.assertTrue(all(w is None for w in weeks.values()))
        fake_sb = type("FakeSB", (), {"get_all": staticmethod(lambda *a, **k: [])})()
        with patch.object(refresh, "_sb", return_value=fake_sb):
            with self.assertRaises(SystemExit):
                refresh.freshness_checkpoint(weeks)


if __name__ == "__main__":
    unittest.main()
