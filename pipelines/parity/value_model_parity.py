"""Backend parity reference for value-model.js pure functions.

JEG-327 Phase E parity (JEG-364). Exact port of the FE pure helpers in
app/trade-value-chart/assets/value-model.js. Every function here MUST match
the JS implementation to floating-point tolerance; this module exists so the
parity test script can compare both sides against fixed JSON vectors.

Conventions:
- POSITION_ORDER / DEFAULT_FLEX_ELIGIBLE / MIN_SHARED_FOR_PIE match value-model.js.
- Players are dicts {player_key, name, pos}; values arrive as a dict
  {player_key: numeric}.
- Stable tiebreak by str(name) localeCompare then int(player_key).
- Math is stdlib only; no numpy, no scipy.

Functions (in parity order; each is referenced by the parity test):
  - source_combo_key
  - flex_eligible
  - stable_tiebreak
  - role_map
  - shared_pie_basis
  - bench_share_of
  - scale_to_shared_total
  - shape_to_anchor_peaks_then_shared_total
  - normalize_to_fixed_pie
  - starter_markup_sane
  - fixed_pie_direction_sane
  - peak_agreement
  - projection_roles
  - positional_tier_scales
  - allocation_counts

Do NOT change the formulas here. Mirror them. A parity mismatch is a defect
in either side, and the standing rule ("every regression guard must prove it
catches the bug it names") applies to the parity test script too.
"""
from __future__ import annotations

from typing import Any, Callable

POSITION_ORDER = ["QB", "RB", "WR", "TE"]
DEFAULT_FLEX_ELIGIBLE = ["RB", "WR", "TE"]
MIN_SHARED_FOR_PIE = 40

# JEG-68 / JEG-69 sane bands.
STARTER_MARKUP_SANE_LOW = 0.98
STARTER_MARKUP_SANE_HIGH = 1.6
STARTER_DIRECTION_EPS = 0.01

# Cross-source peak comparison band.
PEAK_AGREEMENT_LOW = 0.80
PEAK_AGREEMENT_HIGH = 1.25


# ---------------------------------------------------------------------------
# Source combo key: exact identity only; never borrow another league size.
# ---------------------------------------------------------------------------
def source_combo_key(source: str, scoring: str, teams: int, qb_slots: int | None) -> str | None:
    """Mirror value-model.js::sourceComboKey.

    `scoring` is the FE spelling: 'ppr'|'full'|'half_ppr'|'half'|'standard'.
    The function normalises the variant spellings to 'full'|'half'|'standard'
    (matching `public.consolidated_values`).
    """
    score_map = {
        "ppr": "full", "full": "full",
        "half_ppr": "half", "half": "half",
        "standard": "standard",
    }
    score = score_map.get(scoring)
    if score is None:
        return None
    if not isinstance(teams, int) or teams <= 0:
        return None
    key = f"{score}_{teams}"
    if source in ("fantasycalc", "fantasycalc_adjusted"):
        if qb_slots not in (1, 2):
            return None
        key += f"_qb{qb_slots}"
    return key


# ---------------------------------------------------------------------------
# Flex eligibility: SUPERFLEX adds QB to the eligible list.
# ---------------------------------------------------------------------------
def flex_eligible(shape: dict[str, Any] | None) -> list[str]:
    """Mirror value-model.js::flexEligible."""
    if shape and shape.get("SUPERFLEX"):
        return ["QB"] + list(DEFAULT_FLEX_ELIGIBLE)
    return list(DEFAULT_FLEX_ELIGIBLE)


# ---------------------------------------------------------------------------
# Stable tiebreak: locale-compare names, then numeric player_key.
# ---------------------------------------------------------------------------
def stable_tiebreak(a: dict[str, Any] | None, b: dict[str, Any] | None) -> int:
    """Mirror value-model.js::stableTiebreak (return -1/0/+1 like Python cmp)."""
    if not a or not b:
        return 0
    name_cmp = str(a.get("name") or "").__lt__(  # type: ignore[operator]
        str(b.get("name") or "")
    )  # Python lacks str < str -> bool returning -1/+1; emulate via (a < b, a > b)
    if name_cmp:
        return -1
    if str(a.get("name") or "") > str(b.get("name") or ""):
        return 1
    pk_a = int(a.get("player_key") or 0)
    pk_b = int(b.get("player_key") or 0)
    return pk_a - pk_b


