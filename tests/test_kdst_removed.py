"""GAP-029 (Jeremy 2026-10-08, JEG-211 reconfirmed): kickers and team defenses
are not carried anywhere in the trade-value pipeline.

The chart excluded K/DST on 2026-10-03 (JEG-211); the bake still wrote 77
ESPN-only K/DST rows from frozen 2026-09-21 files, with meta.kdst_snapshot
"?", which nothing displayed and which kept a permanent "unknown" chart-input
freshness signal. These tests pin the removal:

  - the committed players.json has no K/DST rows and no K/DST meta;
  - a full (hermetic) bake writes skill positions only, and its
    source-accounting audit fails closed on any K/DST row that reaches it;
  - the freshness monitor no longer lists a K/DST chart input.

Each fails on dac0ff2 (origin/main before the removal).
"""
from __future__ import annotations

import csv
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "tests"))

import bake_players  # noqa: E402
import check_reference_freshness  # noqa: E402
import test_bake_today_unboundlocal as hermetic  # noqa: E402

KDST = {"K", "DST"}
KDST_META = {"n_k", "n_dst", "kdst_snapshot", "kdst_note"}


class CommittedFixtureHasNoKdst(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(
            (ROOT / "data/fixtures/current/players.json").read_text(encoding="utf-8"))

    def test_no_kdst_rows(self):
        kdst = [p["name"] for p in self.payload["players"] if p["pos"] in KDST]
        self.assertEqual(kdst[:5], [], f"{len(kdst)} K/DST rows in players.json")

    def test_no_kdst_meta(self):
        meta = self.payload["meta"]
        self.assertEqual(sorted(KDST_META & set(meta)), [])
        self.assertEqual(meta["n_players"], len(self.payload["players"]))
        keys = [d.get("key") for d in
                (meta.get("dataset_status") or {}).get("datasets") or []]
        self.assertNotIn("kdst", keys)

    def test_frozen_inputs_retired(self):
        self.assertEqual(sorted(p.name for p in (ROOT / "data/inputs").glob("espn_k_*")) +
                         sorted(p.name for p in (ROOT / "data/inputs").glob("espn_dst_*")), [])


class BakeCarriesSkillPositionsOnly(unittest.TestCase):
    """Runs the real bake() on the hermetic inputs of
    test_bake_today_unboundlocal (Supabase, registry and ECR mocked)."""

    def setUp(self):
        self.case = hermetic.BakeTodayUnboundLocalTest()
        self.case.setUp()

    def tearDown(self):
        self.case.tearDown()

    def _bake(self, extra_zero=None):
        zero = (lambda *a, **k: dict(extra_zero)) if extra_zero else None
        real_csv = hermetic._espn_csv

        def espn_csv_with_window(tmpdir):
            # The shared hermetic CSV predates weeks_covered (the ROS window
            # the bake now requires); add it here.
            path = Path(real_csv(tmpdir))
            with path.open(newline="") as f:
                rows = list(csv.DictReader(f))
            with path.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]) + ["weeks_covered"])
                writer.writeheader()
                writer.writerows(dict(r, weeks_covered="5-18") for r in rows)
            return str(path)

        def registry_with_kicker():
            # hermetic._test_registry's two players plus a kicker.
            return hermetic.Registry([
                {"player_key": 777, "id": "u1", "full_name": "Test Player",
                 "position": "QB", "active": True, "team_id": 10},
                {"player_key": 888, "id": "u2", "full_name": "Other Player",
                 "position": "RB", "active": True, "team_id": 20},
                {"player_key": 9001, "id": "u9", "full_name": "Some Kicker",
                 "position": "K", "active": True, "team_id": 10}])

        patches = [patch.object(hermetic, "_test_registry", registry_with_kicker),
                   patch.object(bake_players, "schedule_problems",
                                lambda *a, **k: []),
                   patch.object(hermetic, "_espn_csv", espn_csv_with_window)]
        if zero:
            patches.append(patch.object(bake_players, "espn_zero_universe", zero))
        for p in patches:
            p.start()
        try:
            self.case._run_bake()
        finally:
            for p in patches:
                p.stop()
        return json.loads((bake_players.FIXTURE_DIR / "players.json").read_text())

    def test_bake_writes_no_kdst(self):
        out = self._bake()
        self.assertTrue(out["players"], "the hermetic bake priced no one")
        self.assertEqual({p["pos"] for p in out["players"]} - {"QB", "RB", "WR", "TE"}, set())
        self.assertEqual(sorted(KDST_META & set(out["meta"])), [])

    def test_audit_rejects_a_kdst_row(self):
        # Simulated broken state: a kicker reaches the board.
        kicker = {9001: {"pos": "K", "team": "BUF", "espn_status": "ineligible"}}
        with self.assertRaises(SystemExit) as ctx:
            self._bake(extra_zero=kicker)
        self.assertIn("not carried", str(ctx.exception))

    def test_bake_has_no_kdst_inputs(self):
        src = (ROOT / "pipelines/bake_players.py").read_text(encoding="utf-8")
        self.assertNotIn("--k-json", src)
        self.assertNotIn("--dst-json", src)


class FreshnessHasNoKdstInput(unittest.TestCase):
    def test_chart_inputs(self):
        self.assertNotIn("players.kdst_snapshot", check_reference_freshness.DEFAULT_CHART_INPUT_KEYS)


if __name__ == "__main__":
    unittest.main()
