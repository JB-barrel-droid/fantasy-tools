"""JEG-944: the append-only forward-projection capture.

Pins, on hand-built inputs (no network, no database):
  - ESPN captures every unplayed week, three formats, and no ROS rows;
  - CBS captures ROS plus each offered week; Razzball captures ROS only;
  - the write is first-one-wins (ignore-duplicates on the unique key) and a
    horizon already stored for the content week is not written again;
  - a pull page that answers with a different week is "not offered", not data;
  - the completeness check fails on a missing week, a short capture, and a
    source that never captured, and passes on a complete set;
  - the backfill turns week-history files into ROS rows and nothing else;
  - the migration keeps the unique key, the horizon/week rule and the
    append-only trigger the writers rely on.
Each guard is run once against a simulated broken state and must fail there.
"""
import json
import re
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import backfill_projection_captures as bf  # noqa: E402
import check_projection_captures as chk  # noqa: E402
import projection_capture as pc  # noqa: E402
import pull_cbs_ros_projections as cbs_pull  # noqa: E402
import save_espn_weekly as sv  # noqa: E402

MIGRATION = ROOT / "supabase/migrations/jeg944_source_projection_captures_20261023.sql"
NOW = "2026-10-27T12:00:00+00:00"


class StubIndex:
    def resolve_espn(self, espn_id, name, pos):
        if espn_id == "bad":
            return None, "unmatched"
        return {"id": f"u{espn_id}", "player_key": int(espn_id)}, "id"


class FakeSb:
    def __init__(self, stored=()):
        self.posts, self.stored = [], set(stored)

    def get(self, table, params=""):
        m = re.search(r"source=eq\.(\w+).*source_week=eq\.(\d+).*horizon=eq\.(\w+)", params)
        off = int(re.search(r"offset=(\d+)", params).group(1))
        return [{"id": 1}] if (m.group(1), int(m.group(2)), m.group(3)) in self.stored and off == 0 else []

    def post(self, table, body, params="", prefer=""):
        self.posts.append((table, list(body), params, prefer))


def espn_row(pid, week, rec=4):
    return {"espn_id": pid, "name": f"P{pid}", "pos": "WR", "week": week, "season": 2026,
            "stats": {"receptions": rec, "receiving_yards": 50}}


class EspnCaptureTests(unittest.TestCase):
    def test_every_future_week_three_formats_no_ros(self):
        rows = [espn_row("1", w) for w in range(5, 19)] + [espn_row("bad", 8)]
        out, rep = sv.plan_captures(rows, StubIndex(), set(range(8, 19)), 2026, 8, NOW, "b")
        self.assertEqual({r["target_week"] for r in out}, set(range(8, 19)))
        self.assertEqual(len(out), 11 * 3)
        self.assertEqual({r["horizon"] for r in out}, {"week"})
        self.assertEqual({r["scoring_format"] for r in out}, set(pc.FORMATS))
        self.assertEqual(rep["unresolved_rows"], 1)
        ppr = [r for r in out if r["target_week"] == 9 and r["scoring_format"] == "full_ppr"][0]
        std = [r for r in out if r["target_week"] == 9 and r["scoring_format"] == "standard"][0]
        self.assertGreater(ppr["points"], std["points"])

    def test_next_week_only_would_be_caught(self):
        # the old behaviour (next unplayed week only) must fail the every-week pin
        out, _ = sv.plan_captures([espn_row("1", w) for w in range(8, 19)], StubIndex(),
                                  {8}, 2026, 8, NOW, "b")
        self.assertNotEqual({r["target_week"] for r in out}, set(range(8, 19)))


