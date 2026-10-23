# How much is a bench player worth?

---

## Abstract

Bench points do not count. A player on your bench only creates value when his
production enters a starting lineup. We measure how much of a bench player's
surplus actually reaches a lineup, and what that means for how much starters
and bench players should cost.

The answer: about 9 to 12 percent of league-wide value above waivers sits on
benches. That number is stable across league sizes, scoring formats, and bench
depths. A bench player's value comes almost entirely from filling in for
starters who miss games or have byes; the chance of a bench player becoming
start-worthy adds only a small amount on top.

But the picture is not static. Starters face downside risk too: projection
uncertainty can push a starter below the line. And bench value declines as the
season progresses -- fewer weeks remain for a backup to pay off, and fewer
breakouts happen late. What changes most is the price of starters at shallow
positions. When fewer bench spots go to a position, the waiver line rises, and
the remaining starters are worth less.

## The question

Every fantasy player has value above replacement (what he produces beyond what
the waiver wire offers). But a bench player's surplus only matters when it
enters a starting lineup. How much of it actually does?

This decides two things a manager needs to know:

1. How much should a bench player cost relative to a starter at the same
   position?
2. Where should bench spots go -- and does the answer change anything about
   how much starting quarterbacks and tight ends are worth?

## Method

We measure what share of each position's value above waivers belongs to bench
players who have a realistic chance of entering a starting lineup.

### The value pie

The total value above waivers across all rostered players is the league's
"value pie." The pie is set by a fixed scale factor of 28 points per starting
slot, times the number of teams and slots. The number 28 is a chosen unit of
account -- it sets the size of the currency, not the results. Any other
constant would rescale every player's value proportionally and leave the
percentages, ratios, and rankings unchanged.

At 12 teams with 7 starting slots (1 QB / 2 RB / 2 WR / 1 TE / 1 FLEX), the
pie is 2,352 points (28 x 12 x 7). It does not depend on scoring or bench
size.

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
- **Missed games** (position-specific rates from 2015 to 2025 NFL game logs,
  sourced from nflverse). See the variance discussion below.
- **Projection uncertainty** (the spread across sources; a bench player
  projected close to the starter line may be above it some weeks -- and a
  starter near the line may fall below it).
- **Flex eligibility** (running backs, wide receivers, and tight ends compete
  for flex slots).

The model computes a lineup-share for every player: the fraction of weeks his
production is expected to enter a starting lineup. Projection uncertainty is
applied symmetrically: it can move a bench player above the starter line
(upside) or a starter below it (downside).

At 12-team PPR on a default roster (2 WR, 7 bench), the overall bench share
is 10.0%, distributed by position: QB 6.4%, RB 7.7%, WR 13.0%, TE 2.5%.

## Data

### Fill-in rates from history

A backup is any player rostered past the number of starters at his position.
In a 12-team league with 2 starting running back slots, the top 24 running
backs by season-to-date points per game are starters; the 25th through 36th
(one extra per team) are first backups, the 37th through 48th are second
backups, and so on. A backup "starts" when he is the best available option on
a team's roster in a week when a starter ahead of him is unavailable.

How often does a backup actually start? From 2015 to 2025 NFL game logs
(nflverse), with lineups set each week on season-to-date points per game:

| Backup depth | QB | RB | WR | TE |
|---|---|---|---|---|
| First backup | 0.28 starts/week | 0.30 | 0.33 | 0.21 |
| Second backup | 0.07 | 0.17 | 0.22 | 0.08 |
| Third backup | 0.00 | 0.09 | 0.14 | 0.04 |

The first backup starts about equally often at every position. After that,
running-back and wide-receiver depth earns playing time; quarterback and
tight-end depth does not.

### Missed-game rates: how stable are they?

The model uses position-specific missed-game rates drawn from 11 seasons of
NFL game logs (2015 to 2025, nflverse). Because this is a load-bearing
assumption, here is how much it varies.

Average fraction of games missed by starters, per position, per season:

| Position | 11-season mean | Range (min-max) | Std dev across seasons | Recent 5 years (2020-25) |
|---|---|---|---|---|
| QB | 7.9% | 6.4% - 9.7% | 1.0 pp | 8.3% |
| RB | 12.5% | 7.6% - 16.4% | 2.5 pp | 12.8% |
| WR | 11.0% | 8.8% - 13.9% | 1.3 pp | 11.7% |
| TE | 11.2% | 9.3% - 14.2% | 1.5 pp | 11.0% |

