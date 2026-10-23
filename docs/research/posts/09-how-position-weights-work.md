# How we split value across positions

Research post 9 (JEG-925). Draft for Jeremy's review.
Copy rules: for trades others will accept; no title abbreviations.

---

## Abstract

When the tool says a running back is worth 120 and a quarterback is worth 80,
the gap is not arbitrary. Behind the scenes, the Trade Value Chart computes
**position weights**: the share of the league's total trade value that belongs
to each position. Those weights decide how much of the fixed value pie goes to
quarterbacks, running backs, wide receivers and tight ends -- and within each
position, how much goes to starters versus bench players.

Position weights are the crux of the tool. Every Adjusted value, every DDF
Value, and every trade recommendation depends on them. This post explains
exactly where they come from.

> Evidence: `docs/methodology.md` VP-2 through VP-5.
> Engine: `app/trade-value-chart/assets/value-model.js`, `runValuePipeline` (VP-3, VP-4).
> Reference: `pipelines/value_reference.py`, functions `_mixes` and `ddf_weights`.

## What a position weight is

A position weight is a number between 0 and 1 that says what fraction of the
league's total value pie belongs to a group. There are eight groups: four
positions (QB, RB, WR, TE) times two roles (starter, bench). The eight
weights sum to 1.

At PPR scoring with 12 teams and the default roster (QB1 RB2 WR3 TE1 FLEX1,
6 bench), the current weights are:

| Position | Starter | Bench | Total |
|---|---|---|---|
| QB | 10.0% | 0.7% | 10.7% |
| RB | 35.5% | 2.6% | 38.1% |
| WR | 41.3% | 2.6% | 43.9% |
| TE | 7.2% | 0.1% | 7.3% |
| **Total** | **93.9%** | **6.1%** | **100.0%** |

The total pie at this setting is 2,352 points (28 per starting slot times 12
teams times 7 starters per team, plus the flex slot). Each group's budget is
its weight times the pie. WR starters get 971 of the 2,352; QB starters get
235; TE bench players get 3.

Those budgets control the Adjusted values. A source whose running backs carry
a lot of surplus sees those values scaled up or down until the running back
budget matches what the weights say. The weights are the bridge between each
source's own opinion and the common scale.

> Numbers: recomputed from `pipelines/value_reference.py`, `Setting(Inputs.load(), scoring='ppr', teams=12, expected_starts=True).result()['ddf_weights']` on the week 7 fixture (`data/fixtures/current/`). Verified: the eight groups sum to 1.0000.

## The inputs

The weights come from three things:

1. **The included sources' value above waivers at each position.** This is
   the total surplus that every player at a position produces above what the
   waiver wire offers, computed separately for starters and bench players.
   Each of the included sources (up to seven: four trade charts, three
   projections) produces its own group totals. This is VP-2 and VP-3 in the
   spec.

2. **The league allocation.** How many starters and bench players each
   position gets is decided by the user's roster settings, with flex and
   superflex slots assigned by projected points (not by the source's own
   values). Bench seats are apportioned by D'Hondt across the positions,
   using draft-measured ratios of backups per starter from Fantasy Football
   Calculator data (`config/market_bench.json`). This is VP-2.2.

3. **The bench share from expected starts.** Instead of a fixed 15% bench
   share, the tool computes how much of each position's surplus actually
   reaches a starting lineup, using missed-game rates, bye weeks and
   depth-chart volatility. The bench share is an output of the weight
   computation, not an input. This is the expected-starts system (ES-0 to
   ES-14).

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

For ESPN projections at PPR/12 this week, the group totals are:

| Group | Total |
|---|---|
| QB starter | 48.7 |
| QB bench | 3.4 |
| RB starter | 183.5 |
| RB bench | 19.7 |
| WR starter | 220.1 |
| WR bench | 19.0 |
| TE starter | 36.5 |
| TE bench | 1.0 |

> Numbers: from `res['sources']['espn']['groups']` in the same pipeline run.

### Step 2: Each source gets normalized to mixes (VP-3.2 through VP-3.4)

The group totals are in different units (points per game for projections,
trade value points for charts). To compare them, the tool converts each
source to two unit-free mixes:

- **Starter mix**: the share of starter surplus at each position.
  `starter_mix[QB]` = QB starter total / sum of all starter totals.
- **Bench mix**: the share of bench surplus at each position.
  `bench_mix[QB]` = QB bench total / sum of all bench totals.

ESPN's starter mix this week: QB 10.0%, RB 37.5%, WR 45.0%, TE 7.5%.
ESPN's bench mix: QB 7.8%, RB 45.7%, WR 44.2%, TE 2.3%.

Each source also gets its own 8-group weight set. With expected starts
enabled, each group's weight is simply its group total divided by the
source's grand total (the mixes are combined through the source's own
bench-to-starter ratio, which varies by source).

The per-source starter mixes for all five included sources this week:

| Source | QB | RB | WR | TE |
|---|---|---|---|---|
| FantasyCalc (chart) | 8.5% | 39.6% | 43.7% | 8.2% |
| CBS (chart) | 7.3% | 37.7% | 46.1% | 8.9% |
| ESPN (projection) | 10.0% | 37.5% | 45.0% | 7.5% |
| CBS rest of season (projection) | 15.1% | 36.5% | 40.7% | 7.7% |
| Razzball (projection) | 12.4% | 37.4% | 44.4% | 5.9% |

> Numbers: from `res['sources'][src]['starter_mix']` for each source.

### Step 3: Average the mixes across sources (VP-4)

The DDF weights are the average of all included sources' mixes:

- For each position, the starter mix mean is the arithmetic mean of the
  included sources' starter mixes at that position.
- Same for the bench mix mean.

Sources that have no players at a position, or no weights at all, are
excluded from the average at that position.

With expected starts, the tool then averages each source's 8-group weights
directly and renormalizes to 1. This means the bench share is an output:
it is whatever the averaged weights say, not a fixed 15%. Currently the
computed bench share is about 6.1% at PPR/12.

The final DDF weights this week:

    Starter mix mean:  QB 10.7%  RB 37.8%  WR 44.0%  TE 7.6%
    Bench mix mean:    QB 12.1%  RB 40.5%  WR 44.4%  TE 3.0%
    Bench share:       6.1%

### Step 4: Weights become budgets (VP-5)

The pie for the setting is `28 x teams x starting_slots`. At PPR/12 that is
2,352.

Each group's budget is pie times its weight:

| Group | Weight | Budget |
|---|---|---|
| QB starter | 10.0% | 234.6 |
| QB bench | 0.7% | 17.3 |
| RB starter | 35.5% | 834.6 |
| RB bench | 2.6% | 61.7 |
| WR starter | 41.3% | 971.3 |
| WR bench | 2.6% | 60.3 |
| TE starter | 7.2% | 169.1 |
| TE bench | 0.1% | 3.2 |

Each source's Adjusted values are then scaled so its group totals match these
budgets. A source with relatively more QB value than the average sees its QB
values scaled down; one with less sees them scaled up. The budgets are the
same for every source -- that is how sources end up on a common scale.

## A worked example: ESPN at PPR/12

ESPN projects players' points per game. At PPR/12, the allocation gives:

- QB: 12 starters, 15 bench
- RB: 27 starters (24 dedicated + 3 flex), 28 bench
- WR: 33 starters (24 dedicated + 9 flex), 35 bench
- TE: 12 starters, 6 bench

ESPN's total value above waivers across all groups is 531.9 points per game.
Its group totals (from Step 1 above) give it this weight set:

    QB starter: 48.7 / 531.9 = 9.2%
    RB starter: 183.5 / 531.9 = 34.5%
    WR starter: 220.1 / 531.9 = 41.4%
    TE starter: 36.5 / 531.9 = 6.9%
    (bench groups make up the remaining 8.2%)

ESPN's weights are then averaged with the other four sources' weights. Each
source counts once; no source is favored. The result is the DDF weight set
shown in Step 3.

The QB starter budget (234.6) is then applied to ESPN. ESPN's QB starter
group total is 48.7, so the rate is `234.6 / 48.7 = 4.82`. Every QB starter
on ESPN has their starter slice multiplied by 4.82 to produce their Adjusted
starter contribution. This scales ESPN's per-game surplus into the trade
value units the pie is denominated in.

## What changes the weights

### League size

As leagues get larger, QB's share rises because more quarterbacks are
rostered and the scarcity premium grows:

| Setting | QB | RB | WR | TE | Bench share |
|---|---|---|---|---|---|
| PPR 8 teams | 8.4% | 37.5% | 45.9% | 8.2% | 6.2% |
| PPR 10 teams | 9.1% | 39.8% | 43.3% | 7.8% | 6.2% |
| PPR 12 teams | 10.7% | 38.1% | 43.9% | 7.3% | 6.1% |
| PPR 14 teams | 13.0% | 36.8% | 43.3% | 6.8% | 6.5% |

### Scoring format

PPR scoring inflates the value of pass catchers. In standard scoring, RB
takes a much larger share:

| Setting | QB | RB | WR | TE |
|---|---|---|---|---|
| PPR 12 teams | 10.7% | 38.1% | 43.9% | 7.3% |
| Half PPR 12 teams | 11.7% | 42.9% | 38.4% | 7.0% |
| Standard 12 teams | 12.4% | 47.9% | 33.3% | 6.3% |

### Superflex

Adding a superflex slot nearly doubles QB's share because QBs now fill a
starting slot they were previously excluded from:

| Setting | QB | RB | WR | TE |
|---|---|---|---|---|
| PPR 12, no superflex | 10.7% | 38.1% | 43.9% | 7.3% |
| PPR 12, 1 superflex | 21.0% | 33.3% | 38.7% | 7.1% |

