"""Vegas math: odds -> probabilities -> implied fantasy points.

Conventions verified against nflverse data (2026-09-10):
- spread_line is from the HOME team's perspective: positive => home favored.
- implied team totals: home = total/2 + spread/2, away = total/2 - spread/2.

TD handling (2026-09-12, user-approved):
- Precedence per player: a direct player-TDs over/under line first,
  else the anytime-TD market via Poisson, else no TD component.
  (A direct line and an anytime market on the same player must never
  both contribute — that double-counts the TD expectation.)
- Anytime-TD -> expected TDs: no-vig the two sides when both are posted
  (p = q_yes / (q_yes + q_no)); when only Yes is posted (common), subtract
  half the book's estimated hold (measured from its two-sided markets,
  default 0.05). Then Poisson E[TDs] = -ln(1-p), capped at
  ANYTIME_TD_LAMBDA_CAP.
- Completeness provenance per position (vegas_provenance()):
    QB:   passing-yards market + TD coverage
    RB:   rushing-yards market + TD coverage
    WR/TE: receiving-yards market + receptions market + TD coverage
  'complete'  = all required markets direct (incl. a direct TD line)
  'td-filled' = required yardage/reception markets direct, TD via the
                approved anytime-TD Poisson fill
  'partial'   = anything else missing -> informational only, never published
"""

import math

from .scoring import fantasy_points


def consensus_pick_key(book, line, med, consensus_order):
    """Deterministic sort key for picking one book's quote at a market.

    A bare min() on abs(line - med) silently depends on dict/file order
    when the cross-book median line falls exactly between two posted
    lines (2026-09-20: Michael Mayer receptions sat at 4.5 on
    BetMGM/FanDuel and 5.5 on DraftKings/Pinnacle — the primary leg and
    the QA recompute picked different books and disagreed by 0.79 PPR,
    tripping the bundle's fail-closed sanity check). Distance ties break
    by the consensus book order, then book name, so every consumer of a
    quotable leg always picks the same book.
    """
    order = list(consensus_order)
    return (abs(line - med),
            order.index(book) if book in order else 999,
            book)


def american_to_prob(odds: float) -> float:
    if odds >= 100:
        return 100.0 / (odds + 100.0)
    if odds <= -100:
        return -odds / (-odds + 100.0)
    raise ValueError(f"bad american odds: {odds}")


def devig(over_odds: float, under_odds: float) -> tuple[float, float]:
    """Remove the vig from a two-way prop market -> fair over/under probs."""
    p_over = american_to_prob(over_odds)
    p_under = american_to_prob(under_odds)
    total = p_over + p_under
    return p_over / total, p_under / total


def implied_team_totals(spread_line: float, total_line: float) -> tuple[float, float]:
    """Return (home_total, away_total). spread_line: home perspective."""
    return (
        round(total_line / 2 + spread_line / 2, 2),
        round(total_line / 2 - spread_line / 2, 2),
    )


# Direct over/under markets on player TDs. When any of these is present for
# a player it takes precedence over the anytime-TD market (per-player rule:
# never let both contribute TD expectation).
TD_LINE_MARKETS = frozenset({
    'player_pass_tds', 'player_rush_tds', 'player_reception_tds',
})

# Cap on the Poisson anytime-TD conversion. lambda = 3.0  <=>  P(>=1 TD) =
# 95.0%: the market essentially never prices an anytime-TD above ~-1900
# (95.2%), so anything beyond lambda = 3 is the Poisson tail wagging on
# estimation noise. Without the cap, a prob pinned at the 0.99 clamp would
# imply 4.6 expected TDs (~27 fantasy points from TDs alone) — absurd.
ANYTIME_TD_LAMBDA_CAP = 3.0

# Default book hold used when only the Yes side of an anytime-TD market is
# posted (the No side usually is not). Estimated from the book's own
# two-sided line markets wherever load_props() can measure it.
DEFAULT_BOOK_HOLD = 0.05


def classify_anytime_td_outcome(name, point, player_name, *, book="",
                                source=""):
    """Classify one player_anytime_td outcome as "yes" or "no".

    Recognized shapes (2026-09-18 fix — the parser used to accept only
    the Odds API shape and silently dropped everything else, so the
    Poisson TD leg priced ZERO props on PropLine data):
      - Odds API shape: name "Yes" / "No".
      - PropLine single-Yes shape: name == the player name (== the
        outcome's description), one price = the Yes price.
      - PropLine Over/Under 0.5 shape (Pinnacle): "Over 0.5 TDs" IS
        P(anytime TD) i.e. the Yes side; "Under 0.5 TDs" is the No side.

    Anything else raises ValueError — an unrecognized outcome shape
    must block loudly, never silently price nothing.
    """
    if name == "Yes":
        return "yes"
    if name == "No":
        return "no"
    if name == player_name:
        # PropLine posts the Yes price under the player's own name.
        return "yes"
    if name in ("Over", "Under"):
        try:
            is_half = point is not None and float(point) == 0.5
        except (TypeError, ValueError):
            is_half = False
        if is_half:
            return "yes" if name == "Over" else "no"
    raise ValueError(
        f"unrecognized player_anytime_td outcome shape: name={name!r} "
        f"point={point!r} player={player_name!r} book={book!r} "
        f"source={source!r}")


