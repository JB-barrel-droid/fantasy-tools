"""JEG-1334: the fractional-seat helper for option B (JEG-1286, JEG-1333).

pipelines/lib/fractional_seats.py and its JS twin
app/trade-value-chart/assets/fractional-seats.js build a weighted mix of
whole league allocations from fractional flex and bench seats. These tests
hold that:

- sigma = 0 is today's VP-2.2 allocation (value_reference.allocate) on the
  12-setting grid plus the USO and Charlotte roster shapes;
- the mix's expected counts equal the fractional counts;
- the mix moves continuously when a fringe player crosses a flex or bench
  cutoff, and a hard cutoff (the mutation) fails the same check;
- the JS twin matches Python to 1e-12 on 200 random leagues.
"""
from __future__ import annotations

import copy
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

HARNESS = REPO / "tests" / "fractional_seats_harness.cjs"
SIGMA = 0.75          # the chosen sigma (docs/decisions.md, JEG-1286)
STEP = 0.01           # scan step, mean PPG
STEP_BOUND = 0.05     # largest mix change (L1) allowed per 0.01 PPG step

# The two real leagues' roster shapes (as in tools/research/jeg1286_flex_flips.py).
LEAGUES = {
    "uso": {"scoring": "half_ppr", "teams": 12, "slots": {"QB": 1, "RB": 2, "WR": 3, "TE": 1},
            "flex": 1, "bench": 5},
    "charlotte": {"scoring": "half_ppr", "teams": 12, "slots": {"QB": 1, "RB": 2, "WR": 2, "TE": 1},
                  "flex": 1, "bench": 6},
}

RATES = {p: RC._BYE_RATE + RC._BENCH_MISS_RATE.get(p, 0.12) for p in FS.POSITIONS}


def bench_discount(starters, teams):
    """The usage discount of roster_convention.vorp_bench_allocate."""
    c = {p: (starters.get(p, 0) / teams) * RATES[p] for p in FS.POSITIONS}
    t1 = {p: max(1, round(2.0 * c[p] * float(teams))) for p in FS.POSITIONS}
    return lambda p, k: c[p] ** (1 + k // t1[p])


def _setting(inp, name):
    if name in LEAGUES:
        L = LEAGUES[name]
        s = VR.Setting(inp, L["scoring"], L["teams"])
        s.shape = {**s.shape, **L["slots"], "FLEX": L["flex"], "BENCH": L["bench"]}
        s.league = VR.League(
            teams=s.teams, slots={p: s.shape[p] for p in VR.POSITIONS}, flex=s.shape["FLEX"],
            superflex=s.shape["SUPERFLEX"], bench=s.shape["BENCH"],
            bench_share=s.league.bench_share)
        return s
    sc, t = name.split("/")
    return VR.Setting(inp, sc, int(t))


_CAPTURED = {}


def captured():
    """{setting: [(league, order, score, today's allocation)]}, the
    arguments of every VR.allocate call in one reference run per setting."""
    if _CAPTURED:
        return _CAPTURED
    inp = VR.Inputs.load()
    names = [f"{sc}/{t}" for sc in VR.SCORINGS for t in VR.TEAM_COUNTS] + list(LEAGUES)
    orig = VR.allocate
    for name in names:
        calls = []

        def patched(league, order, score, _calls=calls, **kw):
            out = orig(league, order, score, **kw)
            _calls.append((league, copy.deepcopy(order), dict(score), copy.deepcopy(out), kw))
            return out

        # JEG-1335: the pipeline now runs the mix; sigma 0 makes it call
        # allocate once per allocation, today's hard rule, as before.
        VR.allocate, sigma = patched, VR.SEAT_SIGMA
        VR.SEAT_SIGMA = 0.0
        try:
            _setting(inp, name).result()
        finally:
            VR.allocate, VR.SEAT_SIGMA = orig, sigma
        _CAPTURED[name] = calls
    return _CAPTURED


def mix_for(league, order, score, today, sigma, soft_bench=True, prune=FS.PRUNE):
    t = int(league.teams)
    return FS.allocation_mix(
        teams=t,
        dedicated={p: t * int(league.slots.get(p, 0)) for p in FS.POSITIONS},
        superflex={p: today[p]["superflex"] for p in FS.POSITIONS},
        flex_eligible=tuple(league.flex_eligible), flex_seats=t * int(league.flex),
        bench_seats=t * int(league.bench), order=order, score=score, sigma=sigma,
        bench_discount=bench_discount, soft_bench=soft_bench, prune=prune)


def _key(alloc):
    return tuple((alloc[p]["flex"], alloc[p]["bench"]) for p in FS.POSITIONS)


def l1(mix_a, mix_b):
    a, b = {}, {}
    for w, x in mix_a:
        a[_key(x)] = a.get(_key(x), 0.0) + w
    for w, x in mix_b:
        b[_key(x)] = b.get(_key(x), 0.0) + w
    return sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in set(a) | set(b))


