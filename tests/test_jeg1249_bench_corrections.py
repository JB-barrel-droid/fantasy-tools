"""Codex's two release-blocking probes on #1105, as output tests (JEG-1249).

1. Replacement identity across disagreeing sources. 8 teams, QB1. Q1..Q10
   are held; Q11 is the best free QB in the common projected-points order
   (mean of the two projections). The sources disagree on him: espn 40, p2
   18. The ddf level prices each source's waiver at Q11's own value in that
   source, so the waivers are 40 and 18 and Q11 is worth nothing over
   replacement. On 54279710 the engine used one index (10) in each source's
   own order instead: waivers 30 (held Q10 in espn) and 28 (Q12 in p2), and
   Q11 kept DDF Value. A source with no row for Q11 uses its own best free
   QB.

2. Market depth is what the league holds. QB1 RB2 WR2 TE1 FLEX1 SF1 BN2 at
   8/10/12/14 teams; each team holds 1 QB, 4 RB, 4 WR, 1 TE (80/100/120/140
   players). Market rostered must be 80/100/120/140 and bench 16/20/24/28.
   On 54279710 the theoretical starters took extra QBs and TEs the league
   doesn't hold: 93/116/140/163 rostered, 29/36/44/51 bench.

Both checks run the JS engine (value-model.js under node), the spec
reference (pipelines/spec_reference) and the Python reference
(pipelines/value_reference: allocate and the source lines). These are
synthetic edge fixtures, not league observations.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from tests.test_value_pipeline_engine import DRIVER, VALUE_MODEL, _node  # noqa: E402

POS = ("QB", "RB", "WR", "TE")


def run_js(doc: dict, extra: dict) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(doc, fh)
    try:
        proc = subprocess.run([_node(), str(DRIVER), str(VALUE_MODEL), fh.name, "--setting", json.dumps(extra)],
                              capture_output=True, text=True, timeout=120)
    finally:
        Path(fh.name).unlink()
    if proc.returncode != 0:
        raise AssertionError(proc.stderr[-2000:])
    return json.loads(proc.stdout)


def run_spec(doc: dict, extra: dict) -> dict:
    from spec_reference import value_pipeline as sp
    setting = sp.Setting.from_fixture({**doc["setting"], **extra})
    pos_of = {int(k): v["pos"] for k, v in doc["players"].items()}
    sources = {s: {"family": v["family"], "status": v["status"], "values": {int(k): x for k, x in v["values"].items()}}
               for s, v in doc["inputs"].items()}
    inc = [s for s, v in sources.items() if v["status"] == "included"]
    return json.loads(json.dumps(sp.run_week(setting, pos_of, sources, inc)))


def ref_league(doc: dict, extra: dict):
    import value_reference as ref
    s = doc["setting"]
    return ref.League(teams=s["teams"], slots=s["slots"], flex=s["flex"], superflex=s["superflex"],
                      bench=s["bench_per_team"], league_rostered=tuple(extra["league_rostered"]),
                      bench_level=extra["bench_level"])


def mean_order(doc: dict) -> tuple[dict, dict]:
    """The allocation's order: mean projected value, best first, key tiebreak."""
    proj = [v["values"] for v in doc["inputs"].values() if v["family"] == "projection"]
    score = {}
    for k in doc["players"]:
        xs = [p[k] for p in proj if k in p]
        if xs:
            score[k] = sum(xs) / len(xs)
    order = {p: sorted((k for k in score if doc["players"][k]["pos"] == p), key=lambda k: (-score[k], int(k)))
             for p in POS}
    return order, score


# ---------------------------------------------------------------- probe 1

