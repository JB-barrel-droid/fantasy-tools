"""v2 Compare a trade headline (JEG-505, contract CT-02): the two answers with a confidence level.

    "Should you propose or accept?"  by DDF Value: Yes / No / Even
    "Will they accept?"              from the published charts: Likely / Unlikely / Toss-up

Confidence is High / Medium / Low from agreement plus data quality (rules in the
header of tradeHeadlines in app/v2/trade.js and in docs/v2-design-notes.md):

  * agreement: 75% or more of the sources on the answer's side = High, 60% or more = Medium, else Low;
  * fewer than 3 sources caps at Medium;
  * a DDF net under 5% of the value traded (give + receive) reads Low even if every source agrees
    (Jeremy, 2026-10-09, on JEG-505);
  * a one-source (low-confidence) DDF Value in the trade lowers the DDF line one level.

Each case is a constructed trade (unanimous, split, one-source, razor-thin, ...). The expected answer is
recomputed here from the raw player values, straight from the rules above, not from trade.js output.

Discrimination: test_checks_fail_on_broken_builds runs the same cases against mutated copies of trade.js
(threshold removed, the 5% rule dropped, low-confidence ignored, "other manager wins or even" flipped, ...)
and requires each to fail.
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

CHARTS = ["usatoday", "fantasycalc", "fantasypros", "cbs"]
SERIES = ["ddf_value", "espn"] + CHARTS


def player(key, ddf, espn, usat, fc, fp, cbs):
    return {"player_key": key, "name": f"P{key}",
            "values": {"ddf_value": ddf, "espn": espn, "usatoday": usat, "fantasycalc": fc, "fantasypros": fp, "cbs": cbs}}


# name -> (give players, receive players, low_confidence)
CASES = {
    # Everything says you win by 20 of 120 traded: Yes, High; no chart has them winning or even: Unlikely, High.
    "unanimous": ([player(1, 50, 50, 50, 50, 50, 50)], [player(2, 70, 70, 70, 70, 70, 70)], False),
    # DDF says you win; two charts say you lose, two say you win; ESPN wins.
    "split": ([player(1, 50, 50, 50, 50, 50, 50)], [player(2, 62, 60, 40, 45, 70, 70)], False),
    # Same as unanimous, but a one-source DDF Value is in the trade: the DDF line drops High -> Medium.
    "one-source": ([player(1, 50, 50, 50, 50, 50, 50)], [player(2, 70, 70, 70, 70, 70, 70)], True),
    # Every source agrees but the DDF net is 2 of 100 traded (2%): Low on both lines.
    "razor-thin": ([player(1, 49, 49, 49, 49, 49, 49)], [player(2, 51, 51, 51, 51, 51, 51)], False),
    # DDF says you lose by 20; every chart agrees: No, High; charts have them winning: Likely, High.
    "lose-unanimous": ([player(1, 70, 70, 70, 70, 70, 70)], [player(2, 50, 50, 50, 50, 50, 50)], False),
    # Exactly 5% of 100 traded is not "under 5%": the thin rule does not fire.
    "five-percent": ([player(1, 47.5, 47.5, 47.5, 47.5, 47.5, 47.5)], [player(2, 52.5, 52.5, 52.5, 52.5, 52.5, 52.5)], False),
    # 4% of the value traded is under 5%: Low (the ticket's 3% proposal would have missed it).
    "four-percent": ([player(1, 48, 48, 48, 48, 48, 48)], [player(2, 52, 52, 52, 52, 52, 52)], False),
    # Only two charts price the trade: unanimous, but fewer than 3 published charts caps the second line at Medium.
    "two-charts": ([player(1, 50, 50, 50, 50, None, None)], [player(2, 70, 70, 70, 70, 70, 70)], False),
    # Three of four charts have the other manager winning: Likely; agreement 75%: High. DDF wins narrowly-ish.
    "likely": ([player(1, 60, 60, 60, 60, 60, 60)], [player(2, 90, 60, 50, 50, 50, 70)], False),
    # A value missing in one chart leaves that chart out (no zero standing in).
    "chart-missing": ([player(1, 50, 50, 50, 50, None, 50)], [player(2, 70, 70, 70, 70, 70, 70)], False),
    # DDF value missing: no answer on line 1.
    "ddf-missing": ([player(1, None, 50, 50, 50, 50, 50)], [player(2, 70, 70, 70, 70, 70, 70)], False),
}

HARNESS = """
const T = require(process.argv[1]);
const input = JSON.parse(process.argv[2]);
const rows = T.compareTrade(input.give, input.receive, input.series).rows;
const h = T.tradeHeadlines(rows, "ddf_value", {chartKeys: input.charts, lowConfidence: input.low});
console.log(JSON.stringify({propose: {answer: h.propose.answer, confidence: h.propose.confidence},
  accept: {answer: h.accept.answer, confidence: h.accept.confidence}}));
