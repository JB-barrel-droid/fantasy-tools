"""JEG-1047: a projection source's waiver line is a 7-player band, not one player.

Jeremy, 2026-10-29 (JEG-1047, option A): average the 7 players around the
first non-rostered seat, with the bar that a 1 PPG change to the waiver-line
player moves no other player at that position by more than 1.0 point in that
source's Adjusted value. Research: docs/research/jeg1047-waiver-line.md.

Fails without the fix: under the one-player rule the same perturbation moves
another player by up to 3.2 points (Razzball QB, 8 teams, on the week 8
build), and `test_band_beats_one_player_rule` compares both rules on the same
cases.

JEG-1244 (Codex review of #1077): the zero-seat case (no team starts or
benches the position, a non-empty work list) crashed the Python and spec
references while the engine averaged the top 4. VP-2.3 settles it: the band is
clipped to the work list, so the zero seat is values[0..3]. `EndToEndTest`
runs the production engine (`value-model.js` through `runValuePipeline`), the
Python reference and the spec reference on the same fixtures, including zero
seats, empty and short lists, and checks each waiver line against the VP-2.3
rule written out here. The tolerance test covers the full 12-setting grid
(3 scorings x 8, 10, 12, 14 teams), with the league's slots held fixed
(Jeremy, 2026-10-29, JEG-1244 option A).
"""
from __future__ import annotations

import copy
import json
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO / "pipelines" / "lib"))

import value_reference as vr  # noqa: E402
from spec_reference import worked_example as spec_we  # noqa: E402
from lib.roster_convention import (  # noqa: E402
    WAIVER_BAND_HALF_WIDTH,
    waiver_band_line,
    waiver_line,
)

TOLERANCE = 1.0
PROJECTIONS = ("espn", "cbsros", "razzball")
# JEG-1244: the full grid the research and the tolerance name (3 scorings x
# 4 team counts, default roster). The mutation check keeps the default
# setting and the worst one-player setting before the fix, for time.
CELLS = tuple((sc, t) for sc in vr.SCORINGS for t in vr.TEAM_COUNTS)
MUTATION_CELLS = (("ppr", 12), ("standard", 8))
FIXTURE = REPO / "tests" / "fixtures" / "value_pipeline_worked_example.json"
VALUE_MODEL = REPO / "app" / "trade-value-chart" / "assets" / "value-model.js"
DRIVER = REPO / "tests" / "value_pipeline_driver.js"


class BandMathTest(unittest.TestCase):
    def test_band_is_mean_of_seven_around_seat(self):
        values = [20.0, 18, 16, 14, 12, 10, 8, 6, 4, 2, 1]
        self.assertEqual(WAIVER_BAND_HALF_WIDTH, 3)
        # seat 5 (value 10): window 2..8 = 16,14,12,10,8,6,4
        self.assertAlmostEqual(waiver_band_line(values, 5), sum([16, 14, 12, 10, 8, 6, 4]) / 7)
        # seat 9 (value 2), clipped at the bottom of the list: 8,6,4,2,1
        self.assertAlmostEqual(waiver_band_line(values, 9), sum([8, 6, 4, 2, 1]) / 5)

    def test_short_list_keeps_last_value(self):
        self.assertEqual(waiver_band_line([9.0, 8.0], 2), waiver_line([9.0, 8.0], 2))
        self.assertEqual(waiver_band_line([9.0, 8.0], 5), 8.0)
        self.assertIsNone(waiver_band_line([], 3))
        self.assertIsNone(waiver_band_line([], 0))
        self.assertIsNone(waiver_band_line([1.0], -1))

    def test_zero_seat_is_band_clipped_at_the_top(self):
        """JEG-1244: VP-2.3 clips the band to the work list, so a zero seat
        averages values[0..3] (what the engine already did)."""
        values = [20.0, 18, 16, 14, 12, 10]
        self.assertAlmostEqual(waiver_band_line(values, 0), sum([20, 18, 16, 14]) / 4)
        self.assertAlmostEqual(waiver_band_line([5.0, 3.0], 0), 4.0)
        self.assertEqual(waiver_band_line([7.0], 0), 7.0)

    def test_one_player_moves_band_by_at_most_a_seventh(self):
        values = [20.0, 18, 16, 14, 12, 10, 8, 6, 4, 2, 1]
        base = waiver_band_line(values, 5)
        bumped = sorted(values[:5] + [values[5] + 1.0] + values[6:], reverse=True)
        self.assertLessEqual(abs(waiver_band_line(bumped, 5) - base), 1.0 / 7 + 1e-12)
        self.assertGreater(abs(waiver_line(bumped, 5) - waiver_line(values, 5)), 1.0 / 7)

    def test_js_twin_matches(self):
        """roster-convention.js's twin. The engine's own copy is checked by
        EndToEndTest, through runValuePipeline."""
        rng = random.Random(1047)
        cases = []
        for _ in range(200):
            n = rng.randint(0, 40)
            vals = sorted((round(rng.uniform(0, 30), 3) for _ in range(rng.randint(0, 45))), reverse=True)
            cases.append({"values": vals, "rostered": n})
        js = (
            "const RC=require(process.argv[1]).RosterConvention;"
            "const cases=JSON.parse(require('fs').readFileSync(0,'utf8'));"
            "process.stdout.write(JSON.stringify(cases.map(c=>RC.waiverBandLine(c.values,c.rostered))));"
        )
        out = subprocess.run(
            ["node", "-e", js, str(REPO / "app" / "trade-value-chart" / "assets" / "roster-convention.js")],
            input=json.dumps(cases), capture_output=True, text=True, check=True,
        )
        got = json.loads(out.stdout)
        for c, g in zip(cases, got):
            want = waiver_band_line(c["values"], c["rostered"])
            if want is None:
                self.assertIsNone(g, c)
            else:
                self.assertAlmostEqual(g, want, places=12, msg=c)


