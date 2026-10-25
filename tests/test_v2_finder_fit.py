"""v2 Find a trade v2 (JEG-988), commit 4: natural fit and force fit, pure rules in app/v2/finder.js.

Each team is judged in its own view (you: DDF Value; they: the Trade chart average). A team's net change is its best
lineup's starter value plus its bench value at the engine's bench weight (never 1:1), after minus before; it counts only
beyond the noise of the sources. Need is the distance from the expected depth band plus empty starting slots. A team is
served when it gains and does not move away from its depth, or is level and moves toward it. Natural: both served and one
moves toward its depth. Value fit: both served, no depth change. Force: anything else. Cases (12 teams, 1/2/2/1/1 FLEX):

  * a swap of two backups that fixes both teams' bench balance with no starter gain is natural;
  * the same swap the wrong way round (each deepens a position it is already deep at) is force, and so is a starter gain
    that deepens a position the team is already deep at;
  * a starter loss is not offset 1:1 by bench value: giving a 10 starter for 30 of bench value is force;
  * a thin team giving its RB1 for two RB2s gains starter value (two slots filled), and with the deep team gaining on its
    market view the label is natural; the deep team giving its star for two RB2s that fill no extra slot is force;
  * they are judged on the market view: a trade that is up on DDF for them but down on the charts is force;
  * a gain smaller than the sources' own disagreement is not a gain;
  * tierGroups moves natural first, then value, then force, keeps every group and the order within a tier.

Discrimination: test_checks_fail_on_broken_builds runs the same checks on copies of finder.js with a rule broken.
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


# A: deep at WR (8, over), short at RB (3, under). B: the reverse. Backups: A's WR5 (5) and B's RB6 (5).
A = team("a", [20, 12], [30, 25, 10], [30, 28, 15, 9, 8, 7, 6, 5], [10, 5])
B = team("b", [22, 11], [35, 28, 14, 12, 9, 8, 5], [26, 20, 9], [11, 6])


def check(finder_js: Path) -> list[str]:
    errors = []
    say = errors.append
    # 1. A bench swap that rebalances both teams, no starter gain: natural.
    f = fit(finder_js, A, B, pick(A, "aWR7"), pick(B, "bRB6"))
    if f["label"] != "natural" or not (f["us"]["toward"] and f["them"]["toward"]) or abs(f["us"]["starterDelta"]) > 1e-9 or abs(f["us"]["net"]) > 0.05:
        say(f"bench rebalance: {f['label']} us toward {f['us']['toward']} them toward {f['them']['toward']} us starters {f['us']['starterDelta']} net {f['us']['net']}")
    if f["us"]["towardAt"] != ["RB", "WR"] or f["them"]["towardAt"] != ["RB", "WR"]:
        say(f"bench rebalance moves toward {f['us']['towardAt']} / {f['them']['towardAt']}, want RB and WR on both")
    text = call(finder_js, "fitText", f)
    if not text.startswith("Natural fit:") or "You are short at RB and deep at WR; they are short at WR and deep at RB." not in text:
        say(f"bench rebalance text: {text!r}")
    # 2. The reverse swap deepens each side's deep position: force, though nothing is lost.
    f = fit(finder_js, A, B, pick(A, "aRB2"), pick(B, "bWR2"))
    if f["label"] != "force" or not (f["us"]["away"] or f["them"]["away"]):
        say(f"deepening swap: {f['label']} us away {f['us']['away']} them away {f['them']['away']}")
    # 3. A starter gain that deepens an already-deep position (a WR star for an RB backup): force for you.
    A2 = A + [p("aWRx", "WR", 12)]
    B2 = B + [p("bWRstar", "WR", 40)]
    f = fit(finder_js, A2, B2, pick(A2, "aRB2"), pick(B2, "bWRstar"))
    if not f["us"]["up"] or not f["us"]["away"] or f["us"]["ok"] or f["label"] != "force":
        say(f"starter gain that deepens a deep position: {f['label']} up {f['us']['up']} away {f['us']['away']}")
    # 4. Bench value is not 1:1: giving a 30 starter for two 25 backups costs 4 of starter value and gains 24 of bench value,
    # which is +20 counted 1:1 but -0.4 at the bench weight (0.15).
    mine = team("m", [20, 12], [30, 28, 27, 26], [14, 13, 6, 5, 4, 3], [8, 4])
    theirs = team("t", [22, 11], [25, 25, 9, 8], [26, 20, 9, 6, 5, 4], [11, 6])
    f = fit(finder_js, mine, theirs, pick(mine, "mRB0"), pick(theirs, "tRB0", "tRB1"))
    if f["us"]["net"] >= 0 or f["us"]["starterDelta"] > -3.9 or f["label"] != "force":
        say(f"a starter swapped for bench value: net {f['us']['net']} starters {f['us']['starterDelta']} label {f['label']} (at 1:1 it would be a gain)")
    # 5. Thin team gives its RB1 for two RB2s: two lineup slots fill. Natural when the deep team gains on its market view.
    thin = team("n", [20, 12], [30], [20, 18, 10, 8], [6])
    deep = team("d", [20, 14], [35, 16, 16, 12, 9, 7, 6], [25, 22, 21, 9, 5], [11, 6])
    f = fit(finder_js, thin, deep, pick(thin, "nRB0"), pick(deep, "dRB1", "dRB2"))
    if not (f["us"]["starterDelta"] > 1.9 and f["us"]["starterDelta"] < 2.1) or f["label"] != "natural" or not f["them"]["up"] or not f["us"]["toward"]:
        say(f"thin team 1-for-2: starters {f['us']['starterDelta']} label {f['label']} them up {f['them']['up']} us toward {f['us']['toward']}")
    # 5b. The counter-example: the deep team gives its star for two RB2s that fill no extra slot.
    f = fit(finder_js, deep, thin + [p("nRBb", "RB", 16), p("nRBc", "RB", 16)], pick(deep, "dRB0"), pick(thin + [p("nRBb", "RB", 16), p("nRBc", "RB", 16)], "nRBb", "nRBc"))
    if not f["us"]["down"] or f["label"] != "force":
        say(f"deep team's star for two RB2s that fill no slot: net {f['us']['net']} label {f['label']}")
    # 6. They are judged on the market view: a gain on DDF Value for them is no help when the charts they read say they lose.
    star = p("aRBs", "RB", 30, market=10)
    theirs = [p("bRBs", "RB", 25, market=30)] + [r for r in B if r["player_key"] != "bRB0"]
    mine = [r for r in A if r["player_key"] != "aRB0"] + [star]
    f = fit(finder_js, mine, theirs, pick(mine, "aRBs"), pick(theirs, "bRBs"))
    if f["themOther"]["net"] <= 0:
        say("fixture: they do not gain on DDF Value")
    if f["them"]["net"] >= 0 or f["label"] != "force":
        say(f"market view for them: net {f['them']['net']} label {f['label']}")
    # 7. A gain smaller than the sources' own disagreement is no gain.
    noisy = team("z", [20, 12], [30, 25, 10, 6], [30, 28, 15, 9, 8, 7], [10, 5])
    noisy = [p(r["player_key"], r["pos"], r["values"]["ddf_value"], noise=3.0) if r["player_key"] == "zRB1" else r for r in noisy]
    other = [p("yRBn", "RB", 26.5, noise=3.0)] + team("y", [22, 11], [35, 28], [26, 20, 9, 8, 7], [11, 6])
    f = fit(finder_js, noisy, other, pick(noisy, "zRB1"), pick(other, "yRBn"))
    if f["us"]["up"] or f["us"]["tau"] <= 1.0:
        say(f"a +1.5 gain inside the noise: up {f['us']['up']} tau {f['us']['tau']}")
    # 7b. A value fit: both teams are balanced and both gain on their own view, one RB for one RB: no depth changes.
    bal_a = team("a", [20, 12], [30, 15, 12, 9, 7], [30, 28, 15, 9, 8, 7], [10, 5])
    bal_b = team("b", [22, 11], [35, 14, 12, 9, 8], [26, 20, 9, 8, 7, 6], [11, 6])
    x = p("aX", "RB", 25, market=40)
    y = p("bY", "RB", 30, market=20)
    bal_a, bal_b = bal_a + [x], bal_b + [y]
    f = fit(finder_js, bal_a, bal_b, [x], [y])
    if f["label"] != "value" or not (f["us"]["up"] and f["them"]["up"]) or f["fillsNeed"]:
        say(f"balanced one-for-one gain for both: {f['label']} us up {f['us']['up']} them up {f['them']['up']} fills need {f['fillsNeed']}")
    # 8. tierGroups: natural, value, force; stable; nothing lost.
    out = call(finder_js, "tierOrder", ["force", "natural", "value", "natural", None, "force"])
    if out != [1, 3, 2, 0, 5, 4]:
        say(f"tierGroups order {out}, want [1, 3, 2, 0, 5, 4]")
    return errors


MUTANTS = {
    "bench valued 1:1": ("const benchWeight = (weights, pos) => (weights &&", "const benchWeight = (weights, pos) => (true ? 1 : weights &&"),
    "moving away allowed": ("ok: (up && !away) || (!up && !down && toward)", "ok: up || (!up && !down && toward)"),
    "level team served without depth change": ("ok: (up && !away) || (!up && !down && toward)", "ok: (up && !away) || !down"),
    "their view reads DDF": ("const them = teamFit(sides.theirs, ctx, ctx.marketKey);", "const them = teamFit(sides.theirs, ctx, ctx.ourKey);"),
    "noise ignored": ("const tau = Math.max(NET_FLOOR, (finite(ctx.z) ? ctx.z : FIT_Z) * noise);", "const tau = NET_FLOOR;"),
    "no need needed for natural": ('(fillsNeed ? "natural" : "value")', '"natural"'),
    "force never": ('yourOk && them.ok ? (fillsNeed ? "natural" : "value") : "force"', "(fillsNeed ? \"natural\" : \"value\")"),
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
