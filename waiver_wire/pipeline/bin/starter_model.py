"""Two-tier marginal-price trade value model (replaces utilization weights 2026-09-22).

VALUE ABOVE WAIVERS, PRICED IN TWO TIERS
A player's raw surplus is his per-game projection minus the positional
waiver line (the next-unrostered player's projection), floored at zero.
That surplus is priced slice by slice: slices between the waiver line and
the starter line pay the BENCH rate; slices above the starter line pay the
STARTER rate. The rate glides smoothly from bench to starter across the
starter line (no cliffs): a slice right at the line pays a blend of the
two rates.

The starter line is the midpoint between the last starter's and the first
bench player's projection (flex starters count as starters). The glide
width is 25% of (starter line - waiver line), per position -- narrow
enough that true starters and true bench players keep their tier
economics, wide enough that neighbors near the line are priced alike.

FIXED-PIE CALIBRATION
Per position, the two rates are SOLVED (not chosen) from the fixed-pie
identity: bench players' total value = exactly 15% of the positional pie,
starters' = exactly 85%. The positional pies are ESPN-measured
(lottery/bin/espn_pies.json); K/DST pies sit on top of the skill pie, so
adding them cannot dilute skill values. Fail closed: if the solved starter
rate does not exceed the bench rate, the build aborts.

In the tau -> 0 limit this reduces exactly to the elboberto workbook's
hard two-tier pricing (bench band at the cheap rate, above-starter points
at the premium rate).

BENCH SHARE IS A UI PARAMETER (Jeremy 2026-09-22)
The bench/starter split is user-settable, default 0.15, applied per
position: solve_tier_prices() and build_model() take bench_share (a scalar
or a {pos: share} dict). The UI exposes it as a BOUNDED SLIDER, not a free
input: feasible_bench_share_interval() bisects the share range where the
2x2 solve yields p_b > 0 and p_s > p_b, per (position, league config); the
slider's min/max is the intersection across positions
(slider_bounds()), recomputed when the league config changes, with a
recommended-point tick at 0.15. If 0.15 ever falls outside a config's
feasible range, recommended_share_state() reports a fail-closed display
state with a plain-words reason -- never a silent clamp. The solve's
fail-closed guard stays as a backstop (defense in depth); normal UI use
cannot reach it. Infeasible (config, share) combos mark that position
invalid (tiers[pos]["invalid"], plain-words reason, values priced at zero)
instead of silently shipping; publishing pipelines must refuse a model
with invalid positions.

LIVE CLIENT-SIDE RE-SOLVE
The browser mirror lottery/assets/two_tier.js re-solves per position when
the slider moves, from the baked live_payload() (per-config lines,
exposures, pies). Python/JS mirrors are kept in sync by the shared test
vector tests/golden/two_tier_vectors.json.

DISPLAY
  display(p) = round(value(p) * scale); min 1 if proj > waiver line else 0
  scale      = 70 / max(value over the pool)   (one shared scale)
Normalize-then-round (approved 2026-09-22): the single 70-max multiplier
applies BEFORE rounding; rounding happens at display only. The bench/
starter pie identity is verified pre-rounding. A rounding-first ordering
(round raw values, then scale) is the named defect: on pools where the
max raw value is below 70 the scale amplifies the rounding error and the
top displayed player misses 70 -- see
tests/unit/test_two_tier_mirrors.py::test_normalize_then_round_negative.

The chart's trade-value page is display-only (values are baked by the
pipeline); there is no live client-side copy of this model in the
trade-value chart. The waiver dashboard carries its own older JS port --
flagged for a separate two-tier port, not mirrored here.
"""
import json
import math
from pathlib import Path

POSITIONS = ["QB", "RB", "WR", "TE", "K", "DST"]

# Approved 2026-09-21: the glide width is 25% of (starter line - waiver
# line), per position. Scale-relative: kickers' tiny spread gets a narrow
# glide, running backs' wide spread a wide one.
GLIDE_WIDTH_FRAC = 0.25

