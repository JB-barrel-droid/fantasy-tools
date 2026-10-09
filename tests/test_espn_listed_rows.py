"""JEG-496: every player on ESPN's list gets a row, ESPN 0.0 included.

Jeremy, 2026-10-08 (JEG-486): every player a current-week source prices gets a
row, and ESPN listing a player at 0 shows 0, not "—".

What went wrong (main 0dbf4bc7, 2026-10-09): the page's rows were the union of
the source maps, and the ESPN anchor map is the live two-tier refit, which
keeps only starter and bench players. A waiver-tier player at ESPN 0.0 whom no
other source prices was in no map, so he had no row: 20 players at every
setting, De'Von Achane among them (ESPN: injured reserve, 0 projected for weeks
4-18). The clean-room spec reference counted them as SG-12 / no_engine_row.

The test requires, for all 12 scoring x team combos, that every player in the
built ESPN leg (the combo the page reads) has a row in the engine
(getAllRows) and in the Python reference (value_reference.Setting.rows), and
that a player ESPN projects at zero shows ESPN 0 on both.

Discrimination (test_guard_fails_on_pre_fix_widget): the engine check fails on
the pre-fix curve-widget.js (0dbf4bc7, read from git).
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from datetime import date

from tests._dist_server import DIST, ENGINE_PAGE, ROOT, chromium_executable, serve

sys.path.insert(0, str(ROOT / "pipelines"))
import value_reference as ref  # noqa: E402
from tests import _render_env  # noqa: E402


def setUpModule():
    _render_env.ensure_built()


PRE_FIX_COMMIT = "0dbf4bc7"
SCORINGS = ("standard", "half_ppr", "ppr")
TEAMS = (8, 10, 12, 14)
ENGINE_SCORING = {"standard": "standard", "half_ppr": "half", "ppr": "full"}
ACHANE = 4237
READ = """([s, t]) => {
  const c = window.TradeValueCurveControls;
  c.setScoring(s); c.setTeams(t);
  return c.getAllRows().map(r => [r.player_key, r.values.espn ?? null]);
}"""


def espn_listed(inp, scoring, teams):
    cell = inp.cell("espn", scoring, teams) or {}
    return {int(k) for k in (cell.get("values") or {}) if int(k) in inp.players}


def problems(rows_by_setting, inp):
    """{setting: {...}} for settings where an ESPN-listed player has no row or
    an ESPN-zero player shows anything but ESPN 0."""
    out = {}
    for (scoring, teams), rows in rows_by_setting.items():
        listed = espn_listed(inp, scoring, teams)
        missing = sorted(listed - set(rows))
        not_zero = sorted(k for k in listed & set(rows)
                          if inp.players[k]["espn_zero"] and rows[k] != 0)
        if missing or not_zero:
            out[f"{scoring}_{teams}"] = {
                "n_missing": len(missing),
                "missing": [inp.players[k]["name"] for k in missing[:5]],
                "zero_not_shown_as_0": [(inp.players[k]["name"], rows[k]) for k in not_zero[:5]],
            }
    return out


def read_engine(overrides=None):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    with sync_playwright() as p:
        exe = chromium_executable(p)
        if exe is None:
            raise _render_env.unavailable("no Chromium available")
        browser = p.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=exe)
        try:
            with serve(DIST, overrides) as base:
                page = browser.new_page()
                page.goto(base + "/classic/", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueCurveControls && window.TradeValueCurveDiagnostics",
                                       timeout=30000)
                return {(s, t): {int(k): v for k, v in page.evaluate(READ, [ENGINE_SCORING[s], t])}
                        for s in SCORINGS for t in TEAMS}
        finally:
            browser.close()


def load_inputs():
    return ref.Inputs.load(today=date(2026, 10, 9))


class ReferenceEspnListedRowsTest(unittest.TestCase):
    def test_reference_gives_every_espn_listed_player_a_row(self):
        inp = load_inputs()
        rows = {}
        for s in SCORINGS:
            for t in TEAMS:
                setting_rows = ref.Setting(inp, s, t).rows("indexed")
                rows[(s, t)] = {k: v.get("espn") for k, v in setting_rows.items()}
        self.assertIn(ACHANE, espn_listed(inp, "ppr", 12))
        found = problems(rows, inp)
        self.assertEqual(found, {}, json.dumps(found, indent=1)[:3000])
        self.assertEqual(rows[("ppr", 12)][ACHANE], 0.0)


class EngineEspnListedRowsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ENGINE_PAGE.exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")
        cls.inp = load_inputs()

    def test_engine_gives_every_espn_listed_player_a_row(self):
        rows = read_engine()
        found = problems(rows, self.inp)
        self.assertEqual(found, {}, json.dumps(found, indent=1)[:3000])
        self.assertEqual(rows[("ppr", 12)][ACHANE], 0)

    def test_guard_fails_on_pre_fix_widget(self):
        proc = subprocess.run(["git", "show", f"{PRE_FIX_COMMIT}:app/trade-value-chart/assets/curve-widget.js"],
                              cwd=ROOT, capture_output=True)
        if proc.returncode != 0:
            self.skipTest(f"{PRE_FIX_COMMIT} not in this clone")
        found = problems(read_engine({"assets/curve-widget.js": proc.stdout}), self.inp)
        self.assertEqual(len(found), len(SCORINGS) * len(TEAMS), sorted(found))


if __name__ == "__main__":
    unittest.main()
