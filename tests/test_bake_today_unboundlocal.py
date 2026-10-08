"""Regression tests for the JEG-405 bake UnboundLocalError fix.

JEG-405 (ARCH-004, P0): pipelines/bake_players.py.bake() read the local
`today` at line 615 (prior-snapshot selection) before its assignment at
the meta block (~line 731). Python raises UnboundLocalError on any bake
with an existing dated snapshot, blocking the ESPN-primary bake entirely.

Fix: assign `today = str(_date.today())` once at the top of bake(),
BEFORE the prior-snapshot scan, and remove the later assignment.

These tests:
  1. Verify bake() does NOT raise UnboundLocalError when a dated snapshot
     is present (the bug path).
  2. Verify the prior-snapshot scan selects the correct prior date
     (the one < today with the max date).
  3. Verify the bake produces a players.json with meta.as_of == today's date.
  4. Verify the fail-closed ESPN-zero audit still aborts the bake (the
     fix must not silently weaken the fail-closed gates).

Discrimination: each test is written against bake()'s today-flow contract.
Removing the top-of-bake() assignment and restoring the later one turns
test_prior_snapshot_selected_with_existing_snapshot red (UnboundLocalError
on the prior-snapshot scan). Removing the FAIL-CLOSED gate on zero ESPN
intake turns test_zero_espn_intake_fails_closed red.
"""
import argparse
import csv
import json
import os
import sys
import tempfile
import unittest
from datetime import date as _real_date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import bake_players
from canonical_players import Registry


# ---------------------------------------------------------------------------
# Test fixtures (hermetic, no Supabase / no live CSVs)
# ---------------------------------------------------------------------------

def _test_registry():
    """A small in-memory registry — load_registry(rows=...) builds from it."""
    return Registry([
        {"player_key": 777, "id": "u1", "full_name": "Test Player",
         "position": "QB", "active": True, "team_id": 10},
        {"player_key": 888, "id": "u2", "full_name": "Other Player",
         "position": "RB", "active": True, "team_id": 20},
    ])


def _espn_csv(tmpdir):
    """A minimal ESPN projections CSV that prices one QB + one RB."""
    # weeks_covered: ESPN's ROS window, required since GAP-GAMES-REMAINING-STALE.
    cols = ["player", "pos", "team", "eligible", "espn_snapshot_date",
            "r_pass_yds", "r_pass_tds", "r_rush_yds", "r_rush_tds",
            "r_receptions", "r_rec_yds", "r_rec_tds", "weeks_covered"]
    today = _real_date.today().isoformat()
    rows = [
        {"weeks_covered": "5-18", "player": "Test Player", "pos": "QB", "team": "BUF",
         "eligible": "True", "espn_snapshot_date": today,
         "r_pass_yds": "3163.3", "r_pass_tds": "20.7",
         "r_rush_yds": "", "r_rush_tds": "",
         "r_receptions": "", "r_rec_yds": "", "r_rec_tds": ""},
        {"weeks_covered": "5-18", "player": "Other Player", "pos": "RB", "team": "LA",
         "eligible": "True", "espn_snapshot_date": today,
         "r_pass_yds": "", "r_pass_tds": "",
         "r_rush_yds": "800.0", "r_rush_tds": "6.0",
         "r_receptions": "20.0", "r_rec_yds": "150.0", "r_rec_tds": "1.0"},
    ]
    p = Path(tmpdir) / "espn.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    return str(p)


def _empty_csv(tmpdir, name):
    """Empty PM / Razzball CSV — header only, zero priced rows."""
    p = Path(tmpdir) / name
    p.write_text("player,pos,team,eligible\n")
    return str(p)


def _empty_cbsros_snapshot(tmpdir):
    """An empty CBS ROS snapshot (vintage_date set; no priced rows)."""
    p = Path(tmpdir) / "snapshot.json"
    p.write_text(json.dumps({"vintage_date": "2026-09-30",
                             "rows": [], "review_rows": []}))
    return str(p)


def _k_dst_json(tmpdir):
    """Empty K and DST JSON — no K/DST rows in the test fixture."""
    k = Path(tmpdir) / "k.json"
    k.write_text(json.dumps({"snapshot_date": "2026-09-21", "kickers": []}))
    d = Path(tmpdir) / "dst.json"
    d.write_text(json.dumps({"snapshot_date": "2026-09-21", "defenses": []}))
    return str(k), str(d)