# Bench share of each positional pie: the UI parameter (Jeremy 2026-09-22).
# User-settable via a bounded slider, default 0.15, applied per position.
# BENCH_SHARE / STARTER_SHARE remain as legacy aliases for the default.
DEFAULT_BENCH_SHARE = 0.15
BENCH_SHARE = DEFAULT_BENCH_SHARE
STARTER_SHARE = 1.0 - DEFAULT_BENCH_SHARE

# Arbitrary gap used only for degenerate pools (no starters, or everyone a
# starter). Those pools carry no surplus, so the line placement is harmless.
_EDGE_GAP = 1.0

# ESPN-measured positional pies, written by the ESPN refresh step.
PIES_PATH = Path(__file__).resolve().parent / "espn_pies.json"

DEFAULT_STATE = {
    "teams": 12,
    "slots": {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "K": 1, "DST": 1},
    "bench": 6,
    # Bench depths align with the elboberto workbook reference (2026-09-22):
    # QB 10 / TE 10 (not 6). The two-tier calibration REQUIRES this depth:
    # with 6-deep QB/TE benches, bench surplus is < 14% of the pool, so a
    # 15/85 split mathematically forces the bench rate ABOVE the starter
    # rate and the p_s > p_b guard fails closed on every build. At 10-deep,
    # bench surplus is ~18-22% of the pool and the solve yields a genuine
    # starter premium (workbook: QB 0.256, TE 0.181). RB/WR keep the deeper
    # model depths (27/33), which already satisfy the constraint.
    # K/DST are streamed, rarely stashed: ~3 bench slots each league-wide
    # (15 rostered -> K16/DST16 replacement). Changing any bench_mix shifts
    # that position's waiver line and all its chart values; K/DST model
    # their own pools independently.
    "bench_mix": {"QB": 10, "RB": 27, "WR": 33, "TE": 10, "K": 3, "DST": 3},
    "flex_types": [{"count": 1, "eligible": ["RB", "WR", "TE"]}],
}


def load_pies(scoring="half_ppr", teams=12):
    """ESPN-measured positional pies for one scoring and team count.

    Fail closed: missing file or missing key raises -- a calibration with
    guessed pies would silently re-weight every position."""
    try:
        data = json.loads(PIES_PATH.read_text())
    except OSError as e:
        raise ValueError(
            "two-tier calibration needs %s (run the ESPN refresh step)" % PIES_PATH
        ) from e
    try:
        return dict(data["pies"][scoring][str(teams)])
    except KeyError as e:
        raise ValueError(
            "no pies for scoring=%s teams=%s in %s" % (scoring, teams, PIES_PATH)
        ) from e


def _sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def _softplus(z):
    """log(1 + e^z), numerically stable. d/dz softplus = sigmoid."""
    return math.log1p(math.exp(-abs(z))) + (z if z > 0 else 0.0)


def _slice_exposures(x, rw, rs, tau):
    """Bench-rate (A) and starter-rate (B) exposures of one player's surplus.

    value(x) = p_bench * A + p_starter * B, where the marginal price glides
    from p_bench to p_starter across the starter line rs:
        m(t) = p_b + (p_s - p_b) * sigmoid((t - rs) / tau)
    Integrated in closed form from the waiver line rw to x:
        v = p_b*(x - rw) + (p_s - p_b)*tau*(S((x-rs)/tau) - S((rw-rs)/tau))
    with S = softplus. Returns (0, 0) at or below the waiver line."""
    if x <= rw:
        return (0.0, 0.0)
    glide = tau * (_softplus((x - rs) / tau) - _softplus((rw - rs) / tau))
    return ((x - rw) - glide, glide)


def _check_share(share, pos="?"):
    """A bench share is a fraction of the pie: strictly between 0 and 1.

    Fail closed on anything else -- a share of 0 prices every bench slice
    at nothing, a share of 1 leaves starters with nothing, and anything
    outside [0, 1] is not a share of anything."""
    try:
        s = float(share)
    except (TypeError, ValueError):
        raise ValueError(
            "cannot calibrate %s: bench share %r is not a number" % (pos, share))
    if not 0.0 < s < 1.0:
        raise ValueError(
            "cannot calibrate %s: bench share %r is not between 0 and 1 "
            "(exclusive)" % (pos, share))
    return s


