"""v2 Trade targets: the market-consensus rule in app/v2/targets.js.

Check 1 (JEG-677; default and indexed basis per Jeremy 2026-10-16) on the engine's own rows:

  * consensus = the MEDIAN of the indexed charts that price the player (a
    finite 0 counts; a missing value is left out, never read as 0);
  * a player is a target only with 2+ charts priced, a consensus above the
    waiver line, and a strict majority of those charts on the same side of our
    value as the consensus ("N of M charts agree");
  * Sell: consensus gap > 0. Buy: gap < 0. Each list ranks by the gap weighted
    by the value at stake, score = |gap| x min(ours, consensus), biggest first
    (JEG-820, option B, 2026-10-22); Sell also needs ours >= 5 (SELL_FLOOR), so
    a player we would drop never heads the Sell list. Buy has no floor;
  * our value defaults to DDF Value, the blend (ddf_value; Jeremy 2026-10-16:
    DDF decides who we want); the other DDF versions,
    ESPN, CBS rest-of-season and Razzball stay as choices, each read from its
    own series only, an unavailable one offered disabled with a reason;
  * every available chart is compared, including one still on an earlier week
    (JEG-459), listed in `prior`;
  * a chart value at or below its waiver line shows but has no per-chart gap;
  * VORP vs waivers (a different unit) is never paired with anything.

The expected lists come from an independent Python recomputation (`reference`).
Discrimination: test_checks_fail_on_broken_builds runs the same checks against
mutated copies of targets.js (mean for median, majority rule dropped or made
non-strict, single chart allowed, consensus at the waiver line allowed, sign
flipped, missing read as 0, default reverted, ...) and requires every one to
fail.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS_JS = ROOT / "app" / "v2" / "targets.js"
CHARTS = ["usatoday", "fantasycalc", "fantasypros", "cbs"]

# ddf_value differs from espn on purpose, so the DDF Value and ESPN runs give different lists.
ROWS = [
    {"player_key": 1, "name": "A", "pos": "WR", "values": {"ddf_value": 12.0, "espn": 10.0, "cbsros": 14.0, "usatoday": 15.0, "fantasycalc": 8.0, "fantasypros": None, "cbs": 12.0}},
    {"player_key": 2, "name": "B", "pos": "WR", "values": {"ddf_value": None, "espn": None, "usatoday": 30.0}},
    {"player_key": 3, "name": "C", "pos": "WR", "values": {"ddf_value": 20.0, "espn": 20.0, "usatoday": 20.0}},
    {"player_key": 4, "name": "D", "pos": "WR", "values": {"ddf_value": 25.0, "espn": 5.0, "fantasycalc": 25.0, "usatoday": 20.0, "espn_vorp": 99.0}},
    {"player_key": 5, "name": "E", "pos": "WR", "values": {"ddf_value": 10.0, "espn": 30.0, "cbsros": 5.0, "usatoday": 10.0, "fantasycalc": 4.0, "espn_vorp": 1.0}},
    # F: USA Today puts F at its waiver line (0); FantasyCalc still pays 9 < 12.
    {"player_key": 6, "name": "F", "pos": "WR", "values": {"ddf_value": 12.0, "espn": 12.0, "usatoday": 0.0, "fantasycalc": 9.0}},
    # G: the only chart has G at its waiver line: never a target. No DDF Value.
    {"player_key": 7, "name": "G", "pos": "WR", "values": {"ddf_value": None, "espn": 8.0, "usatoday": 0.0}},
]


def _both(key: int, name: str, ours: float, pos: str = "WR", **charts) -> dict:
    """ddf_value and ddf_value_projections carry the same ours, so the default and DDF Value runs both see it."""
    return {"player_key": key, "name": name, "pos": pos, "values": {"ddf_value": ours, "ddf_value_projections": ours, **charts}}


CONSENSUS_ROWS = [
    _both(31, "K", 10.0, usatoday=20.0, fantasycalc=20.0, cbs=5.0),                    # median 20, 2 of 3 above: sell
    _both(32, "L", 10.0, usatoday=30.0, fantasycalc=5.0, cbs=5.0),                     # median 5, 2 of 3 below: buy
    _both(33, "M", 10.0, usatoday=30.0, fantasycalc=5.0),                              # median 17.5 but 1 of 2: no majority
    _both(34, "N", 10.0, usatoday=30.0),                                               # one chart only: never a target
    _both(35, "P", 10.0, usatoday=30.0, fantasycalc=12.0, cbs=9.0, fantasypros=9.0),   # median 10.5, 2 of 4: no majority
    _both(36, "Q", 10.0, usatoday=0.0, fantasycalc=0.0, cbs=0.0),                      # consensus at the waiver line: never a buy
    _both(37, "R", 10.0, usatoday=40.0, fantasycalc=3.0, cbs=2.0),                     # one huge chart, two below: buy by median
    _both(38, "S", 10.0, usatoday=10.0, fantasycalc=10.0, cbs=10.0),                   # all level: no gap
    _both(39, "T", 6.0, usatoday=9.0, fantasycalc=7.0, cbs=None),                      # median 8, 2 of 2 above, one missing: sell (score 12)
    # JEG-820: U has the biggest raw gap of all (+12) but we value him at 1.0: a drop, never a Sell.
    _both(40, "U", 1.0, usatoday=14.0, fantasycalc=12.0, cbs=13.0),
    # V (gap +5, score 45) outranks W (gap +7.5, score 37.5): the weight, not the raw gap, orders Sell.
    _both(41, "V", 9.0, usatoday=14.0, fantasycalc=14.0, cbs=13.0),
    _both(42, "W", 5.0, usatoday=13.0, fantasycalc=12.0),                              # ours exactly at the floor: listed
    # X: we have him one WR spot above Y, the charts one spot below (0.5 vs 1.0): rank gap 1.0 - 4.0 = -3, a Buy with
    # a 0.5 consensus (score 1.5), last, and under 5: there is no Buy floor. Y: consensus 1.0 = ours, no gap.
    _both(43, "X", 4.0, usatoday=0.5, fantasycalc=0.5),
    _both(50, "Y", 1.0, usatoday=1.0, fantasycalc=1.0),
    # JEG-833 regression guard: TE is a monotone STEEPER rescale of the charts (ours = 2 x chart) for T1..T5, so every
    # one is "priced below our value" (a buy by consensus) yet none is a Buy: the charts rank them where we do.
    _both(44, "T1", 40.0, pos="TE", usatoday=20.0, fantasycalc=20.0),
    _both(45, "T2", 30.0, pos="TE", usatoday=15.0, fantasycalc=15.0),
    _both(46, "T6", 28.0, pos="TE", usatoday=6.0, fantasycalc=6.0),    # we TE3, the charts TE5: our TE5 is 16, gap -12: the Buy
    _both(47, "T3", 24.0, pos="TE", usatoday=12.0, fantasycalc=12.0),
    _both(48, "T4", 16.0, pos="TE", usatoday=8.0, fantasycalc=8.0),
    _both(49, "T5", 10.0, pos="TE", usatoday=5.0, fantasycalc=5.0),
    # JEG-842: QB group. O (ESPN has him out) and E (FantasyCalc's value is estimated) have rank gaps -2 and -8 (Buys by
    # the JEG-833 rule) but must not be listed; S is a Sell by consensus (+10, ours 10 >= floor) with ESPN out: not listed.
    # All three are counted (leftOut 3). Q and R keep the ranks honest (flagged players still take part in the ranks).
    _both(60, "Q", 20.0, pos="QB", usatoday=20.0, fantasycalc=20.0),
    {**_both(61, "O", 30.0, pos="QB", usatoday=10.0, fantasycalc=10.0), "espnProjectsZero": True},
    {**_both(62, "E", 28.0, pos="QB", usatoday=9.0, fantasycalc=9.0), "estimated": {"fantasycalc": "FantasyCalc does not list him"}},
    _both(63, "R", 10.0, pos="QB", usatoday=5.0, fantasycalc=5.0),
    {**_both(64, "S", 10.0, pos="RB", usatoday=20.0, fantasycalc=20.0), "espnProjectsZero": True},
]
SELL_FLOOR = 5.0
BUY_RANK_MARGIN = 2.0

INFO = [
    {"key": "espn", "available": True, "stale": False},
    {"key": "ddf_value", "available": True, "stale": False, "composite": True},
    {"key": "ddf_value_projections", "available": True, "stale": False},
    {"key": "usatoday", "available": True, "stale": False, "week": 5},
    {"key": "fantasycalc", "available": True, "stale": False, "week": 5},
    {"key": "fantasypros", "available": False, "stale": False, "paused": True},
    {"key": "cbs", "available": True, "stale": True, "week": 4},
    {"key": "cbsros", "available": True, "stale": False},
    {"key": "razzball", "available": False, "stale": False},
]

MARKET_ROWS = [
    {"player_key": 21, "name": "I", "pos": "WR", "values": {"ddf_value": 10.0, "usatoday": 14.0, "fantasycalc": 6.0, "cbs": 10.0}},
    {"player_key": 22, "name": "J", "pos": "WR", "values": {"ddf_value": 10.0, "usatoday": 22.0, "fantasycalc": None, "cbs": 0.0}},
]


def median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def rank_gaps(rows: list[dict], ours_key: str, charts: list[str]) -> dict:
    """JEG-833: per position, over the players with our value and a 2+ chart consensus, the gap between our value at
    the charts' rank and our value: {key: (rank_gap, market_rank, our_rank)}. A monotone rescale gives 0 everywhere."""
    by_pos: dict[str, list] = {}
    for order, row in enumerate(rows):
        ours = row["values"].get(ours_key)
        priced = [row["values"][c] for c in charts if row["values"].get(c) is not None]
        if ours is None or len(priced) < 2:
            continue
        by_pos.setdefault(row["pos"], []).append((order, row["player_key"], ours, median(priced)))
    out = {}
    for players in by_pos.values():
        ours_desc = sorted((p[2] for p in players), reverse=True)
        our_rank = {p[1]: i + 1 for i, p in enumerate(sorted(players, key=lambda p: (-p[2], p[0])))}
        for i, p in enumerate(sorted(players, key=lambda p: (-p[3], p[0]))):
            out[p[1]] = (ours_desc[i] - p[2], i + 1, our_rank[p[1]])
    return out


