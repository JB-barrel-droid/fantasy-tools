"""Source-priority switch for the weekly Vegas leg, plus the EV-gate policy.

VEGAS_SOURCE_PRIORITY: ordered tuple. The FIRST source is the primary
coverage backbone; the rest are audit / coverage legs in order.

Current (2026-09-18): ("propline", "odds_api", "fds")
- "propline": PropLine is the PRIMARY raw-price leg (free, full-slate,
  daily; DraftKings, FanDuel, BetMGM, Pinnacle). Raw per-book lines and
  both sides' prices are translated with our own engine (engine.vegas).
  PropLine quotes are the only inputs the play gate may price from.
- "odds_api": The Odds API raw-book leg is the AUDIT leg. Targeted
  raw-book pulls (quota-guarded) are translated with our own engine and
  compared against the PropLine-primary number. Material disagreements
  are QA findings; the PropLine-primary number stands (it is the
  configured primary). Quotes from this leg may also price a play when
  they pass the same EV gate — they are real sportsbook prices.
- "fds": First Down Studio translated stats are FANTASY COVERAGE only.
  They fill Vegas fantasy columns where no raw-book leg prices a
  player. vegas-attributed translated stats are run through OUR OWN
  scoring math locally (engine.fds_fallback) — FDS's blended derived
  points are never used, and projection-attributed stats never feed a
  Vegas column. FDS-attributed rows can NEVER become a betting play.

History: ("fds", "local") ran 2026-09-17 (FDS primary, Odds API audit).
The flip to PropLine primary was approved 2026-09-18.

check_priority() fails closed on anything not in SUPPORTED_PRIORITIES so
a half-configured flip can never silently run with the wrong precedence.
"""

VEGAS_SOURCE_PRIORITY = ("propline", "odds_api", "fds")

SUPPORTED_PRIORITIES = (
    ("propline", "odds_api", "fds"),   # current: PropLine primary
    ("fds", "local"),                  # legacy 2026-09-17 wiring
    ("local", "fds"),                  # legacy: raw-book first
)


def check_priority(priority):
    """Fail-closed: only an approved ordering runs."""
    tup = tuple(priority)
    if tup not in SUPPORTED_PRIORITIES:
        raise NotImplementedError(
            f"Vegas source priority {tup!r} is not implemented. "
            f"Supported: {SUPPORTED_PRIORITIES!r}.")
    return tup


def check_fds_primary(priority):
    """Fail-closed: the FDS-primary merge only runs under an fds-first
    priority (legacy ("fds", "local") wiring)."""
    tup = check_priority(priority)
    if not tup or tup[0] != "fds":
        raise NotImplementedError(
            f"FDS-primary merge requires an fds-first priority, got "
            f"{tup!r}.")
    return tup


# ---------------------------------------------------------------------------
# Primary-leg plumbing
# ---------------------------------------------------------------------------

#: Cache written by collectors/propline.py (Odds-API-compatible shape).
PROPLINE_CACHE_DIR = "data/propline_cache"

#: Audit-leg cache (Odds API shape, written by collectors/odds_api.py).
ODDS_CACHE_DIR = "data/odds_cache"

#: Books the primary leg pulls and prices from (PropLine keys).
PROPLINE_BOOKS = ("draftkings", "fanduel", "betmgm", "pinnacle")

#: Human display names for the primary books.
PROPLINE_BOOK_TITLES = {
    "draftkings": "DraftKings",
    "fanduel": "FanDuel",
    "betmgm": "BetMGM",
    "pinnacle": "Pinnacle",
}

#: Vegas legs whose rows carry quotable sportsbook prices. The play gate
#: may only name a play from one of these. "fds" is deliberately absent:
#: translated stats are fantasy coverage, never a wager input.
QUOTABLE_VEGAS_LEGS = ("propline", "local")