class SourceBuilderTests(unittest.TestCase):
    def test_cbs_ros_and_offered_weeks(self):
        ros = [{"player_name": "A", "pos": "RB", "player_norm": "a", "gp": 10,
                "ros_standard": 100, "ros_half_ppr": 120, "ros_ppr": 140,
                "per_game_standard": 10, "per_game_half_ppr": 12, "per_game_ppr": 14},
               {"player_name": "ZZ", "pos": "RB", "player_norm": "zz", "gp": 1}]
        weekly = {"weeks": {"8": [{"player_name": "A", "pos": "RB", "player_norm": "a", "gp": 1,
                                   "points_standard": 9, "points_half_ppr": 10, "points_ppr": 11}]},
                  "not_offered_weeks": [9, 10], "errors": []}
        resolve = lambda n, p, norm: 5 if n == "A" else None  # noqa: E731
        rows, rep = pc.cbs_capture_rows(ros, weekly, resolve, season=2026, source_week=7,
                                        capture_at=NOW, batch_id="b", vintage="2026-10-27")
        self.assertEqual({(r["horizon"], r["target_week"]) for r in rows}, {("ros", 0), ("week", 8)})
        self.assertEqual(len(rows), 6)
        self.assertEqual(rep["unresolved"], 1)
        self.assertEqual(rep["not_offered_weeks"], [9, 10])
        ppr = [r for r in rows if r["horizon"] == "ros" and r["scoring_format"] == "full_ppr"][0]
        self.assertEqual((ppr["points"], ppr["ppg"], ppr["games"]), (140, 14, 10))

    def test_razzball_is_ros_only_per_game(self):
        clean = [{"player_key": 3, "per_game_standard": 8.1, "per_game_half_ppr": 9.0,
                  "per_game_ppr": None, "games_reported": 11}]
        rows = pc.razzball_capture_rows(clean, season=2026, source_week=7, capture_at=NOW,
                                        batch_id="b", vintage="2026-10-26")
        self.assertEqual({r["horizon"] for r in rows}, {"ros"})
        self.assertEqual(sorted(r["scoring_format"] for r in rows), ["half_ppr", "standard"])
        self.assertTrue(all(r["points"] is None and r["games"] == 11 for r in rows))

    def test_capture_row_refuses_bad_input(self):
        base = dict(source="espn", season=2026, source_week=7, capture_at=NOW, horizon="week",
                    target_week=8, player_key=1, scoring_format="standard", basis="x",
                    batch_id="b", points=1)
        pc.capture_row(**base)
        for bad in ({"source": "fp"}, {"scoring_format": "ppr"}, {"points": None}):
            with self.assertRaises(ValueError):
                pc.capture_row(**{**base, **bad})


class WriteRuleTests(unittest.TestCase):
    def rows(self, n, horizon="week"):
        return [pc.capture_row(source="espn", season=2026, source_week=7, capture_at=NOW,
                               horizon=horizon, target_week=8 if horizon == "week" else 0,
                               player_key=i, scoring_format="standard", points=1.0, basis="x",
                               batch_id="b") for i in range(n)]

    def test_append_with_ignore_duplicates_on_the_key(self):
        sb = FakeSb()
        self.assertEqual(pc.write_capture(sb, self.rows(3) + self.rows(3)), 3)
        _t, body, params, prefer = sb.posts[0]
        self.assertEqual(len(body), 3)
        self.assertIn("on_conflict=" + pc.CONFLICT, params)
        self.assertIn("ignore-duplicates", prefer)

    def test_stored_horizon_is_not_rewritten_and_short_capture_is_flagged(self):
        sb = FakeSb(stored={("espn", 7, "week")})
        out = pc.save_capture_or_flag(sb, self.rows(3500), "espn", 2026, 7, ("week",))
        self.assertIn("already stored", out[0])
        self.assertEqual(sb.posts, [])
        sb = FakeSb()
        out = pc.save_capture_or_flag(sb, self.rows(10), "espn", 2026, 7, ("week",))
        self.assertTrue(out[0].startswith("::error"))
        self.assertEqual(sb.posts, [])
        out = pc.save_capture_or_flag(sb, self.rows(3500), "espn", 2026, 7, ("week",))
        self.assertIn("3500 rows written", out[0])

    def test_a_fault_is_returned_not_raised(self):
        class Boom(FakeSb):
            def post(self, *a, **k):
                raise RuntimeError("HTTP 500")
        out = pc.save_capture_or_flag(Boom(), self.rows(3500), "espn", 2026, 7, ("week",))
        self.assertTrue(out[0].startswith("::error") and "HTTP 500" in out[0])


class CbsPullTests(unittest.TestCase):
    def test_a_page_that_serves_another_week_is_not_offered(self):
        asked = []

        def fake_fetch(url):
            wk = int(re.search(r"/2026/(\d+)/", url).group(1))
            asked.append(wk)
            return f"<title>Week {min(wk, 8)} Proj Fantasy Football Stats</title>"

        row = {"player_name": "A", "player_norm": "a", "pos": "RB", "team": "DET", "gp": 1,
               "ros_standard": 9.0, "ros_half_ppr": 10.0, "ros_ppr": 11.0}
        orig = (cbs_pull.fetch, cbs_pull.parse_position)
        cbs_pull.fetch = fake_fetch
        cbs_pull.parse_position = lambda pos, html: ([dict(row, pos=pos)], [])
        try:
            out = cbs_pull.pull_weekly(7, "t")
        finally:
            cbs_pull.fetch, cbs_pull.parse_position = orig
        self.assertEqual(sorted(out["weeks"]), ["7", "8"])
        self.assertEqual(out["not_offered_weeks"], [9])
        self.assertEqual(len(out["weeks"]["8"]), 4)

    def test_fetch_failure_is_recorded_not_raised(self):
        def boom(url):
            raise SystemExit("Fail closed: HTTP 403")
        orig = cbs_pull.fetch
        cbs_pull.fetch = boom
        try:
            out = cbs_pull.pull_weekly(7, "t")
        finally:
            cbs_pull.fetch = orig
        self.assertEqual(out["weeks"], {})
        self.assertEqual(len(out["errors"]), 3)