def solve_tier_prices(a_bench, b_bench, a_start, b_start, pie, pos="?",
                      bench_share=DEFAULT_BENCH_SHARE):
    """Solve the per-position 2x2 system from the fixed-pie identity.

      a_bench * p_b + b_bench * p_s = bench_share * pie   (bench total)
      a_start * p_b + b_start * p_s = (1-bench_share) * pie (starter total)

    where a_/b_ are the summed bench-rate / starter-rate slice exposures.
    bench_share is the UI parameter (default 0.15); the identity is exact
    pre-rounding at whatever share is passed.
    Fail closed: degenerate exposures, a non-(0,1) share, a non-positive
    bench rate, or a starter rate that does not exceed the bench rate all
    raise -- pricing would be economically backwards. This guard is the
    backstop behind the bounded slider: normal UI use cannot reach it."""
    share = _check_share(bench_share, pos)
    starter_share = 1.0 - share
    if not pie > 0:
        raise ValueError("cannot calibrate %s: non-positive pie %r" % (pos, pie))
    det = a_bench * b_start - a_start * b_bench
    if det == 0:
        raise ValueError(
            "cannot calibrate %s: degenerate slice exposures "
            "(a_bench=%r b_bench=%r a_start=%r b_start=%r)" %
            (pos, a_bench, b_bench, a_start, b_start))
    p_b = (share * pie * b_start - b_bench * starter_share * pie) / det
    p_s = (a_bench * starter_share * pie - share * pie * a_start) / det
    if not p_b > 0:
        raise ValueError(
            "cannot calibrate %s at bench share %r: bench rate %r not "
            "positive" % (pos, share, p_b))
    if not p_s > p_b:
        raise ValueError(
            "cannot calibrate %s at bench share %r: starter rate %r does not "
            "exceed bench rate %r -- the economics break (bench slices "
            "would pay more than starter slices)" % (pos, share, p_s, p_b))
    # Exactness: the solved rates must reproduce the split pre-rounding.
    bench_total = p_b * a_bench + p_s * b_bench
    start_total = p_b * a_start + p_s * b_start
    tol = 1e-9 * pie
    if abs(bench_total - share * pie) > tol or \
            abs(start_total - starter_share * pie) > tol:
        raise ValueError(
            "cannot calibrate %s at bench share %r: solved rates miss the "
            "split (bench=%r starter=%r pie=%r)" %
            (pos, share, bench_total, start_total, pie))
    return p_b, p_s


def _normalize_shares(bench_share):
    """bench_share: scalar or {pos: share}. Returns {pos: share} validated."""
    if isinstance(bench_share, dict):
        shares = dict(bench_share)
        missing = [p for p in POSITIONS if p not in shares]
        if missing:
            raise ValueError(
                "bench_share dict is missing positions: %r" % (missing,))
    else:
        shares = {p: bench_share for p in POSITIONS}
    return {p: _check_share(s, p) for p, s in shares.items()}


