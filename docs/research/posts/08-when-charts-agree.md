# When do the trade charts agree, and does agreement mean anything?

Every number below was computed on 22 October 2026 by re-running our value
engine on six saved weeks of chart history. DDF Value here is built from the
projections only; an earlier version of DDF Value blended the trade charts with
the projections, and none of the blended figures are used in this post.

Terms used below:

- **DDF Value** is our own value for a player: the average of the projection
  sources' values above waivers (how many points a player adds over the best
  freely available player at his position), on one common point scale.
- **DDF Projections** is the same calculation shown on its own, so you can see
  the projection side of the answer.
- **Rescaled** means a trade chart converted onto that same point scale, so a
  chart's price and our value can be compared directly.

---

## Abstract

The Compare a trade page gives two answers with a confidence level: "Should
you propose or accept? Yes / No / Unclear" and "Will they accept? Likely /
Toss-up / Unlikely", plus a sub-line "N of 4 trade charts agree". We asked
whether those labels hold up, using 72,000 plausible trades drawn from six saved
weeks of chart history and scored with the site's own rules.

Three findings. First, the charts agree with each other on rank far more than
on trades: any two charts rank players at Spearman 0.84 to 0.92, but point the
same way on a balanced trade only 61% to 78% of the time. Second, a "Yes" on
"Should you propose or accept?" is much steadier when the charts back it. A
"Yes, High confidence" trade with none of the four charts agreeing changes its
answer the next week 39.1% of the time; with all four agreeing, 21.7%. On this
evidence "High" is only earned when at least three of the four charts agree.
Third, "Will they accept?" is the better-behaved line: "Likely, High" repeats
itself the next week 83% of the time and "Unlikely, High" 76%, while "Toss-up"
repeats only 30%, which is what a split among the charts should look like.

Acceptance cannot be tested: we hold no record of trades that were proposed or
accepted. What this post measures is stability (does the label survive a week of
new data) and consistency (do the sources that feed it agree), not accuracy
against outcomes.

## The question

The rules behind the labels:

- **Should you propose or accept?** "Yes" when DDF Value and DDF Projections
  both say you win and the DDF Value margin is at least 5% of the value traded;
  "No" when both say you lose by the same margin; otherwise "Unclear". The 5%
  margin is a starting choice, not something derived from data. Confidence is
  "High" when the DDF Projections margin is also 5% or more, "Medium" when
  projections agree but by less, and "Low" for "Unclear"; a DDF Value built from
  one source lowers it one level. Now that DDF Value is built from the
  projections only, the two inputs are the same number, so the answer is a
  single margin test and "Medium" no longer occurs. The chart count is shown as
  a reason ("N of 4 trade charts agree") but does not enter the answer or the
  level.
- **Will they accept?** The share of complete trade charts on which the other
  manager wins or breaks even. "Likely" at two thirds or more, "Unlikely" at one
  third or less, "Toss-up" in between. Confidence is "High" when 75% or more of
  the charts sit on the answer's side, "Medium" at 60%, else "Low"; fewer than
  three charts caps it at Medium; a margin under 5% forces Low.
- **Deal read.** DDF Value against the plain mean of the chart results, each
  called win, even or lose at a threshold of 3% of the average side total (at
  least 1 point). That gives nine cells. One of them is a split: our value says
  yes and the market says no ("DDF Value likes it. The market doesn't."). It is
  a trade where you gain on our numbers while the trade charts, taken together,
  say you lose. It needs three complete charts.
- **Find a trade** lists a package when DDF Value says you win and at least 3 of
  the 4 charts have the other manager even or winning.
- A net under 0.05 shows as 0.0 and counts as even.

None of those thresholds was derived from data. This post asks what they do.

## Data

- **Weeks 2 to 7** of the 2026 season: each week's saved values for the four
  published charts (USA Today, FantasyCalc, FantasyPros, CBS Sports) and the
  projection sources (ESPN; Razzball from week 3; CBS rest of season from week
  4). That is six content weeks and five week-to-week transitions.
- **Replaced snapshots:** other pulls of the same chart in the same week (one
  USA Today pull in week 4, twelve FantasyCalc pulls in week 5, eleven in week
  6, two CBS in week 6). Used as a noise floor.
