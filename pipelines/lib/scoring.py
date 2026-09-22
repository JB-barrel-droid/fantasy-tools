"""Fantasy scoring systems: points per stat.

Repo-owned port of football-signal/engine/scoring.py (2026-09-22).
Only the skill-player scoring used by the players.json bake is carried
over: fantasy_points(). Kicker/DST component math is not needed here —
K/DST price from ESPN per-game rates directly.
"""

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