Running backs show the most year-to-year variance (standard deviation of
2.5 percentage points across seasons). The other positions vary by about
1 to 1.5 percentage points per year. Recent seasons (2020-2025) are close to
the 11-year averages: QB and RB are each about half a point higher, WR is
about 0.7 points higher, and TE is essentially unchanged. The model defaults
to the recent 5-year rates.

These rates are stable enough to use as defaults, but a league with reason
to believe injury patterns differ (say, a dynasty league tracking aging
rosters) could adjust them. The sensitivity table below shows that the
overall bench-share result barely moves even with meaningful changes in the
inputs.

### Bench depth barely changes overall value

Changing the number of bench slots moves overall bench share by only a
fraction of a percentage point, with zero rank inversions across the top
150 players.

The practical implication: adding or removing a bench spot does not
meaningfully change how much of the league's value is controlled by bench
players. What it does change is the waiver line. With fewer bench spots,
the replacement player at each position is better, so starters are worth
less relative to replacement. This matters most when deciding whether to
carry a backup quarterback or tight end -- positions where the waiver wire
already provides close to what a held backup offers.

## Results

### The starter-to-bench pay ratio

At 12-team PPR, the ratio of starter value to bench value per player is:
QB 1.6x, RB 3.4x, WR 3.6x, TE 1.3x. A starter running back is worth
3.4 times as much per point above waivers as a bench running back.

### Starter downside and bench upside

Projection uncertainty cuts both ways. A bench player projected near the
starter line has a chance of being above it (upside); a starter projected near
the line has a chance of falling below it (downside). The model accounts for
both.

At 12-team PPR, the risk table per position (in pie points, out of 2,352):

| Position | Starter downside | Bench upside | Net |
|---|---|---|---|
| QB | 64 (2.7% of pie) | 37 (1.6%) | -28 |
| RB | 229 (9.7%) | 269 (11.4%) | +40 |
| WR | 207 (8.8%) | 110 (4.7%) | -97 |
| TE | 9 (0.4%) | 2 (0.1%) | -8 |
| **Overall** | **509 (21.6%)** | **417 (17.7%)** | **-92** |

Starter downside is the value starters lose because projection uncertainty can
push them below the starter line. Bench upside is the value bench players gain
for the same reason. The net is negative overall: starters lose more to
downside risk than bench players gain from upside, because starters are
clustered closer to the line and have more value at stake.

Running backs are the exception: bench RB upside (11.4% of the pie) exceeds
starter RB downside (9.7%), because deep RB benches have more players near the
line with meaningful value. For your roster, this means that running-back depth
is the one position where bench players are not just insurance -- they have a
real chance of delivering starter-quality weeks.

### Historical breakout rates

How often does a bench player actually break into the starter tier mid-season?
From 11 seasons of NFL game logs (2015-2025, nflverse), we measured how many
players ranked outside the starter tier at mid-season (week 9, by cumulative
points per game) finished the season ranked inside it.

| Position | Breakout rate | First backup | Second backup | Third backup |
|---|---|---|---|---|
| QB | 4.2% | 13.6% | 2.3% | 0.0% |
| RB | 3.5% | 22.7% | 4.5% | 3.8% |
| WR | 3.3% | 27.3% | 12.1% | 6.1% |
| TE | 2.6% | 18.2% | 4.5% | 1.5% |

First backups break out at meaningful rates: roughly one in four WR first
backups and one in five RB first backups become starters by season end. But
beyond the first backup, breakout rates fall sharply. Third-backup breakouts
are rare at every position except WR, where 6.1% still make it.

These breakout rates represent an additive bound on bench value beyond what the
fill-in model captures. The fill-in model measures how often a backup enters
the lineup temporarily; the breakout rate measures how often a backup
permanently displaces a starter.

### Where the value sits

Most league value is concentrated in starting running backs and wide
receivers. Bench value is small everywhere, but its distribution across
positions matters because it determines the waiver line.

### What it means for your roster

The bench share number itself is less important than what it implies:

1. A bench player is mostly insurance. His value comes from the weeks a
   starter misses, not from his own production ceiling.