class CompletenessTests(unittest.TestCase):
    def full(self, weeks):
        return {"espn": {(w, "week"): 13000 for w in weeks},
                "cbs": {**{(w, "ros"): 1000 for w in weeks}, **{(w, "week"): 1000 for w in weeks}},
                "razzball": {(w, "ros"): 1900 for w in weeks}}

    def test_complete_passes(self):
        self.assertEqual(pc.missing_captures(self.full([7, 8, 9]), current_week=9), [])

    def test_missing_week_fails_loudly(self):
        counts = self.full([7, 8, 9])
        del counts["cbs"][(8, "week")]
        problems = pc.missing_captures(counts, current_week=9)
        self.assertEqual(problems, ["cbs week capture for content week 8: MISSING"])

    def test_source_that_never_captured_fails(self):
        counts = self.full([7, 8])
        counts["razzball"] = {}
        self.assertEqual(len(pc.missing_captures(counts, current_week=8)), 2)

    def test_short_capture_fails(self):
        counts = self.full([7])
        counts["espn"][(7, "week")] = 1
        self.assertIn("below the floor", pc.missing_captures(counts, current_week=7)[0])

    def test_current_week_grace_only_for_the_current_week(self):
        counts = self.full([7, 8])
        counts["espn"].pop((9, "week"), None)
        self.assertEqual(pc.missing_captures(counts, current_week=9, grace_current=True), [])
        del counts["espn"][(8, "week")]
        self.assertEqual(len(pc.missing_captures(counts, current_week=9, grace_current=True)), 1)
        # no grace: espn week 8 plus all four horizons of week 9
        self.assertEqual(len(pc.missing_captures(counts, current_week=9, grace_current=False)), 5)

    def test_grace_window_is_tuesday_to_wednesday_noon(self):
        t = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)  # noqa: E731
        self.assertTrue(chk.in_grace(t("2026-10-27T01:00")))   # Tuesday
        self.assertTrue(chk.in_grace(t("2026-10-28T11:59")))   # Wednesday before noon
        self.assertFalse(chk.in_grace(t("2026-10-28T12:00")))
        self.assertFalse(chk.in_grace(t("2026-10-25T20:00")))  # Sunday

    def test_fetch_counts_probes_rows_by_offset(self):
        class Probe:
            def get(self, table, params=""):
                src = re.search(r"source=eq\.(\w+)", params).group(1)
                wk = int(re.search(r"source_week=eq\.(\d+)", params).group(1))
                off = int(re.search(r"offset=(\d+)", params).group(1))
                hz = re.search(r"horizon=eq\.(\w+)", params).group(1)
                have = {("espn", 7, "week"): 5000, ("cbs", 7, "week"): 100}.get((src, wk, hz), 0)
                return [{"id": 1}] if off < have else []
        c = pc.fetch_capture_counts(Probe(), 2026, [7])
        self.assertEqual(c["espn"][(7, "week")], pc.MIN_ROWS[("espn", "week")])
        self.assertEqual(c["cbs"][(7, "week")], 1)       # present but short
        self.assertNotIn((7, "ros"), c["cbs"])           # absent
        self.assertEqual(c["razzball"], {})