def build_model(proj, state=None, positions=None, pies=None, calibrate=True,
                bench_share=DEFAULT_BENCH_SHARE, on_infeasible="mark"):
    """proj: dict pid -> per-game projection (None if missing).
    positions: optional dict pid -> pos (required when pids are not
      (norm, pos) tuples, e.g. numeric canonical player_keys).
    pies: dict pos -> fixed positional pie (ESPN-measured). REQUIRED --
      use load_pies(scoring, teams). A guessed pie silently re-weights
      every position, so there is no default.
    calibrate: if False, skip the tier solve (tiers carry pb/ps=None).
      Used for pie MEASUREMENT (pool shape without pricing). The full
      calibration still fails closed on infeasible shapes.
    bench_share: the UI parameter -- a scalar or {pos: share} dict,
      default 0.15, applied per position. Each position's 2x2 solve is
      parametric in its share.
    on_infeasible: "mark" (default) records an infeasible (config, share)
      combo as tiers[pos]["invalid"] with a plain-words reason, prices the
      position's values at zero, and lists it in invalid_positions --
      never silently ships. "raise" restores the old abort-the-build
      behavior. Publishing pipelines must refuse a model whose
      invalid_positions is non-empty.
    Returns dict with replacements, raw values, rostered sets, the frozen
    pricing struct keyed by pid, and invalid_positions {pos: reason}."""
    if pies is None and calibrate:
        raise ValueError(
            "build_model requires pies= (ESPN-measured positional pies); "
            "use starter_model.load_pies(scoring, teams)")
    if on_infeasible not in ("mark", "raise"):
        raise ValueError(
            "build_model: on_infeasible must be 'mark' or 'raise', got %r"
            % (on_infeasible,))
    shares = _normalize_shares(bench_share)
    st = dict(DEFAULT_STATE)
    if state:
        st.update(state)
    teams = st["teams"]
    # POSITIONS may carry K/DST while a caller-supplied state only defines
    # skill-position slots (e.g. the waiver boundary). Missing positions
    # default to 0 dedicated/bench slots: they model no rostered pool in
    # that context instead of raising KeyError.
    slots = {pos: st["slots"].get(pos, 0) for pos in POSITIONS}
    bench_mix = {pos: st["bench_mix"].get(pos, 0) for pos in POSITIONS}
    flex_types = [t for t in st["flex_types"] if t["count"] > 0 and t["eligible"]]
    flex_eligible = sorted({p for t in flex_types for p in t["eligible"]})

    # Canonical identity (2026-09-18): pids may be numeric player_keys.
    # positions maps pid -> pos in that case; tuple pids carry (norm, pos).
    def _pos(pid):
        if positions is not None:
            return positions.get(pid)
        return pid[1]

    # Fail closed on unknown positions: a pid whose position is missing or
    # outside POSITIONS must never be silently priced (or silently dropped).
    for pid in proj:
        if proj[pid] is None:
            continue
        if _pos(pid) not in POSITIONS:
            raise ValueError(
                "build_model: unknown position %r for pid %r" % (_pos(pid), pid))

    def _sort_key(pid):
        tie = pid[0] if isinstance(pid, tuple) else pid
        return (-proj[pid], tie)

    by_pos = {}
    for pos in POSITIONS:
        lst = [pid for pid in proj if proj[pid] is not None
               and _pos(pid) == pos]
        lst.sort(key=_sort_key)
        by_pos[pos] = lst

    rostered, dedicated, flex_starters = set(), set(), set()
    for pos in POSITIONS:
        for pid in by_pos[pos][:teams * slots[pos]]:
            rostered.add(pid)
            dedicated.add(pid)
    flex_pool = [pid for pid in proj
                 if proj[pid] is not None and _pos(pid) in flex_eligible
                 and pid not in dedicated]
    flex_pool.sort(key=_sort_key)
    total_flex = sum(t["count"] for t in flex_types)
    for pid in flex_pool[:teams * total_flex]:
        rostered.add(pid)
        flex_starters.add(pid)
    for pos in POSITIONS:
        extra = [pid for pid in by_pos[pos] if pid not in rostered]
        for pid in extra[:bench_mix[pos]]:
            rostered.add(pid)

    # Waiver lines: the next-unrostered player's projection per position.
    replacements = {}
    for pos in POSITIONS:
        nxt = next((pid for pid in by_pos[pos] if pid not in rostered), None)
        replacements[pos] = proj[nxt] if nxt else 0.0

    # --- two-tier pricing lines (projection space) ---
    # rs[pos]: midpoint between the last starter's and the first bench
    # player's projection. Flex starters count as starters. tau[pos]: the
    # glide width, 25% of (starter line - waiver line).
    starter_pids = dedicated | flex_starters
    tiers = {}
    for pos in POSITIONS:
        lst = by_pos[pos]
        rw = replacements[pos]
        if not lst:
            tiers[pos] = None
            continue
        starter_projs = [proj[pid] for pid in lst if pid in starter_pids]
        bench_projs = [proj[pid] for pid in lst if pid not in starter_pids]
        if not starter_projs:
            rs = proj[lst[0]] + _EDGE_GAP
        elif not bench_projs:
            rs = proj[lst[-1]] - _EDGE_GAP
        else:
            rs = (min(starter_projs) + max(bench_projs)) / 2.0
        if not rs > rw:
            raise ValueError(
                "build_model: starter line %r must exceed waiver line %r "
                "at %s" % (rs, rw, pos))
        tau = GLIDE_WIDTH_FRAC * (rs - rw)
        tiers[pos] = {"rw": rw, "rs": rs, "tau": tau,
                      "pb": None, "ps": None}

    # --- per-position calibration at its bench share ---
    invalid_positions = {}
    for pos in POSITIONS:
        t = tiers[pos]
        if t is None:
            continue
        t["bench_share"] = shares[pos]
        a_b = b_b = a_s = b_s = 0.0
        surplus = 0.0
        for pid in by_pos[pos]:
            x = proj[pid]
            if x <= t["rw"]:
                continue
            surplus += x - t["rw"]
            a, b = _slice_exposures(x, t["rw"], t["rs"], t["tau"])
            if pid in starter_pids:
                a_s += a
                b_s += b
            else:
                a_b += a
                b_b += b
        t["a_bench"], t["b_bench"] = a_b, b_b
        t["a_start"], t["b_start"] = a_s, b_s
        if surplus <= 0:
            # Empty tier: nothing above the waiver line, so nothing to
            # price. Rates stay zero; every value is zero. (A position with
            # surplus but degenerate exposures fails closed in the solver.)
            t["pb"], t["ps"] = 0.0, 0.0
            continue
        if not calibrate:
            continue
        if pos not in pies:
            raise ValueError(
                "build_model: no pie for position %s" % pos)
        try:
            t["pb"], t["ps"] = solve_tier_prices(
                a_b, b_b, a_s, b_s, pies[pos], pos,
                bench_share=shares[pos])
        except ValueError as e:
            # Fail closed per position: the economics break at this
            # (config, share) combo, so the position is marked invalid --
            # priced at zero, never silently shipped. Publishing
            # pipelines must refuse invalid_positions.
            if on_infeasible == "raise":
                raise
            t["pb"], t["ps"] = None, None
            t["invalid"] = True
            t["invalid_reason"] = str(e)
            invalid_positions[pos] = str(e)
            continue
        # Record the exact pre-rounding split for the audit trail.
        t["bench_raw"] = t["pb"] * a_b + t["ps"] * b_b
        t["starter_raw"] = t["pb"] * a_s + t["ps"] * b_s

    # Frozen pool structure, for pricing hypothetical projections against
    # this league context (comparison legs: price_for_projection).
    struct = {
        "teams": teams,
        "slots": dict(slots),
        "flex_types": [dict(t) for t in flex_types],
        "tiers": {pos: (dict(t) if t else None) for pos, t in tiers.items()},
    }

    def _price(pid):
        return price_for_projection(proj[pid], _pos(pid), struct)

    raw = {}
    if calibrate:
        for pid in proj:
            if proj[pid] is None:
                continue
            raw[pid] = _price(pid)

    # Enforcement: bench must total exactly its share per position,
    # pre-rounding. Invalid positions are skipped here -- they carry no
    # rates and their values are zeroed below.
    if not calibrate:
        # Pool-measurement mode: skip pricing and enforcement.
        return {"replacements": replacements, "raw": raw,
                "rostered": rostered, "struct": struct,
                "starters": starter_pids, "bench": rostered - starter_pids,
                "invalid_positions": invalid_positions}
    for pos in POSITIONS:
        t = tiers[pos]
        if t is None or t.get("invalid") or t["pb"] == 0.0:
            continue
        pie = pies[pos]
        share = shares[pos]
        tol = 1e-9 * pie
        if abs(t["bench_raw"] - share * pie) > tol or \
                abs(t["starter_raw"] - (1.0 - share) * pie) > tol:
            raise ValueError(
                "build_model: %s misses the %g/%g split post-solve"
                % (pos, share * 100, (1.0 - share) * 100))

    return {"replacements": replacements, "raw": raw,
            "rostered": rostered, "struct": struct,
            "starters": starter_pids, "bench": rostered - starter_pids,
            "invalid_positions": invalid_positions}


