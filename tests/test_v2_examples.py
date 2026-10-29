"""JEG-1191 path B: the rotating examples on Compare are one of each thing DDF catches (app/v2/trade.js pickShowcase).

The picker only chooses which trades to load; the page judges each with today's Deal read (dealRead). The checks pin:

  * the examples come in slot order, each passing its slot's existing read: miss = the arbitrage cell
    ("DDF Value likes it. The market doesn't.", win|lose, charts not split, Likely), trap = "Trap" (lose|win,
    charts not split), production = DDF Value says win while DDF Value (projections) says lose;
  * the pool is the top players by DDF Value that DDF Value, DDF Value (projections) and every compared chart
    price: a player missing a chart never appears;
  * no player is in two examples;
  * each slot takes its best trade (fewest players first, then its score) sharing no player with an earlier slot;
    the list matches a brute-force walk over every 1-for-1 to 2-for-2 trade in the pool;
  * deterministic: the same rows give the same list;
  * too few charts gives no examples (the page then falls back to the JEG-1190 sample);
  * on this week's data (Python reference rows, 12 teams, Full PPR) every example passes the same read.

test_checks_fail_on_broken_builds runs the checks on mutated copies (a split trap allowed, an even production check
allowed, repeats allowed, the biggest trades first, a player missing a chart allowed) and requires each to fail.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRADE_JS = ROOT / "app" / "v2" / "trade.js"
CHARTS = ["usatoday", "fantasycalc", "fantasypros", "cbs"]

HARNESS = r"""
const T = require(process.argv[1]);
const input = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));
const out = {};
const keys = c => c.give.map(r => r.player_key).concat(c.receive.map(r => r.player_key));
const show = c => ({kind: c.kind, give: c.give.map(r => r.player_key), receive: c.receive.map(r => r.player_key),
  cell: c.deal.cell, split: c.deal.market.split, accept: c.deal.market.charts.accept, v: c.deal.value.side, p: c.deal.projections.side});
const SLOTS = [
  ["miss", d => (d.cell === "win|lose" && !d.market.split ? d.value.net : null)],
  ["trap", d => (d.cell === "lose|win" && !d.market.split ? -d.value.net : null)],
  ["production", d => (d.value.side === "win" && d.projections.side === "lose" ? -d.projections.net : null)]];
for (const [name, rows] of Object.entries(input.pools)) {
  const picks = T.pickShowcase(rows, input.charts);
  const again = T.pickShowcase(rows, input.charts);
  // Brute force: every 1-for-1 .. 2-for-2 in the pool, read by dealRead, ranked per slot and taken in slot order.
  const need = ["ddf_value", "ddf_value_projections"].concat(input.charts);
  const top = rows.filter(r => need.every(k => typeof r.values[k] === "number"))
    .sort((a, b) => b.values.ddf_value - a.values.ddf_value || String(a.player_key).localeCompare(String(b.player_key))).slice(0, T.EXAMPLE_POOL);
  const sets = size => { const s = []; for (let a = 0; a < top.length; a++) { if (size === 1) s.push([top[a]]); else for (let b = a + 1; b < top.length; b++) s.push([top[a], top[b]]); } return s; };
  const all = [];
  for (const g of [1, 2]) for (const r of [1, 2]) for (const give of sets(g)) for (const receive of sets(r)) {
    if (receive.some(x => give.includes(x))) continue;
    const deal = T.dealRead(give, receive, input.charts);
    if (deal.kind === "read") all.push({give, receive, deal, size: g + r});
  }
  const tie = c => keys(c).map(String).join(",");
  const used = new Set(); const brute = [];
  for (const [kind, score] of SLOTS) {
    const list = all.filter(c => score(c.deal) !== null).map(c => ({...c, score: score(c.deal), kind}))
      .sort((a, b) => a.size - b.size || b.score - a.score || tie(a).localeCompare(tie(b)));
    const c = list.find(item => keys(item).every(k => !used.has(k)));
    if (!c) continue;
    keys(c).forEach(k => used.add(k)); brute.push(c);
  }
  out[name] = {picks: picks.map(show), again: again.map(show), brute: brute.map(show), pool: top.map(r => r.player_key),
    few: T.pickShowcase(rows, input.charts.slice(0, 2)).length};
}
console.log(JSON.stringify(out));
"""


def player(key, ddf, proj, charts):
    return {"player_key": key, "name": f"P{key}", "values": {"ddf_value": ddf, "ddf_value_projections": proj,
                                                            **dict(zip(CHARTS, charts))}}


# A small pool (key, DDF Value, projections, the four charts) with a trade for each slot, split-chart traps, even
# production checks, 2-for-2s and one high-value player missing a chart (key 99), who must never appear. Chosen so
# every mutation below changes the list.
SYNTH = [player(k, d, pr, c) for k, d, pr, c in [
    (1, 61, 62, [51, 76, 52, 54]), (2, 53, 49, [46, 42, 46, 35]), (3, 26, 27, [34, 26, 25, 26]),
    (4, 67, 62, [56, 52, 55, 57]), (5, 41, 36, [45, 40, 40, 26]), (6, 43, 37, [46, 45, 46, 44]),
    (7, 51, 45, [40, 62, 45, 41]), (8, 22, 24, [23, 22, 24, 22]), (9, 37, 37, [37, 40, 47, 40]),
    (10, 16, 17, [17, 16, 16, 17]), (99, 80, 78, [60, None, 61, 62]),
]]


def live_rows():
    """This week's rows from the Python reference (12 teams, Full PPR, Indexed), or None if it cannot run."""
    sys.path.insert(0, str(ROOT / "pipelines"))
    try:
        import value_reference as R
        inp = R.Inputs.load(R.FIXTURE, R.PLAYERS)
        week = R.freshness(inp)["current_week"]
        res = R.compute(inp, {"scoring": "ppr", "teams": 12, "superflex": 0}, hist=R.History(R.HISTORY),
                        divergence_exclusions=R.load_divergence_exclusions(week=week))
    except Exception:  # noqa: BLE001 - the live check is a bonus; the synthetic pool always runs
        return None
    return [{"player_key": k, "name": k, "values": v} for k, v in res["views"]["indexed"].items()]


