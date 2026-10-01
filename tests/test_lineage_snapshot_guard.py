"""Lineage builder fail-closed regression tests.

2026-10-01: the Pages workflow rebuilds source-value-lineage.json in CI on
every deploy, but the source snapshots live under gitignored data/raw and are
absent there. The builder silently fell back to TRANSFORMED combo natives,
so the served lineage compared live raw values (e.g. FantasyPros Gibbs 75.1)
against transformed values (88.8) and reported 0/25 matches — a monitor
false-red caused by the build environment, not the data.

The builder must now refuse to write when a required snapshot is missing,
so the committed (locally built, correct) artifact survives the deploy.
"""
import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_source_value_lineage",
        REPO / "pipelines" / "build_source_value_lineage.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestLineageSnapshotGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = _load_builder()

    def test_missing_snapshot_refuses_to_build(self):
        """Simulated CI state: no snapshots loadable. The builder must raise
        instead of writing a degraded lineage file. Proves the guard catches
        the 2026-10-01 false-red state."""
        with self.assertRaises(SystemExit) as ctx:
            self.b.require_snapshot_natives(
                {"fantasypros": {}, "usatoday": {}, "fantasycalc": {}}
            )
        self.assertIn("fantasypros", str(ctx.exception))

    def test_partial_snapshot_still_refuses(self):
        """One missing source is enough to refuse — a half-degraded file is
        still a degraded file."""
        with self.assertRaises(SystemExit):
            self.b.require_snapshot_natives(
                {"fantasypros": {"a": 1.0}, "usatoday": {}, "fantasycalc": {"b": 2.0}}
            )

    def test_all_snapshots_present_passes(self):
        """Normal local state: all snapshots loaded, builder may proceed."""
        self.b.require_snapshot_natives(
            {"fantasypros": {"a": 1.0}, "usatoday": {"b": 2.0}, "fantasycalc": {"c": 3.0}}
        )  # must not raise

    @unittest.skipUnless(
        all(
            (REPO / p).exists()
            for p in (
                "data/raw/sources/fantasypros/2026-09-29/snapshot.json",
                "data/raw/sources/usatoday/2026-09-29/snapshot.json",
                "data/raw/sources/fantasycalc/week-4/snapshot.json",
            )
        ),
        "source snapshots are gitignored and absent (e.g. CI)",
    )
    def test_real_snapshots_satisfy_guard(self):
        """The actual local snapshots must satisfy the guard, or no local
        build could ever run. Skipped where snapshots are absent (CI): the
        guard's whole purpose is that CI lacks them."""
        natives = {
            src: self.b.load_snapshot_natives(src)
            for src in ("fantasypros", "usatoday", "fantasycalc")
        }
        for src, n in natives.items():
            self.assertTrue(n, f"expected local snapshot natives for {src}")
        self.b.require_snapshot_natives(natives)  # must not raise


if __name__ == "__main__":
    unittest.main()
