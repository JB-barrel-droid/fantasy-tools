# How many backups should a fantasy roster hold?

---

## Abstract

How many bench spots does each position deserve, and why? We tested ten
different rules for distributing bench spots across positions, scored each on
fit to 8,857 real drafts, accuracy on drafts the rule had not seen, and
stability across league settings. The winner: bench spots proportional to starters times the observed
backups-per-starter ratio from draft data. It adapts to any roster, it fits
real behavior within 0.06 backups per team, and it reveals the gap between what
leagues actually hold and what the numbers say is worth holding.

Terms used below. The waiver line is the quality of the best player you can
pick up for free at a position. Value above waivers is how much better a player
is than that waiver-line player. A backup is a bench player held behind a
starter at the same position. PPR means points per reception. Positions are
written out (quarterback, running back, wide receiver, tight end); a flex spot
can start a running back, wide receiver or tight end.

## The question

Every trade-value tool needs a waiver line: the quality of the replacement
player available at each position. The waiver line depends on how many players
are rostered at that position, which depends on how many bench spots go there.

Get it wrong, and every player's value above waivers is wrong too. Give too
many bench spots to quarterbacks, and the waiver line at quarterback drops,
making starting quarterbacks look more valuable than they are. Give too few to
running backs, and the waiver line rises, compressing the value of running-back
depth.

This started as a sanity check on one number, a 22.6% quarterback bench share
that turned out to be a data artifact, and became a question about what a bench
is for.

## The odd number that started this

The tool's bench-share readout (the share of a position's total value held by
players below the starter line) showed 22.6% of quarterback value sitting on
benches in a 12-team PPR league. In a format where only one quarterback starts
per team, that seemed too high.

It was. Two starting-caliber quarterbacks were classified as "bench" because
one projection source had them far too low (a data bug). Those two players
accounted for 70% of the quarterback bench value. Fix the data, and the
quarterback bench share drops to about 12%.

The lesson: measure on the same basis you value on. The bench share was
sorting players into tiers by the average of three projections but measuring
value from a different set of inputs. A single bad input in the tier sort
moved real starters into the bench tier.

## Does the bench mix even matter?

Mostly no. Changing the bench allocation -- even giving zero bench spots to
quarterbacks -- keeps overall bench share within a narrow band, with a rank correlation above
0.98 among the top 150 players (1.0 would mean identical order).

What does matter is the waiver line at shallow positions. Fewer backup
quarterbacks held means a better quarterback waiver wire, which makes starting
quarterbacks worth less. With 3 backup quarterbacks instead of 9 in 12-team
leagues, starting quarterbacks lose about 9% of their value. Fewer backup
tight ends cost top tight ends 3 to 5 points.

This is the real price of the bench decision: not how bench players are
valued, but how starters at shallow positions are valued.

## Five ways to think about a bench

### 1. Lineup holes (the "man-games" approach)

The earlier fixed bench mix (10 quarterback, 27 running back, 33 wide
receiver and 10 tight end spots per 80) almost exactly equals the number of
starters at each position times the weekly chance a starter is unavailable
(bye plus missed games). At the default roster, that gives
12% : 32% : 42% : 15%.

This is the "man-games" idea from value-based drafting (ranking players by
how much better they are than a replacement): bench spots go where the lineup
holes are. It is a principled rule, but it does not match what
leagues actually do (fit error 0.36).

### 2. Ranking bench players by projected points

Give bench spots to whichever positions have the most valuable bench players
by projection. This fails. Flat quarterback and tight-end curves keep backups
close to the starter line, so a points-based bench fills with quarterbacks and
tight ends (13 quarterback and 14 tight end bench spots in a 12-team league) and starves running
backs. Real managers do the opposite.

Proximity to the starter line is not the same as value.

### 3. What history says about depth

From 2015 to 2025 NFL game logs (nflverse), lineups set on season-to-date
points per game:

| Backup depth | Quarterback | Running back | Wide receiver | Tight end |
|---|---|---|---|---|
| First backup: starts per week | 0.28 | 0.30 | 0.33 | 0.21 |
| Second backup | 0.07 | 0.17 | 0.22 | 0.08 |
| Third backup | 0.00 | 0.09 | 0.14 | 0.04 |

The first backup starts about equally often at every position. Deeper
running-back and wide-receiver benches are justified; deeper quarterback
and tight-end benches are not.

### 4. Insurance, upside, and the waiver wire

A bench player adds value two ways: insurance (filling in when a starter is
out) and upside (the chance of becoming start-worthy). But how much of that
is available for free on the waiver wire?

Points per week added by each held first backup, 12-team PPR:

| Position | Insurance | Upside | Gross total | Net of waivers |
|---|---|---|---|---|
| Quarterback | 0.33 | 0.48 | 0.81 | +0.19 |
| Running back | 0.48 | 0.41 | 0.89 | +0.37 |
| Wide receiver | 0.64 | 0.67 | 1.31 | +0.54 |
| Tight end | 0.26 | 0.35 | 0.61 | +0.09 |

Net of what you could pick up on the waiver wire that week (no hindsight),
a bench spot is worth 0 to 0.5 points per week. Quarterback and tight-end
upside nets to about zero in every setting tested: whatever a backup at those
positions might become, you can grab it from waivers when it happens.
Running-back and wide-receiver upside survives.

A second quarterback or tight-end backup is worth approximately zero.

### 5. What the field does

An open-web survey of replacement-level approaches:

- **PlayerProfiler** (Value Over Stream): sets replacement at the waiver
  stream, about 1.5 quarterbacks and tight ends rostered per team, about 4
  running backs and wide receivers.
