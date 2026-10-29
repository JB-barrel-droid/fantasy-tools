"""Two bench levels on two real leagues, pinned (JEG-1188, Codex review of #1105).

Fixtures: tests/fixtures/league_levels/{uso,charlotte}.json, built by
tools/build_league_level_fixtures.py from Yahoo rosters pulled 2026-10-29
(Flaim get_roster, read only; Yahoo team ids, no team or owner names) and the
repo's value inputs frozen at build time (half PPR, 12 teams, 1QB, current
week). Every number below is exact for those frozen inputs; no tolerances.

  USO        QB1 RB2 WR3 TE1 W/R/T1 K1 DEF1 BN5, no IR slot.
  Charlotte  QB1 RB2 WR2 TE1 W/R/T1 K1 DEF1 BN6 IR1.

Checks:
  * accounting: every roster spot is counted once (starting, BN, IR, K/DEF,
    empty), and Charlotte's market count of 76 is the 65 valued players on
    its 72 bench seats plus the 11 in IR slots, which the market level now
    leaves out of active depth;
  * completeness: the real leagues pass; a missing team, an empty team, a
    partial roster, a player on two teams, an unmatched paste, an unknown
    or old roster date each fail closed (JS and Python agree on every case);
  * the no-league baseline: today's engine gives the pre-JEG-1188 engine's
    allocation and every player's DDF Value (stored in the fixture);
  * JS engine against the spec reference, every leaf, with no league and at
    both levels, on both leagues;
  * the ddf replacement line is the best free agent in the projected-points
    order; the market depth plus IR equals the league's rostered players at
    the position; starters never count a FLEX or superflex seat twice;
  * a sweep over 8/10/12/14 teams, 1QB/2QB/superflex, 2WR/3WR and one or two
    FLEX seats, plus a source missing half its players: the same invariants
    and JS = spec at both levels.
"""
from __future__ import annotations

import dataclasses
import itertools
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from lib import roster_convention as rc  # noqa: E402
from tests.test_league_bench_levels import IGNORED, js_call  # noqa: E402
from tests.test_value_pipeline_engine import DRIVER, VALUE_MODEL, _node, diff  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "league_levels"
LEAGUES = ("uso", "charlotte")
POS = ("QB", "RB", "WR", "TE")
SKILL = set(POS)
PARTS = ("allocation", "fill_sets", "sources", "indexed", "rows", "default_ranking")


def load(name: str) -> dict:
    return json.loads((FIX / f"{name}.json").read_text())


def league_keys(doc: dict):
    """(every valued player on a team, the ones in an IR slot)."""
    held, reserve = [], []
    for t in doc["league"]["teams"]:
        for p in t["players"]:
            if p["pos"] in SKILL and p.get("key"):
                held.append(p["key"])
                if rc.is_reserve_slot(p["slot"]):
                    reserve.append(p["key"])
    return sorted(held), sorted(reserve)


def level_extra(doc: dict, level: str | None) -> dict:
    if level is None:
        return {}
    held, reserve = league_keys(doc)
    return {"league_rostered": held, "league_reserve": reserve, "bench_level": level}


