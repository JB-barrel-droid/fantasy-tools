# When do the trade charts agree, and does agreement mean anything?

Research post 8 (JEG-883). Draft for Jeremy's review.
Copy rules: for trades others will accept; no named players; no title abbreviations.

Every number below comes from one script, `tools/research/chart_agreement.py`,
run 2026-10-22 on the Python reference engine (`pipelines/value_reference.py`,
value-reference-002/2) at git `cc576e71`, the commit the live site was deployed
from that day. Outputs: `docs/research/data/post8/` (`summary.md` has every
table; the CSV files have the full breakdowns). DDF Value here is the live
blend of charts and projections: PR #814 (DDF Value from projections only)
was open, not merged, when this ran. A "projections only" column is shown
wherever that decision changes the answer.

---

## Abstract

The Compare a trade page gives two answers with a confidence level: "Should
you propose or accept? Yes / No / Unclear" and "Will they accept? Likely /
Toss-up / Unlikely", plus a sub-line "N of 4 trade charts agree". We asked
whether those labels are calibrated, using 72,000 plausible trades drawn from
six saved weeks of chart history and scored with the site's own rules.

Three findings. First, the charts agree with each other on rank far more than
on trades: any two charts rank players at Spearman 0.84 to 0.92, but point the
same way on a balanced trade only 61% to 78% of the time, and only 36% of
trades have all four charts on one side. Second, "High confidence" is earned
by the margin on DDF Projections alone, so it ignores the chart count the
sub-line shows: a "Yes, High confidence" trade with one chart agreeing changes
its answer the next week 36% of the time (95% interval 34% to 38%) and sees
DDF Value flip sign 22% of the time, against 19% and 7% when all four charts
agree. Third, "Will they accept?" is the better-behaved line: "Likely, High"
repeats itself the next week 83% of the time and "Unlikely, High" 76%, while
"Toss-up" repeats only 30%.

Acceptance cannot be tested: the repository holds no record of trades that
were proposed or accepted. What the page calls calibration here is stability
(does the label survive a week of new data) and consistency (do the sources
that feed it agree), not accuracy against outcomes.

## The question

The verdict rules are written in `app/v2/trade.js` and `app/v2/finder.js`:

- **Should you propose or accept?** (`trade.js` lines 153 to 221, JEG-841):
  "Yes" when DDF Value and DDF Projections both say you win and the DDF
  Value margin is at least 5% of the value traded; "No" when both say you
  lose by the same margin; otherwise "Unclear". Confidence is "High" when the
  DDF Projections margin is also 5% or more, "Medium" when projections agree
  but by less, "Low" for "Unclear"; a one-source DDF Value lowers it one
  level. The chart count is shown as a reason ("N of 4 trade charts agree",
  line 219) but does not enter the answer or the level.
- **Will they accept?** (lines 222 to 238, JEG-505): the share of complete
  trade charts on which the other manager wins or breaks even (your net at
  or below zero as shown, line 228). "Likely" at two thirds or more,
  "Unlikely" at one third or less, "Toss-up" between. Confidence "High" when
  75% or more of the charts sit on the answer's side, "Medium" at 60%,
  else "Low"; fewer than three charts caps it at Medium; a margin under 5%
  forces Low.
- **Deal read** (lines 267 to 345, JEG-487 and JEG-832): DDF Value against
  the plain mean of the chart nets, each called win / even / lose at a
  threshold of max(1, 3% of the average side total). Nine cells, from
  "Arbitrage: send it" (value win, market lose) to "Trap" (market win, value
  lose). Needs three complete charts.
- **Find a trade** (`finder.js` lines 15 and 109): list a package when DDF
  Value says you win and at least 3 of the 4 charts have the rival even or
  winning.
- "Points neither way": a net under 0.05 shows as 0.0 and counts as even
  (`trade.js` line 91, `finder.js` line 30).

Nothing in those rules was derived from data. This post asks what they do.

## Data

- **Weeks 2 to 7** of the 2026 season from `data/history/week-N.json`: each
  week's saved natives for the four published charts (USA Today, FantasyCalc,
  FantasyPros, CBS Sports) and the projection sources (ESPN; Razzball from
  week 3; CBS rest of season from week 4). Six content weeks, five
  week-to-week transitions.
- **Superseded snapshots** (`data/history/superseded/`): other pulls of the
  same chart in the same week (one USA Today pull in week 4, twelve FantasyCalc
  pulls in week 5, eleven in week 6, two CBS in week 6). Used as a noise floor.
