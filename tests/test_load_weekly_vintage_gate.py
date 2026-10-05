"""JEG-404 regression tests: source-content-vintage gate in the weekly
dashboard loader.

Unit tier: no network, no Supabase. sbclient is stubbed at import time so the
loader module loads on machines without the skill (matches
test_refresh_fantasycalc_supabase.py).
"""

import sys
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "pipelines"))

with patch.dict(sys.modules, {"sbclient": MagicMock(name="sbclient")}):
    import load_weekly_dashboard as loader

ESPN_EXPERT_SOURCE = "espn_ros"


def make_meta(expert_source=ESPN_EXPERT_SOURCE):
    return {
        "season": 2026,
        "week": 5,
        "built_at": "2026-10-05T12:00:00Z",
        "expert_source": expert_source,
        "expert_leg_replaces": "ecr_week4",
        "source_file": "espn_ros.csv",
    }


def make_rows(snapshot="2026-10-04", n=3):
    return {
        f"p{i}": {"player_key": f"p{i}", "espn_snapshot_date": snapshot}
        for i in range(n)
    }


class TestVintageGate(unittest.TestCase):
    def test_fresh_espn_bundle_passes(self):
        today = date(2026, 10, 5)
        rows = make_rows(snapshot="2026-10-03")  # exactly 2 days old
        self.assertIsNone(loader.expert_vintage_block_reason(make_meta(), rows, today=today))

    def test_fresh_edge_exactly_max_age_passes(self):
        today = date(2026, 10, 5)
        rows = make_rows(snapshot="2026-10-02")  # exactly 3 days old
        self.assertIsNone(loader.expert_vintage_block_reason(make_meta(), rows, today=today))

    def test_stale_vintage_blocks(self):
        today = date(2026, 10, 5)
        rows = make_rows(snapshot="2026-10-01")  # 4 days old
        reason = loader.expert_vintage_block_reason(make_meta(), rows, today=today)
        self.assertIsNotNone(reason)
        self.assertIn("2026-10-01", reason)
        self.assertIn("4 days old", reason)

    def test_wrong_expert_source_blocks(self):
        today = date(2026, 10, 5)
        reason = loader.expert_vintage_block_reason(
            make_meta(expert_source="ecr_static"), make_rows(), today=today)
        self.assertIsNotNone(reason)
        self.assertIn("ecr_static", reason)

    def test_missing_expert_source_blocks(self):
        meta = make_meta()
        del meta["expert_source"]
        reason = loader.expert_vintage_block_reason(meta, make_rows(), today=date(2026, 10, 5))
        self.assertIsNotNone(reason)
        self.assertIn("expert_source", reason)

    def test_missing_row_vintage_blocks(self):
        today = date(2026, 10, 5)
        rows = make_rows()
        rows["p0"]["espn_snapshot_date"] = None
        reason = loader.expert_vintage_block_reason(make_meta(), rows, today=today)
        self.assertIsNotNone(reason)
        self.assertIn("p0", reason)

    def test_non_unanimous_vintage_blocks(self):
        today = date(2026, 10, 5)
        rows = make_rows(snapshot="2026-10-04")
        rows["p1"]["espn_snapshot_date"] = "2026-10-03"
        reason = loader.expert_vintage_block_reason(make_meta(), rows, today=today)
        self.assertIsNotNone(reason)
        self.assertIn("not unanimous", reason)

    def test_unparseable_vintage_blocks(self):
        today = date(2026, 10, 5)
        reason = loader.expert_vintage_block_reason(
            make_meta(), make_rows(snapshot="10/04/2026"), today=today)
        self.assertIsNotNone(reason)
        self.assertIn("ISO date", reason)

    def test_future_vintage_passes_gate(self):
        # A same-day/future stamp is not staleness; manifest rollback checks
        # own chronology. Gate must not block on it.
        self.assertIsNone(loader.expert_vintage_block_reason(
            make_meta(), make_rows(snapshot="2026-10-06"), today=date(2026, 10, 5)))


class TestGatePlacementPreservesNoop(unittest.TestCase):
    def test_gate_is_after_noop_in_main_source(self):
        # The gate must not run before the identical-bundle NOOP check, or an
        # already-current stale bundle would false-block instead of no-op.
        with open(loader.__file__, encoding="utf-8") as f:
            src = f.read()
        noop_idx = src.index('print(f"NOOP: season {season}')
        gate_idx = src.index("expert_vintage_block_reason(meta, rows)")
        self.assertLess(noop_idx, gate_idx)


if __name__ == "__main__":
    unittest.main()
