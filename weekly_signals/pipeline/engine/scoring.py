"""Fantasy scoring systems: points per stat."""

SCORING = {
    'ppr': {
        'passing_yards': 0.04, 'passing_tds': 4.0, 'interceptions': -2.0,
        'rushing_yards': 0.10, 'rushing_tds': 6.0,
        'receptions': 1.0, 'receiving_yards': 0.10, 'receiving_tds': 6.0,
        'fumbles_lost': -2.0,
    },
    'half_ppr': {
        'passing_yards': 0.04, 'passing_tds': 4.0, 'interceptions': -2.0,
        'rushing_yards': 0.10, 'rushing_tds': 6.0,
        'receptions': 0.5, 'receiving_yards': 0.10, 'receiving_tds': 6.0,
        'fumbles_lost': -2.0,
    },
    'standard': {
        'passing_yards': 0.04, 'passing_tds': 4.0, 'interceptions': -2.0,
        'rushing_yards': 0.10, 'rushing_tds': 6.0,
        'receptions': 0.0, 'receiving_yards': 0.10, 'receiving_tds': 6.0,
        'fumbles_lost': -2.0,
    },
}


def fantasy_points(stats: dict, scoring: str = 'ppr') -> float:
    """stats keys: passing_yards, passing_tds, interceptions, rushing_yards,
    rushing_tds, receptions, receiving_yards, receiving_tds, fumbles_lost."""
    table = SCORING[scoring]
    return round(sum(stats.get(k, 0.0) * v for k, v in table.items()), 2)


def fantasy_points_or_null(stats: dict, scoring: str = 'ppr'):
    """Like fantasy_points, but null when no priced stat can move the leg.

    A scoring leg is null — never zero — when none of the priced stats
    carries nonzero weight in that scoring. Example: a receptions-only
    line prices half-PPR/PPR but says nothing about standard (receptions
    score 0 there), so the standard leg is uncomputable. A 0.0 would read
    as "Vegas implies 0"; null reads as "not priced". Never zero-fill
    missing Vegas. (2026-09-18: PropLine name-variant merge exposed a
    receptions-only row whose standard leg printed 0.0.)
    """
    table = SCORING[scoring]
    if not any(table.get(s, 0) != 0 for s in stats):
        return None
    return fantasy_points(stats, scoring)


# ---- kickers & team defenses (2026-09-16) ----------------------------------
# Standard fantasy scoring (Yahoo/ESPN default). Kickers and defenses are
# scoring-invariant: no PPR dimension, so one number serves all three legs.
# Distance-bonus kicker leagues (4/5 pts for 40+/50+ FGs) are NOT the default;
# if a distance-bonus view is ever needed, fg_made_40_49 / fg_made_50_plus
# components can be priced separately.

def kicker_points(stats: dict) -> float:
    """stats keys: fg_made, xp_made. 3 pts per FG, 1 pt per XP."""
    return round(float(stats.get("fg_made", 0.0)) * 3.0
                 + float(stats.get("xp_made", 0.0)) * 1.0, 2)


def _dst_points_allowed_pts(pa: float) -> float:
    if pa < 1:
        return 10.0
    if pa <= 6:
        return 7.0
    if pa <= 13:
        return 4.0
    if pa <= 20:
        return 1.0
    if pa <= 27:
        return 0.0
    if pa <= 34:
        return -1.0
    return -4.0


def _dst_yards_allowed_pts(ya: float) -> float:
    if ya < 100:
        return 5.0
    if ya < 200:
        return 3.0
    if ya < 300:
        return 2.0
    if ya < 350:
        return 0.0
    if ya < 400:
        return -1.0
    if ya < 450:
        return -3.0
    if ya < 500:
        return -5.0
    return -7.0


def dst_component_points(stats: dict) -> float:
    """Counting-stat DST points only: no PA/YA brackets.

    Cross-checkable piece — FP's own DST FPTS column equals exactly this
    (verified 2026-09-16: gap <= 0.02/g across the top 5 defenses), i.e.
    FP's default DST FPTS awards zero PA/YA bracket points. Our chart adds
    the brackets on top because real leagues score them."""
    return round(float(stats.get("sacks", 0.0)) * 1.0
                 + float(stats.get("interceptions", 0.0)) * 2.0
                 + float(stats.get("fumbles_recovered", 0.0)) * 2.0
                 + float(stats.get("touchdowns", 0.0)) * 6.0
                 + float(stats.get("safeties", 0.0)) * 2.0, 2)


def dst_bracket_points(stats: dict) -> float:
    """PA/YA bracket points only — the part FP's FPTS omits."""
    total = 0.0
    if stats.get("points_allowed") is not None:
        total += _dst_points_allowed_pts(float(stats["points_allowed"]))
    if stats.get("yards_allowed") is not None:
        total += _dst_yards_allowed_pts(float(stats["yards_allowed"]))
    return round(total, 2)


def dst_points(stats: dict) -> float:
    """Team defense fantasy points, standard scoring.
    stats keys: sacks, interceptions, fumbles_recovered, touchdowns,
    safeties, points_allowed, yards_allowed.
    Bracket inputs (points_allowed, yards_allowed) must be PER-GAME rates —
    the brackets are per-game."""
    return round(dst_component_points(stats) + dst_bracket_points(stats), 2)
