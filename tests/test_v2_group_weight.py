"""v2 Trade targets, check 2: potential positional weight inflation (JEG-476, JEG-489).

TradeValueTargets.weightCheck compares each position (and each position's DDF
starters / bench) by SHARE of the total, DDF Value against the market, over the
same players on both sides:

    gap = (group market / all market) / (group DDF Value / all DDF Value) - 1

These checks pin, against an independent Python recomputation:

  * the gap equals the formula for the consensus (median of 2+ charts) and for
    each chart;
  * a chart whose whole scale is 80% of ours (every value x0.8) shows 0% in
    every group: raw totals would read "-20% everywhere" (the JEG-489 bug);
  * a group with fewer than 3 priced players has no number; the headline never
    names a group under 8 players;
  * a player the market does not price (or fewer than 2 charts price, for the
    consensus) is left out of both sides, never read as 0;
  * the signal is Sell at +10% or more, Buy at -10% or less, else Fair;
  * a group's players are sorted by the group's signal (sell: biggest overpay
    first; buy: biggest underpay first).

Discrimination: test_checks_fail_on_broken_builds mutates targets.js (raw
totals instead of shares, mean for median, missing read as 0, headline minimum
dropped, signal sign flipped, tier ignored, ...) and requires each to fail.
"""
from __future__ import annotations

import json
import shutil
import statistics
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS_JS = ROOT / "app" / "v2" / "targets.js"
CHARTS = ["usatoday", "fantasycalc", "fantasypros"]


def build_rows() -> list[dict]:
    rows, key = [], 0

    def add(pos, tier, ours, usa, fc, fp):
        nonlocal key
        key += 1
        rows.append({"player_key": key, "name": f"{pos}{key}", "pos": pos, "ddfTier": tier,
                     "values": {"ddf_value": ours, "usatoday": usa, "fantasycalc": fc, "fantasypros": fp}})

    # QB: 10 players, starters priced well under DDF Value by the market.
    for i in range(6):
        add("QB", "starter", 30.0 - i, (30.0 - i) * 0.7, (30.0 - i) * 0.8, (30.0 - i) * 0.75)
    for i in range(4):
        add("QB", "bench", 8.0 - i, (8.0 - i) * 1.0, (8.0 - i) * 1.0, (8.0 - i) * 1.0)
    # RB: 12 players, the market pays more than DDF Value for starters.
    for i in range(8):
        add("RB", "starter", 25.0 - i, (25.0 - i) * 1.3, (25.0 - i) * 1.2, (25.0 - i) * 1.25)
    for i in range(4):
        add("RB", "bench", 6.0 - i, (6.0 - i) * 0.9, (6.0 - i) * 0.9, (6.0 - i) * 0.95)
    # WR: 9 players priced as DDF Value does (fair).
    for i in range(9):
        add("WR", "starter" if i < 6 else "bench", 20.0 - i, 20.0 - i + 0.2, 20.0 - i - 0.2, 20.0 - i)
    # TE: 2 players only (too few to show), and one with a single chart (no consensus) and a missing DDF Value.
    add("TE", "starter", 15.0, 20.0, 20.0, 20.0)
    add("TE", "starter", 14.0, 19.0, 19.0, None)
    add("TE", "starter", 13.0, 18.0, None, None)       # one chart only: no consensus
    add("TE", "starter", None, 18.0, 18.0, 18.0)       # no DDF Value: left out
    # A kicker is never grouped.
    add("K", "starter", 4.0, 4.0, 4.0, 4.0)
    return rows[::-1]   # engine order is not gap order


