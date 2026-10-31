"""JEG-1177: the week-transition rule and the one New York-time calendar.

* weekState/defaultWeek: pipelines/week_state.py and value-model.js return
  the same answer for every case in tests/fixtures/week_state_vectors.json
  (0 / 49 / 50 / 51 / 100% of a setting's DDF Value sources on week N+1,
  plus the edge cases). Exactly 50% stays on week N (Jeremy, 2026-10-27).
* The calendar: "today" is the New York day (nfl_week.today_ny) with an
  injectable clock, so the content week flips at 00:00 Eastern on Tuesday,
  not at 00:00 UTC (Monday evening in Chicago). value_reference.Inputs reads
  the same clock.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import nfl_week  # noqa: E402
import week_state  # noqa: E402

VECTORS = ROOT / "tests" / "fixtures" / "week_state_vectors.json"
VALUE_MODEL = ROOT / "app" / "trade-value-chart" / "assets" / "value-model.js"


def expand(case: dict) -> list[dict]:
    if "entries" in case:
        return case["entries"]
    out, n = [], 0
    for week, count in case["counts"].items():
        for _ in range(count):
            out.append({"source": f"s{n:03d}", "week": None if week == "null" else int(week)})
            n += 1
    return out


def cases() -> list[dict]:
    return json.loads(VECTORS.read_text(encoding="utf-8"))["cases"]


def checked(result: dict, expect: dict) -> dict:
    return {k: result.get(k) for k in expect}


class SharedVectorsTest(unittest.TestCase):
    def test_vectors_cover_the_required_coverage_levels(self):
        names = " | ".join(c["name"] for c in cases())
        for level in ("0%", "49%", "50%", "51%", "100%"):
            self.assertIn(level, names)

    def test_november_transition_vectors_include_unknown_denominator(self):
        """The acceptance replay must exercise 8 -> 9, including unknown inputs."""
        for level in (0, 49, 50, 51, 100):
            with self.subTest(level=level):
                matches = [c for c in cases() if c.get("name") == f"JEG-1176: week 8 to 9 at {level}%"]
                self.assertEqual(len(matches), 1)
                case = matches[0]
                self.assertEqual(case["expect"]["default_week"], 9 if level > 50 else 8)
                self.assertEqual(len(expand(case)), 100)
                if level in (49, 50, 51):
                    self.assertTrue(any(e["week"] is None for e in expand(case)))

    def test_python_matches_the_vectors(self):
        for case in cases():
            with self.subTest(case["name"]):
                got = week_state.week_state(expand(case))
                self.assertEqual(checked(got, case["expect"]), case["expect"])
                self.assertEqual(week_state.default_week(expand(case)), case["expect"]["default_week"])

    def test_js_matches_the_vectors(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        payload = [expand(c) for c in cases()]
        script = ("const vm = require(process.argv[1]);"
                  "const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
                  "process.stdout.write(JSON.stringify(input.map(e => "
                  "({state: vm.weekState(e), dflt: vm.defaultWeek(e)}))));")
        proc = subprocess.run([node, "-e", script, str(VALUE_MODEL)], input=json.dumps(payload),
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        results = json.loads(proc.stdout)
        for case, res in zip(cases(), results):
            with self.subTest(case["name"]):
                self.assertEqual(checked(res["state"], case["expect"]), case["expect"])
                self.assertEqual(res["dflt"], case["expect"]["default_week"])
                # Twins agree on the whole answer, not only the checked fields.
                self.assertEqual(res["state"], week_state.week_state(expand(case)))

    def test_the_guard_discriminates(self):
        """A twin that flips at 50% (>=) fails the vectors."""
        def at_least_half(entries):
            st = week_state.week_state(entries)
            if st["newest"] is not None and 2 * st["on_newest"] >= st["total"]:
                st["default_week"] = st["newest"]
            return st
        bad = [c["name"] for c in cases()
               if checked(at_least_half(expand(c)), c["expect"]) != c["expect"]]
        self.assertTrue(any("50%" in name for name in bad), bad)


class SourceProvenanceTest(unittest.TestCase):
    def test_mixed_sources_keep_their_own_week_and_publication(self):
        fixture = {"built_at": "build-a", "sources": {
            "cbs": {"week_designated": "Week 8", "published_at": "2026-10-28", "fetched_at": "2026-11-03"},
            "espn": {"week_designated": "Week 9", "content_vintage": "2026-11-03"},
            "unknown": {},
        }}
        index = {"fixture_built_at": "build-a", "served": {"cbs": {"week": 8}, "espn": {"week": 9}}}
        got = week_state.source_weeks(fixture, index)
        self.assertEqual((got["cbs"]["served_week"], got["cbs"]["published_at"]), (8, "2026-10-28"))
        self.assertEqual((got["espn"]["served_week"], got["espn"]["published_at"]), (9, "2026-11-03"))
        self.assertIsNone(got["unknown"]["served_week"])
        self.assertIsNone(got["unknown"]["published_at"])


class NewYorkClockTest(unittest.TestCase):
    def tearDown(self):
        nfl_week.set_clock(None)

    def test_monday_night_eastern_is_still_the_old_week(self):
        # Mon 2026-10-26 23:30 EDT = Tue 03:30 UTC: the UTC date already says
        # Tuesday (week 8), the New York day is still Monday (week 7).
        moment = datetime(2026, 10, 27, 3, 30, tzinfo=timezone.utc)
        self.assertEqual(nfl_week.content_week(moment.date()), 8)  # the old UTC reading
        nfl_week.set_clock(moment)
        self.assertEqual(nfl_week.today_ny(), date(2026, 10, 26))
        self.assertEqual(nfl_week.content_week(), 7)

    def test_flip_at_midnight_eastern_tuesday(self):
        nfl_week.set_clock(datetime(2026, 10, 27, 4, 1, tzinfo=timezone.utc))  # 00:01 EDT Tue
        self.assertEqual(nfl_week.content_week(), 8)
        nfl_week.set_clock(datetime(2026, 11, 3, 4, 59, tzinfo=timezone.utc))  # 23:59 EST Mon (DST ended)
        self.assertEqual(nfl_week.content_week(), 8)
        nfl_week.set_clock(datetime(2026, 11, 3, 5, 0, tzinfo=timezone.utc))  # 00:00 EST Tue
        self.assertEqual(nfl_week.content_week(), 9)

    def test_ddf_now_env_injects_the_clock(self):
        with mock.patch.dict(os.environ, {"DDF_NOW": "2026-10-27T03:30:00Z"}):
            self.assertEqual(nfl_week.today_ny(), date(2026, 10, 26))

    def test_naive_clock_is_refused(self):
        nfl_week.set_clock(datetime(2026, 10, 27, 3, 30))
        with self.assertRaises(ValueError):
            nfl_week.today_ny()

    def test_value_reference_reads_the_new_york_clock(self):
        import value_reference as R
        nfl_week.set_clock(datetime(2026, 10, 27, 3, 30, tzinfo=timezone.utc))
        inp = R.Inputs.load()
        self.assertEqual(inp.today, date(2026, 10, 26))
        self.assertEqual(R.freshness(inp)["current_week"], 7)


if __name__ == "__main__":
    unittest.main()
