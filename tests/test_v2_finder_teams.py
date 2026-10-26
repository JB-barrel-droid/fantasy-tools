"""v2 Find a trade, the team value summary (JEG-890), the pure function under node.

teamSummary(rows, shape, chartKeys, ourKey) reads the engine rows (no math of its own beyond adding them):

  * Starters / Bench / Total and QB / RB / WR / TE, in every compared series; the Total is the sum of the listed
    players' values in that series (the Player values table column) and the QB+RB+WR+TE rows sum to it;
  * the starter set is the one pickStarters picks once from DDF Value, so Starters mean the same people in every column
    (a chart that would pick a different lineup does not re-pick);
  * a player a series does not price is missing, never 0: that cell is a partial sum marked complete=false with the
    names in `missing`; a real 0.0 counts; a row nobody prices has no number at all (value null, not 0);
  * the chartKeys passed in are the compared charts (a held chart is simply not in the list, so it is absent here);
  * the Trade chart average is the mean of the compared charts, only with MIN_CHARTS of them (absent otherwise).

Discrimination: test_checks_fail_on_broken_builds runs the checks against mutated copies of finder.js (a missing value
counted as 0, an empty-incomplete cell never flagged, the Total read from the starters, the chart average shown with
too few charts, and the starters re-picked per column from the market) and requires each to fail.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINDER_JS = ROOT / "app" / "v2" / "finder.js"
SHAPE = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "SUPERFLEX": 0}
SHAPE_SF = {"QB": 1, "RB": 1, "WR": 1, "TE": 1, "FLEX": 1, "SUPERFLEX": 1}
CHARTS = ["usatoday", "fantasycalc", "fantasypros"]   # cbs is held and left out (as run() leaves it out)


def p(key, pos, ddf, charts, name=None):
    """charts: the four chart values [usatoday, fantasycalc, fantasypros, cbs]; None for a series that does not price him."""
    values = {"ddf_value": ddf}
    for i, k in enumerate(["usatoday", "fantasycalc", "fantasypros", "cbs"]):
        values[k] = None if charts is None else charts[i]
    return {"player_key": key, "name": name or key, "pos": pos, "values": values}


def roster():
    return [
        p("Q1", "QB", 40, (5, 5, 5, 5)),        # the best DDF QB, a poor chart QB
        p("Q2", "QB", 10, (50, 50, 50, 50)),    # a chart QB the market would start, not DDF
        p("R1", "RB", 30, (25, 26, 24, 25)),
        p("R2", "RB", 25, (20, 21, 19, 20)),
        p("R3", "RB", 20, (15, 16, 14, 15)),    # FLEX by DDF
        p("R4", "RB", 5, (4, 4, 3, 4)),
        p("W1", "WR", 28, (22, 23, 21, 22)),
        p("W2", "WR", 24, (19, 20, 18, 19)),
        p("W3", "WR", 0.0, (2, 2, 2, 2)),       # a real 0.0 (a waiver line) counts
        p("T1", "TE", 15, (12, 13, 11, 12)),
        p("T2", "TE", 3, (2, 2, None, 2)),      # no value on fantasypros
        p("R5", "RB", None, (1, 1, 1, 1)),      # no DDF Value at all
    ]


def write_copy(body: str) -> Path:
    import tempfile
    tmp = Path(tempfile.mkdtemp()) / "finder.js"
    tmp.write_text(body, encoding="utf-8")
    return tmp


def node(finder_js, code, data):
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    script = "const F = require(process.argv[1]); const D = JSON.parse(process.argv[2]); const out = (() => {" + code + "})(); console.log(JSON.stringify(out));"
    proc = subprocess.run(["node", "-e", script, str(finder_js), json.dumps(data)], capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError(proc.stderr[-600:])
    return json.loads(proc.stdout)


SUMMARY = """
const cell = (s, id, row) => s.series.find(x => x.id === id).cells[row];
const fin = v => typeof v === 'number' && isFinite(v);
const sumKey = (list, key) => list.reduce((n, r) => n + (fin(r.values[key]) ? r.values[key] : 0), 0);
const s = F.teamSummary(D.rows, D.shape, D.charts, 'ddf_value');
const ids = s.series.map(x => x.id);
const ddfTotal = cell(s, 'ddf', 'total');
const pos = ['QB', 'RB', 'WR', 'TE'].map(p => cell(s, 'ddf', p).value);
const mix = ['Q1', 'Q2', 'R1', 'R2', 'R3', 'R4', 'W1', 'W2', 'W3', 'T1', 'T2', 'R5'];
return {
  ids, market: s.market,
  ddf: {total: ddfTotal, starters: cell(s, 'ddf', 'starters').value, bench: cell(s, 'ddf', 'bench').value, positions: pos,
    expectTotal: sumKey(D.rows, 'ddf_value'), expectStarters: F.lineupValue(D.rows, D.shape, 'ddf_value').starterValue,
    expectBench: F.lineupValue(D.rows, D.shape, 'ddf_value').benchValue},
  usatoday: {total: cell(s, 'usatoday', 'total'), expect: sumKey(D.rows, 'usatoday')},
  fantasypros: {total: cell(s, 'fantasypros', 'total'), expect: sumKey(D.rows, 'fantasypros')},
  marketStarters: cell(s, 'market', 'starters').value,
  starterKeys: s.picked.starters.map(r => r.player_key),
  heldAbsent: ids.indexOf('cbs') === -1,
  names: mix
};
"""

NULL_SERIES = """
// A chart nobody is priced by (every player null), passed in with one other chart: no average (too few), value null.
const rows = D.rows.map(r => ({...r, values: {...r.values, cbs: null}}));
const s = F.teamSummary(rows, D.shape, ['usatoday', 'cbs'], 'ddf_value');
const cbs = s.series.find(x => x.id === 'cbs').cells.total;
const mkt = s.series.find(x => x.id === 'market');
return {market: s.market, cbsValue: cbs.value, cbsComplete: cbs.complete, cbsMissing: cbs.missing.length, marketCells: Boolean(mkt && mkt.cells)};
"""


def checks(finder_js) -> list[str]:
    errors = []
    base = {"rows": roster(), "shape": SHAPE, "charts": CHARTS}
    r = node(finder_js, SUMMARY, base)

    want_ids = ["ddf", "market", "usatoday", "fantasycalc", "fantasypros"]
    if r["ids"] != want_ids:
        errors.append(f"series {r['ids']}, want {want_ids} (held cbs absent, market present with >=3 charts)")
    if not r["market"]:
        errors.append("the Trade chart average is missing with three compared charts")
    if r["heldAbsent"] is False:
        errors.append("the held chart cbs appears as a series")

    d = r["ddf"]
    if abs(d["total"]["value"] - d["expectTotal"]) > 1e-6 or abs(d["total"]["value"] - 200) > 1e-6:
        errors.append(f"DDF total {d['total']['value']}, want the sum of the listed players {d['expectTotal']} (200)")
    if d["total"]["complete"] or d["total"]["missing"] != ["R5"]:
        errors.append(f"DDF total complete/missing {d['total']['complete']}/{d['total']['missing']}, want false/['R5'] (no DDF value)")
    if abs(d["starters"] - d["expectStarters"]) > 1e-6 or abs(d["bench"] - d["expectBench"]) > 1e-6:
        errors.append(f"starters/bench {d['starters']}/{d['bench']}, want {d['expectStarters']}/{d['expectBench']}")
    if abs(d["starters"] + d["bench"] - d["total"]["value"]) > 1e-6:
        errors.append(f"starters + bench {d['starters'] + d['bench']} != total {d['total']['value']}")
    if d["positions"] != [50, 80, 52, 18]:
        errors.append(f"positions {d['positions']}, want [50, 80, 52, 18]")
    if abs(sum(d["positions"]) - d["total"]["value"]) > 1e-6:
        errors.append(f"positions sum {sum(d['positions'])} != total {d['total']['value']}")

    # the real 0.0 (W3) counts: the DDF columns are complete apart from R5, and the total still holds W3's 0.0
    if r["usatoday"]["total"]["value"] != r["usatoday"]["expect"] or not r["usatoday"]["total"]["complete"]:
        errors.append(f"usatoday total {r['usatoday']['total']}, want {r['usatoday']['expect']} and complete")

    # T2 has no fantasypros value: the total is a partial sum marked incomplete, not 0
    fp = r["fantasypros"]["total"]
    if fp["value"] != r["fantasypros"]["expect"] or fp["complete"] or fp["missing"] != ["T2"]:
        errors.append(f"fantasypros total {fp}, want the partial sum {r['fantasypros']['expect']}, incomplete, missing ['T2']")

    # starters are the DDF lineup in every column: the market starters are Q1's chart value, not the chart QB Q2's
    if r["marketStarters"] != 118:
        errors.append(f"market starters {r['marketStarters']}, want 118 (the DDF lineup read in the market, not a re-pick)")

    if r["starterKeys"] != ["Q1", "R1", "R2", "W1", "W2", "T1", "R3"]:
        errors.append(f"starters {r['starterKeys']}, want the 1/2/2/1/1 DDF lineup")

    null = node(finder_js, NULL_SERIES, {"rows": roster(), "shape": SHAPE})
    if null["market"] or null["marketCells"]:
        errors.append("the Trade chart average shows with fewer than three compared charts")
    if null["cbsValue"] is not None or null["cbsComplete"] or null["cbsMissing"] != len(roster()):
        errors.append(f"a series nobody prices: {null}, want value None, complete false, every name missing (never 0)")

    # superflex: the second QB starts in the SUPERFLEX slot
    sf = node(finder_js, "const s = F.teamSummary(D.rows, D.shape, D.charts, 'ddf_value'); return {keys: s.picked.starters.map(r => r.player_key), empty: s.picked.empty, starters: s.series.find(x=>x.id==='ddf').cells.starters.value};",
              {"rows": roster(), "shape": SHAPE_SF, "charts": CHARTS})
    # SUPERFLEX takes the best remaining value (W2, 24) ahead of the second QB (Q2, 10), as pickStarters does.
    if sf["keys"] != ["Q1", "R1", "W1", "T1", "R2", "W2"] or sf["starters"] != 162:
        errors.append(f"superflex starters {sf}, want Q1/R1/W1/T1/FLEX R2/SUPERFLEX W2 worth 162")

    # a roster shorter than the lineup: empty slots, an empty bench, no crash
    short = node(finder_js, "const s = F.teamSummary(D.rows, D.shape, D.charts, 'ddf_value'); return {empty: s.picked.empty, bench: s.series.find(x=>x.id==='ddf').cells.bench, emptySlot: s.picked.slots.TE.length};",
                 {"rows": [p("Q1", "QB", 40, (5, 5, 5, 5)), p("R1", "RB", 30, (25, 26, 24, 25)), p("W1", "WR", 28, (22, 23, 21, 22))], "shape": SHAPE, "charts": CHARTS})
    if not short["empty"] or short["bench"]["value"] != 0 or short["emptySlot"] != 0:
        errors.append(f"a roster shorter than the lineup: {short}, want the unfilled slots empty and a zero bench")
    return errors


class FinderTeamsTest(unittest.TestCase):
    def test_team_summary(self):
        self.assertEqual(checks(FINDER_JS), [])

    def test_checks_fail_on_broken_builds(self):
        js = FINDER_JS.read_text(encoding="utf-8")
        broken = {
            "a missing value counted as 0": js.replace("return {value: priced || !players.length ? sum : null,", "return {value: sum,", 1),
            "an incomplete cell never flagged": js.replace("complete: missing.length === 0};", "complete: true};", 1),
            "the Total read from the starters": js.replace("const sets = {starters: picked.starters, bench: picked.bench, total: rows.slice(),", "const sets = {starters: picked.starters, bench: picked.bench, total: picked.starters,", 1),
            "the chart average shown with too few charts": js.replace("const market = charts.length >= MIN_CHARTS;", "const market = charts.length >= 0;", 1),
            "the starters re-picked per column from the market": js.replace("starters: picked.starters, bench: picked.bench,", "starters: pickStarters(rows, shape, MARKET_KEY).starters, bench: pickStarters(rows, shape, MARKET_KEY).bench,", 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, js, f"mutation anchor for {name!r} is stale")
                try:
                    errors = checks(write_copy(body))
                except Exception as exc:
                    errors = [str(exc)[:120]]
                self.assertNotEqual(errors, [], f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
