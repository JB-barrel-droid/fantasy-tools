# How DDF Value should be built

Every number below was computed on 23 October 2026 unless otherwise noted,
using our reference implementation of the value engine.

Terms used below:

- **DDF Value (projections)** is the projection-side view: our own value for a player, the average of the projection sources' weight-adjusted indexed values.
- **Value above waivers** is how many points a player adds over the best freely
  available player at his position.
- **Adjusted value** is a source's value above waivers after it has been put on
  one common point scale, so sources can be averaged.

---

## Abstract

DDF Value (projections) is the equal-weight average of the projection sources' weight-adjusted indexed
values (defined above). This post asks whether that average can be improved -- whether some
sources are more accurate than others, and whether weighting or adjusting them
would produce a better fundamental estimate. The answer, on the data we have
today, is: probably not, and we cannot be confident until the right data has
been saved over more weeks.

The core problem is that we do not yet have week-ahead projections from all
three sources saved in a form that can be compared against realised fantasy
points. We have rest-of-season per-game projections (which predict season
averages, not next week's game), and we have ESPN's week-ahead projections for
2026 weeks 1 through 7. That is enough for a directional check but not for a
rigorous comparison. This post lays out what we have, what we need, the
evaluation protocol, and the candidate aggregators we should test once the data
exists.

## What DDF Value (projections) does today

DDF Value (projections) is the equal-weight mean of the weight-adjusted indexed values from
the three projection sources. Each
source's raw projections go through the same pipeline (value above waivers,
expected starts, fixed pie, DDF weights) and come out on a common scale. The
mean of those three numbers is DDF Value (projections).

Equal weights were chosen for good reasons (see post 3): no single source is
consistently better across positions and seasons, the blend is robust to one
source having a bad week, and the reader can see each source's contribution.
But "no evidence that unequal weights help" is different from "equal weights
are optimal". This post is about whether the evidence exists to say more.

## The data we have

### Projection snapshots

We save a weekly snapshot of every source's values (weeks 2 through 7 of the
2026 season). Each snapshot holds the rest-of-season per-game projection from each projection
source and the native trade values from each chart source. All seven sources
are present from week 4 onward; weeks 2 and 3 are missing CBS rest of season
(week 2 also missing Razzball).

These are rest-of-season projections, not week-ahead projections. A
rest-of-season projection predicts a player's average points per game over all
remaining weeks. A week-ahead projection predicts next Sunday's game
specifically, accounting for matchup, weather, injury status as of that week,
and bye. The two are related but different: a rest-of-season projection cannot
account for a player being on bye next week.

Separately, ESPN week-ahead projections are saved for 2026 weeks 1 through 7
(about 500 players per week), and RotoWire week-ahead projections via Sleeper
exist from 2018 onward (about 350 to 400 players per week). CBS rest of season
and Razzball week-ahead projections are not saved.

### Actual fantasy points

Weekly actual points for every player who recorded a stat line are saved for
2024, 2025, and 2026 weeks 1 through 6. NFL game logs from 2015 through 2025
(nflverse) cover the earlier seasons. A player who did not play (bye, injury, inactive) has no
row, which is correct: the projection should predict zero value for a player
who does not play, and the absence of a row encodes that.

### What the data can answer today

1. How accurate is each rest-of-season projection source at predicting
   single-week realised points? (A noisy proxy for source quality, since rest-of-season
   projections are not designed for single-week prediction.)
2. How does the equal-weight mean of the rest-of-season sources compare to the best
   single source, to the median, and to inverse-error-weighted combinations?
3. How do ESPN's week-ahead projections compare to the rest-of-season projections?

### What the data cannot answer yet

1. **Which source is best at week-ahead prediction.** We have week-ahead
   projections only from ESPN. Without CBS rest of season and Razzball
   week-ahead projections, we cannot compare the three sources on the target
   that matters.
2. **Whether weighting improves on equal weights for week-ahead projections.**
   The inverse-error weighting test below uses rest-of-season projections, which is the
   wrong target. The weights might differ for week-ahead accuracy.
3. **Rest-of-season accuracy.** Evaluating a rest-of-season projection
   requires waiting until the season ends and comparing the projection against
   the full-season average. We have no completed season with all three sources
   saved.
4. **Cross-season stability.** We have one partial season of data. Whether a
   source that is more accurate in 2026 weeks 2 through 6 would have been more
   accurate in 2025 or 2024 cannot be tested from the repo's data alone.
