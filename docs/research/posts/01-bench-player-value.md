# How much is a bench player worth?

Research post 1 (JEG-544). Draft for Jeremy's review.
Copy rules: for trades others will accept; no named players (rank-based examples only); no title abbreviations.

---

## Abstract

Bench points do not count. A player on your bench only creates value when his
production enters a starting lineup. We measure how much of a bench player's
surplus actually reaches a lineup, and what that means for how much starters
and bench players should cost.

The answer: about 8 to 10 percent of league-wide value above waivers sits on
benches. That number is stable across league sizes, scoring formats, and bench
depths. A bench player's value comes almost entirely from filling in for
starters who miss games or have byes; the chance of a bench player becoming
start-worthy adds only a small amount on top.

What changes most is the price of starters at shallow positions. When fewer
bench spots go to a position, the waiver line rises, and the remaining starters
are worth less.

> Evidence: [research-post-1-facts.md](../research-post-1-facts.md),
> [bench-rule-research.md](../bench-rule-research.md).
> Readout: JEG-593 (done). Scripts: JEG-566 (pending).

## The question

Every fantasy player has value above replacement (what he produces beyond what
the waiver wire offers). But a bench player's surplus only matters when it
enters a starting lineup. How much of it actually does?

This decides two things a manager needs to know:

1. How much should a bench player cost relative to a starter at the same
   position?
2. Where should bench spots go -- and does the answer change anything about
   how much starting quarterbacks and tight ends are worth?

(See manifesto sections 4 through 8: bench points do not count, bench players
are options, and roster spots have opportunity cost.)

## Method

We measure what share of each position's value above waivers belongs to bench
players who have a realistic chance of entering a starting lineup.

### The value pie

The total value above waivers across all rostered players is the league's
"value pie." At 12 teams with 8 starting slots, the pie is 2,688 points
(28 per starting slot times the number of teams and slots). It does not depend
on scoring or bench size.

Each source (projection or trade chart) is decomposed into value above the
waiver line, then rescaled so its total equals the pie. The waiver line at each
position is the value of the first player past the rostered count.

### Two bounds on bench share

Every bench player's value above waivers splits into two pieces:

- **Fill-in value (the bench slice):** the portion below the starter line.
  This is what any rostered player provides just by being on the roster --
  insurance against byes and missed games.
- **Starter-quality value (the starter slice):** the portion above the
  starter line. This is the premium a player earns by being good enough to
  start even when nobody is injured.

The fill-in-only bound counts only the bench slices of bench players. It is
the floor: how much bench value exists if bench players never become
start-worthy.

The full bound adds the starter slices of bench players, weighted by each
player's probability of reaching a lineup.

### Expected starts

Each player's probability of reaching a lineup depends on:

- **Bye weeks** (one week in 18, about 5.6 percent).
- **Missed games** (position-specific rates from 2015-2025 game logs).
- **Projection uncertainty** (the spread across sources; a bench player
  projected close to the starter line may be above it some weeks).
- **Flex eligibility** (running backs, wide receivers, and tight ends compete
  for flex slots).

The model computes a lineup-share for every player: the fraction of weeks his
production is expected to enter a starting lineup.

> Bench-share readout (JEG-593, 2026-10-12, after the Razzball data fix):
> At 12-team PPR on the default roster, by position:
> QB 12.2% | RB 9.1% | WR 7.0% | TE 12.2% | overall 8.6%.
>
> **Pending JEG-562:** these numbers will update when the tier basis moves to
> the roster convention. The QB number was an artifact at 22.6% before the
> Razzball fix (see [qb-bench-share.md](../qb-bench-share.md)); 12.2% is the
> corrected figure, but the tier-basis effect (JEG-562) has not been applied.
> Do not treat these as final.

## Data

### Fill-in rates from history

How often does a backup actually start? From 2015-2025 NFL game logs
(nflverse), lineups set each week on season-to-date points per game
(JEG-551, verified 2026-10-12):

| Backup depth | QB | RB | WR | TE |
|---|---|---|---|---|
| First backup | 0.28 starts/week | 0.30 | 0.33 | 0.21 |
| Second backup | 0.07 | 0.17 | 0.22 | 0.08 |
| Third backup | 0.00 | 0.09 | 0.14 | 0.04 |

The first backup starts about equally often at every position. After that,
running-back and wide-receiver depth earns playing time; quarterback and
tight-end depth does not.

