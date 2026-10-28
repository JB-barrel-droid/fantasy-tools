"""v2 Compare a trade headline (JEG-505, JEG-821, JEG-841, contract CT-02).

Two answers with a three-step level (High / Medium / Low inside trade.js; the page names it
"Our value: strong / moderate / weak" and "Charts agree: strongly / mostly / weakly", JEG-895):

    "Should you propose or accept?"  by DDF Value (JEG-841):
        Yes  when both say you win and the DDF margin is 5%+ of the value traded;
        No   when both say you lose and the DDF margin is 5%+;
        Unclear otherwise (they split, margin under 5%, or projections unavailable).
        Confidence (JEG-950, Jeremy 2026-10-23): the level also depends on how many trade charts are on the
        answer's side: 3 or more keep it, 2 cap it at Medium, 0 or 1 cap it at Low (Jeremy 2026-10-23, 2026-10-25).
        Confidence: High when projections margin also 5%+, Medium when projections
        agree but margin < 5%, Low when projections even/missing or low-confidence DDF.
        The chart agreement count stays in the reasons for honesty ("0 of N agree").

    "Will they accept?"  from the published charts (unchanged):
        Likely / Unlikely / Toss-up from the share of charts where the other
        manager wins or breaks even.

Discrimination: test_checks_fail_on_broken_builds runs the same cases against
mutated copies of trade.js and requires each to fail.

JEG-841 regression fixtures: four trades from the product review:
  - Skattebo + Kincaid for Evans (arbitrage: DDF win, charts lose, projections win)
  - Skattebo + Kincaid for Egbuka (same pattern)
  - Likely + Skattebo for G. Wilson (same pattern)
  - Jacobs + Montgomery for Chase Brown (DDF win, 1 chart agrees)
  - N13 all-agree-win (every source agrees you win -> propose Yes, accept Unlikely)
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
SERIES = ["ddf_value", "ddf_value_projections", "espn"] + CHARTS


def player(key, ddf, proj, espn, usat, fc, fp, cbs):
    return {"player_key": key, "name": f"P{key}",
            "values": {"ddf_value": ddf, "ddf_value_projections": proj, "espn": espn,
                       "usatoday": usat, "fantasycalc": fc, "fantasypros": fp, "cbs": cbs}}


# name -> (give players, receive players, low_confidence)
CASES = {
    # DDF win +20 of 120 (17%), projections also win +20: Yes, High. Charts all lose -> Unlikely, High.
    "unanimous": ([player(1, 50, 50, 50, 50, 50, 50, 50)], [player(2, 70, 70, 70, 70, 70, 70, 70)], False),
    # DDF win; projections win; two charts say you lose, two win; ESPN wins.
    "split": ([player(1, 50, 50, 50, 50, 50, 50, 50)], [player(2, 62, 62, 60, 40, 45, 70, 70)], False),
    # Same as unanimous, but a one-source DDF Value: High -> Medium.
    "one-source": ([player(1, 50, 50, 50, 50, 50, 50, 50)], [player(2, 70, 70, 70, 70, 70, 70, 70)], True),
    # DDF net 2 of 100 (2%, thin): Unclear even though projections agree.
    "razor-thin": ([player(1, 49, 49, 49, 49, 49, 49, 49)], [player(2, 51, 51, 51, 51, 51, 51, 51)], False),
    # JEG-876: the same thin margin on the losing side: Unclear, not No (the lose branch has its own thin gate).
    "razor-thin-lose": ([player(1, 51, 51, 51, 51, 51, 51, 51)], [player(2, 49, 49, 49, 49, 49, 49, 49)], False),
    # DDF lose -20; projections lose -20: No, High. Charts say you win: Likely, High.
    "lose-unanimous": ([player(1, 70, 70, 70, 70, 70, 70, 70)], [player(2, 50, 50, 50, 50, 50, 50, 50)], False),
    # 5% of 100 is not "under 5%": thin rule does not fire.
    "five-percent": ([player(1, 47.5, 47.5, 47.5, 47.5, 47.5, 47.5, 47.5)], [player(2, 52.5, 52.5, 52.5, 52.5, 52.5, 52.5, 52.5)], False),
    # 4% is under 5%: Unclear.
    "four-percent": ([player(1, 48, 48, 48, 48, 48, 48, 48)], [player(2, 52, 52, 52, 52, 52, 52, 52)], False),
    # Only two charts price the trade: headline from DDF+proj; accept capped at Medium (< 3 charts).
    "two-charts": ([player(1, 50, 50, 50, 50, 50, None, None)], [player(2, 70, 70, 70, 70, 70, 70, 70)], False),
    # DDF win, projections win but chart rows mixed -> propose Yes (from DDF+proj), accept Likely.
    "likely": ([player(1, 60, 60, 60, 60, 60, 60, 60)], [player(2, 90, 90, 60, 50, 50, 50, 70)], False),
    # A value missing in one chart leaves that chart out.
    "chart-missing": ([player(1, 50, 50, 50, 50, 50, None, 50)], [player(2, 70, 70, 70, 70, 70, 70, 70)], False),
    # DDF value missing: no answer on line 1.
    "ddf-missing": ([player(1, None, 50, 50, 50, 50, 50, 50)], [player(2, 70, 70, 70, 70, 70, 70, 70)], False),
    # JEG-841: DDF win, projections win, all charts lose -> Yes (arbitrage), accept Likely.
    "arbitrage": ([player(1, 50, 50, 70, 70, 70, 70, 70)], [player(2, 70, 70, 50, 50, 50, 50, 50)], False),
    # JEG-841: DDF win, projections lose -> Unclear (they split).
    "ddf-proj-split": ([player(1, 50, 70, 50, 50, 50, 50, 50)], [player(2, 70, 50, 70, 70, 70, 70, 70)], False),
    # JEG-841: DDF win, projections missing -> Unclear.
    "proj-missing": ([player(1, 50, None, 50, 50, 50, 50, 50)], [player(2, 70, None, 70, 70, 70, 70, 70)], False),
    # JEG-841: DDF even, projections even, thin -> Unclear.
    "even-no-support": ([player(1, 50, 50, 60, 60, 60, 60, 60)], [player(2, 50, 50, 40, 40, 40, 40, 40)], False),
    # JEG-821 legacy: DDF win +2 of 100 (thin), 0 charts agree -> Unclear.
    "zero-agree-thin": ([player(1, 49, 49, 52, 52, 52, 52, 52)], [player(2, 51, 51, 48, 48, 48, 48, 48)], False),
    # JEG-841: DDF win wide, projections win wide, 0 charts agree -> Yes (the arbitrage fix!).
    "zero-agree-wide": ([player(1, 50, 50, 70, 70, 70, 70, 70)], [player(2, 70, 70, 50, 50, 50, 50, 50)], False),
    # JEG-950: exactly 3 of 4 charts agree keeps High; 2 of 4 drops to Medium (the other line is unchanged).
    "three-of-four": ([player(1, 50, 50, 50, 50, 50, 50, 50)], [player(2, 70, 70, 70, 70, 70, 70, 40)], False),
    "two-of-four": ([player(1, 50, 50, 50, 50, 50, 50, 50)], [player(2, 70, 70, 70, 70, 70, 40, 40)], False),
    "one-of-four": ([player(1, 50, 50, 50, 50, 50, 50, 50)], [player(2, 70, 70, 70, 70, 40, 40, 40)], False),
    "lose-one-of-four": ([player(1, 70, 70, 70, 70, 70, 70, 70)], [player(2, 50, 50, 50, 50, 80, 80, 80)], False),
    "lose-three-of-four": ([player(1, 70, 70, 70, 70, 70, 70, 70)], [player(2, 50, 50, 50, 50, 50, 50, 80)], False),
    "lose-two-of-four": ([player(1, 70, 70, 70, 70, 70, 70, 70)], [player(2, 50, 50, 50, 50, 50, 80, 80)], False),
    # N13: every source agrees you win -> propose Yes, accept Unlikely (consistent, no contradiction).
    "all-agree-win": ([player(1, 50, 50, 50, 50, 50, 50, 50)], [player(2, 70, 70, 70, 70, 70, 70, 70)], False),
}

HARNESS = """
const T = require(process.argv[1]);
const input = JSON.parse(process.argv[2]);
const rows = T.compareTrade(input.give, input.receive, input.series).rows;
const deal = T.dealRead(input.give, input.receive, input.charts);
const h = T.tradeHeadlines(rows, "ddf_value", {chartKeys: input.charts, lowConfidence: input.low, deal: deal});
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
    return 0 if abs(net) < 0.05 else (1 if net > 0 else -1)


