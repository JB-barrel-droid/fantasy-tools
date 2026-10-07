#!/usr/bin/env python3
"""Decision build-lag-001: the import-health gate tolerates a ONE-week lag.

Guards (each negative-tested against the pre-build-lag-001 gate, see
docs/claude-log/ 2026-10-07 entry):

  LAG-001  A week-designated source exactly one content week behind is a
           non-blocking `warning` with reason "LAGGING_ONE_WEEK
           (non-blocking): ..."; the gate is GREEN on today's real state
           (2026-10-07, content week 5: FantasyCalc Week 5, CBS / FantasyPros /
           USA Today / CBS ROS Week 4).
  LAG-002  Two or more weeks behind still blocks (stale or red).
  LAG-003  The green check is fail-closed: publication-window "red"
           (MISSED_WINDOW) and any status outside the allow-list block. The
           old check counted only stale/missing/failed, so red passed.
  LAG-004  A source AHEAD of the check week is fresh, and --nfl-week defaults
           to pipelines/nfl_week.py (content week, flips Tuesday).
  LAG-005  Promotion accepts a lagging source only under its own
           content_vintage; a TABLE_DRIFT warning or stale entry is refused.
  LAG-006  The chain status records each source's own content week.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PIPELINES = ROOT / "pipelines"
sys.path.insert(0, str(PIPELINES))
sys.path.insert(0, str(ROOT / "tests"))

import test_import_health as tih  # noqa: E402  (shared snapshot helpers)

mod = tih.mod  # the verify_import_health module the helpers stamp against

# Today's real state, from the CI health artifact checked 2026-10-07T11:11Z
# (dist/modules/source-import-health.json) and the Supabase tables queried
# 2026-10-07 (source_trade_values, cbs_trade_values, cbs_ros_projections,
# espn_season_projections, razzball_projections; latest vintage per source).
CHECK_DATE = date(2026, 10, 7)  # Wednesday; content week 5
REAL_STATE = {
    # source: (content_vintage, week_designated, row_count, table_kind, table_value)
    "fantasycalc": ("Week 5", 5, 585, "week", 5),
    "usatoday": ("2026-09-29", 4, 747, "date", "2026-09-29"),
    "fantasypros": ("2026-09-29", 4, 534, "date", "2026-09-29"),
    "cbs": ("Week 4", 4, 342, "week", 4),
    "cbsros": ("2026-10-02", None, 363, "date", "2026-10-02"),
    "espn": ("2026-10-06", None, 496, "date", "2026-10-06"),
    "razzball": ("2026-10-06", None, 672, "date", "2026-10-06"),
}
SUPABASE_TABLES = {
    "fantasycalc": "public.source_trade_values",
    "usatoday": "public.source_trade_values",
    "fantasypros": "public.source_trade_values",
    "cbs": "public.cbs_trade_values",
    "cbsros": "public.cbs_ros_projections",
    "espn": "public.espn_season_projections",
    "razzball": "public.razzball_projections",
}
DATE_COLS = {
    "espn_season_projections": "espn_snapshot_date",
    "cbs_ros_projections": "cbs_snapshot_date",
    "razzball_projections": "razzball_snapshot_date",
}


def table_source(table: str, params: str) -> str:
    if table == "espn_season_projections":
        return "espn"
    if table == "cbs_ros_projections":
        return "cbsros"
    if table == "razzball_projections":
        return "razzball"
    if table == "cbs_trade_values":
        return "cbs"
    for name in ("fantasycalc", "usatoday", "fantasypros"):
        if f"source=eq.{name}" in params:
            return name
    raise AssertionError((table, params))


class _GateWorld(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "sources"
        self.out = Path(self.tmp.name) / "output" / "source-import-health.json"
        self._fetch = mod.fetch_table_summary
        self.state = {k: list(v) for k, v in REAL_STATE.items()}

    def tearDown(self):
        mod.fetch_table_summary = self._fetch
        self.tmp.cleanup()

    def stamp(self):
        if self.root.exists():
            shutil.rmtree(self.root)
        state = self.state

        def tables(table, params):
            src = table_source(table, params)
            _, _, n, kind, value = state[src]
            col = DATE_COLS.get(table, "source_content_date")
            if kind == "week":
                return tih.db_rows(n, week=value, date_col=col)
            return tih.db_rows(n, source_content_date=value, date_col=col)

        mod.fetch_table_summary = tables
        for src, (vintage, week, n, _kind, _value) in state.items():
            vdir = f"week-{week}" if str(vintage).startswith("Week") else vintage
            tih.make_snapshot(self.root, src, vdir, content_vintage=vintage,
                              week_designated=week, row_count=n,
                              supabase_table=SUPABASE_TABLES[src])

    def gate(self, nfl_week=5, check_date=CHECK_DATE):
        self.stamp()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = mod.run_health(nfl_week=nfl_week, sources_root=self.root,
                                  output_path=self.out, check_date=check_date)
        return code, json.loads(self.out.read_text(encoding="utf-8")), err.getvalue()


class TodayRealStateTest(_GateWorld):
    """LAG-001: the gate is GREEN on 2026-10-07 with CBS/FP lagging one week."""

    def test_real_state_is_green_with_one_week_laggards(self):
        code, health, err = self.gate()
        self.assertEqual(code, 0, err)
        self.assertIn("GATE: GREEN", err)
        src = health["sources"]
        for name in ("fantasycalc", "espn", "razzball"):
            self.assertEqual(src[name]["status"], "ok", (name, src[name]["failure_reason"]))
        for name in ("cbs", "fantasypros", "usatoday", "cbsros"):
            entry = src[name]
            self.assertEqual(entry["status"], "warning", name)
            self.assertFalse(entry["blocking"], name)
            self.assertTrue(entry["failure_reason"].startswith(
                "LAGGING_ONE_WEEK (non-blocking): "), entry["failure_reason"])
            self.assertEqual(entry["content_week"], 4, name)
        # Each source keeps its own label: nothing is relabelled to Week 5.
        self.assertEqual(src["cbs"]["content_vintage"], "Week 4")
        self.assertEqual(src["fantasypros"]["content_vintage"], "2026-09-29")
        self.assertEqual(src["fantasycalc"]["content_vintage"], "Week 5")
        self.assertEqual(src["fantasycalc"]["content_week"], 5)
        # The window verdict is preserved inside the reason.
        self.assertIn("STALE_VINTAGE", src["cbs"]["failure_reason"])
        self.assertIn("AWAITING_PUBLICATION", src["cbsros"]["failure_reason"])

    def test_one_week_lag_past_its_window_is_still_non_blocking(self):
        # Thursday 2026-10-08: USA Today (Tue publisher, 1-day grace) is past
        # its window -> MISSED_WINDOW, but still only one week behind.
        code, health, err = self.gate(check_date=date(2026, 10, 8))
        self.assertEqual(code, 0, err)
        entry = health["sources"]["usatoday"]
        self.assertEqual(entry["status"], "warning")
        self.assertIn("MISSED_WINDOW", entry["failure_reason"])

    def test_week5_flip_against_week4_data_is_green(self):
        # Same data, Tuesday 2026-10-06 (the flip day): still green.
        code, _, err = self.gate(check_date=date(2026, 10, 6))
        self.assertEqual(code, 0, err)


class TwoWeeksBehindBlocksTest(_GateWorld):
    """LAG-002: two or more weeks behind still blocks."""

    def test_cbs_two_weeks_behind_blocks(self):
        self.state["cbs"] = ["Week 3", 3, 355, "week", 3]
        code, health, err = self.gate()
        self.assertNotEqual(code, 0)
        entry = health["sources"]["cbs"]
        self.assertEqual(entry["status"], "stale")
        self.assertTrue(entry["blocking"])
        self.assertTrue(entry["failure_reason"].startswith("STALE_VINTAGE"))
        self.assertIn("GATE: RED", err)
        self.assertIn("blocking: cbs", err)

    def test_fantasypros_two_weeks_behind_blocks(self):
        self.state["fantasypros"] = ["2026-09-22", 3, 534, "date", "2026-09-22"]
        code, health, _ = self.gate()
        self.assertNotEqual(code, 0)
        self.assertEqual(health["sources"]["fantasypros"]["status"], "stale")


class RedBlocksTest(_GateWorld):
    """LAG-003: red (MISSED_WINDOW) and unknown statuses block (fail-closed)."""

    def test_usatoday_two_weeks_behind_red_blocks_the_gate(self):
        # Verified Tuesday schedule, two weeks behind -> red MISSED_WINDOW.
        # Every other source is fresh, so red is the ONLY non-ok entry: the
        # pre-build-lag-001 gate ignored red and went GREEN here.
        self.state["cbs"] = ["Week 5", 5, 342, "week", 5]
        self.state["fantasypros"] = ["2026-10-06", 5, 534, "date", "2026-10-06"]
        self.state["cbsros"] = ["2026-10-06", None, 363, "date", "2026-10-06"]
        self.state["usatoday"] = ["2026-09-23", 3, 702, "date", "2026-09-23"]
        code, health, err = self.gate()
        entry = health["sources"]["usatoday"]
        self.assertEqual(entry["status"], "red")
        self.assertTrue(entry["failure_reason"].startswith("MISSED_WINDOW"))
        self.assertNotEqual(code, 0, err)
        self.assertIn("GATE: RED", err)

    def test_unknown_status_blocks(self):
        for status in ("red", "yellow", "stale", "missing", "failed", "mystery", None):
            with self.subTest(status=status):
                self.assertTrue(mod.entry_is_blocking("cbs", {"status": status}))
        for status in ("ok", "warning"):
            with self.subTest(status=status):
                self.assertFalse(mod.entry_is_blocking("cbs", {"status": status}))

    def test_razzball_snapshot_age_is_advisory_but_its_failures_block(self):
        for status in ("warn", "bad", "unk"):
            self.assertFalse(mod.entry_is_blocking("razzball", {"status": status}))
            self.assertTrue(mod.entry_is_blocking("cbs", {"status": status}))
        self.assertTrue(mod.entry_is_blocking("razzball", {"status": "failed"}))


class AheadAndCalendarTest(_GateWorld):
    """LAG-004: a newer source never reads stale; default week = content week."""

    def test_source_ahead_of_check_week_is_ok(self):
        # A Thursday-flip caller (week 4 on a Wednesday) must not make
        # FantasyCalc's Week 5 read stale.
        code, health, err = self.gate(nfl_week=4)
        self.assertEqual(code, 0, err)
        self.assertEqual(health["sources"]["fantasycalc"]["status"], "ok")
        self.assertIn("NOTE: --nfl-week 4 differs from content week 5", err)

    def test_cli_default_week_is_pipelines_nfl_week(self):
        import nfl_week
        self.assertEqual(nfl_week.current_nfl_week(CHECK_DATE), 5)
        self.assertEqual(nfl_week.current_nfl_week(date(2026, 10, 6)), 5)  # Tuesday flip
        self.assertEqual(nfl_week.current_nfl_week(date(2026, 10, 5)), 4)
        seen = {}

        def fake_run_health(**kwargs):
            seen.update(kwargs)
            return 0

        with mock.patch.object(mod, "current_nfl_week", lambda: 5), \
                mock.patch.object(mod, "run_health", fake_run_health), \
                mock.patch.object(sys, "argv", ["verify_import_health.py"]):
            self.assertEqual(mod.main(), 0)
        self.assertEqual(seen["nfl_week"], 5)


class PromotionContractTest(unittest.TestCase):
    """LAG-005: promotable = ok, or a one-week lag (never TABLE_DRIFT warning)."""

    def test_promotable_statuses(self):
        lag = {"status": "warning",
               "failure_reason": "LAGGING_ONE_WEEK (non-blocking): cbs content Week 4 ..."}
        drift = {"status": "warning",
                 "failure_reason": "TABLE_DRIFT: table latest vintage Week 5 != manifest"}
        self.assertTrue(mod.entry_is_promotable({"status": "ok"}))
        self.assertTrue(mod.entry_is_promotable(lag))
        self.assertFalse(mod.entry_is_promotable(drift))
        self.assertFalse(mod.entry_is_promotable({"status": "stale",
                                                  "failure_reason": "STALE_VINTAGE: x"}))
        self.assertFalse(mod.entry_is_promotable({"status": "red"}))


class ChainSourceVintagesTest(unittest.TestCase):
    """LAG-006: chain status names each source's own week."""

    def test_source_vintages_from_health(self):
        import rebuild_comparison_chain as chain
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "output").mkdir()
            (repo / "output" / "source-import-health.json").write_text(json.dumps({
                "schema": "trade-value-import-health-v1", "nfl_week": 5,
                "sources": {
                    "fantasycalc": {"status": "ok", "content_vintage": "Week 5",
                                    "content_week": 5, "failure_reason": None},
                    "cbs": {"status": "warning", "content_vintage": "Week 4",
                            "content_week": 4,
                            "failure_reason": "LAGGING_ONE_WEEK (non-blocking): x"},
                }}))
            status = chain.write_chain_status(repo, {}, None, None, 5, "local")
        sv = status["source_vintages"]
        self.assertEqual(sv["cbs"]["content_vintage"], "Week 4")
        self.assertTrue(sv["cbs"]["lagging_one_week"])
        self.assertEqual(sv["fantasycalc"]["content_week"], 5)
        self.assertFalse(sv["fantasycalc"]["lagging_one_week"])


if __name__ == "__main__":
    unittest.main()