5. **Position-specific and tier-specific accuracy.** Five weeks is too few to
   split by position and tier with any confidence.

## Preliminary backtest: rest-of-season projections versus actual points

### Setup

For each of the five weeks where we have both saved projections and actuals
(weeks 2 through 6), we take each projection source's rest-of-season PPR
per-game projection for every player it covers and compare it to that player's
actual PPR points in that week's game. This is a noisy test -- a player on bye
scores zero while the rest-of-season projection is positive, and single-game variance is
large relative to the projection -- but it is the test the data supports.

### Results

MAE is the mean absolute error, the average size of the miss in points; RMSE
is the root mean squared error, which penalises large misses more.

| Source | Player-weeks | MAE | RMSE | Bias | 95% CI on MAE |
|---|---|---|---|---|---|
| ESPN (rest of season) | 1,425 | 4.68 | 6.40 | -0.90 | [4.46, 4.91] |
| CBS rest-of-season | 703 | 5.05 | 6.66 | -0.71 | [4.74, 5.36] |
| Razzball (rest of season) | 1,171 | 4.50 | 6.30 | -1.27 | [4.22, 4.75] |
| ESPN (week-ahead) | 1,600 | 4.36 | 5.96 | -0.16 | [4.17, 4.56] |
| Equal-weight mean | 1,122 | 4.61 | 6.28 | -1.10 | [4.37, 4.87] |
| Median | 1,122 | 4.61 | 6.30 | -1.13 | [4.37, 4.87] |
| Inverse-error weighted | 1,122 | 4.61 | 6.28 | -1.11 | [4.37, 4.87] |

"Bias" is the mean signed error (projection minus actual); negative means the
projections run low on average, which is expected because bye-week zeros pull
the actuals down while the rest-of-season projection does not account for
byes.

### What the numbers say

1. **ESPN week-ahead projections are the most accurate single predictor**
   (MAE 4.36), because they account for byes, matchups, and that week's injury
   status. Every rest-of-season source is worse, as expected.

2. **Among the rest-of-season sources, Razzball is the most accurate** (MAE 4.50),
   followed by ESPN (4.68) and CBS rest-of-season (5.05). But the confidence intervals
   overlap: Razzball's upper bound (4.75) overlaps ESPN's lower bound (4.46),
   and ESPN's upper bound (4.91) overlaps CBS rest-of-season's lower bound (4.74). On
   five weeks of data, we cannot confidently rank them.

3. **The equal-weight mean is indistinguishable from inverse-error weighting**
   (MAE 4.609 vs 4.612, a difference of 0.003 points -- pure noise). The
   leave-one-week-out inverse-error weights give almost exactly 1/3 to each
   source because the per-source MAEs are close.

4. **By position,** tight ends have the lowest MAE (4.13) and quarterbacks
   the highest (5.66), but the sample is small (128 to 445 player-weeks per
   position) and we cannot draw position-specific weighting conclusions.

5. **The bias is consistent across sources** (all negative, -0.71 to -1.27),
   which means all three rest-of-season projections overshoot actuals by a similar amount.
   This is the bye/injury effect: the rest-of-season projection assumes the player plays,
   and about 7 to 15 percent of the time he does not. Our expected-starts
   model already accounts for the bye schedule and the injury hazard; that,
   not a per-source adjustment, is the right fix for this bias.

### Honest limits

- Five weeks. Any of the per-source MAE differences could reverse with five
  more weeks of data.
- rest-of-season versus weekly. The test compares a rest-of-season number against a
  single game. A source that publishes a more stable rest-of-season line would look
  better here than one that reacts to weekly matchups, even though the
  matchup-adjusted one might be better for weekly predictions.
- Coverage. CBS rest-of-season covers 703 player-weeks (absent weeks 2 and 3); ESPN and
  Razzball cover 1,425 and 1,171. The comparison is not apples to apples.
- Survivorship. The player universe is today's; players dropped before
  week 7 are missing from every week.

## Evaluation protocol for the full study

Once week-ahead projections from all three sources have been saved for enough
weeks, the proper evaluation is:

### Target

Two targets, at different horizons:

1. **Week-ahead PPR points per game.** A player who does not play (bye,
   injury, inactive) has an actual of zero -- the projection should account
   for the probability of absence. This is the practical proxy because it
   can be scored every week.

