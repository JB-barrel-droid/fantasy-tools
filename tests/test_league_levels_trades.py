"""Uneven trades (2-for-1 and 1-for-2) at both league bench levels (JEG-1188, Codex review of #1105).

The league page's own search (opportunities.js computePairing over finder.js findTrades, run in Node by
tests/league_levels_trades.cjs) on the frozen USO and Charlotte rosters (tests/fixtures/league_levels), his team
against every other team, maxSize 2, the league's own starting lineup. Rows are priced three ways:
  ddf     DDF Value and the trade charts both from the ddf level (above replacement);
  market  both from the market level (rostered depth);
  page    the league page's contract: DDF Value from the ddf level, the trade charts from the market level.

A 2-for-1 search (you give two, get one) is evened by the other team adding its least valuable bench player
(side "receive"); a 1-for-2 search by you adding yours (side "give"). Checked on every found trade:
  * both sides trade the same number of players (no trade is left unbalanced here);
  * the edge is exactly what you get minus what you give in DDF Value, and each chart's net exactly the same in
    that chart, throw-ins included, from that variant's rows;
  * each added throw-in is the supplying team's least valuable priced bench player in DDF Value (the search's rule
    when no chart average is on the rows), not a starter and not otherwise in the trade.
Pinned: how many trades and throw-ins of each kind each variant finds (exact for the frozen inputs), and that on the
page the evened trades include throw-ins worth nothing to the team giving them (DDF Value 0.0) that the charts still
price, which is the sell gap at work.

Discrimination: test_fails_when_the_evened_trade_is_not_judged_again runs a finder.js that keeps the verdict from
before the throw-in was added and requires the arithmetic check to fail.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import test_league_levels_real as real

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "v2"
RUNNER = ROOT / "tests" / "league_levels_trades.cjs"
CHARTS = ["usatoday", "fantasycalc", "fantasypros", "cbs"]
VARIANTS = {"ddf": ("ddf", "ddf"), "market": ("market", "market"), "page": ("ddf", "market")}

# (trades, throw-ins added by the other team for a 2-for-1, added by you for a 1-for-2), his team vs every other.
# JEG-1249 (Codex review): the ddf waiver is the replacement player's own
# value in each source and market starters come from held players only, so
# the evened-trade counts moved from (92, 16, 11) / (787, 190, 49) for USO and
# (21, 1, 5) / (76, 9, 12) / (505, 121, 32) for Charlotte.
# JEG-1047 / JEG-1249 integration (Jeremy, 2026-10-29: "A, 7-player average"): a projection's waiver line
# is the 7-player band around the line row, which moved the counts from (99, 9, 16) / (112, 9, 8) /
# (317, 44, 25) for USO and (136, 15, 24) / (97, 12, 21) / (720, 65, 104) for Charlotte.
# JEG-1125 (Jeremy, 2026-10-29: option A): "even" is now one band, max(1 point, 3% of the average side), for the DDF
# edge and every chart, not 0.0 as shown, which moved the counts from (100, 8, 20) / (109, 9, 6) / (308, 42, 21)
# for USO and (135, 15, 24) / (107, 13, 23) / (711, 65, 102) for Charlotte.
# JEG-1403 (Jeremy: "I'd still want to see for even one trade chart and then we can use filters"): the search lists a
# trade when one chart has the other side even, not 3 of 4. Main at 951f95df had already moved off the pins below, before
# this change, to (114, 6, 22) / (112, 5, 9) / (356, 40, 28) for USO and (72, 5, 9) / (80, 9, 15) / (596, 46, 78) for
# Charlotte; the one-chart gate takes those to the counts pinned here.
PINNED = {
    ("uso", "ddf"): (3579, 310, 651), ("uso", "market"): (3736, 329, 536), ("uso", "page"): (3188, 370, 392),
    ("charlotte", "ddf"): (2997, 190, 460), ("charlotte", "market"): (3121, 269, 547), ("charlotte", "page"): (3488, 255, 551),
}


def league_input(doc: dict, levels: dict, variant: str) -> dict:
    ds, ms = VARIANTS[variant]
    rows = [{"player_key": k, "name": doc["players"][k]["name"], "pos": levels[ds][k]["pos"],
             "values": {"ddf_value": levels[ds][k]["ddf_blended"]["value"],
                        **{c: levels[ms][k]["adjusted"].get(c) for c in CHARTS}}}
            for k in levels["ddf"]]
    rs = doc["roster_slots"]
    shape = {"QB": rs.get("QB", 0), "RB": rs.get("RB", 0), "WR": rs.get("WR", 0), "TE": rs.get("TE", 0),
             "FLEX": rs.get("W/R/T", 0), "SUPERFLEX": 0}
    teams = {t["id"]: [p["key"] for p in t["players"] if p.get("key") and p["key"] in levels["ddf"]]
             for t in doc["league"]["teams"]}
    mine = doc["mine"]
    return {"rows": rows, "mine": teams[mine], "opponents": {i: v for i, v in teams.items() if i != mine},
            "shape": shape, "maxSize": 2}


def run(app_dir: Path, inp: dict) -> dict:
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(inp, fh)
    try:
        proc = subprocess.run(["node", str(RUNNER), str(app_dir), fh.name], capture_output=True, text=True, timeout=600)
    finally:
        Path(fh.name).unlink()
    if proc.returncode != 0:
        raise AssertionError(f"runner failed: {proc.stderr[-1500:]}")
    return json.loads(proc.stdout)


def arithmetic_problems(inp: dict, out: dict) -> list[str]:
    values = {str(r["player_key"]): r["values"] for r in inp["rows"]}
    total = lambda keys, k: sum(values[x][k] for x in keys)
    bad = []
    for opp, res in out["opponents"].items():
        for t in res["trades"]:
            tag = f"vs {opp} give {t['give']} get {t['receive']}"
            if len(t["give"]) != len(t["receive"]) or t["unbalanced"]:
                bad.append(f"{tag}: sides not even")
            if abs(t["edge"] - (total(t["receive"], "ddf_value") - total(t["give"], "ddf_value"))) > 1e-9:
                bad.append(f"{tag}: edge {t['edge']} is not receive minus give in DDF Value")
            for c in t["charts"]:
                want = total(t["receive"], c["key"]) - total(t["give"], c["key"])
                if c["net"] is None or abs(c["net"] - want) > 1e-9:
                    bad.append(f"{tag}: {c['key']} net {c['net']}, rows give {want}")
    return bad


def throw_in_problems(inp: dict, out: dict) -> list[str]:
    value = {str(r["player_key"]): r["values"]["ddf_value"] for r in inp["rows"]}
    bad = []
    for opp, res in out["opponents"].items():
        for t in res["trades"]:
            for a in t["added"]:
                roster, starters = ((inp["mine"], out["mineStarters"]) if a["side"] == "give"
                                    else (inp["opponents"][opp], res["starters"]))
                others = set(t["give"]) | set(t["receive"])
                others.discard(a["key"])
                bench = [k for k in roster if k not in others and k not in starters and value.get(k) is not None]
                tag = f"vs {opp} throw-in {a['key']} ({a['side']})"
                if a["key"] not in roster:
                    bad.append(f"{tag}: not on the supplying team")
                elif a["key"] in starters:
                    bad.append(f"{tag}: a starter")
                elif a["key"] not in t[a["side"]]:
                    bad.append(f"{tag}: not in the trade")
                elif value[a["key"]] > min(value[k] for k in bench) + 1e-12:
                    bad.append(f"{tag}: worth {value[a['key']]}, a bench player is worth {min(value[k] for k in bench)}")
    return bad


class TestUnevenTrades(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {}
        for name in ("uso", "charlotte"):
            doc = real.load(name)
            levels = {lv: real.run_spec(doc, real.level_extra(doc, lv))["rows"] for lv in ("ddf", "market")}
            for variant in VARIANTS:
                inp = league_input(doc, levels, variant)
                cls.cases[(name, variant)] = (inp, run(APP, inp))

    def test_trades_are_exact_sums_of_the_level_rows(self):
        for case, (inp, out) in self.cases.items():
            with self.subTest(case=case):
                self.assertEqual(arithmetic_problems(inp, out)[:5], [])

    def test_throw_ins_follow_the_bench_rule(self):
        for case, (inp, out) in self.cases.items():
            with self.subTest(case=case):
                self.assertEqual(throw_in_problems(inp, out)[:5], [])

    def test_both_uneven_shapes_found_at_every_level(self):
        for case, (inp, out) in self.cases.items():
            trades = [t for o in out["opponents"].values() for t in o["trades"]]
            sides = [a["side"] for t in trades for a in t["added"]]
            with self.subTest(case=case):
                self.assertEqual((len(trades), sides.count("receive"), sides.count("give")), PINNED[case])

    def test_page_throw_ins_include_players_only_the_charts_price(self):
        # USO only since JEG-1249: with the waiver priced at the replacement
        # player in each source, Charlotte's evened trades no longer use a
        # throw-in at 0.0 DDF Value.
        for name in ("uso",):
            inp, out = self.cases[(name, "page")]
            values = {str(r["player_key"]): r["values"] for r in inp["rows"]}
            gap = {a["key"] for o in out["opponents"].values() for t in o["trades"] for a in t["added"]
                   if abs(values[a["key"]]["ddf_value"]) < 0.05
                   and sum(values[a["key"]][c] for c in CHARTS) / len(CHARTS) >= 0.05}
            with self.subTest(league=name):
                self.assertTrue(gap, "no evened trade carries a throw-in worth 0.0 in DDF Value that the charts price")

    def test_fails_when_the_evened_trade_is_not_judged_again(self):
        anchor = "verdict = judgeSums(sumsOf(giveRows, keys), sumsOf(getRows, keys), chartKeys, minCharts);"
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("finder.js", "opportunities.js"):
                shutil.copy2(APP / name, Path(tmp) / name)
            path = Path(tmp) / "finder.js"
            text = path.read_text(encoding="utf-8")
            self.assertIn(anchor, text, "mutation anchor is stale")
            path.write_text(text.replace(anchor, "verdict = judged;", 1), encoding="utf-8")
            inp, _ = self.cases[("uso", "page")]
            self.assertTrue(arithmetic_problems(inp, run(Path(tmp), inp)))


if __name__ == "__main__":
    unittest.main()
