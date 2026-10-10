"""Two-tier starter/bench pricing, from the written spec only.

Spec sources (quoted where they decide something):
- docs/pipeline-rules.md s9: bench share is a parameter (default 0.15, per
  position); calibration "fail[s] closed per position when starter rate <=
  bench rate".
- docs/claude-log/2026-10-07-qb8-investigation.md: per position a 2x2 system
  gives a bench rate pb and a starter rate ps "so that bench players get
  share * pie and starters (1 - share) * pie"; feasible iff pb > 0 and
  ps > pb; the feasible set is an interval [lo, hi], hi is the natural share
  "bench surplus / total surplus, where pb = ps", below lo pb <= 0.
- docs/methodology.md "Validation Principle": below the window the share used
  is "one percentage point inside the window's lower edge (halving if the
  window is narrower)".
- The leg artifact's own `pies_method` text (data/ddf-two-tier/*/ddf_leg.json):
  "pie = sum(max(0, per-game - waiver_pg)); waiver = next-unrostered
  per-game; rostered = teams*slots + flex (teams flex from RB/WR/TE pool after
  dedicated) + bench_mix scaled by teams/12 (round-half-up)", reference shape
  QB1 RB2 WR3 TE1 FLEX1, bench mix QB10 RB27 WR33 TE10.
- docs/claude-log.md 2026-09-25: the leg prices with a "softplus glide" and
  "slice pricing"; fe-dependency-inventory: values "scaled by 70/max(raw)".

Spec gaps and how they are resolved here are tagged `GAP:` and collected in
compare.SPEC_GAPS.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

POSITIONS = ("QB", "RB", "WR", "TE")
REF_SLOTS = {"QB": 1, "RB": 2, "WR": 3, "TE": 1}
REF_FLEX = 1
FLEX_ELIGIBLE = ("RB", "WR", "TE")
BENCH_MIX_12 = {"QB": 10, "RB": 27, "WR": 33, "TE": 10}
DEFAULT_BENCH_SHARE = 0.15
STEP_INSIDE_WINDOW = 0.01
MAX_HALVINGS = 8
DISPLAY_TOP = 70.0
# SG-3 resolution for a share above the window. "step_inside" is the spec
# reference's choice; "edge" (pb = ps, the natural share) exists only so a
# diagnostic run can separate this gap from the others.
ABOVE_WINDOW = "step_inside"


def round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def bench_counts(teams: int) -> dict[str, int]:
    """Two-tier pool bench per position: the 12-team mix scaled by teams/12."""
    return {pos: round_half_up(BENCH_MIX_12[pos] * teams / 12) for pos in POSITIONS}


def softplus(x: float, tau: float) -> float:
    """tau * ln(1 + e^(x/tau)), overflow-safe; tau <= 0 is the hard hinge."""
    if tau <= 0:
        return max(0.0, x)
    z = x / tau
    if z > 35:
        return x
    return tau * math.log1p(math.exp(z))


@dataclass
class PositionTier:
    pos: str
    starters: list  # [(key, ppg)] best first
    bench: list
    waiver: list
    rw: float  # waiver line: the next unrostered player's per-game
    rs: float  # starter line
    tau: float  # glide width

    @property
    def rostered(self) -> list:
        return self.starters + self.bench

    @property
    def pie(self) -> float:
        return sum(max(0.0, ppg - self.rw) for _, ppg in self.rostered)


def _sorted(rows):
    # GAP: tie order between equal projections is not written; key ascending.
    return sorted(rows, key=lambda r: (-r[1], r[0]))


def build_pool(players: list[tuple], teams: int, slots=None, flex=REF_FLEX,
               bench=None) -> dict[str, PositionTier]:
    """players: [(key, pos, ppg)]. Starters = dedicated + flex by projection,
    bench = the next bench_counts at each position, everyone else waiver."""
    slots = slots or REF_SLOTS
    bench = bench or bench_counts(teams)
    by_pos = {pos: _sorted([(k, float(p)) for k, ps, p in players if ps == pos and p is not None])
              for pos in POSITIONS}
    starters = {pos: by_pos[pos][: teams * slots[pos]] for pos in POSITIONS}
    rest = {pos: by_pos[pos][teams * slots[pos]:] for pos in POSITIONS}
    flex_pool = _sorted([(k, p, pos) for pos in FLEX_ELIGIBLE for k, p in rest[pos]])
    flex_pool = sorted(flex_pool, key=lambda r: (-r[1], r[0]))[: teams * flex]
    flex_keys = {k for k, _, _ in flex_pool}
    tiers = {}
    for pos in POSITIONS:
        st = starters[pos] + [r for r in rest[pos] if r[0] in flex_keys]
        remaining = [r for r in rest[pos] if r[0] not in flex_keys]
        bn = remaining[: bench[pos]]
        wv = remaining[bench[pos]:]
        # GAP: an empty waiver list has no "next unrostered" player; use 0.
        rw = wv[0][1] if wv else 0.0
        # GAP: the starter line is not written in the docs. Resolved from the
        # leg artifact's recorded `rs`: midway between the last starter and the
        # first bench player (the boundary of the two slices).
        if st and bn:
            rs = (st[-1][1] + bn[0][1]) / 2.0
        elif st:
            rs = st[-1][1]
        else:
            rs = rw
        # GAP: the softplus width is not written. Resolved from the leg
        # artifact's recorded `tau`: a quarter of the starter-to-waiver gap.
        tau = max(0.0, (rs - rw) / 4.0)
        tiers[pos] = PositionTier(pos, st, bn, wv, rw, rs, tau)
    return tiers


def exposures(ppg: float, tier: PositionTier) -> tuple[float, float]:
    """Split a player's surplus over the waiver line into a starter slice
    (above the starter line, softplus-glided) and a bench slice (the rest).

    GAP: the slice exposures ("sliceExposures") are not written. Chosen: the
    surplus e = max(0, ppg - rw); starter slice a = min(e, softplus(ppg - rs));
    bench slice b = e - a. So a + b = e and pb = ps prices every player at
    surplus (the natural share), matching the spec's definition of hi.
    """
    e = max(0.0, ppg - tier.rw)
    a = min(e, softplus(ppg - tier.rs, tier.tau))
    return a, e - a


@dataclass
class Calibration:
    pos: str
    pie: float
    requested_share: float
    share_used: float | None
    lo: float | None
    hi: float | None
    ps: float | None
    pb: float | None
    error: str | None = None
    sums: dict = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return self.error is None


def _group_sums(tier: PositionTier):
    sa = sb = ba = bb = 0.0
    for _, ppg in tier.starters:
        a, b = exposures(ppg, tier)
        sa += a
        sb += b
    for _, ppg in tier.bench:
        a, b = exposures(ppg, tier)
        ba += a
        bb += b
    return sa, sb, ba, bb


def solve_rates(sums, pie: float, share: float):
    """[[Sa, Sb], [Ba, Bb]] . [ps, pb] = [(1 - share) pie, share pie]."""
    sa, sb, ba, bb = sums
    det = sa * bb - sb * ba
    if abs(det) < 1e-15:
        return None, None
    ps = ((1 - share) * pie * bb - sb * share * pie) / det
    pb = (sa * share * pie - ba * (1 - share) * pie) / det
    return ps, pb


def feasible_window(sums) -> tuple[float, float] | None:
    """Closed form, both rates are linear in the share.
    pb = 0  at lo = Ba / (Sa + Ba);  pb = ps at hi = (Ba + Bb) / total."""
    sa, sb, ba, bb = sums
    total = sa + sb + ba + bb
    if sa + ba <= 0 or total <= 0:
        return None
    lo = ba / (sa + ba)
    hi = (ba + bb) / total
    if not lo < hi:
        return None
    return lo, hi


def _step_inside(edge_from: float, width: float, direction: int) -> float:
    step = STEP_INSIDE_WINDOW
    for _ in range(MAX_HALVINGS):
        if step < width:
            break
        step /= 2.0
    return edge_from + direction * step


def calibrate(tier: PositionTier, share: float = DEFAULT_BENCH_SHARE) -> Calibration:
    sums = _group_sums(tier)
    pie = tier.pie
    window = feasible_window(sums)
    if pie <= 0 or window is None:
        return Calibration(tier.pos, pie, share, None, None, None, None, None,
                           error="no feasible bench share", sums=dict(zip("Sa Sb Ba Bb".split(), sums)))
    lo, hi = window
    used = share
    if share <= lo:
        used = _step_inside(lo, hi - lo, +1)
    elif share >= hi:
        # GAP: above the window ("economics break") the docs say only that it
        # "falls back down". Resolved symmetric to the written lower-edge
        # rule: one point inside the upper edge, halving if narrower.
        used = _step_inside(hi, hi - lo, -1) if ABOVE_WINDOW == "step_inside" else hi - 1e-9
    ps, pb = solve_rates(sums, pie, used)
    cal = Calibration(tier.pos, pie, share, used, lo, hi, ps, pb,
                      sums=dict(zip("Sa Sb Ba Bb".split(), sums)))
    if ps is None or not (pb > 0 and ps > pb):
        cal.error = "starter rate <= bench rate or bench rate <= 0"
    return cal


def price_leg(players: list[tuple], teams: int, share: float = DEFAULT_BENCH_SHARE):
    """Price a source's per-game projections on the two-tier leg.

    Returns (display values {key: value}, raw values, tiers, calibrations).
    A player in the pool below the pricing line is 0.0 (methodology: "0.0 on
    that leg, not missing"); a position that fails closed is withheld (no
    value for any of its players).
    """
    tiers = build_pool(players, teams)
    cals = {pos: calibrate(tiers[pos], share) for pos in POSITIONS}
    raw: dict = {}
    tier_of: dict = {}
    for pos, tier in tiers.items():
        cal = cals[pos]
        if not cal.valid:
            continue
        for group, rows in (("starter", tier.starters), ("bench", tier.bench), ("waiver", tier.waiver)):
            for key, ppg in rows:
                if group == "waiver":
                    raw[key] = 0.0
                else:
                    a, b = exposures(ppg, tier)
                    raw[key] = cal.ps * a + cal.pb * b
                tier_of[key] = group
    top = max(raw.values(), default=0.0)
    scale = DISPLAY_TOP / top if top > 0 else 0.0
    return {k: v * scale for k, v in raw.items()}, raw, tiers, cals, tier_of