def _node():
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node not installed")
    return node


def _contract_line(values: list, n: int):
    """VP-2.3 as written, independent of every implementation: values sorted
    best first; past the rostered count, the mean of indexes n-3 .. n+3
    clipped to the list; else the last value; empty, no line."""
    if len(values) > n:
        window = values[max(0, n - 3):min(len(values), n + 4)]
        return sum(window) / len(window), "band"
    if values:
        return values[-1], "insufficient_coverage"
    return None, "no_players"


def _variant(fx: dict, setting: dict, keep: dict) -> dict:
    """fx with setting changes and, per projection source and position, only
    the first `keep[src][pos]` players of that source's own order."""
    out = copy.deepcopy(fx)
    out["setting"].update(setting)
    pos_of = {k: p["pos"] for k, p in fx["players"].items()}
    for src, per_pos in keep.items():
        vals = fx["inputs"][src]["values"]
        kept = {}
        for pos in vr.POSITIONS:
            order = sorted((k for k in vals if pos_of[k] == pos), key=lambda k: (-vals[k], int(k)))
            n = per_pos.get(pos, len(order))
            kept.update({k: vals[k] for k in order[:n]})
        out["inputs"][src]["values"] = kept
    return out


def _run_engine(doc: dict, model: Path = VALUE_MODEL) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        json.dump(doc, tmp)
    proc = subprocess.run([_node(), str(DRIVER), str(model), tmp.name], capture_output=True, text=True,
                          timeout=60)
    Path(tmp.name).unlink()
    if proc.returncode != 0:
        raise AssertionError(f"engine driver failed: {proc.stderr[-1500:]}")
    return json.loads(proc.stdout)


def _run_python(doc: dict) -> dict:
    s = doc["setting"]
    league = vr.League(teams=s["teams"], slots=dict(s["slots"]), flex=s["flex"], superflex=s["superflex"],
                       bench=s["bench_per_team"], bench_share=s["bench_share"],
                       flex_eligible=tuple(s["flex_eligible"]), seat_sigma=s.get("seat_sigma"))
    sources = {k: vr.SourceInput(k, v["family"], {int(i): float(x) for i, x in v["values"].items()})
               for k, v in doc["inputs"].items()}
    pos_of = {int(i): p["pos"] for i, p in doc["players"].items()}
    included = [k for k, v in doc["inputs"].items() if v["status"] == "included"]
    return vr.run_pipeline(league, sources, pos_of, included)


