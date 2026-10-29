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
