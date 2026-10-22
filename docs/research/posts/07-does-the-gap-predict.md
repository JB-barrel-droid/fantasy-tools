# Does the market gap predict anything?

Research post 7 (JEG-882). Draft for Jeremy's review.
Copy rules: for trades others will accept; no named players; no title abbreviations; no vanity stats.

Every number below was written by `tools/research/gap_backtest.py` on 2026-10-22
(output: [`../data/gap_backtest.md`](../data/gap_backtest.md), `.json`, `.csv`).
Engine: the Python value reference `pipelines/value_reference.py`
(value-reference-002/2, the engine's reference implementation), re-pricing the
saved content weeks 2 to 7 of the 2026 season. The live site that day was build
`tv-20261022-1627-fee76c6`, whose DDF Value still blends the trade charts with
the projections (PR #814, which makes DDF Value projections-only, was open and
unmerged on 2026-10-22). So the post reports the signal both ways: as the site
computes it today, and as it will after PR #814.

---

## Abstract

On the Trade targets page we compare our value for a player with what the
published trade charts pay for him. When the charts pay more than we think he is
worth, he is a Sell target; when they pay less, a Buy target. This post asks
whether that gap tells you anything about what happens next.

Over the five week-pairs we have (weeks 2 to 7), it does, a little, in one
specific sense: the chart price tends to move toward our value over the next
week. A player the charts overpay for today is priced lower by the charts next
week more often than not (65 percent of Sell targets, against a base rate of 55
percent for any player); a player they underpay for is priced higher next week
(66 percent of Buy targets, against 45 percent). The rank correlation between the
gap and the next week's chart move is about minus 0.15, and it holds in all
twelve league settings. It is not explained by the charts bouncing back from
their own recent moves: that effect runs the other way (chart moves continue
rather than reverse), and the gap effect survives holding it fixed.

Two honest limits. First, the gap predicts our own value's next move about as
well as it predicts the charts', once DDF Value is projections-only: the two
sides converge toward each other, which is what two noisy estimates of the same
thing do. The gap says "these two disagree and will disagree less next week",
not "the market is wrong and we are right". Second, the gap does not predict
actual fantasy points over the next two games relative to the projection
(correlation about zero). Five week-pairs is a small sample; the result should
be read as preliminary and re-run at the end of the season.

## The question

Manifesto section 2 says the fantasy market is efficient but not perfectly so,
and section 11 says the opportunity is where market price and underlying value
diverge, "and acting before that gap closes". The Trade targets page is built
on that claim. This post tests it with the data we have saved: when our value
sits above or below the charts' price, does the gap predict

(a) the charts' price next week and the week after (do overpriced players fall,
    underpriced ones rise?);
(b) the gap's own persistence (does it close, widen or stay?);
(c) the player's actual fantasy points relative to the projection?

## Data

**Weekly snapshots.** `data/history/week-2.json` to `week-7.json`, one per
content week, hold what each source published that week: the four trade charts
(USA Today, FantasyCalc, FantasyPros, CBS Sports) as their native 12-team,
one-quarterback values per scoring, and the three projection sources (ESPN, CBS
rest-of-season, Razzball) as per-game points per scoring. Players are keyed by
the repo's `player_key`, the same key as `players.json`. Week 2 has five sources
(no CBS rest-of-season, no Razzball); week 3 has six (no CBS rest-of-season);
weeks 4 to 7 have all seven. `data/history/superseded/` keeps replaced versions
of the same weeks (for example FantasyCalc pulled again later in the week); they
are not used here. The player universe is the current `players.json` (1,163
players), so a player who left the universe before 2026-10-22 is not in any week
(survivorship; see Limits).

**Actuals.** `data/inputs/weekly_actuals_2024_2026.csv` holds realised points
per player per game for 2026 weeks 1 to 6 (about 360 player rows a week; a
player with no row did not record a line that week).