def q11_doc(drop_q11_from_p2: bool = False) -> dict:
    espn = {str(i): 60 - 2 * (i - 1) for i in range(1, 10)}   # Q1..Q9: 60..44
    p2 = dict(espn)
    espn.update({"10": 30, "11": 40, "12": 20, "13": 15, "14": 10})
    p2.update({"10": 30, "11": 18, "12": 28, "13": 15, "14": 10})
    if drop_q11_from_p2:
        del p2["11"]
    return {"setting": {"teams": 8, "slots": {"QB": 1, "RB": 0, "WR": 0, "TE": 0}, "flex": 0,
                        "flex_eligible": ["RB", "WR", "TE"], "superflex": 0, "bench_per_team": 2,
                        "bench_share": 0.15},
            "players": {str(i): {"name": f"Q{i}", "pos": "QB"} for i in range(1, 15)},
            "inputs": {"espn": {"family": "projection", "status": "included", "values": espn},
                       "p2": {"family": "projection", "status": "included", "values": p2}}}


Q11_HELD = [str(i) for i in range(1, 11)]
DDF = {"league_rostered": Q11_HELD, "bench_level": "ddf"}


class TestReplacementIdentity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _node()
        cls.doc = q11_doc()
        cls.js, cls.spec = run_js(cls.doc, DDF), run_spec(cls.doc, DDF)

    def test_fixture_is_codexs_probe(self):
        order, _ = mean_order(self.doc)
        self.assertEqual(order["QB"][10], "11", "Q11 is the best free QB in the common order")

    def test_waiver_is_q11_in_every_source(self):
        for name, res in (("js", self.js), ("spec", self.spec)):
            self.assertEqual(res["allocation"]["QB"]["replacement_key"], "11", name)
            got = {s: res["sources"][s]["positions"]["QB"]["waiver_value"] for s in ("espn", "p2")}
            self.assertEqual(got, {"espn": 40, "p2": 18}, name)

    def test_q11_is_worth_nothing_over_replacement(self):
        for name, res in (("js", self.js), ("spec", self.spec)):
            # Codex's 24.139: the projection blend (no chart in this probe).
            self.assertEqual(res["rows"]["11"]["ddf_projections"]["value"], 0, name)
            self.assertEqual(res["rows"]["11"]["adjusted"], {"espn": 0, "p2": 0}, name)
            for s in ("espn", "p2"):
                self.assertEqual(res["sources"][s]["players"]["11"]["vorp"], 0, (name, s))

    def test_held_player_below_q11_in_a_source_is_zero_there(self):
        # Q10: 30 in espn (below Q11's 40) is worth 0 there; 30 in p2 (above 18) is worth 12.
        for name, res in (("js", self.js), ("spec", self.spec)):
            self.assertEqual(res["sources"]["espn"]["players"]["10"]["vorp"], 0, name)
            self.assertEqual(res["sources"]["p2"]["players"]["10"]["vorp"], 12, name)

    def test_python_reference_source_lines(self):
        import value_reference as ref
        order, score = mean_order(self.doc)
        alloc = ref.allocate(ref_league(self.doc, DDF), order, score)
        self.assertEqual(alloc["QB"]["replacement_key"], "11")
        pos_of = {k: "QB" for k in self.doc["players"]}
        for s, want in (("espn", 40), ("p2", 18)):
            src = ref.SourceInput(s, "projection", dict(self.doc["inputs"][s]["values"]))
            out = ref._source_lines(src, pos_of, alloc, {}, league_rostered=tuple(Q11_HELD))
            self.assertEqual(out["positions"]["QB"]["waiver_value"], want, s)
            self.assertEqual(out["players"]["11"]["vorp"], 0, s)

    def test_source_without_q11_uses_its_own_best_free_player(self):
        # p2 has no row for Q11: its waiver is its best free QB, Q12 (28).
        doc = q11_doc(drop_q11_from_p2=True)
        js, spec = run_js(doc, DDF), run_spec(doc, DDF)
        for name, res in (("js", js), ("spec", spec)):
            got = {s: res["sources"][s]["positions"]["QB"]["waiver_value"] for s in ("espn", "p2")}
            self.assertEqual(got, {"espn": 40, "p2": 28}, name)
        import value_reference as ref
        order, score = mean_order(doc)
        alloc = ref.allocate(ref_league(doc, DDF), order, score)
        src = ref.SourceInput("p2", "projection", dict(doc["inputs"]["p2"]["values"]))
        out = ref._source_lines(src, {k: "QB" for k in doc["players"]}, alloc, {}, league_rostered=tuple(Q11_HELD))
        self.assertEqual(out["positions"]["QB"]["waiver_value"], 28)

    def test_every_row_held_is_insufficient_coverage(self):
        held = [str(i) for i in range(1, 15)]
        extra = {"league_rostered": held, "bench_level": "ddf"}
        for name, res in (("js", run_js(self.doc, extra)), ("spec", run_spec(self.doc, extra))):
            self.assertIsNone(res["allocation"]["QB"]["replacement_key"], name)
            for s in ("espn", "p2"):
                self.assertEqual(res["sources"][s]["positions"]["QB"]["method"], "insufficient_coverage", (name, s))