2. The waiver wire already provides most of what a backup quarterback or
   tight end offers. Holding a second backup at either position is worth
   close to zero (see post 2: "How many backups should a fantasy roster
   hold?").
3. Running-back and wide-receiver depth earns its roster spots. Second and
   third backups at those positions still start regularly.
4. Starters near the position line face meaningful downside risk. If your
   starter is the 23rd or 24th running back, projection uncertainty gives
   him a real chance of falling out of the lineup.

## Bench value declines as the season progresses

Bench value is not constant over the season. As weeks go by, three things
shrink it:

1. **Fewer remaining weeks** for a backup to fill in. The total value a bench
   player can deliver is proportional to how many games remain.
2. **Fewer remaining byes.** Early in the season, about 6-8% of starters are
   on bye each week; by week 14, all byes are past, eliminating that source of
   bench starts.
3. **Narrowing projection uncertainty.** As more games are played, projections
   converge and the chance of a bench player's true value being above the
   starter line shrinks.

The model is already week-aware: it re-computes bench share using only the
weeks remaining from the current point in the season, counts only future byes,
and narrows the uncertainty band as the horizon shortens. The per-week bench
share declines modestly: from about 8.7% at week 1 to about 7.2% by week 17
at 12-team PPR.

But the bigger effect is on breakout value. Historical breakout rates (the
chance a bench player becomes a starter by season end) decline sharply as the
measurement point moves later:

| Measurement week | QB breakout | RB breakout | WR breakout | TE breakout |
|---|---|---|---|---|
| Week 4 | 6.3% | 5.3% | 5.3% | 4.0% |
| Week 9 | 4.2% | 3.5% | 3.3% | 2.6% |
| Week 13 | 2.8% | 2.1% | 1.9% | 1.3% |
| Week 16 | 1.4% | 1.1% | 1.1% | 0.7% |

By mid-season, breakout rates are roughly half their early-season values.
By week 13, they are a third.

The practical implication for roster management: **depth is worth more early
in the season.** A bench spot that is valuable in week 4 (when byes are
active, projections are uncertain, and breakouts are possible) may be nearly
worthless by week 14. Managers should be more willing to hold speculative
depth early and more willing to drop it for immediate needs as the season
progresses.

## Sensitivity

The bench-share result is stable across league settings:

| Setting | Overall bench share |
|---|---|
| PPR / 12 teams | 10.0% |
| Half PPR / 12 teams | 9.7% |
| Standard / 12 teams | 9.1% |
| PPR / 14 teams | 8.9% |
| PPR / 10 teams | 10.4% |
| PPR / 8 teams | 10.0% |

The overall number stays between 8.9% and 12.5% across every setting tested.
Bench depth changes it by a fraction of a percentage point.

## Limitations

- **Projection-based lineup decisions.** The model sets lineups from
  projections, not actual weekly outcomes. This matches how most managers
  make start/sit decisions: you start the player projected highest, not the
  one who will score the most (which you cannot know in advance). Measuring
  how often projection-based decisions match actual outcomes is a future step.
- **Projection error unmeasured.** The spread of projections across sources is
  a proxy for true uncertainty. Measuring projection error against actual
  results would refine the uncertainty bands.
- **Mid-season improvement not modeled.** The model treats projections as
  fixed over the season. A bench player who improves his actual production
  mid-season -- through a role change, a teammate's injury, or genuine skill
  growth -- can become starter-worthy, but the current model does not capture
  this path dynamically. The historical breakout rates above provide an
  empirical bound on this effect, but integrating it into the model would
  require week-by-week projection updates. This is a prerequisite for
  publication.

## Conclusion

About 9 to 12 percent of fantasy value sits on benches, and that number is
remarkably stable. The real consequence of bench construction is not how much
bench players are worth -- it is how much starters are worth at positions
where the bench is deep or shallow. Fewer backup quarterbacks held means a
better waiver wire at quarterback, which means starting quarterbacks are
worth less.

Starters face downside risk from projection uncertainty, especially at
running back where bench upside actually exceeds starter downside. And bench
value declines as the season progresses: hold depth early, be willing to drop
it late.

The next post in this series covers how many backups each position deserves,
and why the answer is different from what most leagues actually hold.
