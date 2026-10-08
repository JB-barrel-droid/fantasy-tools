"""V2-TIER-VS-ESPN-LEG: the ESPN tier shown in every table comes from the same
roster model that prices the ESPN line.

What went wrong (origin/main dac0ff2, 2026-10-08): the tier (`espnRole`) came
from the raw value-above-waivers rows (ValueModel.projectionRoles: surplus over
each position's starter baseline, custom roster shape) while the ESPN value
comes from the two-tier leg's pool (reference slots, legacy bench mix by
teams). At Full PPR 12 teams 18 players tiered "waiver" carried a positive ESPN
value and 10 tiered "bench" had none; across the 12 league shapes 17-26 and
10-17.

The tier now comes from the two-tier pool. This test requires, for all 12
scoring x team combos on the built dist/:

  * browser/server parity: every player's espnRole equals the tier the
    pipeline's own pool builder (build_ddf_two_tier_leg.build_position_tiers,
    the function that writes values[].tier in every ESPN leg) assigns from the
    same ESPN per-game projections the page is built with (players.json);
  * consistency with the ESPN line: no player tiered "waiver" has an ESPN
    value above 0.

Discrimination (test_guard_fails_on_pre_fix_widget): the same checks fail when
the page runs the pre-fix curve-widget.js (dac0ff2, read from git; skipped when
that commit is not in the clone).
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest

from tests._dist_server import DIST, ROOT, chromium_executable, serve

sys.path.insert(0, str(ROOT / "pipelines"))
from build_ddf_two_tier_leg import (  # noqa: E402
    POSITIONS, REF_FLEX_COUNT, REF_FLEX_ELIGIBLE, REF_SLOTS,
    bench_mix_for_teams, build_position_tiers,
)

PRE_FIX_COMMIT = "dac0ff2"
SCORINGS = ("standard", "half_ppr", "ppr")
TEAMS = (8, 10, 12, 14)
READ = """([s, t]) => {
  const c = window.TradeValueCurveControls;
  c.setScoring(s); c.setTeams(t);
  return c.getAllRows().map(r => [r.player_key, r.espnRole, r.values.espn, r.name]);
}"""


def server_tiers(players, scoring, teams):
    lists = {pos: [] for pos in POSITIONS}
    for p in players:
        x = (p.get("espn_ppg") or {}).get(scoring)
        if p.get("pos") in lists and isinstance(x, (int, float)):
            lists[p["pos"]].append({"id": int(p["player_key"]), "x": float(x)})
    pool = build_position_tiers(lists, teams, dict(REF_SLOTS), REF_FLEX_COUNT,
                                list(REF_FLEX_ELIGIBLE), bench_mix_for_teams(teams))
    return {d["id"]: ("starter" if d["id"] in pool["starters"]
                      else "bench" if d["id"] in pool["bench"] else "waiver")
            for pos in POSITIONS for d in lists[pos]}


def problems(snapshots, players):
    out = {}
    for (scoring, teams), rows in snapshots.items():
        expected = server_tiers(players, scoring, teams)
        mismatch = [(name, role, expected.get(int(key), "waiver")) for key, role, _, name in rows
                    if role != expected.get(int(key), "waiver")]
        waiver_valued = [(name, value) for _, role, value, name in rows
                         if role == "waiver" and isinstance(value, (int, float)) and value > 0]
        if mismatch or waiver_valued:
            out[f"{scoring}_{teams}"] = {"tier != server pool": mismatch[:5], "n_mismatch": len(mismatch),
                                         "waiver with ESPN value": waiver_valued[:5],
                                         "n_waiver_valued": len(waiver_valued)}
    return out


def read_all(overrides=None):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        exe = chromium_executable(p)
        if exe is None:
            raise unittest.SkipTest("no Chromium available")
        browser = p.chromium.launch(executable_path=exe)
        try:
            with serve(DIST, overrides) as base:
                page = browser.new_page()
                page.goto(base + "/classic/", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueCurveControls && window.TradeValueCurveDiagnostics",
                                       timeout=30000)
                return {(s, t): page.evaluate(READ, [s, t]) for s in SCORINGS for t in TEAMS}
        finally:
            browser.close()


class EspnTierMatchesLegTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DIST / "classic" / "index.html").exists():
            raise unittest.SkipTest("dist/ not built (run make sync)")
        cls.players = json.loads((ROOT / "data" / "fixtures" / "current" / "players.json")
                                 .read_text(encoding="utf-8"))["players"]

    def test_tier_matches_server_pool_and_espn_value(self):
        found = problems(read_all(), self.players)
        self.assertEqual(found, {}, json.dumps(found, indent=1)[:3000])

    def test_guard_fails_on_pre_fix_widget(self):
        proc = subprocess.run(["git", "show", f"{PRE_FIX_COMMIT}:app/trade-value-chart/assets/curve-widget.js"],
                              cwd=ROOT, capture_output=True)
        if proc.returncode != 0:
            self.skipTest(f"{PRE_FIX_COMMIT} not in this clone")
        found = problems(read_all({"assets/curve-widget.js": proc.stdout}), self.players)
        self.assertEqual(len(found), len(SCORINGS) * len(TEAMS), sorted(found))
        self.assertTrue(all(v["n_waiver_valued"] > 0 for v in found.values()))


if __name__ == "__main__":
    unittest.main()