def scan(league, order, score, today, pid, lo, hi, sigma):
    """Largest mix change (L1) per STEP as player `pid`'s mean PPG runs from
    lo to hi, keeping his position's order sorted by score."""
    pos = next(p for p in FS.POSITIONS if pid in order.get(p, []))
    prev, worst = None, 0.0
    n = int(round((hi - lo) / STEP))
    for j in range(n + 1):
        sc = dict(score)
        sc[pid] = lo + j * STEP
        od = dict(order)
        od[pos] = sorted(order[pos], key=lambda i: -sc[i])
        m = mix_for(league, od, sc, today, sigma)
        if prev is not None:
            worst = max(worst, l1(prev, m))
        prev = m
    return worst


def _cutoff_players(league, order, today, kind):
    """Players either side of the flex or bench cutoff at each position:
    the last one in and the first one out."""
    out = []
    for p in FS.POSITIONS:
        a = today[p]
        if kind == "flex":
            if p not in league.flex_eligible:
                continue
            first, n = a["dedicated"] + a["superflex"], a["flex"]
        else:
            first, n = a["starters"], a["bench"]
        ids = order.get(p, [])
        if n > 0:
            out.append(ids[first + n - 1])
        if first + n < len(ids):
            out.append(ids[first + n])
    return out


def find_crossing(league, order, score, today, kind, reach=1.5, coarse=0.05):
    """(player, lo, hi): a 1 PPG window over which moving that one player's
    projection flips today's hard allocation (the case B must smooth)."""
    for pid in _cutoff_players(league, order, today, kind):
        pos = next(p for p in FS.POSITIONS if pid in order.get(p, []))
        base = score[pid]
        prev = None
        n = int(round(2 * reach / coarse))
        for j in range(n + 1):
            x = base - reach + j * coarse
            sc = dict(score)
            sc[pid] = x
            od = dict(order)
            od[pos] = sorted(order[pos], key=lambda i: -sc[i])
            m = mix_for(league, od, sc, today, 0.0)
            if prev is not None and l1(prev, m) > 1.0:
                field = "flex" if kind == "flex" else "bench"
                if any(prev[0][1][p][field] != m[0][1][p][field] for p in FS.POSITIONS):
                    return pid, x - 0.5, x + 0.5
            prev = m
    raise AssertionError(f"no {kind} crossing within {reach} PPG of a cutoff")


class SigmaZeroIsTodayTest(unittest.TestCase):
    def test_sigma_zero_matches_allocate_on_every_setting(self):
        for name, calls in captured().items():
            self.assertTrue(calls, name)
            for league, order, score, today, kw in calls:
                if not kw.get("flex_bench_seats", True):
                    continue
                for sigma in (0.0, 1e-7):
                    mix = mix_for(league, order, score, today, sigma)
                    self.assertEqual(len(mix), 1, f"{name} sigma {sigma}: {len(mix)} allocations")
                    w, a = mix[0]
                    self.assertAlmostEqual(w, 1.0, places=12)
                    self.assertEqual(a, {p: today[p] for p in FS.POSITIONS}, f"{name} sigma {sigma}")

    def test_hard_bench_is_vorp_bench_allocate(self):
        for name, calls in captured().items():
            for league, order, score, today, _kw in calls:
                t = int(league.teams)
                starters = {p: today[p]["starters"] for p in FS.POSITIONS}
                remaining = {p: order.get(p, [])[starters[p]:] for p in FS.POSITIONS}
                want = RC.vorp_bench_allocate(starters, remaining, score, t, t * int(league.bench),
                                              {p: int(league.slots.get(p, 0)) for p in FS.POSITIONS},
                                              False, None)
                got = FS._hard_bench(remaining, score, t * int(league.bench), bench_discount(starters, t),
                                     FS.POSITIONS, {p: j for j, p in enumerate(FS.POSITIONS)})
                self.assertEqual(got, {p: want.get(p, 0) for p in FS.POSITIONS}, name)