def _safe_int(v: Any) -> int:
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# roleMap: starter/bench/waiver by VALUE under the active lock.
# ---------------------------------------------------------------------------
def role_map(values: dict[Any, float], player_of: Callable[[Any], dict[str, Any] | None],
             teams: int, shape: dict[str, Any]) -> dict[Any, str]:
    """Mirror value-model.js::roleMap.

    values: {player_key: numeric}
    player_of(player_key) -> {player_key, name, pos, ...}
    """
    teams = _safe_int(teams)
    shape = shape or {}
    rows: list[tuple[float, dict[str, Any], Any]] = []
    for pk, val in values.items():
        player = player_of(pk)
        if player is None or player.get("pos") not in POSITION_ORDER:
            continue
        try:
            num = float(val)
        except (TypeError, ValueError):
            continue
        if num != num or num in (float("inf"), float("-inf")) or not (num > 0):
            continue
        rows.append((num, player, pk))
    rows.sort(key=lambda r: (-r[0], str(r[1].get("name") or ""), _safe_int(r[1].get("player_key"))))

    roles: dict[Any, str] = {}
    for pos in POSITION_ORDER:
        take = teams * (_safe_int(shape.get(pos)))
        for _, p, pk in [r for r in rows if r[1].get("pos") == pos][:take]:
            roles[pk] = "starter"
    elig = flex_eligible(shape)
    elig_rows = [r for r in rows if r[1].get("pos") in elig and r[2] not in roles]
    for _, p, pk in elig_rows[:teams * _safe_int(shape.get("FLEX"))]:
        roles[pk] = "starter"
    bench_rows = [r for r in rows if r[2] not in roles]
    for _, p, pk in bench_rows[:teams * _safe_int(shape.get("BENCH"))]:
        roles[pk] = "bench"
    return roles


# ---------------------------------------------------------------------------
# sharedPieBasis: intersection of player_keys with positive anchor & value.
# ---------------------------------------------------------------------------
def shared_pie_basis(values: dict[Any, float], anchor: dict[Any, float] | None,
                      player_of: Callable[[Any], dict[str, Any] | None]) -> dict[str, Any] | None:
    """Mirror value-model.js::sharedPieBasis."""
    if not anchor:
        return None
    keys: set[Any] = set()
    target = 0.0
    for pk, val in values.items():
        player = player_of(pk)
        if player is None or player.get("pos") not in POSITION_ORDER:
            continue
        a = anchor.get(pk)
        try:
            a_num = float(a) if a is not None else float("nan")
            v_num = float(val) if val is not None else float("nan")
        except (TypeError, ValueError):
            continue
        if a_num != a_num or v_num != v_num or a_num in (float("inf"), float("-inf")) or v_num in (float("inf"), float("-inf")):
            continue
        keys.add(pk)
        if a_num > 0:
            target += a_num
    if len(keys) < MIN_SHARED_FOR_PIE or not (target > 0):
        return None
    return {"keys": keys, "target": target}


# ---------------------------------------------------------------------------
# benchShareOf: share of the pie on bench players (with roleMap if not given).
# ---------------------------------------------------------------------------
def bench_share_of(values: dict[Any, float], roles: dict[Any, str] | None,
                   player_of: Callable[[Any], dict[str, Any] | None] | None = None,
                   teams: int | None = None,
                   shape: dict[str, Any] | None = None) -> float | None:
    """Mirror value-model.js::benchShareOf.

    When `roles` is None the JS implementation calls roleMap(opts) which needs
    player_of, teams, shape. We mirror that path; the parity test passes them
    explicitly via the helper signature.
    """
    if roles is None:
        if player_of is None or teams is None or shape is None:
            raise ValueError("bench_share_of: when roles is None, player_of/teams/shape are required")
        roles = role_map(values, player_of, teams, shape)
    starter = bench = 0.0
    for pk, val in values.items():
        try:
            v = float(val) if val is not None else float("nan")
        except (TypeError, ValueError):
            v = float("nan")
        if v != v or v in (float("inf"), float("-inf")):
            v = 0.0
        if v < 0:
            v = 0.0
        role = roles.get(pk)
        if role == "starter":
            starter += v
        elif role == "bench":
            bench += v
    total = starter + bench
    if not (total > 0) or not (bench > 0):
        return None
    return bench / total


