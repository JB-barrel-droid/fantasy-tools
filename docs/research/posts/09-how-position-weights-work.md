# How we split value across positions

Research post 9 (JEG-925). Jeremy, 2026-10-26: refresh to today's rules and
publish without his review.

> **Status, 2026-10-27: rules text current, numbers pending.** The text below
> follows today's rules: league-wide bench seats by projected points and
> usage (JEG-1121, #957), the two DDF numbers, and fit labels. The tables still
> hold the 2026-10-25 numbers, computed under the old bench rule, and are
> **not to be quoted**. They can't be recomputed today: the four trade
> charts are "not yet published for week 8" (JEG-1175), so the weights
> currently come from the three projections alone. Once every source
> publishes, `python3 tools/research_post9_numbers.py` regenerates every
> table (it refuses while any source is missing), and this note comes out.

Copy rules: for trades others will accept; no title abbreviations.

---

## Abstract

When the tool says a running back is worth 120 and a quarterback is worth 80,
the gap is not arbitrary. Behind the scenes, the Trade Value Chart computes
**position weights**: the share of the league's total trade value that belongs
to each position. Those weights decide how much of the fixed value pie goes to
quarterbacks, running backs, wide receivers and tight ends -- and within each
position, how much goes to starters versus bench players.

Position weights are the crux of the tool. Every Adjusted value depends on
them, so DDF Charted Value (the average of the Adjusted trade charts), DDF
Projected Value (the Adjusted projections) and every fit label on a trade
depend on them too. This post explains
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
| QB | 5.9% | 0.1% | 6.0% |
| RB | 34.7% | 2.4% | 37.2% |
| WR | 47.0% | 4.2% | 51.3% |
| TE | 5.5% | 0.1% | 5.5% |
| **Total** | **93.1%** | **6.9%** | **100.0%** |

(Rounded to one decimal, so a row can differ from its parts by 0.1.)

The total pie at this setting is 2,352 points (28 per starting slot times 12
teams times 7 starting slots per team, the flex slot included). Each group's
budget is its weight times the pie. WR starters get 1,106 of the 2,352; QB
starters get 138; TE bench players get about 1.

What this means for a trade: at this setting more than half of all trade value
sits in wide receivers, and the whole quarterback position gets about the
same pie share as the tight ends. A quarterback is not cheap because he is
bad; he is cheap because one starter per team leaves a small slice to divide.

Those budgets control the Adjusted values. A source whose running backs carry
a lot of surplus sees those values scaled up or down until the running back
budget matches what the weights say. The weights are the bridge between each
source's own opinion and the common scale.

> Numbers: recomputed from `pipelines/value_reference.py`, `Setting(Inputs.load(), scoring='ppr', teams=12, expected_starts=True).result()['ddf_weights']` on the current fixture (`data/fixtures/current/`, built 2026-09-19). Verified: the eight groups sum to 1.0000.

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
   values). Since 2026-10-26 (JEG-1121, #957) bench seats are filled
   league-wide in one pass: every seat goes to the best remaining player at
   any position, scored by his projected points per game times a usage
   discount. The discount is how often a backup at that position is needed
   (starters per team times the bye and missed-game rate). It shrinks a
   step each time a position's backups pass a tier of about two needed
   backups per team. So a position whose starters rarely miss, like
   quarterback in a one-quarterback league, gets few backups, while one
   that misses often gets more. The backup quarterback count therefore
   moves with the data rather than a fixed ratio. It replaces the earlier
   rule, which split the seats by D'Hondt over draft-measured backup ratios
   (`config/market_bench.json`). This is VP-2.2 and
   `pipelines/lib/roster_convention.py` (`vorp_bench_allocate`).

3. **The bench share from expected starts.** Instead of a fixed 15% bench
   share, the tool computes how much of each position's surplus actually
   reaches a starting lineup, using missed-game rates, bye weeks and
   depth-chart volatility. The model now also credits a bench player for the
   chance he is promoted into a starting role (and debits a marginal starter
   for the chance he is demoted), scaled by the weeks remaining (#867). The
   bench share is an output of the weight computation, not an input. This is
   the expected-starts system (ES-0 to ES-14).

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
| QB starter | 19.0 |
| QB bench | 0.2 |
| RB starter | 166.8 |
| RB bench | 18.9 |
| WR starter | 265.8 |
| WR bench | 24.8 |
| TE starter | 29.7 |
| TE bench | 0.4 |

They add to 525.8.

> Numbers: from `res['sources']['espn']['groups']` in the same pipeline run.

### Step 2: Each source gets normalized to mixes (VP-3.2 through VP-3.4)

The group totals are in different units (points per game for projections,
trade value points for charts). To compare them, the tool converts each
source to two unit-free mixes:

- **Starter mix**: the share of starter surplus at each position.
  `starter_mix[QB]` = QB starter total / sum of all starter totals.
- **Bench mix**: the share of bench surplus at each position.
  `bench_mix[QB]` = QB bench total / sum of all bench totals.

ESPN's starter mix this week: QB 4.0%, RB 34.6%, WR 55.2%, TE 6.2%.
ESPN's bench mix: QB 0.5%, RB 42.6%, WR 55.9%, TE 1.0%.

Each source also gets its own 8-group weight set. With expected starts
enabled, each group's weight is simply its group total divided by the
source's grand total (the mixes are combined through the source's own
bench-to-starter ratio, which varies by source).

The per-source starter mixes for all seven included sources this week:

| Source | QB | RB | WR | TE |
|---|---|---|---|---|
| USA Today (chart) | 7.9% | 34.1% | 51.0% | 7.0% |
| FantasyCalc (chart) | 7.3% | 41.4% | 44.5% | 6.8% |
| FantasyPros (chart) | 8.3% | 43.9% | 44.3% | 3.5% |
| CBS (chart) | 7.7% | 38.4% | 48.3% | 5.6% |
| ESPN (projection) | 4.0% | 34.6% | 55.2% | 6.2% |
| CBS rest of season (projection) | 5.3% | 33.9% | 54.2% | 6.6% |
| Razzball (projection) | 3.6% | 34.8% | 56.3% | 5.3% |
| **Mean** | **6.3%** | **37.3%** | **50.5%** | **5.9%** |

All four charts give quarterbacks 7.3% to 8.3% of starter surplus; all three
projections give them 3.6% to 5.3%. That split is the main reason the
combined quarterback share lands near 6% instead of near 8%. For a trade it
means the quarterback prices you see are a compromise between a market that
pays for the position and projections that do not.

> Numbers: from `res['sources'][src]['starter_mix']` for each source.

### Step 3: Average the mixes across sources (VP-4)

The DDF weights are the average of all included sources' mixes:

- For each position, the starter mix mean is the arithmetic mean of the
  included sources' starter mixes at that position.
- Same for the bench mix mean.

Sources that have no players at a position, or no weights at all, are
excluded from the average at that position. So is a source that has not
published for the current week: on 2026-10-27, while the four trade charts
were still on week 7, the weights came from the three projections alone.

With expected starts, the weights that are actually used come from a second
average: the tool averages each source's 8-group weights directly (seven
sources, each counted once) and renormalizes to 1. This means the bench
share is an output: it is whatever the averaged weights say, not a fixed 15%.
Currently the computed bench share is about 6.9% at PPR/12. The mix means
below are reported as diagnostics; the final weights are the 8-group table at
the top of this post.

