"""The FantasyCalc live drift verification must query the combo's own
league size and scoring (2026-10-05: a fixed 12-team half-PPR URL made every
10-team full-PPR candidate fail live verification, 19/25)."""
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines"))
import review_comparison_candidate as r  # noqa: E402

LIVE_BY_URL = {
    # 10-team full PPR live values == candidate natives -> should verify.
    "numTeams=10&ppr=1.0": [{"player": {"name": f"Player {i}"}, "value": 1000 - i} for i in range(30)],
    # 12-team half PPR live values differ by 20% -> would fail if queried.
    "numTeams=12&ppr=0.5": [{"player": {"name": f"Player {i}"}, "value": (1000 - i) * 1.2} for i in range(30)],
}


def fake_urlopen(req, timeout=60):
    url = req.full_url
    for key, payload in LIVE_BY_URL.items():
        if key in url:
            return io.BytesIO(json.dumps(payload).encode())
    raise AssertionError(f"unexpected URL {url}")


class LiveVerifyComboTest(unittest.TestCase):
    def setUp(self):
        self.natives = {f"player {i}": float(1000 - i) for i in range(30)}

    def test_url_follows_combo(self):
        self.assertIn("numTeams=10&ppr=1.0", r.live_api_url("fantasycalc", "full_10_qb2"))
        self.assertIn("numTeams=8&ppr=0", r.live_api_url("fantasycalc", "standard_8_qb1"))
        self.assertIn("numQbs=1", r.live_api_url("fantasycalc", "full_10_qb2"))

    def test_ten_team_full_ppr_candidate_verifies_against_matching_live(self):
        with mock.patch.object(r.urllib.request, "urlopen", fake_urlopen):
            ok, detail = r.verify_top25_live("fantasycalc", self.natives, "full_10_qb1")
        self.assertTrue(ok, detail)

    def test_wrong_live_values_still_fail_closed(self):
        # Negative: the same candidate checked against a mismatching live
        # combo (what the fixed URL did) must not verify.
        with mock.patch.object(r.urllib.request, "urlopen", fake_urlopen):
            ok, _ = r.verify_top25_live("fantasycalc", self.natives, "half_12_qb1")
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