**What is not in the repo.** No record of actual trades proposed or accepted, no
per-chart publication timestamps finer than the week, no saved engine output
from earlier weeks (the engine is re-run on the saved inputs instead).

## Method

### Re-pricing each week

Each saved week is run through the reference value pipeline at the reader's
league settings (default Full PPR, 12 teams, the standard roster), with every
source that has the week saved included, no holds, and the fixed value pie
(2,352 points at 12 teams). The output per player per week is DDF Value (the
blend and the projections-only version) and each chart's Indexed value (the
chart rescaled to our point scale). Because the pie is fixed, values are on the
same scale in every week, so a change in a player's price is a change in points.

Self-test: re-pricing week 7 from its snapshot reproduces the reference's live
run for 2026-10-22 exactly (3,670 values, maximum difference 0.0000; the chain
had held FantasyCalc that day, so the live run and the self-test read
FantasyCalc from the version actually served). The reference and the browser
engine are checked against each other on every chain run (`value_check
compare`, tolerance 0.05).

### The signal, exactly as the page computes it

From `app/v2/targets.js`:

- `marketConsensus` (lines 95 to 117): the market consensus is the median of
  the Indexed chart values that price the player (a chart's 0 counts, a missing
  chart does not); `gap = consensus - ours`; positive is a Sell, negative a Buy.
  A player is eligible only with two or more charts, a consensus above 0 and a
  strict majority of the charts on the same side of our value.
- Sell (lines 171 to 175): eligible, side Sell, our value at least `SELL_FLOOR`
  (5 points).
- Buy (lines 64 to 84, 176 to 180): eligible, side Buy, and the rank-equivalent
  gap at his position (our value at the rank the charts give him, minus our
  value) at or under `-BUY_RANK_MARGIN` (2 points), so a pure difference of
  scale between the charts and us is not a Buy.
- A player ESPN zeroes or whose chart value the engine estimated is never
  listed (lines 181 to 186).

The script rebuilds all of this per week. The test universe is every player the
charts price above 0 with two or more charts (about 205 players a week), not
only the listed ones, so the correlations do not depend on the list thresholds.

### Tests

- **(a) Price move.** For each player at week t, the change in the consensus
  price and in our value from t to t+1 and to t+2. Spearman rank correlation
  with the gap; quintile buckets of the gap; and for the Buy and Sell lists, the
  share whose consensus moved toward our value (Sell: fell; Buy: rose), against
  the base rate for all compared players. Intervals are 95 percent cluster
  bootstraps by player (1,000 draws), because the same player appears in up to
  five week-pairs.
- **Regression-to-the-mean control.** A placebo signal: the consensus price's
  own change from t-1 to t. If the gap effect were only prices bouncing back
  from a recent jump, the placebo would carry it. Both are entered together in
  a rank regression of the next-week change.
- **Position control.** Correlations within each position and with the gap
  demeaned by position.
- **(b) Persistence.** Correlation of the gap with itself a week later, share of
  gaps that shrink, share that flip sign, share of the gap's movement that came
  from the chart side, and how much of each list is still listed next week.
- **(c) Actuals.** Actual points per game over the next two games (weeks t and
  t+1) minus the ESPN per-game projection saved in week t; correlation with the
  gap and share of listed players who beat the projection.
- **Settings.** The headline test repeated in all twelve settings (three
  scorings by four league sizes).

## Results

### (a) The charts move toward our value, a little

Our value as the site blends it today (Full PPR, 12 teams; 1,023 player-weeks,
239 players, weeks 2 to 6 predicting 3 to 7):