def reference(rows: list[dict], ours_key: str, charts: list[str], keep=None) -> dict:
    """The independent calculation of Check 1: {side: [(key, gap, agree, of)]} in list order, plus the counts.
    Sell shows the consensus gap; Buy shows the gap at the charts' rank (JEG-833). `keep` filters what is listed
    after the ranks are taken over every row."""
    ranks = rank_gaps(rows, ours_key, charts)
    sell, buy, below_floor, scale_only, left_out = [], [], 0, [], []

    def flagged(row):   # JEG-842: out (ESPN zero) or an estimated value on a chart that prices him
        return bool(row.get("espnProjectsZero")) or any(row["values"].get(c) is not None and (row.get("estimated") or {}).get(c) for c in charts)

    for order, row in enumerate(rows):
        if keep is not None and not keep(row):
            continue
        ours = row["values"].get(ours_key)
        if ours is None:
            continue
        priced = [row["values"][c] for c in charts if row["values"].get(c) is not None]
        if len(priced) < 2:
            continue
        consensus = median(priced)
        gap = consensus - ours
        if consensus <= 0 or gap == 0:
            continue
        agree = sum(1 for v in priced if (v > ours if gap > 0 else v < ours))
        if agree * 2 <= len(priced):
            continue
        if gap > 0:
            if ours < SELL_FLOOR:   # JEG-820: a player we would drop is never a Sell
                below_floor += 1
                continue
            if flagged(row):
                left_out.append((0, -abs(gap) * min(ours, consensus), order, row["name"]))
                continue
            sell.append((order, row["player_key"], gap, agree, len(priced), abs(gap) * min(ours, consensus)))
            continue
        rank_gap = ranks[row["player_key"]][0]
        if rank_gap > -BUY_RANK_MARGIN:   # JEG-833: the charts rank him where we do: the scale, not a mispricing
            scale_only.append((ours, order, row["name"]))
            continue
        if flagged(row):
            left_out.append((-1, -abs(rank_gap) * min(ours, consensus), order, row["name"]))
            continue
        buy.append((order, row["player_key"], rank_gap, agree, len(priced), abs(rank_gap) * min(ours, consensus)))
    sell.sort(key=lambda t: (-t[5], t[0]))
    buy.sort(key=lambda t: (-t[5], t[0]))
    scale_only.sort(key=lambda t: (-t[0], t[1]))
    left_out.sort()   # Buy rows (by score) first, then Sell rows
    return {"leftOut": len(left_out), "leftOutNames": [t[3] for t in left_out[:5]], "sell": [t[1:5] for t in sell], "buy": [t[1:5] for t in buy], "belowSellFloor": below_floor,
            "scaleOnly": len(scale_only), "scaleOnlyNames": [t[2] for t in scale_only[:5]], "ranks": ranks}