def fair_anytime_prob(yes_odds: float, no_odds: float | None = None,
                      hold: float = DEFAULT_BOOK_HOLD) -> float:
    """De-vigged P(anytime TD) from American odds.

    Both sides posted: p = q_yes / (q_yes + q_no) (standard no-vig).
    Yes only: fair ~= implied_yes - hold/2, clamped to [0.01, 0.99].
    """
    q_yes = american_to_prob(yes_odds)
    if no_odds is not None:
        q_no = american_to_prob(no_odds)
        p = q_yes / (q_yes + q_no)
    else:
        p = q_yes - hold / 2.0
    return max(0.01, min(0.99, p))


def poisson_expected_tds(p: float) -> float:
    """Poisson E[TDs] from P(>=1 TD), capped at ANYTIME_TD_LAMBDA_CAP."""
    return min(-math.log(1.0 - p), ANYTIME_TD_LAMBDA_CAP)


def apply_td_precedence(player_props: dict) -> dict:
    """Enforce the TD precedence rule: if the player has any direct TD
    over/under line, drop the anytime-TD entry (it must not double-count).
    Returns a (shallow-copied) props dict."""
    if 'player_anytime_td' in player_props and \
            (set(player_props) & TD_LINE_MARKETS):
        props = dict(player_props)
        del props['player_anytime_td']
        return props
    return player_props


# Per-position market requirements for a publishable ("complete"/"td-filled")
# Vegas number. TD coverage may come from a direct TD line or from the
# approved anytime-TD Poisson fill.
COMPLETENESS_LINES = {
    'QB': frozenset({'player_pass_yds'}),
    'RB': frozenset({'player_rush_yds'}),
    'WR': frozenset({'player_reception_yds', 'player_receptions'}),
    'TE': frozenset({'player_reception_yds', 'player_receptions'}),
}

PUBLISHABLE_PROVENANCE = ('complete', 'td-filled')


def completeness_gaps(markets_used, td_source: str,
                       position: str) -> list[str]:
    """Human-readable list of what's missing for a complete Vegas number."""
    gaps = []
    required = COMPLETENESS_LINES.get((position or '').upper(), frozenset())
    missing = required - set(markets_used or ())
    gaps.extend(sorted(missing))
    if td_source == 'none':
        gaps.append('td_coverage')
    return gaps


def vegas_provenance(markets_used, td_source: str,
                     position: str) -> str:
    """'complete' | 'td-filled' | 'partial' for a Vegas-implied projection.

    markets_used: market keys that fed the number (post-TD-precedence).
    td_source: 'direct' | 'anytime' | 'none' (from vegas_implied_points).
    Only 'complete' and 'td-filled' are publishable; 'partial' rows are
    computed and stored but informational only — never post-worthy.
    """
    if completeness_gaps(markets_used, td_source, position):
        return 'partial'
    return 'complete' if td_source == 'direct' else 'td-filled'


# Maps Odds API player-prop market keys to (stat_key, is_binary_probability).
# For line markets the posted line is used as the expected stat value
# (yardage distributions are roughly symmetric, so line ~= mean).
# For binary markets (anytime TD) the de-vigged probability is the expectation.
PROP_MARKETS = {
    'player_pass_yds': ('passing_yards', False),
    'player_pass_tds': ('passing_tds', False),
    'player_pass_interceptions': ('interceptions', False),
    'player_rush_yds': ('rushing_yards', False),
    'player_rush_tds': ('rushing_tds', False),
    'player_receptions': ('receptions', False),
    'player_reception_yds': ('receiving_yards', False),
    'player_reception_tds': ('receiving_tds', False),
    'player_anytime_td': (None, True),  # handled specially below
}


def vegas_implied_points(player_props: dict, position: str = 'WR',
                         scoring: str = 'ppr') -> dict:
    """player_props: {market_key: {'line': x, 'over_odds': o, 'under_odds': u}}
       Binary markets: {'prob': lambda} (Poisson E[TDs], precomputed) or
       {'yes_odds': y, 'no_odds': n} (raw American odds, de-vigged here).
    Applies the TD precedence rule (direct TD line beats anytime-TD).
    Returns {'points': float, 'components': {stat: pts},
             'markets_used': [...],
             'td_source': 'direct' | 'anytime' | 'none'}."""
    from .scoring import SCORING
    table = SCORING[scoring]
    player_props = apply_td_precedence(player_props)
    stats: dict = {}
    markets_used = []
    for market, spec in PROP_MARKETS.items():
        if market not in player_props:
            continue
        stat_key, is_binary = spec
        entry = player_props[market]
        if is_binary:
            if 'prob' in entry:
                lam = float(entry['prob'])  # precomputed Poisson E[TDs]
            else:
                p = fair_anytime_prob(entry['yes_odds'],
                                      entry.get('no_odds'))
                lam = poisson_expected_tds(p)
            # attribute the TD expectation to the position-appropriate bucket
            bucket = 'rushing_tds' if position == 'QB' else 'receiving_tds'
            stats[bucket] = stats.get(bucket, 0.0) + lam
        else:
            line = float(entry['line'])
            # nudge the line toward the favored side using de-vigged probs
            if 'over_odds' in entry and 'under_odds' in entry:
                p_over, _ = devig(entry['over_odds'], entry['under_odds'])
                line = line + (p_over - 0.5) * 2.0  # small skew adjustment
            stats[stat_key] = stats.get(stat_key, 0.0) + line
        markets_used.append(market)

    if set(markets_used) & TD_LINE_MARKETS:
        td_source = 'direct'
    elif 'player_anytime_td' in markets_used:
        td_source = 'anytime'
    else:
        td_source = 'none'
    components = {k: round(v * table[k], 2)
                  for k, v in stats.items() if k in table and v}
    return {'points': fantasy_points(stats, scoring),
            'components': components,
            'markets_used': markets_used,
            'td_source': td_source}