- **Setting:** the site default, PPR scoring, 12 teams, one quarterback, two
  running backs, two wide receivers, one tight end, one flex and seven bench
  spots. Other settings were not run.
- **Rows:** each week's values run through the engine with every complete saved
  source included. The holds a week carried at the time are not saved with it,
  so the history weeks have all four charts. The live page on 22 October had
  three, because FantasyCalc was held that day, so it read "N of 3".
- **Players:** 361 (week 2, fewer sources) to 736 priced per week, of which 168
  each week are rostered by the engine's own tier (starter or bench, not
  waiver).

### What is not in the data

No trade outcomes. There is no record of trades proposed on the site, nor of
trades accepted in any league. Testing "Will they accept?" against reality would
need, per proposal: the two packages, the league setting, the week, and whether
the other manager accepted, countered or declined. A league's transaction log
can supply accepted trades but not refused ones.

## Method

1. **Reproduce the rules.** Each rule above was ported line for line to the
   Python reference engine, and the port was checked against the real site
   code: 400 trades from week 7 and 200 from the live page (three charts) were
   run through both, and every label (propose answer and level, agree count,
   accept answer and level, deal cell, finder listing) matched with zero
   mismatches. Two deliberately broken ports (a 10% margin, a 0.5 "as shown"
   rule) produced 125 and 75 mismatches out of 400, so the check catches a wrong
   port. Three live trades were also read off the published page and matched.
2. **Draw trades.** Per week, 3,000 each of 1-for-1, 2-for-1, 2-for-2 and
   3-for-2 (12,000 per week, 72,000 in all) from rostered players priced by DDF
   Value, with the two sides within 20% of each other on DDF Value (the net
   divided by the value traded at most 0.20). The draw is seeded, so the set is
   reproducible. Players are drawn without regard to position, so most trades
   mix positions.
3. **Score** every trade in the week it was drawn and again in the next week
   with the same players.
4. **Report** label frequencies, pairwise agreement between charts (Spearman
   rank correlation on players both price, and trade-direction agreement),
   next-week stability by label with bootstrap intervals (trade-level
   resampling, 500 draws).

## Results

### How often each label fires

Pooled over six weeks, 72,000 trades. With DDF Value from projections only, the
propose line is a single margin test: Yes 34.2%, No 40.7%, Unclear 24.2%.

| Will they accept? | Share |
|---|---|
| Likely, High | 38.8% |
| Unlikely, High | 24.2% |
| Toss-up, Low | 17.9% |
| Likely, Low | 12.9% |
| Unlikely, Low | 6.2% |

### Chart-to-chart agreement

Rank agreement is high. In week 7, over players both charts price, Spearman is
0.84 (FantasyPros and CBS Sports) to 0.92 (FantasyCalc and CBS Sports). By
position it is 0.92 to 0.95 for running backs, 0.88 to 0.94 for wide
receivers, 0.86 to 0.90 for tight ends, and 0.69 to 0.94 for quarterbacks
(FantasyPros is the outlier at quarterback). By tier the gap is large: 0.82 to
0.95 among starters, 0.47 to 0.68 among bench players.

Trade agreement is much lower, because a balanced trade sits where small
differences flip the sign (trades where both series point a way):

| Pair | Same direction | Among starters only | Among bench only |
|---|---|---|---|
| USA Today and CBS Sports | 77.5% | 80.4% | 74.2% |
| FantasyCalc and CBS Sports | 75.1% | 79.9% | 63.0% |
| USA Today and FantasyCalc | 68.9% | 72.6% | 63.7% |
| USA Today and FantasyPros | 67.9% | 69.9% | 63.4% |
| FantasyPros and CBS Sports | 64.6% | 67.6% | 62.2% |
| FantasyCalc and FantasyPros | 60.9% | 65.3% | 57.0% |

Package size barely matters (1-for-1 to 3-for-2 move each pair by one to four
points, usually upward with more players). Position matters at the edges:
same-position running back trades agree most (70% to 77%), quarterback-only and
tight-end-only trades least (51% to 74%) and on small counts (195 to 557
trades).

What this means for you: two charts that rank your players almost the same way
can still disagree about whether a specific trade is fair. When a trade is
close, check more than one chart.

