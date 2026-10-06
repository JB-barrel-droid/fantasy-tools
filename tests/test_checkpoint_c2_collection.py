"""GAP-C2-MTIME: C2 (raw collection) must not read the snapshot file's mtime.

import_supabase_references.py rewrites every snapshot on every run, and a CI
checkout stamps every committed file with the checkout time. Before the fix,
a source with no local pull file fell back to that mtime, so in CI (JEG-414
cutover) a week-old CBS list would read "Pulled 0.0d ago" and C2 went green on
stale data. C2 now uses the Supabase landing time of the latest vintage, or a
committed leg's generated_at, and never the file mtime.
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

import build_pipeline_checkpoints as bpc  # noqa: E402


def _iso(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def old_c2_timestamp(h, pull_path, pull_fetched_at, pull_mtime, repo):
    """Pre-fix C2 timestamp selection, kept verbatim in substance so the
    regression test proves it discriminates."""
    snapshot_path = h.get("snapshot_path")
    snapshot_mtime = None
    if not pull_path and snapshot_path:
        sp = repo / snapshot_path
        if sp.is_file():
            snapshot_mtime = datetime.fromtimestamp(sp.stat().st_mtime, tz=timezone.utc).isoformat()
    return pull_fetched_at or pull_mtime or snapshot_mtime


class C2CollectionTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.repo = Path(self.td.name)
        # Point the module at the temp repo so a reintroduced snapshot-mtime
        # fallback would actually see the freshly written file (mutation-tested).
        self._old_repo, bpc.REPO = bpc.REPO, self.repo
        snap = self.repo / "data/raw/sources/cbs/week-4/snapshot.json"
        snap.parent.mkdir(parents=True)
        snap.write_text("{}")  # freshly (re)written by the importer: mtime = now
        self.stale = {
            "snapshot_path": "data/raw/sources/cbs/week-4/snapshot.json",
            "db_latest_arrived_at": _iso(10),
            "supabase_table": "public.cbs_trade_values",
            "supabase_landing": True,
        }

    def tearDown(self):
        bpc.REPO = self._old_repo
        self.td.cleanup()

    def test_fresh_snapshot_mtime_does_not_make_stale_data_green(self):
        v = bpc.c2_collection_verdict("cbs", self.stale)
        self.assertEqual("warn", v["status"], v)
        self.assertIn("Supabase landing", v["reason"])

    def test_old_selection_would_have_reported_ok(self):
        # Discrimination: the pre-fix rule picks the just-written mtime.
        ts = old_c2_timestamp(self.stale, None, None, None, self.repo)
        self.assertLess(bpc.days_old(ts), 0.1)

    def test_pull_file_still_wins(self):
        v = bpc.c2_collection_verdict("cbs", self.stale, "ops/watchdog/pulls/cbs-x.json", _iso(1), None)
        self.assertEqual("ok", v["status"])
        self.assertIn("ops/watchdog/pulls", v["reason"])

    def test_committed_leg_uses_generated_at_not_checkout_time(self):
        razz = {"supabase_landing": False, "supabase_table": None, "db_latest_arrived_at": None,
                "last_successful_import": _iso(16), "snapshot_path": "data/ddf-two-tier/x/leg.json"}
        self.assertEqual("bad", bpc.c2_collection_verdict("razzball", razz)["status"])

    def test_no_evidence_is_unknown_not_green(self):
        self.assertEqual("unk", bpc.c2_collection_verdict("cbs", {"snapshot_path": "x"})["status"])


if __name__ == "__main__":
    unittest.main()
