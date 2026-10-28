"""JEG-1180: the stale flag, judged by each source's own served week.

Rule (Jeremy, 2026-10-27, JEG-1176 open question 3): a source still serving
week N after Thursday 12:00 CT of week N+1 is stale. Before that it is
lagging, which is normal Tuesday through Thursday morning. Stale is a
warning: it never fails the chain, never changes a hold, never changes an
exit code.

* The rule itself: pipelines/week_state.py source_week_status, pinned to the
  shared vectors in tests/fixtures/week_stale_vectors.json (frozen clocks at
  Wednesday, Thursday 11:59 / 12:00 / 12:01 CT, across the DST change).
* The chain status (rebuild_comparison_chain.write_chain_status): per-source
  state in `source_weeks`, `stale_sources`; a run with a stale source still
  passes, with the same outcome it has when that source is only lagging.
* The health checks: check_reference_freshness rows, scripts/
  check_weekly_freshness.py, and the watchdog (ops/watchdog) use the same
  per-source rule.

Every clock here is frozen with nfl_week.set_clock (or passed in); no test
reads the real clock.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "ops" / "watchdog"))
sys.path.insert(0, str(ROOT / "tests"))

import nfl_week  # noqa: E402
import week_state  # noqa: E402

VECTORS = ROOT / "tests" / "fixtures" / "week_stale_vectors.json"

# Content week 8 opens Tuesday 2026-10-27 (CDT, UTC-5).
WEDNESDAY_NOON_CT = datetime(2026, 10, 28, 17, 0, tzinfo=timezone.utc)
THURSDAY_1159_CT = datetime(2026, 10, 29, 16, 59, tzinfo=timezone.utc)
THURSDAY_1201_CT = datetime(2026, 10, 29, 17, 1, tzinfo=timezone.utc)

# Seven sources mid-transition: three still on week 7.
WEEKS = {s: {"served_week": w, "label_week": w, "published_at": None, "basis": "history_index"}
         for s, w in (("usatoday", 7), ("fantasycalc", 8), ("fantasypros", 8), ("cbs", 7),
                      ("espn", 8), ("cbsros", 8), ("razzball", 7))}


def vector_cases():
    return json.loads(VECTORS.read_text(encoding="utf-8"))["cases"]


def at(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


class ClockMixin:
    def tearDown(self):
        nfl_week.set_clock(None)
        super().tearDown()


class StaleRuleVectorsTest(unittest.TestCase):
    def test_python_matches_the_vectors(self):
        for case in vector_cases():
            with self.subTest(case["name"]):
                got = week_state.source_week_status(case["served_week"], at(case["now"]))
                self.assertEqual({k: got.get(k) for k in case["expect"]}, case["expect"])

    def test_vectors_cover_wednesday_and_thursday_noon(self):
        names = " | ".join(c["name"] for c in vector_cases())
        for needle in ("Wednesday", "Thursday 11:59", "Thursday 12:00", "Thursday 12:01", "DST"):
            self.assertIn(needle, names)

    def test_the_vectors_catch_a_date_only_cutoff(self):
        """A twin that goes stale at the start of Thursday (a date, not
        12:00 CT, like the watchdog's discovery-overdue day count) fails."""
        def date_only(served, now):
            st = week_state.source_week_status(served, now)
            if st["state"] == "lagging" and nfl_week.today_ny(now).weekday() >= 3:
                st.update(state="stale", stale=True)
            return st
        bad = [c["name"] for c in vector_cases()
               if {k: date_only(c["served_week"], at(c["now"])).get(k) for k in c["expect"]} != c["expect"]]
        self.assertTrue(any("11:59" in n for n in bad), bad)

    def test_default_clock_is_the_injected_one(self):
        nfl_week.set_clock(THURSDAY_1201_CT)
        try:
            self.assertEqual(week_state.source_week_status(7)["state"], "stale")
            nfl_week.set_clock(WEDNESDAY_NOON_CT)
            self.assertEqual(week_state.source_week_status(7)["state"], "lagging")
        finally:
            nfl_week.set_clock(None)

    def test_annotate_judges_every_source_at_one_instant(self):
        wed = week_state.annotate_source_weeks(WEEKS, WEDNESDAY_NOON_CT)
        self.assertEqual(week_state.sources_in_state(wed, "lagging"), ["cbs", "razzball", "usatoday"])
        self.assertEqual(week_state.sources_in_state(wed, "stale"), [])
        thu = week_state.annotate_source_weeks(WEEKS, THURSDAY_1201_CT)
        self.assertEqual(week_state.sources_in_state(thu, "stale"), ["cbs", "razzball", "usatoday"])
        self.assertEqual(week_state.sources_in_state(thu, "current"),
                         ["cbsros", "espn", "fantasycalc", "fantasypros"])
        # The JEG-1177 fields ride along untouched.
        self.assertEqual(thu["cbs"]["basis"], "history_index")
        self.assertEqual(thu["cbs"]["label_week"], 7)


class ChainStatusStaleTest(ClockMixin, unittest.TestCase):
    """Stale is reported in the chain status and never fails the chain."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="week-stale-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def run_chain_with_cbs_on_week_4(self, name, clock):
        """Real execute_chain over faked stages (as in the per-source hold
        tests): every gated source promotes Week 5 except CBS, whose newest
        chart is still Week 4. Content week 5 opens Tue 2026-10-06."""
        from test_rebuild_chain_per_source_hold import FIXTURE_REL, run_chain

        def wrap(fake):
            def run_fn(cmd, **kw):
                ok, out = fake(cmd, **kw)
                if (Path(cmd[1]).name == "promote_comparison_section.py"
                        and Path(cmd[2]).name.startswith("cbs-")):
                    path = fake.repo / FIXTURE_REL
                    fixture = json.loads(path.read_text(encoding="utf-8"))
                    fixture["sources"]["cbs"].update(week_designated="Week 4", content_vintage="Week 4")
                    path.write_text(json.dumps(fixture))
                return ok, out
            return run_fn

        nfl_week.set_clock(clock)
        with contextlib.redirect_stdout(io.StringIO()):
            status, _before, after, _fake, repo = run_chain(self.tmp / name, {}, nfl_week=5, run_fn_wrap=wrap)
        written = json.loads((repo / "output" / "comparison-chain-status.json").read_text(encoding="utf-8"))
        return status, after, written

    def test_chain_passes_when_a_source_is_stale(self):
        # Friday 2026-10-09 12:00 CT: CBS is past Thursday's cutoff.
        status, after, written = self.run_chain_with_cbs_on_week_4(
            "stale", datetime(2026, 10, 9, 17, 0, tzinfo=timezone.utc))
        self.assertEqual(after["sources"]["cbs"]["week_designated"], "Week 4")
        self.assertIn("cbs", status["stale_sources"])
        self.assertEqual(status["source_weeks"]["cbs"]["state"], "stale")
        self.assertEqual(status["source_weeks"]["cbs"]["served_week"], 4)
        self.assertEqual(status["source_weeks"]["fantasycalc"]["state"], "current")
        # The chain is untouched by it.
        self.assertTrue(status["success"], status["failed"])
        self.assertEqual(status["outcome"], "green")
        self.assertEqual(status["failed"], [])
        self.assertEqual(status["held"], [])
        self.assertEqual(status["hold_severity"], "none")
        self.assertNotIn("cbs", status["held_detail"])
        self.assertIn("Thursday 12:00 CT", status["stale_rule"])
        self.assertEqual(written["stale_sources"], status["stale_sources"])

    def test_stale_and_lagging_runs_have_the_same_outcome(self):
        """The only difference between Wednesday (lagging) and Friday (stale)
        is the reported state: success, outcome, failed and holds match."""
        lag, *_ = self.run_chain_with_cbs_on_week_4("wed", datetime(2026, 10, 7, 17, 0, tzinfo=timezone.utc))
        stale, *_ = self.run_chain_with_cbs_on_week_4("fri", datetime(2026, 10, 9, 17, 0, tzinfo=timezone.utc))
        self.assertEqual(lag["source_weeks"]["cbs"]["state"], "lagging")
        self.assertIn("cbs", lag["lagging_sources"])
        self.assertNotIn("cbs", lag["stale_sources"])
        self.assertEqual(stale["source_weeks"]["cbs"]["state"], "stale")
        for key in ("success", "outcome", "failed", "held", "hold_severity", "held_detail"):
            self.assertEqual(lag[key], stale[key], key)

    def test_step_summary_warns_and_never_errors(self):
        import rebuild_comparison_chain as chain
        status = {"outcome": "green", "sources": {}, "held": [], "held_detail": {},
                  "stale_sources": ["cbs"],
                  "source_weeks": week_state.annotate_source_weeks(WEEKS, THURSDAY_1201_CT)}
        out = io.StringIO()
        summary = self.tmp / "summary.md"
        with contextlib.redirect_stdout(out):
            chain.write_step_summary(status, path=str(summary))
        self.assertIn("::warning title=Source stale (cbs)::", out.getvalue())
        self.assertNotIn("::error", out.getvalue())
        self.assertIn("STALE", summary.read_text(encoding="utf-8"))

    def test_status_still_written_when_the_clock_breaks(self):
        """A warning-only report never stops the status write."""
        import rebuild_comparison_chain as chain
        repo = self.tmp / "repo"
        results = {s: {"status": "ok", "promoted": 1, "sections": 1} for s in chain.SOURCES}
        with mock.patch.object(week_state, "annotate_source_weeks", side_effect=ValueError("bad clock")), \
                contextlib.redirect_stdout(io.StringIO()):
            status = chain.write_chain_status(repo, results, {"status": "ok"}, 8, "local")
        self.assertTrue(status["success"])
        self.assertTrue((repo / "output" / "comparison-chain-status.json").exists())


class ReferenceFreshnessStaleTest(ClockMixin, unittest.TestCase):
    """check_reference_freshness: one row per source, judged by its own week."""

    def load(self):
        spec = importlib.util.spec_from_file_location("crf_stale", ROOT / "pipelines" / "check_reference_freshness.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def report(self, now, history=None):
        crf = self.load()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "fixtures"
            root.mkdir()
            (root / "players.json").write_text(json.dumps({"meta": {}, "players": []}))
            (root / "comparison-sources-data.json").write_text(json.dumps({
                "built_at": "2026-10-28T12:00:00Z",
                "sources": {"usatoday": {"week_designated": "Week 7"},
                            "fantasycalc": {"week_designated": "Week 8"},
                            # Labelled week 8, but the history index matched its
                            # content to week 7: the served week decides.
                            "cbs": {"week_designated": "Week 8"}}}))
            index = None
            if history:
                index = Path(tmp) / "index.json"
                index.write_text(json.dumps(history))
            return crf.build_report(root, Path(tmp) / "out.json", nfl_week.today_ny(now), now=now,
                                    history_index=index)

    def rows(self, report):
        return {i["key"].rsplit(".", 1)[1]: i for i in report["items"] if i["key"].startswith("comparison.source.")}

    def test_wednesday_lagging_is_fine(self):
        rows = self.rows(self.report(WEDNESDAY_NOON_CT))
        self.assertEqual(rows["usatoday"]["status"], "lagging")
        self.assertEqual(rows["usatoday"]["color"], "yellow")
        self.assertTrue(rows["usatoday"]["freshness_ok"])
        self.assertFalse(rows["usatoday"]["stale"])
        self.assertEqual(rows["fantasycalc"]["status"], "current")

    def test_thursday_1201_ct_is_stale_and_still_a_warning(self):
        report = self.report(THURSDAY_1201_CT)
        rows = self.rows(report)
        self.assertEqual(rows["usatoday"]["status"], "stale")
        self.assertEqual(rows["usatoday"]["color"], "red")
        self.assertEqual(rows["usatoday"]["stale_after"], "2026-10-29T12:00:00-05:00")
        self.assertFalse(rows["usatoday"]["enforced"])
        self.assertEqual(report["summary"]["comparison_sources_stale"], ["usatoday"])
        self.assertEqual(report["summary"]["enforced_expired_count"], 0)
        # 11:59 CT is still lagging.
        self.assertEqual(self.rows(self.report(THURSDAY_1159_CT))["usatoday"]["status"], "lagging")

    def test_served_week_from_the_history_index_decides(self):
        history = {"fixture_built_at": "2026-10-28T12:00:00Z", "served": {"cbs": {"week": 7}}}
        rows = self.rows(self.report(THURSDAY_1201_CT, history))
        self.assertEqual(rows["cbs"]["served_week"], 7)
        self.assertEqual(rows["cbs"]["label_week"], 8)
        self.assertEqual(rows["cbs"]["served_week_basis"], "history_index")
        self.assertEqual(rows["cbs"]["status"], "stale")
        # Without the index the label is all there is.
        self.assertEqual(self.rows(self.report(THURSDAY_1201_CT))["cbs"]["status"], "current")

    def test_replayed_day_is_judged_at_its_end(self):
        crf = self.load()
        nfl_week.set_clock(datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc))
        moment = crf.judging_instant(date(2026, 10, 29))
        self.assertEqual(moment.astimezone(nfl_week.NEW_YORK).date(), date(2026, 10, 29))
        self.assertEqual(week_state.source_week_status(7, moment)["state"], "stale")
        nfl_week.set_clock(THURSDAY_1159_CT)
        self.assertEqual(crf.judging_instant(date(2026, 10, 29)), THURSDAY_1159_CT)


class WeeklyFreshnessScriptTest(unittest.TestCase):
    """scripts/check_weekly_freshness.py reports trade-chart sources by their
    own week; stale is an annotation, never a breach."""

    def setUp(self):
        self.sbclient = mock.MagicMock()
        sys.modules["sbclient"] = self.sbclient
        saved = list(sys.path)
        try:
            spec = importlib.util.spec_from_file_location("cwf_stale", ROOT / "scripts" / "check_weekly_freshness.py")
            self.mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.mod)
        finally:
            sys.path[:] = saved
        tmp = tempfile.mkdtemp(prefix="cwf-")
        self.addCleanup(shutil.rmtree, tmp, True)
        self.status_path = Path(tmp) / "comparison-chain-status.json"
        self.status_path.write_text(json.dumps({"source_weeks": WEEKS}))

    def run_main(self, now, environ=None):
        today = nfl_week.today_ny(now)
        self.sbclient.get.return_value = [{
            "has_current": True, "season": 2026, "week": nfl_week.game_week(today), "signal_count": 5,
            "run_created_at": today.isoformat(), "bundle_built_at": today.isoformat(), "current_run_count": 1}]

        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):  # noqa: ARG003
                return now

        class FrozenDt:
            datetime = FrozenDatetime
            date = date
            timezone = timezone

        env = {"DDF_CHAIN_STATUS": str(self.status_path), **(environ or {})}
        buf = io.StringIO()
        with mock.patch.object(self.mod, "dt", FrozenDt), mock.patch.dict(os.environ, env), \
                contextlib.redirect_stdout(buf):
            code = self.mod.main()
        return code, buf.getvalue()

    def test_wednesday_lagging_is_info_only(self):
        code, out = self.run_main(WEDNESDAY_NOON_CT)
        self.assertEqual(code, 0, out)
        self.assertIn("source cbs: serves Week 7 (calendar Week 8) -> lagging", out)
        self.assertNotIn("WARNING", out)

    def test_thursday_1201_ct_stale_warns_and_still_exits_zero(self):
        code, out = self.run_main(THURSDAY_1201_CT, {"GITHUB_ACTIONS": "true"})
        self.assertEqual(code, 0, out)
        self.assertIn("::warning::source cbs: serves Week 7 (calendar Week 8) -> stale", out)
        self.assertNotIn("::error::", out)
        self.assertIn("OK:", out)

    def test_missing_status_file_is_silent(self):
        self.assertEqual(self.mod.source_week_report(THURSDAY_1201_CT, str(self.status_path) + ".nope"), [])


class WatchdogStaleTest(ClockMixin, unittest.TestCase):
    def test_watchdog_uses_the_shared_rule(self):
        import _common
        self.assertEqual(_common.source_week_state(7, WEDNESDAY_NOON_CT)["state"], "lagging")
        self.assertEqual(_common.source_week_state(7, THURSDAY_1201_CT)["state"], "stale")
        self.assertEqual(_common.source_week_state(None, THURSDAY_1201_CT)["state"], "unknown")

    def test_not_published_result_carries_the_source_week_state(self):
        """A quiet "not published yet" skip reports the source's own newest
        week and its state; stale warns but the skip stays a skip."""
        import ingest_common as ic
        import ingest_cbs
        nfl_week.set_clock(THURSDAY_1201_CT)
        cfg = dict(ingest_cbs.CFG, overdue_after_days=None)  # isolate from the overdue guard

        def miss(week):
            raise ingest_cbs.CFG["discovery_failed_cls"]("nothing", quiet=True, newest_week=7)

        out = io.StringIO()
        with tempfile.TemporaryDirectory() as td, contextlib.redirect_stdout(out):
            res = ic.run_ingest(cfg, week=8, discover_fn=miss, pull_fn=lambda u: self.fail("no pull"),
                                db=object(), state_dir=td, pulls_dir=td)
        self.assertEqual(res["status"], "not_published")
        self.assertEqual(res["week_state"], "stale")
        self.assertEqual(res["stale_after"], "2026-10-29T12:00:00-05:00")
        self.assertIn("::warning title=cbs stale::", out.getvalue())
        nfl_week.set_clock(WEDNESDAY_NOON_CT)
        with tempfile.TemporaryDirectory() as td, contextlib.redirect_stdout(io.StringIO()):
            res = ic.run_ingest(cfg, week=8, discover_fn=miss, pull_fn=lambda u: self.fail("no pull"),
                                db=object(), state_dir=td, pulls_dir=td)
        self.assertEqual(res["week_state"], "lagging")


if __name__ == "__main__":
    unittest.main()