2. **Rest-of-season value above waivers.** DDF Value is a rest-of-season
   quantity: it estimates a player's remaining usable production above the
   waiver line. That value declines as the season progresses -- fewer weeks
   remain for fill-in starts and breakout opportunities (see our manifesto on
   the value of a bench spot). The evaluation should therefore test whether source accuracy and
   optimal weights change with the week of the season. A source that is more
   accurate early (when the rest-of-season window is long and uncertain) may
   be less accurate late (when matchups and injury status dominate), or vice
   versa. Rest-of-season accuracy can only be scored at season end by
   comparing the week-t projection against the actual per-game average from
   week t+1 through the final week.

The protocol reports both targets. For the week-ahead target, the analysis
is stratified by early season (weeks 1-8), mid-season (weeks 9-13), and late
season (weeks 14-18) to detect horizon-dependent differences. If a source's
accuracy depends on the week of the season, the optimal aggregation may also
depend on the horizon -- for example, giving more weight to a source whose
week-ahead accuracy improves late when late-season decisions matter most.

### Splitting

Rolling-origin, time-ordered. Train on weeks 1 through t, evaluate on week
t+1. No future data ever enters the training window. The evaluation starts at
the first week where all three sources have at least four training weeks
(roughly week 8 if saving starts at week 8 of 2026, or earlier if historical
data can be reconstructed).

### Metrics

- **MAE** (mean absolute error): the average size of the miss, in points.
  The primary metric because it matches how a manager experiences error (how
  far off was the projection?).
- **RMSE** (root mean squared error): penalises large misses more than MAE.
  Relevant when a few catastrophic errors (season-ending injury, surprise
  benchings) matter more than many small ones.
- **Rank correlation** (Spearman): does the projection rank players in the
  right order within a position? This is what matters for trades: if the
  projection says player A is worth more than player B, is that true?
- **Calibration by position and tier**: is the projection equally accurate for
  quarterbacks and wide receivers, for starters and bench players? A method
  that is accurate on average but terrible for bench players would hurt the
  part of DDF Value that matters most for trade decisions (bench and fringe
  starter values).
- **Value-above-waivers error**: the same metrics applied to the Adjusted
  value rather than raw points, which is what DDF Value actually averages.

### Baselines

- **Equal-weight mean** (the current DDF Value method): each source counts
  equally.
- **Median**: more robust to one source being an outlier.
- **Best single source**: the source with the lowest MAE (mean absolute
  error) in the training window. If one source is consistently best, the optimal aggregator is to use
  only that source.

### Uncertainty

Bootstrap confidence intervals (1,000 draws, clustered by player because the
same player appears every week). A finding is reported only when the 95%
interval excludes zero. When differences between methods are within noise, we
say so plainly. No claims from tiny samples.

## Candidate aggregators

### 1. Equal-weight mean (current)

What it is: the arithmetic mean of the available sources' Adjusted values.

Data needed: only the sources themselves.

Overfit risk: zero -- no parameters are fitted.

When it is best: when sources are about equally accurate and their errors are
not strongly correlated. The preliminary backtest suggests this may be the
case.

### 2. Median

What it is: the middle value (or mean of the two middle values) across
sources.

Data needed: only the sources themselves.

Overfit risk: zero.

When it is better than the mean: when one source occasionally produces an
outlier (a wildly wrong projection). With three sources, the median ignores the
outlier. With an even number, the mean and median behave similarly.

### 3. Trimmed mean

What it is: drop the highest and lowest source, average the rest.

Data needed: only the sources themselves.

Overfit risk: zero.

When it works: with five or more sources. With three, it reduces to the
median. Relevant if additional projection sources are added.

### 4. Inverse-error weights

What it is: each source's weight is proportional to the inverse of its
historical MAE (or RMSE). A more accurate source gets more weight.

Data needed: aligned week-ahead projections and actuals for a training window
of at least eight weeks to estimate per-source accuracy stably.

Overfit risk: moderate. With three sources and eight weeks of data, the
weights are estimated from about 2,400 player-weeks, which is adequate for
overall weights but not for position-specific weights. The preliminary
backtest shows the weights converge to about 1/3 each, meaning the data does
not yet support unequal weights.

### 5. Inverse-error weights by position

What it is: separate weights for each position. A source that is best at
quarterback gets more weight for quarterbacks.

Data needed: the same as (4), but the training window must be long enough
to estimate four position-specific MAEs per source reliably -- roughly a full
season (about 300 player-weeks per position per source).