def _lines(res: dict) -> dict:
    """{(src, pos): (rostered, method, waiver, starter_line)} and
    {(src, player): adjusted}, the same shape for all three outputs."""
    lines, adjusted = {}, {}
    for src, o in res["sources"].items():
        for pos, p in o["positions"].items():
            lines[(src, pos)] = (p.get("rostered"), p.get("method"), p.get("waiver_value"),
                                 p.get("starter_line"))
        for k, r in (o.get("players") or {}).items():
            adjusted[(src, str(k))] = r.get("adjusted")
    return {"lines": lines, "adjusted": adjusted}


def _close(a, b, tol=1e-9):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(a)))


def _edge_cases(fx: dict) -> list:
    """Named edge fixtures plus a seeded sweep. flex 0 keeps every
    implementation on the same allocation rule for any slot shape."""
    base = {"flex": 0, "superflex": 0}
    cases = [
        ("zero_seat", _variant(fx, {**base, "slots": {"QB": 1, "RB": 1, "WR": 1, "TE": 0},
                                    "bench_per_team": 0}, {})),
        ("zero_seat_short_list", _variant(fx, {**base, "slots": {"QB": 1, "RB": 1, "WR": 1, "TE": 0},
                                               "bench_per_team": 0}, {"p1": {"TE": 2}, "p2": {"TE": 1}})),
        ("empty_list", _variant(fx, base, {"p1": {"TE": 0}, "p2": {"QB": 0}})),
        ("short_list", _variant(fx, base, {"p1": {"RB": 2, "WR": 3}, "p2": {"TE": 1}})),
        ("exact_fit", _variant(fx, {**base, "slots": {"QB": 1, "RB": 1, "WR": 1, "TE": 1},
                                    "bench_per_team": 0}, {"p1": {"QB": 2, "RB": 2}})),
        ("one_past_seat", _variant(fx, {**base, "slots": {"QB": 1, "RB": 1, "WR": 1, "TE": 1},
                                        "bench_per_team": 0}, {"p1": {"QB": 3, "RB": 3}})),
    ]
    rng = random.Random(1244)
    for i in range(24):
        slots = {p: rng.randint(0, 2) for p in vr.POSITIONS}
        if not any(slots.values()):
            slots["RB"] = 1
        keep = {src: {p: rng.randint(0, 9) for p in vr.POSITIONS if rng.random() < 0.6}
                for src in ("p1", "p2")}
        cases.append((f"sweep_{i}", _variant(fx, {**base, "teams": rng.randint(1, 3), "slots": slots,
                                                  "bench_per_team": rng.randint(0, 3)}, keep)))
    return cases