This week's mix means:

    Starter mix mean:  QB 6.3%  RB 37.3%  WR 50.5%  TE 5.9%
    Bench mix mean:    QB 2.5%  RB 34.6%  WR 62.2%  TE 0.8%
    Bench share:       6.9%

### Step 4: Weights become budgets (VP-5)

The pie for the setting is `28 x teams x starting_slots`. At PPR/12 that is
2,352.

Each group's budget is pie times its weight:

| Group | Weight | Budget |
|---|---|---|
| QB starter | 5.9% | 138.1 |
| QB bench | 0.1% | 3.4 |
| RB starter | 34.7% | 817.3 |
| RB bench | 2.4% | 57.6 |
| WR starter | 47.0% | 1,105.9 |
| WR bench | 4.2% | 99.9 |
| TE starter | 5.5% | 128.5 |
| TE bench | 0.1% | 1.4 |

Each source's Adjusted values are then scaled so its group totals match these
budgets. A source with relatively more QB value than the average sees its QB
values scaled down; one with less sees them scaled up. The budgets are the
same for every source -- that is how sources end up on a common scale.

## A worked example: ESPN at PPR/12

ESPN projects players' points per game. At PPR/12, the allocation gives:

- QB: 12 starters, 4 bench
- RB: 27 starters (24 dedicated + 3 flex), 21 bench
- WR: 33 starters (24 dedicated + 9 flex), 57 bench
- TE: 12 starters, 2 bench

