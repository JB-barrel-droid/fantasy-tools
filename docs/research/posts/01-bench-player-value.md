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

What changes most is the price of starters at shallow positions. When fewer
bench spots go to a position, the waiver line rises, and the remaining starters
are worth less.

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
  projected close to the starter line may be above it some weeks).
- **Flex eligibility** (running backs, wide receivers, and tight ends compete
  for flex slots).

The model does not currently account for a player improving his actual
production mid-season and becoming starter-worthy through better play. It
uses pre-season and early-season projections as fixed inputs. This is a
known limitation and a prerequisite for publication (see Limitations).

The model computes a lineup-share for every player: the fraction of weeks his
production is expected to enter a starting lineup.

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
- **Starter downside not broken out.** The model does apply projection
  uncertainty symmetrically -- a starter projected near the line can fall
  below it, just as a bench player can rise above it. But the magnitude of
  starter downside is not reported separately, so the reader cannot see how
  much value starters lose to the risk of falling out of the lineup. This
  must be quantified before publication.
- **Mid-season improvement not modeled.** The model treats projections as
  fixed over the season. A bench player who improves his actual production
  mid-season -- through a role change, a teammate's injury, or genuine skill
  growth -- can become starter-worthy, but the current model does not capture
  this path. Accounting for changes in actual production trends is a
  prerequisite for publication.

## Conclusion

About 9 to 12 percent of fantasy value sits on benches, and that number is
remarkably stable. The real consequence of bench construction is not how much
bench players are worth -- it is how much starters are worth at positions
where the bench is deep or shallow. Fewer backup quarterbacks held means a
better waiver wire at quarterback, which means starting quarterbacks are
worth less.

The next post in this series covers how many backups each position deserves,
and why the answer is different from what most leagues actually hold.