def expected(case, charts=CHARTS) -> dict:
    """The rules recomputed from the raw values (not from trade.js).

    `charts` are the published chart series compared on the page (the render test passes the
    page's own list, which can be shorter than CHARTS when a chart is held)."""
    give, receive, low = case
    CHARTS = list(charts)  # noqa: N806

    def net(key):
        values = [p["values"].get(key) for p in give + receive]
        if any(v is None for v in values):
            return None
        return sum(p["values"][key] for p in receive) - sum(p["values"][key] for p in give)

    def traded(key):
        vals = [p["values"].get(key) for p in give + receive]
        if any(v is None for v in vals):
            return None
        return sum(v for v in vals)

    ddf = net("ddf_value")
    proj = net("ddf_value_projections")
    ddf_traded = traded("ddf_value")
    proj_traded = traded("ddf_value_projections")
    thin = ddf is not None and ddf_traded is not None and (ddf_traded <= 0 or abs(ddf) < 0.05 * ddf_traded)
    result = {}

    # Line 1: JEG-841 — decided by DDF Value.
    if ddf is None:
        result["propose"] = {"answer": None, "confidence": None}
    else:
        # Deal-read side logic: same threshold as sideOf in trade.js
        def side_of(n, give_sum, receive_sum):
            threshold = max(1, 0.03 * ((give_sum + receive_sum) / 2))
            return "win" if n >= threshold else "lose" if n <= -threshold else "even"

        ddf_give = sum(p["values"]["ddf_value"] for p in give if p["values"]["ddf_value"] is not None)
        ddf_receive = sum(p["values"]["ddf_value"] for p in receive if p["values"]["ddf_value"] is not None)
        v_side = side_of(ddf, ddf_give, ddf_receive)

        if proj is not None:
            proj_give = sum(p["values"]["ddf_value_projections"] for p in give if p["values"]["ddf_value_projections"] is not None)
            proj_receive = sum(p["values"]["ddf_value_projections"] for p in receive if p["values"]["ddf_value_projections"] is not None)
            p_side = side_of(proj, proj_give, proj_receive)
            p_margin = abs(proj) / (proj_give + proj_receive) if (proj_give + proj_receive) > 0 else None
        else:
            p_side = None
            p_margin = None

        # Need a complete deal read (market must have >= 3 charts).
        chart_nets = [net(k) for k in CHARTS]
        complete_charts = [n for n in chart_nets if n is not None]
        has_deal = len(complete_charts) >= 3

        if not has_deal:
            answer = "Unclear"
            level = "Low"
        elif v_side == "win" and p_side == "win" and not thin:
            answer = "Yes"
            level = "High" if p_margin is not None and p_margin >= 0.05 else "Medium"
        elif v_side == "lose" and p_side == "lose" and not thin:
            answer = "No"
            level = "High" if p_margin is not None and p_margin >= 0.05 else "Medium"
        else:
            answer = "Unclear"
            level = "Low"

        if low:
            level = LEVELS[max(0, LEVELS.index(level) - 1)]

        if answer in ("Yes", "No"):
            want_sign = 1 if answer == "Yes" else -1
            agreeing = sum(1 for n in complete_charts if sign(n) == want_sign)
            # JEG-950 (Jeremy 2026-10-25): 3+ keep the level, 2 cap at Medium, 0 or 1 cap at Low.
            cap = "High" if agreeing >= 3 else "Medium" if agreeing == 2 else "Low"
            level = LEVELS[min(LEVELS.index(level), LEVELS.index(cap))]

        result["propose"] = {"answer": answer, "confidence": level}

    # Line 2: charts on which the other manager wins or breaks even (unchanged).
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


