"""JEG-1335: the engine's copy of the seat functions equals the helper.

value-model.js must stay one self-contained file (the page, the get-values
and mcp edge functions and the headless check load only it), so it carries
its own copy of the fractional-seat functions of
pipelines/lib/fractional_seats.py (JEG-1334; JS twin fractional-seats.js).
These tests hold the copy equal to the Python helper on random leagues:

- soft selection (the Phi shares that fill n seats), to 1e-12;
- decomposition of fractional counts into weighted whole counts;
- the whole flex-and-bench mix (weights to 1e-12, counts exact), with the
  engine's VORP bench discount against roster_convention.vorp_bench_discount;
- the sigma and prune constants.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "pipelines", REPO / "pipelines" / "lib"):
    sys.path.insert(0, str(p))

import value_reference as VR  # noqa: E402
from lib import fractional_seats as FS  # noqa: E402
from lib import roster_convention as RC  # noqa: E402

HARNESS = REPO / "tests" / "fractional_seats_engine_harness.cjs"
TOL = 1e-12
N_CASES = 200


def _harness(cmd, payload):
    proc = subprocess.run(["node", str(HARNESS), cmd], input=json.dumps(payload),
                          capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise AssertionError(f"harness {cmd} failed: {proc.stderr[:2000]}")
    return json.loads(proc.stdout)


def _league(rng):
    teams = rng.randint(8, 14)
    slots = {"QB": rng.choice((1, 1, 2)), "RB": rng.randint(1, 3), "WR": rng.randint(2, 4), "TE": 1}
    flex, bench = rng.randint(0, 2), rng.randint(3, 8)
    order, score, nxt = {}, {}, 1
    for p in FS.POSITIONS:
        n = teams * (slots[p] + 3) + rng.randint(0, 10)
        top = {"QB": 22, "RB": 20, "WR": 19, "TE": 14}[p]
        vals = sorted((round(rng.uniform(0, top), rng.choice((1, 2, 6))) for _ in range(n)), reverse=True)
        ids = list(range(nxt, nxt + n))
        nxt += n
        order[p] = ids
        score.update(zip(ids, vals))
    sf = rng.random() < 0.2
    return {
        "teams": teams, "dedicated": {p: teams * slots[p] for p in FS.POSITIONS},
        "superflex": {p: (teams if (sf and p == "QB") else 0) for p in FS.POSITIONS},
        "flex_eligible": ["RB", "WR", "TE"], "flex_seats": teams * flex, "bench_seats": teams * bench,
        "order": order, "score": score, "sigma": rng.choice((0.0, 0.3, 0.75, 0.75, 1.0)),
        "soft_bench": rng.random() < 0.8,
    }


class EngineSeatCopy(unittest.TestCase):
    def test_constants(self):
        out = subprocess.run(["node", "-e",
                              "const S=require(process.argv[1]).seatFunctions;"
                              "process.stdout.write(JSON.stringify([S.SEAT_SIGMA,S.SEAT_PRUNE]))",
                              str(REPO / "app" / "trade-value-chart" / "assets" / "value-model.js")],
                             capture_output=True, text=True, timeout=60, check=True)
        self.assertEqual(json.loads(out.stdout), [VR.SEAT_SIGMA, FS.PRUNE])

    def test_soft_select(self):
        rng = random.Random(1335)
        cases = []
        for _ in range(N_CASES):
            k = rng.randint(1, 40)
            sigma = rng.choice((0.0, 0.5, 0.75))
            items = [[rng.choice(FS.POSITIONS), round(rng.uniform(0, 20), 2), sigma] for _ in range(k)]
            cases.append({"items": items, "n": rng.randint(0, k + 2)})
        got = _harness("select", {"cases": cases})
        for c, g in zip(cases, got):
            want = FS.soft_select([tuple(x) for x in c["items"]], c["n"])
            self.assertEqual(set(want), set(g), c)
            for p in want:
                self.assertAlmostEqual(want[p], g[p], delta=TOL)

    def test_decompose(self):
        rng = random.Random(1336)
        fracs = []
        for _ in range(N_CASES):
            parts = {p: rng.uniform(0, 4) for p in FS.POSITIONS}
            tot = sum(parts.values())
            target = round(tot) or 1
            fracs.append({p: v * target / tot for p, v in parts.items()})
        got = _harness("decompose", {"fracs": fracs})
        for f, g in zip(fracs, got):
            want = FS.decompose(f)
            self.assertEqual([c for _w, c in want], [c for _w, c in g], f)
            for (w1, _), (w2, _) in zip(want, g):
                self.assertAlmostEqual(w1, w2, delta=TOL)

    def test_mix(self):
        rng = random.Random(1337)
        cases = [_league(rng) for _ in range(N_CASES)]
        got = _harness("mix", {"cases": cases})
        vertices = 0
        for c, g in zip(cases, got):
            want = FS.allocation_mix(
                teams=c["teams"], dedicated=c["dedicated"], superflex=c["superflex"],
                flex_eligible=tuple(c["flex_eligible"]), flex_seats=c["flex_seats"],
                bench_seats=c["bench_seats"], order=c["order"], score=c["score"], sigma=c["sigma"],
                bench_discount=RC.vorp_bench_discount, soft_bench=c["soft_bench"])
            self.assertEqual(len(want), len(g), c["sigma"])
            vertices += len(want)
            for (w1, a1), (w2, a2) in zip(want, g):
                self.assertAlmostEqual(w1, w2, delta=TOL)
                for p in FS.POSITIONS:
                    self.assertEqual((a1[p]["flex"], a1[p]["bench"]), (a2[p]["flex"], a2[p]["bench"]))
        self.assertGreater(vertices, N_CASES, "no case produced a mix of more than one allocation")


if __name__ == "__main__":
    unittest.main()
