"""JEG-1377: the Sunday pre-kickoff projection capture fires before kickoff on both sides
of the US DST change, retries, alerts before kickoff, and has a dry run that proves it.

Pins (no network, no database):
  - pg_cron runs in GMT; the capture (15:30 UTC) and the ESPN Sunday run (16:20 UTC) fall
    in the Sunday morning, Central time, before the noon CT main slate on 2026-10-25 (CDT),
    2026-11-01 (the day DST ends) and 2026-11-08 (CST), and in that order around the
    pre-kickoff due time;
  - with --pre-kickoff the current week's Sunday copy is due from Sunday 16:00 UTC, so the
    16:20 UTC run fails on a missing copy; the default (Monday 12:00 UTC) is unchanged;
  - the dry run builds both sources' rows, writes nothing, and fails under a row floor;
  - the capture workflow retries, and the ESPN Sunday run re-runs a missing capture and
    then checks with --pre-kickoff.
"""
import json
import re
import sys
import tempfile
import unittest
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import capture_projections_only as cap  # noqa: E402
import check_projection_captures as chk  # noqa: E402
import projection_capture as pc  # noqa: E402
import save_cbsros_references as sc  # noqa: E402
import save_razzball_references as sr  # noqa: E402

CT = ZoneInfo("America/Chicago")
WORKFLOWS = ROOT / ".github" / "workflows"
CAPTURE_SQL = ROOT / "supabase/migrations/jeg944_source_projection_captures_20261023.sql"
ESPN_SQL = ROOT / "supabase/migrations/jeg521_g4_weekly_store_20261009.sql"
SUNDAYS = ("2026-10-25", "2026-11-01", "2026-11-08")  # CDT, DST ends, CST
MAIN_SLATE_CT = time(12, 0)


def utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def sunday_utc_time(sql: Path, job: str) -> time:
    """The UTC time of a weekly Sunday pg_cron job, read from its migration."""
    m = re.search(rf"'{re.escape(job)}',\s*'(\d+) (\d+) \* \* 0'", sql.read_text())
    assert m, f"{job} schedule not found in {sql.name}"
    return time(int(m.group(2)), int(m.group(1)))


class ScheduleAcrossDstTests(unittest.TestCase):
    capture = sunday_utc_time(CAPTURE_SQL, "projection-capture-sunday")
    espn = sunday_utc_time(ESPN_SQL, "espn-weekly-store-sunday")

    def test_both_runs_are_sunday_morning_ct_before_the_main_slate(self):
        for day in SUNDAYS:
            for t in (self.capture, self.espn):
                local = datetime.combine(datetime.fromisoformat(day).date(), t, tzinfo=timezone.utc).astimezone(CT)
                self.assertEqual(local.date().isoformat(), day, (day, t))
                self.assertGreaterEqual(local.time(), time(8, 0), (day, t, local))
                self.assertLess(local.time(), MAIN_SLATE_CT, (day, t, local))

    def test_dst_moves_the_capture_an_hour_earlier_in_ct_not_later(self):
        before = datetime.combine(datetime(2026, 10, 25).date(), self.capture, tzinfo=timezone.utc).astimezone(CT)
        after = datetime.combine(datetime(2026, 11, 1).date(), self.capture, tzinfo=timezone.utc).astimezone(CT)
        self.assertEqual((before.hour, before.minute), (10, 30))
        self.assertEqual((after.hour, after.minute), (9, 30))

    def test_capture_then_due_time_then_espn_check(self):
        due = (datetime.min + pc.SUNDAY_DUE_PRE_KICKOFF - timedelta(days=5)).time()
        self.assertLess(self.capture, due)
        self.assertLess(due, self.espn)


