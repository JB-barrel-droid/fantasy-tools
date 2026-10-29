# Missing is not zero, and the one-source rule

Research post 5.

---

## Abstract

When a source does not list a player, what value should the tool show? When
only one source prices a player, how much should you trust the number? These
two rules, how a missing value is shown and the one-source note, decide what
the tool shows for players at the edges of the roster, and they affect every
trade that involves a deep bench player.

The short version: a trade chart that prices a position but does not list a
player gives him a real 0, or an estimate if he is rosterable, and that number
counts. A source with no opinion shows a dash, and a dash is left out, never
counted as 0.

Terms used below. DDF Value is our one number per player: the four trade
charts (FantasyCalc, USA Today, FantasyPros and CBS), each adjusted to your
league settings and averaged. DDF Value (projections) is the alternate: the
three projection sources (ESPN, CBS rest of season and Razzball), each turned
into a value at your league settings and averaged. The rosterable count is the
number of players at a position that the league's teams can actually hold,
worked out from league size, roster slots and bench spots, with players ranked
by projected points. A fill-in value is an estimate for a rosterable player a
chart does not list. The waiver line is the value of the best player you could
pick up for free at a position; value is measured above it, so 0 means at or
below the waiver line.

All figures below are measured on Week 8 of the 2026 season, with the charts
and projections as published on October 28, 2026, in a 12-team, full PPR
league unless the text says otherwise. "Rostered players" means the 168
players DDF Value places in a starting lineup or on a bench in that league.

## What a trade chart shows for each player

Each chart is read position by position. For a position the chart prices (it
lists at least one player there), every player gets one of three things on that
chart's line:

### The chart lists him

He gets the chart's value, adjusted to your league. A listed player can still
be at 0 if the chart puts him at or below the waiver line.

### He is rosterable, but the chart does not list him

The tool estimates his value for that chart from the other charts that list
him, scaled to this chart's own values. The estimate is capped at the chart's
lowest listed value at his position, so the publisher's listed order is never
disrupted. It is marked "≈ estimated", with the reason.

Example: CBS does not list Dalton Kincaid (TE) this week. The other three charts
put him at 6.6 (USA Today), 4.0 (FantasyCalc) and 10.5 (FantasyPros) after
adjustment. CBS's estimate is 3.5, and his DDF Value is the average of all
four, 6.1.

### He is past rosterable depth, and the chart does not list him

He shows **0** on that chart, with the note "Below rosterable depth; <chart>
doesn't list him". The chart prices players at his position, and he is past
the point where any team in the league would hold him, so the chart's silence
is a judgment, not a gap.

Example: Emmett Johnson (RB) is on the bench in DDF Value's rostered set, but he
sits past CBS's depth by projected points, and CBS does not list him. USA Today
has him at 0.2, FantasyCalc at 0.04 and FantasyPros at 4.0; CBS shows 0. His
DDF Value is (0.2 + 0.04 + 4.0 + 0) / 4 = 1.1. The zero counts, and it pulls
the average down, which is the point: one chart's view is that he has no trade
value at this depth.

### When a chart shows a dash

A dash ("--") means the chart has no opinion, and it is left out of DDF Value
entirely. On a chart's line this happens only when the **chart does not price
the position at all** (it lists nobody there): "<chart> doesn't price <pos>".

A chart can also be out for the whole week: paused because its data failed a
check, or not yet published for the current week. Its values are then not used
anywhere in DDF Value, and the page says why.

### How often each case comes up

For the 168 rostered players this week, each chart's line is:

| Chart | Listed | Estimated | 0, below its depth |
|---|---|---|---|
| USA Today | 168 | 0 | 0 |
| FantasyCalc | 162 | 6 | 0 |
| FantasyPros | 152 | 14 | 2 |
| CBS | 123 | 35 | 10 |

USA Today and FantasyCalc list deep enough that their lines are almost all
their own numbers. CBS lists 123 players in this format, so a fifth of its
rostered values are estimates. Across scoring formats (12 teams, the 672
chart values for rostered players):

| | Standard | Half PPR | Full PPR |
|---|---|---|---|
| Estimated | 82 | 63 | 55 |
| 0, below the chart's depth | 14 | 15 | 12 |

