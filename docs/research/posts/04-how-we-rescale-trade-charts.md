# How we rescale trade charts

Research post 4.

---

## Abstract

Every trade chart uses its own scale. One chart might give the top player a
value of 10,000; another might give him 100. To compare them, we need a common
scale, but the rescaling must not change the chart's own ranking order. If
a publisher ranks player A above player B, our rescaled values must agree.

We use one factor per chart: a single multiplier that brings the chart's total
in line with the DDF Value total over the players they share. One factor
preserves every ranking the publisher made, across positions, between
starters and bench players, everywhere. The older method rescaled each position
separately, which broke rankings. This post explains the problem it caused, the
method we use now, and what it means for reading the "Trade charts (as
published)" tab.

Terms used below. DDF Value is our one number per player: the equal-weight
average of the three projection sources' values (ESPN, CBS rest of season and
Razzball), each turned into a value at your league settings. Rescaled values
are a trade chart's own values multiplied by one factor so they sit on the DDF
Value scale. Value above waivers is how much better a player is than the best
player you could pick up for free at his position.

## The problem: rescaling can break rankings

A trade chart is a publisher's own assessment of what each player is worth
in a trade. The ranking order is the chart's core product: if the chart says
the third-best wide receiver is worth more than the eighth-best running back,
that is a claim about the trade market.

When we rescale a chart to put it on the same scale as DDF Value, we need
the total to match, but we must not rearrange the chart's own rankings in
the process.

The old method rescaled each position separately (starters and bench players
got different factors, and each position got its own total to match). This
meant a chart's ranking across positions could invert, so that a pair of
players the publisher ranked one way came out the other way. One chart ranked
a wide receiver third overall, but after per-position rescaling he showed as
fifth. Across all four charts, the 12-team saved values carried over 15,000
such pairwise inversions.

## The fix: one factor per chart

The rule, in place since 2026-10-08: a published chart's Rescaled values
are its native values times one factor per chart.

    factor  = DDF Value total / native total
              (over the players the chart lists that also have a DDF Value)

    Rescaled = native x factor

That is it. One multiplication. The chart's total over shared players
matches the DDF Value total over the same players, and every ranking the
publisher made survives exactly.

### Why one factor works

Multiplying every native value by the same constant does not change any
ratio between two values. If the chart says player A is worth twice player B,
the Rescaled values say the same thing. The order within a position is
preserved. The order across positions is preserved. The order between
starters and bench players is preserved.

Per-position rescaling applies different multipliers to different positions,
which changes the ratios between positions. That is repricing, not rescaling.

### What gets repriced, and where

The per-position repricing is not gone. It moved to the Adjusted values
tab and the "Value above waivers" tab. Those views turn each source into
value above waivers at the reader's league settings, with the league's own
position weights applied. That is where the tool's opinion about positional
value lives.

The "Trade charts (as published)" tab shows the publisher's opinion, on a
common scale. The Adjusted values tab shows the tool's opinion, informed by
the publisher's data.

## The ranking check

Every time the site is built, an automatic check looks at every pair of
players a chart ranks apart and fails the build if any pair has its Rescaled
order inverted. It runs across all four charts at every league setting.

With one factor, the check is trivially satisfied (one positive multiplier
cannot change order). It exists as a safety net: if anyone changes the
Rescaled calculation, the check catches inversions before they reach the site.

## How to read the "Trade charts (as published)" tab

When you open "Trade charts (as published)," each chart's values are its
native trade values multiplied by one factor so the chart's total matches
the DDF Value total over the same players. What this means:

- **The rankings are the publisher's.** If FantasyCalc ranks a player above
  another player, the Rescaled values agree.
- **The scale is DDF Value's.** The numbers are comparable across charts:
  a value of 50 on CBS and 50 on FantasyCalc mean the same thing on the
  common scale.
- **Projections are available but off by default.** Projections do not have
  a "published" trade value, so in this tab they show their Adjusted
  values, turned off by default. Turn them on in Customize.

## Estimated players

When a chart does not list a player who is within the rosterable count (the
number of players at a position that the league's teams can actually hold),
the tool estimates his value from the other charts. This is the fill-in value.
An estimated player sits at or below the chart's lowest listed player at
that position, so the publisher's listed order is never disrupted. The
Rescaled value of an estimated player is his fill-in value times the same one
factor, marked "estimated" with the reason.