A noise floor: two pulls of FantasyCalc in the same week point different ways on
13% to 17% of trades and change the propose answer on 4% to 6%. The other
charts' repeat pulls differ on 0% to 2%. FantasyCalc is a continuous crowd
value, so part of its disagreement with the others is its own hour-to-hour
movement.

### Is "High confidence" with few charts agreeing justified?

The level is set by the DDF Projections margin, so it ignores the chart count.
The next week shows what that costs. Here "answer changes" means the propose
answer is not the same label next week. With DDF Value from projections only,
"Yes, High" changes 31.4% of the time overall: 39.1% with no chart agreeing and
21.7% with all four. It reverses to "No" 14.8% of the time, because the single
projections margin is the noisiest series we measured (its sign flips from week
to week 18% to 30% of the time).

For comparison, on the same trades a chart's direction flips week to week 9% to
24% of the time (USA Today 15% to 22%, FantasyCalc 13% to 24%, FantasyPros 9% to
19%, CBS Sports 18% to 21%). A "Yes, High" backed by none of the charts is no
steadier than the noisiest single source; the chart count is the input that
separates a verdict likely to survive from one that is not.

What this means for you: treat a "Yes, High" as firm when at least three of the
four charts agree with it. When none do, it is a split between our value and
the market, not a settled answer.

### The split: DDF Value says yes, the market says no

The "DDF Value likes it. The market doesn't." cell is exactly the trade with no chart on your side:
our value says you win and the market says you lose. It is the least stable kind
of "Yes", for the reason above. It is also the trade where our value and the
market most disagree, which is where the opportunity is if our value is right
and the cost if it is not. The label describes the disagreement; it is not a
promise that the other manager will accept.

### Will they accept?

The chart-based line is steadier than the value-based line (same answer next
week): "Likely, High" 82.5% (95% interval 82.0 to 83.0), "Unlikely, High" 76.0%,
"Likely, Low" 71.3%, "Unlikely, Low" 60.8%, "Toss-up" 30.2%. "Toss-up" is nearly
a coin flip about what it will say next week, and it is 18% of trades. That is
the right behaviour for the label: the charts are split, so next week's charts
will probably say something else. With only three charts on the page (as on 22
October), the 2-of-3 and 1-of-3 shares land exactly on the two-thirds and
one-third cuts, so every non-unanimous trade is "Likely" or "Unlikely" at
"Medium" and "Toss-up" cannot occur.

## Limits

- Six weeks, five transitions, one season, one league setting. Week-to-week
  rates vary by up to 12 points between transitions, so the pooled figures are
  a range, not a constant.
- Stability is not accuracy. A label that repeats next week can be wrong twice.
  Without outcomes we cannot say whether "Yes" trades were good trades or
  whether "Likely" trades were accepted.
- Trades are drawn at random within a 20% band on DDF Value. Real proposals are
  not random: they are built to look fair to the other side, which puts them
  nearer the margin, where every label is less stable than shown here.
- History weeks include all four charts; the holds that applied at the time are
  not saved, so the live page some weeks has fewer charts than this study.
- Bootstrap intervals resample trades, which share players; they understate the
  true uncertainty.
- Two pulls of FantasyCalc in the same week differ enough to move 4% to 6% of
  propose answers; which pull counts as "the week" is a convention.

## What this means for a manager

1. A "Yes" is firmer when more of the four charts agree. Read the "N of 4 trade
   charts agree" line before you read the confidence level.
2. "Will they accept?" is the most stable line on the page. "Toss-up" means the
   charts are split, and a different answer next week is likely.
3. A "DDF Value likes it. The market doesn't." trade is a disagreement between
   our numbers and the market's. It can be a real edge, but it is the least
   settled kind of "Yes".

Acceptance itself stays untested: we do not record proposals or their outcomes.

---

## Sources

| Claim | Where it comes from |
|---|---|
| Verdict rules | The trade comparison and trade finder rules on the site |
| The port equals the page | 600 trades run through both implementations, 0 mismatches; three live trades read off the page on 22 October 2026 |
| Label frequencies, chart agreement, stability, noise floor | Our analysis of weeks 2 to 7 of saved chart history, run 22 October 2026 on the reference value engine |
