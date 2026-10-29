#!/usr/bin/env python3
"""JEG-621 (2026-10-29): Fantasy Sharks relay transport and held weekly pull. Hermetic.

Pins: a 403 from fantasysharks.com (what GitHub runners get, GAP-FANTASYSHARKS-CI-BLOCKED)
is retried once through the `fantasysharks-fetch` relay and the relay's status is
kept verbatim; no relay still fails SOURCE_BLOCKED; the relay source is service-role
only and allowlisted to the one projections path; the probe uses the same transport.
Weekly: the Segment comes from the page's own "Week N" label, the snapshot has its
own schema and ranges, and the rest-of-year saver refuses it (never blended).
"""
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
sys.path.insert(0, str(ROOT / "tests"))
import pull_fantasysharks as fs  # noqa: E402
import save_fantasysharks_references as saver  # noqa: E402
import source_probe as sp  # noqa: E402
from test_pull_fantasysharks import csv_body  # noqa: E402

URL = fs.url_for(fs.SCORINGS["half_ppr"], False)
RELAY_SRC = (ROOT / "supabase" / "functions" / "fantasysharks-fetch" / "index.ts").read_text(encoding="utf-8")
NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)

WEEKLY_PAGE = ('<select name="Segment"><option value="877">2026 Rest of Year</option>'
               '<option value="889">Week 7</option>'
               '<option value="890" selected>Week 8</option>'
               '<option value="891">Week 9</option></select>'
               '<select name="Position"><option value="97" selected>All Offense</option></select>'
               '<td>Quarterback projections last updated 10-28</td>')


def direct(status, body="", final=None):
    calls = []

    def go(url):
        calls.append(url)
        return status, final or url, body
    go.calls = calls
    return go


def relay(result):
    calls = []

    def go(url):
        calls.append(url)
        return result
    go.calls = calls
    return go


def weekly_tables(pts=lambda i: (1 + i / 10, 1.5 + i / 10, 2 + i / 10)):
    base, pid = [], 0
    for pos, n in fs.WEEKLY_ROW_FLOORS.items():
        for i in range(n):
            pid += 1
            base.append((pid, f"Last{pos}{i}, Pat", pos, pts(i)))
    return {s: fs.parse_csv(csv_body([(p, n, pos, v[k]) for p, n, pos, v in base]), s)
            for k, s in enumerate(fs.SCORINGS)}


