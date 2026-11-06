# Does the Trade chart average gap predict anything?

This is early evidence from saved 2026 content weeks 2 to 7.
These figures are **mean-based**, rerun on 2026-11-01T20:01Z with the
reference engine at commit `88f51c1f`. Jeremy approved the research
aggregation change on 31 October 2026 (JEG-1411). The earlier October 22
figures used a different aggregation and are superseded here.

Terms used below:

- **DDF Value (projections)** is the projection-side view: the average of the
  projection sources' weight-adjusted indexed values. Every result below uses
  this view as our value.
- **Indexed** is a chart's value on the common scale, before position and
  bench weighting.
- **Trade chart average (mean)** is the arithmetic mean of the available
  Indexed trade-chart values for a player. A real zero counts; a missing chart
  does not.
- **The gap** is the Trade chart average minus DDF Value (projections).
  A positive gap is the Sell side; a negative gap is the Buy side.

## Data and method

The chart inputs are saved as-published 2026 weekly snapshots, then modeled
through the checked-out reference engine. These are historical inputs, not
fresh current-week prices. The player universe has 1161 players
from this checkout. The actuals file contains 2026 weeks
1 to 8; each outcome uses only the next
two calendar weeks from the signal week, skipping a missing game row rather
than counting it as zero. Older reports used earlier player and actuals files,
so their sample sizes need not match this rerun.

The headline setting is Full PPR, 12 teams, one quarterback and the standard
roster. Each saved week uses the sources recorded for that content week, with
no holds. Indexed chart prices and DDF Value (projections) use the same league
scale. A gap can therefore reflect a price disagreement at those settings.

The research signal requires at least two charts, a positive Trade chart
average, and a strict majority of charts on the same side of our value.
A Sell requires our value of at least 5. A Buy requires the position
rank-equivalent gap to be at most -2. Players zeroed by the saved ESPN
projection or given estimated chart prices are excluded from the lists.
This is the research mean variant of the signal; it does not change the site
or engine's calculations.

We compare each gap with the next change in the Trade chart average and in our
value, then check gap persistence. A placebo control uses the chart average's
own previous move. Correlations are Spearman rank correlations. Intervals are
95 percent cluster bootstraps by player, with 1,000 draws at the headline
setting. Results are associations, not evidence that an actual offer was accepted.

## Results

The next-week panel has 1259 player-weeks and 292 players,
covering signal weeks [2, 3, 4, 5, 6]. Figures below show correlations and their
95 percent intervals unless specified otherwise.

| Test | Mean-based result |
|---|---|
| Gap vs next change in Trade chart average | -0.19 [-0.26, -0.13] (n=1259) |
| Gap vs next change in our value | +0.19 [+0.13, +0.25] (n=1259) |
| Gap vs next change in gap | -0.34 [-0.39, -0.29] (n=1259) |
| Placebo vs next change in Trade chart average | +0.20 [+0.14, +0.27] (n=1011) |
| Gap on the same rows as the placebo | -0.22 [-0.28, -0.14] (n=1011) |
| Rank regression, gap and placebo together | gap t=-6.9, placebo t=+6.5 (n=1011) |

The Buy list has 122 player-weeks and 61 players. Its share
with a rising Trade chart average next week is 66% [56, 74] (n=122),
against the all-player base rate of 43% [40, 46] (n=1259).
The intervals matter: a Buy label is not a promise that the price will rise.

| Persistence test | Mean-based result |
|---|---|
| Gap vs gap one week later | +0.66 [+0.61, +0.72] (n=1259) |
| Gap vs gap two weeks later | +0.54 [+0.46, +0.61] (n=997) |
| Gaps changing sign next week | 17% [15, 20] (n=1259) |
| Buy targets still listed next week | 51% [39, 60] (n=122) |

The realised-points panel has 1299 player-weeks and 283 players,
using signal weeks [2, 3, 4, 5, 6, 7]. The gap's correlation with actual points per
game minus the saved ESPN projection is -0.05 [-0.12, +0.01] (n=1299).
The projection's correlation with actual points is
+0.63.
A price gap and a forecast of fantasy production answer different questions.

## Limits and interpretation

- The history covers one season and only a few weekly transitions. It cannot
  establish a stable effect across seasons.
- This is a modeled rerun with the current checkout's player list and
  reference engine. Players absent from that list are absent from every week.
- Chart values come from published snapshots; Indexed values, gaps, list
  memberships and statistics are modeled. Actuals are observed game results.
- A chart dropping a player can produce a large move. The mean of two to four
  charts remains sensitive to outliers and changes in which charts price him.
- No actual proposed or accepted trades are recorded. A price move is a proxy,
  not a measured trade outcome.
- The historical snapshot consistency diagnostic has maximum difference
  14.3009 against the checkout's current fixture;
  it does not pass the 0.05 tolerance. It is not proof of historical live-site
  parity, and no live site was checked for this rerun.

For a manager, use the gap as a description of disagreement between the chart
average and the projection view. Read it alongside the uncertainty and roster
context, rather than as an instruction to buy or sell.

## Evidence

- Reproduction: `python3 tools/research/gap_backtest.py --output-dir docs/research/data/jeg1411-mean --post docs/research/posts/07-does-the-gap-predict.md`.
- [Mean rerun tables](../data/jeg1411-mean/gap_backtest.md),
  [full statistics](../data/jeg1411-mean/gap_backtest.json) and
  [player-week rows](../data/jeg1411-mean/gap_backtest.csv).
- [Before/after comparison](../data/jeg1411-mean/before-after.md) separates
  the old published figures from a median baseline on the same current inputs.
- The underlying script also runs Standard, Half PPR and PPR at each supported
  team count. Its settings appendix is explicitly the DDF Value chart view;
  the headline study above is DDF Value (projections).
