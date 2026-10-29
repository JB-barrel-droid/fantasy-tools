"""A loaded league sets the bench from its own rosters, at two levels (JEG-1188).

Jeremy, 2026-10-29: "we focus on vorp, let other managers make stupid
decisions and capitalize", and "So we are keeping a market level of bench and
a ddf level?" ... "Yes, build it".

  ddf     his value: pure value over replacement, where replacement is the
          league's best available player at each position.
  market  the other side: the league's actual rostered depth.

With no league (setting.league_rostered absent) the modeled bench rule runs
and nothing changes; tests/test_value_pipeline_engine.py pins that path.

Checks: roster_convention.league_bench on its own; the JS engine
(value-model.js, run under node) against the spec reference at both levels
on the worked example, every leaf; the bench counts each level gives; and the
Python reference's League takes the same fields. The bench-count tests fail
on an engine without JEG-1188 (it ignores league_rostered).
"""
from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from lib.roster_convention import league_bench  # noqa: E402
from tests.test_value_pipeline_engine import (  # noqa: E402
    DRIVER, FIXTURE, VALUE_MODEL, _node, _spec_args, diff)

# The worked example's league (2 teams; starters QB 2, RB 2, WR 3, TE 3).
# QB 103, RB 207, WR 305 and TE 404 are the best free agents; QB 104 and
# RB 204/205 and WR 306 are rostered below one.
LEAGUE = [101, 102, 104, 201, 202, 203, 204, 205, 301, 302, 303, 304, 306, 401, 402, 403]
BENCH = {"ddf": {"QB": 0, "RB": 1, "WR": 1, "TE": 0},
         "market": {"QB": 1, "RB": 3, "WR": 2, "TE": 0}}
POS = ("QB", "RB", "WR", "TE")
# Keys the two engines name differently or the spec reference adds.
IGNORED = ("indexed_factor", ".name:")


