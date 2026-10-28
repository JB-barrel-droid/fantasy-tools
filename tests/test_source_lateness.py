"""JEG-1200 / JEG-1201: what "late" means for each source.

Jeremy, 2026-10-28: "dynamic sources should update daily, and never late for
a week"; "Projection sources update constantly, so they should never be
delayed. So does fantasycalc. Trade chart articles tend to publish at the
same time every week."

Every clock is frozen; nothing here reads the real clock or the network.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import nfl_week  # noqa: E402
import source_lateness as sl  # noqa: E402

UTC = timezone.utc
# Content week 8 opens Tuesday 2026-10-27.
TUE_1100_CT = datetime(2026, 10, 27, 16, 0, tzinfo=UTC)
WED_1159_CT = datetime(2026, 10, 28, 16, 59, tzinfo=UTC)
WED_1201_CT = datetime(2026, 10, 28, 17, 1, tzinfo=UTC)


def fresh(now, *, probe_ago=1, acked_ago=2, same=True, week=None, ok=True):
    """A probe-state row: probed `probe_ago` h ago, last good ingest `acked_ago` h ago."""
    row = {"last_ok": ok, "last_fp": "a" if ok else None, "acked_fp": "a" if same else "b",
           "last_probe_at": (now - timedelta(hours=probe_ago)).isoformat(),
           "acked_at": None if acked_ago is None else (now - timedelta(hours=acked_ago)).isoformat(),
           "last_signals": {"week": week} if week else {}}
    return row


class RulesTest(unittest.TestCase):
    def test_every_probed_source_has_a_rule(self):
        import source_probe
        self.assertEqual(set(sl.RULES), set(source_probe.POLICIES))

    def test_live_and_weekly_are_the_sources_jeremy_named(self):
        live = {s for s, r in sl.RULES.items() if r.kind == "live"}
        weekly = {s for s, r in sl.RULES.items() if r.kind == "weekly"}
        self.assertEqual(live, {"fantasycalc", "espn", "cbsros", "razzball"})
        self.assertEqual(weekly, {"fantasypros", "usatoday", "cbs"})

    def test_weekly_due_is_wednesday_noon_central_before_the_stale_flag(self):
        due = sl.due_at(sl.RULES["cbs"], 8)
        self.assertEqual(due.isoformat(), "2026-10-28T12:00:00-05:00")
        # A day before the JEG-1180 Thursday 12:00 CT stale cutoff.
        self.assertEqual((datetime(2026, 10, 29, 17, 0, tzinfo=UTC) - due).total_seconds(), 86400)

    def test_every_source_refreshes_at_least_daily(self):
        # "dynamic sources should update daily": no source may go more than a
        # day and a half unconfirmed before it is late.
        for src, rule in sl.RULES.items():
            self.assertLessEqual(rule.late_after, timedelta(hours=36), src)


class LiveSourceTest(unittest.TestCase):
    def test_on_time(self):
        r = sl.judge("espn", fresh(WED_1201_CT), 8, WED_1201_CT)
        self.assertFalse(r["late"], r["reasons"])

    def test_unchanged_content_confirmed_by_the_probe_counts_as_current(self):
        # ESPN saved 22 h ago and unchanged since: the 1 h old probe confirms it.
        r = sl.judge("espn", fresh(WED_1201_CT, probe_ago=1, acked_ago=22), 8, WED_1201_CT)
        self.assertFalse(r["late"], r["reasons"])

    def test_a_change_not_saved_for_ten_hours_is_late(self):
        r = sl.judge("espn", fresh(WED_1201_CT, probe_ago=1, acked_ago=10, same=False), 8, WED_1201_CT)
        self.assertTrue(r["late"])
        self.assertIn("last confirmed current 10 hours ago", r["reasons"][0])

    def test_fantasycalc_inside_its_six_hour_save_gap_is_on_time(self):
        r = sl.judge("fantasycalc", fresh(WED_1201_CT, probe_ago=0.5, acked_ago=7, same=False), 8, WED_1201_CT)
        self.assertFalse(r["late"], r["reasons"])

    def test_site_on_last_week_after_tuesday_noon_is_late(self):
        r = sl.judge("razzball", fresh(WED_1201_CT), 7, WED_1201_CT)
        self.assertEqual(r["reasons"], ["the site still shows its week 7 data"])
        # Tuesday 11:00 CT, the switch has not come yet.
        self.assertFalse(sl.judge("razzball", fresh(TUE_1100_CT), 7, TUE_1100_CT)["late"])


class WeeklySourceTest(unittest.TestCase):
    def test_last_weeks_article_before_wednesday_noon_is_on_time(self):
        r = sl.judge("cbs", fresh(WED_1159_CT, week=7), 7, WED_1159_CT)
        self.assertFalse(r["late"], r["reasons"])

    def test_publisher_late_after_wednesday_noon(self):
        r = sl.judge("cbs", fresh(WED_1201_CT, week=7), 7, WED_1201_CT)
        self.assertTrue(r["late"])
        self.assertIn("has not published its week 8 chart", r["reasons"][0])

    def test_article_out_but_site_behind_is_our_lateness(self):
        r = sl.judge("usatoday", fresh(WED_1201_CT, week=8), 7, WED_1201_CT)
        self.assertEqual(r["reasons"], ["its week 8 chart is out but the site still shows week 7"])

    def test_article_out_and_on_site_is_on_time(self):
        self.assertFalse(sl.judge("fantasypros", fresh(WED_1201_CT, week=8), 8, WED_1201_CT)["late"])


class FailureModesTest(unittest.TestCase):
    def test_probes_silent_for_a_day_is_late(self):
        # Oct 20-21, 2026: the probes logged nothing for two days.
        now = datetime(2026, 10, 21, 18, 0, tzinfo=UTC)
        r = sl.judge("usatoday", fresh(now, probe_ago=30, acked_ago=30, week=7), 7, now)
        self.assertIn("its change check has not run for 30 hours", r["reasons"])

    def test_a_source_that_never_saves_is_late(self):
        # FantasySharks, Oct 2026: 403 on every probe, never acknowledged.
        row = fresh(WED_1201_CT, probe_ago=9, acked_ago=None, ok=False)
        row["last_error"] = "fantasysharks page: status=403 "
        r = sl.judge("fantasysharks", row, None, WED_1201_CT)
        self.assertTrue(r["late"])
        self.assertIn("status=403", r["reasons"][0])
        self.assertFalse(r["on_site"])

    def test_no_row_at_all_is_late(self):
        r = sl.judge("espn", None, 8, WED_1201_CT)
        self.assertTrue(r["late"])

    def test_week_one_has_no_previous_week(self):
        now = datetime(2026, 9, 9, 18, 0, tzinfo=UTC)
        r = sl.judge("cbs", fresh(now, week=None), None, now)
        self.assertFalse(r["late"], r["reasons"])


class ServedWeeksTest(unittest.TestCase):
    def test_published_history_wins_over_the_last_chain_run(self):
        history = {"served": {"cbs": {"week": 7}}}
        status = {"source_weeks": {"cbs": {"served_week": 8}, "espn": {"served_week": 8}}}
        self.assertEqual(sl.served_weeks(history, status), {"cbs": 7, "espn": 8})


class FakeGitHub:
    def __init__(self, issues=None):
        self.issues = issues or []
        self.calls = []

    def __call__(self, method, path, token, payload=None):
        self.calls.append((method, path, payload))
        if method == "GET":
            return self.issues
        if method == "POST" and path.endswith("/issues"):
            return {"number": 7}
        return {}


class AlertTest(unittest.TestCase):
    def rep(self, late):
        state = {s: fresh(WED_1201_CT, week=8) for s in sl.RULES}
        if late:
            state[late] = fresh(WED_1201_CT, probe_ago=40, acked_ago=40, week=8)
        history = {"served": {s: {"week": 8} for s in sl.RULES}}
        return sl.report(state, history, {}, WED_1201_CT)

    def test_opens_one_issue(self):
        gh = FakeGitHub()
        self.assertEqual(sl.alert(self.rep("espn"), "o/r", "t", WED_1201_CT, gh), "opened #7")
        made = gh.calls[-1][2]
        self.assertEqual(made["title"], sl.TITLE)
        self.assertEqual(made["labels"], [sl.LABEL])
        self.assertIn("**ESPN**", made["body"])

    def test_quiet_while_nothing_changed(self):
        rep = self.rep("espn")
        issue = {"number": 7, "title": sl.TITLE, "labels": [], "body": sl.body(rep) + "\n" + sl._late_marker(rep),
                 "updated_at": (WED_1201_CT - timedelta(hours=2)).isoformat()}
        gh = FakeGitHub([issue])
        self.assertIn("already open", sl.alert(rep, "o/r", "t", WED_1201_CT, gh))
        self.assertEqual([c[0] for c in gh.calls], ["GET"])

    def test_updates_when_another_source_goes_late(self):
        old = self.rep("espn")
        issue = {"number": 7, "title": sl.TITLE, "labels": [], "body": sl._late_marker(old),
                 "updated_at": (WED_1201_CT - timedelta(hours=1)).isoformat()}
        gh = FakeGitHub([issue])
        self.assertEqual(sl.alert(self.rep("cbs"), "o/r", "t", WED_1201_CT, gh), "updated #7")

    def test_closes_when_every_source_is_on_time(self):
        rep = self.rep(None)
        self.assertEqual(rep["late"], [])
        gh = FakeGitHub([{"number": 7, "title": sl.TITLE, "labels": []}])
        self.assertEqual(sl.alert(rep, "o/r", "t", WED_1201_CT, gh), "closed #7")
        self.assertEqual(gh.calls[-1][2]["state"], "closed")

    def test_dry_run_without_a_token(self):
        self.assertIn("dry run", sl.alert(self.rep("espn"), None, None, WED_1201_CT))


class MainTest(unittest.TestCase):
    def tearDown(self):
        nfl_week.set_clock(None)

    def test_never_fails_the_job(self):
        nfl_week.set_clock(WED_1201_CT)
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "state.json"
            bad.write_text("not json")
            out = Path(td) / "rep.json"
            with contextlib.redirect_stdout(io.StringIO()) as buf, mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GITHUB_TOKEN", None)
                rc = sl.main(["--state-file", str(bad), "--history", str(Path(td) / "none.json"),
                              "--status", str(Path(td) / "none.json"), "--out", str(out), "--alert"])
            self.assertEqual(rc, 0)
            rep = json.loads(out.read_text())
            # No state at all: every source is late, loudly.
            self.assertEqual(set(rep["late"]), set(sl.RULES))
            self.assertIn("::warning title=ESPN late::", buf.getvalue())

    def test_a_crash_is_a_warning(self):
        nfl_week.set_clock(WED_1201_CT)
        with mock.patch.object(sl, "report", side_effect=RuntimeError("boom")), \
                contextlib.redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(sl.main(["--state-file", "/nonexistent"]), 0)
        self.assertIn("not checked", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
