# How we split value across positions

Research post 9 (JEG-925). Jeremy, 2026-10-26: refresh to today's rules and
publish without his review.

All numbers recomputed 2026-10-29 on main 7f212319, on the week 8 fixture
built 2026-10-29 21:11 UTC, with all seven sources included. They describe
the weights as the tool computes them today; nothing in this post changes a
weight, a default or a value.
Copy rules: for trades others will accept; no title abbreviations.

---

## Abstract

When the tool says a running back is worth 120 and a quarterback is worth 80,
the gap is not arbitrary. Behind the scenes, the Trade Value Chart computes
**position weights**: the share of the league's total trade value that belongs
to each position. Those weights decide how much of the fixed value pie goes to
quarterbacks, running backs, wide receivers and tight ends, and within each
position, how much goes to starters versus bench players.

Position weights are the crux of the tool. Every Adjusted value depends on
them, and DDF Value and DDF Value (projections) are both averages of Adjusted
values, so every fit label on a trade depends on them too. This post explains
exactly where they come from.

> Evidence: `docs/methodology.md` VP-2 through VP-5.
> Engine: `app/trade-value-chart/assets/value-model.js`, `runValuePipeline` (VP-3, VP-4).
> Reference: `pipelines/value_reference.py`, functions `_mixes` and `ddf_weights`.

## What a position weight is

A position weight is a number between 0 and 1 that says what fraction of the
league's total value pie belongs to a group. There are eight groups: four
positions (QB, RB, WR, TE) times two roles (starter, bench). The eight
weights sum to 1.

At PPR scoring with 12 teams and the default roster (QB1 RB2 WR2 TE1 FLEX1,
7 bench), the current weights are:

| Position | Starter | Bench | Total |
|---|---|---|---|
| QB | 6.9% | 0.3% | 7.2% |
| RB | 40.1% | 2.9% | 43.0% |
| WR | 38.6% | 3.0% | 41.7% |
| TE | 7.7% | 0.4% | 8.1% |
| **Total** | **93.3%** | **6.7%** | **100.0%** |

(Rounded to one decimal, so a row can differ from its parts by 0.1.)

The total pie at this setting is 2,352 points (28 per starting slot times 12
teams times 7 starting slots per team, the flex slot included). Each group's
budget is its weight times the pie. Running back starters get 943 of the
2,352, wide receiver starters 909, quarterback starters 163, and tight end
bench players 10.

What this means for a trade: at this setting running backs and wide receivers
split about 85% of all trade value almost evenly, and the whole quarterback
position gets less of the pie than tight ends do. A quarterback is not cheap
because he is bad; he is cheap because one starter per team leaves a small
slice to divide.

Those budgets control the Adjusted values. A source whose running backs carry
a lot of surplus sees those values scaled up or down until the running back
budget matches what the weights say. The weights are the bridge between each
source's own opinion and the common scale.

> Numbers: `pipelines/value_reference.py`, `Setting(Inputs.load(), scoring='ppr', teams=12).result()['ddf_weights']` on the week 8 fixture (`data/fixtures/current/`, built 2026-10-29). Verified: the eight groups sum to 1.000000.

## The inputs

The weights come from three things:

1. **The included sources' value above waivers at each position.** This is
   the total surplus that every player at a position produces above what the
   waiver wire offers, computed separately for starters and bench players.
   Each of the included sources (seven this week: four trade charts, three
   projections) produces its own group totals. This is VP-2 and VP-3 in the
   spec.

2. **The league allocation.** How many starters and bench players each
   position gets is decided by the user's roster settings, with flex and
   superflex slots assigned by projected points (not by the source's own
   values). Bench seats are then filled league-wide in one pass: every seat
   goes to the best remaining player at any position, scored by his projected
   points per game times a usage discount. The discount is how often a
   backup at that position is needed: starters per team (flex starters
   included) times the bye rate (one bye in 17 games) plus the position's
   missed-game rate (QB 12%, RB 14%, WR 11%, TE 15%). It shrinks a step each
   time a position's backups pass a tier sized at about two weeks of the
   league's expected missing starters at that position (11 seats for running
   backs at PPR/12, under one per team). So a position whose starters rarely miss gets few backups, and the
   backup count moves with the data rather than a fixed ratio. At PPR/12 that
   gives 8 quarterback, 33 running back, 33 wide receiver and 10 tight end
   bench seats. This is VP-2.2 and `pipelines/lib/roster_convention.py`
   (`vorp_bench_allocate`, JEG-1121).