def run_js(doc: dict, extra: dict) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(doc, fh)
    cmd = [_node(), str(DRIVER), str(VALUE_MODEL), fh.name, "--variant", "variant_live",
           "--setting", json.dumps(extra)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    Path(fh.name).unlink()
    if proc.returncode != 0:
        raise AssertionError(f"driver failed: {proc.stderr[-2000:]}")
    return json.loads(proc.stdout)


def run_spec(doc: dict, extra: dict) -> dict:
    from spec_reference import value_pipeline as sp
    s = {**doc["setting"], **{k: v for k, v in extra.items() if k != "league_reserve"}}
    setting = sp.Setting.from_fixture(s)
    if extra.get("league_reserve") is not None:
        setting = dataclasses.replace(setting, league_reserve=tuple(extra["league_reserve"]))
    pos_of = {int(k): v["pos"] for k, v in doc["players"].items()}
    sources = {k: {"family": v["family"], "status": v["status"], "values": v["values"]}
               for k, v in doc["inputs"].items()}
    out = sp.run_week(setting, pos_of, sources, doc["included"], lineup=doc["variant_live"]["lineup"],
                      hidden=doc.get("hidden") or None)
    return json.loads(json.dumps(out))


def _vocabulary(res: dict, engine: str) -> dict:
    """Two differences that are only how each engine writes the same thing,
    with or without a league (they predate JEG-1188): the order of a DDF
    entry's source list, and JS naming the moved unfunded budget `amount`."""
    res = json.loads(json.dumps(res))
    for r in res.get("rows", {}).values():
        for v in r.values():
            if isinstance(v, dict) and isinstance(v.get("sources"), list):
                v["sources"] = sorted(v["sources"])
    if engine == "js":
        for src in res.get("sources", {}).values():
            for m in src.get("unfunded_moved") or []:
                if "amount" in m:
                    m["budget"] = m.pop("amount")
    return res


def parity(case, spec: dict, js: dict):
    spec, js = _vocabulary(spec, "spec"), _vocabulary(js, "js")
    for key in PARTS:
        with case.subTest(part=key):
            problems = [d for d in diff(spec[key], js.get(key), key) if not any(i in d for i in IGNORED)]
            case.assertEqual(problems, [], problems[:5])


def ppg_order(res: dict) -> dict:
    """The allocation's order: mean projected points per game, best first, key tiebreak."""
    out = {p: [] for p in POS}
    for k, m in res["mean_ppg"].items():
        p = res["rows"][str(k)]["pos"] if str(k) in res["rows"] else None
        if p in out and m is not None:
            out[p].append((-m, int(k), str(k)))
    return {p: [k for _, _, k in sorted(v)] for p, v in out.items()}


def check_invariants(case, doc: dict, res: dict, level: str, held, reserve):
    s = doc["setting"]
    teams = s["teams"]
    alloc = res["allocation"]
    order = ppg_order(res)
    held_s, res_s = set(held), set(reserve)
    starters_total = sum(alloc[p]["starters"] for p in POS)
    seats = teams * (sum(s["slots"].values()) + s["flex"] + s.get("superflex", 0))
    # No FLEX or superflex seat counted twice: starters fill exactly the starting seats (or every player, if fewer).
    case.assertEqual(starters_total, min(seats, sum(len(order[p]) for p in POS)))
    for p in POS:
        a = alloc[p]
        with case.subTest(level=level, pos=p):
            case.assertEqual(a["starters"], a["dedicated"] + a["superflex"] + a["flex"])
            case.assertEqual(a["rostered"], a["starters"] + a["bench"])
            in_order = [k for k in order[p]]
            free = next((i for i, k in enumerate(in_order) if k not in held_s and k not in res_s), len(in_order))
            n_res = sum(1 for k in in_order if k in res_s)
            n_held = sum(1 for k in in_order if k in held_s and k not in res_s)
            case.assertEqual((a["held"], a["reserve"]), (n_held, n_res))
            if level == "ddf":
                case.assertEqual(a["replacement"], free)
                case.assertEqual(a["bench"], max(0, free - a["starters"]))
                case.assertEqual(a["bench_basis"], "above_replacement")
            else:
                case.assertEqual(a["bench"], max(0, n_held - a["starters"]))
                case.assertEqual(a["replacement"], a["starters"] + a["bench"])
                case.assertEqual(a["bench_basis"], "rostered_depth")
            # Each source's waiver line is its own value at the replacement index.
            for src, info in res["sources"].items():
                pos = info["positions"][p]
                case.assertEqual(pos["replacement"], a["replacement"])


class TestAccounting(unittest.TestCase):
    """Every roster spot counted once; Codex's 17/60, 22/72 and 76/72."""

    def test_every_spot_counted_once(self):
        for name in LEAGUES:
            doc = load(name)
            raw = json.loads(next((FIX / "raw").glob(f"{name}_rosters_*.json")).read_text())
            acct = doc["league"]["accounting"]
            with self.subTest(league=name):
                self.assertEqual(sum(acct["by_kind_and_slot"].values()),
                                 sum(len(t["players"]) for t in raw["teams"]))
                self.assertEqual(acct["unresolved_players"], 0)
                # Bench seats: valued players + K/DEF + empty = configured.
                self.assertEqual(acct["bench_seats_skill_players"] + acct["bench_seats_k_def"]
                                 + acct["bench_seats_empty"], acct["bench_seats_configured"])

    def test_uso(self):
        acct = load("uso")["league"]["accounting"]
        # 60 seats; 61 valued players on BN because one team left its QB slot empty and carries a sixth BN player.
        self.assertEqual((acct["bench_seats_configured"], acct["bench_seats_skill_players"]), (60, 61))
        self.assertEqual(acct["starting_skill_slots_configured"] - acct["starting_skill_slots_filled"], 1)
        self.assertEqual((acct["reserve_seats_configured"], acct["k_def_players"]), (0, 24))

    def test_charlotte(self):
        acct = load("charlotte")["league"]["accounting"]
        # 72 seats = 65 valued players + 3 K/DEF (two second defenses, one second kicker) + 4 empty; 11 IR slots used.
        self.assertEqual((acct["bench_seats_configured"], acct["bench_seats_skill_players"],
                          acct["bench_seats_k_def"], acct["bench_seats_empty"]), (72, 65, 3, 4))
        self.assertEqual((acct["reserve_seats_configured"], acct["reserve_seats_used"]), (12, 11))

    def test_charlotte_market_76_was_bench_plus_ir(self):
        """9614452 counted IR players as depth: market bench 76 = 65 + 11. With
        the IR slots passed as reserve, active depth beyond the modeled
        starters is 65, the valued players on bench seats."""
        doc = load("charlotte")
        held, reserve = league_keys(doc)
        with_ir = run_spec(doc, {"league_rostered": held, "bench_level": "market"})
        without = run_spec(doc, level_extra(doc, "market"))
        self.assertEqual(sum(with_ir["allocation"][p]["bench"] for p in POS), 76)
        self.assertEqual(sum(without["allocation"][p]["bench"] for p in POS), 65)
        self.assertEqual(sum(without["allocation"][p]["reserve"] for p in POS), 11)


def completeness_cases(doc: dict):
    now = doc_now(doc)
    teams = [{"id": t["id"], "unresolved": 0, "loaded_at": now,
              "players": [{"key": p["key"], "slot": p["slot"]} for p in t["players"]
                          if p["pos"] in SKILL and p.get("key")]} for t in doc["league"]["teams"]]
    start = sum(doc["setting"]["slots"].values()) + doc["setting"]["flex"]
    day = 24 * 3600 * 1000

    def edit(fn):
        tt = json.loads(json.dumps(teams))
        fn(tt)
        return tt
    yield "complete", 12, teams, []
    yield "missing team", 12, teams[:-1], ["team_count"]
    yield "empty team", 12, edit(lambda tt: tt[3].update(players=[])), ["empty_team", "short_roster"]
    yield "partial roster", 12, edit(lambda tt: tt[5].update(players=tt[5]["players"][:start - 1])), ["short_roster"]
    yield "player on two teams", 12, edit(lambda tt: tt[1]["players"].append(dict(tt[0]["players"][0]))), \
        ["duplicate_owner"]
    yield "unmatched paste", 12, edit(lambda tt: tt[7].update(unresolved=2)), ["unresolved"]
    yield "match count unknown", 12, edit(lambda tt: tt[7].update(unresolved=None)), ["unresolved"]
    yield "no roster date", 12, edit(lambda tt: tt[2].update(loaded_at=None)), ["no_timestamp"]
    yield "roster eight days old", 12, edit(lambda tt: tt[9].update(loaded_at=now - 8 * day)), ["stale"]
    yield "roster six days old", 12, edit(lambda tt: tt[9].update(loaded_at=now - 6 * day)), []


def doc_now(doc: dict) -> int:
    import datetime as dt
    raw = json.loads(next((FIX / "raw").glob("*_rosters_*.json")).read_text())
    return int(dt.datetime.fromisoformat(raw["fetched"].replace("Z", "+00:00")).timestamp() * 1000)


class TestCompleteness(unittest.TestCase):
    def test_cases_fail_closed_in_python_and_js(self):
        for name in LEAGUES:
            doc = load(name)
            start = sum(doc["setting"]["slots"].values()) + doc["setting"]["flex"]
            now = doc_now(doc)
            for label, expected, teams, reasons in completeness_cases(doc):
                with self.subTest(league=name, case=label):
                    py = rc.league_completeness(expected, start, teams, now)
                    js = js_call("leagueCompleteness", {
                        "teamsExpected": expected, "startingSlotsPerTeam": start, "now": now,
                        "teams": [{"id": t["id"], "players": t["players"], "unresolved": t["unresolved"],
                                   "loadedAt": t["loaded_at"]} for t in teams]})
                    self.assertEqual(py["reasons"], reasons)
                    self.assertEqual(js, py)
                    self.assertEqual(py["ok"], not reasons)

    def test_complete_league_gives_the_level_keys(self):
        doc = load("charlotte")
        teams = next(c for c in completeness_cases(doc) if c[0] == "complete")[2]
        got = rc.league_completeness(12, 7, teams, doc_now(doc))
        held, reserve = league_keys(doc)
        self.assertEqual((got["rostered"], got["reserve"]), (held, reserve))
        self.assertEqual(len(reserve), 11)


class TestRealLeagues(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _node()
        cls.res = {}
        for name in LEAGUES:
            doc = load(name)
            for level in (None, "ddf", "market"):
                extra = level_extra(doc, level)
                cls.res[name, level] = (run_spec(doc, extra), run_js(doc, extra))

    def test_no_league_baseline_unchanged(self):
        for name in LEAGUES:
            base = load(name)["baseline_no_league"]
            for engine, res in zip(("spec", "js"), self.res[name, None]):
                with self.subTest(league=name, engine=engine):
                    self.assertEqual(json.loads(json.dumps(res["allocation"])), base["allocation"])
                    got = {k: (None if r["ddf_blended"]["value"] is None else round(r["ddf_blended"]["value"], 9))
                           for k, r in res["rows"].items()}
                    self.assertEqual(got, base["ddf_value"])

    def test_js_matches_spec_reference(self):
        for (name, level), (spec, js) in self.res.items():
            with self.subTest(league=name, level=level):
                parity(self, spec, js)

    def test_level_invariants(self):
        for name in LEAGUES:
            doc = load(name)
            held, reserve = league_keys(doc)
            for level in ("ddf", "market"):
                for engine, res in zip(("spec", "js"), self.res[name, level]):
                    with self.subTest(league=name, level=level, engine=engine):
                        check_invariants(self, doc, res, level, held, reserve)

    def test_pinned_counts(self):
        """The three counts, kept apart (Codex: 17 vs 60 and 22 vs 72 are
        above-replacement counts, not bench seats)."""
        want = {
            ("uso", "ddf"): PINNED["uso_ddf"], ("uso", "market"): PINNED["uso_market"],
            ("charlotte", "ddf"): PINNED["cha_ddf"], ("charlotte", "market"): PINNED["cha_market"],
        }
        for (name, level), counts in want.items():
            alloc = self.res[name, level][0]["allocation"]
            with self.subTest(league=name, level=level):
                self.assertEqual({p: (alloc[p]["bench"], alloc[p]["held"], alloc[p]["reserve"]) for p in POS}, counts)


# (bench, held, reserve) per position, from the frozen inputs. ddf bench =
# players above the best free agent beyond the starters; market bench =
# active players beyond the modeled starters; held = active players at the
# position; reserve = players in IR slots.
PINNED = {
    # USO: 17 above replacement, 60 active beyond starters (= its 60 seats; 61 sit on BN, one QB slot is empty).
    "uso_ddf": {"QB": (1, 18, 0), "RB": (5, 52, 0), "WR": (5, 66, 0), "TE": (6, 20, 0)},
    "uso_market": {"QB": (6, 18, 0), "RB": (17, 52, 0), "WR": (29, 66, 0), "TE": (8, 20, 0)},
    # Charlotte: 22 above replacement, 65 active beyond starters (65 valued players on its 72 seats), 11 in IR.
    "cha_ddf": {"QB": (4, 20, 1), "RB": (6, 56, 3), "WR": (8, 54, 6), "TE": (4, 19, 1)},
    "cha_market": {"QB": (8, 20, 1), "RB": (27, 56, 3), "WR": (23, 54, 6), "TE": (7, 19, 1)},
}


SWEEP_TEAMS = (8, 10, 12, 14)
SWEEP_QB = {"1QB": ({"QB": 1}, 0), "2QB": ({"QB": 2}, 0), "SF": ({"QB": 1}, 1)}
SWEEP_WR = (2, 3)
SWEEP_FLEX = (1, 2)


class TestSweep(unittest.TestCase):
    """Charlotte's rosters and inputs under other league shapes. The roster
    set stays Charlotte's, so the levels see a league whose depth does not
    match the shape; the rules must still hold exactly, in both engines."""

    def test_shapes(self):
        _node()
        doc = load("charlotte")
        held, reserve = league_keys(doc)
        for teams, (qb, (qslots, sf)), wr, flex in itertools.product(SWEEP_TEAMS, SWEEP_QB.items(), SWEEP_WR, SWEEP_FLEX):
            d = json.loads(json.dumps(doc))
            d["setting"].update(teams=teams, superflex=sf, flex=flex,
                                slots={"QB": qslots["QB"], "RB": 2, "WR": wr, "TE": 1})
            for level in ("ddf", "market"):
                extra = level_extra(d, level)
                spec, js = run_spec(d, extra), run_js(d, extra)
                with self.subTest(teams=teams, qb=qb, wr=wr, flex=flex, level=level):
                    check_invariants(self, d, spec, level, held, reserve)
                    parity(self, spec, js)

    def test_source_missing_half_its_players(self):
        _node()
        doc = load("charlotte")
        held, reserve = league_keys(doc)
        proj = next(k for k, v in doc["inputs"].items() if v["family"] == "projection")
        vals = doc["inputs"][proj]["values"]
        doc["inputs"][proj]["values"] = {k: v for i, (k, v) in enumerate(sorted(vals.items())) if i % 2}
        for level in (None, "ddf", "market"):
            extra = level_extra(doc, level)
            spec, js = run_spec(doc, extra), run_js(doc, extra)
            with self.subTest(level=level):
                parity(self, spec, js)
                if level:
                    check_invariants(self, doc, spec, level, held, reserve)


if __name__ == "__main__":
    unittest.main()
