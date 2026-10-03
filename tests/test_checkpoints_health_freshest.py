"""Checkpoint builder must use the freshest valid health input, not a hardcoded path.

2026-10-03: build_checkpoints() read only the gitignored
output/source-import-health.json. A rebuild from a clean worktree (no runtime
file) silently produced "unk" for 30 per-source checkpoints even though a
fresh committed dist copy existed -- the same hardcoded-fallback class as the
2026-10-01 sync_dashboard_artifacts.py fix. The builder now resolves via
import_health_source() (freshest valid of output/, dist/modules/, fixture).
These tests prove the wiring: with REPO pointed at a sandbox, the builder's
exact selection call must return the freshest valid candidate.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
import build_pipeline_checkpoints as bpc  # noqa: E402
from sync_dashboard_artifacts import import_health_source  # noqa: E402


def _health(checked_at):
    return {
        "schema": "trade-value-import-health-v1",
        "checked_at": checked_at,
        "nfl_week": 4,
        "sources": {},
    }


class CheckpointsHealthFreshestTest(unittest.TestCase):
    def _sandbox(self, candidates):
        tmp = Path(tempfile.mkdtemp())
        for rel, checked_at in candidates:
            p = tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(_health(checked_at)))
        return tmp

    def test_builder_selection_prefers_freshest_committed_copy(self):
        tmp = self._sandbox([
            ("dist/modules/source-import-health.json", "2026-10-03T14:37:27Z"),
            ("data/fixtures/current/source-import-health.json", "2026-10-03T09:12:50Z"),
        ])
        old_repo = bpc.REPO
        bpc.REPO = tmp
        try:
            # The exact call build_checkpoints() makes.
            chosen = import_health_source(bpc.REPO)
        finally:
            bpc.REPO = old_repo
        self.assertEqual(chosen, tmp / "dist/modules/source-import-health.json")

    def test_builder_selection_prefers_runtime_when_freshest(self):
        tmp = self._sandbox([
            ("output/source-import-health.json", "2026-10-03T15:00:00Z"),
            ("dist/modules/source-import-health.json", "2026-10-03T14:37:27Z"),
        ])
        old_repo = bpc.REPO
        bpc.REPO = tmp
        try:
            chosen = import_health_source(bpc.REPO)
        finally:
            bpc.REPO = old_repo
        self.assertEqual(chosen, tmp / "output/source-import-health.json")

    def test_invalid_candidates_are_skipped(self):
        tmp = Path(tempfile.mkdtemp())
        bad = tmp / "dist" / "modules" / "source-import-health.json"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text(json.dumps({"schema": "wrong-schema", "checked_at": "2026-10-03T15:00:00Z"}))
        good = tmp / "data" / "fixtures" / "current" / "source-import-health.json"
        good.parent.mkdir(parents=True, exist_ok=True)
        good.write_text(json.dumps(_health("2026-10-03T09:12:50Z")))
        old_repo = bpc.REPO
        bpc.REPO = tmp
        try:
            chosen = import_health_source(bpc.REPO)
        finally:
            bpc.REPO = old_repo
        self.assertEqual(chosen, good)


if __name__ == "__main__":
    unittest.main()