| Test | Spearman, next week [95 percent interval] |
|---|---|
| Gap vs next week's change in the chart consensus | -0.15 [-0.22, -0.09] |
| Gap vs next week's change in our value | +0.01 [-0.06, +0.08] |
| Position-demeaned gap vs change in consensus | -0.14 [-0.21, -0.08] |
| Placebo (consensus's own move last week) vs change in consensus | +0.18 [+0.11, +0.24] |
| Rank regression of the change on gap and placebo together | gap t = -4.9, placebo t = +5.0 (n = 818) |

The sign is the one the page assumes: the more the charts overpay relative to
us, the more their price falls next week. By quintile of the gap, the top
fifth (charts pay 2.7 to 9.4 points more than us) fell by 0.66 points on average
and rose only 34 percent of the time; the middle three fifths were flat; the
bottom fifth (charts pay 2.7 to 15 points less) was flat on average and rose 50
percent of the time. The asymmetry matters: in today's blend the Sell side
carries the signal, the Buy side barely does.

The placebo runs the other way. A chart price that rose last week tends to keep
rising this week (momentum, most likely the charts updating at different speeds
so a move spreads across them over two weeks). So the gap effect is not the
charts reverting from their own jumps; it survives with the placebo held fixed.

Two weeks ahead the correlation is weaker, -0.10 [-0.20, -0.01] (816
player-weeks, weeks 2 to 5), and the top quintile fell 1.05 points.

**Hit rates for the lists.** Sell targets: 142 player-weeks (69 players); the
consensus fell next week for 65 percent [57, 73], against 55 percent [52, 59]
for any compared player. Buy targets: 47 player-weeks (32 players); the
consensus rose for 66 percent [52, 80], against 45 percent [41, 48]. The
eligible-but-not-listed Buy players (the "scale, not a mispricing" group the
rank margin filters out) rose only 52 percent of the time, so the JEG-833 rank
margin is doing real work; the Sell floor's effect is similar but smaller (59
percent for all eligible Sells).

**By position.** RB -0.15 (313 player-weeks), WR -0.14 (412), TE -0.36 (138),
QB +0.02 (160). The gap says nothing about next week's quarterback price in a
one-quarterback league; it says most about tight ends.

**By week.** -0.07, -0.16, -0.04, -0.27, -0.20 for weeks 2 to 6. The two weeks
with the strongest result are the two most recent; weeks 2 and 3 had fewer
projection sources saved. Five numbers is not a trend.

**All twelve settings** (DDF Value blend, next week): the correlation runs from
-0.10 (standard, 10 teams) to -0.17 (half PPR, 14 teams), every interval
excluding zero; Sell-target hit rates 54 to 70 percent; Buy-target hit rates 54
to 70 percent on 35 to 47 player-weeks each.

### The projections-only gap (after PR #814): both sides converge

With DDF Value from projections only (1,017 player-weeks, 238 players):

| Test | Spearman, next week [95 percent interval] |
|---|---|
| Gap vs change in the chart consensus | -0.22 [-0.28, -0.16] |
| Gap vs change in our value | +0.21 [+0.14, +0.27] |
| Gap vs change in the gap | -0.36 [-0.41, -0.31] |
| Rank regression, gap and placebo together | gap t = -7.6, placebo t = +5.0 |

The chart-side signal is stronger than with the blend, and the Buy list is
larger (121 player-weeks, 62 players; consensus rose for 60 percent [51, 68]).
But now the gap predicts our own next move just as well: a player the charts
pay more for sees our value rise next week (67 percent of Buy targets had our
value fall toward the charts; 53 percent of Sell targets had it rise). The two
estimates move toward each other at about the same rate. Read plainly: when
the charts and the projections disagree, the disagreement shrinks, and roughly
half of the shrinking is us catching up to the charts. In today's blend our
value does not move toward the charts (+0.01) only because the blend already
contains them.

### (b) The gap persists, and lists churn

The gap is sticky: its rank correlation with itself a week later is +0.84
(blend) or +0.68 (projections-only), and +0.73 / +0.56 two weeks later. Only 13
percent (blend) or 21 percent (projections-only) of gaps change sign in a week.
About half of gaps shrink in a week (54 percent), half of the movement coming
from the chart side (49 percent). A Sell target has a 56 percent chance of still
being a Sell target next week; a Buy target 32 percent (blend) or 55 percent
(projections-only). So the lists turn over about half each week, mostly
because a player crosses a threshold, not because the gap flips.

