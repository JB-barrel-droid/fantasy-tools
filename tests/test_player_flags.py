"""Bye week on player rows in Compare, Find a trade and Trade targets (JEG-892, path A: byes only).

The rule lives in app/v2/player-flags.js:

  * teamCode: roster feeds write JAC, LAR, WSH and LVR; the bye table uses JAX, LA, WAS and LV;
  * byeOf: a team the table has gets its bye, marked done / this week / ahead against the calendar week when one is
    known; a free agent or an unknown team gets null, never a guessed week;
  * node: the " · Bye 11" span on a row's sub-line, with the schedule named on hover.

Coverage (the ticket's Done when): the bye table has all 32 teams, and every players.json row on an NFL team gets a
bye through the same function the page uses, so a missing team fails here, not on the live page.

Discrimination: test_checks_fail_on_broken_copies runs the checks on copies of player-flags.js with one rule broken.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLAGS_JS = ROOT / "app" / "v2" / "player-flags.js"
BYES = ROOT / "data" / "inputs" / "nfl_byes_2026.json"
PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"

PRELUDE = """
const fs = require('fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const made = [];
globalThis.document = {createElement: tag => { const n = {tag, dataset: {}, title: '', textContent: ''}; made.push(n); return n; }};
globalThis.TradeValueByes = input.table;
globalThis.TradeValueProductData = input.week === undefined ? undefined
  : {getSourceFreshness: () => { if (input.week === 'throws') throw new Error('not ready'); return {current_content_week: input.week}; }};
const P = require(process.argv[2]);
const out = (function () { %s })();
console.log(JSON.stringify(out));
"""

RULES = """
return {
  codes: input.teams.map(P.teamCode),
  byes: input.cases.map(c => P.byeOf(c.team, input.table.byes, c.week)),
  texts: input.cases.map(c => P.byeText(P.byeOf(c.team, input.table.byes, c.week))),
};
"""

NODES = """
return input.rows.map(r => { const n = P.node(r); return n ? {text: n.textContent, title: n.title, bye: n.dataset.bye, state: n.dataset.byeState} : null; });
"""

COVERAGE = """
return input.teams.map(t => [t, P.byeOf(t, input.table.byes, null)]);
"""


def run(script: str, payload: dict, path: Path = FLAGS_JS):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as handle:
        handle.write(PRELUDE % script)
        runner = handle.name
    try:
        done = subprocess.run(["node", runner, str(path)], input=json.dumps(payload), capture_output=True, text=True, check=True)
    finally:
        Path(runner).unlink()
    return json.loads(done.stdout)


def table() -> dict:
    data = json.loads(BYES.read_text(encoding="utf-8"))
    return {"season": data["season"], "byes": data["byes"]}


class PlayerFlagsTest(unittest.TestCase):
    path = FLAGS_JS

    def rules(self, cases, teams=()):
        return run(RULES, {"table": table(), "cases": cases, "teams": list(teams)}, self.path)

    def test_team_codes_normalise_to_the_bye_table(self):
        out = self.rules([], ["JAC", "LAR", "WSH", "LVR", " jax ", "LA", "KC"])
        self.assertEqual(out["codes"], ["JAX", "LA", "WAS", "LV", "JAX", "LA", "KC"])

    def test_bye_and_state_against_the_calendar_week(self):
        cases = [{"team": "CIN", "week": 9}, {"team": "PIT", "week": 9}, {"team": "LAR", "week": 9}, {"team": "JAC", "week": None}]
        out = self.rules(cases)
        self.assertEqual([b["week"] for b in out["byes"]], [6, 9, 11, 7])
        self.assertEqual([b["state"] for b in out["byes"]], ["done", "now", "ahead", "ahead"])
        self.assertEqual(out["texts"], ["Bye 6 (done)", "Bye this week (9)", "Bye 11", "Bye 7"])

    def test_free_agent_and_unknown_team_get_no_bye(self):
        out = self.rules([{"team": "", "week": 9}, {"team": None, "week": 9}, {"team": "XYZ", "week": 9}])
        self.assertEqual(out["byes"], [None, None, None])
        self.assertEqual(out["texts"], ["", "", ""])

    def test_row_node_names_the_schedule_and_never_claims_an_unknown_week(self):
        rows = [{"team": "JAC"}, {"team": ""}, {"team": "CIN"}]
        known = run(NODES, {"table": table(), "rows": rows, "week": 9}, self.path)
        self.assertEqual(known[0], {"text": " · Bye 7 (done)", "title": "Bye week: 2026 NFL schedule (published, fixed for the season).", "bye": "7", "state": "done"})
        self.assertIsNone(known[1])
        self.assertEqual(known[2]["text"], " · Bye 6 (done)")
        # Source freshness not loaded yet (it throws before init), or no freshness at all: the week alone.
        for week in ("throws", None):
            payload = {"table": table(), "rows": rows}
            if week is not None:
                payload["week"] = week
            out = run(NODES, payload, self.path)
            self.assertEqual(out[0]["text"], " · Bye 7")
            self.assertEqual(out[0]["state"], "ahead")
        # No bye table on the page: no bye on any row.
        self.assertEqual(run(NODES, {"table": None, "rows": rows, "week": 9}, self.path), [None, None, None])

    def test_every_team_backed_player_gets_a_bye(self):
        data = json.loads(BYES.read_text(encoding="utf-8"))
        weeks = data["byes"]
        self.assertEqual(len(weeks), 32, "the bye table must have all 32 teams")
        lo, hi = data["regular_season_weeks"]
        self.assertTrue(all(isinstance(w, int) and lo <= w <= hi for w in weeks.values()))
        players = json.loads(PLAYERS.read_text(encoding="utf-8"))["players"]
        teams = sorted({p["team"] for p in players if p.get("team")})
        self.assertTrue(teams)
        out = run(COVERAGE, {"table": table(), "teams": teams}, self.path)
        missing = [team for team, bye in out if bye is None]
        self.assertEqual(missing, [], f"players.json teams with no bye: {missing}")

    def test_page_loads_and_ships_the_script(self):
        import sys
        sys.path.insert(0, str(ROOT / "pipelines"))
        import build_v2_page
        with tempfile.TemporaryDirectory() as tmp:
            # The built engine page when there is one, else its source (the same script tags).
            engine = build_v2_page.ENGINE_PAGE if build_v2_page.ENGINE_PAGE.exists() else ROOT / "app" / "trade-value-chart" / "index.html"
            page = build_v2_page.build(dist=Path(tmp), engine_page=engine)
            self.assertIn('src="v2/player-flags.js"', page.read_text(encoding="utf-8"))
            self.assertTrue((Path(tmp) / "v2" / "player-flags.js").exists())


class BrokenCopies(unittest.TestCase):
    def test_checks_fail_on_broken_copies(self):
        source = FLAGS_JS.read_text(encoding="utf-8")
        breaks = {
            "no aliases": ('const ALIASES = {JAC: "JAX", LAR: "LA", WSH: "WAS", LVR: "LV"};', "const ALIASES = {};"),
            "guesses a bye": ("if (!code || !byes || !Number.isInteger(byes[code])) return null;",
                              "if (!byes) return null; if (!Number.isInteger(byes[code])) return {team: code, week: 1, state: \"ahead\"};"),
            "ignores the week": ('const state = !Number.isInteger(week) ? "ahead"', 'const state = true ? "ahead"'),
            "no provenance": ("span.title = sourceText(table.season);", 'span.title = "";'),
        }
        with tempfile.TemporaryDirectory() as tmp:
            for name, (old, new) in breaks.items():
                self.assertIn(old, source, name)
                broken = Path(tmp) / f"{name.replace(' ', '-')}" / "player-flags.js"
                broken.parent.mkdir()
                broken.write_text(source.replace(old, new), encoding="utf-8")
                suite = unittest.TestSuite()
                case = type("Broken", (PlayerFlagsTest,), {"path": broken})
                suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
                result = unittest.TestResult()
                suite.run(result)
                self.assertFalse(result.wasSuccessful(), f"checks passed on a broken copy: {name}")


if __name__ == "__main__":
    unittest.main()