3. **The bench share from expected starts.** Instead of a fixed 15% bench
   share, the tool computes how much of each position's surplus actually
   reaches a starting lineup, using missed-game rates, bye weeks and
   depth-chart volatility. The bench share is an output of the weight
   computation, not an input. This is the expected-starts system (ES-0 to
   ES-14). The promotion model (credit for a bench player being promoted into
   a starting role) is switched off (JEG-1142), so it plays no part in
   today's weights.

## The derivation, step by step

### Step 1: Each source computes its group totals (VP-2, VP-3)

Every included source goes through the same steps:

1. List each position's players in the source's own order (native values
   descending).
2. Use the league allocation to mark the first S players as starters and the
   next B as bench. The allocation is shared: every source uses the same
   counts, based on projected points, not its own values.
3. Find the waiver line (the value of the first player past rosterable depth)
   and the starter line (the value of the first non-starter) at each
   position.
4. Split each player's value above waivers into a starter slice (the part
   above the starter line) and a bench slice (the part between the waiver
   line and the starter line).
5. Sum the starter slices and the bench slices at each position. This gives
   the source's eight group totals.

For ESPN projections at PPR/12 this week, the group totals (points per game
of surplus over the waiver line, after the expected-starts split) are:

| Group | Total |
|---|---|
| QB starter | 30.8 |
| QB bench | 0.8 |
| RB starter | 222.4 |
| RB bench | 23.2 |
| WR starter | 208.9 |
| WR bench | 21.0 |
| TE starter | 37.0 |
| TE bench | 1.7 |

They add to 545.9 (the rounded rows add to 545.8).

> Numbers: from `res['sources']['espn']['groups']` in the same pipeline run.

### Step 2: Each source gets normalized to mixes (VP-3.2 through VP-3.4)

The group totals are in different units (points per game for projections,
trade value points for charts). To compare them, the tool converts each
source to two unit-free mixes:

- **Starter mix**: the share of starter surplus at each position.
  `starter_mix[QB]` = QB starter total / sum of all starter totals.
- **Bench mix**: the share of bench surplus at each position.
  `bench_mix[QB]` = QB bench total / sum of all bench totals.

ESPN's starter mix this week: QB 6.2%, RB 44.6%, WR 41.9%, TE 7.4%.
ESPN's bench mix: QB 1.8%, RB 49.6%, WR 45.0%, TE 3.6%.

Each source also gets its own 8-group weight set. With expected starts
enabled, each group's weight is simply its group total divided by the
source's grand total (the mixes are combined through the source's own
bench-to-starter ratio, which varies by source).

The per-source starter mixes for all seven included sources this week:

| Source | QB | RB | WR | TE |
|---|---|---|---|---|
| USA Today (chart) | 8.8% | 38.7% | 42.3% | 10.2% |
| FantasyCalc (chart) | 7.9% | 40.6% | 43.1% | 8.4% |
| FantasyPros (chart) | 8.5% | 48.1% | 36.2% | 7.2% |
| CBS (chart) | 7.0% | 41.2% | 44.1% | 7.7% |
| ESPN (projection) | 6.2% | 44.6% | 41.9% | 7.4% |
| CBS rest of season (projection) | 8.2% | 43.2% | 39.6% | 9.0% |
| Razzball (projection) | 5.4% | 44.5% | 42.5% | 7.7% |
| **Mean** | **7.4%** | **43.0%** | **41.4%** | **8.2%** |

The sources agree on the shape and disagree on the split between the two big
positions. Every source gives running backs and wide receivers between 81%
and 87% of starter surplus together, but FantasyPros puts running backs 12
points ahead of wide receivers while USA Today, FantasyCalc and CBS put wide
receivers ahead. Quarterbacks get 5.4% (Razzball) to 8.8% (USA Today). For a trade it
means the running back and wide receiver prices you see are a compromise
between sources that do not agree on which of the two matters more.

> Numbers: from `res['sources'][src]['starter_mix']` for each source.

### Step 3: Average across sources (VP-4)

The DDF weights are an average over all included sources:

- For each position, the starter mix mean is the arithmetic mean of the
  included sources' starter mixes at that position.
- Same for the bench mix mean.