- **Setting**: the engine default, PPR, 12 teams, QB1 RB2 WR2 TE1 FLEX1
  BENCH7 (`curve-widget.js` lines 294 to 295). Other settings were not run.
- **Rows**: each week's natives through `run_pipeline` with every complete
  saved source included. The holds a week carried at the time are not saved
  with it, so history weeks have all four charts. The live week 7 page has
  three: FantasyCalc is held (`fidelity: publisher_vs_stored`), which is why
  the page reads "N of 3" this week.
- **Players**: 361 (week 2, fewer sources) to 736 priced per week, of which
  168 each week are rostered by the engine's own tier (starter or bench, not
  waiver).

### What is not in the data

No trade outcomes. There is no table of trades proposed on the site, nor of
trades accepted in any league. To test "Will they accept?" against reality
would need, per proposal: the two packages, the league setting, the week, and
whether the other manager accepted, countered or declined. A Sleeper or ESPN
league's transaction log can supply accepted trades but not refused ones;
refusals need the site to record proposals.

## Method

1. **Port the rules.** Each function in `trade.js` and the finder's acceptance
   rule were ported line for line to Python (the script names the lines).
   The port was proved against the real JavaScript: `node` loads `trade.js`
   and `finder.js`, runs 400 trades from week 7 and 200 from the live week
   (three charts), and every label (propose answer and level, agree count,
   accept answer and level, deal cell, finder listing) matched with zero
   mismatches (`port_check.json`). Two deliberately broken ports (a 10%
   margin, a 0.5 "as shown" rule) produced 125 and 75 mismatches out of 400,
   so the check catches a wrong port. Three live trades were also read off
   the published page and matched the port.
2. **Draw trades.** Per week, 3,000 each of 1-for-1, 2-for-1, 2-for-2 and
   3-for-2 (12,000 per week, 72,000 in all) from rostered players priced by
   DDF Value, with the two sides within 20% of each other on DDF Value
   (|net| / value traded at most 0.20). Seeded, so the set is reproducible.
   Players are drawn without regard to position, so most trades mix
   positions; same-position subsets are reported where the count allows.
