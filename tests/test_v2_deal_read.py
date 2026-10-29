"""v2 Compare a trade: the rule-based deal read in app/v2/trade.js (JEG-487, contract CT-08).

Three nets from engine series: DDF Value (V), Trade chart average (M: JEG-832 #780, the mean of the compared
charts' nets, at least MIN_DEAL_CHARTS = 3 complete charts, else no read) and DDF Value
(P, ddf_value_projections). The side of a net is win at or above max(1, 3% of the average side total of that
series), lose at or below the negative of that, else even. The read is a fixed table on (V, M): V win with M lose is
"DDF Value likes it. The market doesn't." (JEG-950, Jeremy 2026-10-26), V lose with M win is "Trap". P is a
production sentence against V. These checks pin, against an independent recomputation:

  * the side thresholds, including the 1.0 floor and the 3% scale on a large trade, at both edges;
  * all nine (V, M) combinations land in their own cell, and the two named reads are where the ticket puts them;
  * the win|lose read has no call to action and its text is the real market gap, one decimal and the right
    direction word, from the pure helper (marketGapText) and from dealRead (never hard-coded);
  * the read does not depend on P, only the production sentence does;
  * a series with a missing player value has no net: no V, or fewer than 3 complete charts for M, means no read
    (never a 0 standing in), a missing P only drops the production sentence.

Discrimination: test_checks_fail_on_broken_builds mutates trade.js (floor dropped, percentage changed, arbitrage and
trap swapped, a missing value read as 0, the production sentence inverted, P changing the cell) and requires failures.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRADE_JS = ROOT / "app" / "v2" / "trade.js"
KEYS = {"v": "ddf_value", "p": "ddf_value_projections"}
# JEG-832: M is the mean of the compared charts' nets; dealRead takes the chart keys as its third argument.
CHARTS = ["usatoday", "fantasycalc", "fantasypros"]


def side(net, give, receive):
    threshold = max(1.0, 0.03 * (give + receive) / 2)
    return "win" if net >= threshold else "lose" if net <= -threshold else "even"


def rows_for(nets, total=20.0, missing=None):
    """One give row and one receive row whose per-series nets are `nets` (give total `total`)."""
    give = {"player_key": 1, "name": "G", "values": {}}
    receive = {"player_key": 2, "name": "R", "values": {}}
    for letter, key in KEYS.items():
        give["values"][key] = total
        receive["values"][key] = total + nets[letter]
    for chart in CHARTS:  # every chart nets the same, so the mean of their nets is nets["m"]
        give["values"][chart] = total
        receive["values"][chart] = total + nets["m"]
    for letter, who in (missing or []):
        for key in (CHARTS if letter == "m" else [KEYS[letter]]):
            (give if who == "give" else receive)["values"][key] = None
    return [give], [receive]


HARNESS = """
const T = require(process.argv[1]);
const cases = JSON.parse(process.argv[2]);
console.log(JSON.stringify(cases.map(c => {
  const r = T.dealRead(c.give, c.receive, c.charts || JSON.parse(process.argv[3]));
  return {id: c.id, kind: r.kind, cell: r.cell || null, title: r.title || null, action: typeof r.action === "string" ? r.action : null,
    sides: [r.value.side, r.market.side, r.projections.side], production: r.production || null, text: r.text};
})));
"""

# JEG-950: the win|lose sub-line is built from the real market net by a pure helper.
HELPER_HARNESS = """
const T = require(process.argv[1]);
console.log(JSON.stringify({up: T.marketGapText(8.24), down: T.marketGapText(-8.2), zero: T.marketGapText(0),
  wordUp: T.marketGapWord(8.2), wordDown: T.marketGapWord(-8.2), wordZero: T.marketGapWord(0)}));
