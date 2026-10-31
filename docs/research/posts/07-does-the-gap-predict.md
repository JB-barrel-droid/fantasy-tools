# Does the market gap predict anything?

This is early evidence: six saved weeks of one season (weeks 2 to 7 of 2026),
which gives five week-to-week comparisons. The uncertainty is shown with every
number. All figures were computed on 22 October 2026 with DDF Value (projections); an earlier version of DDF Value blended the trade charts
with the projections, and those figures are not used here.

Terms used below:

- **DDF Value (projections)** is the projection-side view: our own value for a player built from the projections only — the average of the projection
  sources' values above waivers (how many points a player adds over the best
  freely available player at his position), on one common point scale. Every figure in this post uses this view.
- **Rescaled** means a trade chart converted onto that same point scale, so a
  chart's price and our value can be compared directly.
- **The gap** is the market's price minus our value for the same player.

---

## Abstract

On the Trade targets page we compare our value for a player with what the
published trade charts pay for him. When the charts pay more than we think he is
worth, he is a Sell target; when they pay less, a Buy target. This post asks
whether that gap tells you anything about what happens next.

Over the five week-pairs we have, it does, a little, in one specific sense: the
chart price tends to move toward our value over the next week. The rank
correlation between the gap and the next week's change in the charts' price is
-0.22 (95 percent interval -0.28 to -0.16): the more the charts overpay
relative to us, the more their price falls. Of the players on the Buy list, the
charts' price rose the following week for 60 percent (interval 51 to 68
percent), against about 45 percent for any player. The effect is not explained
by the charts bouncing back from their own recent moves: chart moves tend to
continue rather than reverse, and the gap effect survives holding that fixed.

Two honest limits. First, the gap predicts our own value's next move about as
well as it predicts the charts' (correlation +0.21): the two sides converge
toward each other, which is what two noisy estimates of the same thing do. The
gap says "these two disagree and will disagree less next week", not "the market
is wrong and we are right". Second, the gap does not predict actual fantasy
points over the next two games relative to the projection (correlation about
zero). Five week-pairs is a small sample, so read every figure as an early
estimate with the uncertainty shown, not as a season-long fact.

## The question

Our manifesto says the fantasy market is efficient but not perfectly so, and
that the opportunity is where market price and underlying value diverge, "and
acting before that gap closes". The Trade targets page is built on that claim.
This post tests it with the data we have saved: when our value sits above or
below the charts' price, does the gap predict

(a) the charts' price next week and the week after (do overpriced players fall,
    underpriced ones rise?);
(b) the gap's own persistence (does it close, widen or stay?);
(c) the player's actual fantasy points relative to the projection?

## Data

**Weekly snapshots.** One saved snapshot per content week, weeks 2 to 7, holds
what each source published that week: the four trade charts (USA Today,
FantasyCalc, FantasyPros, CBS Sports) as their native 12-team, one-quarterback
values per scoring, and the three projection sources (ESPN, CBS rest of season,
Razzball) as per-game points per scoring. Week 2 has five sources (no CBS rest
of season, no Razzball); week 3 has six (no CBS rest of season); weeks 4 to 7
have all seven. Replaced versions of the same weeks (for example FantasyCalc
pulled again later in the week) are not used. The player universe is the
current player list (1,163 players), so a player who left it before 22 October
is not in any week (survivorship; see Limits).

**Actuals.** Realised points per game for each player for 2026 weeks 1 to 6
(about 360 player rows a week; a player with no row did not record a line that
week).

**What we do not have.** No record of actual trades proposed or accepted, no
chart publication times finer than the week, and no saved engine output from
earlier weeks (the engine is re-run on the saved inputs instead).

## Method

### Re-pricing each week

Each saved week is run through our reference implementation of the value
engine at the reader's default league settings (Full PPR, 12 teams, the
standard roster), with every source that has the week saved included, no holds,
and the fixed value pie (2,352 points at 12 teams; the pie is the total value
shared across all players, held constant so values are comparable between
weeks). The output per player per week is DDF Value and each chart's Rescaled
value. Because the pie is fixed, values are on the same scale in every week, so
a change in a player's price is a change in points.

Check: re-pricing week 7 from its snapshot reproduces the live run for 22
October exactly (3,670 values, maximum difference 0.0000). The reference and
the browser engine are also compared against each other on every data refresh,
with a tolerance of 0.05 points.

### The signal, exactly as the page computes it

