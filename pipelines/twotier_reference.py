"""Backend parity reference for the TwoTier module.

JEG-364 (JEG-327 Phase E, part 1 of 3): computation parity. Exact, faithful
port of the pure TwoTier helpers in
`app/trade-value-chart/assets/curve-widget.js:195-584`. Every function here
must match the JS implementation to floating-point tolerance; the parity
script (`pipelines/check_twotier_parity.py`) loads both sides against the
same fixed JSON vectors and reports mismatches.

Conventions
- POSITIONS / DEFAULT_BENCH_SHARE / GLIDE_WIDTH_FRAC / REF_SLOTS /
  REF_FLEX_COUNT / REF_FLEX_ELIGIBLE / WITHHELD_FLAG match the JS module
  (TwoTier frozen at curve-widget.js:196-214).
- Players are dicts {id, x}; x is per-game projection, id is a stable string
  used as a Set key (the JS code only needs them to be comparable, never
  numeric).
- Math is stdlib only (math.log1p / math.exp); no numpy, no scipy.
- Stable tiebreak for sorted projections is by (-x, str(id)).
- The FE export is the global `TradeValueTwoTier`; parity tests reach into
  it the same way the Python module exposes a `TwoTier` namespace.

Functions ported (in source order; each is covered by the parity script):
  - softplus
  - slice_exposures
  - check_share
  - solve_tier_prices
  - feasible_at
  - feasible_bench_share_interval
  - slider_bounds
  - round_half_even
  - display_value
  - normalize_then_round
  - tail_floor
  - bench_mix_for
  - inward_bounds
  - build_position_tiers
  - calibrate_position
  - calibrate_position_feasible
  - price_for_projection
  - skill_bench_shares
  - skill_bench_share
  - legacy_bench_mix_for

Do NOT change the formulas here. Mirror them. A parity mismatch is a defect
in either side, and the standing rule ("every regression guard must prove
it catches the bug it names") applies to the parity test script too.
"""
from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# Constants (mirror TwoTier frozen block at curve-widget.js:196-214).
# ---------------------------------------------------------------------------
POSITIONS = ["QB", "RB", "WR", "TE"]
DEFAULT_BENCH_SHARE = 0.15
GLIDE_WIDTH_FRAC = 0.25
FEAS_TOL = 1e-4
REF_BENCH_SLOTS = 6
# Kept only as the regression anchor for the pinned-constant test.
LEGACY_BENCH_MIX_12 = {"QB": 10, "RB": 27, "WR": 33, "TE": 10}
# JEG-392 (2026-10-05): 0.01 -> 0.0075, mirrors curve-widget.js (see comment there).
FLOOR_SLOPE_FRAC = 0.0075
FLOOR_WINDOW = 5
REF_SLOTS = {"QB": 1, "RB": 2, "WR": 3, "TE": 1}
REF_FLEX_COUNT = 1
REF_FLEX_ELIGIBLE = ["RB", "WR", "TE"]
WITHHELD_FLAG = "withheld: calibration failed closed"

# Mirrors TwoTier.solveTierPrices exactness check (curve-widget.js:260).
_SOLVE_TOL_NUM = 1e-9


# ---------------------------------------------------------------------------
# softplus: log(1 + e^z), numerically stable. d/dz softplus = sigmoid.
# ---------------------------------------------------------------------------
def softplus(z: float) -> float:
    """Mirror TwoTier.softplus (curve-widget.js:217)."""
    # JS: Math.log1p(Math.exp(-Math.abs(z))) + (z > 0 ? z : 0)
    return math.log1p(math.exp(-abs(z))) + (z if z > 0 else 0.0)


# ---------------------------------------------------------------------------
# sliceExposures: returns [a, b] for one player's surplus.
# ---------------------------------------------------------------------------
def slice_exposures(x: float, rw: float, rs: float, tau: float) -> list[float]:
    """Mirror TwoTier.sliceExposures (curve-widget.js:223-227)."""
    if not (x > rw):
        return [0.0, 0.0]
    glide = tau * (softplus((x - rs) / tau) - softplus((rw - rs) / tau))
    return [(x - rw) - glide, glide]


