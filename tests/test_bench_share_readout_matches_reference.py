"""JEG-536 / ES-14: the engine's bench-share readout matches the Python
reference, expected_starts_model.bench_share_readout(), within 0.05
percentage points, at all 12 settings and at three non-default reader
settings; and the readout responds to the settings and the override.

Runs the built engine page headless (dist/, served like the other render
tests), sets each league setting and reader setting through the page's own
controls (TradeValueCurveControls: setScoring, setTeams, setOptimizeFor,
setInjuryHistory, setProjectionConfidence, setLeagueWeeks,
setBenchShareOverride) and reads getBenchShareReadout().

Fails before JEG-536: the engine has no getBenchShareReadout (and no
expected-starts pipeline), so every setting is missing its readout.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import ENGINE_URL, serve

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipelines"))

TOL = 0.0005   # 0.05 percentage points
POSITIONS = ("QB", "RB", "WR", "TE")
SCORINGS = ("standard", "half_ppr", "ppr")
TEAMS = (8, 10, 12, 14)
# (scoring, teams, engine settings, resolve() keyword arguments)
NON_DEFAULT = [
    ("ppr", 12, {"optimizeFor": "playoffs"}, {"objective": "playoffs"}),
    ("half_ppr", 10, {"injuryHistory": "all", "projectionConfidence": 0.5},
     {"injury_history": "all", "projection_confidence": 0.5}),
    ("standard", 14, {"optimizeFor": "regular", "regularSeasonEnd": 13, "playoffWeeks": [14, 16]},
     {"objective": "regular", "league_weeks": {"regular_season_end": 13, "playoff_weeks": [14, 16]}}),
]

READ = """async ([scoring, teams, lineup, override]) => {
  const c = window.TradeValueCurveControls;
  c.setLineupSettings({regularSeasonEnd: 14, playoffWeeks: [15, 17], optimizeFor: 'season',
    injuryHistory: 'recent', projectionConfidence: 1, benchShareOverride: null}, false);
  c.setScoring(scoring); c.setTeams(teams);
  if (lineup) c.setLineupSettings(lineup, false);
  if (override !== null) c.setBenchShareOverride(override, false);
  const readout = c.getBenchShareReadout ? c.getBenchShareReadout() : null;
  return {readout, benchShare: c.getBenchShare(), settings: c.getLineupSettings ? c.getLineupSettings() : null};
}"""


def setUpModule():
    _render_env.ensure_built()


def engine_readouts(cases):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise _render_env.unavailable(f"playwright not installed: {exc}")
    out = []
    with serve() as base, sync_playwright() as pw:
        exe = _render_env.chromium_executable(pw)
        browser = pw.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
        try:
            page = browser.new_page()
            page.goto(f"{base}/{ENGINE_URL}")
            page.wait_for_function("() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()",
                                   timeout=120000)
            for case in cases:
                out.append(page.evaluate(READ, list(case)))
        finally:
            browser.close()
    return out


class BenchShareReadoutMatchesReference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import expected_starts_model as esm
        import value_reference as ref
        cls.esm = esm
        cls.inp = ref.Inputs.load(ref.FIXTURE, ref.PLAYERS)
        cls.cfg = json.loads((REPO / "config" / "lineup_parameters.json").read_text(encoding="utf-8"))
        cls.hist = ref.History(ref.HISTORY)
        cls.cases = ([(sc, t, None, None) for sc in SCORINGS for t in TEAMS]
                     + [(sc, t, lineup, None) for sc, t, lineup, _ in NON_DEFAULT]
                     + [("ppr", 12, None, 0.10)])
        cls.engine = engine_readouts(cls.cases)

    def reference(self, scoring, teams, **settings):
        return self.esm.bench_share_readout(self.inp, scoring, teams, self.cfg, hist=self.hist, **settings)

    def assert_matches(self, got, want, label):
        r = got["readout"]
        self.assertIsNotNone(r, f"{label}: the engine has no bench-share readout")
        self.assertEqual(r["method"], "expected-starts", label)
        for p in POSITIONS:
            self.assertAlmostEqual(r[p], want["bench_share"][p], delta=TOL, msg=f"{label} {p}")
        self.assertAlmostEqual(r["overall"], want["bench_share_overall"], delta=TOL, msg=f"{label} overall")

    def test_twelve_settings_at_the_defaults(self):
        for (sc, t, _, _), got in zip(self.cases[:12], self.engine[:12]):
            with self.subTest(setting=f"{sc}/{t}"):
                self.assert_matches(got, self.reference(sc, t), f"{sc}/{t}")
                self.assertFalse(got["readout"]["override"])
                # The share in effect is the computed overall share.
                self.assertAlmostEqual(got["benchShare"], got["readout"]["overall"], places=12)
                self.assertTrue(0.05 < got["readout"]["overall"] < 0.15, got["readout"])

    def test_three_non_default_settings(self):
        base = {f"{sc}/{t}": got for (sc, t, _, _), got in zip(self.cases[:12], self.engine[:12])}
        for (sc, t, lineup, kwargs), got in zip(NON_DEFAULT, self.engine[12:15]):
            with self.subTest(setting=f"{sc}/{t} {lineup}"):
                self.assert_matches(got, self.reference(sc, t, **kwargs), f"{sc}/{t} {lineup}")
                # The setting reached the pipeline: the readout moved.
                moved = max(abs(got["readout"][p] - base[f"{sc}/{t}"]["readout"][p]) for p in POSITIONS)
                self.assertGreater(moved, 1e-6, f"{sc}/{t} {lineup}: readout did not move")

    def test_override_is_reported_and_priced(self):
        got = self.engine[15]
        r = got["readout"]
        self.assertTrue(r["override"])
        self.assertAlmostEqual(r["overrideValue"], 0.10, places=12)
        self.assertAlmostEqual(r["fillInShare"], 0.10, places=9)
        self.assertAlmostEqual(got["benchShare"], 0.10, places=12)
        want = self.reference("ppr", 12, bench_share_override=0.10)
        self.assertTrue(want["override"])
        for p in POSITIONS:
            self.assertAlmostEqual(r[p], want["bench_share"][p], delta=TOL, msg=p)


if __name__ == "__main__":
    unittest.main()
