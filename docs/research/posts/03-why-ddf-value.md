# Why DDF Value is the core

Research post 3 (JEG-545, post 1 of 4). Draft for Jeremy's review.
Copy rules: for trades others will accept; no title abbreviations.

---

## Abstract

Every player on this tool has one number that matters most: the DDF Value. It
is the average of the four trade charts' weight-adjusted indexed values for that
player. It does not favor any single source, it uses each source's own ranking
order, and it exists in two views so you can see what the trade charts say
separately from what the projections say.

This post explains what goes into DDF Value, why it is built the way it is,
and what the two views tell you.

> Evidence: `docs/methodology.md` sections VP-3 through VP-6.
> Engine: `app/trade-value-chart/assets/value-model.js`, `runValuePipeline`.
> Reference: `pipelines/value_reference.py`.

## What DDF Value is

DDF Value is one number per player, the same in every tab and view on the
site. It is the average of the four trade charts' weight-adjusted indexed values.

- **Equal weight.** Each of the four trade charts counts once in DDF Value.
  The projection sources form the separate DDF Value (projections) view.
  Within each view, none is weighted more heavily than any other.
- **Adjusted values only.** The Adjusted value is what a source's own
  ranking implies at your league settings, after rescaling to a common pie.
  It is not the raw published number, and it is not the Indexed value
  (the chart's value on the common scale, before position and bench weighting). DDF Value always reads from
  Adjusted.
- **One number per player.** DDF Value does not change between tabs. The
  "Trade charts (as published)" tab shows each chart's Indexed values; the
  "Adjusted values" tab shows each source's Adjusted values; the "Value
  above waivers" tab shows each source's surplus. But DDF Value stays the
  same across all three. It is the tool's own assessment.

## How each source reaches the average

Every source goes through the same pipeline:

1. **Native values.** Each source publishes its own numbers -- trade values
   for charts, projected points per game for projections.
2. **League allocation.** The tool determines how many starters, bench
   players, and waiver-level players exist at each position for your league
   (teams, scoring, roster). This is the same for every source.
3. **Value above waivers.** Each player's value is measured against the
   waiver line at his position (the value of the first player past the
   rostered count). This splits into a bench slice (below the starter line)
   and a starter slice (above it).
4. **DDF weights.** The tool averages each source's implied position mix
   (how much value the source puts on each position's starters versus bench
   players) to get a single set of weights. The weight normalization uses a
   15% bench-share parameter by default (the reader's slider can change it).
   This is the normalization target, not the measured bench share -- the
   measured share from expected starts is about 9 to 12 percent (see post 1).
5. **Fixed pie.** Every source's values are rescaled so its total equals the
   league pie (28 per starting slot times teams times slots). A chart that
   lists 50 players and a projection that covers 300 both sum to the same
   total.
6. **Adjusted value.** Each player's rescaled value -- bench slice times the
   bench rate, starter slice times the starter rate. This is what DDF Value
   reads.

The result: every source's Adjusted values are on the same scale, use the
same league settings, and preserve that source's own ranking order within
each position. The average of the four trade charts' weight-adjusted indexed values is DDF Value.

## Two views

DDF Value comes in two views:

| Version | What it averages | When to use it |
|---|---|---|
| DDF Value | The four trade charts | The default. The average of the four trade charts' weight-adjusted indexed values. |
| DDF Value (projections) | The three projections only | What the production projections say, independent of market pricing. Use this when the market might be wrong about a player. |

Both views are available in Customize.

## Why equal weights

A natural question: should better sources count more?

Equal weights were chosen deliberately:

- **No source is consistently more accurate** across positions and seasons.
  A projection that is best at quarterback may be worst at tight end.
- **Market value and fundamental value are different things.** A trade
  chart's value reflects what others will pay; a projection's value reflects
  expected production. Weighting one more highly conflates the two.
- **Robustness.** Equal weights are insensitive to one source having a bad
  week. With equal weights and seven sources, a single outlier moves the
  average by at most one-seventh.
- **Transparency.** When every source counts equally, the reader can see
  each one's contribution and judge for herself.

## What DDF Value does not do

- It does not use Indexed values directly (the charts' values on the common
  scale, before weighting). DDF Value averages the weight-adjusted indexed
  values in the common Adjusted scale.
- It does not leave out a source for being "too different." If a source
  disagrees with the others, that disagreement shows up in the spread,
  not in an exclusion.
- It does not adjust for the number of players a source lists. A chart
  that lists fewer players has its unlisted rosterable players estimated
  from the other charts (fill-in), so every source prices every rosterable
  player.

## The live widget

> Widget (for the research tab): one player's DDF Value broken into its
> inputs. Select a player and see each source's Adjusted value, the
> equal-weight mean, and which version (blended, charts, projections) each
> source contributes to.

---

## Evidence links

| Claim | Source |
|---|---|
| Equal-weight mean of Adjusted | `docs/methodology.md` VP-6.3 |
| Two views | `docs/methodology.md` VP-6.3, JEG-497 |
| DDF weights are the average of source mixes | `docs/methodology.md` VP-4 |
| Fixed pie at 28 per slot | `docs/methodology.md` VP-5.1 |
| Bench share normalization at 15% default | `docs/methodology.md` VP-3.4 (OC-2); measured share: ES-5, post 1 |
| Fill-in of unlisted players | `docs/methodology.md` VP-2.4 |
