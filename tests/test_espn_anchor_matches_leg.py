"""JEG-493: the ESPN anchor at every league size is the two-tier leg built at
that league size, not a linear remap of the 12-team leg.

What went wrong (main 0dbf4bc7, 2026-10-09): the fixture's ESPN section holds
the 12-team leg for every combo (build_espn_section_from_ddf_leg pins 12t). The
engine priced the anchor by fitting one line per position x tier from that
12-team value to the live two-tier value at the active team count
(alpha + beta * published). At 14 teams the bench reaches players the 12-team
leg prices at 0.0, so every one of them landed on the intercept: ppr/14 RB
Kyle Juszczyk (2.29 ppg, leg 0.04) and AJ Dillon (4.71 ppg, leg 3.59) both
showed 2.73, with 4-15 such ties per position, up to 2.7 off the leg. At 8 and
10 teams the line only approximated the leg (within about 0.2).

This test requires, for all 12 scoring x team combos on the built dist/, that
every player the engine's `espn` series prices equals the value the pipeline's
own leg builder (build_ddf_two_tier_leg: build_position_tiers, calibrate_tiers,
price_for_projection, 70/max scale) gives from the same ESPN per-game
projections at 0.15 bench share, within TOL; and, at ppr/14, that Juszczyk is
priced below Dillon (the order follows the projections).
"""
from __future__ import annotations

import json
import sys
import unittest

from tests._dist_server import DIST, ENGINE_PAGE, ROOT, chromium_executable, serve

sys.path.insert(0, str(ROOT / "pipelines"))
from build_ddf_two_tier_leg import (  # noqa: E402
    POSITIONS, REF_FLEX_COUNT, REF_FLEX_ELIGIBLE, REF_SLOTS,
    bench_mix_for_teams, build_position_tiers, calibrate_tiers, price_for_projection,
)
from tests import _render_env  # noqa: E402


def setUpModule():
    _render_env.ensure_built()


SCORINGS = ("standard", "half_ppr", "ppr")
TEAMS = (8, 10, 12, 14)
TOL = 0.01
READ = """([s, t]) => {
  const c = window.TradeValueCurveControls;
  c.setScoring(s); c.setTeams(t);
  return c.getAllRows().map(r => [r.player_key, r.values.espn, r.name]);
}"""


def built_leg(players, scoring, teams):
    """player_key -> 70-scale value, exactly as build_ddf_two_tier_leg.build_leg prices it."""
    lists = {pos: [] for pos in POSITIONS}
    for p in players:
        x = (p.get("espn_ppg") or {}).get(scoring)
        if p.get("pos") in lists and isinstance(x, (int, float)):
            lists[p["pos"]].append({"id": int(p["player_key"]), "x": float(x)})
    pool = build_position_tiers(lists, teams, dict(REF_SLOTS), REF_FLEX_COUNT,
                                list(REF_FLEX_ELIGIBLE), bench_mix_for_teams(teams))
    calibration, _ = calibrate_tiers(pool, 0.15)
    raw = {d["id"]: price_for_projection(d["x"], calibration[pos]) for pos in POSITIONS for d in lists[pos]}
    scale = 70.0 / max(raw.values())
    return {key: value * scale for key, value in raw.items()}


def problems(snapshots, players):
    out = {}
    for (scoring, teams), rows in snapshots.items():
        leg = built_leg(players, scoring, teams)
        off = sorted(((abs(value - leg[int(key)]), name, round(value, 2), round(leg[int(key)], 2))
                      for key, value, name in rows
                      if isinstance(value, (int, float)) and int(key) in leg
                      and abs(value - leg[int(key)]) > TOL), reverse=True)
        if off:
            out[f"{scoring}_{teams}"] = {"n_off": len(off), "worst (|d|, name, engine, leg)": off[:5]}
    return out


def read_all():
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
            with serve(DIST) as base:
                page = browser.new_page()
                page.goto(base + "/classic/", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueCurveControls && window.TradeValueCurveDiagnostics",
                                       timeout=30000)
                return {(s, t): page.evaluate(READ, [s, t]) for s in SCORINGS for t in TEAMS}
        finally:
            browser.close()


class EspnAnchorMatchesLegTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ENGINE_PAGE.exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")
        cls.players = json.loads((ROOT / "data" / "fixtures" / "current" / "players.json")
                                 .read_text(encoding="utf-8"))["players"]
        cls.snapshots = read_all()

    def test_anchor_equals_built_leg_at_every_league_size(self):
        found = problems(self.snapshots, self.players)
        self.assertEqual(found, {}, json.dumps(found, indent=1)[:3000])

    def test_bench_order_follows_projections_at_14_teams(self):
        by_name = {name: value for _, value, name in self.snapshots[("ppr", 14)]}
        fullback, back = by_name.get("Kyle Juszczyk"), by_name.get("AJ Dillon")
        if fullback is None or back is None:
            self.skipTest("Juszczyk / Dillon not both priced in this week's data")
        self.assertLess(fullback, back)


if __name__ == "__main__":
    unittest.main()
