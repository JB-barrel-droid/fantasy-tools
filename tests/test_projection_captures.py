"""JEG-944: the append-only forward-projection capture.

Pins, on hand-built inputs (no network, no database):
  - ESPN captures every unplayed week, three formats, and no ROS rows;
  - CBS captures ROS plus each offered week; Razzball captures ROS only;
  - the write is first-one-wins (ignore-duplicates on the unique key) and a
    horizon already stored for the content week is not written again;
  - a pull page that answers with a different week is "not offered", not data;
  - the completeness check fails on a missing week, a short capture, and a
    source that never captured, and passes on a complete set;
  - the backfill turns week-history files into ROS rows and nothing else, pinned on a
    frozen fixture with literal rows; the live-tree smoke accepts a new week but fails
    a dropped week or source, weekly horizon, changed null handling or empty output;
  - the migration keeps the unique key, the horizon/week rule and the
    append-only trigger the writers rely on.
Each guard is run once against a simulated broken state and must fail there.
"""
import inspect
import json
import re
import shutil
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import backfill_projection_captures as bf  # noqa: E402
import capture_projections_only as cap  # noqa: E402
import save_cbsros_references as sc  # noqa: E402
import save_razzball_references as sr  # noqa: E402
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
        m = re.search(r"source=eq\.(\w+).*source_week=eq\.(\d+).*capture_phase=eq\.(\w+).*horizon=eq\.(\w+)", params)
        off = int(re.search(r"offset=(\d+)", params).group(1))
        key = (m.group(1), int(m.group(2)), m.group(3), m.group(4))
        return [{"id": 1}] if key in self.stored and off == 0 else []

    def post(self, table, body, params="", prefer=""):
        self.posts.append((table, list(body), params, prefer))


def espn_row(pid, week, rec=4):
    return {"espn_id": pid, "name": f"P{pid}", "pos": "WR", "week": week, "season": 2026,
            "stats": {"receptions": rec, "receiving_yards": 50}}


class EspnCaptureTests(unittest.TestCase):
    def test_every_future_week_three_formats_no_ros(self):
        rows = [espn_row("1", w) for w in range(5, 19)] + [espn_row("bad", 8)]
        out, rep = sv.plan_captures(rows, StubIndex(), set(range(8, 19)), 2026, 8, NOW, "b", "midweek")
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
                                  {8}, 2026, 8, NOW, "b", "midweek")
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
                                        capture_at=NOW, phase="sunday", batch_id="b", vintage="2026-10-27")
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
                                        phase="sunday", batch_id="b", vintage="2026-10-26")
        self.assertEqual({r["horizon"] for r in rows}, {"ros"})
        self.assertEqual({r["capture_phase"] for r in rows}, {"sunday"})
        self.assertEqual(sorted(r["scoring_format"] for r in rows), ["half_ppr", "standard"])
        self.assertTrue(all(r["points"] is None and r["games"] == 11 for r in rows))

    def test_capture_row_refuses_bad_input(self):
        base = dict(source="espn", season=2026, source_week=7, capture_at=NOW, phase="midweek", horizon="week",
                    target_week=8, player_key=1, scoring_format="standard", basis="x",
                    batch_id="b", points=1)
        pc.capture_row(**base)
        for bad in ({"source": "fp"}, {"scoring_format": "ppr"}, {"points": None}, {"phase": "monday"}):
            with self.assertRaises(ValueError):
                pc.capture_row(**{**base, **bad})


