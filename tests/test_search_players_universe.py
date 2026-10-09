"""JEG-502: search finds every active NFL player, priced or not (headless).

Jeremy GL-20 (2026-10-09): "The user knowing they are a 0 is better than the
user questioning why they aren't in the tool."

A player no source prices (players.json universe_only, e.g. a practice-squad
receiver) is not one of the engine's computed rows: getAllRows, the curves and
the pies stay exactly as before (the lead's call, 2026-10-09: computing ~550
more rows cost ~+55% per settings switch). TradeValueCurveControls.searchPlayers
and getPlayer materialise his row on demand with the same row rules.

The test serves the built page with one practice-squad receiver added to the
inline players data, so it proves the engine path whatever the committed bake
holds. Fails on main: searchPlayers/getPlayer do not exist.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from tests._dist_server import DIST, serve  # noqa: E402
from tests import _render_env  # noqa: E402
from sync_dashboard_artifacts import replace_inline_players  # noqa: E402

SQUAD_KEY = 990001
SQUAD = {
    "player_key": SQUAD_KEY, "name": "Zebulon Squadtest", "pos": "WR", "team": "KC",
    "espn_ros": {"standard": 0.0, "half_ppr": 0.0, "ppr": 0.0}, "blend_ros": {"standard": 0.0, "half_ppr": 0.0, "ppr": 0.0},
    "espn_complete": False, "rz_complete": False, "cbsros_complete": False, "pricing": "espn_only",
    "espn_zeroed": True, "espn_status": "absent", "espn_missing_reason": "not on ESPN's list",
    "games_remaining": 13, "roster_status": "practice_squad", "roster_status_label": "Practice squad",
    "roster_status_inferred": True, "depth_chart_position": None, "sleeper_id": "99999",
    "universe_only": True, "unpriced_reason": "Practice squad (KC). No chart or projection prices this player.",
}

PROBE = """({key}) => {
  const c = window.TradeValueCurveControls;
  const all = c.getAllRows();
  const hits = c.searchPlayers('squadtest', {limit: 5});
  const accent = c.searchPlayers('ZEBULON  squad', {limit: 5}).map(r => r.player_key);
  const one = c.getPlayer(key);
  const priced = all.find(r => r.values && Object.values(r.values).some(v => Number.isFinite(v) && v > 5));
  const pricedHit = priced ? c.searchPlayers(priced.name, {limit: 50}).find(r => r.player_key === priced.player_key) : null;
  const t0 = performance.now();
  for (let i = 0; i < 20; i++) c.searchPlayers('a', {limit: 20});
  const searchMs = (performance.now() - t0) / 20;
  const nulls = one ? Object.entries(one.values).filter(([, v]) => v === null).map(([k]) => k) : [];
  return {
    inAllRows: all.some(r => r.player_key === key),
    nHits: hits.length, hit: hits[0] || null, accent, one,
    unexplained: nulls.filter(k => !(one.missingReasons || {})[k]),
    zeros: one ? Object.entries(one.values).filter(([, v]) => v === 0).map(([k]) => k) : [],
    pricedSame: pricedHit ? JSON.stringify(pricedHit.values) === JSON.stringify(priced.values) && !pricedHit.materialized : null,
    searchMs, empty: c.searchPlayers('  ', {}).length,
  };
}"""


def run_probe():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    tmp = Path(tempfile.mkdtemp())
    try:
        site = tmp / "dist"
        shutil.copytree(DIST, site)
        html = (site / "index.html").read_text(encoding="utf-8")
        start = html.index('<script id="players-data" type="application/json">') + len(
            '<script id="players-data" type="application/json">')
        players = json.loads(html[start:html.index("</script>", start)])
        players["players"].append(SQUAD)
        (site / "index.html").write_text(replace_inline_players(html, players), encoding="utf-8")
        with sync_playwright() as p:
            exe = _render_env.chromium_executable(p)
            if exe is None:
                raise _render_env.unavailable("no Chromium available")
            browser = p.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=exe)
            try:
                with serve(site) as base:
                    page = browser.new_page(viewport={"width": 1280, "height": 900})
                    errors = []
                    page.on("pageerror", lambda exc: errors.append(str(exc)))
                    page.goto(base + "/", wait_until="domcontentloaded")
                    page.wait_for_function(
                        "() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()",
                        timeout=90000)
                    page.wait_for_timeout(300)
                    has_api = page.evaluate("() => typeof window.TradeValueCurveControls.searchPlayers === 'function'")
                    out = page.evaluate(PROBE, {"key": SQUAD_KEY}) if has_api else {}
                    out["hasApi"] = has_api
                    out["pageErrors"] = errors
                    return out
            finally:
                browser.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class SearchPlayersUniverseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _render_env.ensure_built()
        if not (DIST / "index.html").exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")
        cls.out = run_probe()

    def test_practice_squad_player_is_found_with_zero_and_a_reason(self):
        out = self.out
        self.assertEqual([], out["pageErrors"])
        self.assertTrue(out["hasApi"], "TradeValueCurveControls.searchPlayers is missing")
        self.assertEqual(1, out["nHits"])
        hit = out["hit"]
        self.assertEqual(SQUAD_KEY, hit["player_key"])
        self.assertEqual("Zebulon Squadtest", hit["name"])
        self.assertEqual("practice_squad", hit["roster_status"])
        self.assertEqual("Practice squad", hit["roster_status_label"])
        self.assertEqual(SQUAD["unpriced_reason"], hit["unpriced_reason"])
        self.assertTrue(hit["universe_only"])
        self.assertTrue(hit["materialized"])
        # 0.0, not "not found": the fully loaded charts price him at 0.
        self.assertTrue({"usatoday", "fantasycalc", "fantasypros"} & set(out["zeros"]), out["zeros"])
        # DDF Value (JEG-479 #465: Adjusted values only) follows the same rule
        # as a computed row: 0 when an included input prices him at 0, else
        # null with its reason (covered by `unexplained` below).
        self.assertIn(hit["values"]["ddf_value"], (0, None))
        self.assertIn("blended", hit["ddfByVersion"])
        # Every null has a reason (the v2 row contract).
        self.assertEqual([], out["unexplained"])
        self.assertEqual(out["one"]["values"], hit["values"])  # getPlayer == the search hit
        self.assertIn(SQUAD_KEY, out["accent"])  # case and spacing ignored

    def test_unpriced_players_stay_out_of_the_computed_rows(self):
        self.assertFalse(self.out["inAllRows"])

    def test_a_priced_player_comes_back_as_the_engine_row(self):
        self.assertTrue(self.out["pricedSame"])
        self.assertEqual(0, self.out["empty"])

    def test_search_is_cheap(self):
        self.assertLess(self.out["searchMs"], 100)


if __name__ == "__main__":
    unittest.main()