class EndToEndTest(unittest.TestCase):
    """JEG-1244: the production engine (`vpWaiverBand` via runValuePipeline),
    the Python reference and the spec reference give the same waiver line,
    starter line, method and Adjusted value on zero-seat, empty and short
    lists, and each projection line is VP-2.3's."""

    @classmethod
    def setUpClass(cls):
        _node()
        cls.fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.cases = _edge_cases(cls.fx)

    def _mismatches(self, model: Path = VALUE_MODEL) -> tuple[list, dict]:
        bad, seen = [], {"zero_seat": 0, "band": 0, "insufficient_coverage": 0, "no_players": 0}
        for name, doc in self.cases:
            outs = {"engine": _lines(_run_engine(doc, model)), "python": _lines(_run_python(doc)),
                    "spec": _lines(spec_we.run_fixture(doc))}
            eng = outs["engine"]
            for other in ("python", "spec"):
                for kind in ("lines", "adjusted"):
                    for key, want in eng[kind].items():
                        got = outs[other][kind].get(key)
                        same = (all(_close(a, b) for a, b in zip(want, got)) if kind == "lines" and got
                                else _close(want, got, 1e-7))
                        if not same:
                            bad.append(f"{name} {other} {kind} {key}: engine {want} vs {got}")
                    if set(eng[kind]) != set(outs[other][kind]):
                        bad.append(f"{name} {other} {kind}: key sets differ")
            pos_of = {k: p["pos"] for k, p in doc["players"].items()}
            for src, inp in doc["inputs"].items():
                if inp["family"] != "projection":
                    continue
                for pos in vr.POSITIONS:
                    vals = sorted((float(x) for k, x in inp["values"].items() if pos_of[k] == pos), reverse=True)
                    rostered, method, waiver, _ = eng["lines"][(src, pos)]
                    want, kind = _contract_line(vals, rostered)
                    seen[kind] += 1
                    if kind == "band" and rostered == 0:
                        seen["zero_seat"] += 1
                    if not _close(waiver, want):
                        bad.append(f"{name} {src} {pos} N={rostered} n={len(vals)}: engine {waiver}, "
                                   f"VP-2.3 {want}")
                    if kind != "band" and method != kind:
                        bad.append(f"{name} {src} {pos}: method {method}, VP-2.3 {kind}")
        return bad, seen

    def test_engine_and_references_agree_on_edge_cases(self):
        bad, seen = self._mismatches()
        self.assertEqual(bad, [], "\n".join(bad[:40]))
        # The fixtures reach every branch, the zero seat included.
        for kind, n in seen.items():
            self.assertGreater(n, 0, f"no {kind} case in the fixtures: {seen}")

    def test_comparison_fails_on_broken_engines(self):
        """Mutation check: each break of the production helper is caught."""
        src = VALUE_MODEL.read_text(encoding="utf-8")
        mutations = {
            # JEG-1249 integration: the band sits at the line row W (N with no league).
            "one-player line": ('family === "projection" ? vpWaiverBand(work, W) : work[W].native',
                                "work[W].native"),
            "5-player band": ("var VP_WAIVER_BAND_HALF_WIDTH = 3;", "var VP_WAIVER_BAND_HALF_WIDTH = 2;"),
            "zero seat as one player": ("function vpWaiverBand(work, N) {",
                                        "function vpWaiverBand(work, N) {\n    if (N === 0) return work[0].native;"),
        }
        for label, (old, new) in mutations.items():
            self.assertIn(old, src, f"mutation anchor gone: {label}")
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as tmp:
                tmp.write(src.replace(old, new, 1))
            try:
                bad, _ = self._mismatches(Path(tmp.name))
            finally:
                Path(tmp.name).unlink()
            self.assertTrue(bad, f"a broken engine passed: {label}")