class WriteRuleTests(unittest.TestCase):
    def rows(self, n, horizon="week"):
        return [pc.capture_row(source="espn", season=2026, source_week=7, capture_at=NOW,
                               phase="midweek", horizon=horizon, target_week=8 if horizon == "week" else 0,
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
        sb = FakeSb(stored={("espn", 7, "midweek", "week")})
        out = pc.save_capture_or_flag(sb, self.rows(3500), "espn", 2026, 7, "midweek", ("week",))
        self.assertIn("already stored", out[0])
        self.assertEqual(sb.posts, [])
        sb = FakeSb()
        out = pc.save_capture_or_flag(sb, self.rows(10), "espn", 2026, 7, "midweek", ("week",))
        self.assertTrue(out[0].startswith("::error"))
        self.assertEqual(sb.posts, [])
        out = pc.save_capture_or_flag(sb, self.rows(3500), "espn", 2026, 7, "midweek", ("week",))
        self.assertIn("3500 rows written", out[0])

    def test_a_fault_is_returned_not_raised(self):
        class Boom(FakeSb):
            def post(self, *a, **k):
                raise RuntimeError("HTTP 500")
        out = pc.save_capture_or_flag(Boom(), self.rows(3500), "espn", 2026, 7, "midweek", ("week",))
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


def utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


class CompletenessTests(unittest.TestCase):
    # content week 8 opens Tuesday 2026-10-27 (nfl_week.content_week_start)
    def full(self, cells):
        out = {s: {} for s in pc.SOURCES}
        for wk, ph in cells:
            for s_, hs in pc.REQUIRED_HORIZONS.items():
                for h in hs:
                    out[s_][(wk, ph, h)] = pc.MIN_ROWS[(s_, h)]
        return out

    def test_cells_midweek_then_sunday_with_grace(self):
        self.assertEqual(pc.required_cells(utc("2026-10-27T10:00")), [(7, "midweek")])
        self.assertEqual(pc.required_cells(utc("2026-10-28T12:00")), [(7, "midweek"), (8, "midweek")])
        self.assertEqual(pc.required_cells(utc("2026-11-01T20:00")), [(7, "midweek"), (8, "midweek")])
        self.assertEqual(pc.required_cells(utc("2026-11-02T12:00")),
                         [(7, "midweek"), (8, "midweek"), (8, "sunday")])

    def test_complete_passes(self):
        cells = pc.required_cells(utc("2026-11-02T12:00"))
        self.assertEqual(pc.missing_captures(self.full(cells), cells), [])

    def test_missing_sunday_copy_fails_loudly(self):
        cells = pc.required_cells(utc("2026-11-02T12:00"))
        counts = self.full(cells)
        del counts["cbs"][(8, "sunday", "week")]
        self.assertEqual(pc.missing_captures(counts, cells),
                         ["cbs week sunday capture for content week 8: MISSING"])

    def test_midweek_does_not_satisfy_sunday(self):
        cells = pc.required_cells(utc("2026-11-02T12:00"))
        counts = self.full([(7, "midweek"), (8, "midweek")])
        self.assertEqual(len(pc.missing_captures(counts, cells)), 4)

    def test_missing_midweek_week_fails(self):
        cells = pc.required_cells(utc("2026-10-29T12:00"))
        counts = self.full(cells)
        del counts["espn"][(8, "midweek", "week")]
        self.assertEqual(pc.missing_captures(counts, cells),
                         ["espn week midweek capture for content week 8: MISSING"])

    def test_source_that_never_captured_fails(self):
        cells = pc.required_cells(utc("2026-10-29T12:00"))
        counts = self.full(cells)
        counts["razzball"] = {}
        self.assertEqual(len(pc.missing_captures(counts, cells)), 2)

    def test_short_capture_fails(self):
        cells = [(7, "midweek")]
        counts = self.full(cells)
        counts["espn"][(7, "midweek", "week")] = 1
        self.assertIn("below the floor", pc.missing_captures(counts, cells)[0])

    def test_phase_is_sunday_only_on_sunday(self):
        self.assertEqual(pc.capture_phase(utc("2026-11-01T11:20")), "sunday")
        for d in ("2026-10-27", "2026-10-30", "2026-11-02"):
            self.assertEqual(pc.capture_phase(utc(d + "T12:40")), "midweek")

    def test_fetch_counts_probes_rows_by_offset(self):
        class Probe:
            def get(self, table, params=""):
                src = re.search(r"source=eq\.(\w+)", params).group(1)
                wk = int(re.search(r"source_week=eq\.(\d+)", params).group(1))
                ph = re.search(r"capture_phase=eq\.(\w+)", params).group(1)
                hz = re.search(r"horizon=eq\.(\w+)", params).group(1)
                off = int(re.search(r"offset=(\d+)", params).group(1))
                have = {("espn", 7, "midweek", "week"): 5000,
                        ("cbs", 7, "midweek", "week"): 100}.get((src, wk, ph, hz), 0)
                return [{"id": 1}] if off < have else []
        c = pc.fetch_capture_counts(Probe(), 2026, [(7, "midweek"), (7, "sunday")])
        self.assertEqual(c["espn"][(7, "midweek", "week")], pc.MIN_ROWS[("espn", "week")])
        self.assertEqual(c["cbs"][(7, "midweek", "week")], 1)
        self.assertNotIn((7, "midweek", "ros"), c["cbs"])
        self.assertNotIn((7, "sunday", "week"), c["espn"])
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
        self.assertEqual({r["capture_phase"] for r in rows}, {"backfill"})
        self.assertEqual({r["horizon"] for r in rows}, {"ros"})
        self.assertEqual({(r["source"], r["source_week"]) for r in rows}, {("espn", 5), ("cbs", 5)})
        self.assertTrue(all(r["points"] is None and r["games"] is None for r in rows))
        self.assertEqual(rows[0]["capture_at"], "2026-10-12T21:49:12Z")

    def test_real_history_counts(self):
        # Current-tree smoke over data/history. Pins the historical floor (each source's
        # first week through week 7 must stay present) and requires every later week the
        # tree holds, so a legitimate new week passes without editing this test.
        live = sorted(bf.HISTORY.glob("week-*.json"))
        self.assertTrue(live, "no data/history/week-*.json files")
        latest = max(int(re.fullmatch(r"week-(\d+)\.json", p.name).group(1)) for p in live)
        self.assertGreaterEqual(latest, 7)
        assert_live_history(self, bf.rows_from_history, bf.HISTORY, latest)


# --- JEG-1242: pinned fixture, new-week case and mutation checks --------------------

FIXTURE = ROOT / "tests" / "fixtures" / "projection_history_backfill"

# Written by hand from the fixture files, not computed by the code under test.
# (source, source_week, capture_at, player_key, scoring_format, ppg)
PINNED_ROWS = {
    ("espn", 2, "2026-09-16T12:00:00Z", 101, "standard", 10.0),
    ("espn", 2, "2026-09-16T12:00:00Z", 101, "half_ppr", 11.5),
    ("espn", 2, "2026-09-16T12:00:00Z", 101, "full_ppr", 13.0),
    ("espn", 2, "2026-09-16T12:00:00Z", 102, "standard", 5.0),
    ("espn", 2, "2026-09-16T12:00:00Z", 102, "full_ppr", 7.25),
    ("espn", 3, "2026-09-23T12:00:00Z", 101, "standard", 10.5),
    ("espn", 3, "2026-09-23T12:00:00Z", 101, "half_ppr", 12.0),
    ("espn", 3, "2026-09-23T12:00:00Z", 101, "full_ppr", 13.5),
    ("razzball", 3, "2026-09-23T13:00:00Z", 201, "standard", 8.123),
    ("razzball", 3, "2026-09-23T13:00:00Z", 201, "half_ppr", 9.5),
    ("razzball", 3, "2026-09-23T13:00:00Z", 201, "full_ppr", 10.875),
    ("espn", 4, "2026-09-30T12:00:00Z", 103, "full_ppr", 4.0),
    ("razzball", 4, "2026-09-30T13:00:00Z", 201, "standard", 7.0),
    ("razzball", 4, "2026-09-30T13:00:00Z", 201, "half_ppr", 8.0),
    ("razzball", 4, "2026-09-30T13:00:00Z", 201, "full_ppr", 9.0),
    ("cbs", 4, "2026-09-30T14:00:00Z", 301, "standard", 6.0),
    ("cbs", 4, "2026-09-30T14:00:00Z", 301, "half_ppr", 6.5),
    ("cbs", 4, "2026-09-30T14:00:00Z", 301, "full_ppr", 7.0),
}
# A legitimate later week, and the rows it must add (again written by hand).
NEW_WEEK = {"season": 2026, "week": 5, "sources": {
    "espn": {"captured_at": "2026-10-07T12:00:00Z", "ppg": {"101": [11.0, 12.0, 13.0]}},
    "razzball": {"captured_at": "2026-10-07T13:00:00Z", "ppg": {"201": [6.0, 7.0, 8.0]}},
    "cbsros": {"captured_at": "2026-10-07T14:00:00Z", "ppg": {"301": [5.0, 5.5, 6.0]}},
    "cbs": {"captured_at": "2026-10-07T12:05:00Z", "ppg": {}}}}
NEW_WEEK_ROWS = {
    ("espn", 5, "2026-10-07T12:00:00Z", 101, "standard", 11.0),
    ("espn", 5, "2026-10-07T12:00:00Z", 101, "half_ppr", 12.0),
    ("espn", 5, "2026-10-07T12:00:00Z", 101, "full_ppr", 13.0),
    ("razzball", 5, "2026-10-07T13:00:00Z", 201, "standard", 6.0),
    ("razzball", 5, "2026-10-07T13:00:00Z", 201, "half_ppr", 7.0),
    ("razzball", 5, "2026-10-07T13:00:00Z", 201, "full_ppr", 8.0),
    ("cbs", 5, "2026-10-07T14:00:00Z", 301, "standard", 5.0),
    ("cbs", 5, "2026-10-07T14:00:00Z", 301, "half_ppr", 5.5),
    ("cbs", 5, "2026-10-07T14:00:00Z", 301, "full_ppr", 6.0),
}
# History section -> capture source, and the [standard, half_ppr, ppr] triple order,
# restated here so the live check does not lean on the module's own tables.
HISTORY_SOURCES = {"espn": "espn", "razzball": "razzball", "cbsros": "cbs"}
FIRST_WEEK = {"espn": 2, "razzball": 3, "cbs": 4}
FROZEN_THROUGH = 7
MIN_ROWS_PER_SOURCE_WEEK = 500  # every live source-week holds 349+ players x 3 formats


def run_backfill(rows_fn, history_dir):
    rows = []
    for p in sorted(Path(history_dir).glob("week-*.json")):
        rows += rows_fn(p, "b")
    return rows


def assert_ros_backfill_shape(case, rows, season=2026):
    case.assertTrue(rows, "backfill yielded no rows")
    for r in rows:
        case.assertEqual((r["capture_phase"], r["horizon"], r["target_week"]), ("backfill", "ros", 0), r)
        case.assertIsNone(r["points"], r)
        case.assertIsNone(r["games"], r)
        case.assertIsNotNone(r["ppg"], r)
        case.assertEqual(r["season"], season, r)
        case.assertEqual(r["batch_id"], "b", r)
        case.assertIn(f"data/history/week-{r['source_week']}.json", r["basis"], r)


def key(r):
    return (r["source"], r["source_week"], r["capture_at"], r["player_key"], r["scoring_format"], r["ppg"])


def assert_pinned(case, rows, expected):
    assert_ros_backfill_shape(case, rows)
    keys = [key(r) for r in rows]
    case.assertEqual(len(keys), len(set(keys)), "duplicate backfill rows")
    case.assertEqual(set(keys), expected)


def expected_live_count(path):
    """Rows a history file should yield, counted straight from the raw JSON."""
    d = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for hist_key, source in HISTORY_SOURCES.items():
        sec = d["sources"].get(hist_key) or {}
        if not sec.get("captured_at"):
            continue
        n = sum(v is not None for triple in (sec.get("ppg") or {}).values() if triple for v in triple)
        if n:
            out[(source, int(d["week"]))] = n
    return out


def assert_live_history(case, rows_fn, history_dir, latest):
    files = sorted(Path(history_dir).glob("week-*.json"))
    for p in files:
        case.assertEqual(json.loads(p.read_text(encoding="utf-8"))["week"],
                         int(re.fullmatch(r"week-(\d+)\.json", p.name).group(1)), p.name)
    rows = run_backfill(rows_fn, history_dir)
    assert_ros_backfill_shape(case, rows)
    counts = {}
    for r in rows:
        counts[(r["source"], r["source_week"])] = counts.get((r["source"], r["source_week"]), 0) + 1
    for source, first in FIRST_WEEK.items():
        weeks = {w for s, w in counts if s == source}
        case.assertTrue(set(range(first, FROZEN_THROUGH + 1)) <= weeks,
                        f"{source}: historical weeks missing, have {sorted(weeks)}")
        case.assertEqual(weeks, set(range(first, latest + 1)), f"{source}: weeks {sorted(weeks)}")
        case.assertNotIn(first - 1, weeks)
    case.assertEqual({s for s, _w in counts}, set(FIRST_WEEK))
    for sw, n in counts.items():
        case.assertGreaterEqual(n, MIN_ROWS_PER_SOURCE_WEEK, f"{sw}: {n} rows")
    want = {}
    for p in files:
        want.update(expected_live_count(p))
    case.assertEqual(counts, want)


def mutant(*edits):
    """rows_from_history with source edits (old, new), compiled against the real module globals."""
    src = textwrap.dedent(inspect.getsource(bf.rows_from_history))
    for old, new in edits:
        if src.count(old) != 1:
            raise RuntimeError(f"mutation anchor not found exactly once: {old!r}")
        src = src.replace(old, new)
    ns = dict(vars(bf))
    exec(compile(src, bf.__file__, "exec"), ns)  # noqa: S102
    return ns["rows_from_history"]


# Structural mutants: both the frozen fixture and the live-tree smoke must catch them.
MUTANTS = {
    "omit razzball": lambda: mutant(('for hist_key, source in SOURCE_OF.items():',
                                     ('for hist_key, source in ((k, v) for k, v in SOURCE_OF.items() '
                                      'if k != "razzball"):'))),
    "weekly cbs instead of cbsros": lambda: mutant(('for hist_key, source in SOURCE_OF.items():',
                                                    ('for hist_key, source in ((k, v) for k, v in '
                                                     '{**SOURCE_OF, "cbs": "cbs"}.items() if k != "cbsros"):'))),
    "weekly horizon": lambda: mutant(('horizon="ros", target_week=0',
                                      'horizon="week", target_week=week + 1')),
    "drop a format": lambda: mutant(('for fmt, i in FORMAT_AT:', 'for fmt, i in FORMAT_AT[1:]:')),
    "empty output": lambda: mutant(('    return out', '    return []')),
    "skip latest week": lambda: mutant(('week, season = int(d["week"]), int(d["season"])',
                                        ('week, season = int(d["week"]), int(d["season"])\n'
                                         '    if path.name == max(path.parent.glob("week-*.json"), '
                                         'key=lambda q: int(q.stem[5:])).name:\n        return []'))),
}
# Value mutants: the live tree holds no per-format nulls and its values are not pinned,
# so only the frozen fixture's literal rows can catch these.
VALUE_MUTANTS = {
    "missing ppg written as 0": lambda: mutant(
        ('if triple is None or triple[i] is None:\n                    continue',
         'if triple is None:\n                    continue'),
        ('ppg=triple[i]', 'ppg=0.0 if triple[i] is None else triple[i]')),
    "per-format shift": lambda: mutant(('ppg=triple[i]', 'ppg=triple[min(i + 1, 2)]')),
    "wrong capture_at": lambda: mutant(('capture_at=sec["captured_at"]', 'capture_at=pc.now_iso()')),
}


class BackfillFixtureTests(unittest.TestCase):
    """JEG-1242: a frozen fixture with literal expected rows, separate from the live smoke."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        for p in FIXTURE.glob("week-*.json"):
            shutil.copy(p, self.dir / p.name)

    def test_frozen_fixture_rows_are_exact(self):
        assert_pinned(self, run_backfill(bf.rows_from_history, FIXTURE), PINNED_ROWS)

    def test_a_new_week_adds_rows_without_touching_history(self):
        (self.dir / "week-5.json").write_text(json.dumps(NEW_WEEK))
        rows = run_backfill(bf.rows_from_history, self.dir)
        assert_pinned(self, rows, PINNED_ROWS | NEW_WEEK_ROWS)
        self.assertEqual({key(r) for r in rows if r["source_week"] < 5}, PINNED_ROWS)

    def test_live_check_accepts_a_new_week_with_no_edit(self):
        # The live smoke must pass when the tree gains a week beyond the frozen floor.
        big = {"season": 2026, "week": 0, "sources": {
            h: {"captured_at": f"2026-10-0{i}T12:00:00Z",
                "ppg": {str(1000 + j): [1.0, 2.0, 3.0] for j in range(200)}}
            for i, h in enumerate(HISTORY_SOURCES, 1)}}
        d = Path(self.tmp.name) / "live"
        d.mkdir()
        for w in range(2, 10):
            doc = json.loads(json.dumps(big))
            doc["week"] = w
            for h, src in HISTORY_SOURCES.items():
                if w < FIRST_WEEK[src]:
                    del doc["sources"][h]
            (d / f"week-{w}.json").write_text(json.dumps(doc))
        assert_live_history(self, bf.rows_from_history, d, 9)
        (d / "week-9.json").unlink()
        assert_live_history(self, bf.rows_from_history, d, 8)
        with self.assertRaises(AssertionError):  # a dropped latest week is not "fine"
            assert_live_history(self, bf.rows_from_history, d, 9)

    def test_dropping_a_week_file_fails(self):
        (self.dir / "week-3.json").unlink()
        with self.assertRaises(AssertionError):
            assert_pinned(self, run_backfill(bf.rows_from_history, self.dir), PINNED_ROWS)

    def test_each_mutation_fails_the_pinned_fixture(self):
        for name, build in {**MUTANTS, **VALUE_MUTANTS}.items():
            with self.subTest(mutant=name):
                fn = build()
                with self.assertRaises((AssertionError, ValueError, TypeError)):
                    assert_pinned(self, run_backfill(fn, FIXTURE), PINNED_ROWS)

    def test_each_mutation_fails_the_live_smoke(self):
        live = sorted(bf.HISTORY.glob("week-*.json"))
        latest = max(int(re.fullmatch(r"week-(\d+)\.json", p.name).group(1)) for p in live)
        for name, build in MUTANTS.items():
            with self.subTest(mutant=name):
                fn = build()
                with self.assertRaises((AssertionError, ValueError, TypeError)):
                    assert_live_history(self, fn, bf.HISTORY, latest)

    def test_unmutated_function_passes_both_checks(self):
        # Guards the mutation tests above against passing for the wrong reason.
        assert_pinned(self, run_backfill(bf.rows_from_history, FIXTURE), PINNED_ROWS)
        live = sorted(bf.HISTORY.glob("week-*.json"))
        latest = max(int(re.fullmatch(r"week-(\d+)\.json", p.name).group(1)) for p in live)
        assert_live_history(self, bf.rows_from_history, bf.HISTORY, latest)


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


class SundayCaptureOnlyTests(unittest.TestCase):
    """The Sunday copy for CBS and Razzball must not be able to move a published value."""

    def test_capture_only_never_calls_the_published_table_writers(self):
        calls = []
        def boom(*a, **k):
            raise AssertionError("published-table writer called")
        saved = (sc.upsert_rows, sr.upsert_rows, sc.delete_rows, sr.build_razzball_rows,
                 sc.save_captures, sr.save_captures)
        sc.upsert_rows = sr.upsert_rows = sc.delete_rows = boom
        sr.build_razzball_rows = lambda path: ([{"player_key": 1}], [], "2026-11-01")
        sc.save_captures = lambda path, vintage: calls.append(("cbs", vintage))
        sr.save_captures = lambda clean, vintage: calls.append(("razzball", vintage))
        try:
            with tempfile.TemporaryDirectory() as t:
                cbs, rz = Path(t) / "cbs", Path(t) / "rz"
                cbs.mkdir(); rz.mkdir()
                (cbs / "snapshot.json").write_text(json.dumps({"vintage_date": "2026-11-01"}))
                (rz / "snapshot.json").write_text("{}")
                rc = cap.main(["--cbs", str(cbs), "--razzball", str(rz)])
        finally:
            (sc.upsert_rows, sr.upsert_rows, sc.delete_rows, sr.build_razzball_rows,
             sc.save_captures, sr.save_captures) = saved
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [("cbs", "2026-11-01"), ("razzball", "2026-11-01")])

    def test_workflow_runs_the_capture_only_script_and_no_saver(self):
        wf = (ROOT / ".github/workflows/projection-capture-sunday.yml").read_text()
        self.assertIn("capture_projections_only.py", wf)
        for banned in ("save_cbsros_references.py", "save_razzball_references.py",
                       "gh workflow run", "dispatch_gha_workflow", "git push",
                       "contents: write", "actions: write"):
            self.assertNotIn(banned, wf)

    def test_espn_gate_step_exists(self):
        wf = (ROOT / ".github/workflows/espn-weekly-store.yml").read_text()
        self.assertIn("pipelines/check_projection_captures.py", wf)


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
                       "capture_phase in ('midweek', 'sunday', 'backfill')",
                       "projection-capture-sunday.yml",
                       "enable row level security",
                       "revoke all on public.source_projection_captures from anon, authenticated"):
            self.assertIn(needle, self.sql)

    def test_sources_and_formats_agree_with_the_library(self):
        for s in pc.SOURCES + pc.FORMATS:
            self.assertIn(f"'{s}'", self.sql)


if __name__ == "__main__":
    unittest.main()
