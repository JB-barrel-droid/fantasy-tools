# Trade confidence

Research post 6 (JEG-545, post 4 of 4). Draft for Jeremy's review.
Copy rules: for trades others will accept; no title abbreviations.

**Partially gated on JEG-505** (compare trade headline). The confidence
signal described here will be finalized after JEG-505 ships. The framework
and the one-source rule are ready; the agreement threshold and the
"should you propose / will they accept" framing need JEG-505.

---

## Abstract

When the tool shows a player's DDF Value, how much should you trust the
number? Trade confidence combines two signals: how much the sources agree,
and how much data stands behind the value. A value where all seven sources
land close together and each one lists the player is high confidence. A
value from a single source, or one where the charts and projections
disagree sharply, is low confidence.

This matters most when you are evaluating a trade. A fair trade where both
players have high-confidence values is a well-supported deal. A fair trade
where one side has a low-confidence value could go either way.

> Evidence: `docs/methodology.md` VP-6.3, VP-11.
> Gated: JEG-505 (compare trade headline).

## Two components of confidence

### 1. Source agreement

DDF Value is the average of up to seven sources. The spread of those sources
is a direct measure of how much the market and the projections agree about
a player's value.

When the sources cluster tightly, the value is well-established. When they
spread widely, at least one source sees the player differently -- and the
DDF Value is an average that may not represent any single source's view.

> **Pending JEG-505:** the threshold for "Low" confidence based on
> agreement (e.g., below a 5% margin of the DDF Value) will be set when
> the compare-trade headline ships. Until then, the source spread is
> available in the math inspector and the DDF decomposition.

### 2. Data quality (source count)

A DDF Value built from seven sources is more robust than one built from
three, which is more robust than one built from one. The tool already flags
the extreme case:

- **One source:** "Only one source prices this player." The DDF Value is
  that source's Adjusted value, flagged `lowConfidence`. There is no
  cross-validation.
- **Zero sources:** "No source prices this player." No DDF Value at all.

The one-source flag is live today. It appears on the site next to the DDF
Value and in the row's `ddfLowConfidence` field.

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

> **Pending JEG-505:** the compare-trade headline ("Should you propose this?
> Will they accept?") will use confidence alongside the value comparison.
> A trade within a 5% margin where one side is low-confidence will say so
> explicitly.

## Where confidence shows up

- **Player row:** the `ddfLowConfidence` flag and `ddfConfidenceNote` text.
- **DDF decomposition (math inspector):** the per-source Adjusted values,
  the count of sources, and which sources are null versus zero.
- **Compare trade (pending JEG-505):** the headline will incorporate
  confidence into the deal recommendation.

## Limitations

- **Agreement is not accuracy.** Seven sources can agree and all be wrong.
  Agreement measures consensus, not truth.
- **One-source values are not always wrong.** A player listed by one chart
  at a high value may be correctly priced; the other charts simply have not
  updated. The flag is a signal to investigate, not an automatic downgrade.
- **No historical confidence tracking.** The tool does not yet show whether
  a player's confidence has improved or worsened over recent weeks. That
  requires storing confidence per week alongside the DDF Value history.

---

## Evidence links

| Claim | Source |
|---|---|
| One-source lowConfidence flag | `docs/methodology.md` VP-6.3 |
| DDF Value from one source = that source's Adjusted | `docs/methodology.md` VP-6.3 |
| ddfLowConfidence, ddfConfidenceNote fields | `docs/methodology.md` VP-11 |
| Compare trade headline | JEG-505 (pending) |
| Agreement threshold | JEG-505 (pending) |