# ---------------------------------------------------------------------------
# scaleToSharedTotal: scale a series onto the anchor's pie WITHOUT re-splitting.
# ---------------------------------------------------------------------------
def scale_to_shared_total(values: dict[Any, float], anchor: dict[Any, float] | None,
                          player_of: Callable[[Any], dict[str, Any] | None]) -> dict[Any, float]:
    """Mirror value-model.js::scaleToSharedTotal."""
    basis = shared_pie_basis(values, anchor, player_of)
    out: dict[Any, float] = {}
    if basis is None:
        return dict(values)
    total = 0.0
    for pk, val in values.items():
        if pk not in basis["keys"]:
            continue
        try:
            v = float(val) if val is not None else float("nan")
        except (TypeError, ValueError):
            continue
        if v != v or v in (float("inf"), float("-inf")) or not (v > 0):
            continue
        total += v
    scale = (basis["target"] / total) if total > 0 else 1.0
    for pk, val in values.items():
        try:
            v = float(val) if val is not None else float("nan")
        except (TypeError, ValueError):
            v = float("nan")
        if v != v or v in (float("inf"), float("-inf")):
            out[pk] = 0.0
        else:
            out[pk] = max(0.0, v) * scale
    return out


# ---------------------------------------------------------------------------
# shapeToAnchorPeaksThenSharedTotal: align each position peak to the anchor.
# ---------------------------------------------------------------------------
def shape_to_anchor_peaks_then_shared_total(
    values: dict[Any, float], anchor: dict[Any, float] | None,
    player_of: Callable[[Any], dict[str, Any] | None]
) -> dict[Any, float]:
    """Mirror value-model.js::shapeToAnchorPeaksThenSharedTotal."""
    basis = shared_pie_basis(values, anchor, player_of)
    if basis is None:
        return dict(values)
    anchor_peaks = {pos: 0.0 for pos in POSITION_ORDER}
    value_peaks = {pos: 0.0 for pos in POSITION_ORDER}
    for pk in basis["keys"]:
        player = player_of(pk)
        if player is None or player.get("pos") not in POSITION_ORDER:
            continue
        a = anchor.get(pk) if anchor else None
        v = values.get(pk)
        try:
            a_num = float(a) if a is not None else float("nan")
            v_num = float(v) if v is not None else float("nan")
        except (TypeError, ValueError):
            continue
        if a_num == a_num and a_num not in (float("inf"), float("-inf")) and a_num > anchor_peaks[player["pos"]]:
            anchor_peaks[player["pos"]] = a_num
        if v_num == v_num and v_num not in (float("inf"), float("-inf")) and v_num > value_peaks[player["pos"]]:
            value_peaks[player["pos"]] = v_num
    shaped: dict[Any, float] = {}
    for pk, val in values.items():
        player = player_of(pk)
        try:
            safe = float(val) if val is not None else float("nan")
        except (TypeError, ValueError):
            safe = float("nan")
        if safe != safe or safe in (float("inf"), float("-inf")):
            safe = 0.0
        if safe < 0:
            safe = 0.0
        s = 1.0
        if player is not None and value_peaks[player["pos"]] > 0 and anchor_peaks[player["pos"]] > 0:
            s = anchor_peaks[player["pos"]] / value_peaks[player["pos"]]
        shaped[pk] = safe * s
    return scale_to_shared_total(shaped, anchor, player_of)


# ---------------------------------------------------------------------------
# normalizeToFixedPie: two-tier scaling with shared-set target.
# ---------------------------------------------------------------------------
def normalize_to_fixed_pie(values: dict[Any, float], share: float,
                           roles: dict[Any, str] | None,
                           anchor: dict[Any, float] | None,
                           player_of: Callable[[Any], dict[str, Any] | None],
                           single_scale: bool = False,
                           fallback_target: Callable[[float], float] | None = None
                           ) -> dict[Any, float]:
    """Mirror value-model.js::normalizeToFixedPie."""
    basis = shared_pie_basis(values, anchor, player_of)
    in_basis = (lambda pk: True) if basis is None else (lambda pk: pk in basis["keys"])

    starter_total = bench_total = 0.0
    for pk, val in values.items():
        if not in_basis(pk):
            continue
        try:
            safe = float(val) if val is not None else float("nan")
        except (TypeError, ValueError):
            safe = float("nan")
        if safe != safe or safe in (float("inf"), float("-inf")):
            safe = 0.0
        if safe < 0:
            safe = 0.0
        role = (roles or {}).get(pk)
        if role == "starter":
            starter_total += safe
        elif role == "bench":
            bench_total += safe

    if basis is not None:
        target = basis["target"]
    elif fallback_target is not None:
        target = fallback_target(starter_total + bench_total)
    else:
        target = starter_total + bench_total

    out: dict[Any, float] = {}
    if single_scale:
        total = starter_total + bench_total
        scale = (target / total) if (total > 0 and target > 0) else 0.0
        for pk, val in values.items():
            try:
                safe = float(val) if val is not None else float("nan")
            except (TypeError, ValueError):
                safe = float("nan")
            if safe != safe or safe in (float("inf"), float("-inf")):
                safe = 0.0
            if safe < 0:
                safe = 0.0
            out[pk] = safe * scale
        return out

    s = max(0.0, min(1.0, 1.0 - float(share)))
    b = max(0.0, min(1.0, float(share)))
    starter_scale = ((target * s) / starter_total) if (starter_total > 0 and target > 0) else 0.0
    bench_scale = ((target * b) / bench_total) if (bench_total > 0 and target > 0) else 0.0
    for pk, val in values.items():
        role = (roles or {}).get(pk) or "waiver"
        try:
            safe = float(val) if val is not None else float("nan")
        except (TypeError, ValueError):
            safe = float("nan")
        if safe != safe or safe in (float("inf"), float("-inf")):
            safe = 0.0
        if safe < 0:
            safe = 0.0
        if role == "starter":
            out[pk] = safe * starter_scale
        elif role == "bench":
            out[pk] = safe * bench_scale
        else:
            out[pk] = 0.0
    return out


