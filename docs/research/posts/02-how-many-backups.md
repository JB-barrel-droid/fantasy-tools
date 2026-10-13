# How many backups should a fantasy roster hold?

Research post 2 (JEG-557). Draft for Jeremy's review.
Copy rules: for trades others will accept; no named players in examples; no title abbreviations.

---

## Abstract

How many bench spots does each position deserve, and why? We tested ten
different rules for distributing bench spots across positions, scored each on
fit to 8,857 real drafts, out-of-sample accuracy, and stability across league
settings. The winner: bench spots proportional to starters times the observed
backups-per-starter ratio from draft data. It adapts to any roster, it fits
real behavior within 0.06 backups per team, and it reveals the gap between what
leagues actually hold and what the numbers say is worth holding.

> Evidence: [bench-rule-research.md](../bench-rule-research.md).
> Draft data: `pipelines/derive_market_bench.py`, `config/market_bench.json`.
> Analysis scripts: JEG-566 (pending; not yet committed to `tools/bench_research`).

## The question

Every trade-value tool needs a waiver line: the quality of the replacement
player available at each position. The waiver line depends on how many players
are rostered at that position, which depends on how many bench spots go there.

Get it wrong, and every player's value above replacement is wrong too. Give too
many bench spots to quarterbacks, and the waiver line at quarterback drops,
making starting quarterbacks look more valuable than they are. Give too few to
running backs, and the waiver line rises, compressing the value of running-back
depth.

This started as a sanity check on one number -- a 22.6% QB bench share that
turned out to be a data artifact (see [the QB bench-share
finding](../qb-bench-share.md)) -- and became a question about what a bench is
for.

## The odd number that started this

The model's bench-share readout showed 22.6% of quarterback value sitting on
benches in a 12-team PPR league. In a format where only one quarterback starts
per team, that seemed too high.

It was. Two starting-caliber quarterbacks were classified as "bench" because
one projection source had them far too low (a data bug). Those two players
accounted for 70% of the QB bench value. Fix the data, and QB bench share
drops to about 12%.

The lesson: measure on the same basis you value on. The bench share was
sorting players into tiers by the average of three projections but measuring
value from a blend of seven sources. A single bad input in the tier sort
moved real starters into the bench tier.

(Full details: [qb-bench-share.md](../qb-bench-share.md).)

## Does the bench mix even matter?

Mostly no. Changing the bench allocation -- even giving zero bench spots to
quarterbacks -- keeps overall bench share between 8.3% and 8.7%, with top-150
rank correlation above 0.98.

What does matter is the waiver line at shallow positions. Fewer backup
quarterbacks held means a better quarterback waiver wire, which makes starting
quarterbacks worth less. With 3 backup quarterbacks instead of 9 in 12-team
leagues, starting quarterbacks lose about 9% of their value. Fewer backup
tight ends cost top tight ends 3 to 5 points.

This is the real price of the bench decision: not how bench players are
valued, but how starters at shallow positions are valued.

## Five ways to think about a bench

### 1. Lineup holes (the "man-games" approach)

The legacy bench mix (QB 10, RB 27, WR 33, TE 10) almost exactly equals the
number of starters at each position times the weekly chance a starter is
unavailable (bye plus missed games). At the default roster, that gives
12% : 32% : 42% : 15%.

This is the "man-games" idea from value-based drafting: bench spots go where
the lineup holes are. It is a principled rule, but it does not match what
leagues actually do (fit error 0.36).

### 2. Ranking bench players by projected points

Give bench spots to whichever positions have the most valuable bench players
by projection. This fails. Flat quarterback and tight-end curves keep backups
close to the starter line, so a points-based bench fills with quarterbacks and
tight ends (13 QB / 14 TE bench spots in a 12-team league) and starves running
backs. Real managers do the opposite.

Proximity to the starter line is not the same as value.

### 3. What history says about depth

From 2015 to 2025 NFL game logs (nflverse), lineups set on season-to-date
points per game:

| Backup depth | QB | RB | WR | TE |
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

Points added per held first backup, 12-team PPR:

| Position | Insurance | Upside | Gross total | Net of waivers |
|---|---|---|---|---|
| QB | 0.33 | 0.48 | 0.81 | +0.19 |
| RB | 0.48 | 0.41 | 0.89 | +0.37 |
| WR | 0.64 | 0.67 | 1.31 | +0.54 |
| TE | 0.26 | 0.35 | 0.61 | +0.09 |

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
- **Subvertadown**: no value holding quarterbacks past QB12 to QB16 in 1-QB
  leagues; streaming lands within 2 to 3 points per game of a top-5
  quarterback.
- **Fantasy Football Analytics**: baselines by worst starter, man-games, or
  pick-100 cutoff.
- **Harvard Sports Analysis Collective**: weekly replacement level.
- **Footballguys** (Harstad): per-game VBD times games played.
- **Football Perspective**: missed games valued against an average backup
  (TE18 in 12-team leagues).
- **RotoWire** (35,000 leagues): the most common setup is 12 teams, PPR or
  half PPR, 1 QB / 2 RB / 2 WR / 1 TE / 1 FLEX / K / DEF, 7 bench.

## What real drafters do

