"""Regression: dist/modules must carry the current comparison fixture (JEG-8).

On 2026-10-01 the served monitor copy dist/modules/comparison-sources-data.json
was stale (built 02:27, no Razzball section) while the app copy and the fixture
were current. `make sync` copied the fixture to the app copy on every deploy but
never to the monitor copy; only a green rebuild-chain run refreshed it, and the
chain was red on a fail-closed review hold.

These tests prove sync_monitor_fixture() overwrites a stale monitor copy with the
fixture's exact bytes, and they are shown to fail when the copy is removed.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import sync_dashboard_artifacts as sync  # noqa: E402

NAME = "comparison-sources-data.json"


class SyncMonitorFixtureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.fixtures = self.tmp / "fixtures"
        self.modules = self.tmp / "dist" / "modules"
        self.fixtures.mkdir(parents=True)

    def test_stale_monitor_copy_is_overwritten_with_the_fixture(self):
        (self.fixtures / NAME).write_bytes(b'{"sources":{"razzball":{}}}')
        self.modules.mkdir(parents=True)
        (self.modules / NAME).write_bytes(b'{"sources":{}}')  # stale: no razzball
        sync.sync_monitor_fixture(self.fixtures, self.modules)
        self.assertEqual((self.fixtures / NAME).read_bytes(), (self.modules / NAME).read_bytes())
        self.assertIn(b"razzball", (self.modules / NAME).read_bytes())

    def test_creates_the_monitor_directory_and_copy_when_absent(self):
        (self.fixtures / NAME).write_bytes(b'{"a":1}')
        target = sync.sync_monitor_fixture(self.fixtures, self.modules)
        self.assertEqual(self.modules / NAME, target)
        self.assertEqual(b'{"a":1}', target.read_bytes())

    def test_missing_fixture_fails_loudly_instead_of_leaving_a_stale_copy(self):
        self.modules.mkdir(parents=True)
        (self.modules / NAME).write_bytes(b"stale")
        with self.assertRaises(FileNotFoundError):
            sync.sync_monitor_fixture(self.fixtures, self.modules)

    def test_main_calls_the_helper(self):
        # main() must wire the helper in, or the monitor copy silently goes stale again.
        source = (ROOT / "pipelines" / "sync_dashboard_artifacts.py").read_text()
        self.assertIn("sync_monitor_fixture(FIXTURES, dist_modules)", source)


if __name__ == "__main__":
    unittest.main()