# ---------------------------------------------------------------------------
# Positive-EV play-gate policy
# ---------------------------------------------------------------------------
#
# A play is named only when ALL of these hold for one exact
# (player, prop, side, line, price, sportsbook) quote:
#
#   1. The row's vegas_leg is quotable (propline/local) — FDS never plays.
#   2. The game has not kicked off.
#   3. Both sides of the prop are quoted at the same line by the same
#      book (so the price can be de-vigged and verified as live).
#   4. The quote is fresh: line_as_of within EV_MAX_LINE_AGE_HOURS.
#   5. Modeled cover probability P(model) comes from an explicit
#      distribution centered on the EXPERT projection (Poisson for
#      counting stats, market-implied-volatility normal for yardage) —
#      never from the bare line and never from a fantasy-point edge.
#   6. Breakeven probability P(be) = american_to_prob(offered price).
#   7. Positive EV: P(model) > P(be), with margin
#      P(model) - P(be) >= EV_MIN_PROB_EDGE.
#
# Missing, stale, partial, one-sided, translated-only, or post-kickoff
# inputs fail closed: no play, with the reason recorded.

#: Minimum modeled-minus-breakeven probability margin to name a play.
#: Calibrated 2026-09-18: 5pp keeps the gate on high-conviction,
#: genuinely bettable edges. A 3pp bar admitted marginal plays (e.g.
#: Allen under 1.5 at +134: 3.5pp on a rigid Poisson model centered on
#: a point-estimate expert projection) that read as false direction.
#: "Only flag real opportunities" means the model must clear a
#: meaningful margin, not just scrape past breakeven.
EV_MIN_PROB_EDGE = 0.05

#: Maximum age of a quoted line (hours) for it to price a play.
EV_MAX_LINE_AGE_HOURS = 24

#: Sanity cap on the expert-vs-line disagreement, in standard deviations
#: under the model's own distribution. If the expert projection and the
#: quoted line are more than this many sigma apart, the inputs are
#: treated as stale/mismatched (a 5-sigma "edge" is a data problem, not
#: alpha) and the stat cannot price a play. Fail-closed on input quality.
EV_MAX_ZSCORE = 3.0

#: Maximum plausible expert-vs-line RATIO. When the expert projection
#: and the quoted line differ by more than this factor (in either
#: direction), they live in different universes — stale experts, injury
#: news the weekly projection missed, a mismatched player — and the
#: "edge" is not bettable. Calibrated 2026-09-18: across 393 Week-2
#: player-props the median expert/line ratio is 1.12x (p90 1.44x), so
#: 1.5x allows 3x the typical disagreement while blocking the tail
#: where data mismatch dominates. The weekly ECR projection refreshes
#: on a slower cadence than the market; the market is usually the
#: fresher number when they disagree wildly. Fail-closed on input
#: quality.
EV_MAX_DISAGREEMENT_RATIO = 1.5

#: Thursday fantasy cards only surface for a major difference.
THURSDAY_MAJOR_DIFF_PTS = 3.5

#: Per-stat coefficient of variation used ONLY when the market-implied
#: volatility cannot be backed out of the quote (e.g. a symmetric
#: -110/-110 line). Documented approximations; the 3-point probability
#: margin above is the safety buffer against misspecification.
STAT_DEFAULT_CV = {
    "passing_yards": 0.30,
    "rushing_yards": 0.55,
    "receiving_yards": 0.55,
    "receptions": 0.50,
}

#: Stats modeled as Poisson(expert_mean) for the cover probability.
POISSON_STATS = frozenset({
    "passing_tds", "rushing_tds", "receiving_tds", "interceptions",
})


# ---------------------------------------------------------------------------
# Play-gate stat eligibility (evidence-based, 2026-09-18)
# ---------------------------------------------------------------------------
#
# A stat may price a wager ONLY while the weekly retrospective backtest
# shows it earning its place. Eligibility is config, not code — and it is
# never permanent: the backtest is REPORT-ONLY (it recommends
# promotion/demotion in plain language); changing this list is always a
# human decision.
#
# This list gates WAGERS only. Every stat — eligible or not — still flows
# through the signals/fantasy pipeline (compute_driving_prop,
# fantasy_context): an excluded stat becomes a fantasy read, never a
# silent drop.
#
# 2026-09-18: "receptions" sits out. The Week-1 backtest of the real gate
# went 6-14 for -16% ROI on receptions flags — the market prices catches
# more efficiently than yardage, so there is no disagreement to exploit —
# while yardage props showed genuine edge (56-34, +19.1% ROI/unit over
# 90 scored plays). Receptions stays in fantasy reads; the weekly
# backtest re-scores it on paper and will recommend re-admission when
# the evidence flips.
GATE_ELIGIBLE_STATS = frozenset({
    "passing_yards", "rushing_yards", "receiving_yards",
    "passing_tds", "rushing_tds", "receiving_tds", "interceptions",
})
