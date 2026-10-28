"""A build with seeded holds passes the gate (JEG-569).

Jeremy (JEG-520): "hold a source, never take the whole site down".
Jeremy (JEG-569 part 2, 2026-10-12): "gray out the source, run no calcs on
it, gray out its derivatives. No computation on old data."

This test seeds that state on the committed fixture: one published chart
(FantasyCalc) and one projection (Razzball) held, with validationHold set.
Combos are KEPT so the engine includes the held source in the pipeline
(weights, pie, universe) -- removing a source renormalizes every other
source's values.  The page hides a held source's curves via validationHold.

It requires:

1. held sections keep their combos and carry a validationHold;
2. the fixture-level gate checks pass on that build: tests.test_static_export
   (run on the seeded fixture) and the test_superflex identity check.

Tests that need an unheld baseline read tests/_holds.without_held_sources.
"""
from __future__ import annotations

import json
import os
import copy
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipelines"))

import fidelity_hold as fh  # noqa: E402

FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
CHART, PROJECTION = "fantasycalc", "razzball"
HOLDS = {root: {"stage": "publisher_vs_stored", "reason": "fidelity: publisher_vs_stored",
                "identity": f"seeded-{root}", "since": "2026-10-10T21:40:15Z", "summary": "seeded hold"}
         for root in (CHART, PROJECTION)}


def seeded_build() -> tuple[dict, dict]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for section in fixture["sources"].values():
        if isinstance(section, dict):
            section.pop("validationHold", None)
            section.pop("promotionHold", None)
    held, report = fh.apply_fidelity_holds(fixture, HOLDS, 5)
    return fixture, held


class SeededHoldBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current, cls.held = seeded_build()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "comparison-sources-data.json"
        cls.path.write_text(json.dumps(cls.held), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_held_chart_keeps_combos_and_has_hold(self):
        """JEG-569 part 2: combos are kept so the engine can include the held
        source in the pipeline (weights, pie, universe). The validationHold
        flag tells the page to gray it out."""
        section = self.held["sources"][CHART]
        self.assertTrue(section.get("combos"), f"{CHART} combos should be preserved (not stripped)")
        hold = section["validationHold"]
        self.assertEqual(hold["reason"], "fidelity: publisher_vs_stored")
        self.assertEqual(hold["root"], CHART)

    def test_held_projection_keeps_combos_and_has_hold(self):
        section = self.held["sources"][PROJECTION]
        self.assertTrue(section.get("combos"), f"{PROJECTION} combos should be preserved (not stripped)")
        hold = section["validationHold"]
        self.assertEqual(hold["reason"], "fidelity: publisher_vs_stored")
        self.assertEqual(hold["root"], PROJECTION)

    def test_unheld_source_keeps_its_combos(self):
        """At least one unheld source must keep its combos intact."""
        for key in ("usatoday", "fantasypros", "cbs", "espn", "cbsros"):
            section = self.held["sources"].get(key)
            if isinstance(section, dict) and not section.get("validationHold"):
                self.assertTrue(section.get("combos"), f"{key} combos should not be empty")
                return
        self.fail("no unheld source found to verify")

    def test_static_export_passes_on_the_held_build(self):
        env = {**os.environ, "STATIC_EXPORT_COMPARISON": str(self.path)}
        proc = subprocess.run([sys.executable, "-m", "unittest", "tests.test_static_export"], cwd=str(ROOT),
                              env=env, capture_output=True, text=True, timeout=600)
        tail = "\n".join(proc.stderr.splitlines()[-60:])
        self.assertEqual(proc.returncode, 0, f"test_static_export fails on a held build:\n{tail}")

    def test_superflex_identity_passes_on_the_held_build(self):
        from tests import test_superflex  # noqa: PLC0415
        problems = test_superflex.identity_problems(fixture=self.path)
        self.assertEqual(problems, [], "\n".join(problems[:10]))


class AmberHoldNotHiddenTest(unittest.TestCase):
    """JEG-726: amber-held sources stay in DDF/bench-share/indexed (not hidden).

    Negative-test: with a red hold, the source IS hidden. This proves the
    code that was broken in PR 704 now distinguishes the two levels.
    """

    @classmethod
    def setUpClass(cls):
        import value_reference as ref  # noqa: PLC0415
        cls.ref = ref
        cls.fixture_path = FIXTURE
        cls.players_path = ref.PLAYERS

    def _fixture_with_hold(self, root, hold_level):
        """Return a fixture with one source held at the given level."""
        fixture = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        # Strip all holds first
        for section in fixture["sources"].values():
            if isinstance(section, dict):
                section.pop("validationHold", None)
                section.pop("promotionHold", None)
        # Apply one hold at the given level
        section = fixture["sources"].get(root)
        if isinstance(section, dict):
            section["validationHold"] = {
                "reason": f"fidelity: stored_vs_chart",
                "root": root, "stage": "stored_vs_chart", "week": 6,
                "hold_level": hold_level,
            }
        return fixture

    def _resolve_hidden(self, fixture, scoring="standard", teams=10):
        """Build a Setting and return its hidden set."""
        import tempfile as _tmp  # noqa: PLC0415
        with _tmp.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(fixture, f)
            f.flush()
            inp = self.ref.Inputs.load(f.name, self.players_path)
        setting = self.ref.Setting(inp, scoring, teams)
        state = setting.state()
        return state["hidden"], state["eligible"]

    def test_red_hold_hides_source(self):
        """A red-held source must appear in hidden (JEG-569 semantics)."""
        fixture = self._fixture_with_hold("espn", "red")
        hidden, eligible = self._resolve_hidden(fixture)
        self.assertIn("espn", hidden, "red-held source should be hidden")
        self.assertIn("espn", eligible, "red-held source should still be eligible (pipeline)")

    def test_amber_hold_does_not_hide_source(self):
        """An amber-held source must NOT appear in hidden (JEG-726)."""
        fixture = self._fixture_with_hold("espn", "amber")
        hidden, eligible = self._resolve_hidden(fixture)
        self.assertNotIn("espn", hidden, "amber-held source must NOT be hidden")
        self.assertIn("espn", eligible, "amber-held source should be eligible")

    def test_hold_without_level_defaults_to_red_hidden(self):
        """A hold without an explicit hold_level defaults to red (hidden)."""
        fixture = self._fixture_with_hold("espn", "red")
        # Remove hold_level to simulate pre-JEG-726 data
        fixture["sources"]["espn"]["validationHold"].pop("hold_level")
        hidden, _ = self._resolve_hidden(fixture)
        self.assertIn("espn", hidden, "hold without level should default to red (hidden)")


class SourceScenarioFixtureTest(unittest.TestCase):
    """JEG-1204: every root, held now, one week behind, and both.

    This module already runs in test-core and preview's shard 1. Keeping the
    matrix here gives both gates the same coverage without workflow changes.
    All replay data is isolated; no committed fixture or generated asset is
    replaced. A hold retains the source's inputs, but excludes its DDF vote.
    """

    @classmethod
    def setUpClass(cls):
        from tests import _render_env
        _render_env.ensure_built()

    def check_scenario(self, scenario):
        import value_reference as ref
        from check_rank_guard import check_fixture
        from tests import test_week_history as W

        self.assertEqual(scenario.index["served"][scenario.root]["week"], scenario.source_week)
        self.assertEqual(scenario.source_week, scenario.week - int(scenario.lagging))
        expected_held = {scenario.root} if scenario.held else set()
        self.assertEqual(W.held_roots(scenario.fixture["sources"]), expected_held)
        # A held fixture retains all combos; a hold must never exempt corrupt
        # saved Indexed values from the existing fixture rank guard.
        report = check_fixture(scenario.fixture)
        self.assertEqual(report["status"], "pass", report)
        self.assertEqual({c["source"] for c in report["checks"] if "skipped" not in c},
                         set(ref.PUBLISHED))

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            fixture, players, history = tmp / "fixture.json", tmp / "players.json", tmp / "history"
            fixture.write_text(json.dumps(scenario.fixture), encoding="utf-8")
            players.write_text(json.dumps(scenario.players), encoding="utf-8")
            shutil.copytree(W.HISTORY, history)
            (history / "index.json").write_text(json.dumps(scenario.index), encoding="utf-8")
            inp = ref.Inputs.load(fixture, players, today=date.fromisoformat(W._fixture_today(scenario.fixture)))
            hist = ref.History(history)
            setting = ref.Setting(inp, "ppr", 12, hist=hist)
            view, state = setting.week_view(), setting.state()
            self.assertIsNotNone(view)
            self.assertEqual(view["week"], scenario.week)
            self.assertEqual(view["served_weeks"][scenario.root], scenario.source_week)
            self.assertEqual(set(state["included"]), set(ref.SOURCES) - (
                {scenario.root} if scenario.lagging else set()))
            rows = setting.rows("indexed")
            self.assertTrue(rows, "empty reference output")
            if scenario.lagging:
                self.assertNotIn(scenario.root, state["eligible"])
                if not scenario.held:
                    own = ref.Setting(inp, "ppr", 12, hist=hist, week=scenario.source_week)
                    self.assertEqual(own.week_view()["week"], scenario.source_week)
                    self.assertIn(scenario.root, own.state()["included"])
                    self.assertTrue(own.rows("indexed"))
            elif scenario.held:
                self.assertIn(scenario.root, state["eligible"])
                self.assertIn(scenario.root, state["hidden"])

    def test_held_chart_rank_corruption_still_fails(self):
        from check_rank_guard import check_fixture
        from tests._hold_scenarios import source_scenario
        from tests.test_rank_guard import PUBLISHED
        for root in PUBLISHED:
            with self.subTest(root=root):
                scenario = source_scenario(root, held=True)
                broken = copy.deepcopy(scenario.fixture)
                combo = next(iter(broken["sources"][root]["combos"].values()))
                ordered = sorted(combo["reindexed"], key=lambda k: combo["native"][k], reverse=True)
                first, last = ordered[0], ordered[-1]
                self.assertGreater(combo["native"][first], combo["native"][last])
                combo["reindexed"][first], combo["reindexed"][last] = (
                    combo["reindexed"][last], combo["reindexed"][first])
                report = check_fixture(broken)
                self.assertEqual(report["status"], "fail")
                self.assertEqual({c["source"] for c in report["checks"] if not c["ok"]}, {root})

    def test_current_hold_replays_current_week_even_if_live_source_already_lags(self):
        from tests import _hold_scenarios as H
        original_read = H._read
        for root in H.ROOTS:
            with self.subTest(root=root):
                lagged = H.source_scenario(root, lagging=True)
                inputs = {H.DIST / H.FIXTURE_ASSET: lagged.fixture,
                          H.DIST / H.INDEX_ASSET: lagged.index,
                          H.ROOT / "data/fixtures/current/players.json": lagged.players}

                def read(path):
                    return copy.deepcopy(inputs[path]) if path in inputs else original_read(path)

                with patch.object(H, "_read", side_effect=read):
                    restored = H.source_scenario(root, held=True)
                self.assertIn(root, restored.normalized_roots)
                self.assertEqual({r["week"] for r in restored.index["served"].values()}, {restored.week})
                self.check_scenario(restored)


class SourceScenarioRenderTest(unittest.TestCase):
    """Run the real gate checks on the same per-source replay, sequentially."""

    @classmethod
    def setUpClass(cls):
        from tests import _render_env
        _render_env.ensure_built()
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(
                    args=_render_env.HERMETIC_ARGS,
                    executable_path=_render_env.chromium_executable(playwright))
            except Exception as exc:
                raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
            browser.close()

    def check_scenario(self, scenario):
        from playwright.sync_api import sync_playwright
        from tests import _render_env, test_superflex as S, test_rank_guard as R, test_week_history as W
        self.assertEqual(S.page_problems(S.collect_page(data_overrides=scenario.overrides),
                                        scenario.fixture), [])
        self.assertEqual(W.collect(scenario.overrides), [])
        with W._server(scenario.overrides) as url, sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                args=_render_env.HERMETIC_ARGS,
                executable_path=_render_env.chromium_executable(playwright))
            page = browser.new_page()
            try:
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.add_init_script(f"window.TRADE_VALUE_TODAY = {json.dumps(W._fixture_today(scenario.fixture))};")
                page.goto(url, wait_until="networkidle")
                page.wait_for_function(W.READY)
                swept = {}
                for scoring in ("standard", "half", "ppr"):
                    page.evaluate("s => { const c = window.TradeValueCurveControls; c.setScoring(s); c.setTeams(12); }",
                                  scoring)
                    swept[scoring] = R.read_setting(page, R.PUBLISHED)
                self.assertEqual(errors, [])
                self.assertEqual(R.order_problems(swept), [])
                # A skip is legitimate only for the specifically held lagging
                # chart with no offered week view. Healthy lagging charts are
                # actually read and checked in their own view.
                for result in swept.values():
                    self.assertEqual(set(result["lagging"]), {scenario.root} if (
                        scenario.held and scenario.lagging and scenario.root in R.PUBLISHED) else set())
                    if scenario.lagging and not scenario.held and scenario.root in R.PUBLISHED:
                        self.assertEqual(result["weeks"][scenario.root], scenario.source_week)
            finally:
                browser.close()

    def check_corruption(self, root):
        from tests._hold_scenarios import source_scenario
        from tests import test_week_history as W
        scenario = source_scenario(root, lagging=True, corrupt=True)
        failures = W.collect(scenario.overrides)
        self.assertTrue(any(f.startswith(f"{root} served week != chart") for f in failures), failures)


def _matrix_case(root, held, lagging):
    def test(self):
        from tests._hold_scenarios import source_scenario
        self.check_scenario(source_scenario(root, held=held, lagging=lagging))
    return test


def _corruption_case(root):
    def test(self):
        self.check_corruption(root)
    return test


# Individual names expose the failing source and scenario in PR CI, and let a
# developer rerun one case without replaying the other six sources.
from value_check import SOURCE_DERIVED  # noqa: E402

for _root in SOURCE_DERIVED:
    for _mode, _held, _lagging in (("held", True, False), ("lagging", False, True),
                                 ("held_lagging", True, True)):
        for _case in (SourceScenarioFixtureTest, SourceScenarioRenderTest):
            setattr(_case, f"test_{_root}_{_mode}", _matrix_case(_root, _held, _lagging))
    setattr(SourceScenarioRenderTest, f"test_{_root}_corrupt", _corruption_case(_root))

# unittest inspects every module attribute, including underscored aliases.
# Leaving the loop's class variable behind would run the render matrix twice.
del _root, _mode, _held, _lagging, _case


if __name__ == "__main__":
    unittest.main()
