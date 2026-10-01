#!/usr/bin/env python3
"""Regression tests for the CBS ROS bake intake (JEG-33).

_intake_cbsros must:
  - price only rows with all three per-game scorings finite (never partial),
  - fail closed when the snapshot has no vintage_date,
  - exclude unresolvable identities (never guess),
  - key the med dict by numeric player_key (the chart join key).

_latest_cbsros_snapshot must pick the max vintage_date snapshot and fail
closed when none parse.
"""

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO / "pipelines" / "lib"))

import bake_players
from bake_players import _intake_cbsros, _latest_cbsros_snapshot


def _snap(rows, vintage="2026-09-30"):
    d = {"vintage_date": vintage, "rows": rows, "review_rows": []}
    if vintage is None:
        d.pop("vintage_date")
    return d


def _row(name, pos, std, half, ppr, team="KC"):
    return {"player_name": name, "player_norm": name.lower(), "pos": pos,
            "team": team, "gp": 13.0,
            "per_game_standard": std, "per_game_half_ppr": half,
            "per_game_ppr": ppr}


class IntakeCbsrosTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, snap):
        p = self.dir / "snapshot.json"
        p.write_text(json.dumps(snap))
        return p

    def test_prices_complete_rows_by_player_key(self):
        # Jahmyr Gibbs must resolve to his numeric chart key with all 3.
        p = self._write(_snap([_row("Jahmyr Gibbs", "RB", 20.0, 22.0, 24.0)]))
        med, vintage = _intake_cbsros(p, None)
        self.assertEqual(vintage, "2026-09-30")
        self.assertEqual(len(med), 1)
        key = next(iter(med))
        self.assertIsInstance(key, int)
        self.assertEqual(med[key],
                         {"standard": 20.0, "half_ppr": 22.0, "ppr": 24.0})

    def test_partial_scoring_row_excluded(self):
        rows = [_row("Jahmyr Gibbs", "RB", 20.0, 22.0, 24.0),
                _row("Saquon Barkley", "RB", 19.0, 21.0, None)]
        p = self._write(_snap(rows))
        med, _ = _intake_cbsros(p, None)
        self.assertEqual(len(med), 1)
        # the complete row survives; the partial one does not
        vals = list(med.values())[0]
        self.assertEqual(vals["ppr"], 24.0)

    def test_missing_vintage_fails_closed(self):
        p = self._write(_snap([_row("Jahmyr Gibbs", "RB", 20, 22, 24)],
                              vintage=None))
        with self.assertRaises(SystemExit):
            _intake_cbsros(p, None)

    def test_unresolvable_identity_excluded_not_guessed(self):
        rows = [_row("Jahmyr Gibbs", "RB", 20.0, 22.0, 24.0),
                _row("Not A Real Player Xyz", "RB", 99.0, 99.0, 99.0)]
        p = self._write(_snap(rows))
        med, _ = _intake_cbsros(p, None)
        self.assertEqual(len(med), 1)
        for v in med.values():
            self.assertLess(v["ppr"], 50.0)

    def test_non_skill_position_excluded(self):
        rows = [_row("Jahmyr Gibbs", "RB", 20.0, 22.0, 24.0),
                _row("Harrison Butker", "K", 9.0, 9.0, 9.0)]
        p = self._write(_snap(rows))
        med, _ = _intake_cbsros(p, None)
        self.assertEqual(len(med), 1)

    def test_nonfinite_values_excluded(self):
        rows = [_row("Jahmyr Gibbs", "RB", 20.0, float("nan"), 24.0)]
        p = self._write(_snap(rows))
        med, _ = _intake_cbsros(p, None)
        self.assertEqual(med, {})

    def test_latest_snapshot_picks_max_vintage(self):
        real_dir = bake_players.CBSROS_SNAPSHOT_DIR
        try:
            d1 = self.dir / "2026-09-29"
            d2 = self.dir / "2026-09-30"
            d1.mkdir()
            d2.mkdir()
            (d1 / "snapshot.json").write_text(
                json.dumps(_snap([], vintage="2026-09-29")))
            (d2 / "snapshot.json").write_text(
                json.dumps(_snap([], vintage="2026-09-30")))
            bake_players.CBSROS_SNAPSHOT_DIR = self.dir
            self.assertEqual(_latest_cbsros_snapshot(), d2 / "snapshot.json")
        finally:
            bake_players.CBSROS_SNAPSHOT_DIR = real_dir

    def test_latest_snapshot_fails_closed_when_none_parse(self):
        real_dir = bake_players.CBSROS_SNAPSHOT_DIR
        try:
            bake_players.CBSROS_SNAPSHOT_DIR = self.dir / "empty"
            with self.assertRaises(SystemExit):
                _latest_cbsros_snapshot()
        finally:
            bake_players.CBSROS_SNAPSHOT_DIR = real_dir


if __name__ == "__main__":
    unittest.main()
