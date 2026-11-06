# How we rescale trade charts

Research post 4.

---

## Abstract

Every trade-value source uses its own scale. FantasyCalc gives its top player
a value above 10,000; CBS gives the same player 56. To show them side by side we
put them on one common scale, and the rescaling must not change the source's own
ranking order. If a source ranks player A above player B, our rescaled values
must agree.

We use one factor per source: a single multiplier that brings the source's
total, over the players it lists, in line with the DDF Value total over the same
players. One factor keeps every ranking the source made, across positions,
between starters and bench players, everywhere. An older method rescaled each
position separately, which broke rankings. This post explains the problem, the
rule we use now, what the factors were in the week we measured, and how to read
the rescaled lines in the Market view.

### Three kinds of source

The site sorts its sources into three kinds, and this post uses the same names
and descriptions. The site's [Value chart](#player-values) is where they are
explained, in its source groups and in each player's detail; this post only
says which ones are rescaled.

- **Published charts:** published trade-value opinions. USA Today, FantasyPros
  and CBS.
- **Observed-trade estimates:** algorithmic estimates from completed fantasy
  trades. FantasyCalc.
- **Projections:** what players are projected to score, turned into trade value
  for your league. ESPN, CBS rest of season and Razzball.

The rescaling in this post applies to the three published charts and to
FantasyCalc's observed-trade estimate, in exactly the same way. Projections are
not rescaled, because they have no trade value of their own to put on a scale.

Terms used below. DDF Value is our one number per player: the average of four
trade-value inputs (the three published charts and FantasyCalc's observed-trade
estimate), each weight-adjusted at your league settings. Weight-adjusted means
turned into value above waivers and re-weighted to our position weights, so it
is our opinion, informed by the source. Rescaled values are a source's own
values multiplied by one factor so they sit on the DDF Value scale: the
source's opinion, on our scale. Value above waivers is how much better a player
is than the best player you could pick up for free at his position. The
rosterable count is the number of players at a position that the league's teams
can actually hold.

When these figures were measured: every figure below comes from one data build
of the site, made on October 28, 2026 at 23:27 UTC, with every source at its
2026 Week 8 release, in a 12-team league unless the text says otherwise. They
were measured once on that build and have not been refreshed since; they are
Week 8 figures, not current-week ones. The one older figure, from October 8,
2026, is labeled where it appears.

## The problem: rescaling can break rankings

A trade chart is a publisher's own assessment of what each player is worth in
a trade. The ranking order is the chart's core product: if the chart says the
third-best wide receiver is worth more than the eighth-best running back, that
is a claim about the trade market.

When we rescale a source to put it on the same scale as DDF Value, the total
has to match, but the source's own rankings must not be rearranged in the
process.

The older method rescaled each position separately, so each position got its
own factor (and, at the time, starters and bench players got different factors
too). A pair of players the publisher ranked one way across two positions could
come out the other way. When we retired that method on October 8, 2026, the
saved 12-team values of that time carried over 15,000 such flipped pairs across
the four trade-value sources. That count is historical: it describes the old
method on the data of that day.

The same thing happens on the Week 8 data. If we gave each position its own
factor (the simpler half of the old method, without the starter and bench
split), 2,091 of the 79,272 pairs of listed players across the three published
charts and FantasyCalc would swap order in a full PPR league. One example, from
the USA Today chart:

| | Published | One factor (0.490) | A factor per position |
|---|---|---|---|
| Trey McBride (TE) | 53 | 26.0 | 16.6 |
| Rhamondre Stevenson (RB) | 30 | 14.7 | 16.8 |

USA Today values McBride at 1.77 times Stevenson. One factor keeps that.
Separate tight end and running back factors put Stevenson ahead, which is a
claim USA Today never made.

## The rule: one factor per source

A source's rescaled values are its own values times one factor:

    factor   = DDF Value total / source total
               (over the players the source lists that also have a DDF Value)

    rescaled = source value x factor

That is the whole calculation. The source's total over shared players matches
the DDF Value total over the same players, and every ranking the source made
survives exactly. Listed players whose DDF Value is 0 count in both totals;
players the tool estimated for the source (below) do not.

### The Week 8 factors

At 12 teams, by scoring format, on the October 28 build. The shared count is
how many listed players enter the totals.

| Source | Standard | Half PPR | Full PPR | Shared players (full PPR) |
|---|---|---|---|---|
| USA Today | 0.523 | 0.509 | 0.490 | 270 |
| FantasyCalc (observed-trade estimate) | 0.00658 | 0.00658 | 0.00655 | 199 |
| FantasyPros | 0.675 | 0.678 | 0.678 | 178 |
| CBS | 1.345 | 1.273 | 1.193 | 123 |

The factor moves with scoring because DDF Value does: a format that changes
how much a player is worth changes the DDF Value total the chart is matched
to. It also grows with league size, because the total value DDF Value hands
out grows with the number of starting lineup spots in the league: the CBS
chart's full PPR factor is 0.804 at 8 teams, 1.002 at 10, 1.193 at 12 and 1.372
at 14.

### Same total, different shape

Matching totals does not make the sources agree. Jahmyr Gibbs is every
source's top player in Week 8, and his rescaled value in a full PPR league is:

| Source | Its own value | Rescaled |
|---|---|---|
| FantasyCalc (observed-trade estimate) | 10,402 | 68.1 |
| CBS | 56 | 66.8 |
| FantasyPros | 75.1 | 50.9 |
| USA Today | 81 | 39.7 |

USA Today lists 270 players and spreads its value further down its list, so the
same total leaves less for the top. That difference is the publisher's view of
how steeply value falls from the top player to the depth players, and the
rescaled chart shows it rather than hiding it.

The player detail on the site keeps the two kinds of trade-value source apart.
Its Published chart average is the equal-weight mean of the three published
charts, shown only when all three have a value: for Gibbs here,
(39.7 + 50.9 + 66.8) / 3 = 52.5. FantasyCalc's observed-trade estimate, 68.1,
is shown beside it, not inside it. Both are comparisons only; neither changes
DDF Value or any trade read.

### Why one factor works

Multiplying every value by the same positive number does not change any ratio
between two values. If the source says player A is worth twice player B, the
rescaled values say the same thing. The order within a position, across
positions, and between starters and bench players is kept.

A factor per position applies different multipliers to different positions,
which changes the ratios between positions. That is repricing, not
rescaling.

### What gets repriced, and where

The per-position repricing is not gone. It lives in DDF Value and in the Value
above waivers view. Those turn each trade-value source into value above waivers
at your league settings, with your league's position weights applied. That is
where the tool's opinion about positional value lives.

The Market view shows each source's own opinion, rescaled to our scale. The DDF
Value view shows our opinion, built from the sources' data.

The two connect exactly. The weight adjustment ignores a source's scale, so
adjusting a source's rescaled values gives the same numbers as adjusting its
own ones: DDF Value is the average of the four trade-value inputs'
weight-adjusted rescaled values. It is not the trade chart average, the plain
average of the four rescaled values (the three published charts and
FantasyCalc), which Compare reads as the market. That average is an estimate,
not a record of what a trade will pay. For rostered players in Week 8 the two
differ by 2.8 points for the middle player and by up to 18.2.

### When a source cannot be rescaled

If a source shares no players with DDF Value, or either total is zero or less,
there is no positive factor. The whole source then shows no rescaled values,
with the note "Not enough shared players to index", rather than a guess.

### If you choose your own value basis

You can change what DDF Value is built from (one source, or a blend of sources
with your own weights). The trade-value sources are then rescaled to your basis
instead, and the page says so, for example "rescaled to FantasyCalc". The rule
is the same one factor per source, so each source's rankings are still kept.

## The ranking check

Every time the site's data is published, an automatic check looks at every
pair of players each trade-value source ranks apart, at every saved scoring and
league size, and stops the publish if any pair has its rescaled order flipped,
or tied when the source ranked them apart. The same check runs in the core test
suite.

With one factor the check is satisfied by construction: on the Week 8 build it
finds 0 flipped pairs on every source. It exists as a safety net, so that a future change
to the calculation cannot reach the site with broken rankings.

## How to read the Market view

In the Market view's list of series, the rescaled lines sit in two groups,
Published charts and Observed-trade estimates. A published chart's line is
"<publisher> chart (rescaled)", and FantasyCalc's is "FantasyCalc
observed-trade estimate (rescaled)": each is its source's own values times its
one factor. What this
means:

- **The rankings are the source's.** If FantasyCalc ranks a player above
  another player, the rescaled values agree.
- **The scale is DDF Value's.** A value of 50 on CBS and 50 on FantasyCalc mean
  the same thing on the common scale.
- **The shape is the source's.** Two sources can agree on the order and still
  disagree on how much the top player is worth compared with the tenth.
- **Projections are not shown by default.** Projections have no published
  trade value, so in this view a projection line shows its adjusted value. Add
  them from Customize.

## Estimated players

When a trade-value source does not list a player who is within the
rosterable count, the tool estimates his value for that source. This is the
fill-in value. It is scaled from the other trade-value sources that list him,
and it is capped at the source's lowest listed value at his position, so the
source's listed order is never disrupted. An estimated player's rescaled value
is his fill-in value times the same one factor, marked "≈ estimated" with the
reason.

How often this happened in a 12-team, full PPR league in Week 8: FantasyCalc
got 12 estimated players, FantasyPros 20 and CBS 51. USA Today lists deep
enough that it needed none.

---

## Sources

| Claim | Where it comes from | When |
|---|---|---|
| The three kinds of source and their names | The Value chart's source groups and player detail | Current rule |
| One factor per source, and when a source cannot be rescaled | The value methodology, section on rows, DDF Value and Indexed values | Current rule |
| DDF Value is the four trade-value inputs' adjusted values, averaged | The value methodology, section on DDF Value (decision of October 25, 2026) | Current rule |
| The Published chart average beside FantasyCalc's estimate | The site's player detail comparisons | Current rule |
| Factors, shared counts, Gibbs and McBride examples, the 2,091 flipped pairs, estimate counts | The Week 8 data build of October 28, 2026 (23:27 UTC) run through the reference value engine | Measured once, Week 8 |
| Over 15,000 flipped pairs under the old method | The saved 12-team values at the time the old method was retired | Historical, October 8, 2026 |
| The ranking check | The site's publish step and core test suite | Current rule |
| Fill-in values and their cap | The value methodology, section on filling in rosterable players | Current rule |
