"""JEG-1108: verify projections data is still computed but does NOT affect the fit label.

Before JEG-1108, the tri-view rule (JEG-1081) let projections upgrade a force trade to natural.
After JEG-1108, the label depends only on construction + DDF Value total + their Trade chart average.
Projections are still computed (usProj) for informational display, but variant = label and qualifier = null.

Fixtures: THIN (short at RB) gives nRB0 for DEEP's dRB1+dRB2 at controlled DDF/proj/market values.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.test_v2_finder_import import FINDER_JS, call
from tests.test_v2_finder_balance import ALLOC, SHAPE

CH = ["usatoday", "fantasycalc", "fantasypros", "cbs"]
PK = "ddf_value_projections"


def p(key, pos, ddf, proj="same", market="same"):
    proj = ddf if proj == "same" else proj
    market = ddf if market == "same" else market
    values = {"ddf_value": ddf, "ddf_value_charts": ddf, PK: proj, "chart_avg": market}
    values.update({k: market for k in CH})
    if proj is not None:
        values.update({"espn": proj, "cbsros": proj, "razzball": proj})
    else:
        values.pop(PK)
    return {"player_key": key, "pos": pos, "name": key, "values": values}


def team(prefix, qb, rb, wr, te):
    rows = []
    for pos, vals in (("QB", qb), ("RB", rb), ("WR", wr), ("TE", te)):
        rows += [p(f"{prefix}{pos}{i}", pos, v) for i, v in enumerate(vals)]
    return rows


def pick(rows, *keys):
    return [r for r in rows if r["player_key"] in keys]


def fit(finder_js, mine, theirs, give, get, **kw):
    expected = call(finder_js, "expectedDepth", ALLOC, 12)
    ctx = {"shape": SHAPE, "weights": {"QB": 0.15, "RB": 0.15, "WR": 0.15, "TE": 0.15, "overall": 0.15}, "ourKey": "ddf_value",
           "marketKey": "chart_avg", "chartKeys": CH, "z": 1, "expected": expected}
    ctx.update(kw)
    return call(finder_js, "tradeFit", {"mine": {"roster": mine, "leaving": give, "arriving": get}, "theirs": {"roster": theirs, "leaving": get, "arriving": give}}, ctx)


THIN = team("n", [20, 12], [30], [20, 18, 10, 8], [6])
DEEP = team("d", [20, 14], [35, 16, 16, 12, 9, 7, 6], [25, 22, 21, 9, 5], [11, 6])


def scenario(finder_js, ddf, proj, market="same", **kw):
    """THIN gives nRB0 (30 everywhere) for dRB1+dRB2 priced (ddf, proj, market) in the three views."""
    deep = [p(r["player_key"], r["pos"], *(ddf, proj, ddf if market == "same" else market)) if r["player_key"] in ("dRB1", "dRB2") else r for r in DEEP]
    return fit(finder_js, THIN, deep, pick(THIN, "nRB0"), pick(deep, "dRB1", "dRB2"), **kw)


def check(finder_js: Path) -> list[str]:
    errors = []
    say = errors.append

    # 1. Agreeing views (ddf=16, proj=16): natural (all conditions pass).
    f = scenario(finder_js, 16, 16)
    if f["label"] != "natural":
        say(f"agreeing views should be natural: {f['label']}")
    if f["variant"] != f["label"]:
        say(f"variant should equal label: variant={f['variant']} label={f['label']}")
    if f["qualifier"] is not None:
        say(f"qualifier should be null: {f['qualifier']}")
    # usProj still computed when projections available.
    if f["usProj"] is None or not f["usProj"]["ok"]:
        say(f"usProj should be computed and ok when projections agree: {f.get('usProj')}")

    # 2. DDF Value serves you (16) but projections (2) do not: label depends on DDF, not projections.
    # With ddf=16 and market=16, yourTotalUp depends on us.tau which is large because DDF charts and
    # projections disagree (noise). yourTotalUp may be false, making this market (not natural).
    f = scenario(finder_js, 16, 2, market=16)
    # The label should NOT be "value" (retired).
    if f["label"] == "value":
        say(f"value label is retired: got {f['label']}")
    if f["variant"] != f["label"]:
        say(f"variant should equal label (charts-only): {f['variant']} vs {f['label']}")
    if f["qualifier"] is not None:
        say(f"qualifier should be null (no qualifier system): {f['qualifier']}")
    # usProj computed, shows projections don't serve you.
    if f["usProj"] is None:
        say("usProj should be computed even when projections disagree")

    # 3. DDF Value says lose (5), projections and market say gain (16): no tri-view escalation.
    # Under old rules, projections would upgrade this to natural-projections. Now: label is market
    # (yourTotalUp=false but marketSupported=true since theirNet is positive).
    f = scenario(finder_js, 5, 16, market=16)
    if f["label"] == "natural":
        say(f"DDF loss should not be natural just because projections say gain: {f['label']}")
    if f["label"] == "value":
        say(f"value label is retired: got {f['label']}")
    # Under two-view rule (projections key = DDF value): same result since projections don't affect label.
    f2 = scenario(finder_js, 5, 16, market=16, projectionsKey="ddf_value")
    if f2["label"] != f["label"]:
        say(f"projectionsKey should not change label: {f2['label']} vs {f['label']}")

    # 4. Missing projections: usProj is null, label unchanged.
    f = scenario(finder_js, 16, None, market=16)
    if f["projected"]:
        say("should not be projected when projections missing")
    if f["usProj"] is not None:
        say(f"usProj should be null when not projected: {f['usProj']}")
    if f["label"] != "natural":
        say(f"missing projections with ddf=16: should be natural: {f['label']}")

    # 5. Neither DDF view serves you (5,5) but market does (16): market supported.
    f = scenario(finder_js, 5, 5, market=16)
    if f["label"] == "value":
        say(f"value label is retired: got {f['label']}")
    # theirNet is positive (they gain from giving market-16 players, receiving market-30 nRB0): market supported.
    if f.get("marketSupported") and f["label"] != "market":
        say(f"should be market when marketSupported: {f['label']}")

    # 6. Them: the market says they lose => not natural.
    thin = [p("nRB0", "RB", 30, market=2) if r["player_key"] == "nRB0" else r for r in THIN]
    deep = [p(r["player_key"], r["pos"], 16, 16, 16) if r["player_key"] in ("dRB1", "dRB2") else r for r in DEEP]
    f = fit(finder_js, thin, deep, pick(thin, "nRB0"), pick(deep, "dRB1", "dRB2"))
    # They give market 16+16=32, receive market 2 => theirNet = 2-32 = -30. Way outside noise.
    if f["label"] == "natural":
        say(f"their market loss should prevent natural: {f['label']} them net {f['them']['net']}")

    # 7. Text: natural starts with "Natural fit:", no qualifier parenthetical.
    text = call(finder_js, "fitText", scenario(finder_js, 16, 16))
    if not text.startswith("Natural fit:"):
        say(f"natural text: {text!r}")
    if "(" in text.split(":")[0]:
        say(f"natural text should not have qualifier: {text!r}")

    return errors


# Guard mutants are tested in test_v2_finder_fit.py (7 mutants covering all new guards).
# This file focuses on verifying projections data is computed but labels are independent of it.


class TriViewFitTests(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(check(FINDER_JS), [])


if __name__ == "__main__":
    unittest.main()