class ExpectedCountsTest(unittest.TestCase):
    def test_decompose_expectation_equals_fractions(self):
        rng = random.Random(1334)
        for _ in range(500):
            k = rng.randint(1, 30)
            raw = {p: rng.random() * 10 for p in FS.POSITIONS}
            whole = {p: rng.randint(0, 20) for p in FS.POSITIONS}
            tot = sum(raw.values())
            frac = {p: whole[p] + raw[p] * k / tot for p in FS.POSITIONS}
            parts = FS.decompose(frac)
            self.assertAlmostEqual(sum(w for w, _ in parts), 1.0, places=9)
            for p in FS.POSITIONS:
                exp = sum(w * c[p] for w, c in parts)
                self.assertAlmostEqual(exp, frac[p], places=9, msg=p)
                for _w, c in parts:
                    self.assertIn(c[p] - whole[p], range(int(raw[p] * k / tot), int(raw[p] * k / tot) + 2))
            for _w, c in parts:
                self.assertEqual(sum(c.values()), sum(whole.values()) + k)

    def test_mix_flex_expectation_equals_soft_select(self):
        for name in ("half_ppr/12", "standard/10", "uso", "charlotte"):
            league, order, score, today, _kw = captured()[name][0]
            mix = mix_for(league, order, score, today, SIGMA, prune=0.0)
            exp = FS.expected_counts(mix)
            t = int(league.teams)
            d = {p: t * int(league.slots.get(p, 0)) for p in FS.POSITIONS}
            items = []
            fitems = sorted((FS.POSITIONS.index(p), i, p) for p in FS.POSITIONS if p in league.flex_eligible
                            for idx, i in enumerate(order.get(p, [])) if idx >= d[p] + today[p]["superflex"])
            items = [(p, float(score[i]), SIGMA) for _r, i, p in fitems]
            want = FS.soft_select(items, t * int(league.flex))
            for p in FS.POSITIONS:
                self.assertAlmostEqual(exp[p]["flex"], want.get(p, 0.0), places=9, msg=f"{name} {p}")
            self.assertAlmostEqual(sum(exp[p]["bench"] for p in FS.POSITIONS), t * int(league.bench),
                                   places=9, msg=name)

    def test_soft_select_fills_the_seats(self):
        rng = random.Random(7)
        for _ in range(100):
            items = [(rng.choice(FS.POSITIONS), rng.uniform(0, 20), 0.75) for _ in range(rng.randint(5, 60))]
            n = rng.randint(1, len(items))
            got = FS.soft_select(items, n)
            self.assertAlmostEqual(sum(got.values()), n, places=9)


class ContinuityTest(unittest.TestCase):
    """A fringe player's projection crossing a cutoff moves the mix a little
    per step under B, and a whole seat under a hard cutoff."""

    def _case(self, name, kind):
        league, order, score, today, _kw = captured()[name][0]
        pid, lo, hi = find_crossing(league, order, score, today, kind)
        return league, order, score, today, pid, lo, hi

    def test_crossings_are_continuous(self):
        for name, kind in (("uso", "flex"), ("charlotte", "flex"), ("standard/10", "flex"),
                           ("charlotte", "bench"), ("standard/10", "bench"), ("ppr/14", "bench")):
            league, order, score, today, pid, lo, hi = self._case(name, kind)
            worst = scan(league, order, score, today, pid, lo, hi, SIGMA)
            self.assertLess(worst, STEP_BOUND,
                            f"{name} {kind}: mix moved {worst:.3f} in one 0.01 PPG step")

    def test_mutation_hard_cutoff_fails_continuity(self):
        for name, kind in (("uso", "flex"), ("charlotte", "flex"), ("charlotte", "bench"),
                           ("standard/10", "bench")):
            league, order, score, today, pid, lo, hi = self._case(name, kind)
            worst = scan(league, order, score, today, pid, lo, hi, 0.0)
            self.assertGreaterEqual(worst, 1.0, f"{name} {kind}: a hard cutoff should jump")


