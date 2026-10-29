# Trade confidence

Research post 6.

---

## Abstract

When the tool shows a player's DDF Value, or reads a trade, how much should you
trust it? Confidence rests on three things the tool shows: how many sources
stand behind each value, how much the trade charts agree with each other, and
whether projected production backs the value. A trade where every value has
all its sources behind it, the charts agree on the market, and the projections
point the same way is well supported. A trade where any of those breaks is
closer than the headline number suggests.

Terms used below. DDF Value is our one number per player: the average of the
four trade charts' (FantasyCalc, USA Today, FantasyPros and CBS) weight-adjusted
values at your league settings (value above waivers, re-weighted to our
position weights). It is not the trade chart average, which Compare uses
separately as the market's view. DDF Value (projections) is the alternate: the
three projection sources (ESPN, CBS rest of season and Razzball), averaged the
same way. A rescaled chart value is a chart's own published value on our
scale, with the publisher's ranking unchanged. Value above waivers is how much
better a player is than the best player you could pick up for free at his
position.

All figures below are measured on Week 8 of the 2026 season, with the charts
and projections as published on October 28, 2026, in a 12-team, full PPR
league. "Rostered players" means the 168 players DDF Value places in a starting
lineup or on a bench in that league.

## 1. How many sources stand behind a value

Each version of DDF Value is an average, so the number of sources in it is the
first measure of how much to trust it:

- **One source:** "Only one source prices this player." The value is that one
  source's value, with no cross-check.
- **No source:** "No source prices this player." There is no value at all.

This week, every one of the 168 rostered players has all four charts behind
his DDF Value. A chart that prices a position gives every player there a value,
an estimate or a 0, so DDF Value only drops to one source when charts are out
for the week (post 5 has the detail). DDF Value (projections) is thinner at the
edges: 202 players have only one projection behind it, 2 of them rostered.

## 2. How much the trade charts agree

DDF Value averages four charts, and the average can hide a disagreement. For
rostered players this week, the gap between the highest and lowest of the four
charts' adjusted values is:

| Position | Rostered players | Middle player's gap | One in ten has a gap of at least |
|---|---|---|---|
| QB | 20 | 5.1 | 10.6 |
| RB | 61 | 4.8 | 13.0 |
| WR | 65 | 4.7 | 11.2 |
| TE | 22 | 4.1 | 7.4 |

A typical rostered player's charts land within about 5 points of each other.
For one in ten running backs they are 13 or more points apart, more than the
whole DDF Value of the last running backs in starting lineups (about 11). The tool does not turn this gap into a
score. Each player's breakdown lists every chart's value, so you can see when
an average stands on a wide split.

## 3. Whether projected production agrees

DDF Value is the market's view, adjusted to your league. DDF Value
(projections) is what the stat projections say the same players are worth. When
the two point the same way on a trade, the value is backed by projected
production; when they split, the trade rests on market opinion alone.

## How Compare puts this into words

Compare reads a trade in three steps, each from a different number.

**Our value.** The DDF Value net (what you receive minus what you give) decides
whether you come out ahead. A net counts as a win or a loss only when it is at
least 1 point and at least 3% of the average side's total; anything smaller is
even.

**The market.** The rescaled trade charts' nets are averaged, with the same
win, even or lose threshold. Compare needs at least three charts that price
every player in the trade; with fewer it says "Not enough compared charts to
read the market". The two answers together give the read: for example, a value
win the market calls even is "Value win at a fair market price", and a value
win the market calls a loss is "DDF Value likes it. The market doesn't."

Then it checks the average against the charts one by one. It counts the charts
on which the other manager wins or breaks even. If that count does not match
what the average implies (two thirds or more of the charts on the other
manager's side for a market the average calls even or a loss, a third or fewer
for one it calls a win), the read says the charts split, gives their range,
and calls acceptance uncertain, instead of trusting the average.

**Production.** One sentence says whether DDF Value (projections) agrees with
DDF Value about the trade.

A player with a one-source value carries the "Only one source prices this
player" note wherever his value shows in the trade.

### A worked example

Trade Trevor Lawrence (QB) for Brock Purdy (QB):

| | You give | You receive | Net |
|---|---|---|---|
| DDF Value | 13.9 | 14.9 | +1.0 |
| DDF Value (projections) | 11.1 | 9.8 | -1.3 |

By the charts, rescaled, the net is -1.0 on USA Today, +1.7 on FantasyCalc,
+3.9 on FantasyPros and -1.2 on CBS.

- **Our value:** +1.0 is just over the 1-point line, so DDF Value calls it a
  win, and only just.
- **The market:** the four charts average +0.9, under the line, so the market
  calls it even. But two of the four charts have the other manager winning, and
  two have you winning. An even market should mean most charts let him accept,
  and two of four is a toss-up, so the read is "Value win, but the trade charts
  split" (suggested action: propose it), with the charts 5.1 points apart
  (-1.2 to +3.9) and acceptance uncertain.
- **Production:** DDF Value (projections) has you losing 1.3, so projected
  production does not back the value.

Every signal says this is a close trade: a value win barely past the smallest
margin that counts, a market split down the middle, and projections on the other
side. The read says so instead of a confident yes.

## What confidence means for trades

| What you see | What it means |
|---|---|
| Every player has all his sources, the charts agree, production agrees | The read is well supported. |
| A one-source value in the trade | That player's number is directional. If the trade is close, it could go either way. |
| The charts split | The average market read hides a disagreement. Expect the other manager's answer to depend on which chart they use. |
| Production disagrees | The value rests on market opinion. A manager who trades on projections will see it differently. |

## Limitations

- **Agreement is not accuracy.** Four charts can agree and all be wrong.
  Agreement measures consensus, not truth.
- **One-source values are not always wrong.** A player one source prices may be
  priced correctly; the others may not have caught up. The note is a signal to
  look closer, not an automatic downgrade.
- **The chart gap is shown, not scored.** The tool lists each chart's value but
  does not turn the spread into a confidence level.
- **No history of confidence.** The tool does not show whether a player's
  sources have grown closer or further apart over recent weeks.

---

## Sources

| Claim | Where it comes from |
|---|---|
| One-source and no-source notes on each value | The value methodology, section on DDF Value |
| DDF Value is the charts, DDF Value (projections) the alternate | The value methodology, section on DDF Value (decision of October 25, 2026) |
| How Compare reads value, market, split and production | The trade comparison rules in the site |
| Source counts, chart gaps and the Lawrence for Purdy example | This week's data run through the reference value engine and the site's trade rules (readout of October 29, 2026) |