Fantasy Football Calculator, 12-team PPR, 8,857 human-pick drafts,
2016 to 2024.

Share of skill-position picks, stable within 1 percentage point across
seasons:

| Position | Share | Per team | Backups per starter |
|---|---|---|---|
| QB | 14.3% | 1.86 | 0.86 |
| RB | 35.6% | 4.63 | 0.85 |
| WR | 39.3% | 5.11 | 1.05 |
| TE | 10.7% | 1.39 | 0.39 |

Fewer than half of teams carry a backup tight end. Nearly every team carries
a backup quarterback, and that is the position where a backup is most easily
streamed.

With kickers and defenses (15-round drafts): K rostered 1.00 per team,
DEF 1.06. Backups per starter: K 0.00, DEF 0.06. Leagues stream both.

> Source: `pipelines/derive_market_bench.py`; frozen ratios in
> `config/market_bench.json`.

### Superflex and 2-QB leagues

In FFC 12-team 2-QB drafts (2018 to 2024, 6,967 drafts): 2.56 quarterbacks
per team, only 0.28 backups per quarterback starter. A 12-team 2-QB league
rosters about 31 quarterbacks -- nearly every NFL starter. The backup-QB
question answers itself in superflex: there is nobody left to hold.

## The test: scoring ten candidate rules

Every candidate scored on:

1. **Fit to observed rosters** (backups per team against the draft data).
2. **Out-of-sample fit** (trained on 2016 to 2020, predicted 2022 to 2024).
3. **Stability** across all 12 league settings.
4. **Zero rank inversions** in every setting.

| Rule | Fit error | Held-out error | Adapts to roster |
|---|---|---|---|
| A. Fixed 10:27:33:10 | 0.18 | 0.18 | no |
| B. Lineup holes | 0.36 | 0.40 | yes |
| **C1. Draft ratio per starter** | **0.06** | **0.10** | **yes** |
| C2. Draft ratio per team | 0.05 | 0.06 | no |
| C3. C1 with QB halved | 0.22 | 0.21 | yes |

Also tested and rejected (all unstable, circular, or produced cliffs):
open by points, open by chart value, lineup holes times drop-off, starts by
depth round, insurance plus upside points, net-of-waivers value, measured
streaming coverage from history.

## Answer

**Bench spots are proportional to starters times the measured
backups-per-starter ratio from draft data.**

The chosen rule (C1) fits real roster construction within 0.06 backups per
team, holds up out of sample (0.10), adapts to any roster configuration,
and produces zero rank inversions across every setting tested.

In a 12-team league with 1 QB / 2 RB / 2 WR / 1 TE / FLEX / K / DEF and
7 bench spots, the market bench rule gives:

| Position | Bench spots (D'Hondt) |
|---|---|
| QB | ~1 |
| RB | ~3 |
| WR | ~3 |
| TE | ~0 |

(Exact counts depend on where flex lands.)

## What leagues do versus what works

Just as players have a market value (what others will pay) and a fundamental
value (what their production is worth), benches have a market expectation
(what leagues actually hold) and a fundamental strategy (what is worth
holding).

- **Market bench:** real drafts hold about 0.86 backup QBs, 0.85 backup RBs,
  1.05 backup WRs, and 0.39 backup TEs per starter. This sets the waiver
  line -- the replacement level everyone actually faces.
- **Fundamental bench:** net of waivers, running-back and wide-receiver depth
  earn their spots; one backup quarterback is marginal; a second quarterback
  or tight-end backup is worth about zero.
- **The gap is the advice:** leagues over-hold backup quarterbacks relative
  to their fundamental worth. That thins the waiver wire, which makes
  starting quarterbacks worth more than they would be in a league that held
  only what is worth holding.

## Methodology lessons

- Measure on the basis you value on. The QB artifact came from sorting by
  projection-mean rank but measuring the seven-source blend.
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
- 2-QB/superflex data is from FFC's "2 QB" label, which does not separate
  superflex from true 2-QB.
- Real-league rostered-percentage data (from platform APIs) would be the
  natural validation but was not reachable.
- Value-effect tables (how many bench seats under each rule, which players
  move) were computed on the 2026-10-10 engine, before the roster convention
  (JEG-562) and new default roster (JEG-563). Direction and size are correct;
  exact numbers will update.

---

## Evidence links

| Claim | Source | Script |
|---|---|---|
| Draft ratios (8,857 drafts) | [bench-rule-research.md](../bench-rule-research.md) section 1 | `pipelines/derive_market_bench.py` |
| Scorecard (10 rules) | [bench-rule-research.md](../bench-rule-research.md) section 2 | JEG-566 pending |
| Starts per week by depth | [bench-rule-research.md](../bench-rule-research.md) section 3 | JEG-566 pending |
| Insurance vs upside, net of waivers | [bench-rule-research.md](../bench-rule-research.md) section 3 | JEG-566 pending |
| QB bench share artifact | [qb-bench-share.md](../qb-bench-share.md) | JEG-566 pending |
| Superflex / 2-QB | JEG-557 comment (2026-10-10) | JEG-566 pending |
| K/DEF streaming | JEG-557 comment (2026-10-10) | `pipelines/derive_market_bench.py` |
| Field survey | JEG-557 description, section 8 | links in description |