(Those 168 rostered players are 12 teams times 14 roster spots.)

ESPN's total value above waivers across all groups is 525.8 points per game.
Its group totals (from Step 1 above) give it this weight set:

    QB starter: 19.0 / 525.8 = 3.6%
    RB starter: 166.8 / 525.8 = 31.7%
    WR starter: 265.8 / 525.8 = 50.6%
    TE starter: 29.7 / 525.8 = 5.7%
    (bench groups make up the remaining 8.4%)

ESPN's weights are then averaged with the other six sources' weights. Each
source counts once; no source is favored. The result is the DDF weight set
shown in Step 3.

The QB starter budget (138.1) is then applied to ESPN. ESPN's QB starter
group total is 19.0, so the rate is `138.1 / 19.0 = 7.26`. Every QB starter
on ESPN has their starter slice multiplied by 7.26 to produce their Adjusted
starter contribution. This scales ESPN's per-game surplus into the trade
value units the pie is denominated in. ESPN gives quarterbacks a smaller
share (3.6%) than the 5.9% budget, so its quarterbacks are scaled up; the
same step scales its wide receivers (50.6% against a 47.0% budget) down.

## What changes the weights

### League size

League size moves the weights, but not in a straight line. The quarterback
share rises from 8 to 12 teams and then eases at 14; running backs peak at
12 teams. The bench share falls steadily as the league grows. I did not
isolate why each position moves; treat the pattern as a measurement, not an
explanation. In practice: do not assume a 14-team league values running
backs more than a 12-team one.

| Setting | QB | RB | WR | TE | Bench share |
|---|---|---|---|---|---|
| PPR 8 teams | 4.8% | 31.1% | 58.4% | 5.7% | 8.0% |
| PPR 10 teams | 5.2% | 34.9% | 54.8% | 5.1% | 7.8% |
| PPR 12 teams | 6.0% | 37.2% | 51.3% | 5.5% | 6.9% |
| PPR 14 teams | 5.8% | 33.6% | 54.9% | 5.6% | 6.8% |

### Scoring format

PPR scoring inflates the value of pass catchers. In standard scoring, RB
takes a much larger share:

| Setting | QB | RB | WR | TE | Bench share |
|---|---|---|---|---|---|
| PPR 12 teams | 6.0% | 37.2% | 51.3% | 5.5% | 6.9% |
| Half PPR 12 teams | 6.2% | 47.2% | 41.4% | 5.2% | 6.8% |
| Standard 12 teams | 6.7% | 60.0% | 28.4% | 4.9% | 7.9% |

Moving from PPR to standard hands running backs 23 more points of the pie
and takes 23 from wide receivers. A running back-for-wide receiver swap that
looks even in PPR is not even in a standard league.

### Superflex

Adding a superflex slot more than triples QB's share because quarterbacks now
fill a starting slot on every team (24 quarterback starters instead of 12),
and the pie grows from 2,352 to 2,688 points with the extra slot:

| Setting | QB | RB | WR | TE |
|---|---|---|---|---|
| PPR 12, no superflex | 6.0% | 37.2% | 51.3% | 5.5% |
| PPR 12, 1 superflex | 21.8% | 33.9% | 37.7% | 6.7% |

### Bench depth and roster shape