def recompute_market(row: dict, charts: list[str]) -> dict:
    """The independent calculation: median of the finite chart values (a 0 counts), ours minus it."""
    ours = row["values"]["ddf_value"]
    priced = [row["values"][c] for c in charts if row["values"].get(c) is not None]
    consensus = median(priced)
    return {"value": consensus, "count": len(priced), "left": len(charts) - len(priced), "diff": ours - consensus,
            "equal": f"{ours:.1f}" == f"{consensus:.1f}"}


HARNESS = """
const T = require(process.argv[1]);
const input = JSON.parse(process.argv[2]);
const brief = p => ({key: p.row.player_key, ours: p.ours, cells: p.cells, market: p.market});
const run = (rows, opts) => { const r = T.buildTargets(rows, input.charts, opts); return {ours: r.ours, sell: r.sell.map(brief),
  buy: r.buy.map(brief), compared: r.compared, omitted: r.omittedNoOurs}; };
// JEG-1186 (Jeremy, 2026-10-27: "Suppress"; replaces 2026-10-08 "a one-source DDF Value is still a target"):
// H (DDF Value from 1 source) is no Buy/Sell call and is counted in thinSource; H2 (2 sources, same numbers) still is.
// H3 picks ESPN as our value: a single published series is never thin.
const lc = T.buildTargets([
  {player_key: 9, name: "H", values: {ddf_value: 6.0, usatoday: 9.0, fantasycalc: 8.0}, ddfCount: 1, ddfLowConfidence: true},
  {player_key: 10, name: "H2", values: {ddf_value: 6.0, usatoday: 9.0, fantasycalc: 8.0}, ddfCount: 2}], ["usatoday", "fantasycalc"], {ours: "ddf_value"});
const lcCharts = T.buildTargets([{player_key: 11, name: "H4", values: {ddf_value_charts: 6.0, usatoday: 9.0, fantasycalc: 8.0}, ddfChartsCount: 1}],
  ["usatoday", "fantasycalc"], {ours: "ddf_value_charts"});
const lcEspn = T.buildTargets([{player_key: 12, name: "H3", values: {espn: 6.0, usatoday: 9.0, fantasycalc: 8.0}, ddfCount: 1}], ["usatoday", "fantasycalc"], {ours: "espn"});
// JEG-504: consensus cases. I: the median equals our value (10.0) to one decimal;
// J: one chart does not price the player (left out), one at its waiver line (a finite 0 counts).
const mk = T.buildTargets(input.market, ["usatoday", "fantasycalc", "cbs"], {ours: "ddf_value"});
const rows = input.rows.concat(input.consensus);
console.log(JSON.stringify({
  market: mk.players.map(brief),
  lowConfidence: lc.sell.map(p => [p.row.player_key, p.ours, p.market.gap]),
  thin: [lc.thinSource, lc.thinSourceNames], thinCharts: [lcCharts.sell.length, lcCharts.thinSource], espnSingle: [lcEspn.sell.length, lcEspn.thinSource],
  byDefault: run(rows),
  belowSellFloor: T.buildTargets(rows, input.charts, {}).belowSellFloor, sellFloor: T.SELL_FLOOR,
  // JEG-833: the counts, the margin, and a name-search run (keep) whose ranks must still come from every row.
  leftOut: T.buildTargets(rows, input.charts, {}).leftOut, leftOutNames: T.buildTargets(rows, input.charts, {}).leftOutNames,
  scaleOnly: T.buildTargets(rows, input.charts, {}).scaleOnly, scaleOnlyNames: T.buildTargets(rows, input.charts, {}).scaleOnlyNames,
  buyMargin: T.BUY_RANK_MARGIN,
  keepRun: run(rows, {ours: "ddf_value", keep: row => row.player_key === 46}),
  ddf: run(rows, {ours: "ddf_value"}),
  proj: run(rows, {ours: "ddf_value_projections"}),
  espn: run(rows, {ours: "espn"}),
  cbsros: run(rows, {ours: "cbsros"}),
  choices: T.ourChoices(input.info), ourKeys: T.OUR_KEYS,
  defaultCharts: T.chartsToCompare(input.info, {}),
  onlyCharts: T.chartsToCompare(input.info, {only: "fantasycalc"}),
  ourKey: T.OUR_KEY,
  // JEG-851: single-chart mode — one chart compared, minCharts = 1.
  singleUSA: (() => { const r = T.buildTargets(input.consensus, ["usatoday"], {ours: "ddf_value"}); return {sell: r.sell.map(brief), buy: r.buy.map(brief), compared: r.compared, singleChart: r.singleChart}; })(),
  // JEG-851: chart as our value — usatoday as ours, fantasycalc as the compared chart.
  chartAsOurs: (() => { const r = T.buildTargets(input.consensus, ["usatoday", "fantasycalc"], {ours: "usatoday"}); return {sell: r.sell.map(brief), buy: r.buy.map(brief), compared: r.compared, singleChart: r.singleChart}; })(),
  // JEG-868: chart as our value against ALL charts — every player's cells are exactly the other charts.
  chartAsOursAll: (() => { const r = T.buildTargets(input.consensus, T.CHART_KEYS, {ours: "usatoday"}); return {cells: [...new Set(r.players.flatMap(p => Object.keys(p.cells)))].sort(), singleChart: r.singleChart}; })(),
  // JEG-851: chart as our value, same chart in the compare set — self-comparison excluded.
  selfCompare: (() => { const r = T.buildTargets(input.consensus, ["usatoday"], {ours: "usatoday"}); return {sell: r.sell.map(brief), buy: r.buy.map(brief), compared: r.compared, singleChart: r.singleChart}; })(),
  // JEG-851: single-chart with an estimated value — must be excluded.
  singleEstimated: (() => { const r = T.buildTargets([{player_key: 90, name: "Est", pos: "QB", values: {ddf_value: 10.0, fantasycalc: 20.0}, estimated: {fantasycalc: "filled in"}}], ["fantasycalc"], {ours: "ddf_value"}); return {sell: r.sell.map(brief), buy: r.buy.map(brief), leftOut: r.leftOut}; })(),
}));
"""