- **Market consensus** is the median of the Rescaled chart values that price
  the player (a chart's 0 counts, a missing chart does not). The gap is the
  consensus minus our value; positive is a Sell, negative a Buy. A player is
  eligible only with two or more charts, a consensus above 0, and a strict
  majority of the charts on the same side of our value.
- **Sell target:** eligible, on the Sell side, and our value at least 5 points.
  The 5-point floor keeps near-zero values, where a small gap is mostly noise,
  off the list.
- **Buy target:** eligible, on the Buy side, and the rank-equivalent gap at his
  position (our value at the rank the charts give him, minus our value) at
  least 2 points below zero. The 2-point margin keeps a pure difference of
  scale between the charts and us from counting as a Buy.
- A player ESPN zeroes, or whose chart value the engine had to estimate, is
  never listed.

The test universe is every player the charts price above 0 with two or more
charts (about 205 players a week), not only the listed ones, so the
correlations do not depend on the list thresholds.

### Tests

- **(a) Price move.** For each player at week t, the change in the consensus
  price and in our value from t to t+1. Spearman rank correlation with the gap,
  and for the Buy list, the share whose consensus rose, against the base rate
  for all compared players. Intervals are 95 percent cluster bootstraps by
  player (1,000 draws), because the same player appears in up to five
  week-pairs.
- **Regression-to-the-mean control.** A placebo signal: the consensus price's
  own change from t-1 to t. If the gap effect were only prices bouncing back
  from a recent jump, the placebo would carry it. Both are entered together in
  a rank regression of the next-week change.
- **(b) Persistence.** Correlation of the gap with itself a week later, the
  share of gaps that change sign, and how much of the Buy list is still listed
  next week.
- **(c) Actuals.** Actual points per game over the next two games (weeks t and
  t+1) minus the ESPN per-game projection saved in week t, correlated with the
  gap.

## Results

### (a) Both sides move toward each other

DDF Value from projections only (Full PPR, 12 teams; 1,017 player-weeks, 238
players, weeks 2 to 6 predicting 3 to 7):

| Test | Spearman, next week [95 percent interval] |
|---|---|
| Gap vs change in the chart consensus | -0.22 [-0.28, -0.16] |
| Gap vs change in our value | +0.21 [+0.14, +0.27] |
| Gap vs change in the gap | -0.36 [-0.41, -0.31] |
| Rank regression, gap and placebo together | gap t = -7.6, placebo t = +5.0 |

The sign is the one the page assumes: the more the charts overpay relative to
us, the more their price falls next week. The placebo runs the other way. A
chart price that rose last week tends to keep rising this week (most likely
the charts updating at different speeds, so a move spreads across them over two
weeks). So the gap effect is not the charts reverting from their own jumps; it
survives with the placebo held fixed.

The Buy list has 121 player-weeks (62 players); the consensus rose the next
week for 60 percent (interval 51 to 68 percent), against about 45 percent for
any compared player.

The gap also predicts our own next move just as well: a player the charts pay
more for sees our value rise next week, and a player they pay less for sees
it fall. The two estimates move toward each other at about the same rate.
Read plainly: when the charts and the projections disagree, the disagreement
shrinks, and roughly half of the shrinking is us catching up to the charts.

What this means for you: a Sell target is a player whose asking price is more
likely to fall than rise over the next week, and a Buy target one whose price
is more likely to rise. It does not mean the charts have the player wrong; our
own number moves too.

### (b) The gap persists

The gap is sticky: its rank correlation with itself a week later is +0.68, and
+0.56 two weeks later. Only 21 percent of gaps change sign in a week. A Buy
target has a 55 percent chance of still being a Buy target next week, so the
lists turn over about half each week, mostly because a player crosses a
threshold, not because the gap flips.

What this means for you: a gap you see today is usually still there next
week, but the closing is gradual. A single week is rarely the whole move.

### (c) The gap does not predict points against the projection

883 player-weeks (227 players, weeks 2 to 6) have a saved ESPN projection and
at least one game in the next two. The correlation between the gap and the
realised points per game minus that projection is -0.04 [-0.12, +0.04]. The
projection itself is informative (correlation with actual +0.59); the gap adds
nothing we can detect in two games. With this sample a true effect of a few
tenths of a point per game would be invisible, so this is "not detected", not
"absent".

What this means for you: the gap is about price, not about how many points a
player will score. Do not read a Buy target as a player who will outscore his
projection.

## Limits

- **Five week-pairs, one season.** A correlation of -0.22 on about a thousand
  player-weeks is statistically clear, but one season is one draw. Different
  weeks could land higher or lower, so quote these as early evidence.
- **Survivorship.** The universe is the player list as of 22 October. Players
  who dropped out before then are missing from every week; players whose charts
  dropped them in week t+1 count as a price fall to 0, which is a real fall but
  an extreme one.
- **Engine.** Numbers come from the reference implementation, not the browser,
  as of 22 October 2026.
- **Mechanics.** The charts are rescaled to our curve with one factor per chart
  per week; a change in our overall scale moves every rescaled value together.
  The consensus is a median of two to four charts, so a single chart's update
  can move it a lot, and a chart dropping a player sends the consensus toward
  0.
- **No trades.** We have no record of what anyone accepted. "The chart price
  fell" is a proxy for "the player became harder to sell at that price", not a
  measure of trade outcomes.
- **Realised points.** Two games is a short window and actuals exist only to
  week 6; bye and injury weeks are skipped, not zeroed.
- **Mid-week timing.** We have one chart version per week, so we cannot tell
  whether a move happens within the week the gap appears.

## Conclusion

The gap between our value and the charts' price is a modest, consistent
predictor of where the charts' price goes next week, in the direction the page
assumes, and it is not a mean-reversion artifact. It is also a predictor of
where our own value goes, in the opposite direction: the two converge. It does
not predict fantasy points over the next two games. For a manager, that means a
Sell target is a player whose asking price is more likely to fall than rise over
the next week, and a Buy target one whose price is more likely to rise; it does
not mean the charts have the player wrong.

---

## Sources

| Claim | Where it comes from |
|---|---|
| Correlations, hit rates, placebo, persistence, actuals | Our backtest of the saved weekly snapshots, run 22 October 2026 on the reference value engine |
| Signal definition | The Trade targets page rules, rebuilt in the backtest |
| Weekly snapshots, weeks 2 to 7 | Saved source values for each content week |
| Realised points | Weekly game results for 2026 weeks 1 to 6 |
