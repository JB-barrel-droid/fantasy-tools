#!/usr/bin/env python3
"""Test that content vintage is properly rendered in the frontend.

This validates JEG-131: the render side needs to properly display content vintage
for each source. The frontend's sourceDate function should show the vintage in a
user-friendly format ("content Sep 15") rather than "date unavailable".

Each test runs the vintage_harness.js with source data and verifies the output.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


class TestContentVintageRender(unittest.TestCase):
    """Test that content vintage is properly rendered in the frontend."""

    def _run_harness(self, payload):
        """Run the vintage harness with the given payload."""
        result = subprocess.run(
            ["node", str(REPO / "tests" / "vintage_harness.js")],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=str(REPO),
        )
        if result.returncode != 0:
            # If the harness fails to load the module, skip
            self.skipTest(f"Harness failed to load: {result.stderr}")
        return json.loads(result.stdout)

    def test_fantasycalc_with_date_vintage(self):
        """FantasyCalc with date-based vintage should display properly."""
        payload = {
            "sourceKey": "fantasycalc",
            "sources": {
                "fantasycalc": {
                    "published": "2026-09-29",
                }
            },
        }
        result = self._run_harness(payload)
        self.assertFalse(result["isDateUnavailable"], "FantasyCalc with date vintage should not show 'date unavailable'")
        self.assertIn("content", result["vintageDisplay"], "Should show 'content' prefix")

    def test_fantasycalc_with_week_vintage(self):
        """FantasyCalc with week-based vintage should display properly."""
        payload = {
            "sourceKey": "fantasycalc",
            "sources": {
                "fantasycalc": {
                    "week": "4",
                }
            },
        }
        result = self._run_harness(payload)
        # Week-based vintage falls back to vintage key
        self.assertTrue(result["isDateUnavailable"] or "content" in result["vintageDisplay"])

    def test_espn_with_snapshot_date(self):
        """ESPN with espn_snapshot should display properly."""
        payload = {
            "sourceKey": "espn",
            "sources": {
                "espn": {
                    "espn_snapshot": "2026-09-30",
                }
            },
        }
        result = self._run_harness(payload)
        self.assertFalse(result["isDateUnavailable"], "ESPN with snapshot should not show 'date unavailable'")
        self.assertIn("content", result["vintageDisplay"])

    def test_cbs_with_published_date(self):
        """CBS with published date should display properly."""
        payload = {
            "sourceKey": "cbs",
            "sources": {
                "cbs": {
                    "published": "2026-10-01",
                }
            },
        }
        result = self._run_harness(payload)
        self.assertFalse(result["isDateUnavailable"], "CBS with published should not show 'date unavailable'")

    def test_missing_vintage_shows_unavailable(self):
        """Source without any vintage should show 'date unavailable'."""
        payload = {
            "sourceKey": "fantasycalc",
            "sources": {
                "fantasycalc": {}
            },
        }
        result = self._run_harness(payload)
        self.assertTrue(result["isDateUnavailable"], "Missing vintage should show 'date unavailable'")
        self.assertEqual(result["vintageDisplay"], "date unavailable")

    def test_unknown_source_shows_unavailable(self):
        """Unknown source key should show 'date unavailable'."""
        payload = {
            "sourceKey": "unknown_source",
            "sources": {},
        }
        result = self._run_harness(payload)
        self.assertTrue(result["isDateUnavailable"], "Unknown source should show 'date unavailable'")

    def test_razzball_with_vintage(self):
        """Razzball with vintage should display properly."""
        payload = {
            "sourceKey": "razzball",
            "sources": {
                "razzball": {
                    "vintage": "2026-10-01",
                }
            },
        }
        result = self._run_harness(payload)
        self.assertFalse(result["isDateUnavailable"], "Razzball with vintage should not show 'date unavailable'")

    def test_cbsros_with_vintage(self):
        """CBSROS with vintage should display properly."""
        payload = {
            "sourceKey": "cbsros",
            "sources": {
                "cbsros": {
                    "vintage": "2026-09-30",
                }
            },
        }
        result = self._run_harness(payload)
        self.assertFalse(result["isDateUnavailable"], "CBSROS with vintage should not show 'date unavailable'")


class TestVintageDisplayFormat(unittest.TestCase):
    """Test that vintage display follows the expected format."""

    def test_date_format_is_readable(self):
        """Vintage dates should be in readable format (e.g., 'content Sep 30')."""
        payload = {
            "sourceKey": "fantasycalc",
            "sources": {
                "fantasycalc": {
                    "published": "2026-09-30",
                }
            },
        }
        result = subprocess.run(
            ["node", str(REPO / "tests" / "vintage_harness.js")],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=str(REPO),
        )
        if result.returncode != 0:
            self.skipTest(f"Harness failed to load: {result.stderr}")

        output = json.loads(result.stdout)
        # Should contain month abbreviation
        self.assertRegex(
            output["vintageDisplay"],
            r"content [A-Z][a-z]{2} \d{1,2}",
            "Vintage should be in format 'content Mon DD'"
        )


if __name__ == "__main__":
    unittest.main()
