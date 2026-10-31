"""JEG-1335: fractional flex everywhere, fractional bench with no league loaded
(Jeremy, 2026-10-30, option A of JEG-1333).

Under the hard VP-2.2 rule a fringe player crossing a flex or bench cutoff
moves a whole seat at once, and other players' DDF Values jump with it (up to
3.8 on the Charlotte shape). With the seat mix (value_reference.allocation_mix,
SEAT_SIGMA = 0.75) a 1 PPG change in one projection source for one fringe
player moves no other player by more than 1.0 DDF Value.

For each of the 12 settings (3 scorings x 8/10/12/14 teams) plus the USO and
Charlotte roster shapes, the fringe is the last starter and first non-starter
of each flex position and the last rostered and first waiver player of each
position. Each fringe player's first projection source with a value is moved
by -1 and +1 PPG, the whole pipeline is rerun with the allocation free, and
every other player's blended DDF Value is compared with the base run.

test_hard_rule_fails_the_bound is the mutation: the same check at sigma 0
(today's rule on main) breaks the bound on the Charlotte shape.

Heavy (about two minutes on four cores, live inputs); runs in test-core (shard 2).
"""
from __future__ import annotations

import os
import sys
import unittest
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "pipelines", REPO / "pipelines" / "lib"):
    sys.path.insert(0, str(p))

import value_reference as VR  # noqa: E402

BOUND = 1.0   # largest DDF Value move allowed for any other player
PPG_STEP = 1.0

# The two real leagues' roster shapes (as in tests/test_fractional_seats.py).
LEAGUES = {
    "uso": {"scoring": "half_ppr", "teams": 12, "slots": {"QB": 1, "RB": 2, "WR": 3, "TE": 1},
            "flex": 1, "bench": 5},
    "charlotte": {"scoring": "half_ppr", "teams": 12, "slots": {"QB": 1, "RB": 2, "WR": 2, "TE": 1},
                  "flex": 1, "bench": 6},
}
SETTINGS = [f"{sc}/{t}" for sc in VR.SCORINGS for t in VR.TEAM_COUNTS] + list(LEAGUES)

_INPUTS = None


def _setting(inp, name):
    if name in LEAGUES:
        lg = LEAGUES[name]
        s = VR.Setting(inp, lg["scoring"], lg["teams"])
        s.shape = {**s.shape, **lg["slots"], "FLEX": lg["flex"], "BENCH": lg["bench"]}
        s.league = VR.League(teams=s.teams, slots={p: s.shape[p] for p in VR.POSITIONS}, flex=s.shape["FLEX"],
                             superflex=s.shape["SUPERFLEX"], bench=s.shape["BENCH"],
                             bench_share=s.league.bench_share)
        return s, lg["scoring"]
    sc, t = name.split("/")
    return VR.Setting(inp, sc, int(t)), sc


def _values(inp, name):
    s, sc = _setting(inp, name)
    r = s.result()
    return {i: row["ddf"]["blended"]["value"] for i, row in r["rows"].items()}, r, sc


def _fringe(r):
    m, alloc = r["mean_ppg"], r["allocation"]
    pos_of = {i: row["pos"] for i, row in r["rows"].items()}
    keys = []
    for kind in ("flex", "bench"):
        for p in VR.POSITIONS:
            if kind == "flex" and p not in VR.FLEX_ELIGIBLE:
                continue
            order = sorted((i for i in m if pos_of.get(i) == p), key=lambda i: (-m[i], i))
            cut = alloc[p]["starters"] if kind == "flex" else alloc[p]["rostered"]
            keys += [k for k in order[max(0, cut - 1):cut + 1] if k not in keys]
    return keys


def worst_move(name: str, sigma: float) -> tuple[float, str, int]:
    """(largest other-player move, what moved it, runs) for one setting."""
    global _INPUTS
    if _INPUTS is None:
        _INPUTS = VR.Inputs.load()
    inp = _INPUTS
    saved = VR.SEAT_SIGMA
    VR.SEAT_SIGMA = sigma
    try:
        base, r0, sc = _values(inp, name)
        worst, why, runs = 0.0, "", 0
        for k in _fringe(r0):
            src = next((s for s in VR.PROJECTIONS
                        if VR._finite((inp.players[k].get(VR.PPG_FIELD[s]) or {}).get(sc))), None)
            if src is None:
                continue
            rec = inp.players[k][VR.PPG_FIELD[src]]
            old = rec[sc]
            for d in (-PPG_STEP, PPG_STEP):
                rec[sc] = max(0.0, old + d)
                try:
                    v, _r, _ = _values(inp, name)
                finally:
                    rec[sc] = old
                runs += 1
                for i, b in base.items():
                    if i == k or b is None or v.get(i) is None:
                        continue
                    mv = abs(v[i] - b)
                    if mv > worst:
                        worst, why = mv, f"{k} {src} {d:+.0f} moved {i}"
        return worst, why, runs
    finally:
        VR.SEAT_SIGMA = saved


class FractionalSeatStability(unittest.TestCase):
    def test_no_other_player_moves_more_than_one(self):
        workers = max(1, min(len(SETTINGS), os.cpu_count() or 1))
        with ProcessPoolExecutor(max_workers=workers) as ex:
            out = dict(zip(SETTINGS, ex.map(worst_move, SETTINGS, [VR.SEAT_SIGMA] * len(SETTINGS))))
        bad = {n: o for n, o in out.items() if o[0] > BOUND}
        for n, (w, why, runs) in out.items():
            self.assertGreater(runs, 0, f"{n}: no fringe player had a projection to move")
        self.assertEqual(bad, {}, "a 1 PPG one-source change moved another player by more than "
                                  f"{BOUND} DDF Value: {bad}")

    def test_hard_rule_fails_the_bound(self):
        worst, why, _ = worst_move("charlotte", 0.0)
        self.assertGreater(worst, BOUND, f"the hard rule should break the bound on Charlotte (worst {worst})")


if __name__ == "__main__":
    unittest.main()