def run_targets(path: Path) -> dict:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is not available")
    payload = json.dumps({"rows": ROWS, "consensus": CONSENSUS_ROWS, "charts": CHARTS, "info": INFO, "market": MARKET_ROWS})
    out = subprocess.run([node, "-e", HARNESS, str(path), payload], capture_output=True, text=True)
    if out.returncode:
        return {"crashed": out.stderr.strip().splitlines()[-1:] or ["no output"]}   # a build that throws fails the checks
    return json.loads(out.stdout)


def lists(run: dict) -> dict:
    """Each side with the gap it shows: Sell the consensus gap, Buy the gap at the charts' rank (JEG-833)."""
    return {side: [(p["key"], p["market"]["gap"] if side == "sell" else p["market"].get("rankGap"), p["market"]["agree"], p["market"]["of"])
                   for p in run[side]] for side in ("sell", "buy")}


def check(result: dict) -> list[str]:
    """Return every rule the result breaks (empty list = correct)."""
    if "crashed" in result:
        return [f"targets.js threw: {result['crashed']}"]
    errors = []
    if result["ourKey"] != "ddf_value":
        errors.append(f"our value must default to DDF Value, the blend (Jeremy 2026-10-16), got {result['ourKey']}")
    all_rows = ROWS + CONSENSUS_ROWS
    for name, key in (("byDefault", "ddf_value"), ("ddf", "ddf_value"), ("proj", "ddf_value_projections"), ("espn", "espn"), ("cbsros", "cbsros")):
        run = result[name]
        if run["ours"] != key:
            errors.append(f"{name}: expected our value series {key}, got {run['ours']}")
        want = reference(all_rows, key, CHARTS)
        got = lists(run)
        for side in ("sell", "buy"):
            if [tuple(x) for x in got[side]] != want[side]:
                errors.append(f"{name} {side} list must follow the consensus rule: want {want[side]}, got {got[side]}")
    # The named cases, on the default series (DDF Value).
    d = lists(result["byDefault"])
    sell_keys = [k for k, *_ in d["sell"]]
    buy_keys = [k for k, *_ in d["buy"]]
    # JEG-820: Sell scores K 100, V 45, W 37.5, T 12 (U is under the Sell floor).
    # JEG-833: Buy by the gap at the charts' rank x value at stake: T6 12 x 6 = 72, F 6 x 4.5 = 27, R 5 x 3 = 15,
    # X 3 x 0.5 = 1.5. L (rank gap -1, inside the 2-point margin) and the steeper-rescale TEs are the scale, not Buys.
    if sell_keys != [31, 41, 42, 39] or buy_keys != [46, 6, 37, 43]:
        errors.append(f"default lists wrong (sell {sell_keys}, buy {buy_keys}); wanted sell [31, 41, 42, 39], buy [46, 6, 37, 43]")
    for key, why in ((33, "1 of 2 is not a majority"), (34, "one chart is not a consensus"),
                     (35, "2 of 4 is not a majority"), (36, "a consensus at the waiver line is never a target"),
                     (38, "no gap"), (40, "we value him under the Sell floor (JEG-820)"),
                     (32, "the charts rank him within 2 points of where we do (JEG-833)"), (50, "no gap"),
                     (44, "steeper rescale: same rank on both sides (JEG-833)"), (45, "steeper rescale (JEG-833)"),
                     (47, "steeper rescale (JEG-833)"), (48, "steeper rescale (JEG-833)"), (49, "steeper rescale (JEG-833)")):
        if key in sell_keys + buy_keys:
            errors.append(f"player {key} must not be a target: {why}")
    # JEG-833: the rank-equivalent numbers on T6, the counts, the margin, and ranks taken over every row in a search.
    t6 = next((p for p in result["byDefault"]["buy"] if p["key"] == 46), None)
    if t6 is None or (t6["market"].get("rankGap"), t6["market"].get("marketRank"), t6["market"].get("ourRank"), t6["market"].get("oursAtRank")) != (-12.0, 5, 3, 16.0):
        errors.append(f"T6 must read rank gap -12 (charts TE5, we TE3, our TE5 is 16.0): {t6 and t6['market']}")
    if t6 is not None and abs((t6["market"].get("buyScore") or 0) - 72.0) > 1e-9:
        errors.append(f"T6's Buy score must be 12 x min(28, 6) = 72: {t6['market'].get('buyScore')}")
    want = reference(all_rows, "ddf_value", CHARTS)
    if result.get("scaleOnly") != want["scaleOnly"] or result.get("scaleOnlyNames") != want["scaleOnlyNames"]:
        errors.append(f"players priced below our value but ranked where we rank them must be counted and named (by ours): want {want['scaleOnly']} {want['scaleOnlyNames']}, got {result.get('scaleOnly')} {result.get('scaleOnlyNames')}")
    # JEG-842: out / estimated players are not recommended on either side, and the exclusion is counted and named.
    if {61, 62, 64} & set(sell_keys + buy_keys):
        errors.append(f"an out (ESPN zero) or estimated-chart player must not be a Buy or Sell target: {sell_keys} {buy_keys}")
    if result.get("leftOut") != want["leftOut"] or result.get("leftOutNames") != want["leftOutNames"] or want["leftOut"] != 3:
        errors.append(f"left-out players must be counted and named: want {want['leftOut']} {want['leftOutNames']}, got {result.get('leftOut')} {result.get('leftOutNames')}")
    if result.get("buyMargin") != BUY_RANK_MARGIN:
        errors.append(f"Buy margin must be {BUY_RANK_MARGIN} points: {result.get('buyMargin')}")
    keep_run = result.get("keepRun") or {}
    if [p["key"] for p in keep_run.get("buy", [])] != [46] or keep_run.get("compared") != 1 \
            or (keep_run["buy"][0]["market"].get("rankGap") if keep_run.get("buy") else None) != -12.0:
        errors.append(f"a name search lists only the kept player but ranks him among every row: {keep_run.get('buy') and [(p['key'], p['market'].get('rankGap')) for p in keep_run['buy']]}, compared {keep_run.get('compared')}")
    if result.get("sellFloor") != SELL_FLOOR or result.get("belowSellFloor") != 1:
        errors.append(f"Sell floor must be {SELL_FLOOR} and count the one player under it: {result.get('sellFloor')}, {result.get('belowSellFloor')}")
    v = next((p for p in result["byDefault"]["sell"] if p["key"] == 41), None)
    if v is None or abs((v["market"].get("weight") or 0) - 9.0) > 1e-9 or abs((v["market"].get("score") or 0) - 45.0) > 1e-9:
        errors.append(f"V must carry weight min(9, 14) = 9 and score 5 x 9 = 45: {v and v['market']}")
    k = next((p for p in result["byDefault"]["sell"] if p["key"] == 31), None)
    if k is None or (k["market"]["agree"], k["market"]["of"]) != (2, 3) or [d_["side"] for d_ in k["market"]["dots"]] != ["above", "above", "below"]:
        errors.append(f"K must read 2 of 3 charts agree with one dot per chart: {k and k['market']}")
    if k is not None and [d_["value"] for d_ in k["market"]["dots"]] != [k["cells"][c]["value"] for c in ("usatoday", "fantasycalc", "cbs")]:
        errors.append(f"each dot must carry its chart's indexed value: {k['market']['dots']}")
    if k is not None and [k["cells"][c]["gap"] for c in ("usatoday", "fantasycalc", "cbs")] != [10.0, 10.0, -5.0]:
        errors.append(f"per-chart gap = chart value - our value (positive: the chart pays more): {k['cells']}")
    # JEG-1186 (Jeremy, 2026-10-27): fewer than 2 sources behind DDF Value -> no Buy/Sell call, counted and named.
    if result["lowConfidence"] != [[10, 6.0, 2.5]]:
        errors.append(f"only the 2-source twin may be a Sell; the 1-source player must not: {result['lowConfidence']}")
    if result["thin"] != [1, ["H"]]:
        errors.append(f"the 1-source player must be counted and named in thinSource: {result['thin']}")
    if result["thinCharts"] != [0, 1]:
        errors.append(f"DDF Value (charts) with 1 source must be suppressed too (its own count): {result['thinCharts']}")
    if result["espnSingle"] != [1, 0]:
        errors.append(f"a single published series picked as our value is never thin: {result['espnSingle']}")
    # Per-chart cells.
    dd = result["ddf"]
    if 1 in {p["key"] for p in dd["sell"] + dd["buy"]}:
        errors.append("DDF Value run: player A (median 12 = ours 12) has no gap and must not be listed")
    sell_e = {p["key"]: p for p in result["espn"]["sell"] + result["espn"]["buy"]}
    five = sell_e.get(5)
    if five is None:
        errors.append("ESPN run: player E missing")
    else:
        cell = five["cells"]["fantasypros"]
        if cell["value"] is not None or cell["gap"] is not None or not cell["reason"]:
            errors.append(f"missing chart value must be null gap + reason, never 0: {cell}")
    f_run = {p["key"]: p for p in result["ddf"]["sell"] + result["ddf"]["buy"]}
    fcell = f_run.get(6, {}).get("cells", {}).get("usatoday")
    if fcell is not None and (fcell["gap"] is not None or not fcell.get("atWaiver")):
        errors.append(f"chart value at the waiver line must have no gap: {fcell}")
    every = result["byDefault"]["sell"] + result["byDefault"]["buy"] + result["ddf"]["sell"] + result["ddf"]["buy"]
    if any("espn_vorp" in p["cells"] for p in every):
        errors.append("VORP vs waivers must never be paired with trade-value points")
    if 7 in {p["key"] for p in every} or 3 in {p["key"] for p in every}:
        errors.append("G (waiver line) and C (no gap) are never targets")
    if result["ddf"]["omitted"] != 2 or result["byDefault"]["omitted"] != 2:
        errors.append(f"players without our value are left out and counted: ddf={result['ddf']['omitted']} default={result['byDefault']['omitted']}")
    # JEG-459: a chart still on an earlier week is always compared, and flagged.
    if result["defaultCharts"]["used"] != ["usatoday", "fantasycalc", "cbs"]:
        errors.append(f"every available chart must be compared, prior week included: {result['defaultCharts']}")
    if result["defaultCharts"].get("prior") != ["cbs"]:
        errors.append(f"the prior-week chart must be flagged (and only it): {result['defaultCharts']}")
    skipped = {s["key"]: s["reason"] for s in result["defaultCharts"]["skipped"]}
    if set(skipped) != {"fantasypros"} or not skipped["fantasypros"]:
        errors.append(f"only unavailable charts are skipped, with a reason: {skipped}")
    if result["onlyCharts"]["used"] != ["fantasycalc"]:
        errors.append(f"single-chart filter wrong: {result['onlyCharts']}")
    # JEG-851: chart keys are now selectable as "Our value" too.
    if result["ourKeys"] != ["ddf_value", "ddf_value_charts", "ddf_value_projections", "espn", "cbsros", "razzball", "usatoday", "fantasycalc", "fantasypros", "cbs"]:
        errors.append(f"our value choices: DDF Value first, then the other DDF versions, then the projections, then the charts: {result['ourKeys']}")
    choices = {c["key"]: c for c in result["choices"]}
    if not all(choices.get(k, {}).get("available") for k in ("ddf_value", "ddf_value_projections", "espn", "cbsros")):
        errors.append(f"available series must be offered: {choices}")
    rz = choices.get("razzball", {})
    if rz.get("available") is not False or not rz.get("reason"):
        errors.append(f"an unavailable series must be offered disabled with a reason: {rz}")
    # JEG-504: the consensus and difference equal a recomputation from the engine values (every compared
    # player is returned in `players`, listed or not: I's median equals ours, J has 1 of 2 and is not listed).
    market = {p["key"]: p["market"] for p in result["market"]}
    if not market.get(21, {}).get("equal") or market.get(22, {}).get("equal"):
        errors.append(f"a consensus equal to our value to one decimal is flagged equal (and only then): {market}")
    for row in MARKET_ROWS:
        want = recompute_market(row, ["usatoday", "fantasycalc", "cbs"])
        got = market.get(row["player_key"])
        if got is None:
            errors.append(f"consensus for {row['name']} missing")
            continue
        if got["count"] != want["count"] or got["left"] != want["left"] or got["equal"] != want["equal"] \
                or abs(got["value"] - want["value"]) > 1e-9 or abs(got["diff"] - want["diff"]) > 1e-9:
            errors.append(f"consensus for {row['name']} must be {want}, got {got}")
    # JEG-851: single-chart mode.
    sc = result.get("singleUSA", {})
    if sc.get("singleChart") != "usatoday":
        errors.append(f"single-chart mode must report the chart key: {sc.get('singleChart')}")
    # K (ddf_value 10, usatoday 20): usatoday > ours, eligible with 1 chart, gap +10, ours 10 >= floor: Sell.
    sc_sell_keys = [p["key"] for p in sc.get("sell", [])]
    sc_buy_keys = [p["key"] for p in sc.get("buy", [])]
    if 31 not in sc_sell_keys:
        errors.append(f"single-chart mode: K (usatoday 20 > ours 10) must be a Sell target: {sc_sell_keys}")
    # N (ddf_value 10, usatoday 30): only one chart, was ineligible in multi-chart mode, now eligible: Sell.
    if 34 not in sc_sell_keys:
        errors.append(f"single-chart mode: N (one chart, usatoday 30 > ours 10) must be a Sell target: {sc_sell_keys}")
    # JEG-851: chart-as-our-value (usatoday as ours, fantasycalc compared); self-excluded from chart set.
    cao = result.get("chartAsOurs", {})
    if cao.get("singleChart") != "fantasycalc":
        errors.append(f"chart-as-ours: with usatoday as ours, effectiveCharts should be [fantasycalc]: singleChart={cao.get('singleChart')}")
    # JEG-868: usatoday as ours against all four charts: cells for exactly the other three, never our own.
    caa = result.get("chartAsOursAll", {})
    if caa.get("cells") != ["cbs", "fantasycalc", "fantasypros"] or caa.get("singleChart") is not None:
        errors.append(f"chart-as-ours vs all: cells must be the other charts only: {caa}")
    # JEG-851: self-comparison (usatoday as both ours and the only chart) — no effective charts, empty lists.
    selfcmp = result.get("selfCompare", {})
    if selfcmp.get("sell") or selfcmp.get("buy"):
        errors.append(f"self-comparison must produce empty lists: sell={len(selfcmp.get('sell', []))}, buy={len(selfcmp.get('buy', []))}")
    if selfcmp.get("singleChart") is not None:
        errors.append(f"self-comparison: effectiveCharts is empty, singleChart must be null: {selfcmp.get('singleChart')}")
    # JEG-851: estimated value on a single chart must be excluded.
    se = result.get("singleEstimated", {})
    if se.get("sell") or se.get("buy"):
        errors.append(f"single-chart with estimated value must not list the player: sell={len(se.get('sell', []))}, buy={len(se.get('buy', []))}")
    if se.get("leftOut") != 1:
        errors.append(f"single-chart with estimated value must count it as leftOut: {se.get('leftOut')}")
    return errors