# ---------------------------------------------------------------------------
# check_share: throws unless share is strictly in (0, 1).
# ---------------------------------------------------------------------------
def check_share(share: Any, pos: str = "?") -> float:
    """Mirror TwoTier.checkShare (curve-widget.js:230-236)."""
    s = float(share)
    if not math.isfinite(s) or not (s > 0 and s < 1):
        raise ValueError(
            f"cannot calibrate {pos}: bench share {share!r} is not between 0 and 1 (exclusive)"
        )
    return s


# ---------------------------------------------------------------------------
# solve_tier_prices: per-position 2x2 from fixed-pie identity.
# ---------------------------------------------------------------------------
def solve_tier_prices(
    a_bench: float,
    b_bench: float,
    a_start: float,
    b_start: float,
    pie: float,
    pos: str = "?",
    bench_share: float = DEFAULT_BENCH_SHARE,
) -> dict[str, float]:
    """Mirror TwoTier.solveTierPrices (curve-widget.js:245-266)."""
    share = check_share(bench_share, pos)
    starter_share = 1 - share
    if not (pie > 0):
        raise ValueError(f"cannot calibrate {pos}: non-positive pie {pie}")
    det = a_bench * b_start - a_start * b_bench
    if det == 0:
        raise ValueError(
            f"cannot calibrate {pos}: degenerate slice exposures "
            f"(a_bench={a_bench} b_bench={b_bench} a_start={a_start} b_start={b_start})"
        )
    pb = (share * pie * b_start - b_bench * starter_share * pie) / det
    ps = (a_bench * starter_share * pie - share * pie * a_start) / det
    if not (pb > 0):
        raise ValueError(
            f"cannot calibrate {pos} at bench share {share}: bench rate {pb} not positive"
        )
    if not (ps > pb):
        raise ValueError(
            f"cannot calibrate {pos} at bench share {share}: starter rate {ps} "
            f"does not exceed bench rate {pb} -- the economics break "
            f"(bench slices would pay more than starter slices)"
        )
    # Exactness: the solved rates must reproduce the split pre-rounding.
    tol = _SOLVE_TOL_NUM * pie
    if (
        abs(pb * a_bench + ps * b_bench - share * pie) > tol
        or abs(pb * a_start + ps * b_start - starter_share * pie) > tol
    ):
        raise ValueError(
            f"cannot calibrate {pos} at bench share {share}: solved rates miss the split "
            f"(bench={pb * a_bench + ps * b_bench} "
            f"starter={pb * a_start + ps * b_start} pie={pie})"
        )
    return {"pb": pb, "ps": ps}


def feasible_at(
    a_bench: float,
    b_bench: float,
    a_start: float,
    b_start: float,
    pie: float,
    share: float,
    pos: str = "?",
) -> bool:
    """Mirror TwoTier.feasibleAt (curve-widget.js:268-275)."""
    try:
        solve_tier_prices(a_bench, b_bench, a_start, b_start, pie, pos, share)
        return True
    except Exception:
        return False


def feasible_bench_share_interval(
    a_bench: float,
    b_bench: float,
    a_start: float,
    b_start: float,
    pie: float,
    pos: str = "?",
) -> list[float] | None:
    """Mirror TwoTier.feasibleBenchShareInterval (curve-widget.js:281-297)."""
    if not feasible_at(a_bench, b_bench, a_start, b_start, pie, DEFAULT_BENCH_SHARE, pos):
        return None
    lo = 1e-6
    hi = DEFAULT_BENCH_SHARE
    while hi - lo > FEAS_TOL:
        mid = (lo + hi) / 2
        if feasible_at(a_bench, b_bench, a_start, b_start, pie, mid, pos):
            hi = mid
        else:
            lo = mid
    lo_edge = hi
    lo = DEFAULT_BENCH_SHARE
    hi = 1 - 1e-6
    while hi - lo > FEAS_TOL:
        mid = (lo + hi) / 2
        if feasible_at(a_bench, b_bench, a_start, b_start, pie, mid, pos):
            lo = mid
        else:
            hi = mid
    return [lo_edge, lo]