class OnePlayerPerturbationTest(unittest.TestCase):
    """A 1 PPG change to the waiver-line player moves no other player at the
    position by more than 1.0 point in that source's Adjusted value, with the
    league's slots and bench seats held as they were.

    Jeremy, 2026-10-29 (JEG-1244, option A): the bar measures the waiver
    line, so the check holds the league allocation fixed. When the perturbed
    player also sits at a flex or bench cutoff by mean projected points, the
    allocation itself can flip (Coker, standard/10, CBS ROS WR: the flex slot
    moves WR to RB and Smith-Njigba moves 2.35). That jump is the slot-filling
    rule's, tracked on its own ticket; `test_only_slot_flips_break_the_bar_
    with_slots_free` keeps it visible and checks nothing else fails."""

    @classmethod
    def setUpClass(cls):
        cls.inp = vr.Inputs.load()

    def _cases(self, cells=CELLS):
        inp = self.inp
        out = []
        for scoring, teams in cells:
            s = vr.Setting(inp, scoring, teams)
            res = s.result()
            for src in PROJECTIONS:
                if src not in res["sources"]:
                    continue
                natives = s.natives(src)
                for pos in vr.POSITIONS:
                    info = res["sources"][src]["positions"].get(pos) or {}
                    n = info.get("rostered")
                    work = sorted(((k, x) for k, x in natives.items() if inp.players[k]["pos"] == pos),
                                  key=lambda t: (-t[1], t[0]))
                    if n is None or len(work) <= n:
                        continue
                    out.append((scoring, teams, src, pos, work[n][0]))
        return out

    def _run(self, scoring, teams, src, pos, replay=None):
        """Adjusted values at `pos` in `src`, and every allocation the run
        made. With `replay`, each allocation call returns the recorded one
        instead (slots and bench seats held). JEG-1335: a run makes its
        allocations through allocation_mix (the fractional-seat mix), so the
        mix is recorded and replayed whole, weights included; allocate calls
        made inside it are not recorded on their own."""
        orig_alloc, orig_mix = vr.allocate, vr.allocation_mix
        made = []
        it = iter(replay) if replay is not None else None
        depth = [0]

        def call(kind, orig, args, kwargs):
            if depth[0]:
                return orig(*args, **kwargs)
            if it is not None:
                got_kind, out = next(it)
                self.assertEqual(got_kind, kind, "allocation calls changed between runs")
                out = copy.deepcopy(out)
            else:
                depth[0] += 1
                try:
                    out = orig(*args, **kwargs)
                finally:
                    depth[0] -= 1
            made.append((kind, copy.deepcopy(out)))
            return out

        vr.allocate = lambda *a, **k: call("allocate", orig_alloc, a, k)
        vr.allocation_mix = lambda *a, **k: call("mix", orig_mix, a, k)
        try:
            rows = vr.Setting(self.inp, scoring, teams).result()["rows"]
        finally:
            vr.allocate, vr.allocation_mix = orig_alloc, orig_mix
        if replay is not None:
            self.assertEqual(len(made), len(replay), "allocation calls changed between runs")
        return {i: (r.get("adjusted") or {}).get(src) for i, r in rows.items() if r["pos"] == pos}, made

    @staticmethod
    def _slots(made):
        """The whole allocations a run used, without the mix weights: a
        perturbation that only reweights the mix has not flipped a slot."""
        return [[a for _w, a in out] if kind == "mix" else out for kind, out in made]

    def _worst(self, scoring, teams, src, pos, key, delta, hold_slots=True):
        """(worst move of another player, whether the free allocation changed)."""
        field = vr.PPG_FIELD[src]
        base, base_alloc = self._run(scoring, teams, src, pos)
        rec = self.inp.players[key][field]
        old = rec[scoring]
        rec[scoring] = max(0.0, old + delta)
        try:
            new, new_alloc = self._run(scoring, teams, src, pos, base_alloc if hold_slots else None)
        finally:
            rec[scoring] = old
        moves = [abs(new[i] - b) for i, b in base.items()
                 if i != key and b is not None and new.get(i) is not None]
        return max(moves, default=0.0), self._slots(new_alloc) != self._slots(base_alloc)

    def test_fringe_player_moves_no_one_more_than_tolerance(self):
        cases = self._cases()
        self.assertGreaterEqual(len(cases), 20, "expected a waiver line at most source/position cells")
        failures = []
        for scoring, teams, src, pos, key in cases:
            for delta in (-1.0, 1.0):
                worst, _ = self._worst(scoring, teams, src, pos, key, delta)
                if worst > TOLERANCE:
                    failures.append(f"{scoring}/{teams} {src} {pos} {key} {delta:+}: {worst:.3f}")
        self.assertEqual(failures, [], "one fringe player repriced the position:\n" + "\n".join(failures))

    def test_only_slot_flips_break_the_bar_with_slots_free(self):
        """With the allocation free, every case over the bar is one where the
        perturbation changed the league's slots or bench seats (the separate
        flex-flip ticket), never the waiver line alone."""
        bad = []
        for scoring, teams, src, pos, key in self._cases():
            for delta in (-1.0, 1.0):
                worst, flipped = self._worst(scoring, teams, src, pos, key, delta, hold_slots=False)
                if worst > TOLERANCE and not flipped:
                    bad.append(f"{scoring}/{teams} {src} {pos} {key} {delta:+}: {worst:.3f}")
        self.assertEqual(bad, [], "over the bar with the slots unchanged:\n" + "\n".join(bad))

    def test_band_beats_one_player_rule(self):
        """Mutation check: with the slots held the same way, the one-player
        rule moves some other player further than the band does and fails the
        bar."""
        cases = self._cases(MUTATION_CELLS)
        band = max(self._worst(*c, d)[0] for c in cases for d in (-1.0, 1.0))
        orig = vr._waiver_value
        vr._waiver_value = lambda src, pos, values, n: values[n]
        try:
            one = max(self._worst(*c, d)[0] for c in cases for d in (-1.0, 1.0))
        finally:
            vr._waiver_value = orig
        self.assertGreater(one, band)
        self.assertGreater(one, TOLERANCE, "the one-player rule should fail the bar on these cells")


if __name__ == "__main__":
    unittest.main()
