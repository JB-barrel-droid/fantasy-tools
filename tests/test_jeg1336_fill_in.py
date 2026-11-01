"""JEG-1336: the fill-in research script holds what it says it holds.

Two regressions from the Codex review of #1181 (head da2ccd6d):

1. Since JEG-1335 (#1242), run_pipeline runs once per allocation vertex, so the
   fill hook fires once per vertex. Holding a bake's fill set must replay each
   vertex's own set: the same inputs held against themselves give a step of 0
   under every option. Replaying the last vertex's set everywhere (the old
   behaviour) gave 0.0133 at standard/12.
2. The sweep's "fill changed" flag compares against the unperturbed fill set.
   The old code cached the first perturbed case's set as the baseline, so that
   case read as unchanged.

    python3 -m unittest -v tests.test_jeg1336_fill_in
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools" / "research"))

import jeg1336_fill_in as J  # noqa: E402

CELL = "standard/12"


def _cell():
    return next(c for c in J.F.cells() if c["name"] == CELL)


class HeldFillPerVertex(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        J.setup(str(REPO))
        cls.inp = J.VR.Inputs.load()
        cls.cell = _cell()
        _, made, _, cls.fill = J.run(cls.inp, cls.cell)
        cls.hold = staticmethod(J.F.replay(made))   # a plain function would bind as a method

    def test_setting_has_several_vertices(self):
        self.assertGreater(len(self.fill), 1, f"{CELL} no longer blends allocation vertices")

    def test_identical_bake_steps_zero_under_every_option(self):
        for o in J.OPTIONS:
            with self.subTest(option=o):
                free = J.run(self.inp, self.cell, o, self.hold)[0]
                held = J.run(self.inp, self.cell, o, self.hold, held=J.run(self.inp, self.cell, o)[3])[0]
                self.assertEqual(J.worst(held, free)[0], 0.0)

    def test_last_vertex_everywhere_is_caught(self):
        # The old behaviour: one fill set (the last vertex's) for every vertex.
        members = J.fill_members(self.fill)
        if all(x == members[-1] for x in members):
            self.skipTest("every vertex has the same fill set today; the old behaviour can't differ")
        free = J.run(self.inp, self.cell, "A", self.hold)[0]
        held = J.run(self.inp, self.cell, "A", self.hold, held=[self.fill[-1]])[0]
        self.assertGreater(J.worst(held, free)[0], 0.0)


class SweepBaselineUnperturbed(unittest.TestCase):
    def test_first_case_that_moves_the_fill_set_is_flagged(self):
        J.setup(str(REPO))
        inp = J.VR.Inputs.load()
        cell = _cell()
        _, made, res, _ = J.run(inp, cell)
        hold = J.F.replay(made)
        base = J.fill_members(J.run(inp, cell, "A", hold)[3])
        m = res["mean_ppg"]
        key = None
        # A player near a cutoff whose first sweep case (first projection with
        # a value, first delta) changes the fill set.
        for p in J.VR.POSITIONS:
            order = sorted((i for i in m if inp.players.get(i, {}).get("pos") == p), key=lambda i: (-m[i], i))
            n = res["allocation"][p]["rostered"] + 1
            for k in sorted(order[max(0, n - J.BAND):n + J.BAND]):
                src = next((s for s in J.VR.PROJECTIONS
                            if isinstance(inp.players[k].get(J.VR.PPG_FIELD[s]), dict)
                            and J.VR._finite(inp.players[k][J.VR.PPG_FIELD[s]].get(cell["scoring"]))), None)
                if src is None:
                    continue
                rec = inp.players[k][J.VR.PPG_FIELD[src]]
                old = rec[cell["scoring"]]
                rec[cell["scoring"]] = max(0.0, old + J.DELTAS[0])
                try:
                    moved = J.fill_members(J.run(inp, cell, "A", hold)[3]) != base
                finally:
                    rec[cell["scoring"]] = old
                if moved:
                    key = k
                    break
            if key is not None:
                break
        if key is None:
            self.skipTest(f"no player near a {CELL} cutoff moves the fill set on his first sweep case today")
        cases = J.sweep_cell((str(REPO), cell, [key], ("A",)))["cases"]
        self.assertTrue(cases)
        # The old cached baseline was this very case's fill set, so it read False.
        self.assertTrue(cases[0]["fill_changed"])


if __name__ == "__main__":
    unittest.main()
