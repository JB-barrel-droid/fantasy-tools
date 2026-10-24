# Missing is not zero, and the one-source rule

Research post 5.

---

## Abstract

When a source does not list a player, what value should the tool show? When
only one source prices a player, how much should you trust the number? These
two rules, how a missing value is shown and the one-source note, determine what
the tool shows for players at the edges of the roster, and they affect every
trade evaluation that involves a deep bench player or a player one source
disagrees about.

Terms used below. DDF Value is our one number per player: the equal-weight
average of the values from the three projection sources (ESPN, CBS rest of
season and Razzball), each turned into a value at your league settings. A
trade chart (CBS, FantasyCalc, FantasyPros, USA Today) is shown next to DDF
Value for comparison but is not part of the average. The rosterable count is
the number of players at a position that the league's teams can actually hold,
worked out from league size, roster slots and bench spots. A fill-in value is
an estimate for a rosterable player a chart does not list.

## When a player shows 0

A player can show a value of 0 on a chart for a specific reason, and the
distinction from a dash matters.

### Below rosterable depth

The tool works out the rosterable count for each position. A chart that
prices a position but neither lists nor estimates a player below that count
shows him at **0**, with the note "Below rosterable depth." The chart prices
players at his position, but he is past the point where any team in the league
would roster him.

This zero is shown on the chart's own line so you can see that chart's view.
It does not count in DDF Value, because DDF Value uses the projection sources
only. The trade charts are there for comparison.

### Fill-in values for rosterable players

When a chart prices a position but does not list a player who *is* within
the rosterable count, the tool estimates his value from the other charts
that do list him. The fill-in value is capped at or below the chart's lowest
listed value at that position, so the publisher's listed ranking order is
never disrupted. It is marked "estimated" and shown on that chart's line. Like
the zero above, it is for comparison and is not part of DDF Value.

### When a source gives a dash

A dash ("--") means the source has no opinion. This is a missing value, not a
zero, and it is left out of the DDF Value average entirely. It happens when:

- A **chart does not price the position at all** (it lists nobody there).
- A **projection does not project the player** (the source has no
  projection for him).
- **No source is available** this week.

## The rules in plain terms

| Situation | What shows | Counts in DDF Value? |
|---|---|---|
| Projection projects the player | The projection's value | Yes |
| Projection does not project him | -- ("Source doesn't project this player") | No (left out) |
| Chart lists the player | The chart's value | No (shown for comparison) |
| Chart gives a fill-in value | Estimated value, marked "estimated" | No (shown for comparison) |
| Player below rosterable depth, chart prices position | 0 ("Below rosterable depth") | No (shown for comparison) |
| Chart does not price the position | -- ("Source doesn't price this position") | No (left out) |
| No source available this week | -- ("No source available this week") | No (left out) |

## When only one source prices a player

When exactly one included projection has a value for a player (the others are
missing), DDF Value equals that one projection's value. The tool flags it with
a low-confidence note.

On the site, this appears next to the DDF Value as: "Only one source prices
this player."

### Why this matters for trades

A one-source DDF Value is not wrong, but it is less trustworthy than a value
confirmed by several sources. The reasons:

- **No cross-validation.** With all three projections, a value is robust to
  any single source being wrong. A one-source value has no check.
- **The source might be an outlier.** The one source that prices the player
  might be unusually high or low for reasons specific to its method.
- **He is at the edge of relevance.** A player only one projection covers is
  usually outside the rosterable count for most leagues.

When evaluating a trade involving a player with a one-source value, treat the
number as directional (he is worth roughly this much) rather than precise.
If both sides of a trade include one-source players, the uncertainty is
larger.

## When no source prices a player

When no included source has a value for a player, DDF Value is missing: "No
source prices this player." The player appears on the site (he has a row)
but has no DDF Value, no tier, and no trade-value number. He is below the
floor of every source.

## How the pieces fit together

Consider a player whom ESPN and Razzball project but CBS rest of season does
not. His DDF Value averages two inputs:

- ESPN's value.
- Razzball's value.

CBS rest of season shows a dash and is left out, so the average is of two
values, not three with a zero. The player is not penalized for a source having
no opinion.

On the trade-chart side, suppose one chart lists him, a second chart prices
his position but he is below its rosterable depth (it shows 0), and a third
gives him a fill-in value. All three appear on their own lines for comparison.
The zero tells you that chart's scale puts him outside the rosterable set,
which is real information about how that part of the market views him, but it
does not move his DDF Value.
