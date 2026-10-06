"""Coverage drops pass only when every dropped player is gone from the live
source for the same combo (Jeremy 2026-10-05). Negative cases prove the
check still holds a real pipeline loss."""
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines"))
import review_comparison_candidate as r  # noqa: E402

LIVE = [{"player": {"name": "Jauan Jennings"}, "value": 900},
        {"player": {"name": "Tyler Higbee"}, "value": 400},
        {"player": {"name": "Jerry Jeudy"}, "value": 0}]


def fake_urlopen(req, timeout=60):
    assert "numTeams=10&ppr=1.0" in req.full_url, req.full_url
    return io.BytesIO(json.dumps(LIVE).encode())


class CoverageLiveVerifyTest(unittest.TestCase):
    def test_genuine_rotation_passes(self):
        # Fixture players the source no longer lists (or lists at 0).
        with mock.patch.object(r.urllib.request, "urlopen", fake_urlopen):
            ok, detail = r.verify_coverage_drop_live(
                "fantasycalc", "full_10_qb1", ["jayden reed", "jerry jeudy"])
        self.assertTrue(ok, detail)

    def test_pipeline_loss_still_holds(self):
        # A dropped player the live source still prices = we lost them.
        with mock.patch.object(r.urllib.request, "urlopen", fake_urlopen):
            ok, detail = r.verify_coverage_drop_live(
                "fantasycalc", "full_10_qb1", ["jayden reed", "jauan jennings"])
        self.assertFalse(ok)
        self.assertIn("jauan jennings", detail)

    def test_fetch_failure_and_empty_drop_fail_closed(self):
        def boom(req, timeout=60):
            raise OSError("network down")
        with mock.patch.object(r.urllib.request, "urlopen", boom):
            self.assertFalse(r.verify_coverage_drop_live("fantasycalc", "full_10_qb1", ["x"])[0])
        self.assertFalse(r.verify_coverage_drop_live("fantasycalc", "full_10_qb1", [])[0])

    def test_source_without_live_api_never_verifies(self):
        self.assertFalse(r.verify_coverage_drop_live("usatoday", "full_12", ["x"])[0])


if __name__ == "__main__":
    unittest.main()