def price_for_projection(x, pos, struct):
    """Two-tier value of a hypothetical per-game projection x at pos,
    evaluated against a frozen pool's pricing (its lines, glide width, and
    calibrated rates).

    Comparison legs use this: the player's OWN projection varies while the
    league context (lines, rates, waiver line, scale) stays frozen, so a
    leg-to-leg delta is purely "what is he worth if his projection changes"
    -- smooth in x, with no field-reordering or waiver-line artifacts. A
    large ECR-vs-blend projection move still moves the player along the
    price glide (his slices reprice against HIS projection); the frozen
    pool's ordering never enters.

    A position marked invalid (infeasible calibration) prices at zero --
    never a guessed value.
    """
    t = struct["tiers"].get(pos)
    if t is None or x is None:
        return 0.0
    if t.get("invalid") or t.get("pb") is None or t.get("ps") is None:
        return 0.0
    if x <= t["rw"]:
        return 0.0
    a, b = _slice_exposures(x, t["rw"], t["rs"], t["tau"])
    return t["pb"] * a + t["ps"] * b


def bench_share_report(values, model, pos_of, expected_share=DEFAULT_BENCH_SHARE):
    """Per-position bench share of (possibly rounded) display values.

    values: dict pid -> number. model: build_model's return (carries the
    starter/bench pid partition). pos_of: pid -> pos. expected_share: the
    bench share the model was calibrated at (the UI parameter; default
    0.15). Returns {pos: {"bench": b, "starter": s,
    "bench_share": b/(b+s) or None, "expected": expected_share}}.
    The pipeline asserts bench_share within tolerance of the configured
    share on DISPLAY values; build_model asserts exactness on pre-rounding
    values itself. Rounding moves the display ratio around the calibrated
    split -- that is expected, not a defect."""
    starters = model.get("starters", set())
    out = {}
    for pos in POSITIONS:
        b = s = 0.0
        for pid, v in values.items():
            if not v or pos_of(pid) != pos:
                continue
            if pid in starters:
                s += v
            else:
                b += v
        tot = b + s
        out[pos] = {"bench": b, "starter": s,
                    "bench_share": (b / tot if tot > 0 else None),
                    "expected": expected_share}
    return out