def slider_bounds(intervals: dict[str, list[float] | None]) -> list[float] | None:
    """Mirror TwoTier.sliderBounds (curve-widget.js:303-314)."""
    lo = -float("inf")
    hi = float("inf")
    seen = 0
    for pos, iv in intervals.items():
        if iv is None:
            return None
        seen += 1
        if iv[0] > lo:
            lo = iv[0]
        if iv[1] < hi:
            hi = iv[1]
    if not seen or lo > hi:
        return None
    return [lo, hi]


# ---------------------------------------------------------------------------
# round_half_even (banker's rounding, matches Python's default round()).
# ---------------------------------------------------------------------------
def round_half_even(x: float) -> int:
    """Mirror TwoTier.roundHalfEven (curve-widget.js:317-322)."""
    # The JS code uses Math.floor + a manual half-even rule. The Python
    # `round()` builtin uses banker's rounding, which is the same rule for
    # positive numbers; we mirror the JS path explicitly so this stays
    # portable across Python builds that differ from IEEE-754 banker's
    # rounding in their round() default.
    n = math.floor(x)
    d = x - n
    if d < 0.5:
        return n
    if d > 0.5:
        return n + 1
    return n if n % 2 == 0 else n + 1


# ---------------------------------------------------------------------------
# display_value: round-half-even of raw * scale, min 1 when above waiver.
# ---------------------------------------------------------------------------
def display_value(raw_value: float, scale: float, above_waiver: bool) -> int:
    """Mirror TwoTier.displayValue (curve-widget.js:328-331)."""
    if not above_waiver:
        return 0
    return max(1, round_half_even(raw_value * scale))


def normalize_then_round(
    raw_by_key: dict[str, float], above_waiver_by_key: Any
) -> dict[str, Any]:
    """Mirror TwoTier.normalizeThenRound (curve-widget.js:336-343).

    `above_waiver_by_key` may be a callable (JS: predicate over keys) or a
    dict; both reach the same predicate path.
    """
    above = (above_waiver_by_key.get if isinstance(above_waiver_by_key, dict)
             else above_waiver_by_key)
    mx = 0.0
    for v in raw_by_key.values():
        if v > mx:
            mx = v
    scale = 70.0 / mx if mx > 0 else 1.0
    values: dict[str, int] = {}
    for k, v in raw_by_key.items():
        values[k] = display_value(v, scale, above(k))
    return {"values": values, "scale": scale}


# ---------------------------------------------------------------------------
# tail_floor: bottom-up scan to find where the position stops separating.
# ---------------------------------------------------------------------------
def tail_floor(xs: list[float], frac: float = FLOOR_SLOPE_FRAC,
               win: int = FLOOR_WINDOW) -> int:
    """Mirror TwoTier.tailFloor (curve-widget.js:348-356)."""
    if len(xs) <= win:
        return len(xs)
    thr = frac * (xs[0] - xs[-1])
    if not (thr > 0):
        return len(xs)
    # JS: for (s = xs.length - win - 1; s >= 0; s--) → descending scan.
    for s in range(len(xs) - win - 1, -1, -1):
        if (xs[s] - xs[s + win]) / win >= thr:
            return s + win + 1
    return 1


