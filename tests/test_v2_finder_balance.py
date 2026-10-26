"""v2 Find a trade v2 (JEG-988), commit 3: roster balance and the generated evaluation, pure rules in app/v2/finder.js.

  * expectedDepth: the engine's seats per team (starters plus bench seats, league-wide rostered / teams), as a range:
    12 teams with the standard allocation give QB 2-3, RB 4-5, WR 5-6, TE 1-2;
  * rosterBalance: a player counts toward a view's depth only with a usable value in that view (>= 0.05); under means
    fewer than the low end, over means two or more above the high end (one extra is normal depth); a partial roster is
    not ready; unusable players are listed, never counted as 0 and never dropped;
  * evalSentence: "Based on <view>, your roster is overweight at ... and underweight at ...", the lineup values in that
    view, a note for players with no usable value; a balanced roster says so.

Discrimination: test_checks_fail_on_broken_builds runs the same checks on copies of finder.js with a rule broken.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.test_v2_finder_import import FINDER_JS, call

ALLOC = [{"pos": "QB", "lineup": 12, "bench": 15, "rostered": 27}, {"pos": "RB", "lineup": 27, "bench": 28, "rostered": 55},
         {"pos": "WR", "lineup": 33, "bench": 35, "rostered": 68}, {"pos": "TE", "lineup": 12, "bench": 6, "rostered": 18}]
SHAPE = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "SUPERFLEX": 0}


def row(pos, i, ddf=10.0, market=None):
    values = {"ddf_value": ddf}
    if market is not None or ddf is None:
        values["chart_avg"] = market
    return {"player_key": f"{pos}{i}", "pos": pos, "values": values}


def roster(counts, **kw):
    return [row(pos, i, **kw) for pos, n in counts.items() for i in range(n)]


def check(finder_js: Path) -> list[str]:
    errors = []
    expected = call(finder_js, "expectedDepth", ALLOC, 12)
    got = {pos: (e["lo"], e["hi"]) for pos, e in (expected or {}).items()}
    if got != {"QB": (2, 3), "RB": (4, 5), "WR": (5, 6), "TE": (1, 2)}:
        errors.append(f"expected depth is {got}")
    if expected and abs(expected["RB"]["expected"] - 55 / 12) > 1e-9:
        errors.append("the expected RB count is not rostered / teams")
    if call(finder_js, "expectedDepth", ALLOC, 0) is not None or call(finder_js, "expectedDepth", None, 12) is not None:
        errors.append("expected depth without teams or an allocation is not null")
    # Roster A of the spec: RB-heavy, short at QB / WR; the TE with value 0 is not depth.
    a = roster({"QB": 1, "RB": 6, "WR": 2}) + [row("TE", 0, 5.0), row("TE", 1, 0.0)]
    b = call(finder_js, "rosterBalance", a, expected, "ddf_value", SHAPE)
    if b["under"] != ["QB", "WR"] or b["over"] != []:
        errors.append(f"roster A: under {b['under']} over {b['over']}, want under QB and WR")
    if b["positions"]["TE"]["have"] != 1 or b["positions"]["TE"]["unusable"] != 1 or b["unusable"] != 1:
        errors.append(f"a TE worth 0.0 was counted as depth: {b['positions']['TE']}")
    if not b["ready"]:
        errors.append("a roster with 11 players for 7 slots is not ready")
    # Over: eight RBs where 4-5 are expected; seven is still normal depth plus one.
    b = call(finder_js, "rosterBalance", roster({"QB": 2, "RB": 8, "WR": 5, "TE": 2}), expected, "ddf_value", SHAPE)
    if b["over"] != ["RB"] or b["under"] != []:
        errors.append(f"eight RBs: over {b['over']} under {b['under']}")
    b = call(finder_js, "rosterBalance", roster({"QB": 2, "RB": 6, "WR": 5, "TE": 2}), expected, "ddf_value", SHAPE)
    if b["over"] or b["under"]:
        errors.append(f"six RBs (one above the range) flagged: over {b['over']} under {b['under']}")
    # The market view: players the charts do not price (null) do not count, so the same roster reads differently.
    full = roster({"QB": 2, "RB": 5, "WR": 6, "TE": 2}, market=3.0)
    thin = [dict(r, values={**r["values"], "chart_avg": None}) if r["pos"] == "WR" and r["player_key"] in ("WR3", "WR4", "WR5") else r for r in full]
    if call(finder_js, "rosterBalance", thin, expected, "chart_avg", SHAPE)["under"] != ["WR"]:
        errors.append("three WRs the charts do not price were counted as market depth")
    if call(finder_js, "rosterBalance", thin, expected, "ddf_value", SHAPE)["under"] != []:
        errors.append("the fundamental view was changed by chart prices")
    # A partial roster is not ready.
    if call(finder_js, "rosterBalance", roster({"QB": 1, "RB": 2, "WR": 2}), expected, "ddf_value", SHAPE)["ready"]:
        errors.append("a partial roster is judged")
    # Sentences.
    b = call(finder_js, "rosterBalance", roster({"QB": 2, "RB": 8, "WR": 2, "TE": 2}), expected, "ddf_value", SHAPE)
    s = call(finder_js, "evalSentence", "your", "fundamentals", "DDF Value", b, {"starters": 141.94, "bench": 37.8})
    for need in ("Based on fundamentals, your roster is overweight at RB (8 counted, 4-5 expected) and underweight at WR (2 counted, 5-6 expected).",
                 "Your starting lineup is worth 141.9 in DDF Value; the bench adds 37.8."):
        if need not in s:
            errors.append(f"sentence lacks {need!r}: {s!r}")
    ok = call(finder_js, "rosterBalance", roster({"QB": 2, "RB": 5, "WR": 6, "TE": 2}), expected, "ddf_value", SHAPE)
    s = call(finder_js, "evalSentence", "their", "market pricing", "trade chart average", ok, {"starters": 10, "bench": 2})
    if not s.startswith("Based on market pricing, their roster is balanced by position.") or "Their starting lineup is worth 10.0 in trade chart average" not in s:
        errors.append(f"balanced sentence reads {s!r}")
    s = call(finder_js, "evalSentence", "your", "fundamentals", "DDF Value", call(finder_js, "rosterBalance", a, expected, "ddf_value", SHAPE), {"starters": 1, "bench": 1})
    if "1 player has no usable value in this view and is not counted toward depth." not in s:
        errors.append(f"the unusable note is missing: {s!r}")
    # JEG-1019: the biggest imbalance (the one line the table does not say) and the natural-fit headline texts.
    worst = call(finder_js, "biggestImbalance", call(finder_js, "rosterBalance", roster({"QB": 2, "RB": 7, "WR": 2, "TE": 2}), expected, "ddf_value", SHAPE))
    if not worst or (worst["pos"], worst["status"]) != ("WR", "under") or worst["gap"] != 3:
        errors.append(f"the biggest imbalance is {worst} (WR is 3 short, RB 2 over)")
    if call(finder_js, "biggestImbalance", ok) is not None:
        errors.append("a balanced roster has a biggest imbalance")
    heads = {k: call(finder_js, "fitHeadline", k, v)["text"] for k, v in (("missing", {}), ("pending", {}), ("natural", {"count": 1}), ("none", {}), ("unjudged", {}))}
    if heads["missing"] != "Add both rosters to see fit" or heads["natural"] != "Natural fit found: 1 group" or call(finder_js, "fitHeadline", "natural", {"count": 3})["text"] != "Natural fit found: 3 groups":
        errors.append(f"headline texts: {heads}")
    if heads["none"] != "No natural fit between these rosters: the trades below are market supported or force fits":
        errors.append(f"the no-natural headline reads {heads['none']!r}")
    if call(finder_js, "fitHeadline", "natural", {"count": 2})["link"] is None or call(finder_js, "fitHeadline", "none", {})["link"] is not None:
        errors.append("the jump link is offered without a natural group, or missing with one")
    # Throw-ins are live in the search (JEG-1108): the team that receives more players adds its own least valuable
    # bench player (a non-starter, Jeremy 2026-10-26), so no trade the search lists has unequal player counts, and the added player is listed on it.
    def tr(key, pos, ddf, charts):
        return {"player_key": key, "name": key, "pos": pos, "values": dict(zip(["ddf_value", "usatoday", "fantasycalc", "fantasypros", "cbs"], [ddf] + [charts] * 4))}
    mine_rows = [tr("M1", "WR", 10, 20), tr("M2", "WR", 0.3, 0.3), tr("M3", "WR", 0.4, 0.4)]
    their_rows = [tr("T1", "WR", 8, 8), tr("T2", "WR", 4, 4)]
    chart_keys = ["usatoday", "fantasycalc", "fantasypros", "cbs"]
    res = call(finder_js, "findTrades", mine_rows, their_rows, {"chartKeys": chart_keys, "maxSize": 2, "limit": 50})
    unequal = [t for t in res["trades"] if len(t["give"]) != len(t["receive"])]
    if unequal:
        errors.append(f"the search listed {len(unequal)} trade(s) with unequal player counts; throw-ins are not wired in")
    flagged = [t for t in res["trades"] if t.get("addedThrowIns")]
    if not any(t["addedThrowIns"][0]["row"]["player_key"] == "M2" and t["addedThrowIns"][0]["side"] == "give" for t in flagged):
        errors.append("a 1-for-2 package did not get my least valuable player (M2) as a listed throw-in")
    ids = [",".join(r["player_key"] for r in t["give"]) + "|" + ",".join(r["player_key"] for r in t["receive"]) for t in res["trades"]]
    if len(ids) != len(set(ids)):
        errors.append("the search listed the same package twice (throw-in variants not collapsed)")
    # The throw-in is judged with the package: M2 is a real cost, so the edge is 12 - 10.3, not 12 - 10.
    one = [t for t in res["trades"] if [r["player_key"] for r in t["give"]] == ["M1", "M2"] and len(t["receive"]) == 2]
    if one and abs(one[0]["edge"] - 1.7) > 1e-6:
        errors.append(f"the throw-in was not counted in the edge: {one[0]['edge']}")
    # Two players short: 1-for-3 gets two throw-ins (my two cheapest), not one.
    res = call(finder_js, "findTrades", mine_rows + [tr("M4", "WR", 0.5, 0.5)], their_rows + [tr("T3", "WR", 2, 2)], {"chartKeys": chart_keys, "maxSize": 3, "limit": 200})
    if any(len(t["give"]) != len(t["receive"]) for t in res["trades"]):
        errors.append("with a 3-player package the search still lists unequal player counts")
    if not any(len(t.get("addedThrowIns") or []) == 2 for t in res["trades"]):
        errors.append("a 1-for-3 package did not get two throw-ins")
    # The throw-in is the least valuable BENCH player, not the least valuable overall: Q1 (0.1) is the lone QB and starts.
    shape_qw = {"QB": 1, "RB": 0, "WR": 1, "TE": 0, "FLEX": 0, "SUPERFLEX": 0}
    mine_b = [tr("Q1", "QB", 0.1, 0.1), tr("W1", "WR", 10, 20), tr("W2", "WR", 3, 3), tr("W3", "WR", 5, 5)]
    theirs_b = [tr("T1", "WR", 9, 9), tr("T2", "WR", 8, 8)]
    res = call(finder_js, "findTrades", mine_b, theirs_b, {"chartKeys": chart_keys, "maxSize": 2, "limit": 50,
               "sanity": {"shape": shape_qw, "mine": mine_b, "theirs": theirs_b, "keepMine": False, "keepTheirs": False}})
    added = [t["addedThrowIns"][0]["row"]["player_key"] for t in res["trades"] if t.get("addedThrowIns") and t["addedThrowIns"][0]["side"] == "give"]
    if "Q1" in added:
        errors.append("a starter (the lone QB) was added as the throw-in")
    if "W2" not in added:
        errors.append(f"the throw-in should be the cheapest bench player W2, got {added}")
    # A team with no bench player left cannot supply a throw-in: the trade stays, marked unbalanced, nothing added.
    shape = {"QB": 0, "RB": 0, "WR": 2, "TE": 0, "FLEX": 0, "SUPERFLEX": 0}
    res = call(finder_js, "findTrades", mine_rows[:2], their_rows, {"chartKeys": chart_keys, "maxSize": 2, "limit": 50,
               "sanity": {"shape": shape, "mine": mine_rows[:2], "theirs": their_rows, "keepMine": False, "keepTheirs": False}})
    skipped = [t for t in res["trades"] if t.get("unbalanced")]
    if not skipped or any(t.get("addedThrowIns") for t in skipped):
        errors.append("a team with no bench player should leave the trade unbalanced with no throw-in added")

    return errors


MUTANTS = {
    "headline says natural for none": ('return {text: `No natural fit between these rosters:', 'return {text: `Natural fit found:'),
    "biggest imbalance picks the smallest": ("(!worst || gap > worst.gap)", "(!worst || gap < worst.gap)"),
    "bench seats ignored": ("const expected = a.rostered / teams;", "const expected = a.lineup / teams;"),
    "range lo rounded up": ("lo: Math.floor(expected + 1e-9)", "lo: Math.ceil(expected - 1e-9)"),
    "zero-value counted as depth": ("r.values[valueKey] >= USABLE_MIN", "r.values[valueKey] >= 0"),
    "under rule loose": ("have < e.lo ? \"under\"", "have < e.lo - 1 ? \"under\""),
    "over rule one early": ("have > e.hi + 1 ? \"over\"", "have > e.hi ? \"over\""),
    "partial roster judged": ("includes(r.pos)).length >= slots &&", "includes(r.pos)).length >= 0 &&"),
    "market view reads fundamentals": ("r.values && finite(r.values[valueKey]) && r.values[valueKey] >= USABLE_MIN", "r.values && finite(r.values.ddf_value) && r.values.ddf_value >= USABLE_MIN"),
    "throw-ins not wired into the search": ("const step = balanceCounts(work, balanceMine, balanceTheirs, balanceShape, ourKey, keys);", "const step = {balanced: false};"),
    "throw-in may be a starter": ("&& !starterKeys.has(String(r.player_key)) && priced(r)", "&& priced(r)"),
    "only one throw-in added": ("while (work.give.length !== work.receive.length) {", "while (work.give.length < 1 && work.give.length !== work.receive.length) {"),
    "sentence drops the lineup": ("const value = sums ?", "const value = false ?"),
}


class FinderBalanceTests(unittest.TestCase):
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