def _prior_snapshot(tmpdir, as_of):
    """Write a prior-bake snapshot dated as_of (< today) so the scan picks it up."""
    snap = {
        "meta": {"as_of": as_of},
        "players": [{
            "player_key": 777,
            "name": "Test Player",
            "pos": "QB",
            "team": "BUF",
            "espn_ros": {"standard": 200.0, "half_ppr": 200.0, "ppr": 200.0},
            "blend_ros": {"standard": 200.0, "half_ppr": 200.0, "ppr": 200.0},
        }],
    }
    p = Path(tmpdir) / "snapshots" / f"players_{as_of}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snap))
    return p


def _args(tmpdir):
    """argparse.Namespace with all the file inputs bake() expects."""
    espn = _espn_csv(tmpdir)
    pm = _empty_csv(tmpdir, "pm.csv")
    rz = _empty_csv(tmpdir, "razzball.csv")
    cbsros = _empty_cbsros_snapshot(tmpdir)
    k_json, dst_json = _k_dst_json(tmpdir)
    return argparse.Namespace(
        espn_csv=espn,
        pm_csv=pm,
        razzball_csv=rz,
        cbsros_snapshot=cbsros,
        k_json=k_json,
        dst_json=dst_json,
    )


def _stub_dataset_status(meta, players, **kwargs):
    """Stand-in for build_dataset_status: the 400-player universe floor is
    orthogonal to the JEG-405 contract (today defined before the
    prior-snapshot scan), and this hermetic fixture prices 2 players."""
    return {"stubbed": True, "n_players": len(players or [])}


def _schedule_from_bye_table():
    """A full season schedule consistent with data/inputs/nfl_byes_2026.json.

    bake() cross-checks the bye table against the Supabase schedule and fails
    closed on any disagreement (GAP-GAMES-REMAINING-STALE, 2026-10-08). The
    old two-row games stub predates that check and made every bake here abort,
    so the stub now plays every team once in each of its non-bye weeks."""
    byes, (first, last) = bake_players.load_byes()
    teams = sorted(byes)
    ids = {abbr: 100 + i for i, abbr in enumerate(teams)}
    rows = []
    for week in range(first, last + 1):
        playing = [t for t in teams if byes[t] != week]
        assert len(playing) % 2 == 0, f"odd team count in week {week}"
        for home, away in zip(playing[0::2], playing[1::2]):
            rows.append({"week": week, "home_team_id": ids[home], "away_team_id": ids[away]})
    return [{"id": i, "abbreviation": a} for a, i in ids.items()], rows