# ---------------------------------------------------------------------------
# bench_mix_for: bench spots per position derived from starter load + flex.
# ---------------------------------------------------------------------------
def bench_mix_for(
    teams: int,
    bench_slots: int,
    slots: dict[str, int],
    flex_count: int,
    flex_eligible: list[str],
    pools: dict[str, list[float]],
) -> dict[str, int]:
    """Mirror TwoTier.benchMixFor (curve-widget.js:369-415)."""
    capacity = teams * bench_slots
    out: dict[str, int] = {pos: 0 for pos in POSITIONS}
    if capacity <= 0:
        return out

    # JS: ranked[pos] = (pools[pos] || []).slice().sort((a, b) => b - a)
    ranked: dict[str, list[float]] = {
        pos: sorted(pools.get(pos) or [], reverse=True) for pos in POSITIONS
    }
    taken: dict[str, int] = {}
    flex_hits: dict[str, int] = {}
    for pos in POSITIONS:
        taken[pos] = teams * (slots.get(pos) or 0)
        flex_hits[pos] = 0

    flex_pool: list[tuple[float, str]] = []
    for pos in POSITIONS:
        if pos not in flex_eligible:
            continue
        for x in ranked[pos][taken[pos]:]:
            flex_pool.append((x, pos))
    flex_pool.sort(key=lambda t: -t[0])
    # JS: flexPool.slice(0, teams * flexCount).forEach(...) → mutate flexHits
    for _, pos in flex_pool[: teams * flex_count]:
        flex_hits[pos] += 1

    starters: dict[str, int] = {}
    load: dict[str, float] = {}
    cap: dict[str, int] = {}
    for pos in POSITIONS:
        starters[pos] = taken[pos] + flex_hits[pos]
        load[pos] = (slots.get(pos) or 0) + flex_hits[pos] / teams
        cap[pos] = max(0, tail_floor(ranked[pos]) - starters[pos])

    alloc: dict[str, float] = {pos: 0.0 for pos in POSITIONS}
    remaining = float(capacity)
    for _ in range(8):
        open_pos = [p for p in POSITIONS
                    if alloc[p] < cap[p] - 1e-9 and load[p] > 0]
        weight = sum(load[p] for p in open_pos)
        if not open_pos or weight <= 0 or remaining < 1e-9:
            break
        for p in open_pos:
            alloc[p] = min(cap[p], alloc[p] + remaining * load[p] / weight)
        remaining = capacity - sum(alloc[p] for p in POSITIONS)

    for pos in POSITIONS:
        out[pos] = math.floor(alloc[pos])

    # Largest-remainder rounding: order by descending fractional remainder.
    order = sorted(
        POSITIONS,
        key=lambda p: -(alloc[p] - math.floor(alloc[p])),
    )
    guard = 0
    while sum(out[p] for p in POSITIONS) < capacity and guard < 10000:
        p = order[guard % len(order)]
        if out[p] < cap[p]:
            out[p] += 1
        guard += 1
    return out


# ---------------------------------------------------------------------------
# inward_bounds: round slider bounds INWARD to grid steps.
# ---------------------------------------------------------------------------
def inward_bounds(lo: float, hi: float, step: float = 0.001) -> list[float]:
    """Mirror TwoTier.inwardBounds (curve-widget.js:419-421)."""
    return [
        math.ceil(lo / step - 1e-12) * step,
        math.floor(hi / step + 1e-12) * step,
    ]


