"""JEG-1191 path A: the rotating examples on Compare are trades the market misses (app/v2/trade.js pickMarketMisses).

The picker only chooses which trades to load; the page judges each with today's Deal read (dealRead). The checks pin:

  * every example is in the Deal read's arbitrage cell ("DDF Value likes it. The market doesn't.", win|lose) with
    the trade charts not split, so "Will they accept?" reads Likely;
  * the pool is the top players by DDF Value that DDF Value, DDF Value (projections) and every compared chart
    price: a player missing a chart never appears;
  * no player is in two examples;
  * order: fewest players first, then the biggest DDF Value gain; the list matches a brute-force walk over every
    1-for-1 to 2-for-2 trade in the pool;
  * deterministic: the same rows give the same list;
  * too few charts gives no examples (the page then falls back to the JEG-1190 sample);
  * on this week's data (Python reference rows, 12 teams, Full PPR) every example passes the same read.

test_checks_fail_on_broken_builds runs the checks on mutated copies (split charts allowed, repeats allowed, the
biggest trades first, a player missing a chart allowed) and requires each to fail. The Example line's claim
("DDF Value says you win; the charts favor the other side") is shown only while the current Deal read passes the
same test (isMarketMiss), so a change of charts, league or overrides after loading drops it.
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
const show = c => ({give: c.give.map(r => r.player_key), receive: c.receive.map(r => r.player_key),
  cell: c.deal.cell, split: c.deal.market.split, accept: c.deal.market.charts.accept, net: c.deal.value.net});
for (const [name, rows] of Object.entries(input.pools)) {
  const picks = T.pickMarketMisses(rows, input.charts);
  const again = T.pickMarketMisses(rows, input.charts);
  // Brute force: every 1-for-1 .. 2-for-2 in the pool, read by dealRead, ranked and picked greedily.
  const need = ["ddf_value", "ddf_value_projections"].concat(input.charts);
  const top = rows.filter(r => need.every(k => typeof r.values[k] === "number"))
    .sort((a, b) => b.values.ddf_value - a.values.ddf_value || String(a.player_key).localeCompare(String(b.player_key))).slice(0, T.EXAMPLE_POOL);
  const sets = size => { const s = []; for (let a = 0; a < top.length; a++) { if (size === 1) s.push([top[a]]); else for (let b = a + 1; b < top.length; b++) s.push([top[a], top[b]]); } return s; };
  const all = [];
  for (const g of [1, 2]) for (const r of [1, 2]) for (const give of sets(g)) for (const receive of sets(r)) {
    if (receive.some(x => give.includes(x))) continue;
    const deal = T.dealRead(give, receive, input.charts);
    if (deal.kind === "read" && deal.cell === "win|lose" && !deal.market.split) all.push({give, receive, deal, size: g + r});
  }
  const tie = c => keys(c).map(String).join(",");
  all.sort((a, b) => a.size - b.size || b.deal.value.net - a.deal.value.net || tie(a).localeCompare(tie(b)));
  const used = new Set(); const brute = [];
  for (const c of all) { if (brute.length >= T.EXAMPLE_COUNT) break; if (keys(c).some(k => used.has(k))) continue; keys(c).forEach(k => used.add(k)); brute.push(c); }
  out[name] = {picks: picks.map(show), again: again.map(show), brute: brute.map(show), pool: top.map(r => r.player_key),
    few: T.pickMarketMisses(rows, input.charts.slice(0, 2)).length,
    // The Example line's claim (isMarketMiss) on the first pick, the same trade read on two charts, and no read.
    claim: picks.length ? {pick: T.isMarketMiss(picks[0].deal), fewCharts: T.isMarketMiss(T.dealRead(picks[0].give, picks[0].receive,
      input.charts.slice(0, 2))), none: T.isMarketMiss(null)} : null};
}
console.log(JSON.stringify(out));
"""


def player(key, ddf, proj, charts):
    return {"player_key": key, "name": f"P{key}", "values": {"ddf_value": ddf, "ddf_value_projections": proj,
                                                            **dict(zip(CHARTS, charts))}}


# A small pool (key, DDF Value, projections, the four charts) with arbitrage 2-for-1s, a split-chart trade, 2-for-2s
# and one high-value player missing a chart (key 99), who must never appear. Chosen so every mutation below changes
# the list.
SYNTH = [player(k, d, pr, c) for k, d, pr, c in [
    (1, 29, 27, [30, 29, 30, 32]), (2, 29, 26, [31, 29, 31, 29]), (3, 53, 49, [66, 45, 46, 46]),
    (4, 17, 18, [18, 17, 18, 18]), (5, 39, 36, [41, 44, 42, 42]), (6, 55, 54, [48, 49, 46, 48]),
    (7, 39, 39, [38, 39, 42, 37]), (8, 57, 53, [49, 47, 70, 48]), (9, 19, 17, [20, 20, 18, 20]),
    (10, 33, 33, [35, 35, 41, 34]), (99, 80, 78, [60, None, 61, 62]),
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
        for i, c in enumerate(picks):
            if c["cell"] != "win|lose" or c["split"] or c["accept"] != "Likely":
                errors.append(f"{name} #{i + 1}: not a trade the market misses: {c}")
            players = c["give"] + c["receive"]
            if any(k not in res["pool"] for k in players):
                errors.append(f"{name} #{i + 1}: a player outside the fully priced pool: {players}")
            if seen & set(players):
                errors.append(f"{name} #{i + 1}: a player repeats across examples: {players}")
            seen |= set(players)
        sizes = [len(c["give"]) + len(c["receive"]) for c in picks]
        if sizes != sorted(sizes):
            errors.append(f"{name}: not fewest players first: {sizes}")
        if picks != res["brute"]:
            errors.append(f"{name}: list {picks} != brute-force ranking {res['brute']}")
        if res["again"] != picks:
            errors.append(f"{name}: not deterministic")
        if res["few"] != 0:
            errors.append(f"{name}: two charts should give no examples, gave {res['few']}")
        if res["claim"] is not None and res["claim"] != {"pick": True, "fewCharts": False, "none": False}:
            errors.append(f"{name}: isMarketMiss must hold for a pick and fail once the read no longer qualifies: {res['claim']}")
    return errors


class MarketMissExamplesTest(unittest.TestCase):
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
            "split charts allowed": source.replace(
                'deal.cell === "win|lose" && !deal.market.split);', 'deal.cell === "win|lose");', 1),
            "repeats allowed": source.replace("if (!disjoint(c, used)) continue;", "", 1),
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

    def test_example_claim_follows_the_current_read(self):
        # Codex review on #1193: after an example loads, Edit sources (fewer than three charts), league settings or
        # overrides can end the market-miss read while the players stay the same. The Example line's claim must come
        # from the current Deal read, not from the picker having filled its list.
        v2 = (ROOT / "app" / "v2" / "v2.js").read_text(encoding="utf-8")
        start = v2.index('$("v2CExampleText").textContent = ')
        claim = v2[start:v2.index(";", start)]
        self.assertIn("TradeValueTrade.isMarketMiss(compareView.deal)", claim)
        self.assertNotIn("fallback", claim)


if __name__ == "__main__":
    unittest.main()