### Bench depth and roster shape

More bench slots shift value toward positions with higher backup ratios
(RB, WR). The bench share also rises slightly. Changing dedicated roster
slots (for example, adding a second TE slot) increases that position's share
directly because more starters means more surplus above the waiver line.

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
   the user's roster shape. Rule C1 (per starter) was chosen instead.

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
   a starting lineup. The computed share turned out to be around 6% -- less
   than half the fixed 15%. The 15% is still the default for the reader's
   manual slider, but the tool's own weights use the computed share.

> Source for rules A through C3: `docs/research/bench-rule-research.md`, scorecard table. The chosen rule is C1 (draft ratio per starter, D'Hondt apportionment). Source for the 15% replacement: `docs/methodology.md` VP-3.4, ES-0 to ES-14, and `docs/research/qb-bench-share.md`.

## Sensitivity: what happens if the weights move

Because every source is rescaled to the same budgets, shifting weight between
positions changes the relative value of players across positions.

A 5-percentage-point shift from WR to RB (for example, moving WR from 44% to
39% and RB from 38% to 43%) would increase every running back's Adjusted
value by about 13% and decrease every wide receiver's Adjusted value by about
11%. DDF Value, which averages the Adjusted values, would move proportionally.

The sensitivity is roughly proportional: a 1-point shift in weight moves a
position's values by about 2 to 3 percent. This means the weights are
consequential -- small changes to the inputs (for example, one source joining
or leaving the included set) can shift a position's total trade value by a
meaningful amount.

However, the multi-source averaging provides stability. Because the DDF
weights are the mean of five to seven sources' mixes, a single source
changing its position opinion moves the weights by only about 1/5 to 1/7 of
the change in that source's mix.

## Known limits and open questions

1. **The bench share is lower than intuition suggests.** At about 6%, the
   expected-starts bench share is less than half the original 15% fixed
   share. The expected-starts model says this is correct: most bench value
   comes from filling in for injured starters and bye weeks, which adds up
   to a small share. The reader's slider still defaults to 15% for manual
   override, so there is a gap between the tool's computed share and the
   default slider position. This is a known design tension.

2. **The QB bench share was an artifact.** An earlier version showed QB
   bench share at 22.6% because two elite quarterbacks were misclassified as
   bench players due to one projection source's outlier inputs. The Razzball
   missed-games guard (JEG-555/593) fixed the cause. See
   `docs/research/qb-bench-share.md` for the full story.

3. **Draft-measured backup ratios are frozen.** The `config/market_bench.json`
   ratios come from FFC drafts in 2016 to 2024 (skill-only set, 8,857
   drafts). They are not re-derived each season. If real roster composition
   shifts materially, the frozen ratios would need updating. The superflex
   ratios come from the 2-QB format because FFC does not separate superflex.

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

---

## Dashboard explainer (draft, 120 words)

> **How position weights work**
>
> The tool computes how much of the league's total trade value belongs to each
> position. It does this by measuring how much surplus each position produces
> above what the waiver wire offers, across all included sources -- trade
> charts and projections alike. Each source gets its own position split, then
> the tool averages them.
>
> The result: at PPR with 12 teams, wide receivers hold about 44% of the
> value, running backs about 38%, quarterbacks about 11%, and tight ends about
> 7%. Those shares change with your league size, scoring format, and roster
> settings. In superflex leagues, QB's share nearly doubles.
>
> The weights are recomputed every week from fresh data. No position has a
> fixed share.

**Placement (Jeremy, 2026-10-23):** collapsible section in the "How values work"
tab (`app/v2/shell.html`, `data-view="how"`). No separate card. UI
implementation is a follow-up ticket.

---

## Traceability

Every number in this post was produced by running the Python reference
pipeline on the week 7 fixture:

    python3 -c "
    from pipelines.value_reference import Setting, Inputs, POSITIONS
    inp = Inputs.load()   # data/fixtures/current/
    s = Setting(inp, scoring='ppr', teams=12, expected_starts=True)
    res = s.result()
    W = res['ddf_weights']
    for p in POSITIONS:
        sw, bw = W[f'{p}|starter'], W[f'{p}|bench']
        print(f'{p}: starter={sw:.6f} bench={bw:.6f} total={sw+bw:.6f}')
    "

The per-source mixes, group totals and allocation counts come from
`res['sources'][src]` and `res['slot_fill']` in the same run. The sensitivity
tables come from the same script run at different `teams`, `scoring` and
`superflex` parameters.

**Verified:** eight-group sum equals 1.0000; budgets equal pie times weights;
per-source group totals match the code's output. **Not verified:** the
sensitivity percentages (2 to 3 percent per 1-point shift) are approximate,
estimated from the budget formula, not from a full re-run with perturbed
weights.