def run(trade_js: Path, pools: dict) -> dict:
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"pools": pools, "charts": CHARTS}, f)
    out = subprocess.run(["node", "-e", HARNESS, str(trade_js), f.name], check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


def check(trade_js: Path, pools: dict) -> list[str]:
    errors = []
    try:
        got = run(trade_js, pools)
    except subprocess.CalledProcessError as exc:
        return [f"harness failed: {exc.stderr[:300]}"]
    for name, res in got.items():
        picks = res["picks"]
        if not picks:
            errors.append(f"{name}: no examples")
        seen = set()
        kinds = [c["kind"] for c in picks]
        if kinds != [k for k in ("miss", "trap", "production") if k in kinds]:
            errors.append(f"{name}: not in slot order: {kinds}")
        for i, c in enumerate(picks):
            ok = {"miss": c["cell"] == "win|lose" and not c["split"] and c["accept"] == "Likely",
                  "trap": c["cell"] == "lose|win" and not c["split"],
                  "production": c["v"] == "win" and c["p"] == "lose"}.get(c["kind"], False)
            if not ok:
                errors.append(f"{name} #{i + 1}: does not pass its read: {c}")
            players = c["give"] + c["receive"]
            if any(k not in res["pool"] for k in players):
                errors.append(f"{name} #{i + 1}: a player outside the fully priced pool: {players}")
            if seen & set(players):
                errors.append(f"{name} #{i + 1}: a player repeats across examples: {players}")
            seen |= set(players)
        if picks != res["brute"]:
            errors.append(f"{name}: list {picks} != brute-force ranking {res['brute']}")
        if res["again"] != picks:
            errors.append(f"{name}: not deterministic")
        if res["few"] != 0:
            errors.append(f"{name}: two charts should give no examples, gave {res['few']}")
    return errors


class ShowcaseExamplesTest(unittest.TestCase):
    def test_synthetic_pool(self):
        self.assertEqual(check(TRADE_JS, {"synthetic": SYNTH}), [])

    def test_live_week(self):
        rows = live_rows()
        if rows is None:
            self.skipTest("the Python reference could not run on this checkout")
        self.assertEqual(check(TRADE_JS, {"live ppr/12": rows}), [])

    def test_checks_fail_on_broken_builds(self):
        source = TRADE_JS.read_text(encoding="utf-8")
        broken = {
            "split trap allowed": source.replace(
                'deal.cell === "lose|win" && !deal.market.split ? -deal.value.net : null', 'deal.cell === "lose|win" ? -deal.value.net : null', 1),
            "even production check allowed": source.replace(
                'deal.projections.side === "lose" ? -deal.projections.net', 'deal.projections.side !== "win" ? -deal.projections.net', 1),
            "repeats allowed": source.replace("const c = lists[i].find(item => disjoint(item, used));",
                                              "const c = lists[i][0];", 1),
            "biggest trades first": source.replace("a.size - b.size || b.score - a.score", "b.size - a.size || b.score - a.score", 1),
            "a player missing a chart allowed": source.replace(
                "const need = [DEAL_KEYS.value, DEAL_KEYS.projections].concat(chartKeys || []);",
                "const need = [DEAL_KEYS.value];", 1),
        }
        with tempfile.TemporaryDirectory() as tmp:
            for name, body in broken.items():
                with self.subTest(mutation=name):
                    self.assertNotEqual(body, source, f"mutation anchor for {name!r} is stale")
                    path = Path(tmp) / f"{name.replace(' ', '_')}.js"
                    path.write_text(body, encoding="utf-8")
                    self.assertNotEqual(check(path, {"synthetic": SYNTH}), [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