def run_js(level: str | None, rostered=LEAGUE) -> dict:
    extra = {} if level is None else {"league_rostered": [str(k) for k in rostered], "bench_level": level}
    cmd = [_node(), str(DRIVER), str(VALUE_MODEL), str(FIXTURE), "--variant", "variant_expected_starts",
           "--setting", json.dumps(extra)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError(f"driver failed: {proc.stderr[-2000:]}")
    return json.loads(proc.stdout)


def run_spec(level: str | None, rostered=LEAGUE) -> dict:
    from spec_reference import value_pipeline as sp
    setting, pos_of, sources, inc_keys, lineup = _spec_args()
    if level is not None:
        setting = dataclasses.replace(setting, league_rostered=tuple(rostered), bench_level=level)
    return json.loads(json.dumps(sp.run_week(setting, pos_of, sources, inc_keys, lineup=lineup)))


class TestLeagueBenchRule(unittest.TestCase):
    order = {"QB": [1, 2, 3, 4, 5], "RB": [11, 12, 13, 14], "WR": [], "TE": [31, 32]}
    starters = {"QB": 2, "RB": 2, "WR": 0, "TE": 1}

    def test_ddf_stops_at_the_best_free_agent(self):
        # QB 3 is free: QBs 4 and 5 are rostered below him and get no seat.
        got = league_bench(self.starters, self.order, [1, 2, 4, 5, 11, 12, 13, 14, 31], "ddf")
        self.assertEqual({p: got[p] for p in POS}, {"QB": 0, "RB": 2, "WR": 0, "TE": 0})

    def test_market_counts_the_rostered_depth(self):
        got = league_bench(self.starters, self.order, [1, 2, 4, 5, 11, 12, 13, 14, 31], "market")
        self.assertEqual({p: got[p] for p in POS}, {"QB": 2, "RB": 2, "WR": 0, "TE": 0})

    def test_free_agent_inside_the_starter_line_gives_no_bench(self):
        got = league_bench(self.starters, self.order, [2, 3, 4], "ddf")
        self.assertEqual(got["QB"], 0)

    def test_keys_compare_as_strings(self):
        a = league_bench(self.starters, self.order, ["1", "2", "3"], "ddf")
        b = league_bench(self.starters, {p: [str(k) for k in ks] for p, ks in self.order.items()}, [1, 2, 3], "ddf")
        self.assertEqual(a, b)
        self.assertEqual(a["QB"], 1)

    def test_unknown_level_raises(self):
        with self.assertRaises(ValueError):
            league_bench(self.starters, self.order, [], "chart")


class TestEngineLevels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _node()
        cls.js = {lvl: run_js(lvl) for lvl in ("ddf", "market")}
        cls.spec = {lvl: run_spec(lvl) for lvl in ("ddf", "market")}

    def test_bench_counts_by_level(self):
        for lvl, want in BENCH.items():
            for name, res in (("js", self.js[lvl]), ("spec", self.spec[lvl])):
                with self.subTest(level=lvl, engine=name):
                    self.assertEqual({p: res["allocation"][p]["bench"] for p in POS}, want)

    def test_js_matches_spec_reference_at_both_levels(self):
        for lvl in ("ddf", "market"):
            for key in ("allocation", "fill_sets", "sources", "indexed", "rows", "default_ranking"):
                with self.subTest(level=lvl, part=key):
                    problems = [d for d in diff(self.spec[lvl][key], self.js[lvl].get(key), key)
                                if not any(i in d for i in IGNORED)]
                    self.assertEqual(problems, [], problems[:5])
        self.assertEqual(len(self.spec["ddf"]["rows"]), 30, "the comparison must cover every fixture player")

    def test_rostered_below_the_best_free_agent_is_worth_nothing_to_him(self):
        # RB 205 is rostered but ranks below RB 207, a free agent: zero at the
        # DDF level, worth something at the market level (a sell candidate).
        ddf = self.js["ddf"]["rows"]["205"]["ddf_blended"]["value"]
        market = self.js["market"]["rows"]["205"]["ddf_blended"]["value"]
        self.assertEqual(ddf, 0)
        self.assertGreater(market, 0)

    def test_no_league_is_the_modeled_rule(self):
        base = run_js(None)
        self.assertNotEqual(base["allocation"], self.js["ddf"]["allocation"])
        self.assertEqual(base["allocation"], run_spec(None)["allocation"])


class TestPythonReferenceLeague(unittest.TestCase):
    def test_league_fields_reach_the_allocation(self):
        import value_reference as ref
        lg = ref.League(teams=2, slots={"QB": 1, "RB": 1, "WR": 1, "TE": 1}, flex=1, bench=2,
                        league_rostered=tuple(LEAGUE), bench_level="market")
        order = {"QB": [101, 102, 103, 104], "RB": [201, 202, 203, 207, 204, 205], "WR": [301, 302, 303, 304, 305, 306],
                 "TE": [401, 402, 403, 404]}
        score = {k: 100 - i for p in order for i, k in enumerate(order[p])}
        # Two flex seats go to RB 203 and WR 303: starters QB 2, RB 3, WR 3, TE 2.
        got = ref.allocate(lg, order, score)
        self.assertEqual({p: got[p]["bench"] for p in POS}, {"QB": 1, "RB": 2, "WR": 2, "TE": 1})
        ddf = ref.allocate(dataclasses.replace(lg, bench_level="ddf"), order, score)
        self.assertEqual({p: ddf[p]["bench"] for p in POS}, {"QB": 0, "RB": 0, "WR": 1, "TE": 1})


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Codex review on #1105 (2026-10-29): the replacement line is its own index,
# separate from the starter count; IR and taxi players are held but are not
# active depth; the three counts carry their own names.
# ---------------------------------------------------------------------------

def js_call(fn: str, *args):
    """ValueModel.<fn>(*args) under node, JSON in and out."""
    script = (f"const V = require({json.dumps(str(VALUE_MODEL))});"
              f"process.stdout.write(JSON.stringify(V.{fn}(...{json.dumps(list(args))})));")
    proc = subprocess.run([_node(), "-e", script], capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr[-2000:])
    return json.loads(proc.stdout)


class TestLeagueDepthFields(unittest.TestCase):
    order = {"QB": ["1", "2", "3", "4", "5"], "RB": ["11", "12", "13", "14"], "WR": [], "TE": ["31", "32"]}
    starters = {"QB": 2, "RB": 2, "WR": 0, "TE": 1}

    def test_reserve_is_held_but_not_depth(self):
        from lib.roster_convention import league_depth
        # QB 3 sits in an IR slot: still not a free agent (QB 4 is), but not active depth.
        rostered, reserve = ["1", "2", "3", "5", "11", "12", "13", "31"], ["3"]
        ddf = league_depth(self.starters, self.order, rostered, "ddf", reserve)
        market = league_depth(self.starters, self.order, rostered, "market", reserve)
        self.assertEqual(ddf["QB"], {"bench": 1, "replacement": 3, "held": 3, "reserve": 1,
                                     "best_free_index": 3, "bench_basis": "above_replacement"})
        self.assertEqual(market["QB"], {"bench": 1, "replacement": 3, "held": 3, "reserve": 1,
                                        "best_free_index": 3, "bench_basis": "rostered_depth"})
        # Without the reserve list QB 3 counts as depth: market bench 2.
        self.assertEqual(league_depth(self.starters, self.order, rostered, "market")["QB"]["bench"], 2)

    def test_free_agent_inside_the_starter_line_sets_replacement_there(self):
        from lib.roster_convention import league_depth
        got = league_depth(self.starters, self.order, ["2", "3", "4", "5"], "ddf")["QB"]
        self.assertEqual((got["replacement"], got["bench"], got["held"]), (0, 0, 4))

    def test_js_matches_python(self):
        from lib.roster_convention import league_depth
        orders_js = {p: [{"key": k} for k in ks] for p, ks in self.order.items()}
        cases = [(["1", "2", "3", "5", "11", "12", "13", "31"], ["3"]), (["2", "3", "4", "5"], []),
                 ([], []), ([k for ks in self.order.values() for k in ks], ["31", "32"])]
        for rostered, reserve in cases:
            for level in ("ddf", "market"):
                with self.subTest(rostered=rostered, level=level):
                    got = js_call("leagueDepth", self.starters, orders_js, rostered, level, reserve)
                    want = league_depth(self.starters, self.order, rostered, level, reserve)
                    self.assertEqual({p: got[p] for p in POS}, {p: want[p] for p in POS})


class TestReplacementInsideStarters(unittest.TestCase):
    """Codex's P1 probe: the best player at a position is a free agent. The
    waiver line must be that player, not the last starter, so every QB is
    worth nothing over replacement at the DDF level. Fails on 9614452 (the
    waiver stayed at work[starters])."""
    # QB 101, the top QB in every source, is free; 102-104 are held.
    FREE_TOP_QB = [k for k in LEAGUE if k != 101] + [103]

    @classmethod
    def setUpClass(cls):
        _node()
        cls.js = {lvl: run_js(lvl, cls.FREE_TOP_QB) for lvl in ("ddf", "market")}
        cls.spec = {lvl: run_spec(lvl, cls.FREE_TOP_QB) for lvl in ("ddf", "market")}
        doc = json.loads(FIXTURE.read_text())
        qbs = [k for k, p in doc["players"].items() if p["pos"] == "QB"]
        cls.top_qb = {s: max(v["values"][k] for k in qbs if k in v["values"]) for s, v in doc["inputs"].items()}

    def test_waiver_is_the_free_agent_in_every_source(self):
        for name, res in (("js", self.js["ddf"]), ("spec", self.spec["ddf"])):
            self.assertEqual(res["allocation"]["QB"]["replacement"], 0, name)
            self.assertEqual(res["allocation"]["QB"]["bench"], 0, name)
            self.assertEqual(res["allocation"]["QB"]["starters"], 2, name)
            for src, info in res["sources"].items():
                with self.subTest(engine=name, source=src):
                    pos = info["positions"]["QB"]
                    self.assertEqual(pos["replacement"], 0)
                    self.assertEqual(pos["waiver_value"], self.top_qb[src])

    def test_every_qb_is_worth_nothing_to_him(self):
        for name, res in (("js", self.js["ddf"]), ("spec", self.spec["ddf"])):
            for k in ("101", "102", "103", "104"):
                with self.subTest(engine=name, player=k):
                    self.assertEqual(res["rows"][k]["ddf_blended"]["value"], 0)

    def test_market_level_still_prices_the_held_qbs(self):
        for name, res in (("js", self.js["market"]), ("spec", self.spec["market"])):
            self.assertGreater(res["rows"]["101"]["ddf_blended"]["value"], 0, name)
            self.assertEqual(res["allocation"]["QB"]["replacement"], 3, name)

    def test_js_matches_spec_reference(self):
        for lvl in ("ddf", "market"):
            for key in ("allocation", "fill_sets", "sources", "indexed", "rows", "default_ranking"):
                with self.subTest(level=lvl, part=key):
                    problems = [d for d in diff(self.spec[lvl][key], self.js[lvl].get(key), key)
                                if not any(i in d for i in IGNORED)]
                    self.assertEqual(problems, [], problems[:5])

    def test_python_reference_eight_team_probe(self):
        # Codex's numbers: 8 teams, QB1, Q1 (29 PPG) free, Q2..Q17 held.
        import value_reference as ref
        keys = [f"q{i}" for i in range(1, 18)]
        nat = {k: 29 - i for i, k in enumerate(keys)}
        lg = ref.League(teams=8, slots={"QB": 1, "RB": 0, "WR": 0, "TE": 0}, flex=0, bench=2,
                        league_rostered=tuple(keys[1:]), bench_level="ddf")
        alloc = ref.allocate(lg, {"QB": keys, "RB": [], "WR": [], "TE": []}, dict(nat))
        self.assertEqual((alloc["QB"]["starters"], alloc["QB"]["bench"], alloc["QB"]["replacement"]), (8, 0, 0))
        out = ref._source_lines(ref.SourceInput("p1", "projection", nat), {k: "QB" for k in keys}, alloc, {})
        self.assertEqual(out["positions"]["QB"]["waiver_value"], 29)
        self.assertEqual({k: out["players"][k]["vorp"] for k in ("q1", "q2", "q9")}, {"q1": 0, "q2": 0, "q9": 0})
        # The modeled line (no league) keeps the waiver below the starters.
        base = ref.allocate(ref.League(teams=8, slots={"QB": 1, "RB": 0, "WR": 0, "TE": 0}, flex=0, bench=2),
                            {"QB": keys, "RB": [], "WR": [], "TE": []}, dict(nat))
        self.assertNotIn("replacement", base["QB"])