Bench size mostly changes the bench share and barely moves the position
split. At PPR/12 with 4, 7 (default) and 10 bench spots, the bench share is
5.2%, 6.9% and 7.9%, and no position's total moves by more than about a
point (QB 5.3%, 6.0%, 6.0%; TE 6.0%, 5.5%, 5.0%). Changing dedicated roster
slots moves the split directly: adding a second TE slot takes TE from 5.5%
to 11.3% and the pie from 2,352 to 2,688 points, because there are now two
tight end starters per team above the waiver line. If you play a bigger bench
or an extra starting slot, expect the tool's values for that position to
move; a deeper bench alone will not reshuffle the positions.

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
   a starting lineup. The computed share turned out to be around 7% -- less
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

A 5-percentage-point shift from WR to RB at PPR/12 (RB from 37.2% to 42.2%,
WR from 51.3% to 46.3%) raises every running back's DDF Value by 13.4% and
lowers every wide receiver's by 9.8%. Quarterbacks and tight ends do not
move. I checked this by re-running the reference with those position shares
set: every running back and every wide receiver moved by the same ratio.

The size of the effect depends on how big the position's share is. A
1-point shift changes a position's values by about 1 divided by its share:

| Position | Share | Value change per 1-point shift |
|---|---|---|
| QB | 6.0% | 16.6% |
| RB | 37.2% | 2.7% |
| WR | 51.3% | 2.0% |
| TE | 5.5% | 18.1% |

So a small position is far more sensitive to the weights than a large one.
For you, this means quarterback and tight end values are the ones most
exposed to a change in method (for example, one source joining or leaving).

The multi-source average gives stability. Each of the seven sources counts for
one seventh of the weights. Leaving out any single source at PPR/12 moves the
quarterback share between 5.7% and 6.5% (from 6.0%), running backs between
36.1% and 37.9% (from 37.2%) and wide receivers between 50.4% and 52.3% (from
51.3%). The largest single move is FantasyPros, whose removal takes running
backs down 1.1 points.

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
   usage (JEG-1121), so the quarterback bench is small in a one-quarterback
   league; the count is recomputed with the tables. See
   `docs/research/qb-bench-share.md` for the full story.

3. **The bench rule rests on two rates per position.** Since JEG-1121 the
   backup count comes from bye and missed-game rates, not from draft data,
   so it adapts to the roster. But a rate that is off (a position's real
   miss rate in a given season) moves that position's bench seats, and
   with them its bench weight. The draft-measured ratios
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
> The result: at PPR with 12 teams, wide receivers hold about 51% of the
> value, running backs about 37%, quarterbacks about 6%, and tight ends about
> 5.5%. Those shares change with your league size, scoring format, and roster
> settings. In superflex leagues, QB's share more than triples.
>
> The weights are recomputed every week from fresh data. No position has a
> fixed share.

**Placement (Jeremy, 2026-10-23):** collapsible section in the "How values work"
tab (`app/v2/shell.html`, `data-view="how"`). No separate card. UI
implementation is a follow-up ticket.

---

## Traceability

Every number in this post was produced on 2026-10-25 by running the Python
reference pipeline on the current fixture (`data/fixtures/current/`, built
2026-09-19) at main bd345e00:

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

**Pending (2026-10-27):** the 2026-10-25 run below predates the JEG-1121 bench
rule; `tools/research_post9_numbers.py` replaces it once every source
publishes.

**Verified (2026-10-25):** eight-group sum equals 1.0000; budgets equal pie times weights;
per-source group totals match the code's output; the same checks hold at all
24 combinations of 3 scorings (standard, half PPR, PPR), 4 league sizes
(8, 10, 12, 14) and no or one superflex slot. The sensitivity table's
13.4% and 9.8% come from a re-run with position shares set
(`position_shares`); the per-point column is the formula 1 divided by the
share. **Not verified:** the browser engine was not re-run against these
figures (that it matches the reference rests on the strict compare in the
deploy gate); the bench-rule fit errors are quoted from the older bench
research; the fixture does not state its week, so the post no longer names
one.