"""


def gap_text(net):
    """The win|lose sub-line, recomputed independently of trade.js."""
    if net == 0:
        return "The trade charts call it even."
    if net > 0:
        return f"The trade charts have you {abs(net):.1f} points ahead."
    return f"The trade charts have you {abs(net):.1f} points behind, so the other manager will likely see it as their win."


def case_set():
    cases = []
    sides = {"win": 5.0, "even": 0.0, "lose": -5.0}
    for v, vn in sides.items():
        for m, mn in sides.items():
            give, receive = rows_for({"v": vn, "m": mn, "p": vn})
            case = {"id": f"cell {v}|{m}", "give": give, "receive": receive, "want_cell": f"{v}|{m}"}
            if (v, m) == ("win", "lose"):
                # JEG-950: the live read shows the real market gap (mn), and no call to action.
                case.update({"want_text": gap_text(mn), "want_action": ""})
            cases.append(case)
    # Thresholds: small trade (floor of 1.0) and large trade (3% of the average side total).
    for net, want in ((1.0, "win"), (0.99, "even"), (-0.99, "even"), (-1.0, "lose")):
        give, receive = rows_for({"v": net, "m": net, "p": net}, total=10.0)
        cases.append({"id": f"small {net}", "give": give, "receive": receive, "want_sides": [want, want, want]})
    # 100 given, 103 received: average side 101.5, 3% = 3.045 (a loss of 3 averages 98.5, so its line is 2.955)
    for net, want in ((3.1, "win"), (3.0, "even"), (-2.9, "even"), (-3.0, "lose")):
        give, receive = rows_for({"v": net, "m": net, "p": net}, total=100.0)
        cases.append({"id": f"large {net}", "give": give, "receive": receive, "want_sides": [want, want, want]})
    # P disagrees with V: live again since JEG-1073 (DDF Value = the Adjusted trade charts, the projections
    # version is the alternate); the sentence says production does not back the value.
    give, receive = rows_for({"v": 5.0, "m": -5.0, "p": -5.0})
    cases.append({"id": "p disagrees", "give": give, "receive": receive, "want_cell": "win|lose", "production": "not"})
    give, receive = rows_for({"v": 5.0, "m": -5.0, "p": 5.0})
    cases.append({"id": "p agrees", "give": give, "receive": receive, "want_cell": "win|lose", "production": "backs"})
    # Missing values.
    give, receive = rows_for({"v": 5.0, "m": -5.0, "p": 5.0}, missing=[("p", "receive")])
    cases.append({"id": "p missing", "give": give, "receive": receive, "want_cell": "win|lose", "production": None,
                  "want_text": gap_text(-5.0)})
    give, receive = rows_for({"v": 5.0, "m": -5.0, "p": 5.0}, missing=[("m", "give")])
    cases.append({"id": "m missing", "give": give, "receive": receive, "want_kind": "incomplete"})
    give, receive = rows_for({"v": 5.0, "m": -5.0, "p": 5.0}, missing=[("v", "receive")])
    cases.append({"id": "v missing", "give": give, "receive": receive, "want_kind": "incomplete"})
    # JEG-832: fewer than MIN_DEAL_CHARTS complete charts is no market read.
    give, receive = rows_for({"v": 5.0, "m": -5.0, "p": 5.0})
    cases.append({"id": "two charts", "give": give, "receive": receive, "charts": CHARTS[:2], "want_kind": "incomplete"})
    give, receive = rows_for({"v": 5.0, "m": -5.0, "p": 5.0}, missing=[("m", "give")])
    cases.append({"id": "one chart missing a value", "give": give, "receive": receive, "want_kind": "incomplete"})
    return cases


def run(path: Path):
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is not available")
    cases = case_set()
    out = subprocess.run([node, "-e", HARNESS, str(path), json.dumps(cases), json.dumps(CHARTS)],
                         capture_output=True, text=True, check=True)
    return cases, {r["id"]: r for r in json.loads(out.stdout)}


def run_helper(path: Path) -> list[str]:
    """JEG-950: the win|lose sub-line helper, on its own (a positive net the cells cannot produce)."""
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is not available")
    out = subprocess.run([node, "-e", HELPER_HARNESS, str(path)], capture_output=True, text=True, check=True)
    got = json.loads(out.stdout)
    errors = []
    if got["up"] != "The trade charts have you 8.2 points ahead.":
        errors.append(f"marketGapText(8.24) = {got['up']!r}")
    if got["down"] != "The trade charts have you 8.2 points behind, so the other manager will likely see it as their win.":
        errors.append(f"marketGapText(-8.2) = {got['down']!r}")
    if got["zero"] != "The trade charts call it even.":
        errors.append(f"marketGapText(0) = {got['zero']!r}")
    if (got["wordUp"], got["wordDown"], got["wordZero"]) != ("ahead", "behind", "even"):
        errors.append(f"marketGapWord = {got['wordUp']!r}/{got['wordDown']!r}/{got['wordZero']!r}")
    return errors


def check(cases, results) -> list[str]:
    errors = []
    titles = {}
    for c in cases:
        r = results[c["id"]]
        if "want_cell" in c and r["cell"] != c["want_cell"]:
            errors.append(f"{c['id']}: cell {r['cell']}, want {c['want_cell']}")
        if "want_sides" in c and r["sides"] != c["want_sides"]:
            errors.append(f"{c['id']}: sides {r['sides']}, want {c['want_sides']}")
        if "want_kind" in c and r["kind"] != c["want_kind"]:
            errors.append(f"{c['id']}: kind {r['kind']}, want {c['want_kind']}")
        if "want_kind" in c and r["cell"] is not None:
            errors.append(f"{c['id']}: an incomplete series must give no cell, got {r['cell']}")
        if c["id"].startswith("cell "):
            titles[r["cell"]] = r["title"]
        if "want_text" in c and r["text"] != c["want_text"]:
            errors.append(f"{c['id']}: text {r['text']!r}, want {c['want_text']!r}")
        if "want_action" in c and r["action"] != c["want_action"]:
            errors.append(f"{c['id']}: action {r['action']!r}, want {c['want_action']!r}")
        prod = c.get("production", "unchecked")
        if prod is None and r["production"] is not None:
            errors.append(f"{c['id']}: a missing P must drop the production sentence, got {r['production']!r}")
        if prod == "not" and not (r["production"] or "").startswith("Projected production does not back"):
            errors.append(f"{c['id']}: production {r['production']!r}")
        if prod == "backs" and not (r["production"] or "").startswith("Projected production backs"):
            errors.append(f"{c['id']}: production {r['production']!r}")
        if prod == "inconclusive" and not (r["production"] or "").startswith("Production check inconclusive"):
            errors.append(f"{c['id']}: production {r['production']!r}")
    if len(set(titles.values())) != 9 or len(titles) != 9:
        errors.append(f"the nine cells need nine distinct reads: {titles}")
    if "DDF Value likes it. The market doesn't." != titles.get("win|lose"):
        errors.append(f"win|lose must be \"DDF Value likes it. The market doesn't.\", got {titles.get('win|lose')!r}")
    if "Trap" != titles.get("lose|win"):
        errors.append(f"lose|win must be 'Trap', got {titles.get('lose|win')!r}")
    return errors


MUTATIONS = {
    "floor dropped": ("const threshold = Math.max(1, 0.03 * ((give + receive) / 2));", "const threshold = 0.03 * ((give + receive) / 2);"),
    "percentage changed": ("0.03 * ((give + receive) / 2)", "0.10 * ((give + receive) / 2)"),
    "value-likes-it and trap swapped": ('"win|lose": {title: "DDF Value likes it. The market doesn\'t."', '"win|lose": {title: "Trap"'),
    "hard-coded direction word": ('const marketGapWord = net => (net > 0 ? "ahead" : net < 0 ? "behind" : "even");',
                                  'const marketGapWord = net => (net >= 0 ? "ahead" : "behind");'),
    "missing read as zero": ("      if (missing.length) return {key, give: null, receive: null, net: null, missing};",
                             "      if (missing.length && false) return {key, give: null, receive: null, net: null, missing};"),
    "production inverted": ("    if (p === v) return p === \"win\"", "    if (p !== v) return p === \"win\""),
    "projections move the cell": ("cell: cellKey, title: cell.title",
                                  "cell: `${out.value.side}|${out.projections.side}`, title: cell.title"),
    "no incomplete on too-few charts": ("if (market.tooFew) {", "if (false) {"),
}


class DealReadTest(unittest.TestCase):
    def test_rules(self):
        cases, results = run(TRADE_JS)
        self.assertEqual(check(cases, results), [])

    def test_market_gap_helper(self):
        self.assertEqual(run_helper(TRADE_JS), [])

    def test_checks_fail_on_broken_builds(self):
        source = TRADE_JS.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            for name, (old, new) in MUTATIONS.items():
                with self.subTest(mutation=name):
                    self.assertIn(old, source, f"mutation anchor for {name!r} is stale")
                    broken = Path(tmp) / f"trade_{abs(hash(name))}.js"
                    broken.write_text(source.replace(old, new, 1), encoding="utf-8")
                    try:
                        errors = check(*run(broken)) + run_helper(broken)
                    except (subprocess.CalledProcessError, KeyError, TypeError):
                        errors = ["crashed"]
                    self.assertNotEqual(errors, [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
