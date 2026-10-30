"""JEG-1178 (part of JEG-1176): the week selector's stale deadline, with no browser.

A source still on week N-1 is flagged stale once Central time is past Thursday 12:00 of content
week N (product-data.js pastThursdayNoon). Both clocks are pinned per case (TRADE_VALUE_NOW, an
instant, and TRADE_VALUE_TODAY, a day); the real clock is never read. The cases straddle the
boundary in daylight time (week 8, Thursday 2026-10-29, CDT) and in standard time (week 10,
Thursday 2026-11-12, CST, after the 2026-11-01 change), so a fixed UTC offset or a UTC reading
fails. The browser checks of the same rule (badge text at 390 and 1366x768) are in
tests/test_week_selector_render.py.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "source_freshness_harness.js"

# (label, case, expected)
CASES = [
    ("week 8 Wed 23:59 CDT", {"week": 8, "now": "2026-10-29T04:59:00Z"}, False),
    ("week 8 Thu 08:00 CDT (13:00 UTC)", {"week": 8, "now": "2026-10-29T13:00:00Z"}, False),
    ("week 8 Thu 11:59 CDT", {"week": 8, "now": "2026-10-29T16:59:00Z"}, False),
    ("week 8 Thu 12:00 CDT exactly", {"week": 8, "now": "2026-10-29T17:00:00Z"}, False),
    ("week 8 Thu 12:01 CDT", {"week": 8, "now": "2026-10-29T17:01:00Z"}, True),
    ("week 8 Thu 22:00 CDT (Fri UTC)", {"week": 8, "now": "2026-10-30T03:00:00Z"}, True),
    ("week 8 the next Tuesday", {"week": 8, "now": "2026-11-03T15:00:00Z"}, True),
    ("week 10 Thu 11:30 CST (12:30 CDT)", {"week": 10, "now": "2026-11-12T17:30:00Z"}, False),
    ("week 10 Thu 12:00 CST exactly", {"week": 10, "now": "2026-11-12T18:00:00Z"}, False),
    ("week 10 Thu 12:01 CST", {"week": 10, "now": "2026-11-12T18:01:00Z"}, True),
    # A page pinned only to a day reads that day from midnight.
    ("day pin: the Thursday itself", {"week": 8, "today": "2026-10-29"}, False),
    ("day pin: the Friday", {"week": 8, "today": "2026-10-30"}, True),
    ("day pin: the Wednesday", {"week": 8, "today": "2026-10-28"}, False),
    # The instant wins over the day when both are pinned.
    ("instant over day", {"week": 8, "now": "2026-10-29T17:01:00Z", "today": "2026-10-28"}, True),
    # No week, no deadline.
    ("week 0", {"week": 0, "now": "2026-12-31T00:00:00Z"}, False),
    ("week missing", {"week": None, "now": "2026-12-31T00:00:00Z"}, False),
]

# Simulated broken implementations: each must turn at least one case red.
MUTATIONS = {
    "reads UTC, not Central": [('timeZone: "America/Chicago", year', 'timeZone: "UTC", year')],
    "noon counts as past noon": [("minutes > 12 * 60", "minutes >= 12 * 60")],
    "Friday, not Thursday": [("((week - 1) * 7 + 2) * DAY_MS", "((week - 1) * 7 + 3) * DAY_MS")],
    "day pin reads as end of day": [("      minutes = 0;\n", "      minutes = 24 * 60;\n")],
}


def run(mutations=None):
    payload = {"cmd": "stale", "cases": [case for _, case, _ in CASES], "mutations": mutations or []}
    proc = subprocess.run(["node", str(HARNESS)], input=json.dumps(payload).encode(),
                          capture_output=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError(f"harness failed ({proc.returncode}): {proc.stderr.decode()[:800]}")
    return json.loads(proc.stdout.decode())["results"]


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class StaleDeadlineTest(unittest.TestCase):
    def test_thursday_noon_central_boundary(self):
        results = run()
        for (label, _, expected), got in zip(CASES, results):
            with self.subTest(label):
                self.assertIs(got, expected)

    def test_each_broken_deadline_is_caught(self):
        want = [expected for _, _, expected in CASES]
        for name, mutation in MUTATIONS.items():
            with self.subTest(name):
                self.assertNotEqual(run(mutation), want, f"mutation not caught: {name}")


if __name__ == "__main__":
    unittest.main()