Sources that have no players at a position, or no weights at all, are
excluded from the average at that position. So is a source that has not
published for the current week: on 2026-10-27, while the four trade charts
were still on week 7, the weights came from the three projections alone
(JEG-1175, since fixed). A source that is held but has this week's data stays
in the weight average (JEG-569). This week Razzball is on an amber hold,
because one publisher name does not resolve to a player, so it counts like
any other source; a red hold would also keep it in the weights and only take
it out of the DDF Value blend.

With expected starts, the weights that are actually used come from a second
average: the tool averages each source's 8-group weights directly (seven
sources, each counted once) and renormalizes to 1. This means the bench
share is an output: it is whatever the averaged weights say, not a fixed 15%.
Currently the computed bench share is 6.7% at PPR/12. The mix means below are
reported as diagnostics; the final weights are the 8-group table at the top
of this post.

This week's mix means:

    Starter mix mean:  QB 7.4%  RB 43.0%  WR 41.4%  TE 8.2%
    Bench mix mean:    QB 4.8%  RB 43.1%  WR 45.6%  TE 6.5%
    Bench share:       6.7%

### Step 4: Weights become budgets (VP-5)

The pie for the setting is `28 x teams x starting_slots`. At PPR/12 that is
2,352.

Each group's budget is pie times its weight:

| Group | Weight | Budget |
|---|---|---|
| QB starter | 6.9% | 162.9 |
| QB bench | 0.3% | 6.8 |
| RB starter | 40.1% | 942.6 |
| RB bench | 2.9% | 69.1 |
| WR starter | 38.6% | 908.6 |
| WR bench | 3.0% | 71.6 |
| TE starter | 7.7% | 180.5 |
| TE bench | 0.4% | 10.0 |

Each source's Adjusted values are then scaled so its group totals match these
budgets. A source with relatively more QB value than the average sees its QB
values scaled down; one with less sees them scaled up. The budgets are the
same for every source; that is how sources end up on a common scale.

## A worked example: ESPN at PPR/12

ESPN projects players' points per game. At PPR/12, the allocation gives:

- QB: 12 starters, 8 bench
- RB: 28 starters (24 dedicated + 4 flex), 33 bench
- WR: 32 starters (24 dedicated + 8 flex), 33 bench
- TE: 12 starters, 10 bench

(Those 168 rostered players are 12 teams times 14 roster spots.)

ESPN's total value above waivers across all groups is 545.9 points per game.
Its group totals (from Step 1 above) give it this weight set:

    QB starter: 30.8 / 545.9 = 5.6%
    RB starter: 222.4 / 545.9 = 40.7%
    WR starter: 208.9 / 545.9 = 38.3%
    TE starter: 37.0 / 545.9 = 6.8%
    (bench groups make up the remaining 8.6%)

ESPN's weights are then averaged with the other six sources' weights. Each
source counts once; no source is favored. The result is the DDF weight set
shown at the top of this post.

The QB starter budget (162.9) is then applied to ESPN. ESPN's QB starter
group total is 30.8, so the rate is `162.9 / 30.8 = 5.29`. Every QB starter
on ESPN has his starter slice multiplied by 5.29 to produce his Adjusted
starter contribution. This turns ESPN's per-game surplus into the trade value
units the pie is denominated in. The rate for ESPN's wide receiver starters
is `908.6 / 208.9 = 4.35`. ESPN gives quarterbacks a smaller share (5.6%)
than the 6.9% budget, so each point of quarterback surplus on ESPN is paid
about a fifth more than a point of wide receiver surplus, whose share (38.3%)
is close to its budget (38.6%).

## What changes the weights

### League size

League size moves the weights, but not in a straight line. Running backs
peak at 10 teams and fall back by 14; wide receivers do the reverse. The
quarterback share stays between 7.2% and 7.7%. I did not isolate why each
position moves; treat the pattern as a measurement, not an explanation. In
practice: do not assume a bigger league values running backs more.

| Setting | QB | RB | WR | TE | Bench share |
|---|---|---|---|---|---|
| PPR 8 teams | 7.4% | 40.8% | 45.6% | 6.3% | 6.3% |
| PPR 10 teams | 7.7% | 45.7% | 40.2% | 6.4% | 7.2% |
| PPR 12 teams | 7.2% | 43.0% | 41.7% | 8.1% | 6.7% |
| PPR 14 teams | 7.7% | 39.0% | 45.3% | 8.0% | 6.4% |

### Scoring format

PPR scoring inflates the value of pass catchers. In standard scoring,
running backs take a much larger share:

| Setting | QB | RB | WR | TE | Bench share |
|---|---|---|---|---|---|
| PPR 12 teams | 7.2% | 43.0% | 41.7% | 8.1% | 6.7% |
| Half PPR 12 teams | 7.6% | 46.9% | 38.0% | 7.4% | 6.9% |
| Standard 12 teams | 7.7% | 56.8% | 29.3% | 6.2% | 7.0% |

Moving from PPR to standard hands running backs about 14 more points of the
pie and takes about 12 from wide receivers. A running back-for-wide receiver
swap that looks even in PPR is not even in a standard league.

### Superflex

Adding a superflex slot more than quadruples the quarterback share because
quarterbacks now fill the superflex slot on every team (24 quarterback
starters instead of 12), and the pie grows
from 2,352 to 2,688 points with the extra slot:

| Setting | QB | RB | WR | TE |
|---|---|---|---|---|
| PPR 12, no superflex | 7.2% | 43.0% | 41.7% | 8.1% |
| PPR 12, 1 superflex | 33.3% | 30.1% | 30.6% | 5.9% |

### Bench depth and roster shape

Bench size mostly changes the bench share and barely moves the position
split. At PPR/12 with 4, 7 (default) and 10 bench spots, the bench share is
5.1%, 6.7% and 7.8%, and no position's total moves by more than 1.5
points (QB 7.5%, 7.2%, 7.2%; RB 42.9%, 43.0%, 42.6%; WR 42.8%, 41.7%, 43.2%;
TE 6.9%, 8.1%, 7.1%). Changing dedicated roster slots moves the split
directly: adding a second TE slot takes TE from 8.1% to 16.5% and the pie
from 2,352 to 2,688 points, because there are now two tight end starters per
team above the waiver line. If you play a bigger bench or an extra starting
slot, expect the tool's values for that position to move; a deeper bench
alone will not reshuffle the positions.

## Alternatives tried and rejected

These are documented in the bench-rule research
(`docs/research/bench-rule-research.md`) and the methodology's decision log:

1. **Fixed bench mix (rule A: 10:27:33:10).** Bench seats are assigned by a
   constant ratio regardless of roster shape. Fit error 0.18 against
   observed draft rosters. Rejected because it does not adapt when the user
   changes their roster.

2. **Lineup-hole rule (rule B).** Bench weight proportional to the number
   of starting lineup holes each position needs to fill. Fit error 0.36.
   Rejected: poor out-of-sample accuracy.

3. **Draft ratio per team (rule C2).** Backups based on the team's total
   draft capital, not per starter. Fit error 0.05, but does not adapt to
   the user's roster shape. Rule C1 (per starter) was chosen instead,
   and later replaced (item 8).

4. **Draft ratio with QB halved (rule C3).** Halving the QB backup ratio.
   Fit error 0.22. Rejected because it overcompensated and put QB bench
   share too low.

5. **Open by projected points over the starter line.** Filled benches with
   QBs and TEs, starved RBs. Unstable across league sizes.