def _random_case(rng):
    teams = rng.randint(8, 14)
    slots = {"QB": rng.choice((1, 1, 2)), "RB": rng.randint(1, 3), "WR": rng.randint(2, 4), "TE": 1}
    flex = rng.randint(0, 2)
    bench = rng.randint(3, 8)
    order, score = {}, {}
    for p in FS.POSITIONS:
        n = teams * (slots[p] + 3) + rng.randint(0, 10)
        top = {"QB": 22, "RB": 20, "WR": 19, "TE": 14}[p]
        vals = sorted((rng.uniform(0, top) for _ in range(n)), reverse=True)
        ids = [f"{p}{j:03d}" for j in range(n)]
        order[p] = ids
        score.update(zip(ids, vals))
    return {
        "teams": teams, "dedicated": {p: teams * slots[p] for p in FS.POSITIONS},
        "superflex": {p: 0 for p in FS.POSITIONS}, "flex_eligible": ["RB", "WR", "TE"],
        "flex_seats": teams * flex, "bench_seats": teams * bench, "order": order, "score": score,
        "sigma": rng.choice((0.0, 0.3, 0.75, 0.75, 1.0)), "soft_bench": rng.random() < 0.8,
        "rates": RATES,
    }


def _harness(cmd, payload):
    proc = subprocess.run(["node", str(HARNESS), cmd], input=json.dumps(payload),
                          capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise AssertionError(f"harness {cmd} failed: {proc.stderr[:2000]}")
    return json.loads(proc.stdout)


class JsTwinParityTest(unittest.TestCase):
    def test_phi_matches(self):
        zs = [j / 100.0 for j in range(-800, 801)]
        got = _harness("phi", {"z": zs})
        for z, g in zip(zs, got):
            self.assertAlmostEqual(g, FS.phi(z), delta=1e-14, msg=f"z={z}")

    def test_decompose_matches(self):
        rng = random.Random(42)
        fracs = []
        for _ in range(200):
            raw = {p: rng.random() for p in FS.POSITIONS}
            k = rng.randint(1, 3)
            tot = sum(raw.values())
            fracs.append({p: rng.randint(0, 9) + raw[p] * k / tot for p in FS.POSITIONS})
        got = _harness("decompose", {"fracs": fracs})
        for f, g in zip(fracs, got):
            want = FS.decompose(f)
            self.assertEqual([c for _w, c in want], [c for _w, c in g])
            for (w1, _), (w2, _) in zip(want, g):
                self.assertAlmostEqual(w1, w2, delta=1e-12)

    def test_allocation_mix_matches_on_200_random_leagues(self):
        rng = random.Random(1286)
        cases = [_random_case(rng) for _ in range(200)]
        got = _harness("mix", {"cases": cases})
        for j, (c, g) in enumerate(zip(cases, got)):
            want = FS.allocation_mix(
                teams=c["teams"], dedicated=c["dedicated"], superflex=c["superflex"],
                flex_eligible=tuple(c["flex_eligible"]), flex_seats=c["flex_seats"],
                bench_seats=c["bench_seats"], order=c["order"], score=c["score"], sigma=c["sigma"],
                bench_discount=bench_discount, soft_bench=c["soft_bench"])
            self.assertEqual(len(want), len(g), f"case {j}")
            for (w1, a1), (w2, a2) in zip(want, g):
                self.assertEqual(a1, a2, f"case {j}")
                self.assertAlmostEqual(w1, w2, delta=1e-12, msg=f"case {j}")


if __name__ == "__main__":
    unittest.main()