def _feasible_at(a_bench, b_bench, a_start, b_start, pie, share, pos="?"):
    """Feasibility predicate: the 2x2 solve succeeds at this bench share."""
    try:
        solve_tier_prices(a_bench, b_bench, a_start, b_start, pie, pos,
                          bench_share=share)
        return True
    except ValueError:
        return False


def feasible_bench_share_interval(a_bench, b_bench, a_start, b_start, pie,
                                  pos="?", tol=1e-4):
    """The bench-share range where the economics hold, via bisection.

    Returns (lo, hi): the interval of bench shares where the 2x2 solve
    yields p_b > 0 and p_s > p_b. The solved rates are linear in the
    share, so each feasibility condition is an interval and the feasible
    set is contiguous -- bisection on the predicate is exact. Returns
    None when the recommended default (0.15) is itself infeasible: the UI
    must show the fail-closed display state (see recommended_share_state),
    never a silent clamp to something nearby.

    a_/b_ are the summed slice exposures for one (position, league
    config); compute them from build_model's tiers (t["a_bench"] etc.)
    or live_payload()."""
    feasible = lambda s: _feasible_at(a_bench, b_bench, a_start, b_start,
                                      pie, s, pos)
    if not feasible(DEFAULT_BENCH_SHARE):
        return None
    lo, hi = 1e-6, DEFAULT_BENCH_SHARE
    while hi - lo > tol:
        mid = (lo + hi) / 2.0
        if feasible(mid):
            hi = mid
        else:
            lo = mid
    lo_edge = hi
    lo, hi = DEFAULT_BENCH_SHARE, 1.0 - 1e-6
    while hi - lo > tol:
        mid = (lo + hi) / 2.0
        if feasible(mid):
            lo = mid
        else:
            hi = mid
    return (lo_edge, lo)