# ---------------------------------------------------------------- probe 2

def capacity_doc(teams: int) -> tuple[dict, list]:
    players, values, held = {}, {}, []
    for p, base, n_held in (("QB", 1000, teams), ("RB", 2000, 4 * teams), ("WR", 3000, 4 * teams),
                            ("TE", 4000, teams)):
        for i in range(100):
            k = str(base + i)
            players[k] = {"name": f"{p}{i}", "pos": p}
            values[k] = 100 - i
            if i < n_held:
                held.append(k)
    doc = {"setting": {"teams": teams, "slots": {"QB": 1, "RB": 2, "WR": 2, "TE": 1}, "flex": 1,
                       "flex_eligible": ["RB", "WR", "TE"], "superflex": 1, "bench_per_team": 2,
                       "bench_share": 0.15},
           "players": players,
           "inputs": {"espn": {"family": "projection", "status": "included", "values": values}}}
    return doc, held


class TestMarketHeldDepth(unittest.TestCase):
    def test_complete_capacity_rosters(self):
        _node()
        import value_reference as ref
        for teams in (8, 10, 12, 14):
            doc, held = capacity_doc(teams)
            extra = {"league_rostered": held, "bench_level": "market"}
            order, score = mean_order(doc)
            ref_alloc = ref.allocate(ref_league(doc, extra), order, score)
            for name, alloc in (("js", run_js(doc, extra)["allocation"]), ("spec", run_spec(doc, extra)["allocation"]),
                                ("ref", ref_alloc)):
                with self.subTest(teams=teams, engine=name):
                    self.assertEqual(sum(alloc[p]["rostered"] for p in POS), 10 * teams)
                    self.assertEqual(sum(alloc[p]["bench"] for p in POS), 2 * teams)
                    self.assertEqual({p: alloc[p]["rostered"] for p in POS},
                                     {"QB": teams, "RB": 4 * teams, "WR": 4 * teams, "TE": teams})
                    self.assertEqual({p: alloc[p]["held"] for p in POS},
                                     {"QB": teams, "RB": 4 * teams, "WR": 4 * teams, "TE": teams})
                    self.assertEqual(sum(alloc[p]["starters"] for p in POS), 8 * teams)
                    # The theoretical demand is kept, labelled, and never counted as players.
                    self.assertEqual(sum(alloc[p]["modeled_starters"] for p in POS), 8 * teams)
                    self.assertGreater(alloc["QB"]["modeled_starters"], alloc["QB"]["starters"])

    def test_short_league_reports_unfilled_seats(self):
        # Half the QBs: four dedicated QB seats go unfilled, never invented.
        _node()
        doc, held = capacity_doc(8)
        held = [k for k in held if not ("1004" <= k <= "1007")]
        extra = {"league_rostered": held, "bench_level": "market"}
        for name, res in (("js", run_js(doc, extra)), ("spec", run_spec(doc, extra))):
            alloc = res["allocation"]
            with self.subTest(engine=name):
                self.assertEqual(alloc["QB"]["dedicated"], 4)
                self.assertEqual(sum(alloc[p]["rostered"] for p in POS), 76)
                self.assertEqual(sum(alloc[p]["modeled_starters"] for p in POS)
                                 - sum(alloc[p]["starters"] for p in POS), 4)


if __name__ == "__main__":
    unittest.main()