class BackfillTests(unittest.TestCase):
    def test_week_history_becomes_ros_ppg_rows_only(self):
        d = {"season": 2026, "week": 5, "sources": {
            "espn": {"captured_at": "2026-10-12T21:49:12Z", "ppg": {"11": [1.0, 2.0, 3.0]}},
            "cbsros": {"captured_at": "2026-10-12T19:30:41Z", "ppg": {"12": [4.0, None, 6.0]}},
            "fantasycalc": {"captured_at": "x", "ppg": {}}}}
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "week-5.json"
            p.write_text(json.dumps(d))
            rows = bf.rows_from_history(p, "b")
        self.assertEqual(len(rows), 5)
        self.assertEqual({r["horizon"] for r in rows}, {"ros"})
        self.assertEqual({(r["source"], r["source_week"]) for r in rows}, {("espn", 5), ("cbs", 5)})
        self.assertTrue(all(r["points"] is None and r["games"] is None for r in rows))
        self.assertEqual(rows[0]["capture_at"], "2026-10-12T21:49:12Z")

    def test_real_history_counts(self):
        rows = []
        for p in sorted(bf.HISTORY.glob("week-*.json")):
            rows += bf.rows_from_history(p, "b")
        pairs = {(r["source"], r["source_week"]) for r in rows}
        self.assertEqual({w for s, w in pairs if s == "espn"}, {2, 3, 4, 5, 6, 7})
        self.assertEqual({w for s, w in pairs if s == "razzball"}, {3, 4, 5, 6, 7})
        self.assertEqual({w for s, w in pairs if s == "cbs"}, {4, 5, 6, 7})


class SaverHookTests(unittest.TestCase):
    """The savers' capture step posts to source_projection_captures and nothing else."""

    PLAYERS = [{"player_key": 5, "full_name": "Alpha Back", "position": "RB", "active": True}]

    def run_cbs(self, weekly):
        import save_cbsros_references as sc
        sb = FakeSb()
        snap = {"vintage_date": "2026-10-27", "rows": [
            {"player_name": "Alpha Back", "pos": "RB", "player_norm": "alpha back", "gp": 9,
             "ros_standard": 90, "ros_half_ppr": 99, "ros_ppr": 108,
             "per_game_standard": 10, "per_game_half_ppr": 11, "per_game_ppr": 12}]}
        saved = (sc._sb, sc.fetch_players, dict(pc.MIN_ROWS))
        sc._sb, sc.fetch_players = (lambda: sb), (lambda: self.PLAYERS)
        pc.MIN_ROWS.update({("cbs", "ros"): 1, ("cbs", "week"): 1})
        try:
            with tempfile.TemporaryDirectory() as t:
                snap_path = Path(t) / "snapshot.json"
                snap_path.write_text(json.dumps(snap))
                if weekly is not None:
                    (Path(t) / "weekly_snapshot.json").write_text(json.dumps(weekly))
                sc.save_captures(snap_path, "2026-10-27")
        finally:
            sc._sb, sc.fetch_players = saved[0], saved[1]
            pc.MIN_ROWS.clear(); pc.MIN_ROWS.update(saved[2])
        return sb

    def test_cbs_writes_ros_and_week_rows_to_the_capture_table_only(self):
        weekly = {"weeks": {"8": [{"player_name": "Alpha Back", "pos": "RB", "player_norm": "alpha back",
                                   "gp": 1, "points_standard": 9, "points_half_ppr": 10,
                                   "points_ppr": 11}]}, "not_offered_weeks": [9], "errors": []}
        sb = self.run_cbs(weekly)
        self.assertEqual({t for t, *_ in sb.posts}, {"source_projection_captures"})
        horizons = {(r["horizon"], r["target_week"]) for _t, body, *_ in sb.posts for r in body}
        self.assertEqual(horizons, {("ros", 0), ("week", 8)})

    def test_cbs_without_week_pages_still_captures_ros_and_flags(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            sb = self.run_cbs(None)
        self.assertIn("::error title=projection capture cbs week", buf.getvalue())
        self.assertEqual({r["horizon"] for _t, body, *_ in sb.posts for r in body}, {"ros"})


class MigrationPinTests(unittest.TestCase):
    sql = MIGRATION.read_text()

    def test_unique_key_matches_the_writers_conflict_target(self):
        m = re.search(r"unique\s*\(([^)]*)\)", self.sql, re.S)
        self.assertEqual(re.sub(r"\s+", "", m.group(1)), pc.CONFLICT)

    def test_rules_the_writers_rely_on(self):
        for needle in ("source in ('espn', 'cbs', 'razzball')",
                       "(horizon = 'ros' and target_week = 0)",
                       "points is not null or ppg is not null",
                       "before update or delete",
                       "enable row level security",
                       "revoke all on public.source_projection_captures from anon, authenticated"):
            self.assertIn(needle, self.sql)

    def test_sources_and_formats_agree_with_the_library(self):
        for s in pc.SOURCES + pc.FORMATS:
            self.assertIn(f"'{s}'", self.sql)


if __name__ == "__main__":
    unittest.main()
