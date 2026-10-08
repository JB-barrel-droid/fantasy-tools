#!/usr/bin/env python3
"""Test that content_vintage is rendered correctly on the trade value chart page.

JEG-131 R4b: The render half. Validates:
- Per-source date display reads content_vintage (not the four-way fallback)
- Per-source badge is a state (green/amber/red), not constant "Live"
- Top "As of" shows oldest displayed content_vintage, not built_at
- "Hidden: N invalid rows" line from hidden_invalid_rows (defensive: missing → 0)

The full headless-Chromium rendered tests (A-E) require a browser; the reviewer
runs those. These tests validate the JS logic and HTML structure directly.
"""

import json
import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO / "app" / "trade-value-chart" / "index.html"


def get_html():
    return INDEX_HTML.read_text()


def extract_badge_js():
    """Extract the JEG-131 badge logic JS for Node testing."""
    src = get_html()
    start = src.find("const PUBLICATION_SCHEDULES=")
    end = src.find("// JEG-131 R4b: Get current NFL week")
    assert start > 0 and end > start, "JEG-131 badge JS not found in index.html"
    return src[start:end]


def run_badge_test(key, vintage, week):
    """Run vintageBadgeState via Node and return the result."""
    js = extract_badge_js()
    test_js = js + f"""
const r = vintageBadgeState("{key}", {{content_vintage: "{vintage}"}}, {week});
console.log(JSON.stringify(r));
"""
    result = subprocess.run(
        ["node", "-e", test_js],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"Node failed: {result.stderr}"
    return json.loads(result.stdout)


class TestContentVintageRender(unittest.TestCase):
    """JEG-131 R4b render tests."""

    def test_date_display_reads_content_vintage(self):
        """Per-source date display prioritizes content_vintage over fallback."""
        src = get_html()
        # The contentDate must read content_vintage FIRST
        pattern = r'const contentDate=String\(source\.content_vintage\|\|source\.published'
        self.assertRegex(
            src, pattern,
            "Date display must read source.content_vintage before the fallback chain"
        )

    def test_no_constant_live_badge(self):
        """No hardcoded 'Live' badge remains; badge is dynamic from vintageBadgeState."""
        src = get_html()
        # The old template had <span class="dataset-badge">Live</span> hardcoded
        # New template uses ${esc(badge.label)}
        self.assertNotIn(
            '<span class="dataset-badge">Live</span>',
            src,
            "Constant 'Live' badge must be replaced with dynamic badge.label"
        )
        self.assertIn(
            "${esc(badge.label)}",
            src,
            "Badge must render the dynamic label from vintageBadgeState"
        )

    def test_badge_state_green_current_week(self):
        """Test A: CBS content_vintage 'Week 4' (current) → green 'Week 4'."""
        r = run_badge_test("cbs", "Week 4", 4)
        self.assertEqual(r["label"], "Week 4")
        self.assertEqual(r["cls"], "status-live")  # green (default styling)

    def test_badge_state_amber_one_behind(self):
        """Test B: CBS one week behind → amber 'Week 3', never 'Live'."""
        r = run_badge_test("cbs", "Week 3", 4)
        self.assertEqual(r["label"], "Week 3")
        self.assertEqual(r["cls"], "status-caution")  # amber
        self.assertNotIn("Live", r["label"])

    def test_badge_state_red_stale(self):
        """Test B (red): CBS much older → red 'STALE'."""
        r = run_badge_test("cbs", "Week 1", 4)
        self.assertIn("STALE", r["label"])
        self.assertEqual(r["cls"], "status-stale")

    def test_badge_state_no_rule(self):
        """Test E: Source with no publication rule → 'no freshness rule' (never green)."""
        r = run_badge_test("unknown_source", "Week 4", 4)
        self.assertEqual(r["label"], "no freshness rule")
        # Must not be green
        self.assertNotEqual(r["cls"], "status-live")

    def test_as_of_uses_oldest_vintage(self):
        """Test D: Top 'As of' reads oldest displayed content_vintage, not built_at."""
        src = get_html()
        # Must compute from vintages, not directly from built_at
        self.assertIn("oldestVintage", src,
                      "As of must compute from oldest displayed vintage")
        # The old code was: document.getElementById("asOfDate").textContent=monthDayTime(data.built_at);
        # New code must NOT unconditionally use built_at
        old_pattern = r'document\.getElementById\("asOfDate"\)\.textContent=monthDayTime\(data\.built_at\);'
        # Allow built_at as fallback, but not as the primary
        matches = re.findall(old_pattern, src)
        # If found, it must be in a fallback context (ternary with oldestVintage)
        if matches:
            self.assertIn("oldestVintage?", src,
                          "built_at must only be a fallback when no vintage available")

    def test_hidden_rows_line(self):
        """Test C: 'Hidden: N invalid rows' from hidden_invalid_rows (defensive)."""
        src = get_html()
        self.assertIn("hidden_invalid_rows", src,
                      "Must read hidden_invalid_rows from source data")
        self.assertIn("Hidden", src,
                      "Must render 'Hidden' line for invalid rows")
        # Defensive: missing → 0, never crash
        self.assertRegex(
            src,
            r"Number\(source\.hidden_invalid_rows\|\|0\)",
            "Must handle missing hidden_invalid_rows defensively"
        )


if __name__ == "__main__":
    unittest.main()