def expected(rows, column):
    """Independent recomputation. Returns {group key: (n, gap or None)}."""
    pairs = []
    for r in rows:
        v = r["values"]
        if v["ddf_value"] is None or r["pos"] not in ("QB", "RB", "WR", "TE"):
            continue
        if column == "consensus":
            priced = [v[c] for c in CHARTS if v.get(c) is not None]
            market = statistics.median(priced) if len(priced) >= 2 else None
        else:
            market = v.get(column)
        if market is not None:
            pairs.append((r, v["ddf_value"], market))
    to, tm = sum(p[1] for p in pairs), sum(p[2] for p in pairs)
    out = {}
    for pos in ("QB", "RB", "WR", "TE"):
        for tier in (None, "starter", "bench"):
            members = [p for p in pairs if p[0]["pos"] == pos and (tier is None or p[0]["ddfTier"] == tier)]
            k = pos if tier is None else f"{pos}|{tier}"
            if len(members) < 3:
                out[k] = (len(members), None)
                continue
            o, m = sum(p[1] for p in members), sum(p[2] for p in members)
            out[k] = (len(members), (m / tm) / (o / to) - 1)
    return out


HARNESS = """
const T = require(process.argv[1]);
const input = JSON.parse(process.argv[2]);
const r = T.weightCheck(input.rows, input.charts, {ours: "ddf_value"});
const scaled = input.rows.map(x => ({...x, values: {...x.values, fantasycalc: x.values.ddf_value === null ? null : x.values.ddf_value * 0.8}}));
const s = T.weightCheck(scaled, ["fantasycalc"], {ours: "ddf_value"});
const cells = g => Object.fromEntries(r.columns.map(c => [c, [g.cells[c].n, g.cells[c].gap, g.cells[c].signal]]));
const head = g => g ? g.key : null;
console.log(JSON.stringify({
  groups: r.groups.map(g => ({key: g.key, n: g.n, cells: cells(g)})),
  headline: {over: head(r.headline.over), under: head(r.headline.under), biggest: head(r.headline.biggest)},
  scaled: s.groups.map(g => [g.key, g.cells.fantasycalc.gap]),
  qbStarterPlayers: r.playersOf(r.groups.find(g => g.key === "QB|starter")).map(p => [p.row.player_key, p.gap]),
  rbStarterPlayers: r.playersOf(r.groups.find(g => g.key === "RB|starter")).map(p => [p.row.player_key, p.gap]),
  signals: [-0.1, -0.0999, 0, 0.0999, 0.1, null].map(g => T.weightSignal(g)),
  compared: r.compared,
}));
"""