- **Subvertadown**: no value holding quarterbacks past the 12th to 16th best
  quarterback in one-quarterback leagues; streaming lands within 2 to 3 points per game of a top-5
  quarterback.
- **Fantasy Football Analytics**: baselines by worst starter, man-games, or
  the player taken at pick 100.
- **Harvard Sports Analysis Collective**: weekly replacement level.
- **Footballguys** (Harstad): value over replacement per game, times
  games played.
- **Football Perspective**: missed games valued against an average backup
  (TE18 in 12-team leagues).
- **RotoWire** (35,000 leagues): the most common setup is 12 teams, PPR or
  half PPR, one quarterback, two running backs, two wide receivers, one tight
  end, one flex, a kicker, a defense and 7 bench spots.

## What real drafters do

Fantasy Football Calculator (a public mock-draft site), 12-team PPR, 8,857
human-pick drafts, 2016 to 2024.

Share of skill-position picks, stable within 1 percentage point across
seasons:

| Position | Share | Per team | Backups per starter |
|---|---|---|---|
| Quarterback | 14.3% | 1.86 | 0.86 |
| Running back | 35.6% | 4.63 | 0.85 |
| Wide receiver | 39.3% | 5.11 | 1.05 |
| Tight end | 10.7% | 1.39 | 0.39 |

Fewer than half of teams carry a backup tight end. Nearly every team carries
a backup quarterback, and that is the position where a backup is most easily
streamed.

With kickers and defenses (15-round drafts): kickers rostered 1.00 per
team, defenses 1.06. Backups per starter: kickers 0.00, defenses 0.06. Leagues stream both.

### Superflex and two-quarterback leagues

In Fantasy Football Calculator 12-team two-quarterback drafts (2018 to 2024,
6,967 drafts): 2.56 quarterbacks per team, only 0.28 backups per quarterback
starter. A 12-team two-quarterback league rosters about 31 quarterbacks,
nearly every NFL starter. The backup-quarterback question answers itself in
superflex (a format where a flex spot may start a quarterback): there is
nobody left to hold.

## The test: scoring ten candidate rules

Every candidate scored on:

1. **Fit to observed rosters** (backups per team against the draft data).
2. **Held-out fit** (trained on 2016 to 2020, predicted 2022 to 2024).
3. **Stability** across all 12 league settings.
4. **Zero rank inversions** in every setting (no pair of players whose order
   flips against the source ranking).

| Rule | Fit error (backups per team) | Held-out error | Adapts to roster |
|---|---|---|---|
| A. Fixed 10:27:33:10 | 0.18 | 0.18 | no |
| B. Lineup holes | 0.36 | 0.40 | yes |
| **C1. Draft ratio per starter** | **0.06** | **0.10** | **yes** |
| C2. Draft ratio per team | 0.05 | 0.06 | no |
| C3. C1 with the quarterback ratio halved | 0.22 | 0.21 | yes |

Also tested and rejected (all unstable, circular, or produced cliffs):
open by points, open by trade-chart value, lineup holes times drop-off, starts by
depth round, insurance plus upside points, net-of-waivers value, measured
streaming coverage from history.

## Answer

**Bench spots are proportional to starters times the measured
backups-per-starter ratio from draft data.**

The chosen rule (C1) fits real roster construction within 0.06 backups per
team, holds up on held-out drafts (0.10), adapts to any roster configuration,
and produces zero rank inversions across every setting tested.

In a 12-team league with one quarterback, two running backs, two wide
receivers, one tight end, one flex, a kicker, a defense and 7 bench spots, the
market bench rule gives (spots are shared out with the D'Hondt method, a
highest-averages way of dividing seats in proportion to a weight):

| Position | Bench spots |
|---|---|
| Quarterback | about 1 |
| Running back | about 3 |
| Wide receiver | about 3 |
| Tight end | about 0 |

Exact counts depend on where the flex spot lands.

## What leagues do versus what works

Just as players have a market value (what others will pay) and a fundamental
value (what their production is worth), benches have a market expectation
(what leagues actually hold) and a fundamental strategy (what is worth
holding).

- **Market bench:** real drafts hold about 0.86 backup quarterbacks, 0.85 backup
  running backs, 1.05 backup wide receivers, and 0.39 backup tight ends per
  starter. This sets the waiver
  line -- the replacement level everyone actually faces.
- **Fundamental bench:** net of waivers, running-back and wide-receiver depth
  earn their spots; one backup quarterback is marginal; a second quarterback
  or tight-end backup is worth about zero.
- **The gap is the advice:** leagues over-hold backup quarterbacks relative
  to their fundamental worth. That thins the waiver wire, which makes
  starting quarterbacks worth more than they would be in a league that held
  only what is worth holding.

## Methodology lessons

- Measure on the basis you value on. The quarterback artifact came from
  sorting by the average of three projections but measuring a different set
  of inputs.
- Prefer rules that need no iteration and no projections. Watch for circular
  measurements: waiver quality depends on how deep everyone else holds.
- Score candidates on fit, out-of-sample fit, and stability, not on whether
  they confirm a prior. Several intuitive rules failed.

## Limitations

- Draft data is from draft-day mock drafts, not in-season rosters. In-season
  quarterback backups are probably fewer (managers stream), but that is
  unmeasured.
- Only 12-team archives are available; other league sizes are extrapolated
  by per-starter ratios.
- Two-quarterback and superflex data comes from Fantasy Football
  Calculator's "2 QB" label, which does not separate superflex from a true
  two-quarterback league.
- Real-league rostered-percentage data from fantasy platforms would be the
  natural validation but was not available.
- The value-effect tables use the default roster of one quarterback, two
  running backs, two wide receivers, one tight end, one flex, a kicker, a
  defense and 7 bench spots.
