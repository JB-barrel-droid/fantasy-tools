# Open Question 4: Bias-Adjusted Charts in DDF Value

Context written for Jeremy's decision (JEG-613, 2026-10-22).

## What the question means

DDF Value is our single best estimate of a player's fundamental value -- what
his production is worth in this league's scoring and roster. It is computed as
the equal-weight mean of each included source's Adjusted value for that player.

Today, the included sources are both projection-based series (ESPN, CBS ROS,
Razzball) and published trade charts (FantasyCalc, USA Today, FantasyPros, CBS).
Every source passes through the same Adjusted view: its positional and
starter/bench biases are normalized out, so the remaining difference between
sources is pure player-level opinion.

"Bias-adjusted charts" refers to the published trade charts after this
normalization. The question is: **should these bias-adjusted trade charts count
as inputs to DDF Value?**

Three options:

1. **Fundamental input** -- keep trade charts in the DDF Value blend alongside
   projections. This is the current behavior.
2. **Market input** -- remove trade charts from DDF Value; show them only as
   market-value comparisons. DDF Value would be computed from projections only
   (ESPN, CBS ROS, Razzball).
3. **Out** -- remove bias-adjusted charts from the product entirely (not just
   from DDF Value).

## What each option changes in the numbers

Measured at PPR 12-team (the default setup), all sources included. Values are
the Adjusted view (the DDF Value input), in the 0-to-~70 scale.

### Current behavior (option 1: all sources)

DDF Value = mean of up to 5 sources per player (3 projections + 2 charts at
this fixture). A player's DDF Value is pulled toward the trade-chart consensus
when it disagrees with projections.

Example top players (PPR/12):

| Player | ESPN | CBS ROS | Razzball | FantasyCalc | CBS | All-source DDF | Proj-only DDF | Shift |
|--------|------|---------|----------|-------------|-----|---------------|--------------|-------|
| pk 2227 (top) | 71.1 | 73.8 | 59.2 | 62.2 | 56.3 | 64.5 | 68.0 | -3.5 |
| pk 217 | 43.5 | 48.2 | 51.5 | 57.2 | 58.2 | 51.7 | 47.7 | +4.0 |
| pk 1110 | 38.7 | 28.5 | 10.4 | 38.3 | 37.7 | 30.7 | 25.9 | +4.8 |

Across all 12 setups, including charts shifts individual values by up to
roughly 6 points in either direction relative to projections-only.

### Option 2: projections only

DDF Value = mean of ESPN, CBS ROS and Razzball only. Trade charts appear on the
Indexed and VORP tabs for comparison but do not enter the fundamental estimate.

Effect: DDF Value moves closer to the projection consensus. Where trade charts
agree with projections, the change is small; where they disagree, the shift can
be several points. Players whom charts value much higher than projections (often
name-brand veterans with declining production) lose DDF Value. Players whom
charts undervalue (often breakout candidates or less-traded positions) gain it.

### Option 3: out entirely

The bias-adjusted chart series would be removed from the product. Only raw
(un-adjusted) published charts would remain on the Indexed tab, and DDF Value
would use projections only. This is the most aggressive simplification.

## Arguments for each option

### Keep charts in (option 1 -- current behavior)

- More inputs smooth out noise from any single projector's error. With 5
  sources instead of 3, a bad projection from one source has less impact.
- Trade charts embed crowd wisdom: millions of transactions and expert
  consensus. After removing systematic bias (position and starter/bench
  weighting), the remaining signal is player-level opinion that may capture
  information projections miss (usage trends, coaching changes, trade rumors).
- The manifesto says market value is distinct from fundamental value, but the
  Adjusted view strips out the market's structural biases. What remains is
  closer to a fundamental signal than a market one.

### Remove charts from DDF Value (option 2)

- DDF Value is supposed to be fundamental value -- what production is worth.
  Trade charts are market prices, not production estimates. Even after bias
  removal, a chart's per-player values reflect trading demand, name
  recognition, roster construction and league psychology, not projected points.
- Mixing market and fundamental signals makes DDF Value neither purely
  fundamental nor purely market, which weakens the core product insight (the
  gap between the two).
- When trade charts and projections agree, adding charts is redundant. When they
  disagree, the disagreement is the product -- showing it as a gap is more
  useful than averaging it away.
- Jeremy's inline comment on the goals doc says "We need research to get to
  what this should be in terms of weights & adjustments" -- the current
  equal-weight blend was a convenience, not a researched decision.

### Remove entirely (option 3)

- Simplifies the product. Fewer series to maintain and explain.
- Risk: loses the ability to show "what does this chart think, on our scale?"
  which is valuable for comparing chart-vs-chart.

## Measurements at all 12 setups

The magnitude of the shift (charts-in vs charts-out) across all setups:

- Mean absolute shift per player (top 50): 1.5 to 3.2 points depending on setup
- Maximum shift: up to 6.5 points (about 9% of the 70-point scale)
- The shift is NOT constant across positions: it is largest at positions where
  charts and projections disagree most (often TE and WR2+)
- The shift does NOT vary much across scorings for the same player

## Recommendation

**Option 2: remove charts from DDF Value; keep them on the comparison tabs.**

Reasoning:
- It sharpens DDF Value as a purely fundamental estimate, which is the
  manifesto's intent.
- The gap between market (charts) and fundamental (projections) IS the product.
  Averaging them together hides the signal the dashboard exists to show.
- Option 3 is too aggressive: bias-adjusted charts on the comparison tabs have
  clear value for chart-vs-chart analysis.
- Jeremy's inline comment ("We need research") suggests the current blend is
  provisional; removing charts is the conservative choice until that research
  exists.

This is a product decision for Jeremy. The three options are all implementable
without engine changes; only the source lists that feed each DDF version change.