### (c) The gap does not predict points against the projection

883 player-weeks (227 players, weeks 2 to 6) have a saved ESPN projection and
at least one game in the next two. The correlation between the gap and the
realised points per game minus that projection is -0.01 [-0.09, +0.07] (blend)
and -0.04 [-0.12, +0.04] (projections-only). Sell targets beat their projection
41 percent [30, 50] of the time (118 player-weeks), Buy targets 55 percent [39,
71] (42). The projection itself is informative (correlation with actual +0.59);
the gap adds nothing we can detect in two games. With this sample a true effect
of a few tenths of a point per game would be invisible, so this is "not
detected", not "absent".

## Limits

- **Five week-pairs.** Correlations of -0.15 on about a thousand player-weeks
  are statistically clear, but the week-to-week spread (-0.04 to -0.27) says a
  season could land anywhere in that range. Nothing here should be quoted as a
  season-level fact until re-run at the end of 2026.
- **Survivorship.** The universe is today's `players.json`. Players who dropped
  out before 2026-10-22 are missing from every week; players whose charts
  dropped them in week t+1 count as a price fall to 0, which is a real fall but
  an extreme one.
- **Engine.** Numbers come from the Python reference, not the browser, at the
  commit of 2026-10-22. The blend numbers reflect DDF Value as it was before PR
  #814; after it merges they are stale for the live product and the
  projections-only columns are the live ones. Before JEG-804, DDF Value and the
  chart mean correlated at 0.9966, which is why the blend's gap barely predicts
  our own value's move.
- **Mechanics.** The charts are indexed to our curve with one factor per chart
  per week; a change in our overall scale moves every indexed value together.
  The consensus is a median of two to four charts, so a single chart's update
  can move it a lot, and a chart dropping a player sends the consensus toward 0.
- **No trades.** We have no record of what anyone accepted. "The chart price
  fell" is a proxy for "the player became harder to sell at that price", not a
  measure of trade outcomes.
- **Realised points.** Two games is a short window and actuals exist only to
  week 6; bye and injury weeks are skipped, not zeroed.

### What would settle it

- The remaining weeks of 2026 (weeks 8 to 18 give ten more week-pairs) with
  actuals to season end, re-running the same script; a follow-up ticket is
  linked from JEG-882.
- The superseded mid-week chart versions, to see whether the move happens
  within the week the gap appears.
- Any record of trades proposed through the tool and whether they went through.

## What changes in the product

Nothing in the engine. The post supports the page's claim in its weakest form
and should be quoted that way:

1. Copy on Trade targets can say that the chart price of a Sell target fell the
   next week about two times in three over weeks 2 to 7, against about one in
   two for any player, with a link here. It should not say the market is wrong.
2. The JEG-833 rank margin for Buys and the JEG-820 Sell floor are supported:
   the players they leave off had hit rates near the base rate.
3. Quarterback gaps had no next-week signal in one-quarterback leagues; the
   page could say so until a season of data says otherwise.
4. The projections-only gap (PR #814) has the stronger chart-side signal and a
   usable Buy list; the blend's Buy list was too small to say much.

The decisions these raise are posted on JEG-882 as choices for Jeremy.

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

## Evidence links

| Claim | Source | Script |
|---|---|---|
| Correlations, quintiles, hit rates, placebo, positions, settings | [`../data/gap_backtest.md`](../data/gap_backtest.md) (2026-10-22) | `tools/research/gap_backtest.py` |
| Per player-week rows | `../data/gap_backtest.csv` | same |
| Signal definition | `app/v2/targets.js` lines 36 to 193 | rebuilt in `build_signal` |
| Week snapshots and their versions | `data/history/index.json`, `pipelines/build_week_history.py` | - |
| Self-test against the live run | `gap_backtest.json` key `self_test` | `self_test` |