# Hand-checked anchors.
ANCHORS = {
    "unanimous": {"propose": ("Yes", "High"), "accept": ("Unlikely", "High")},
    "one-source": {"propose": ("Yes", "Medium"), "accept": ("Unlikely", "High")},
    "razor-thin": {"propose": ("Unclear", "Low"), "accept": ("Unlikely", "Low")},
    # JEG-876: lose by 2 of 100 on every series: thin, so Unclear; the charts all have them winning -> Likely, Low.
    "razor-thin-lose": {"propose": ("Unclear", "Low"), "accept": ("Likely", "Low")},
    "lose-unanimous": {"propose": ("No", "High"), "accept": ("Likely", "High")},
    "four-percent": {"propose": ("Unclear", "Low"), "accept": ("Unlikely", "Low")},
    # JEG-841: only 2 charts, deal read incomplete -> propose Unclear (needs 3 charts for market read).
    "two-charts": {"propose": ("Unclear", "Low"), "accept": ("Unlikely", "Medium")},
    "five-percent": {"propose": ("Yes", "High"), "accept": ("Unlikely", "High")},
    "likely": {"propose": ("Yes", "Low"), "accept": ("Likely", "High")},
    "ddf-missing": {"propose": (None, None), "accept": ("Unlikely", "High")},
    # JEG-841: the arbitrage fix — DDF win + proj win + all charts lose -> Yes, not Unclear.
    "arbitrage": {"propose": ("Yes", "Low"), "accept": ("Likely", "High")},
    "zero-agree-wide": {"propose": ("Yes", "Low"), "accept": ("Likely", "High")},
    # DDF win + proj lose -> Unclear.
    "ddf-proj-split": {"propose": ("Unclear", "Low"), "accept": ("Unlikely", "High")},
    # Projections missing -> Unclear.
    "proj-missing": {"propose": ("Unclear", "Low"), "accept": ("Unlikely", "High")},
    # Thin margin -> Unclear even when projections agree.
    "zero-agree-thin": {"propose": ("Unclear", "Low"), "accept": ("Likely", "Low")},
    # Even sides -> Unclear.
    "even-no-support": {"propose": ("Unclear", "Low"), "accept": ("Likely", "Low")},
    # N13: every source agrees -> Yes (not contradictory with Unlikely accept).
    "all-agree-win": {"propose": ("Yes", "High"), "accept": ("Unlikely", "High")},
    # JEG-950: three-of-four has one chart (cbs) against; two-of-four has two against.
    "three-of-four": {"propose": ("Yes", "High"), "accept": ("Unlikely", "High")},
    "two-of-four": {"propose": ("Yes", "Medium"), "accept": ("Toss-up", "Low")},
    "lose-two-of-four": {"propose": ("No", "Medium"), "accept": ("Toss-up", "Low")},
    "one-of-four": {"propose": ("Yes", "Low"), "accept": ("Likely", "High")},
    "lose-one-of-four": {"propose": ("No", "Low"), "accept": ("Unlikely", "High")},
    "lose-three-of-four": {"propose": ("No", "High"), "accept": ("Likely", "High")},
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
    # JEG-841: removing the deal-based propose must be caught (arbitrage case would break).
    "deal-based propose removed": (
        "const deal = ctx && ctx.deal;",
        "const deal = null;"
    ),
    # Dropping the thin-margin gate on propose (the Yes branch) must be caught.
    "thin propose dropped": (
        "if (vSide === \"win\" && pSide === \"win\" && !thinFlag) {",
        "if (vSide === \"win\" && pSide === \"win\") {"
    ),
    # JEG-876: dropping the thin gate on the No branch is caught by razor-thin-lose.
    "thin gate dropped on No": (
        "} else if (vSide === \"lose\" && pSide === \"lose\" && !thinFlag) {",
        "} else if (vSide === \"lose\" && pSide === \"lose\") {"
    ),
    # JEG-876: moving the thin threshold is caught by four-percent (4% is under 5%, not under 3%).
    "threshold at 3% instead of 5%": ("const THIN_MARGIN = 0.05;", "const THIN_MARGIN = 0.03;"),
    # Low-confidence DDF ignored.
    "low-confidence DDF ignored": (
        "if (ctx && ctx.lowConfidence) { level = lowered(level); reasons.push(\"a one-source DDF Value is in this trade\"); }",
        ""
    ),
    # Other manager wins flipped on accept line.
    "other manager wins flipped": ("signOf(row.net) <= 0).length", "signOf(row.net) >= 0).length"),
    # High threshold lowered on accept.
    "High threshold lowered": ("share >= 0.75 ? \"High\"", "share >= 0.5 ? \"High\""),
    # JEG-950: the 3-chart requirement for High removed or loosened must be caught.
    "chart requirement removed": ("if (answer === \"Yes\" || answer === \"No\") {\n        if (chartAgree", "if (false) {\n        if (chartAgree"),
    "chart requirement loosened to 2": ("const MIN_CHARTS_FOR_HIGH = 3;", "const MIN_CHARTS_FOR_HIGH = 2;"),
    "one chart only caps at Medium": ('level = capped(level, "Low");\n        else if', 'level = capped(level, "Medium");\n        else if'),
    "two charts not capped": ('else if (chartAgree < MIN_CHARTS_FOR_HIGH) level = capped(level, "Medium");', ""),
    # Few-sources cap removed on accept.
    "few-sources cap removed": (
        "if (charts.length < 3) { level = capped(level, \"Medium\");",
        "if (false) { level = capped(level, \"Medium\");"
    ),
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