# ---------------------------------------------------------------------------
# Sanity bands (JEG-68 / JEG-69 / cross-source peak agreement).
# ---------------------------------------------------------------------------
def starter_markup_sane(markup: float) -> bool:
    """Mirror value-model.js::starterMarkupSane."""
    try:
        m = float(markup)
    except (TypeError, ValueError):
        return False
    if m != m or m in (float("inf"), float("-inf")):
        return False
    return STARTER_MARKUP_SANE_LOW <= m <= STARTER_MARKUP_SANE_HIGH


def fixed_pie_direction_sane(raw_starter_share: float, starter_share: float) -> bool:
    """Mirror value-model.js::fixedPieDirectionSane."""
    try:
        rss = float(raw_starter_share)
        ss = float(starter_share)
    except (TypeError, ValueError):
        return False
    if rss != rss or rss in (float("inf"), float("-inf")):
        return False
    if ss != ss or ss in (float("inf"), float("-inf")):
        return False
    return rss < ss + STARTER_DIRECTION_EPS


def peak_agreement(anchor_peaks: dict[str, float], sources: dict[str, dict[str, float]],
                   low: float | None = None, high: float | None = None,
                   label_of: Callable[[str], str] | None = None) -> dict[str, Any]:
    """Mirror value-model.js::peakAgreement."""
    lo = float(low) if (low is not None and low == low) else PEAK_AGREEMENT_LOW
    hi = float(high) if (high is not None and high == high) else PEAK_AGREEMENT_HIGH
    label = label_of or (lambda k: k)
    offenders: list[str] = []
    compared = 0
    for key, peaks in sources.items():
        peaks = peaks or {}
        for pos in POSITION_ORDER:
            try:
                a = float(anchor_peaks.get(pos, float("nan")))
                v = float(peaks.get(pos, float("nan")))
            except (TypeError, ValueError):
                continue
            if a != a or v != v or a in (float("inf"), float("-inf")) or v in (float("inf"), float("-inf")):
                continue
            if not (a > 0) or not (v > 0):
                continue
            compared += 1
            ratio = v / a
            if ratio < lo or ratio > hi:
                offenders.append(f"{label(key)} {pos} {v:.1f} vs anchor {a:.1f} ({ratio:.2f}x)")
    return {"ok": compared > 0 and not offenders, "compared": compared,
            "offenders": offenders, "band": [lo, hi]}