class RelayTransport(unittest.TestCase):
    def test_runner_403_is_retried_through_the_relay(self):
        r = relay((200, "Rank,Player ID\n"))
        self.assertEqual(fs.fetch(URL, direct(403), r), "Rank,Player ID\n")
        self.assertEqual(r.calls, [URL])

    def test_no_relay_still_fails_blocked(self):
        with self.assertRaises(fs.PullError) as cm:
            fs.fetch(URL, direct(403), relay(None))
        self.assertEqual(cm.exception.code, "SOURCE_BLOCKED")
        self.assertIn("relay not configured", str(cm.exception))

    def test_relay_status_is_kept_verbatim(self):
        with self.assertRaises(fs.PullError) as cm:
            fs.fetch(URL, direct(403), relay((403, "denied")))
        self.assertEqual(cm.exception.code, "SOURCE_BLOCKED")
        self.assertIn("relay HTTP 403", str(cm.exception))

    def test_direct_success_and_other_errors_skip_the_relay(self):
        r = relay((200, "x"))
        self.assertEqual(fs.fetch(URL, direct(200, "ok"), r), "ok")
        with self.assertRaises(fs.PullError) as cm:
            fs.fetch(URL, direct(500), r)
        self.assertEqual(cm.exception.code, "SOURCE_BLOCKED")
        self.assertEqual(r.calls, [])

    def test_login_redirect_is_still_blocked(self):
        with self.assertRaises(fs.PullError) as cm:
            fs.fetch(URL, direct(200, "<html>", final="https://www.fantasysharks.com/login"), relay(None))
        self.assertEqual(cm.exception.code, "SOURCE_BLOCKED")

    def test_relay_is_off_without_supabase_env(self):
        saved = {k: os.environ.pop(k, None) for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY")}
        try:
            self.assertIsNone(fs.fetch_via_relay(URL))
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_probe_uses_the_same_relay(self):
        r = relay((200, "relayed"))
        got = sp._sharks_get(lambda u: sp.Resp(403, {}, ""), URL, r)
        self.assertEqual((got.status, got.body), (200, "relayed"))
        self.assertEqual(r.calls, [URL])
        untouched = relay((200, "no"))
        self.assertEqual(sp._sharks_get(lambda u: sp.Resp(200, {}, "direct"), URL, untouched).body, "direct")
        self.assertEqual(untouched.calls, [])


class RelaySource(unittest.TestCase):
    def test_service_role_is_required_before_any_fetch(self):
        self.assertIn('callerRole(req) !== "service_role"', RELAY_SRC)
        self.assertLess(RELAY_SRC.index('callerRole(req) !== "service_role"'), RELAY_SRC.index("await fetch("))

    def test_allowlist_is_the_one_projections_path(self):
        hosts = set(re.findall(r'^\s*"([a-z0-9.-]+)":\s*\[', RELAY_SRC, re.M))
        self.assertEqual({"www.fantasysharks.com"}, hosts)
        self.assertIn(r"/^\/apps\/bert\/forecasts\/projections\.php$/", RELAY_SRC)
        self.assertTrue(fs.BASE.startswith("https://www.fantasysharks.com/apps/bert/forecasts/projections.php"))

    def test_redirects_are_checked_hop_by_hop_and_no_spoofing(self):
        self.assertIn('redirect: "manual"', RELAY_SRC)
        self.assertIn("allowed(new URL(location, target)", RELAY_SRC)
        self.assertIn('"User-Agent": "DataDrivenFootball-ingest/1.0', RELAY_SRC)

    def test_the_puller_names_the_function_and_sends_the_service_key(self):
        src = (ROOT / "pipelines" / "pull_fantasysharks.py").read_text(encoding="utf-8")
        self.assertEqual(fs.RELAY_FUNCTION, "fantasysharks-fetch")
        self.assertIn('os.environ.get("SUPABASE_SERVICE_KEY"', src)
        self.assertIn('"Authorization": "Bearer " + key', src)


class WeeklyPull(unittest.TestCase):
    def test_segment_comes_from_the_week_label(self):
        self.assertEqual(fs.week_segment(WEEKLY_PAGE, 8), 890)
        self.assertEqual(fs.week_segment(WEEKLY_PAGE, 9), 891)
        for html, week in ((WEEKLY_PAGE, 12), (WEEKLY_PAGE.replace("Week", "Wk"), 8)):
            with self.assertRaises(fs.PullError) as cm:
                fs.week_segment(html, week)
            self.assertEqual(cm.exception.code, "SOURCE_LAYOUT")

    def test_page_meta_pins_the_selected_week(self):
        meta = fs.parse_page_meta(WEEKLY_PAGE, date(2026, 10, 29), 890, fs.week_label(8))
        self.assertEqual(meta["vintage_date"], date(2026, 10, 28))
        with self.assertRaises(fs.PullError):                       # week 9 is not the selected period
            fs.parse_page_meta(WEEKLY_PAGE, date(2026, 10, 29), 891, fs.week_label(9))
        with self.assertRaises(fs.PullError):                       # week 8 is not the rest-of-year period
            fs.parse_page_meta(WEEKLY_PAGE, date(2026, 10, 29), 890)

    def test_weekly_snapshot_is_its_own_schema(self):
        meta = {"vintage_date": date(2026, 10, 28), "segment": 890}
        snap = fs.build_snapshot(weekly_tables(), meta, NOW, fs.WEEKLY_MAX_AGE_DAYS, week=8)
        self.assertEqual((snap["schema"], snap["source"], snap["week"], snap["segment"]),
                         (fs.WEEKLY_SCHEMA, fs.WEEKLY_SOURCE, 8, 890))
        self.assertEqual(snap["row_count"], sum(fs.WEEKLY_ROW_FLOORS.values()))
        with self.assertRaises(fs.PullError) as cm:                 # the same rows miss rest-of-year floors
            fs.build_snapshot(weekly_tables(), meta, NOW)
        self.assertEqual(cm.exception.code, "SOURCE_TRUNCATED")

    def test_weekly_range_is_per_week(self):
        meta = {"vintage_date": date(2026, 10, 28)}
        with self.assertRaises(fs.PullError) as cm:
            fs.build_snapshot(weekly_tables(lambda i: (80, 81, 82)), meta, NOW, 8, week=8)
        self.assertEqual(cm.exception.code, "VALUE_RANGE")

    def test_rest_of_year_saver_refuses_a_weekly_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "snapshot.json"
            p.write_text(json.dumps({"schema": fs.WEEKLY_SCHEMA, "vintage_date": "2026-10-28", "week": 8,
                                     "rows": [{"player_name": "Jahmyr Gibbs", "pos": "RB",
                                               "pts": {"half_ppr": 17.0}}]}), encoding="utf-8")
            with self.assertRaises(SystemExit) as cm:
                saver.build_rows(p)
            self.assertIn("rest-of-year projections only", str(cm.exception))
        self.assertEqual(saver.ROS_SCHEMA, fs.SCHEMA)

    def test_pull_weekly_asks_for_the_weekly_segment(self):
        seen = []
        page = WEEKLY_PAGE.replace("10-28", f"{NOW.month}-{NOW.day}")
        csvs = {sid: csv_body([(r["Player ID"], r["Player Name"], r["Position"], r["Pts"]) for r in rows])
                for (scoring, rows), sid in zip(weekly_tables().items(), fs.SCORINGS.values())}

        def fake(url):
            seen.append(url)
            if "csv=1" in url:
                return csvs[int(re.search(r"scoring=(\d+)", url).group(1))]
            return page
        snap = fs.pull_weekly(0, fs.WEEKLY_MAX_AGE_DAYS, 8, fake)
        self.assertEqual(snap["week"], 8)
        self.assertIn("Segment=877", seen[0])                       # page list read first
        self.assertTrue(all("Segment=890" in u for u in seen[1:]), seen)
        self.assertEqual(len(seen), 5)

    def test_cli_weekly_replay(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
            today = datetime.now(timezone.utc).date()
            Path(d, "page.html").write_text(WEEKLY_PAGE.replace("10-28", f"{today.month}-{today.day}"))
            for scoring, rows in weekly_tables().items():
                Path(d, f"{scoring}.csv").write_text(
                    csv_body([(r["Player ID"], r["Player Name"], r["Position"], r["Pts"]) for r in rows]))
            self.assertEqual(fs.main(["--out-dir", out, "--replay-dir", d, "--period", "weekly", "--week", "8"]), 0)
            snap = json.loads(Path(out, "snapshot.json").read_text())
            self.assertEqual((snap["schema"], snap["week"]), (fs.WEEKLY_SCHEMA, 8))
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
            Path(d, "page.html").write_text(WEEKLY_PAGE)
            self.assertEqual(fs.main(["--out-dir", out, "--replay-dir", d, "--period", "weekly", "--week", "12"]), 1)
            self.assertEqual(os.listdir(out), [])


if __name__ == "__main__":
    unittest.main()