def run(path: Path) -> dict:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is not available")
    payload = json.dumps({"rows": build_rows(), "charts": CHARTS})
    out = subprocess.run([node, "-e", HARNESS, str(path), payload], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def check(result: dict) -> list[str]:
    errors: list[str] = []
    rows = build_rows()
    for column in ["consensus"] + CHARTS:
        want = expected(rows, column)
        for g in result["groups"]:
            n, gap, _ = g["cells"][column]
            wn, wgap = want[g["key"]]
            if n != wn:
                errors.append(f"{column} {g['key']}: n {n}, want {wn}")
            if (gap is None) != (wgap is None) or (gap is not None and abs(gap - wgap) > 1e-9):
                errors.append(f"{column} {g['key']}: gap {gap}, want {wgap}")
    # The share check removes a uniform scale: x0.8 on a whole chart reads 0% in every group.
    for key, gap in result["scaled"]:
        if gap is not None and abs(gap) > 1e-9:
            errors.append(f"a chart at 80% scale must read 0% in {key}, got {gap}")
    # Too few players: no number, no signal. TE has 2 priced players.
    te = next(g for g in result["groups"] if g["key"] == "TE")
    if te["cells"]["consensus"][1] is not None or te["cells"]["consensus"][2] is not None:
        errors.append(f"a 2-player group must show no gap or signal: {te}")
    # The headline names only groups with 8+ players: QB (10), RB (12), WR (9) qualify; RB starters (8) too;
    # QB starters (6) and TE do not.
    h = result["headline"]
    if h["under"] not in ("QB", "QB|starter") or h["under"] == "QB|starter":
        errors.append(f"headline under must be a group of 8+ players (QB), got {h['under']}")
    if h["over"] not in ("RB", "RB|starter"):
        errors.append(f"headline over must be RB or RB starters (8+ players), got {h['over']}")
    sizes = {g["key"]: g["n"] for g in result["groups"]}
    for name in h.values():
        if name and sizes[name] < 8:
            errors.append(f"headline names {name} with only {sizes[name]} players")
    # Signals at the 10% line.
    if result["signals"] != ["buy", "fair", "fair", "fair", "sell", None]:
        errors.append(f"signal thresholds wrong: {result['signals']}")
    qb = next(g for g in result["groups"] if g["key"] == "QB|starter")
    if qb["cells"]["consensus"][2] != "buy":
        errors.append(f"QB starters are priced far under DDF Value: want buy, got {qb['cells']['consensus']}")
    # Players sorted by the group's signal.
    gaps = [g for _, g in result["qbStarterPlayers"]]
    if gaps != sorted(gaps):
        errors.append(f"a buy group lists the biggest underpay first: {gaps}")
    gaps = [g for _, g in result["rbStarterPlayers"]]
    if gaps != sorted(gaps, reverse=True):
        errors.append(f"a sell group lists the biggest overpay first: {gaps}")
    # Missing is left out, never 0: 3 TE rows qualify as priced by 2+ charts with DDF Value... only two do.
    want_compared = sum(1 for r in rows if r["pos"] in ("QB", "RB", "WR", "TE") and r["values"]["ddf_value"] is not None
                        and len([r["values"][c] for c in CHARTS if r["values"].get(c) is not None]) >= 2)
    if result["compared"] != want_compared:
        errors.append(f"compared {result['compared']}, want {want_compared}")
    return errors


MUTATIONS = {
    "raw totals instead of shares": ("const gap = shown ? (market / totalMarket) / (ours / totalOurs) - 1 : null;",
                                     "const gap = shown ? market / ours - 1 : null;"),
    "mean instead of median": ("return priced.length >= 2 ? median(priced) : null;",
                               "return priced.length >= 2 ? priced.reduce((a, b) => a + b, 0) / priced.length : null;"),
    "single chart makes a consensus": ("return priced.length >= 2 ? median(priced) : null;",
                                       "return priced.length >= 1 ? median(priced) : null;"),
    "missing chart read as zero": ("return finite(row.values[column]) ? row.values[column] : null;",
                                   "return finite(row.values[column]) ? row.values[column] : 0;"),
    "headline minimum dropped": ("g.consensus.n >= WEIGHT_MIN_HEADLINE &&", "g.consensus.n >= 3 &&"),
    "small group shows a number": ("members.length >= WEIGHT_MIN_SHOW &&", "members.length >= 1 &&"),
    "signal line moved": ("const WEIGHT_SIGNAL = 0.10;", "const WEIGHT_SIGNAL = 0.25;"),
    "buy and sell swapped": ('return gap >= WEIGHT_SIGNAL ? "sell" : gap <= -WEIGHT_SIGNAL ? "buy" : "fair";',
                             'return gap >= WEIGHT_SIGNAL ? "buy" : gap <= -WEIGHT_SIGNAL ? "sell" : "fair";'),
    "tier ignored": ("row.pos === group.pos && (!group.tier || row.ddfTier === group.tier)", "row.pos === group.pos"),
    "players unsorted": ('list.sort((a, b) => signal === "buy" ? a.gap - b.gap : signal === "sell" ? b.gap - a.gap : Math.abs(b.gap) - Math.abs(a.gap));',
                         ""),
    "no-DDF player kept": ("filter(p => finite(p.ours) && finite(p.market)", "filter(p => finite(p.market)"),
}


class GroupWeightTest(unittest.TestCase):
    def test_share_rules(self):
        self.assertEqual(check(run(TARGETS_JS)), [])

    def test_checks_fail_on_broken_builds(self):
        source = TARGETS_JS.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            for name, (old, new) in MUTATIONS.items():
                with self.subTest(mutation=name):
                    self.assertIn(old, source, f"mutation anchor for {name!r} is stale")
                    broken = Path(tmp) / f"targets_{abs(hash(name))}.js"
                    broken.write_text(source.replace(old, new, 1), encoding="utf-8")
                    try:
                        errors = check(run(broken))
                    except subprocess.CalledProcessError:
                        errors = ["crashed"]
                    self.assertNotEqual(errors, [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