# ---------------------------------------------------------------------------
# projectionRoles / positionalTierScales / allocationCounts: surplus model.
# ---------------------------------------------------------------------------
def projection_roles(pool: list[dict[str, Any]], teams: int, shape: dict[str, Any],
                     rank_of: Callable[[dict[str, Any]], float]) -> dict[str, Any]:
    """Mirror value-model.js::projectionRoles.

    pool is a list of player dicts with `player_key` and `pos`; `rank_of` is a
    pure function returning a sortable projection (higher is better).
    """
    teams = _safe_int(teams)
    shape = shape or {}
    by_pos: dict[str, list[dict[str, Any]]] = {}
    direct: dict[str, int] = {}
    for pos in POSITION_ORDER:
        direct[pos] = teams * _safe_int(shape.get(pos))
        rows = [p for p in pool if p.get("pos") == pos]
        try:
            rows.sort(key=lambda p: (-float(rank_of(p)), str(p.get("name") or ""), _safe_int(p.get("player_key"))))
        except (TypeError, ValueError):
            rows = [p for p in rows if rank_of(p) == rank_of(p)]
        by_pos[pos] = rows
    baseline: dict[str, float] = {}
    for pos in POSITION_ORDER:
        lst = by_pos[pos]
        if not lst:
            baseline[pos] = 0.0
            continue
        idx = max(0, min(direct[pos] - 1, len(lst) - 1))
        baseline[pos] = float(rank_of(lst[idx]))

    def surplus(p: dict[str, Any]) -> float:
        return float(rank_of(p)) - float(baseline.get(p.get("pos") or "", 0.0))

    roles: dict[Any, str] = {}
    for pos in POSITION_ORDER:
        for p in by_pos[pos][:direct[pos]]:
            roles[p.get("player_key")] = "starter"

    def remaining(positions: list[str], score_of: Callable[[dict[str, Any]], float]) -> list[dict[str, Any]]:
        out_list = []
        for pos in positions:
            for p in by_pos[pos]:
                if p.get("player_key") not in roles:
                    out_list.append(p)
        out_list.sort(key=lambda p: (-float(score_of(p)), str(p.get("name") or ""), _safe_int(p.get("player_key"))))
        return out_list

    flex_positions = flex_eligible(shape)
    flex_score = rank_of if "QB" not in flex_positions else surplus
    for p in remaining(flex_positions, flex_score)[: teams * _safe_int(shape.get("FLEX"))]:
        roles[p.get("player_key")] = "starter"
    for p in remaining(POSITION_ORDER, surplus)[: teams * _safe_int(shape.get("BENCH"))]:
        roles[p.get("player_key")] = "bench"
    return {"roles": roles, "direct": direct, "baseline": baseline}


def positional_tier_scales(rows: list[dict[str, Any]],
                           target_for: Callable[[str], float],
                           share: float) -> dict[str, dict[str, float]]:
    """Mirror value-model.js::positionalTierScales."""
    starter_raw = {pos: 0.0 for pos in POSITION_ORDER}
    bench_raw = {pos: 0.0 for pos in POSITION_ORDER}
    for row in rows:
        if row.get("pos") not in POSITION_ORDER:
            continue
        try:
            v = float(row.get("value"))
        except (TypeError, ValueError):
            continue
        if v != v or v in (float("inf"), float("-inf")) or not (v > 0):
            continue
        role = row.get("role")
        if role == "starter":
            starter_raw[row["pos"]] += v
        elif role == "bench":
            bench_raw[row["pos"]] += v
    s = max(0.0, min(1.0, 1.0 - float(share)))
    b = max(0.0, min(1.0, float(share)))
    starter = {pos: 0.0 for pos in POSITION_ORDER}
    bench = {pos: 0.0 for pos in POSITION_ORDER}
    target: dict[str, float] = {}
    for pos in POSITION_ORDER:
        try:
            t = float(target_for(pos))
        except (TypeError, ValueError):
            t = float("nan")
        if t != t or t in (float("inf"), float("-inf")) or not (t > 0):
            t = 0.0
        target[pos] = t
        starter[pos] = ((target[pos] * s) / starter_raw[pos]) if (starter_raw[pos] > 0 and target[pos] > 0) else 0.0
        bench[pos] = ((target[pos] * b) / bench_raw[pos]) if (bench_raw[pos] > 0 and target[pos] > 0) else 0.0
    return {"starter": starter, "bench": bench, "starterRaw": starter_raw,
            "benchRaw": bench_raw, "target": target}


def allocation_counts(pool: list[dict[str, Any]], teams: int, shape: dict[str, Any],
                      rank_of: Callable[[dict[str, Any]], float]) -> dict[str, dict[str, int]]:
    """Mirror value-model.js::allocationCounts."""
    assigned = projection_roles(pool, teams, shape, rank_of)
    direct = assigned["direct"]
    lineup = dict(direct)
    rostered = dict(direct)
    seen_direct = {pos: 0 for pos in POSITION_ORDER}
    sorted_pool = sorted(pool, key=lambda p: (-float(rank_of(p)), str(p.get("name") or ""), _safe_int(p.get("player_key"))))
    for p in sorted_pool:
        if p.get("pos") not in POSITION_ORDER:
            continue
        role = assigned["roles"].get(p.get("player_key"))
        if not role:
            continue
        if role == "starter" and seen_direct[p["pos"]] < direct[p["pos"]]:
            seen_direct[p["pos"]] += 1
            continue
        if role == "starter":
            lineup[p["pos"]] += 1
            rostered[p["pos"]] += 1
            continue
        rostered[p["pos"]] += 1
    return {"direct": direct, "lineup": lineup, "rostered": rostered}