6. **Open by chart value.** QB bench spots ranged from 5 to 14 across league
   sizes. Unstable and circular (bench allocation should not depend on the
   trade charts' own position opinions).

7. **Fixed 15% bench share (the original OC-2 decision).** Jeremy's initial
   decision was a flat 15% bench share. This was replaced by the
   expected-starts computation (OC-9, `es-value-001`, Jeremy 2026-10-09),
   which derives the bench share from how much bench surplus actually reaches
   a starting lineup. The computed share turned out to be around 7%, less
   than half the fixed 15%. The 15% is still the default for the reader's
   manual slider, but the tool's own weights use the computed share.

8. **D'Hondt over draft-measured backup ratios (rule C1, in use until
   2026-10-26).** It placed bench seats by fixed ratios, so a position got
   backups whether or not its players were worth rostering, and running
   backs collected a long tail of near-zero backups. Replaced by the
   league-wide pass by projected points and usage (JEG-1121, #957),
   described under The inputs.

> The fit errors in items 1 to 4 come from the bench-rule research, which that
> page marks as run on the 2026-10-10 engine, before bench seats counted flex
> starters. They were not recomputed here. Source for rules A through C3: `docs/research/bench-rule-research.md`, scorecard table. Rule C1 (draft ratio per starter, D'Hondt apportionment) was chosen then and replaced on 2026-10-26 (JEG-1121; `docs/claude-log/2026-10-26-jeg-1121-stable-bench.md`). Source for the 15% replacement: `docs/methodology.md` VP-3.4, ES-0 to ES-14, and `docs/research/qb-bench-share.md`.

## Sensitivity: what happens if the weights move

Because every source is rescaled to the same budgets, shifting weight between
positions changes the relative value of players across positions.

A 5-percentage-point shift from WR to RB at PPR/12 (RB from 43.0% to 48.0%,
WR from 41.7% to 36.7%) raises every running back's DDF Value by 11.6% and
lowers every wide receiver's by 12.0%. Quarterbacks and tight ends do not
move. I checked this by re-running the reference with those position shares
set: every running back and every wide receiver moved by the same ratio.

The size of the effect depends on how big the position's share is. A
1-point shift changes a position's values by about 1 divided by its share:

| Position | Share | Value change per 1-point shift |
|---|---|---|
| QB | 7.2% | 13.9% |
| RB | 43.0% | 2.3% |
| WR | 41.7% | 2.4% |
| TE | 8.1% | 12.3% |

So a small position is far more sensitive to the weights than a large one.
For you, this means quarterback and tight end values are the ones most
exposed to a change in method (for example, one source joining or leaving).

Each of the seven sources counts for one seventh of the weight average, but a
source that drops out (as the four charts did on 2026-10-27) moves more than
its seventh. Dropping it also changes the shared allocation and the chart
fill-ins, and with them every other source's group totals. Rerunning the
whole pipeline with one source left out at PPR/12:

| Source left out | QB | RB | WR | TE | RB, averaging step only |
|---|---|---|---|---|---|
| None (all seven) | 7.2% | 43.0% | 41.7% | 8.1% | 43.0% |
| USA Today | 6.8% | 44.3% | 40.7% | 8.2% | 43.8% |
| FantasyCalc | 6.7% | 43.5% | 41.6% | 8.1% | 43.4% |
| FantasyPros | 7.5% | 42.0% | 42.4% | 8.1% | 42.2% |
| CBS | 7.3% | 43.6% | 41.1% | 8.0% | 43.4% |
| ESPN | 7.4% | 41.6% | 42.8% | 8.2% | 42.7% |
| CBS rest of season | 7.0% | 45.5% | 39.6% | 7.9% | 42.9% |
| Razzball | 7.5% | 41.8% | 42.5% | 8.2% | 42.6% |

The quarterback share stays between 6.7% and 7.5%, but running backs range
from 41.6% to 45.5% and wide receivers from 39.6% to 42.8%. The biggest
mover is CBS rest of season: without it running backs gain 2.5 points and
wide receivers lose 2.1. Without ESPN, running backs lose 1.4. The last
column shows the same drop with the allocation held fixed (re-averaging the
other six sources' existing weights): there CBS rest of season moves
running backs by only 0.1. So most of its effect comes from what the drop changes
upstream of the average. The projections are the only sources that feed the
shared allocation (who starts, and who takes the flex and bench seats, by
the projections' mean points per game), so a missing projection reshuffles
every source's starters and backups. I did not separate the allocation's
share of that effect from the fill-ins'. For
you, this means the running back and wide receiver split is most exposed
to a projection source going missing for a week, not to any one trade
chart.

## Known limits and open questions

1. **The bench share is lower than intuition suggests.** At about 7%, the
   expected-starts bench share is less than half the original 15% fixed
   share. The expected-starts model says this is correct: most bench value
   comes from filling in for injured starters and bye weeks, which adds up
   to a small share. The reader's slider still defaults to 15% for manual
   override, so there is a gap between the tool's computed share and the
   default slider position. This is a known design tension.

2. **The QB bench share was an artifact.** An earlier version showed QB
   bench share at 22.6% because two elite quarterbacks were misclassified as
   bench players due to one projection source's outlier inputs. The Razzball
   missed-games guard (JEG-555/593) fixed the cause. Bench seats now follow
   usage (JEG-1121), so a one-quarterback 12-team league gets 8 quarterback
   bench seats and a 0.3% quarterback bench weight. See
   `docs/research/qb-bench-share.md` for the full story.

3. **The bench rule rests on two rates per position.** Since JEG-1121 the
   backup count comes from bye and missed-game rates, not from draft data,
   so it adapts to the roster. But a rate that is off (a position's real
   miss rate in a given season) moves that position's bench seats, and
   with them its bench weight. The quarterback miss rate (12%) is an open
   question with Jeremy. The draft-measured ratios
   (`config/market_bench.json`) that this rule replaced are no longer used
   to place bench seats.

4. **No per-source weighting.** Every included source counts once in the
   average. A source with shallow coverage (fewer listed players) has the
   same influence on the weights as one with deep coverage. This is a
   deliberate simplicity choice (see post 3: Why DDF Value is the core).

5. **Fill-in affects chart weights.** Trade charts that do not list enough
   players to fill out the rostered set get estimated values (VP-2.4).
   Those estimates count in the chart's group totals and therefore in its
   mix. A chart that lists only 50 players and gets 20 estimates has a mix
   that partly reflects the estimation model, not purely the publisher's
   opinion.

6. **Flex slot assignment is by projected points, not VORP.** Jeremy's
   decision (OC-4): flex and superflex slots are assigned by mean projected
   points per game, not by value above waivers. This means the allocation
   depends on how projections rank players at the margin, which can differ
   from how the market values them.

7. **The position-shares slider.** Readers can override the computed weights
   with manual position shares (VP-4.4, BE-2/MR-16). When set, the override
   rescales the computed starter and bench weights at that position to hit
   the user's target share. This is a power-user feature; the defaults use
   the computed weights.

8. **The numbers move every week, and with pending method work.** They are
   this week's figures from this week's sources. Approved changes still in
   review, such as the waiver line averaged over the seven players around
   the replacement spot (JEG-1244) and fractional flex and bench seats
   (JEG-1286), would move them once they merge; rerun the numbers then.

---

## Dashboard explainer (draft, 120 words)

> **How position weights work**
>
> The tool computes how much of the league's total trade value belongs to each
> position. It does this by measuring how much surplus each position produces
> above what the waiver wire offers, across all included sources: trade
> charts and projections alike. Each source gets its own position split, then
> the tool averages them.
>
> The result: at PPR with 12 teams, running backs hold about 43% of the
> value, wide receivers about 42%, tight ends about 8% and quarterbacks about
> 7%. Those shares change with your league size, scoring format, and roster
> settings. In superflex leagues, the quarterback share more than quadruples.
>
> The weights are recomputed every week from fresh data. No position has a
> fixed share.

**Placement (Jeremy, 2026-10-23):** collapsible section in the "How values work"
tab (`app/v2/shell.html`, `data-view="how"`). No separate card. UI
implementation is a follow-up ticket.

---

## Traceability

Every number in this post was produced on 2026-10-29 by
`python3 tools/research_post9_numbers.py` at main 7f212319, on the week 8
fixture (`data/fixtures/current/`, built 2026-10-29 21:11 UTC; comparison
chain run 2026-10-29 21:11 UTC, success, nothing failed). The script runs the
Python reference (`pipelines/value_reference.py`) and refuses (exit 2) when
any of the seven sources is missing at PPR/12, so it cannot quote an outage
as the method. The core call is:

    from pipelines.value_reference import Setting, Inputs, POSITIONS
    s = Setting(Inputs.load(), scoring='ppr', teams=12)   # expected starts on
    res = s.result()
    W = res['ddf_weights']

The per-source mixes, group totals and allocation counts come from
`res['sources'][src]` and `res['slot_fill']` in the same run. The league
size, scoring, superflex, bench and two-TE tables come from the same pipeline
at those settings. Leave-one-out reruns the whole pipeline
(`run_pipeline`, with the Setting's own arguments) with one source removed
from `included`; the averaging-only column recomputes just the weight
average (`ddf_weights(..., computed_share=True)`) over the other sources'
existing weights.

**Verified (2026-10-29):** all seven sources included; eight-group sum equals
1.000000; budgets equal pie times weights; the same checks hold, with all
seven sources included, at all 24 combinations of 3 scorings (standard, half
PPR, PPR), 4 league sizes (8, 10, 12, 14) and no or one superflex slot; both
leave-one-out measures with every source kept reproduce the pipeline's
weights exactly (the script refuses otherwise). The sensitivity figures (11.6% and 12.0%) come from a re-run
with position shares set (`position_shares`), checked on the blended DDF
Value of every running back and wide receiver above 1; the per-point column
is the formula 1 divided by the share. **Not verified:** the browser engine
was not re-run against these figures (that it matches the reference rests on
the strict compare in the deploy gate); the bench-rule fit errors are quoted
from the older bench research.