Over all 741 players with a row this week, 545 have a DDF Value of exactly 0:
every chart puts them at or below the waiver line. That is a measured 0, and
it is different from a missing value.

## What a projection shows for each player

Projections follow a stricter rule, because a projection that skips a player
is not making a judgment about his trade value; it simply did not project him.

- **The projection projects him:** its value, turned into value above waivers
  at your league settings.
- **The projection does not project him:** a dash, "<source> doesn't project
  this player". It is left out of DDF Value (projections). Projections are
  never filled in.
- **The projection does not price the position:** a dash, left out.

Example: Razzball does not project Jonah Coleman (RB) this week. ESPN has him at
3.4 and CBS rest of season at 12.7, so his DDF Value (projections) is the
average of those two, 8.0, not of three values with a zero.

## The rules in plain terms

| Situation | What shows | Counts in DDF Value? | Counts in DDF Value (projections)? |
|---|---|---|---|
| Chart lists the player | The chart's value | Yes | No |
| Chart gives a fill-in value | The estimate, marked "estimated" | Yes | No |
| Chart prices the position, player below rosterable depth | 0 ("Below rosterable depth") | Yes, as 0 | No |
| Chart does not price the position | -- ("Source doesn't price this position") | No (left out) | No |
| Chart paused or not yet published this week | Labeled on the page | No (left out) | No |
| Projection projects the player | The projection's value | No | Yes |
| Projection does not project him | -- ("Source doesn't project this player") | No | No (left out) |

## When only one source prices a player

When exactly one of a version's sources has a value for a player and the
others are left out, that version's value equals that one source's value. The
tool shows it with the note "Only one source prices this player", next to the
value it applies to.

How often this happens depends on the version:

- **DDF Value: 0 of 741 players this week.** Every chart prices every
  position, and a chart gives each player either his value, an estimate or a
  0. So while all four charts are in, every player has four inputs. The note
  appears on DDF Value only when three of the four charts are out for the week,
  or when you build DDF Value from a blend of sources of your own and only one
  of them prices the player. A basis of one source you chose yourself is not
  flagged.
- **DDF Value (projections): 202 of 741 players this week**, almost all past
  rosterable depth; 2 of them are rostered. Example: only ESPN projects Malachi
  Fields (WR), so his DDF Value (projections), 0.9, is ESPN's value, with the
  note.

### Why this matters for trades

A one-source value is not wrong, but it is less trustworthy than one confirmed
by several sources:

- **No cross-check.** With three or four sources, a value is robust to any one
  of them being off. A one-source value has no check.
- **The source might be an outlier.** The one source that prices the player
  might be high or low for reasons specific to its method.
- **He is usually at the edge of relevance.** A player only one projection
  covers is almost always outside the rosterable count.

When a trade involves a player with a one-source value, treat that number as
directional (he is worth roughly this much) rather than precise.

## When no source prices a player

When none of a version's sources has a value, that version is missing for the
player: "No source prices this player", or "No source available this week" when
every source of that version is out. The player still has a row, but no value
in that version. DDF Value never falls back to the projections when the charts
are missing. This week it happens to no player in DDF Value and to 2 players in
DDF Value (projections).

## How the pieces fit together

Take a rosterable running back that two charts list, that a third chart does
not list but estimates, and that sits past a fourth chart's depth:

- DDF Value averages four numbers: the two listed values, the estimate and the
  0. The zero is real information about how that chart's part of the market
  sees him.
- DDF Value (projections) averages the projections that project him. If one
  projection skips him, it averages the other two, with no penalty for the
  source that had no opinion.

The two rules point the same way: a source that has looked at a position and
passed on a player is counted, and a source that has no view is not.

---

## Sources

| Claim | Where it comes from |
|---|---|
| What each chart and projection shows for an unlisted player | The value methodology, section on rows, DDF Value and Indexed values |
| DDF Value is the charts, DDF Value (projections) the alternate | The value methodology, section on DDF Value (decision of October 25, 2026) |
| Fill-in values, the cap and the rosterable count | The value methodology, section on filling in rosterable players |
| One-source note and "No source prices this player" | The value methodology, section on DDF Value |
| Counts and the Kincaid, Johnson, Coleman and Fields examples | This week's data run through the reference value engine (readout of October 29, 2026) |