3. **Score** every trade in the week it was drawn and again in the next week
   with the same players, under two readings of DDF Value: the live blend and
   projections only (PR #814).
4. **Report** label frequencies, pairwise agreement between charts (Spearman
   rank correlation on players both price, and trade-direction agreement),
   next-week stability by label with bootstrap intervals (trade-level
   resampling, 500 draws), and threshold sweeps.

## Results

### How often each label fires

Pooled over six weeks, 72,000 trades (`labels.csv`):

| Should you propose or accept? | Share |
|---|---|
| Unclear, Low | 48.6% |
| No, High | 25.5% |
| Yes, High | 21.4% |
| Yes, Medium | 2.3% |
| No, Medium | 2.1% |

Why "Unclear": the margin is under 5% (25.3% of all trades), DDF Projections
disagree with DDF Value (20.0%), DDF Value calls it even (2.7%), projections
cannot price a player (0.6%). Of the trades that get a Yes or No, 91% get
"High".

| Will they accept? | Share |
|---|---|
| Likely, High | 38.8% |
| Unlikely, High | 24.2% |
| Toss-up, Low | 17.9% |
| Likely, Low | 12.9% |
| Unlikely, Low | 6.2% |

"N of 4 trade charts agree" (with DDF Value's direction): 4 of 4 on 36.4% of
trades, 3 of 4 on 26.8%, 2 of 4 on 18.1%, 1 of 4 on 12.7%, 0 of 4 on 6.0%.
The finder's rule (DDF win and three or more charts have the rival even or
winning) passes 11.5% of these balanced trades. The deal read lands on
"Arbitrage: send it" (value win, market lose) for 7.3% and "Trap" for 2.6%.

If DDF Value were projections only (PR #814), the propose line becomes a
projections-only margin test: Yes 34.2%, No 40.7%, Unclear 24.2%, and the
"Medium" level disappears because the two inputs are the same number.

### Chart-to-chart agreement

Rank agreement is high. In week 7 (`pairwise_rank_corr.csv`), over players
both charts price, Spearman is 0.84 (FantasyPros and CBS Sports) to 0.92
(FantasyCalc and CBS Sports). By position it is 0.92 to 0.95 for running
backs, 0.88 to 0.94 for wide receivers, 0.86 to 0.90 for tight ends, and
0.69 to 0.94 for quarterbacks (FantasyPros is the outlier at quarterback).
By tier the gap is large: 0.82 to 0.95 among starters, 0.47 to 0.68 among
bench players.

Trade agreement is much lower, because a balanced trade sits where small
differences flip the sign (`pairwise_direction.csv`, trades where both
series point a way):

| Pair | Same direction | Among starters only | Among bench only |
|---|---|---|---|
| USA Today and CBS Sports | 77.5% | 80.4% | 74.2% |
| FantasyCalc and CBS Sports | 75.1% | 79.9% | 63.0% |
| USA Today and FantasyCalc | 68.9% | 72.6% | 63.7% |
| USA Today and FantasyPros | 67.9% | 69.9% | 63.4% |
| FantasyPros and CBS Sports | 64.6% | 67.6% | 62.2% |
| FantasyCalc and FantasyPros | 60.9% | 65.3% | 57.0% |

Against DDF Value: FantasyCalc 76.6%, CBS Sports 74.8%, USA Today 69.2%,
FantasyPros 65.0%. Package size barely matters (1-for-1 to 3-for-2 move each
pair by one to four points, usually upward with more players). Position
matters at the edges: same-position running back trades agree most (70% to
77%), quarterback-only and tight-end-only trades least (51% to 74%) and on
small counts (195 to 557 trades).

A noise floor: two pulls of FantasyCalc in the same week point different
ways on 13% to 17% of trades and change the propose answer on 4% to 6%
(`superseded_snapshots.csv`). The other charts' repeat pulls differ on 0%
to 2%. FantasyCalc is a continuous crowd value, so part of its disagreement
with the others is its own hour-to-hour movement.

### Is "High confidence" with one chart agreeing justified?

The level is set by the DDF Projections margin, so it is blind to the chart
count. The next week shows what that costs (`high_by_agree.csv`; "answer
changes" is the propose answer not being the same label next week, "DDF
sign flips" is DDF Value changing from win to lose or the reverse, or to
even):

| Yes, High: charts agreeing now | Trades | Answer changes next week (95% interval) | DDF sign flips | Becomes "No" |
|---|---|---|---|---|
| 0 of 4 | 636 | 36.0% (32.5 to 39.3) | 24.2% | 11.0% |
| 1 of 4 | 1,703 | 36.2% (34.1 to 38.4) | 21.5% | 9.8% |
| 2 of 4 | 2,566 | 33.5% (31.7 to 35.2) | 15.9% | 7.4% |
| 3 of 4 | 3,620 | 26.6% (25.2 to 27.9) | 11.4% | 5.0% |
| 4 of 4 | 4,186 | 18.7% (17.6 to 19.9) | 6.7% | 2.9% |
| any | 12,711 | 27.2% (26.4 to 27.9) | 12.7% | 5.7% |

"No, High" behaves the same way: 34.8% change with one chart agreeing, 20.6%
with four. "Yes, Medium" (projections agree but by under 5%) changes 45.8%
of the time, "Unclear" 49.4%.

Compare that to the charts' own stability (`stability.csv`): on the same
trades, a chart's direction flips week to week 9% to 24% of the time
(USA Today 15% to 22%, FantasyCalc 13% to 24%, FantasyPros 9% to 19%,
CBS Sports 18% to 21%), DDF Value 22% to 29%, DDF Projections 18% to 30%.
A "Yes, High" with one chart agreeing (21.5% sign flip) is about as stable
as a single chart; with four charts agreeing (6.7%) it is three times
steadier than any one source. The chart count is the best single predictor
of whether the verdict survives, and it is the one input the level ignores.

By tier and package (`high_by_group.csv`): "Yes, High" on all-bench trades
changes 44.9% of the time (DDF sign flips 31.4%) against 23.7% (10.0%) on
all-starter trades. Package size changes little (25% to 30%).

Under projections-only DDF Value the picture is worse at every chart count:
"Yes, High" changes 31.4% overall (39.1% with no chart agreeing, 21.7% with
four) and reverses to "No" 14.8% of the time, because the single projections
margin is the noisiest series in the table (18% to 30% sign flips). The
"Yes / Send it" arbitrage cell (JEG-841) is exactly the trade with no chart
on your side: value win, market lose.

### What thresholds make the labels honest

For trades where DDF Value and DDF Projections both win now (the "Yes"
population), by the margin and the chart count required (`thresholds.csv`):

| DDF margin at least | Charts agreeing at least | Share of all trades | Still a win next week | Still a win by 5%+ | A loss next week |
|---|---|---|---|---|---|
| 5% (today) | 0 (today) | 27.3% | 84.2% | 75.1% | 15.3% |
| 5% | 2 | 21.6% | 87.3% | 77.9% | 12.3% |
| 5% | 3 | 16.1% | 89.3% | 80.5% | 10.2% |
| 10% | 0 | 19.0% | 87.2% | 81.0% | 12.3% |
| 10% | 2 | 15.8% | 89.6% | 83.2% | 10.0% |
| 10% | 3 | 12.5% | 91.2% | 85.1% | 8.4% |
| 15% | 3 | 6.9% | 93.0% | 88.6% | 6.7% |

No cut reaches 95% on one week of drift. Requiring three charts at 5% lifts
"still a win" from 84% to 89% and drops the Yes rate from 27% to 16% of
balanced trades; a 10% margin alone does about as much (87%). Doing both
reaches 91% and labels one trade in eight.

### Will they accept?

The chart-based line is steadier than the value-based line
(`accept_stability.csv`, same answer next week): "Likely, High" 82.5% (95%
interval 82.0 to 83.0), "Unlikely, High" 76.0%, "Likely, Low" 71.3%,
"Unlikely, Low" 60.8%, "Toss-up" 30.2%. "Toss-up" is nearly a coin flip
about what it will say next week, and it is 18% of trades. With only three
charts on the page (this week), the 2-of-3 and 1-of-3 shares land exactly on
the two-thirds and one-third cuts, so every non-unanimous trade is "Likely"
or "Unlikely" at "Medium" and "Toss-up" cannot occur.

## Limits

- Six weeks, five transitions, one season, one league setting. Week-to-week
  rates vary by up to 12 points between transitions (propose answer changes
  32% to 44%), so the pooled figures are a range, not a constant.
- Stability is not accuracy. A label that repeats next week can be wrong
  twice. Without outcomes we cannot say whether "Yes" trades were good trades
  or whether "Likely" trades were accepted.
- Trades are drawn at random within a 20% band on DDF Value. Real proposals
  are not random: they are built to look fair to the other side, which puts
  them nearer the margin, where every label is less stable than shown here.
- History weeks include all four charts; the holds that applied at the time
  are not saved, so the live page some weeks has fewer charts than this
  study (three this week).
- Bootstrap intervals resample trades, which share players; they understate
  the true uncertainty.
- Two pulls of FantasyCalc in the same week differ enough to move 4% to 6% of
  propose answers; which pull is "the week" is a convention
  (`docs/v2-design-notes.md`).

## What changes in the product

Proposed label and threshold changes are on JEG-883 as a multiple-choice
question for Jeremy (never defaults). The evidence points three ways:

1. The confidence level on "Should you propose or accept?" should depend on
   the chart count, which the page already shows: with 0 or 1 of 4 charts
   agreeing the answer is as unstable as a single chart, and "High" is not
   earned.
2. The 5% margin is loose: "Yes, High" at 5% to 10% changes next week more
   often than at 10% and above. A 10% margin, or three charts, each cuts
   the next-week loss rate by about a fifth.
3. "Will they accept?" is the most stable line on the page and can keep its
   thresholds; "Toss-up" should be labelled as what it is (the charts are
   split and next week will likely say something else).

Acceptance itself stays untested until the site records proposals and their
outcomes.

---

## Evidence links

| Claim | Source |
|---|---|
| Verdict rules | `app/v2/trade.js` lines 91, 136 to 240, 267 to 345; `app/v2/finder.js` lines 15, 24, 30, 109 |
| Port equals the page | `docs/research/data/post8/port_check.json` (600 trades, 0 mismatches); three live trades read on 2026-10-22 |
| Label frequencies | `docs/research/data/post8/labels.csv` |
| Rank correlation | `docs/research/data/post8/pairwise_rank_corr.csv` |
| Direction agreement | `docs/research/data/post8/pairwise_direction.csv` |
| High-confidence flips | `docs/research/data/post8/high_by_agree.csv`, `high_by_group.csv` |
| Week-to-week stability | `docs/research/data/post8/stability.csv` |
| Thresholds | `docs/research/data/post8/thresholds.csv` |
| Accept stability | `docs/research/data/post8/accept_stability.csv` |
| Same-week noise floor | `docs/research/data/post8/superseded_snapshots.csv` |
| Engine, data and run | `docs/research/data/post8/run_meta.json` |