def _fake_query_all(table, params):
    """Stub Supabase query_all(): teams and a bye-consistent schedule."""
    teams, games = _schedule_from_bye_table()
    if table == "teams":
        return teams
    if table == "games":
        return games
    return []


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class BakeTodayUnboundLocalTest(unittest.TestCase):
    """The JEG-405 regression: bake() must not raise UnboundLocalError when
    an existing dated snapshot is present in SNAPSHOT_DIR."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = self.tmp.name
        # Hermetic SNAPSHOT_DIR so the test doesn't read the repo's real
        # snapshots (which carry other meta keys the test doesn't need).
        self._real_snap_dir = bake_players.SNAPSHOT_DIR
        self._real_fix_dir = bake_players.FIXTURE_DIR
        self._real_cbsros_dir = bake_players.CBSROS_SNAPSHOT_DIR
        bake_players.SNAPSHOT_DIR = Path(self.tmpdir) / "snapshots"
        bake_players.SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        bake_players.FIXTURE_DIR = Path(self.tmpdir) / "current"
        bake_players.FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        bake_players.CBSROS_SNAPSHOT_DIR = Path(self.tmpdir) / "cbsros"

    def tearDown(self):
        bake_players.SNAPSHOT_DIR = self._real_snap_dir
        bake_players.FIXTURE_DIR = self._real_fix_dir
        bake_players.CBSROS_SNAPSHOT_DIR = self._real_cbsros_dir
        self.tmp.cleanup()

    def _run_bake(self):
        """Invoke bake() with every external side-effect mocked."""
        args = _args(self.tmpdir)
        with patch.object(bake_players, "load_registry", return_value=_test_registry()), \
             patch.object(bake_players, "query_all", side_effect=_fake_query_all), \
             patch.object(bake_players, "load_preseason_ecr_ranks",
                          return_value=({}, {"resolved": 0, "unmatched": 0})), \
             patch.object(bake_players, "annotate_rows", lambda players, ranks: None), \
             patch.object(bake_players, "build_dataset_status",
                          side_effect=_stub_dataset_status):
            return bake_players.bake(args)

    def test_prior_snapshot_selected_with_existing_snapshot(self):
        """The bug path: an existing dated snapshot in SNAPSHOT_DIR must
        be picked up by the prior-snapshot scan without raising
        UnboundLocalError. Prior date must equal the snapshot's as_of."""
        prior_date = (_real_date.today().replace(day=1) if _real_date.today().day > 1
                      else (_real_date.today() - _real_date.resolution)).isoformat()
        # Guarantee strict less-than vs today.
        if prior_date >= _real_date.today().isoformat():
            prior_date = "2026-01-01"
        _prior_snapshot(self.tmpdir, prior_date)

        result = self._run_bake()

        self.assertEqual(result["meta"]["prior_blend_snapshot"], prior_date,
                         "prior-snapshot scan must pick the dated snapshot")
        self.assertEqual(result["meta"]["as_of"], _real_date.today().isoformat(),
                         "meta.as_of must equal today's date")

    def test_prior_scan_skips_snapshots_dated_today_or_later(self):
        """The filter `d < today` must drop same-day / future-dated
        snapshots. With NO qualifying prior, prior_blend_snapshot is None."""
        # Same-day snapshot must be ignored by the strict-less-than filter.
        _prior_snapshot(self.tmpdir, _real_date.today().isoformat())

        result = self._run_bake()
        self.assertIsNone(result["meta"]["prior_blend_snapshot"],
                          "same-day snapshot must not be selected as prior")

    def test_prior_scan_picks_max_dated_snapshot(self):
        """Two snapshots, both < today — the max-dated one wins."""
        older = "2026-01-01"
        newer = (_real_date.today() - _real_date.resolution).isoformat()
        if newer <= older:
            newer = "2026-02-01"
        _prior_snapshot(self.tmpdir, older)
        _prior_snapshot(self.tmpdir, newer)

        result = self._run_bake()
        self.assertEqual(result["meta"]["prior_blend_snapshot"], newer,
                         "prior scan picks the max-dated snapshot (< today)")

    def test_bake_writes_players_json(self):
        """Bake must produce data/fixtures/current/players.json with
        the expected meta block."""
        # No prior snapshot needed — the bake still must complete.
        result = self._run_bake()
        out_path = bake_players.FIXTURE_DIR / "players.json"
        self.assertTrue(out_path.exists(), "players.json must be written")
        payload = json.loads(out_path.read_text())
        self.assertEqual(payload["meta"]["as_of"], _real_date.today().isoformat())
        self.assertGreaterEqual(result["meta"]["n_players"], 2,
                                "two priced ESPN rows must appear")
        self.assertIn("prior_blend_snapshot", payload["meta"])

    def test_zero_espn_intake_fails_closed(self):
        """Fix must not weaken the ESPN-zero audit: an empty ESPN intake
        must still abort the bake (fail-closed)."""
        args = _args(self.tmpdir)
        # Overwrite the ESPN CSV with an empty one (header only).
        cols = ["player", "pos", "team", "eligible", "espn_snapshot_date",
                "r_pass_yds", "r_pass_tds", "r_rush_yds", "r_rush_tds",
                "r_receptions", "r_rec_yds", "r_rec_tds"]
        Path(args.espn_csv).write_text(",".join(cols) + "\n")

        with patch.object(bake_players, "load_registry", return_value=_test_registry()), \
             patch.object(bake_players, "query_all", side_effect=_fake_query_all), \
             patch.object(bake_players, "load_preseason_ecr_ranks",
                          return_value=({}, {"resolved": 0, "unmatched": 0})), \
             patch.object(bake_players, "annotate_rows", lambda players, ranks: None), \
             patch.object(bake_players, "build_dataset_status",
                          side_effect=_stub_dataset_status):
            with self.assertRaises(SystemExit) as cm:
                bake_players.bake(args)
        self.assertIn("FAIL-CLOSED", str(cm.exception))


if __name__ == "__main__":
    unittest.main()