def slider_bounds(intervals):
    """Slider min/max for the active league config.

    intervals: {pos: (lo, hi)} from feasible_bench_share_interval. The
    slider's range is the INTERSECTION across positions, so no reachable
    setting can break any position's economics. Returns (lo, hi), or
    None when the intersection is empty (fail closed -- no valid setting
    exists for this config)."""
    los = [iv[0] for iv in intervals.values()]
    his = [iv[1] for iv in intervals.values()]
    lo, hi = max(los), min(his)
    if lo > hi:
        return None
    return (lo, hi)


def recommended_share_state(lo, hi, share=DEFAULT_BENCH_SHARE, teams=None,
                            pos=None):
    """Is the recommended bench share reachable? Fail-closed display state.

    Returns {"ok": True, ...} when share sits inside [lo, hi]; otherwise
    {"ok": False, "reason": <plain-words reason>} -- the UI shows the
    reason instead of values, never a silent clamp to a nearby share.
    lo/hi None (empty intersection or an infeasible position) also fails
    closed. pos names the offending position when known."""
    where = ("for %s-team leagues" % teams) if teams else "for this league setup"
    if lo is None or hi is None:
        return {"ok": False,
                "reason": ("The bench-share slider has no valid setting %s: "
                           "no bench share keeps every position's starter "
                           "rate above its bench rate. No values are shown "
                           "rather than wrong ones." % where)}
    if not lo <= share <= hi:
        return {"ok": False,
                "reason": ("The recommended %g%% bench share doesn't work %s%s: "
                           "at %g%% the calibration would price bench slices "
                           "at or above starter slices -- the economics "
                           "break. No values are shown rather than wrong "
                           "ones." % (share * 100, where,
                                      (" for " + pos) if pos else "",
                                      share * 100))}
    return {"ok": True, "lo": lo, "hi": hi, "share": share,
            "reason": None}


def live_payload(proj, state=None, positions=None, pies=None, teams=None,
                 bench_share=DEFAULT_BENCH_SHARE):
    """Bake the per-league-config payload for live client-side re-solving.

    Returns {"teams", "bench_share_default", "positions": {pos: {
    "rw", "rs", "tau", "pie", "a_b", "b_b", "a_s", "b_s",
    "bench_share", "pb", "ps", "invalid", "invalid_reason"}}}.
    The browser mirror (lottery/assets/two_tier.js) re-solves each
    position at the slider's share from a_b/b_b/a_s/b_s/pie and reprices
    players from their projections via the frozen lines (rw, rs, tau);
    per-player exposures are recomputed client-side, so they are not
    baked. Invalid positions ride along with their plain-words reason
    for the fail-closed display state."""
    shares = _normalize_shares(bench_share)
    m = build_model(proj, state, positions, pies,
                    bench_share=bench_share, on_infeasible="mark")
    out = {}
    for pos in POSITIONS:
        t = m["struct"]["tiers"][pos]
        if t is None:
            continue
        out[pos] = {"rw": t["rw"], "rs": t["rs"], "tau": t["tau"],
                    "pie": pies.get(pos),
                    "a_b": t.get("a_bench", 0.0),
                    "b_b": t.get("b_bench", 0.0),
                    "a_s": t.get("a_start", 0.0),
                    "b_s": t.get("b_start", 0.0),
                    "bench_share": shares[pos],
                    "pb": t.get("pb"), "ps": t.get("ps"),
                    "invalid": bool(t.get("invalid")),
                    "invalid_reason": t.get("invalid_reason")}
    return {"teams": teams, "bench_share_default": DEFAULT_BENCH_SHARE,
            "positions": out,
            "invalid_positions": m["invalid_positions"]}


