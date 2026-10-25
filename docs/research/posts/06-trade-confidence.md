# Trade confidence

---

## Abstract

When the tool shows a player's DDF Value, how much should you trust the
number? DDF Value is our single number for a player: the average of the
projection sources' values above waivers (how many points a player adds over
the best freely available player at his position), put on one common scale.
Trade confidence combines two signals: how much the sources agree, and how
much data stands behind the value. A value where the sources land close
together and each one lists the player is high confidence. A value from a
single source, or one where the sources disagree sharply, is low confidence.

This matters most when you are evaluating a trade. A fair trade where both
players have high-confidence values is a well-supported deal. A fair trade
where one side has a low-confidence value could go either way.

## Two components of confidence

### 1. Source agreement

DDF Value is the average of the projection sources' values (ESPN, CBS rest of
season and Razzball). The spread of those sources is a direct measure of how
much they agree about a player's value.

When the sources cluster tightly, the value is well-established. When they
spread widely, at least one source sees the player differently, and the
DDF Value is an average that may not represent any single source's view.

The spread is visible in the math inspector and the DDF decomposition, which
list each source's value for the player. The compare-trade headline does not
turn the spread into a separate score; it reads confidence from the margin
between the two sides and from how many sources stand behind the numbers, as
described below.

### 2. Data quality (source count)

A DDF Value built from seven sources is more robust than one built from
three, which is more robust than one built from one. The tool already flags
the extreme case:

- **One source:** "Only one source prices this player." The DDF Value is
  that source's Adjusted value (its value above waivers, put on the common
  scale), flagged as low confidence. There is no cross-validation.
- **Zero sources:** "No source prices this player." No DDF Value at all.

The one-source flag appears on the site next to the DDF Value.

Players who trigger the one-source flag are typically at the edge of the
roster: deep bench players listed by one chart, or players projected by
one source but not the others. Their DDF Value is directional, not precise.

## What confidence means for trades

When you compare two sides of a trade, the confidence of each player's
value changes how much you should trust the comparison:

| Side A confidence | Side B confidence | What it means |
|---|---|---|
| High | High | Both values are well-supported. The comparison is reliable. |
| High | Low | Side B's value is uncertain. The trade might be fair, or side B might be worth more or less. |
| Low | Low | Both values are uncertain. The comparison is directional at best. |

The compare-trade headline puts this into words. It answers two questions,
"Should you propose or accept?" (Yes, No or Unclear) and "Will they accept?"
(Likely, Toss-up or Unlikely), and attaches a confidence level to each. A
DDF Value built from one source lowers the confidence of the first answer by
one level. On the second answer, a margin under 5% of the value traded
forces Low confidence, and fewer than three complete trade charts caps it at
Medium. A close trade where one side is low-confidence therefore reads as
uncertain rather than as a clear verdict.

## Where confidence shows up

- **Player row:** the low-confidence flag and its note.
- **DDF decomposition (math inspector):** the per-source Adjusted values,
  the count of sources, and which sources are null versus zero.
- **Compare trade:** the headline shows a confidence level beside each
  answer.

## Limitations

- **Agreement is not accuracy.** Seven sources can agree and all be wrong.
  Agreement measures consensus, not truth.
- **One-source values are not always wrong.** A player listed by one chart
  at a high value may be correctly priced; the other charts simply have not
  updated. The flag is a signal to investigate, not an automatic downgrade.
- **No historical confidence tracking.** The tool does not show whether a
  player's confidence has improved or worsened over recent weeks.

---

## Sources

| Claim | Where it comes from |
|---|---|
| A single source sets the flag, and its Adjusted value becomes the DDF Value | The value methodology, section on DDF Value |
| The low-confidence flag and note shown on each row | The value methodology, section on the page contract |
| Confidence levels on the compare-trade headline | The trade comparison rules in the site |