# ---------------------------------------------------------------------------
# build_position_tiers: frozen pool structure for one league config.
# ---------------------------------------------------------------------------
def build_position_tiers(
    lists: dict[str, list[dict[str, Any]]],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Mirror TwoTier.buildPositionTiers (curve-widget.js:429-480)."""
    teams = cfg["teams"]
    slots = cfg["slots"]
    flex_count = cfg["flexCount"]
    flex_eligible = cfg["flexEligible"]
    bench_mix = cfg["benchMix"]

    # JS: sort by (-x, str(id)); entries filtered to finite x.
    by_pos: dict[str, list[dict[str, Any]]] = {}
    for pos in POSITIONS:
        rows = []
        for d in (lists.get(pos) or []):
            x = d["x"]
            try:
                xf = float(x)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(xf):
                continue
            rows.append({"id": d["id"], "x": xf})
        rows.sort(key=lambda d: (-d["x"], str(d["id"])))
        by_pos[pos] = rows

    dedicated: set[str] = set()
    starters: set[str] = set()
    for pos in POSITIONS:
        for d in by_pos[pos][: teams * (slots.get(pos) or 0)]:
            dedicated.add(d["id"])
            starters.add(d["id"])

    flex_pool: list[dict[str, Any]] = []
    for pos in POSITIONS:
        if pos not in flex_eligible:
            continue
        for d in by_pos[pos]:
            if d["id"] not in dedicated:
                flex_pool.append(d)
    flex_pool.sort(key=lambda d: (-d["x"], str(d["id"])))
    for d in flex_pool[: teams * (flex_count or 0)]:
        starters.add(d["id"])

    rostered = set(starters)
    bench: set[str] = set()
    for pos in POSITIONS:
        cap = bench_mix.get(pos) or 0
        # JS: byPos[pos].filter(d => !rostered.has(d.id)).slice(0, cap)
        # → top-`cap` non-rostered players at this position (already -x sorted).
        eligible_non = [d for d in by_pos[pos] if d["id"] not in rostered]
        for d in eligible_non[:cap]:
            bench.add(d["id"])
            rostered.add(d["id"])

    tiers: dict[str, Any] = {}
    for pos in POSITIONS:
        lst = by_pos[pos]
        if not lst:
            tiers[pos] = None
            continue
        nxt = next((d for d in lst if d["id"] not in rostered), None)
        rw = nxt["x"] if nxt else 0.0
        s_projs = [d["x"] for d in lst if d["id"] in starters]
        b_projs = [d["x"] for d in lst if d["id"] not in starters]
        if not s_projs:
            rs = lst[0]["x"] + 1
        elif not b_projs:
            rs = lst[-1]["x"] - 1
        else:
            rs = (min(s_projs) + max(b_projs)) / 2
        if not (rs > rw):
            raise ValueError(
                f"build_position_tiers: starter line {rs} must exceed waiver line {rw} at {pos}"
            )
        tau = GLIDE_WIDTH_FRAC * (rs - rw)
        a_bench = b_bench = a_start = b_start = surplus = 0.0
        for d in lst:
            if not (d["x"] > rw):
                continue
            surplus += d["x"] - rw
            a, b = slice_exposures(d["x"], rw, rs, tau)
            if d["id"] in starters:
                a_start += a
                b_start += b
            else:
                a_bench += a
                b_bench += b
        tiers[pos] = {
            "rw": rw,
            "rs": rs,
            "tau": tau,
            "aBench": a_bench,
            "bBench": b_bench,
            "aStart": a_start,
            "bStart": b_start,
            "surplus": surplus,
        }
    return {"tiers": tiers, "starters": starters, "bench": bench, "rostered": rostered}


# ---------------------------------------------------------------------------
# calibrate_position / calibrate_position_feasible.
# ---------------------------------------------------------------------------
def calibrate_position(
    tier: dict[str, Any] | None,
    pie: float,
    bench_share: float = DEFAULT_BENCH_SHARE,
) -> dict[str, Any] | None:
    """Mirror TwoTier.calibratePosition (curve-widget.js:486-502)."""
    if tier is None:
        return None
    if not (tier["surplus"] > 0):
        return {
            **tier,
            "pb": 0,
            "ps": 0,
            "invalid": False,
            "invalidReason": None,
            "benchRaw": 0,
            "starterRaw": 0,
        }
    if not (pie > 0):
        return {
            **tier,
            "pb": None,
            "ps": None,
            "invalid": True,
            "invalidReason": f"cannot calibrate: non-positive pie {pie}",
        }
    try:
        sol = solve_tier_prices(
            tier["aBench"], tier["bBench"], tier["aStart"], tier["bStart"],
            pie, "?", bench_share,
        )
        pb, ps = sol["pb"], sol["ps"]
        return {
            **tier,
            "pb": pb,
            "ps": ps,
            "invalid": False,
            "invalidReason": None,
            "benchRaw": pb * tier["aBench"] + ps * tier["bBench"],
            "starterRaw": pb * tier["aStart"] + ps * tier["bStart"],
        }
    except Exception as e:
        return {
            **tier,
            "pb": None,
            "ps": None,
            "invalid": True,
            "invalidReason": str(e),
        }


def calibrate_position_feasible(
    tier: dict[str, Any] | None,
    pie: float,
    requested_share: float,
    pos: str = "?",
) -> dict[str, Any] | None:
    """Mirror TwoTier.calibratePositionFeasible (curve-widget.js:513-532)."""
    first = calibrate_position(tier, pie, requested_share)
    if first is None or not first.get("invalid"):
        if first is not None:
            first = {**first, "bench_share_used": float(requested_share)}
        return first
    reason = str(first.get("invalidReason") or "")
    if not _ECON_BREAK_RE.search(reason):
        return first
    lo = 0.01
    hi = float(requested_share)
    for _ in range(20):
        mid = (lo + hi) / 2
        attempt = calibrate_position(tier, pie, mid)
        if attempt is not None and not attempt.get("invalid"):
            lo = mid
        else:
            hi = mid
    best = calibrate_position(tier, pie, lo)
    if best is None or best.get("invalid"):
        return first
    best = {**best, "bench_share_used": lo}
    return best


# Imported lazily to avoid regex dep in older runtimes; we use re at top.
import re  # noqa: E402

_ECON_BREAK_RE = re.compile(r"does not exceed|economics break", re.IGNORECASE)


# ---------------------------------------------------------------------------
# price_for_projection.
# ---------------------------------------------------------------------------
def price_for_projection(x: float, cal: dict[str, Any] | None) -> float:
    """Mirror TwoTier.priceForProjection (curve-widget.js:537-542)."""
    if not cal or cal.get("invalid") or cal.get("pb") is None:
        return 0.0
    if not (x > cal["rw"]):
        return 0.0
    a, b = slice_exposures(x, cal["rw"], cal["rs"], cal["tau"])
    return cal["pb"] * a + cal["ps"] * b


# ---------------------------------------------------------------------------
# skill_bench_shares / skill_bench_share.
# ---------------------------------------------------------------------------
def skill_bench_shares(share: float) -> dict[str, float]:
    """Mirror TwoTier.skillBenchShares (curve-widget.js:549-552)."""
    s = check_share(share)
    return {"default": s, "QB": s, "RB": s, "WR": s, "TE": s}


def skill_bench_share(shares: dict[str, Any] | None, pos: str) -> float:
    """Mirror TwoTier.skillBenchShare (curve-widget.js:553-560)."""
    if not isinstance(shares, dict):
        return DEFAULT_BENCH_SHARE
    v = shares.get(pos)
    if isinstance(v, (int, float)) and math.isfinite(float(v)):
        return check_share(v)
    d = shares.get("default")
    if isinstance(d, (int, float)) and math.isfinite(float(d)):
        return check_share(d)
    return DEFAULT_BENCH_SHARE


# ---------------------------------------------------------------------------
# legacy_bench_mix_for: scale LEGACY_BENCH_MIX_12 by team count.
# ---------------------------------------------------------------------------
def legacy_bench_mix_for(teams: int) -> dict[str, int]:
    """Mirror TwoTier.legacyBenchMixFor (curve-widget.js:566-572)."""
    return {
        pos: int(math.floor(LEGACY_BENCH_MIX_12[pos] * teams / 12 + 0.5))
        for pos in POSITIONS
    }


# ---------------------------------------------------------------------------
# Public namespace mirroring `TwoTier` for parity test consumption.
# ---------------------------------------------------------------------------
TwoTier = {
    "POSITIONS": POSITIONS,
    "DEFAULT_BENCH_SHARE": DEFAULT_BENCH_SHARE,
    "GLIDE_WIDTH_FRAC": GLIDE_WIDTH_FRAC,
    "REF_SLOTS": REF_SLOTS,
    "REF_FLEX_COUNT": REF_FLEX_COUNT,
    "REF_FLEX_ELIGIBLE": REF_FLEX_ELIGIBLE,
    "WITHHELD_FLAG": WITHHELD_FLAG,
    "softplus": softplus,
    "sliceExposures": slice_exposures,
    "checkShare": check_share,
    "solveTierPrices": solve_tier_prices,
    "feasibleAt": feasible_at,
    "feasibleBenchShareInterval": feasible_bench_share_interval,
    "sliderBounds": slider_bounds,
    "roundHalfEven": round_half_even,
    "displayValue": display_value,
    "normalizeThenRound": normalize_then_round,
    "benchMixFor": bench_mix_for,
    "tailFloor": tail_floor,
    "REF_BENCH_SLOTS": REF_BENCH_SLOTS,
    "LEGACY_BENCH_MIX_12": LEGACY_BENCH_MIX_12,
    "legacyBenchMixFor": legacy_bench_mix_for,
    "inwardBounds": inward_bounds,
    "buildPositionTiers": build_position_tiers,
    "calibratePosition": calibrate_position,
    "calibratePositionFeasible": calibrate_position_feasible,
    "priceForProjection": price_for_projection,
    "skillBenchShares": skill_bench_shares,
    "skillBenchShare": skill_bench_share,
}