MUTATIONS = {
    "sign flipped": ("const gap = value - ours;\n        cells[chart]", "const gap = ours - value;\n        cells[chart]"),
    "consensus sign flipped": ("const diff = ours - value;\n    const gap = value - ours;", "const diff = ours - value;\n    const gap = ours - value;"),
    "missing read as zero": ("const value = row.values[chart];", "const value = row.values[chart] ?? 0;"),
    "prior-week chart dropped": ("      else used.push(key);", "      else if (!item.stale) used.push(key);"),
    "prior-week chart not flagged": ("if (item && item.available && item.stale) prior.push(key);", "if (false) prior.push(key);"),
    "missing ours read as zero": ("const ours = row.values ? row.values[ourKey] : null;",
                                  "const ours = (row.values && row.values[ourKey]) || 0;"),
    "waiver rule removed": ("if (value <= 0) {", "if (false) {"),
    "chosen series ignored": ("const ourKey = (opts && opts.ours) || OUR_KEY;", "const ourKey = OUR_KEY;"),
    "unavailable series offered": ("const available = Boolean(item && item.available);", "const available = true;"),
    "default moved off DDF Value": ("const OUR_KEY = OUR_KEYS[0];", "const OUR_KEY = OUR_KEYS[2];"),
    # JEG-1186
    "one-source player still a call": ("return n !== null && n < MIN_DDF_SOURCES;", "return false;"),
    "two-source player suppressed": ("const MIN_DDF_SOURCES = 2;", "const MIN_DDF_SOURCES = 3;"),
    "version count ignored": ('ddf_value_charts: "ddfChartsCount", ', ""),
    "single series counted as thin": ("return field && finite(row[field]) ? row[field] : null;", "return finite(row.ddfCount) ? row.ddfCount : null;"),
    "thin not counted": ("thinSource: thinOut.length,", "thinSource: 0,"),
    # JEG-677
    "mean instead of median": ("const value = median(values);", "const value = values.reduce((a, b) => a + b, 0) / values.length;"),
    "majority rule dropped": (" && agree * 2 > priced.length;", ";"),
    "majority not strict": ("agree * 2 > priced.length", "agree * 2 >= priced.length"),
    "single chart always allowed (minCharts bypass)": ("priced.length >= minCharts && value > 0", "priced.length >= 1 && value > 0"),
    "consensus at waiver line allowed": ("priced.length >= minCharts && value > 0", "priced.length >= minCharts"),
    "consensus ignores a finite zero": ("const values = priced.map(key => cells[key].value);",
                                        "const values = priced.map(key => cells[key].value).filter(v => v > 0);"),
    "agreement counted on the wrong side": ('(side === "sell" ? v > ours : v < ours)', '(side === "sell" ? v < ours : v > ours)'),
    "equal never flagged": ("equal: ours.toFixed(1) === value.toFixed(1),\n      side", "equal: false,\n      side"),
    "DDF Value dropped from the choices": ('"ddf_value_charts", "ddf_value_projections", "espn"', '"ddf_value_charts", "espn"'),
    "dot value not the indexed chart value": ("dots = priced.map(key => ({chart: key, value: cells[key].value,", "dots = priced.map(key => ({chart: key, value: 0,"),
    # JEG-820: the weighted ranking and the Sell floor. Each of these is the bug the ticket names (raw-gap order
    # put 0.0 to 3.4 players at the top of Sell) or a plausible slip while fixing it.
    "sell floor removed (raw-gap bug returns)": ("const sellAll = sellable.filter(p => p.ours >= SELL_FLOOR).sort(byScore);",
                                                 "const sellAll = sellable.slice().sort(byScore);"),
    "sell floor strict": ("const sellAll = sellable.filter(p => p.ours >= SELL_FLOOR).sort(byScore);",
                          "const sellAll = sellable.filter(p => p.ours > SELL_FLOOR).sort(byScore);"),
    "sell floor moved": ("const SELL_FLOOR = 5;", "const SELL_FLOOR = 2;"),
    "floor applied to buy": ('const buyable = players.filter(p => p.market.eligible && p.market.side === "buy");',
                             'const buyable = players.filter(p => p.market.eligible && p.market.side === "buy" && p.ours >= SELL_FLOOR);'),
    "weight dropped (raw gap order)": ("const score = Math.abs(gap) * weight;", "const score = Math.abs(gap);"),
    "weight uses the larger value": ("const weight = Math.min(ours, value);", "const weight = Math.max(ours, value);"),
    "score sorted ascending": ("const byScore = (a, b) => b.market.score - a.market.score || a.order - b.order;",
                               "const byScore = (a, b) => a.market.score - b.market.score || a.order - b.order;"),
    "players under the floor not counted": ("const belowSellFloor = sellable.length - sellAll.length;", "const belowSellFloor = 0;"),
    # JEG-833: Buy at the charts' rank. The first is the bug the ticket names (Buy by consensus gap: the overall top).
    "buy by consensus gap (JEG-833 bug returns)": ("const buyAll = buyable.filter(p => finite(p.market.rankGap) && p.market.rankGap <= -BUY_RANK_MARGIN)",
                                                   "const buyAll = buyable.filter(p => true)"),
    "rank margin dropped": ("p.market.rankGap <= -BUY_RANK_MARGIN", "p.market.rankGap < 0"),
    "rank margin moved": ("const BUY_RANK_MARGIN = 2;", "const BUY_RANK_MARGIN = 4;"),
    "rank gap sign flipped": ("m.rankGap = oursDesc[i] - p.ours;", "m.rankGap = p.ours - oursDesc[i];"),
    "ranks taken on the searched subset": ("    rankEquivalents(players, minCharts);\n    if (keep) players = players.filter(p => keep(p.row));",
                                           "    if (keep) players = players.filter(p => keep(p.row));\n    rankEquivalents(players, minCharts);"),
    "ranks taken across positions": ("      if (!byPos.has(p.row.pos)) byPos.set(p.row.pos, []);\n      byPos.get(p.row.pos).push(p);",
                                     "      if (!byPos.has(0)) byPos.set(0, []);\n      byPos.get(0).push(p);"),
    # JEG-842: the bug the ticket names (an out player in Buy) and each way to half-fix it.
    "out players recommended (JEG-842 bug returns)": ('if (row.espnProjectsZero) return "out";', ""),
    "estimated values trusted": ('return Object.keys(cells).some(key => finite(cells[key].value) && est[key]) ? "estimated" : null;', "return null;"),
    "sell not excluded": ("const sell = sellAll.filter(p => !flagged(p) && !thin(p));", "const sell = sellAll.filter(p => !thin(p));"),
    "buy not excluded": ("const buy = buyAll.filter(p => !flagged(p) && !thin(p));", "const buy = buyAll.filter(p => !thin(p));"),
    "exclusion not counted": ("leftOut: leftOut.length,", "leftOut: 0,"),
    "scale-only players not counted": ("scaleOnly: scaleOnly.length, scaleOnlyNames", "scaleOnly: 0, scaleOnlyNames"),
    "buy score uses the larger value": ("m.buyScore = Math.abs(m.rankGap) * Math.min(p.ours, m.value);", "m.buyScore = Math.abs(m.rankGap) * Math.max(p.ours, m.value);"),
    # JEG-851: single-chart mode and chart-as-our-value.
    "single chart minCharts always 2": ("const minCharts = effectiveCharts.length === 1 ? 1 : 2;", "const minCharts = 2;"),
    "self-comparison not excluded": ("const effectiveCharts = CHART_KEYS.includes(ourKey) ? charts.filter(c => c !== ourKey) : charts;",
                                     "const effectiveCharts = charts;"),
    "singleChart not reported": ("singleChart: effectiveCharts.length === 1 ? effectiveCharts[0] : null", "singleChart: null"),
    "chart keys not in OUR_KEYS": ('const OUR_KEYS = ["ddf_value", "ddf_value_charts", "ddf_value_projections", "espn", "cbsros", "razzball"].concat(CHART_KEYS);',
                                   'const OUR_KEYS = ["ddf_value", "ddf_value_charts", "ddf_value_projections", "espn", "cbsros", "razzball"];'),
}


class TradeTargetsTest(unittest.TestCase):
    def test_consensus_rules(self):
        self.assertEqual(check(run_targets(TARGETS_JS)), [])

    def test_checks_fail_on_broken_builds(self):
        source = TARGETS_JS.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            for name, (old, new) in MUTATIONS.items():
                with self.subTest(mutation=name):
                    self.assertIn(old, source, f"mutation anchor for {name!r} is stale")
                    broken = Path(tmp) / f"targets_{abs(hash(name))}.js"
                    broken.write_text(source.replace(old, new, 1), encoding="utf-8")
                    self.assertNotEqual(check(run_targets(broken)), [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
