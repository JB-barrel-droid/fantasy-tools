"""GAP-LIVE-SCRAPE-STALE: the rebuild chain no longer runs the lineage builder."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipelines"))


class LineageStageRetiredTest(unittest.TestCase):
    # -- Stage 10 retired (GAP-LIVE-SCRAPE-STALE, 2026-10-08) -----------
    #
    # The chain's Stage 10 ran build_source_value_lineage.py on every run. In
    # CI it always failed (no gitignored data/raw snapshots; the Week 4 live
    # scrape aged past 48h) and its output was never committed, so it only
    # logged "Live page scrape artifact is N h old". The three tests that
    # pinned Stage 10's wiring were replaced by this one, which fails on the
    # pre-retirement chain (it invoked the builder).

    def test_chain_no_longer_runs_the_lineage_builder(self):
        import rebuild_comparison_chain as rcc
        from rebuild_comparison_chain import execute_chain
        self.assertFalse(hasattr(rcc, "run_lineage_rebuild"))
        tmp = tempfile.mkdtemp(prefix="gap-live-scrape-")
        try:
            fixdir = Path(tmp) / "data/fixtures/current"
            fixdir.mkdir(parents=True)
            (fixdir / "comparison-sources-data.json").write_text(
                json.dumps({"built_at": "2026-10-02T21:21:44+00:00", "sources": {}}))
            calls = []

            def fake_run(cmd, **kw):
                calls.append(cmd)
                return (True, "ok")
            orig_wcs, orig_wss = rcc.write_chain_status, rcc.write_step_summary
            rcc.write_chain_status = lambda *a, **kw: {"success": True, "outcome": "ok", "held": []}
            rcc.write_step_summary = lambda *a, **kw: None
            try:
                execute_chain(nfl_week=4, repo=tmp, run_fn=fake_run)
            finally:
                rcc.write_chain_status, rcc.write_step_summary = orig_wcs, orig_wss
            self.assertTrue(calls, "the fake chain ran no stages; the test proves nothing")
            lineage_calls = [c for c in calls if "build_source_value_lineage.py" in " ".join(c)]
            self.assertEqual(lineage_calls, [], f"chain still runs the lineage builder: {calls}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
