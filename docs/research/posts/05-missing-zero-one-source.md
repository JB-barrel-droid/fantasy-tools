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

A player can show a value of 0 on a source for two different reasons, and the
distinction matters:

### The chart goes deep enough (fully loaded)

A chart is "fully loaded" at a position when its own list extends past the
rostered count -- meaning the chart itself defines the waiver line at that
position, without needing to borrow from other charts.

When a chart is fully loaded at a position and does not list a player there,
that player is below the chart's floor. His value on that chart is **0**. The
chart has implicitly said: this player is not worth rostering.

This zero counts in DDF Value. If three charts give a player a value and one
fully-loaded chart does not list him, DDF Value averages the three values
and the zero -- four inputs, not three. The zero is real information: one
chart thinks the player has no trade value.

### The chart does not go deep enough

When a chart is not fully loaded at a position (it lists fewer players than
the rostered count), an unlisted player gets a dash ("--") with a reason:
the chart does not list players that deep. This is a null, not a zero.

Nulls are left out of the DDF Value average entirely. They do not count as
zero and they do not count as the source skipping the player. The source
simply has no opinion.

### What about estimated players?

When a chart does not list a player who is within the rosterable count, the
tool estimates his value from the other charts that do list him (the fill-in
rule). The estimate is capped at or below the chart's lowest listed value at
that position. The estimated value counts in DDF Value just like a listed
value -- it represents what the chart would plausibly price the player at,
given its own scale and the other charts' opinions.

## The rules in plain terms

| Situation | What shows | Counts in DDF Value? |
|---|---|---|
| Chart lists the player | The chart's value | Yes |
| Chart estimates the player (fill-in) | Estimated value, marked "estimated" | Yes |
| Chart is fully loaded, does not list him | 0 ("Below rosterable depth") | Yes (as 0) |
| Chart is not fully loaded, does not list him | -- ("Chart doesn't list players this deep") | No (null) |
| Projection does not project him | -- ("Source doesn't project this player") | No (null) |
| Source does not price the position at all | -- ("Source doesn't price this position") | No (null) |

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

Consider a player listed by two of four charts, not listed by a third chart
that is fully loaded at his position, and estimated by the fourth chart.

His DDF Value averages four inputs:
- Chart 1's Adjusted value (listed).
- Chart 2's Adjusted value (listed).
- Chart 3's zero (fully loaded, does not list him).
- Chart 4's estimated Adjusted value (fill-in).

Plus any projections that project him.

The zero from chart 3 pulls the average down, which is the intended effect:
a chart that goes deep enough to price players at this depth and does not
list this player is expressing a view that he has no trade value.

---

## Evidence links

| Claim | Source |
|---|---|
| Missing = 0 for fully loaded charts | `docs/methodology.md` "Published Charts On The Rows" |
| Null for insufficiently deep charts | `docs/methodology.md` VP-6.2 |
| One-source low confidence | `docs/methodology.md` VP-6.3 |
| Estimated values count in DDF | `docs/methodology.md` VP-2.4h, VP-6.3 |
| Fill-in capped at lowest listed | `docs/methodology.md` VP-2.4f |
