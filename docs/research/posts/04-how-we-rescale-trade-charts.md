# How we rescale trade charts

Research post 4.

---

## Abstract

Every trade chart uses its own scale. FantasyCalc gives its top player a value
above 10,000; CBS gives the same player 56. To show the charts side by side we
put them on one common scale, and the rescaling must not change the chart's own
ranking order. If a publisher ranks player A above player B, our rescaled
values must agree.

We use one factor per chart: a single multiplier that brings the chart's total,
over the players it lists, in line with the DDF Value total over the same
players. One factor keeps every ranking the publisher made, across positions,
between starters and bench players, everywhere. An older method rescaled each
position separately, which broke rankings. This post explains the problem, the
rule we use now, what the factors are this week, and how to read the rescaled
charts in the Market view.

Terms used below. DDF Value is our one number per player: the average of the
four trade charts' (FantasyCalc, USA Today, FantasyPros and CBS) weight-adjusted
values at your league settings. Weight-adjusted means turned into value above
waivers and re-weighted to our position weights, so it is our opinion,
informed by the chart. Rescaled values are a trade chart's own published values multiplied by
one factor so they sit on the DDF Value scale: the publisher's opinion, on our
scale. Value above waivers is how much better a player is than the best player
you could pick up for free at his position. The rosterable count is the number
of players at a position that the league's teams can actually hold.

All figures below are measured on Week 8 of the 2026 season, with the charts
and projections as published on October 28, 2026, in a 12-team league unless
the text says otherwise.

## The problem: rescaling can break rankings

A trade chart is a publisher's own assessment of what each player is worth in
a trade. The ranking order is the chart's core product: if the chart says the
third-best wide receiver is worth more than the eighth-best running back, that
is a claim about the trade market.

When we rescale a chart to put it on the same scale as DDF Value, the total has
to match, but the chart's own rankings must not be rearranged in the process.

The older method rescaled each position separately, so each position got its
own factor (and, at the time, starters and bench players got different factors
too). A pair of players the publisher ranked one way across two positions could
come out the other way. When we retired that method in October 2026, the saved
12-team values carried over 15,000 such flipped pairs across the four charts.

The same thing happens on this week's data. If we gave each position its own
factor (the simpler half of the old method, without the starter and bench
split), 2,091 of the 79,272 pairs of listed players across the four charts
would swap order in a full PPR league. One example, from USA Today:

| | Published | One factor (0.490) | A factor per position |
|---|---|---|---|
| Trey McBride (TE) | 53 | 26.0 | 16.6 |
| Rhamondre Stevenson (RB) | 30 | 14.7 | 16.8 |

USA Today values McBride at 1.77 times Stevenson. One factor keeps that.
Separate tight end and running back factors put Stevenson ahead, which is a
claim USA Today never made.

## The rule: one factor per chart

A chart's rescaled values are its published values times one factor:

    factor   = DDF Value total / published total
               (over the players the chart lists that also have a DDF Value)

    rescaled = published value x factor

That is the whole calculation. The chart's total over shared players matches
the DDF Value total over the same players, and every ranking the publisher
made survives exactly. Listed players whose DDF Value is 0 count in both
totals; players the tool estimated for the chart (below) do not.

### This week's factors

At 12 teams, by scoring format. The shared count is how many listed players
enter the totals.

| Chart | Standard | Half PPR | Full PPR | Shared players (full PPR) |
|---|---|---|---|---|
| USA Today | 0.523 | 0.509 | 0.490 | 270 |
| FantasyCalc | 0.00658 | 0.00658 | 0.00655 | 199 |
| FantasyPros | 0.675 | 0.678 | 0.678 | 178 |
| CBS | 1.345 | 1.273 | 1.193 | 123 |

The factor moves with scoring because DDF Value does: a format that changes
how much a player is worth changes the DDF Value total the chart is matched
to. It also grows with league size, because the total value DDF Value hands
out grows with the number of starting lineup spots in the league: CBS's full
PPR factor is 0.804 at 8 teams, 1.002 at 10, 1.193 at 12 and 1.372 at 14.

### Same total, different shape

Matching totals does not make the charts agree. Jahmyr Gibbs is every chart's
top player this week, and his rescaled value in a full PPR league is:

| Chart | Published | Rescaled |
|---|---|---|
| FantasyCalc | 10,402 | 68.1 |
| CBS | 56 | 66.8 |
| FantasyPros | 75.1 | 50.9 |
| USA Today | 81 | 39.7 |

USA Today lists 270 players and spreads its value further down its list, so the
same total leaves less for the top. That difference is the publisher's view of
how steeply value falls from the top player to the depth players, and the
rescaled chart shows it rather than hiding it.

### Why one factor works

Multiplying every value by the same positive number does not change any ratio
between two values. If the chart says player A is worth twice player B, the
rescaled values say the same thing. The order within a position, across
positions, and between starters and bench players is kept.

A factor per position applies different multipliers to different positions,
which changes the ratios between positions. That is repricing, not
rescaling.

### What gets repriced, and where

The per-position repricing is not gone. It lives in DDF Value and in the Value
above waivers view. Those turn each chart into value above waivers at your
league settings, with your league's position weights applied. That is where
the tool's opinion about positional value lives.

The Market view shows each chart's own opinion, rescaled to our scale. The DDF
Value view shows our opinion, built from the charts' data.

The two connect exactly. The weight adjustment ignores a chart's scale, so
adjusting a chart's rescaled values gives the same numbers as adjusting its
published ones: DDF Value is the average of the four charts' weight-adjusted
rescaled values. It is not the trade chart average, the plain average of the
four rescaled values, which Compare uses as the market's view. For rostered
players this week the two differ by 2.8 points for the middle player and by up
to 18.2.

### When a chart cannot be rescaled

If a chart shares no players with DDF Value, or either total is zero or less,
there is no positive factor. The whole chart then shows no rescaled values,
with the note "Not enough shared players to index", rather than a guess.

### If you choose your own value basis

You can change what DDF Value is built from (one source, or a blend of sources
with your own weights). The charts are then rescaled to your basis instead, and
the page says so, for example "rescaled to FantasyCalc". The rule is the same
one factor per chart, so the publishers' rankings are still kept.

## The ranking check

Every time the site's data is published, an automatic check looks at every
pair of players each chart ranks apart, at every saved scoring and league size,
and stops the publish if any pair has its rescaled order flipped, or tied when
the chart ranked them apart. The same check runs in the core test suite.

With one factor the check is satisfied by construction: this week it finds 0
flipped pairs on every chart. It exists as a safety net, so that a future change
to the calculation cannot reach the site with broken rankings.

## How to read the Market view

In the Market view, each chart's line is "<publisher> chart (rescaled)": its
published values times its one factor. What this means:

- **The rankings are the publisher's.** If FantasyCalc ranks a player above
  another player, the rescaled values agree.
- **The scale is DDF Value's.** A value of 50 on CBS and 50 on FantasyCalc mean
  the same thing on the common scale.
- **The shape is the publisher's.** Two charts can agree on the order and still
  disagree on how much the top player is worth compared with the tenth.
- **Projections are not shown by default.** Projections have no published
  trade value, so in this view a projection line shows its adjusted value. Add
  them from Customize.

## Estimated players

When a chart does not list a player who is within the rosterable count, the
tool estimates his value for that chart. This is the fill-in value. It is
scaled from the other charts that list him, and it is capped at the chart's
lowest listed value at his position, so the publisher's listed order is never
disrupted. An estimated player's rescaled value is his fill-in value times the
same one factor, marked "≈ estimated" with the reason.

How often this happens in a 12-team, full PPR league this week: FantasyCalc
gets 12 estimated players, FantasyPros 20 and CBS 51. USA Today lists deep
enough that it needs none.

---

## Sources

| Claim | Where it comes from |
|---|---|
| One factor per chart, and when a chart cannot be rescaled | The value methodology, section on rows, DDF Value and Indexed values |
| DDF Value is the four charts' adjusted values, averaged | The value methodology, section on DDF Value (decision of October 25, 2026) |
| Factors, shared counts, Gibbs and McBride examples, the 2,091 flipped pairs | This week's data run through the reference value engine (readout of October 29, 2026) |
| Over 15,000 flipped pairs under the old method | The saved 12-team values at the time the old method was retired (October 8, 2026) |
| The ranking check | The site's publish step and core test suite |
| Fill-in values and their cap | The value methodology, section on filling in rosterable players |