Overfit risk: high with one season of data. Twelve parameters (three sources
times four positions) from one season's data is a recipe for fitting noise.

### 6. Per-source bias correction

What it is: subtract each source's average signed error (bias) before
averaging. If ESPN projects 0.5 points low on average, add 0.5 to every ESPN
projection before blending.

Data needed: the same aligned data as (4). An additive bias is the simplest
correction; a multiplicative correction (scale factor) or a per-position
correction needs more data.

Overfit risk: low for overall additive bias (one parameter per source). The
preliminary backtest shows all three rest-of-season sources have similar negative bias
(-0.7 to -1.3), which is the bye/injury effect already addressed by expected
starts (the expected number of games a player starts, after byes and injuries). A per-source correction might remove a real difference (CBS rest-of-season's
bias is -0.71 vs Razzball's -1.27) or might fit noise.

### 7. Shrinkage toward a prior

What it is: blend the source's projection with a position-level baseline
(league-average points at the position, or the previous week's actual). The
blend coefficient controls how much the source's own number counts versus the
fallback.

Data needed: the baseline (available from the actuals data) and a tuning
window to set the blend coefficient.

Overfit risk: low if the coefficient is fixed (such as 0.9 source + 0.1
baseline); moderate if optimised per source or position.

When it helps: when a source's projection for a specific player is noisy but
the position baseline is informative -- mainly for players with few data
points (rookies, low-volume backups).

### 8. Stacking (regression on actuals)

What it is: a linear regression that predicts actual points from the three
sources' projections, with regularisation (ridge or lasso) to prevent
overfitting. The fitted coefficients become the weights.

Data needed: at least one full season of aligned week-ahead projections and
actuals (about 6,000 player-weeks across 17 weeks). Out-of-sample evaluation
on a second season.

Overfit risk: high with one season, manageable with two. The number of
parameters is small (three coefficients plus a constant, or twelve for
position-specific), but the effective sample size is limited by the number of
independent weeks (17), not the number of player-weeks.

### 9. Horizon-dependent weights

What it is: the source weights change with the week of the season. Early in
the season (weeks 1-8), rest-of-season projections carry most of the signal
and a source's season-long accuracy matters most. Late in the season (weeks
14-18), few weeks remain and the value of bench players shrinks (fewer fill-in
opportunities, less breakout runway). A source that reacts quickly to recent
production and matchup data may deserve more weight late, while a source that
is more stable and long-horizon-accurate may deserve more weight early.

Data needed: at least one full season of aligned projections and actuals,
stratified by early/mid/late. Two seasons to validate.

Overfit risk: moderate to high. With three time strata and three sources,
there are nine weight parameters. One season provides only about 5-6 weeks
per stratum, which is not enough for stable estimates. Two full seasons would
give a plausible pilot.

What it implies for DDF Value: if the weights should change mid-season, they
would need to be re-derived at a regular cadence (monthly or at a defined
week) rather than fixed at the start of the season. The expected-starts model
already accounts for the declining value of later weeks (the bye share falls
as weeks pass, and the spread of outcomes drifts with remaining weeks), so some
horizon adjustment is already built in. The question is whether the source
weights need to change too.

### 10. Recency and production trend (moved from 9)

What it is: incorporate the player's recent actual production (last 3 weeks)
as an additional input alongside the projections. A player trending up in
actuals while the projections have not caught up would get a boost.

Data needed: weekly actuals (available) and a mechanism to avoid double-
counting (the projections may already incorporate recent performance).

Overfit risk: moderate. The risk is that recent actuals predict regression to
the mean, not continued production, and that the projections already account
for them.

### 11. Handling missing and held sources

What it is: when a source is held (fidelity pulse red) or absent, the
current method drops it from the average. An alternative is to impute the
missing source from the other two (regressed toward the two-source mean) to
reduce the variance jump when a source drops out.

Data needed: historical instances of held sources (rare; FantasyCalc was held
in week 7) and their subsequent restoration.

Overfit risk: low.

## Decay: what changes as the season progresses

DDF Value is a rest-of-season quantity. As weeks pass, the value of every
player changes for reasons beyond projection accuracy:

1. **Fewer remaining weeks.** A player's value above waivers is his weekly
   surplus times the number of weeks that surplus enters a lineup. At week 2
   there are 16 weeks left; at week 14 there are 4. A bench player whose
   value comes from fill-in starts (post 1) loses value faster than a starter
   whose surplus enters the lineup every week, because the expected number of
   fill-in opportunities shrinks with the calendar.

2. **Reduced breakout runway.** A bench player with upside (our manifesto
   explains why that upside is worth paying for) has fewer weeks to prove himself as the season progresses. The option
   value of holding him declines.

3. **Better information late.** By week 12, projections are informed by ten
   weeks of actual production. The uncertainty bands narrow, which means the
   probability of a bench player surprising into start-worthiness drops, and
   the value of insurance against that surprise drops with it.

4. **Position-specific rates.** Running backs have the highest missed-game
   hazard (15.3%) and therefore the highest fill-in value early. But
   running back injuries also tend to be more catastrophic (season-ending),
   so the fill-in value at that position falls more steeply: by week 14, the
   fill-in opportunities from early-season injuries have already been
   realised.

The expected-starts model already accounts for the declining bye share (it
falls to 0 from week 15) and for the spread of outcomes, which widens with
the number of remaining weeks. What it does not model is:

- **Decay of option value** (the extra value of a player who might break out;
  the model leaves this out on purpose).
- **Discounting of later weeks.** The current model treats every remaining week
  equally.
- **Whether source accuracy changes with the season.** A source that is
  accurate early may be inaccurate late, or vice versa.

### Open questions about decay

Any change to DDF Value that depends on the time of season needs a definition
of decay first. The open questions are:

1. **What decays:** the fill-in share (already declining via expected starts),
   the option/breakout component (not modeled), or the overall value
   (discounting)?
2. **Over what horizon:** weekly (each remaining week is worth less than the
   previous), or by phase (preseason, early, mid, late, playoff)?
3. **Per position:** should the decay rate differ by position? Running back
   bench value decays faster because injuries are more catastrophic; tight
   end bench value may hold because the position is shallow.
4. **Relation to the rest-of-season target:** if DDF Value is the expected
   remaining contribution, and contribution declines with weeks left, then
   DDF Value should naturally fall for every player as the season progresses
   -- but it should fall faster for bench players than for starters, and
   faster at deep positions than shallow ones.

Post 1 notes that mid-season improvement is not modeled. That is the
upward-drift component of the same question: a bench player can gain value through actual
production, and that gain partially offsets the time decay. The two posts do
not conflict: post 1 describes the current model's bench-share mechanics,
this post asks how to aggregate sources and whether the aggregation should
change over time.

## What the full evaluation requires

To run the evaluation protocol, each week needs a structured record of:

1. **Week-ahead per-game projections** from each projection source (ESPN, CBS
   rest of season, Razzball), captured before Sunday kickoff, for each
   scoring. ESPN weekly projections are already saved. For CBS rest of season
   and Razzball we save the rest-of-season value but not the week-ahead value,
   which is the gap.

2. **Actuals** per player per week, which are saved and kept current.

3. **Injury and bye status** per player per week (injury status is saved daily
   and the bye schedule is known). This is needed to separate the accuracy of
   the projection from the accuracy of the availability estimate.

Each record needs the season, week, source, player, scoring, the projected
points per game, when the snapshot was taken, and whether it is a week-ahead or
rest-of-season projection.

## Conclusion

On five weeks of 2026 data, the three projection sources are close enough in
accuracy that equal weights and inverse-error weights produce the same result
to three decimal places. The data cannot yet distinguish them.

The limiting factor is data, not method: a fancier aggregation cannot be
validated without week-ahead projections from all three sources, aligned with
actuals. With ten or more weeks of aligned data, the evaluation protocol
described here can produce a defensible answer. Until then, equal weights are
the honest choice.

If the data does eventually show that one source is consistently more
accurate, the simplest change to DDF Value would be inverse-error weighting
(method 4) applied to the Adjusted values. It adds no new parameters. More
complex methods (stacking, position-specific weights) need a full season of
data and should be tested only after the simpler methods.

---

## Sources

| Claim | Where it comes from |
|---|---|
| Per-source error, bias, equal mean vs inverse-error, by position | Our source-accuracy backtest, run 23 October 2026 on the reference value engine |
| Weekly source values, weeks 2 to 7 | Saved weekly snapshots of every source |
| ESPN week-ahead projections | Saved weekly ESPN projections, 2026 |
| Actuals | Saved weekly game results, 2024 to 2026 |
| DDF Value from projections only; expected starts and the bye/injury bias | The value methodology |