At the approved defaults, the model gives first-backup fill-in rates of
RB depth-1 50.9% and WR depth-1 46.3% (JEG-551, verified).

### Bench depth barely changes overall value

Changing the number of bench slots from 4 to 8 moves overall bench share by
only 0.2 percentage points (8.8% to 9.0%), with zero rank inversions across
the top 150 players (JEG-553, verified 2026-10-12).

What does change is the waiver line: with fewer bench spots, the replacement
player at each position is better, so starters are worth less relative to
replacement.

## Results

### The starter-to-bench pay ratio

At 12-team PPR with the current engine, the ratio of starter value to bench
value per player is:

> **Pending JEG-562:** re-run after the tier-basis convention lands to get
> final ratios. The draft's RB 1.0x to 1.7x and WR 1.0x to 3.0x (Jeremy's
> approved figures) will be confirmed against the convention.

### Where the value sits

Most league value is concentrated in starting running backs and wide
receivers. Bench value is small everywhere, but its distribution across
positions matters because it determines the waiver line.

### What matters to readers

The bench share number itself is less important than what it implies:

1. A bench player is mostly insurance. His value comes from the weeks a
   starter misses, not from his own production ceiling.
2. The waiver wire already provides most of what a backup quarterback or
   tight end offers. Holding a second backup at either position is worth
   close to zero (see post 2: "How many backups should a fantasy roster
   hold?").
3. Running-back and wide-receiver depth earns its roster spots. Second and
   third backups at those positions still start regularly.

## Sensitivity

The bench-share readout is stable across league settings:

| Setting | Overall bench share |
|---|---|
| PPR / 12 teams | 8.6% |
| Half PPR / 12 teams | 7.8% |
| Standard / 12 teams | 8.0% |
| PPR / 14 teams | 7.7% |
| PPR / 10 teams | 8.6% |
| PPR / 8 teams | 8.7% |

(JEG-593, 2026-10-12. Pending JEG-562 for final numbers.)

The overall number stays between 7.7% and 8.7% across every setting tested.
Bench depth (4 to 8 slots) changes it by 0.2 percentage points (JEG-553).

## Limitations

- **Numbers are not final.** The tier-basis convention (JEG-562) and the
  default roster switch (JEG-563, to 1 QB / 2 RB / 2 WR / 1 TE / FLEX /
  K / DEF, 7 bench) will change the readout. Every number above will be
  updated before publishing.
- **No actuals storage.** The model uses projected points, not actual
  outcomes. Measuring realized bench value requires storing weekly actuals
  and comparing projected lineup shares with actual starts.
- **Projection error unmeasured.** The spread of projections is a proxy for
  true uncertainty. Measuring projection error against actuals is a future
  step (manifesto G4/G6).
- **Starter downside not shown.** The model applies projection uncertainty
  to bench players (the chance of becoming start-worthy) but the inverse --
  a starter falling below the line -- is not broken out separately.
  JEG-550 will quantify this.

## Conclusion

About 8 to 10 percent of fantasy value sits on benches, and that number is
remarkably stable. The real consequence of bench construction is not how much
bench players are worth -- it is how much starters are worth at positions
where the bench is deep or shallow. Fewer backup quarterbacks held means a
better waiver wire at quarterback, which means starting quarterbacks are
worth less.

The next post in this series covers how many backups each position deserves,
and why the answer is different from what most leagues actually hold.

---

## Live widgets (for the research tab, JEG-543)

- **Readout:** bench share this week by position, from the engine's
  `getBenchShareReadout()`.
- **Lineup-share-by-rank chart** per position, with the starter line marked.
- **What-ifs:** bench slots, league size, scoring, injury rates, projection
  confidence. Recomputed on a scratch copy of settings; "Apply to my league"
  is optional.

## Evidence links

| Claim | Source | Script |
|---|---|---|
| Fill-in rates by depth | JEG-551 comment (verified) | JEG-566 pending |
| Bench-slots effect 0.2pp | JEG-553 comment (verified) | JEG-566 pending |
| QB 22.6% artifact | [qb-bench-share.md](../qb-bench-share.md) | JEG-566 pending |
| Bench-share readout by setting | JEG-593 (done) | engine `bench_share_readout` |
| Bench-share bounds | JEG-548 (done, 2026-10-12) | `tools/bench_research/bench_share_bounds.py` |
| Decomposition (start-worthy vs fill-in) | JEG-549 (done, 2026-10-12) | `tools/bench_research/bench_share_decomposition.py` |
