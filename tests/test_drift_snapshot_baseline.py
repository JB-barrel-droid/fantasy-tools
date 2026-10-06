"""JEG-426: the drift check must compare live values against the baseline it
is given (CI passes the snapshot freshly imported from Supabase), not the
committed Week-4 file. Before JEG-426 check_drift() always read the
hard-coded data/raw/sources/fantasycalc/week-4/snapshot.json.
"""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import check_fantasycalc_drift as D  # noqa: E402

LIVE = {f"Player {i}": 1000.0 + i for i in range(30)}


def snapshot(path, scale):
    rows = [{"player_name": n, "scoring": "half_ppr", "teams": 12, "native_value": v * scale}
            for n, v in LIVE.items()]
    path.write_text(json.dumps({"rows": rows}))


class DriftBaselineTest(unittest.TestCase):
    def run_main(self, argv):
        out = io.StringIO()
        with mock.patch.object(D, "fetch_live", return_value=dict(LIVE)), \
                mock.patch.object(sys, "argv", ["check_fantasycalc_drift.py"] + argv), \
                redirect_stdout(out), redirect_stderr(io.StringIO()):
            try:
                rc = D.main()
            except SystemExit as e:
                rc = e.code
        return rc, out.getvalue()

    def test_given_baseline_is_the_one_compared(self):
        with TemporaryDirectory() as tmp:
            fresh, stale = Path(tmp, "fresh.json"), Path(tmp, "stale.json")
            snapshot(fresh, 1.0)
            snapshot(stale, 0.8)   # every player 25% below live
            with mock.patch.object(D, "SNAPSHOT_PATH", stale):
                self.assertEqual(0, self.run_main(["--snapshot", str(fresh)])[0])
                # Negative: without --snapshot the (stale) default is used and drift shows.
                self.assertEqual(1, self.run_main([])[0])

    def test_trigger_cannot_target_an_imported_baseline(self):
        with TemporaryDirectory() as tmp:
            fresh = Path(tmp, "fresh.json")
            snapshot(fresh, 1.0)
            rc, _ = self.run_main(["--trigger", "--snapshot", str(fresh)])
            self.assertEqual(2, rc)


if __name__ == "__main__":
    unittest.main()
