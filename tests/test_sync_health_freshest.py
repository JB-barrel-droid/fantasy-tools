"""Regression: CI sync must not serve a stale health file over a fresh pushed one.

On 2026-10-01 the 30-min cron pushed dist/modules/source-import-health.json
stamped 10:07:07Z, but the Pages deploy workflow's `make sync` in CI (where the
gitignored output/ runtime file is absent) fell back to the committed fixture
data/fixtures/current/source-import-health.json stamped 08:37:08Z and
OVERWROTE the fresh pushed copy. The served monitor read 08:37Z while main
held 10:07Z.

import_health_source() now picks the freshest valid candidate (runtime > dist >
fixture by checked_at). These tests prove the fix against the simulated broken
state: a stale fixture + a fresh dist copy must resolve to the dist copy, and
a stale dist + fresh fixture must resolve to the fixture.
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from sync_dashboard_artifacts import import_health_source  # noqa: E402


def _write_health(root: Path, rel: str, checked_at: str, *, schema_ok=True) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"checked_at": checked_at}
    payload["schema"] = "trade-value-import-health-v1" if schema_ok else "wrong-schema"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _broken_state(root: Path) -> None:
    # CI-like broken state: no gitignored runtime output, stale committed
    # fixture, but the pushed dist copy is fresh.
    _write_health(root, "data/fixtures/current/source-import-health.json",
                  "2026-10-01T08:37:08Z")
    _write_health(root, "dist/modules/source-import-health.json",
                  "2026-10-01T10:07:07Z")


class ImportHealthFreshestTest(unittest.TestCase):
    def test_stale_fixture_does_not_beat_fresh_dist(self):
        """The exact 2026-10-01 failure: fixture must not overwrite the fresh dist copy."""
        with TemporaryDirectory() as td:
            root = Path(td)
            _broken_state(root)
            chosen = import_health_source(root)
            self.assertEqual(
                chosen,
                root / "dist" / "modules" / "source-import-health.json",
                "stale fixture (08:37Z) must not win over the fresh pushed dist copy (10:07Z)",
            )

    def test_fresh_fixture_still_wins_over_stale_dist(self):
        """Freshest-wins is symmetric: a stale dist copy must not pin an older file."""
        with TemporaryDirectory() as td:
            root = Path(td)
            _write_health(root, "data/fixtures/current/source-import-health.json",
                          "2026-10-01T10:37:05Z")
            _write_health(root, "dist/modules/source-import-health.json",
                          "2026-10-01T08:37:08Z")
            chosen = import_health_source(root)
            self.assertEqual(
                chosen,
                root / "data" / "fixtures" / "current" / "source-import-health.json",
            )

    def test_runtime_still_wins_when_present(self):
        """Local runs keep their existing behavior: freshest runtime file wins."""
        with TemporaryDirectory() as td:
            root = Path(td)
            _broken_state(root)
            _write_health(root, "output/source-import-health.json",
                          "2026-10-01T10:37:05Z")
            chosen = import_health_source(root)
            self.assertEqual(
                chosen, root / "output" / "source-import-health.json")

    def test_invalid_payloads_are_skipped_fail_closed(self):
        """Malformed or wrong-schema candidates never get selected."""
        with TemporaryDirectory() as td:
            root = Path(td)
            dist = root / "dist" / "modules" / "source-import-health.json"
            dist.parent.mkdir(parents=True, exist_ok=True)
            dist.write_text("{not valid json", encoding="utf-8")
            _write_health(root, "data/fixtures/current/source-import-health.json",
                          "2026-10-01T08:37:08Z", schema_ok=False)
            _write_health(root, "output/source-import-health.json",
                          "2026-10-01T10:37:05Z")
            chosen = import_health_source(root)
            self.assertEqual(
                chosen, root / "output" / "source-import-health.json")


if __name__ == "__main__":
    unittest.main()