"""


def run(trade_js: Path, case) -> dict:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is not installed")
    give, receive, low = case
    payload = json.dumps({"give": give, "receive": receive, "series": SERIES, "charts": CHARTS, "low": low})
    out = subprocess.run([node, "-e", HARNESS, str(trade_js), payload], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


LEVELS = ["Low", "Medium", "High"]


def level_for(share: float) -> str:
    return "High" if share >= 0.75 else "Medium" if share >= 0.6 else "Low"


def sign(net: float) -> int:
    return 0 if abs(net) < 0.05 else (1 if net > 0 else -1)   # 0.0 as shown points neither way


def expected(case) -> dict:
    """The rules, recomputed from the raw values (not from trade.js)."""
    give, receive, low = case

    def net(key):
        values = [p["values"][key] for p in give + receive]
        if any(v is None for v in values):
            return None
        return sum(p["values"][key] for p in receive) - sum(p["values"][key] for p in give)

    def traded(key):
        return sum(p["values"][key] for p in give + receive)

    ddf = net("ddf_value")
    thin = ddf is not None and (traded("ddf_value") <= 0 or abs(ddf) < 0.05 * traded("ddf_value"))
    result = {}
    # Line 1: agreement among the other complete series (espn + the four charts).
    if ddf is None:
        result["propose"] = {"answer": None, "confidence": None}
    else:
        others = [n for n in (net(k) for k in ["espn"] + CHARTS) if n is not None]
        answer = {1: "Yes", -1: "No", 0: "Even"}[sign(ddf)]
        agree = sum(1 for n in others if sign(n) == sign(ddf))
        level = "Medium" if not others else level_for(agree / len(others))
        if 0 < len(others) < 3 and LEVELS.index(level) > 1:
            level = "Medium"
        if low:
            level = LEVELS[max(0, LEVELS.index(level) - 1)]
        if thin:
            level = "Low"
        result["propose"] = {"answer": answer, "confidence": level}
    # Line 2: charts on which the other manager wins or breaks even (our net <= 0 as shown).
    nets = [n for n in (net(k) for k in CHARTS) if n is not None]
    if not nets:
        result["accept"] = {"answer": None, "confidence": None}
    else:
        yes = sum(1 for n in nets if sign(n) <= 0)
        no = len(nets) - yes
        share = yes / len(nets)
        answer = "Likely" if share >= 2 / 3 else "Unlikely" if share <= 1 / 3 else "Toss-up"
        same = yes if answer == "Likely" else no if answer == "Unlikely" else max(yes, no)
        level = level_for(same / len(nets))
        if len(nets) < 3 and LEVELS.index(level) > 1:
            level = "Medium"
        if thin:
            level = "Low"
        result["accept"] = {"answer": answer, "confidence": level}
    return result


# Hand-checked anchors so the recomputation above cannot drift with the build.
ANCHORS = {
    "unanimous": {"propose": ("Yes", "High"), "accept": ("Unlikely", "High")},
    "one-source": {"propose": ("Yes", "Medium"), "accept": ("Unlikely", "High")},
    "razor-thin": {"propose": ("Yes", "Low"), "accept": ("Unlikely", "Low")},
    "lose-unanimous": {"propose": ("No", "High"), "accept": ("Likely", "High")},
    "four-percent": {"propose": ("Yes", "Low"), "accept": ("Unlikely", "Low")},
    "two-charts": {"propose": ("Yes", "High"), "accept": ("Unlikely", "Medium")},
    "five-percent": {"propose": ("Yes", "High"), "accept": ("Unlikely", "High")},
    "likely": {"propose": ("Yes", "Low"), "accept": ("Likely", "High")},
    "ddf-missing": {"propose": (None, None), "accept": ("Unlikely", "High")},
}


def check(trade_js: Path) -> list[str]:
    errors = []
    for name, case in CASES.items():
        got = run(trade_js, case)
        want = expected(case)
        if got != want:
            errors.append(f"{name}: got {got}, expected {want}")
        if name in ANCHORS:
            anchor = {line: {"answer": a, "confidence": c} for line, (a, c) in ANCHORS[name].items()}
            if want != anchor:
                errors.append(f"{name}: recomputation {want} disagrees with the hand-checked anchor {anchor}")
    return errors


MUTATIONS = {
    "thin-margin rule dropped": ("if (thinFlag) { level = \"Low\"; reasons.push(\"the margin is under 5% of the value traded\"); }\n      propose",
                                 "propose"),
    "threshold at 3% instead of 5%": ("const THIN_MARGIN = 0.05;", "const THIN_MARGIN = 0.03;"),
    "low-confidence DDF ignored": ("if (ctx && ctx.lowConfidence) {", "if (false) {"),
    "other manager wins flipped": ("signOf(row.net) <= 0).length", "signOf(row.net) >= 0).length"),
    "High threshold lowered": ("share >= 0.75 ? \"High\"", "share >= 0.5 ? \"High\""),
    "few-sources cap removed": ("if (charts.length < 3) { level = capped(level, \"Medium\");", "if (false) { level = capped(level, \"Medium\");"),
}


class TradeHeadlinesTest(unittest.TestCase):
    def test_headlines(self):
        self.assertEqual(check(TRADE_JS), [])

    def test_checks_fail_on_broken_builds(self):
        source = TRADE_JS.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            for name, (old, new) in MUTATIONS.items():
                with self.subTest(mutation=name):
                    self.assertIn(old, source, f"mutation anchor for {name!r} is stale")
                    broken = Path(tmp) / f"trade_{abs(hash(name))}.js"
                    broken.write_text(source.replace(old, new, 1), encoding="utf-8")
                    self.assertNotEqual(check(broken), [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
