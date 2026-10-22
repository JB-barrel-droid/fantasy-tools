# Missing = 0 and the one-source rule

Research post 5 (JEG-545, post 3 of 4). Draft for Jeremy's review.
Copy rules: for trades others will accept; no title abbreviations.

---

## Abstract

When a source does not list a player, what value should the tool show? When
only one source prices a player, how much should you trust the number? These
two rules -- Missing = 0 and the one-source tag -- determine what the tool
shows for players at the edges of the roster, and they affect every trade
evaluation that involves a deep bench player or a player one chart disagrees
about.

> Evidence: `docs/methodology.md` section "Published Charts On The Rows"
> and VP-6.2, VP-6.3.
> Engine: `value-model.js`, `compositeValue`.

## When a player shows 0

A player can show a value of 0 on a chart for a specific reason, and the
distinction from a dash matters.

### Below rosterable depth

The tool determines how many players are rosterable at each position based on
league size, roster slots, and bench spots. A chart that prices a position
but neither lists nor estimates a player below that depth gives him **0**:
"Below rosterable depth." The chart prices players at his position, but he
is past the point where any team in the league would roster him.

This zero counts in DDF Value. If three charts give a player a value and one
chart gives him 0, DDF Value averages the three values and the zero -- four
inputs, not three. The zero is real information: one chart's scale puts this
player outside the rosterable set.

### Fill-in estimates for rosterable players

When a chart prices a position but does not list a player who *is* within
the rosterable count, the tool estimates his value from the other charts
that do list him (the fill-in rule, VP-2.4). The estimate is capped at or
below the chart's lowest listed value at that position, so the publisher's
listed ranking order is never disrupted. The estimated value counts in DDF
Value just like a listed value -- it represents what the chart would
plausibly price the player at, given its own scale and the other charts'
opinions.

### When a source gives a dash

A dash ("--") means the source has no opinion. This is a null, not a zero,
and it is left out of the DDF Value average entirely. It happens when:

- A **chart does not price the position at all** (it lists nobody there).
- A **projection does not project the player** (the source has no
  projection for him).
- **No source is available** this week.

## The rules in plain terms

| Situation | What shows | Counts in DDF Value? |
|---|---|---|
| Chart lists the player | The chart's value | Yes |
| Chart estimates the player (fill-in) | Estimated value, marked "estimated" | Yes |
| Player below rosterable depth, chart prices position | 0 ("Below rosterable depth") | Yes (as 0) |
| Chart does not price the position | -- ("Source doesn't price this position") | No (null) |
| Projection does not project him | -- ("Source doesn't project this player") | No (null) |
| No source available this week | -- ("No source available this week") | No (null) |

## When only one source prices a player

When exactly one included source has a value for a player (all others are
null), DDF Value equals that one source's Adjusted value. The tool flags it
with a low-confidence marker.

On the site, this appears as a note next to the DDF Value: "Only one source
prices this player."

### Why this matters for trades

A one-source DDF Value is not wrong, but it is less trustworthy than a value
confirmed by multiple sources. The reasons:

- **No cross-validation.** With seven sources, a value confirmed by all
  seven is robust to any single source being wrong. A one-source value has
  no check.
- **The source might be an outlier.** The one source that prices the player
  might be unusually high or low for reasons specific to its methodology.
- **The fill-in might not reach him.** A player priced by one source and
  not estimated by the others is outside the rosterable count for most
  charts. He is at the edge of relevance.

When evaluating a trade involving a player with a one-source value, treat the
number as directional (he is worth roughly this much) rather than precise.
If both sides of a trade include one-source players, the uncertainty is
larger.

## When no source prices a player

When no included source has a value for a player, DDF Value is null: "No
source prices this player." The player appears on the site (he has a row)
but has no DDF Value, no tier, and no trade-value number. He is below the
floor of every source.

## How estimated values and zeros interact

Consider a player listed by two of four charts. A third chart prices his
position but he is below its rosterable depth (0). The fourth chart does not
list him but he is within the rosterable count, so the tool estimates his
value from the other charts.

His DDF Value averages four chart inputs:
- Chart 1's Adjusted value (listed).
- Chart 2's Adjusted value (listed).
- Chart 3's zero (below rosterable depth).
- Chart 4's estimated Adjusted value (fill-in).

Plus any projections that project him.

The zero from chart 3 pulls the average down, which is the intended effect:
that chart's scale puts this player outside the rosterable set, which is
real information about how the market views him.

---

## Evidence links

| Claim | Source |
|---|---|
| Below rosterable depth = 0 | `docs/methodology.md` VP-6.2 |
| Null when source does not price position | `docs/methodology.md` VP-6.2 |
| One-source low confidence | `docs/methodology.md` VP-6.3 |
| Estimated values count in DDF | `docs/methodology.md` VP-2.4h, VP-6.3 |
| Fill-in capped at lowest listed | `docs/methodology.md` VP-2.4f |