class PreKickoffDueTests(unittest.TestCase):
    # content week 8 opens Tuesday 2026-10-27; its Sunday is 2026-11-01

    def test_pre_kickoff_requires_this_sundays_copy_from_16_utc(self):
        due = pc.SUNDAY_DUE_PRE_KICKOFF
        self.assertNotIn((8, "sunday"), pc.required_cells(utc("2026-11-01T15:45"), sunday_due=due))
        self.assertIn((8, "sunday"), pc.required_cells(utc("2026-11-01T16:20"), sunday_due=due))

    def test_default_still_waits_for_monday(self):
        self.assertNotIn((8, "sunday"), pc.required_cells(utc("2026-11-01T16:20")))
        self.assertIn((8, "sunday"), pc.required_cells(utc("2026-11-02T12:00")))

    def test_cli_fails_on_a_missing_sunday_copy_at_the_1620_run(self):
        seen = {}
        def fake_counts(_sb, _season, cells):
            seen["cells"] = cells
            return {s: {(wk, ph, h): pc.MIN_ROWS[(s, h)]
                        for wk, ph in cells if ph == "midweek" for h in pc.REQUIRED_HORIZONS[s]}
                    for s in pc.SOURCES}
        saved = pc.fetch_capture_counts
        pc.fetch_capture_counts = fake_counts
        sys.modules.setdefault("sbclient", type(sys)("sbclient"))
        try:
            self.assertEqual(chk.main(["--now", "2026-11-01T16:20:00+00:00"]), 0)
            self.assertEqual(chk.main(["--pre-kickoff", "--now", "2026-11-01T16:20:00+00:00"]), 1)
            self.assertIn((8, "sunday"), seen["cells"])
        finally:
            pc.fetch_capture_counts = saved


class DryRunTests(unittest.TestCase):
    def setUp(self):
        self.saved = (sc.save_captures, sr.save_captures, sr.build_razzball_rows, cap._cbs_resolver)
        def boom(*a, **k):
            raise AssertionError("a dry run must not write")
        sc.save_captures = sr.save_captures = boom
        cap._cbs_resolver = lambda: (lambda name, pos, norm: abs(hash(name)) % 10**6 + 1)

    def tearDown(self):
        sc.save_captures, sr.save_captures, sr.build_razzball_rows, cap._cbs_resolver = self.saved

    def run_dry(self, n_players, *, weekly=True):
        clean = [{"player_key": i + 1, "per_game_standard": 10, "per_game_half_ppr": 11, "per_game_ppr": 12,
                  "games_reported": 9} for i in range(n_players)]
        sr.build_razzball_rows = lambda path: (clean, [], "2026-11-01")
        ros = [{"player_name": f"P{i}", "pos": "RB", "player_norm": f"p{i}", "gp": 9,
                "ros_standard": 90, "ros_half_ppr": 99, "ros_ppr": 108,
                "per_game_standard": 10, "per_game_half_ppr": 11, "per_game_ppr": 12}
               for i in range(n_players)]
        wk = {"weeks": {"9": [{"player_name": f"P{i}", "pos": "RB", "player_norm": f"p{i}", "gp": 1,
                                "points_standard": 9, "points_half_ppr": 10, "points_ppr": 11}
                               for i in range(n_players)]}, "not_offered_weeks": [], "errors": []}
        with tempfile.TemporaryDirectory() as t:
            cbs, rz = Path(t) / "cbs", Path(t) / "rz"
            cbs.mkdir(); rz.mkdir()
            (cbs / "snapshot.json").write_text(json.dumps({"vintage_date": "2026-11-01", "rows": ros}))
            if weekly:
                (cbs / "weekly_snapshot.json").write_text(json.dumps(wk))
            (rz / "snapshot.json").write_text("{}")
            return cap.main(["--cbs", str(cbs), "--razzball", str(rz), "--dry-run"])

    def test_full_pull_passes_and_writes_nothing(self):
        self.assertEqual(self.run_dry(200), 0)  # 200 players x 3 formats = 600 rows a horizon

    def test_short_pull_fails(self):
        self.assertEqual(self.run_dry(50), 1)  # 150 rows, under the floor of 300

    def test_missing_cbs_week_pages_fail(self):
        self.assertEqual(self.run_dry(200, weekly=False), 1)


class WorkflowTests(unittest.TestCase):
    def test_capture_workflow_retries(self):
        wf = (WORKFLOWS / "projection-capture-sunday.yml").read_text()
        self.assertIn("until python3 pipelines/pull_cbs_ros_projections.py", wf)
        self.assertIn('if [ "$attempt" -ge 3 ]', wf)

    def test_espn_sunday_run_backstops_then_checks_pre_kickoff(self):
        wf = (WORKFLOWS / "espn-weekly-store.yml").read_text()
        back = wf.index("Sunday backstop, CBS and Razzball pre-kickoff capture")
        check = wf.index("- name: Check projection captures (JEG-944)")
        self.assertLess(back, check)
        backstop = wf[back:check]
        self.assertIn('"$(date -u +%H)" -lt 16', backstop)
        self.assertIn("capture_projections_only.py", backstop)
        self.assertNotIn("save_cbsros_references.py", backstop)
        self.assertNotIn("save_razzball_references.py", backstop)
        self.assertIn("run: python3 pipelines/check_projection_captures.py --pre-kickoff", wf[check:])


if __name__ == "__main__":
    unittest.main()
