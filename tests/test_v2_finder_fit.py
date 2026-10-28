"""v2 Find a trade: fit labels rewrite (JEG-1108).

Natural fit = roster construction works for both teams (after the trade: no bench player promoted to starter, no starter
lost without a starter coming back, no empty starting slot) AND your DDF Value total roster value (starters plus bench at
bench weight) rises with starters not worse AND the other team's Trade chart average change is within the noise floor or positive.

Market supported = the Trade chart average says the other team's side is favorable: their change is above 0.05, the
smallest change the page shows (JEG-1187; not the noise floor). Independent of the roster test.

Force fit = everything else. Value fit is RETIRED.

Discrimination: test_checks_fail_on_broken_builds runs the same checks on mutated copies of finder.js.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.test_v2_finder_import import FINDER_JS, call
from tests.test_v2_finder_balance import ALLOC, SHAPE

CH = ["usatoday", "fantasycalc", "fantasypros", "cbs"]


def p(key, pos, ddf, market=None, noise=0.0):
    market = ddf if market is None else market
    values = {"ddf_value": ddf, "chart_avg": market, "ddf_value_charts": ddf - noise, "ddf_value_projections": ddf + noise}
    for i, k in enumerate(CH):
        values[k] = market + (noise if i % 2 else -noise)
    return {"player_key": key, "pos": pos, "name": key, "values": values}


def team(prefix, qb, rb, wr, te):
    rows = []
    for pos, vals in (("QB", qb), ("RB", rb), ("WR", wr), ("TE", te)):
        rows += [p(f"{prefix}{pos}{i}", pos, v) for i, v in enumerate(vals)]
    return rows


def pick(rows, *keys):
    return [r for r in rows if r["player_key"] in keys]


def ctx(**kw):
    out = {"shape": SHAPE, "weights": {"QB": 0.15, "RB": 0.15, "WR": 0.15, "TE": 0.15, "overall": 0.15}, "ourKey": "ddf_value", "marketKey": "chart_avg",
           "chartKeys": CH, "z": 1}
    out.update(kw)
    return out


def fit(finder_js, mine, theirs, give, get, **kw):
    expected = call(finder_js, "expectedDepth", ALLOC, 12)
    return call(finder_js, "tradeFit", {"mine": {"roster": mine, "leaving": give, "arriving": get}, "theirs": {"roster": theirs, "leaving": get, "arriving": give}},
                ctx(expected=expected, **kw))


# A: deep at WR (8, over), short at RB (3, under). B: the reverse.
A = team("a", [20, 12], [30, 25, 10], [30, 28, 15, 9, 8, 7, 6, 5], [10, 5])
B = team("b", [22, 11], [35, 28, 14, 12, 9, 8, 5], [26, 20, 9], [11, 6])


def check(finder_js: Path) -> list[str]:
    errors = []
    say = errors.append

    # 1. A starter-for-starter swap where both teams gain and construction is OK: natural.
    # A gives low-value WR6 (6), receives a better RB from B (RB5=8). Both gain total, starters not worse,
    # construction OK (WR6 is bench, incoming RB5 replaces on bench; no promotion).
    # Need to construct a cleaner trade: give my bench WR for their bench RB, both gain total.
    mine1 = team("m1", [20, 12], [30, 25, 10, 8, 5], [30, 28, 15, 9, 7, 6], [10, 5])
    theirs1 = team("t1", [22, 11], [35, 28, 14, 12, 9, 8, 5], [26, 20, 9], [11, 6])
    # Give my WR5 (7) which is bench; receive their RB6 (5) which is bench. Both bench swaps.
    # My total: lose 7 WR bench, gain 5 RB bench = -2 net => not natural (total must rise).
    # Better: give bench WR worth 6, receive a higher bench RB worth 12.
    f = fit(finder_js, mine1, theirs1, pick(mine1, "m1WR5"), pick(theirs1, "t1RB3"))
    # My net: lose 6, gain 12 = gain. Their net on chart_avg: lose 12, gain 6 = lose (force for me).
    # Actually for natural, their side must be within noise or positive.
    # Let's use a trade where both sides gain in their views.
    x = p("myGive", "WR", 10, market=25)   # I value low, market values high
    y = p("theirGive", "RB", 25, market=10)  # I value high, market values low
    mine_n = team("mn", [20, 12], [30, 25, 10, 8, 5], [30, 28, 15, 9, 7], [10, 5]) + [x]
    theirs_n = team("tn", [22, 11], [35, 28, 14, 12, 9], [26, 20, 9, 8, 7], [11, 6]) + [y]
    f = fit(finder_js, mine_n, theirs_n, [x], [y])
    # My DDF total rises: give 10 ddf, receive 25 ddf = +15 net.
    # Their chart_avg: give 10 market, receive 25 market = +15 net for them.
    # Construction: both sides are swapping bench players, no starter changes.
    if f["label"] != "natural":
        say(f"bench swap both gain: label={f['label']}, expected natural. us net={f['us']['net']}, them net={f['them']['net']}, constructionOk={f.get('constructionOk')}")
    if not f.get("constructionOk"):
        say(f"bench swap construction should be OK: myConstruction={f.get('myConstruction')}, theirConstruction={f.get('theirConstruction')}")
    text = call(finder_js, "fitText", f)
    if not text.startswith("Natural fit:"):
        say(f"natural text should start with 'Natural fit:': {text!r}")

    # 2. Market supported: chart avg favors them, but our total does not rise (or construction fails).
    # Give my starter for a lower-value player: their charts say they win.
    ms = team("ms", [20, 12], [30, 25, 10, 8, 5], [30, 28, 15, 9, 7], [10, 5])
    ts = team("ts", [22, 11], [35, 28, 14, 12, 9], [26, 20, 9, 8, 7], [11, 6])
    give2 = [p("msGive", "RB", 5, market=30)]  # I value low, they value high
    recv2 = [p("tsGive", "RB", 3, market=35)]   # I value lower, they value higher
    ms2 = ms + give2
    ts2 = ts + recv2
    f = fit(finder_js, ms2, ts2, give2, recv2)
    # My DDF: give 5, receive 3 = -2 (total drops, not natural).
    # Their charts: give 35, receive 30 = -5 for them? No wait: they give tsGive (market=35), receive msGive (market=30).
    # That's -5 for them. Not favorable.
    # Let me fix: my side gives something they value high, gets something they value low.
    give2b = [p("msG", "WR", 5, market=40)]
    recv2b = [p("tsG", "WR", 3, market=10)]
    ms2b = ms + give2b
    ts2b = ts + recv2b
    f = fit(finder_js, ms2b, ts2b, give2b, recv2b)
    # Their charts: they give tsG (market=10), they receive msG (market=40) => net +30 for them. Market supported.
    # My DDF: give 5, receive 3 => net -2. Total drops. Not natural.
    if f["label"] != "market":
        say(f"market supported trade: label={f['label']}, expected market. us net={f['us']['net']}, them net={f['them']['net']}, marketSupported={f.get('marketSupported')}")
    text = call(finder_js, "fitText", f)
    if not text.startswith("Market supported:"):
        say(f"market text should start with 'Market supported:': {text!r}")

    # 3. Force fit: total drops and charts don't favor them.
    give3 = [p("fg", "WR", 20, market=10)]   # I value high, market values low
    recv3 = [p("fr", "WR", 5, market=3)]     # Both value low
    ms3 = ms + give3
    ts3 = ts + recv3
    f = fit(finder_js, ms3, ts3, give3, recv3)
    # My DDF: give 20, receive 5 = -15. Total drops.
    # Their charts: they give 3, receive 10 = +7 for them. So they gain... that would be market supported.
    # I need them to lose too.
    give3b = [p("fg2", "WR", 20, market=5)]
    recv3b = [p("fr2", "WR", 5, market=20)]
    ms3b = ms + give3b
    ts3b = ts + recv3b
    f = fit(finder_js, ms3b, ts3b, give3b, recv3b)
    # My DDF: give 20, receive 5 = -15. Total drops.
    # Their charts: they give 20 market, receive 5 market = -15 for them. They lose.
    if f["label"] != "force":
        say(f"force trade: label={f['label']}, expected force. us net={f['us']['net']}, them net={f['them']['net']}")
    text = call(finder_js, "fitText", f)
    if not text.startswith("Force fit:"):
        say(f"force text should start with 'Force fit:': {text!r}")

    # 4. Value fit is retired: no trade should produce "value" label.
    bal_a = team("a", [20, 12], [30, 15, 12, 9, 7], [30, 28, 15, 9, 8, 7], [10, 5])
    bal_b = team("b", [22, 11], [35, 14, 12, 9, 8], [26, 20, 9, 8, 7, 6], [11, 6])
    x4 = p("aX", "RB", 25, market=40)
    y4 = p("bY", "RB", 30, market=20)
    f = fit(finder_js, bal_a + [x4], bal_b + [y4], [x4], [y4])
    if f["label"] == "value":
        say(f"value label should be retired but got: {f['label']}")

    # 5. Construction check: bench player promoted to starter = construction fails.
    # Give my RB starter, receive a WR bench player. My RB bench must promote to starter.
    mine5 = team("c5", [20], [30, 8], [20, 15, 10, 8], [10])  # RB0=30 is starter, RB1=8 is bench
    theirs5 = team("t5", [22], [25, 12, 10], [18, 15, 10], [11])
    f = fit(finder_js, mine5, theirs5, pick(mine5, "c5RB0"), pick(theirs5, "t5WR2"))
    # Give my RB starter (30), receive their WR bench (10). My RB1 (8) must start now.
    # Construction: bench promoted to starter = fails.
    if f.get("constructionOk") is not False and f.get("myConstruction", {}).get("ok") is not False:
        say(f"construction should fail for bench promotion: constructionOk={f.get('constructionOk')}, myConstruction={f.get('myConstruction')}")

    # 6. Roster construction: empty starting slot after trade.
    mine6 = team("c6", [20], [30], [20, 15], [10])
    theirs6 = team("t6", [22], [25, 12, 10], [18, 15, 10], [11])
    # Give the only RB; the slot is now empty.
    f = fit(finder_js, mine6, theirs6, pick(mine6, "c6RB0"), pick(theirs6, "t6WR2"))
    if f.get("constructionOk") is not False:
        say(f"construction should fail for empty slot: constructionOk={f.get('constructionOk')}")

    # 7. tierOrder: natural, market, force; stable; nothing lost.
    out = call(finder_js, "tierOrder", ["force", "natural", "market", "natural", None, "force"])
    if out != [1, 3, 2, 0, 5, 4]:
        say(f"tierOrder {out}, want [1, 3, 2, 0, 5, 4]")

    # 8. Trade where total drops (bench players lost): not natural.
    mine8 = team("m8", [20, 12], [15, 12, 10, 8], [25, 20, 15, 10, 8], [10, 5])
    theirs8 = team("t8", [22, 11], [35, 30, 28, 14, 12, 9], [26, 20, 9, 8, 7], [11, 6])
    g8 = [p("m8g", "WR", 8, market=4)]
    r8 = [p("t8g", "WR", 3, market=30)]
    f = fit(finder_js, mine8 + g8, theirs8 + r8, g8, r8)
    if f["label"] == "natural":
        say(f"should not be natural when total drops: label={f['label']} net={f['us']['net']}")

    # 9. Starter drop: construction OK, total rises, but starters fall => not natural.
    # Stacked roster with one QB so no QB bench player can promote. Give QB (ddf=30), receive a
    # worse QB (ddf=22) + 3 bench RBs (ddf=20 each). The QB downgrade (starterDelta=-8) is offset
    # by bench gain (60*0.15=9 => net=+1), but starters are worse. Market values balanced so their
    # side is neutral. Construction passes: arriving QB replaces departing QB; 3 RBs stay bench.
    mine9_qb = p("m9QB0", "QB", 30, market=20)
    mine9 = [mine9_qb] + [p(f"m9RB{i}", "RB", v) for i, v in enumerate([40, 35, 30, 25, 20])] \
        + [p(f"m9WR{i}", "WR", v) for i, v in enumerate([45, 40, 35, 30, 25, 20])] \
        + [p(f"m9TE{i}", "TE", v) for i, v in enumerate([15, 10])]
    recv_qb = p("t9rQB", "QB", 22, market=20)
    recv_rbs = [p(f"t9rRB{i}", "RB", 20, market=0.01) for i in range(3)]
    theirs9 = team("t9", [28], [38, 33, 28, 23, 18], [43, 38, 33, 28], [13, 8]) \
        + [recv_qb] + recv_rbs
    g9 = [mine9_qb]
    r9 = [recv_qb] + recv_rbs
    f = fit(finder_js, mine9, theirs9, g9, r9)
    if f["label"] == "natural":
        say(f"starter drop should not be natural: starterDelta={f['us']['starterDelta']}")
    if f.get("constructionOk") is not True:
        say(f"test 9 construction should be OK: {f.get('myConstruction')}, {f.get('theirConstruction')}")
    if f["us"]["net"] <= 0.05:
        say(f"test 9 total should rise: net={f['us']['net']}")
    if f["us"]["starterDelta"] >= -0.05:
        say(f"test 9 starters should drop: starterDelta={f['us']['starterDelta']}")

    # 10. Their loss outside noise floor: other team loses more than noise => not natural even if our value rises.
    # Bench-for-bench WR swap on deep rosters so construction passes on both sides.
    # m10g: low DDF, low market (bench both sides). t10g: low DDF, high market (bench both sides).
    # My DDF: gain 3 bench = +0.45 net. Their market: give 22, receive 2 = -20 (lose).
    mine10 = team("m10", [20, 12], [30, 25, 10, 8, 5], [30, 28, 15, 9, 7], [10, 5])
    theirs10 = team("t10", [22, 11], [35, 28, 25, 20, 15], [40, 35, 30, 25, 20], [11, 6])
    g10 = [p("m10g", "WR", 5, market=2)]
    r10 = [p("t10g", "WR", 8, market=22)]
    f = fit(finder_js, mine10 + g10, theirs10 + r10, g10, r10)
    # Their charts: give 22, receive 2 = -20. Well outside noise. Not natural.
    if f["label"] == "natural":
        say(f"their loss outside noise should not be natural: label={f['label']} them net={f['them']['net']}")
    if f.get("constructionOk") is not True:
        say(f"test 10 construction should be OK: my={f.get('myConstruction')}, their={f.get('theirConstruction')}")

    # 11. Noise-scaled tau: high chart disagreement makes tau large, allowing a small their-side loss.
    # Players have high chart noise (±10) but zero DDF noise, so my tau stays small.
    # Their market loss of -4 is within noise-scaled tau (~8) but outside NET_FLOOR (0.05).
    # Without noise scaling: not natural (theirOk fails). With noise: natural.
    def noisy_p(key, pos, ddf, market, chart_noise):
        values = {"ddf_value": ddf, "chart_avg": market, "ddf_value_charts": ddf, "ddf_value_projections": ddf}
        for i, k in enumerate(CH):
            values[k] = market + (chart_noise if i % 2 else -chart_noise)
        return {"player_key": key, "pos": pos, "name": key, "values": values}
    mine11 = team("m11", [20, 12], [30, 25, 10, 8, 5], [30, 28, 15, 9, 7], [10, 5])
    theirs11 = team("t11", [22, 11], [35, 28, 25, 20, 15], [40, 35, 30, 25, 20], [11, 6])
    g11 = [noisy_p("m11g", "WR", 5, 18, chart_noise=10)]
    r11 = [noisy_p("t11g", "WR", 25, 22, chart_noise=10)]
    f = fit(finder_js, mine11 + g11, theirs11 + r11, g11, r11)
    # My DDF: bench swap, give 5 receive 25, net=+3.0 (bench weight 0.15). totalUp=true.
    # Their market: give 22, receive 18 = -4. Noise tau ~8.16. Within noise => theirOk=true.
    if f["label"] != "natural":
        say(f"noisy trade within noise floor should be natural: label={f['label']} them={f['them']['net']:.1f} tau={f['them']['tau']:.1f}")

    # 12. Your side has no noise floor (Jeremy, 2026-10-26): a small rise that is far inside the noise still counts.
    # Bench WR swap on the deep rosters of test 10; both moving players carry DDF noise 10 (charts vs projections), so
    # your tau is about 14 while your rise is only +0.45. Their side is level on the charts (inside their noise floor).
    mine12 = team("m12", [20, 12], [30, 25, 10, 8, 5], [30, 28, 15, 9, 7], [10, 5])
    theirs12 = team("t12", [22, 11], [35, 28, 25, 20, 15], [40, 35, 30, 25, 20], [11, 6])
    g12 = [p("m12g", "WR", 5, market=7, noise=10)]
    r12 = [p("t12g", "WR", 8, market=7, noise=10)]
    f = fit(finder_js, mine12 + g12, theirs12 + r12, g12, r12)
    if not (f["us"]["net"] > 0.05 and f["us"]["net"] < f["us"]["tau"]):
        say(f"test 12 setup: your rise should sit between 0.05 and your noise floor: net={f['us']['net']} tau={f['us']['tau']}")
    if f["label"] != "natural":
        say(f"a rise inside your noise floor should still be natural: label={f['label']} us net={f['us']['net']:.2f} tau={f['us']['tau']:.2f}")

    # 13. But the rise must be a rise: +0.03 (at or under the 0.05 display floor) is not natural.
    g13 = [p("m13g", "WR", 5, market=7, noise=10)]
    r13 = [p("t13g", "WR", 5.2, market=7, noise=10)]
    f = fit(finder_js, mine12 + g13, theirs12 + r13, g13, r13)
    if f["label"] == "natural":
        say(f"a rise of {f['us']['net']:.2f} is not a rise: label={f['label']}")

    # 14. Market supported needs any gain the page shows, not the noise floor (JEG-1187). On real charts the three or
    # four trade charts disagree by about 10 points on one player, so the other team's noise floor is several points
    # while the gain the finder leaves them is under a point; with the noise floor the label never appeared on the real
    # page. Bench WR swap on the deep rosters of test 11: your DDF Value total drops (not natural), their Trade chart
    # average rises 0.15 x 4 = +0.6 with a noise floor of about 8.
    g14 = [noisy_p("m14g", "WR", 8, 22, chart_noise=10)]
    r14 = [noisy_p("t14g", "WR", 5, 18, chart_noise=10)]
    f = fit(finder_js, mine11 + g14, theirs11 + r14, g14, r14)
    if not (0.05 < f["them"]["net"] < f["them"]["tau"]):
        say(f"test 14 setup: their gain should sit between 0.05 and their noise floor: net={f['them']['net']:.2f} tau={f['them']['tau']:.2f}")
    if f["label"] != "market" or not f.get("marketSupported"):
        say(f"their gain inside their noise floor should be market supported: label={f['label']} them={f['them']['net']:.2f} tau={f['them']['tau']:.2f}")
    text = call(finder_js, "fitText", f)
    if not text.startswith("Market supported: the trade charts favor them (+0.6)"):
        say(f"test 14 text should name their gain: {text!r}")

    # 15. But the gain must be one the page shows: +0.03 (under the 0.05 display floor) is not market supported.
    g15 = [noisy_p("m15g", "WR", 8, 18.2, chart_noise=10)]
    r15 = [noisy_p("t15g", "WR", 5, 18, chart_noise=10)]
    f = fit(finder_js, mine11 + g15, theirs11 + r15, g15, r15)
    if f["label"] != "force" or f.get("marketSupported"):
        say(f"a gain of {f['them']['net']:.2f} is not market supported: label={f['label']}")

    return errors


MUTANTS = {
    "construction check bypassed": ("const constructionOk = myConstruction.ok && theirConstruction.ok;", "const constructionOk = true;"),
    "starter drop allowed": ("const yourStartersOk = us.starterDelta >= -NET_FLOOR;", "const yourStartersOk = true;"),
    "their loss allowed": ("const theirOk = theirNet >= -theirTau;", "const theirOk = true;"),
    "noise ignored": ("const tau = Math.max(NET_FLOOR, (finite(ctx.z) ? ctx.z : FIT_Z) * noise);", "const tau = NET_FLOOR;"),
    "your side needs the noise floor": ("const yourTotalUp = us.net > NET_FLOOR;", "const yourTotalUp = us.net > us.tau;"),
    "your side needs no rise": ("const yourTotalUp = us.net > NET_FLOOR;", "const yourTotalUp = us.net > -1000;"),
    "market needs the noise floor": ("const marketSupported = theirNet > NET_FLOOR;", "const marketSupported = theirNet > theirTau;"),
    "market needs no gain": ("const marketSupported = theirNet > NET_FLOOR;", "const marketSupported = theirNet > -1000;"),
    "market always": ('const label = isNatural ? "natural" : marketSupported ? "market" : "force";', 'const label = "market";'),
    "tiers reversed": ("a.t - b.t || a.i - b.i", "b.t - a.t || a.i - b.i"),
    "tiers unstable": ("a.t - b.t || a.i - b.i", "a.t - b.t || b.i - a.i"),
}


class FinderFitTests(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(check(FINDER_JS), [])

    def test_checks_fail_on_broken_builds(self):
        source = FINDER_JS.read_text(encoding="utf-8")
        for name, (old, new) in MUTANTS.items():
            with self.subTest(name):
                self.assertIn(old, source, f"mutant {name!r} no longer applies")
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "finder.js"
                    path.write_text(source.replace(old, new, 1), encoding="utf-8")
                    self.assertTrue(check(path), f"checks passed on a build with: {name}")


if __name__ == "__main__":
    unittest.main()