def trade_values(proj, state=None, positions=None, pies=None,
                bench_share=DEFAULT_BENCH_SHARE, on_infeasible="mark"):
    """Full display values: dict pid -> int, same as the chart shows.

    Normalize-then-round (approved 2026-09-22): one shared scale per pool,
    scale = 70 / max(raw value), applied to full-precision raw values
    BEFORE rounding; rounding happens at display only. The top displayed
    player lands exactly on 70 and near-tie ordering follows the
    full-precision ordering. bench_share is the UI parameter (scalar or
    {pos: share}); on_infeasible="mark" marks infeasible positions invalid
    (display 0) instead of aborting the build."""
    m = build_model(proj, state, positions, pies, bench_share=bench_share,
                    on_infeasible=on_infeasible)
    mx = max([0.0] + list(m["raw"].values()))
    scale = 70.0 / mx if mx > 0 else 1.0
    return _finalize(proj, m, scale, positions), m


def trade_values_pinned(proj, proj_frozen, state=None, positions=None,
                        pies=None, bench_share=DEFAULT_BENCH_SHARE,
                        on_infeasible="mark"):
    """Display values with the scale pinned to the frozen pool's max raw.

    The Monday step reprices projections but must not move the chart's own
    scale: a star's big week would otherwise shrink everyone else's number
    with no new information about them. Ranks, lines, rates and the waiver
    line stay live (the waiver line really can move); only the 70-point
    scale is anchored to the frozen chart. bench_share / on_infeasible as
    in trade_values; both pools use the same share."""
    m = build_model(proj, state, positions, pies, bench_share=bench_share,
                    on_infeasible=on_infeasible)
    mf = build_model(proj_frozen, state, positions, pies,
                     bench_share=bench_share, on_infeasible=on_infeasible)
    mx = max([0.0] + list(mf["raw"].values()))
    scale = 70.0 / mx if mx > 0 else 1.0
    return _finalize(proj, m, scale, positions), m


def display_value(raw_value, scale, above_waiver=True):
    """One raw value -> display int. The shared normalize-then-round step.

    scale is the pool's single 70-max multiplier, applied to the
    full-precision raw value BEFORE rounding; rounding is display-only
    (round-half-even; min 1 when above the waiver line, else 0).
    _finalize and build_compare_dashboard_data.anchored_leg_tv both use
    this so the chart's legs cannot drift into a rounding-first variant."""
    if not above_waiver:
        return 0
    return max(1, round(raw_value * scale))


def _finalize(proj, m, scale, positions=None):
    """Normalize-then-round display mapping (approved 2026-09-22).

    The single 70-max multiplier (scale) applies to full-precision raw
    values BEFORE rounding; rounding happens at display only
    (round-half-even; min 1 if proj > waiver line, else 0). The top
    displayed player lands exactly on 70, and near-tie ordering follows
    the full-precision ordering -- rounding can collapse a gap but never
    invert it. Rounding raw values FIRST (the named defect) lets the
    scale amplify the rounding error: on pools whose max raw value is
    below 70 the top displayed player misses 70. Negative-tested in
    tests/unit/test_two_tier_mirrors.py.

    Positions marked invalid (infeasible calibration) display 0 -- no
    value rather than a wrong value; see invalid_positions."""
    def _pos(pid):
        if positions is not None:
            return positions.get(pid)
        return pid[1]
    tiers = m["struct"]["tiers"]
    out = {}
    for pid, r in m["raw"].items():
        pos = _pos(pid)
        t = tiers.get(pos) or {}
        above = (proj[pid] is not None and not t.get("invalid")
                 and proj[pid] > m["replacements"][pos])
        out[pid] = display_value(r, scale, above_waiver=above)
    return out
