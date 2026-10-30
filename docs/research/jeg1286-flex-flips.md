# Flex and bench slot flips (JEG-1286)

Research only, 2026-10-29. No value math, default, ranking or published
output changed. Jeremy picks the rule; this page lays out the options.
Figures: [data/jeg1286_flex_flips.md](data/jeg1286_flex_flips.md). Script:
`tools/research/jeg1286_flex_flips.py` (report: `tools/research/jeg1286_report.py`).

## The answer

Flips are frequent and large. On the real data updates since October 1, the
flex split changed between two consecutive bakes 233 times in 1,386
comparisons across the 14 settings (17%), on 8 to 13 of the 20 days with a
bake in every setting but standard 8-team. Each flip moved the most affected
player's DDF Value by a median 1.73 points (90th percentile 3.12, worst
5.58). That player is usually the top of a position: Jahmyr Gibbs in 106 of
the 233 flips, Brock Bowers in 28, Jaxon Smith-Njigba in 23. Nothing about
those players changed; one fringe RB or WR crossed the flex cutoff.

**Recommendation: option B, fractional flex and bench seats with σ = 0.75
PPG.** With PR #1077's waiver band, no 1 PPG change to any one source moves
any other player more than 0.53 DDF Value points (today: 3.90, and 236 cases
over the 1.0 bar). It costs a one-time shift of 0.4 to 4.5 points for the
most affected player per setting, and more engine work per setting.

## Options

| | Rule | Worst move from a 1 PPG change (with #1077) | Cases over 1.0 of 6,564 | One-time change to today's values |
|---|---|---|---|---|
| A | Leave as is: flex and bench seats go to the highest mean projections, a hard cutoff | 3.90 | 236 | none |
| **B (pick)** | **Fractional seats: each player near a cutoff holds a share of a seat by how sure the projections are that he clears it (σ 0.75 PPG), for flex and bench** | **0.53** | **0** | **0.4 to 4.5 per setting (USO: Gibbs 88.6 to 85.8, Smith-Njigba 70.0 to 71.8)** |
| C | Fixed flex split from real-league flex usage (42% RB, 46% WR, 12% TE); bench as today | 1.05 (main) | 2 (main) | up to 12.6 (Smith-Njigba 42.2 to 54.8, standard/8) |
| D | Keep the flex step, but stop the bench discount reacting to it (fixed flex share in the discount) | 2.24 (main) | 120 (main) | up to 7.5 (Gibbs 76.3 to 68.8, standard/8) |

C and D were swept on main only (one-player waiver line); A and B on both.
On main, B's worst is 1.01, one QB waiver-line case that #1077 removes.

Not built, and why:

- **Stickiness (keep last week's split unless the new one wins by a margin).**
  Values would depend on the order of past updates, not on today's inputs, so
  the Python reference, the spec reference and `value_check` could no longer
  reproduce a published number from its fixture. It also still jumps, just
  less often.
- **Each source allocates its own flex.** Each source's own step is a third
  of the size but there are three of them, and it reverses OC-4 (one league
  allocation).

## What a flip is

VP-2.2 fills flex seats with the flex-eligible players who have the highest
mean projected points, then fills bench seats one at a time by points times
a usage discount (`roster_convention.vorp_bench_allocate`). Both are hard
cutoffs. When the last flex WR and the best non-flex RB swap order, a whole
seat moves from WR to RB. Two things then amplify it:

1. **The bench follows.** The bench discount uses starters per team
   (`c = starters/teams × (bye rate + miss rate)`), so the flip also reshuffles
   bench seats: in the JEG-1286 repro, one flex seat moves two bench seats
   (WR bench 17 to 15, RB 41 to 43).
2. **The pie follows.** Each position's share of the fixed pie comes from its
   group totals of value above the waiver and starter lines (VP-3, VP-4). One
   more RB starter raises the RB starter group, so every RB gains and every
   WR loses in proportion to his value. That is why stars move most.

The cutoff is usually close. In 12 of the 14 settings, a 1 PPG change in one
source to one player is enough to cross the flex cutoff today; in five of
them 0.15 PPG is enough (figures, section 1). Bench cutoffs are as close.

## How often and how big

**Real updates** (figures, section 4). Each of the 107 `players.json` bakes
on main, replayed with today's code and its own fixture. A flip's size is
the gap, at the later bake, between DDF Value with the allocation free and
with the earlier bake's allocation held, so everything else that changed
between the two bakes cancels out. Over the 99 bakes with all three
projections (from October 1):

| Setting | Flex flips | Bench-only flips | Days with a flex flip | Flex splits seen RB/WR/TE |
|---|---|---|---|---|
| standard/10 | 19 | 5 | 10 of 20 | 10/0/0, 9/1/0, 8/2/0 |
| ppr/12 | 11 | 1 | 9 of 20 | 2/10/0 to 5/7/0 |
| half_ppr/8 | 16 | 1 | 12 of 20 | 7/1/0 to 3/5/0 |
| USO | 19 | 1 | 13 of 20 | 12/0/0 to 9/3/0 |
| Charlotte | 16 | 10 | 11 of 20 | 8/4/0 to 4/8/0 |

Only standard 8-team never flipped (its flex cutoff is 2.7 PPG of one source
away). The splits wander widely: half PPR 8-team ranged from 7 RB / 1 WR to
3 RB / 5 WR over the month.

**One-player sweep** (figures, section 3). Every player within 3 of a flex
or rostered cutoff, each source, ±0.5 and ±1 PPG: 6,564 cases. 276 flipped
the allocation (192 flex, 84 bench only). Of the 239 cases where any other
player moved more than 1.0 DDF Value, 220 were flips. The other 19 are one
separate step, below.

## Before and after, named players

A 1 PPG drop in one source's projection for one fringe player (figures,
section 2; DDF Value before to after the change):

| Case | Player | A today | B (σ 0.75, flex and bench) |
|---|---|---|---|
| Charlotte, DJ Moore ESPN −1 (flex 5 RB/7 WR to 6/6) | Jahmyr Gibbs | 78.6 to 82.4 (+3.79) | 81.2 to 81.4 (+0.22) |
| | Kenneth Walker III | 71.1 to 74.6 (+3.52) | 73.5 to 73.7 (+0.20) |
| USO, Blake Corum ESPN −1 (flex 11/1 to 10/2) | Jahmyr Gibbs | 88.6 to 86.6 (−2.06) | 85.8 to 85.7 (−0.11) |
| | Bijan Robinson | 80.3 to 78.3 (−1.93) | 77.6 to 77.5 (−0.10) |
| standard/10, Jalen Coker CBS ROS −1 (the ticket's repro) | Jahmyr Gibbs | 83.0 to 84.8 (+1.82) | 81.6 to 81.8 (+0.14) |
| | Chris Olave | 21.4 to 19.7 (−1.66) | 22.4 to 22.3 (−0.12) |

Under A a manager in Charlotte sees Gibbs gain almost 4 points because DJ
Moore's ESPN projection dipped. Under B he gains 0.2.

## Option B in detail

**What it does.** Today a flex seat goes to whoever ranks above the cutoff,
all or nothing. Under B each candidate holds a share of a seat equal to
Φ((projection − cutoff) / σ), with the cutoff set so the shares add up to the
league's seats. A player well above the cutoff holds a whole seat, one well
below holds none, and the two players either side of a near-tie hold about
half each. The fractional counts (standard/10 today: 9 RB, 1 WR; under B: 8.3
RB, 1.7 WR) are written as a weighted mix of whole allocations, the pipeline
runs once per allocation, and the values are averaged by weight. Bench seats
get the same treatment within each flex allocation, on the bench rule's
discounted points. As σ goes to 0, B is exactly today's rule.

**Why σ = 0.75.** It is the measured disagreement of the projections near
the flex cutoff: the standard error of the three sources' mean for the 20
players either side of it is 0.5 to 0.93 PPG by setting, about 0.7 typical
(figures, section 1). σ 0.5 leaves 9 cases over 1.0 on main; σ 1.0 is
barely smoother (99th percentile 0.42 against 0.48) and shifts values
further (up to 5.0 points).

**What it changes once.** The split moves toward what the projections can
actually tell apart. The largest one-time change per setting, B σ 0.75:

| Setting | Largest change | Setting | Largest change |
|---|---|---|---|
| standard/10 | Smith-Njigba 48.9 to 50.3 | half_ppr/8 | Lamb 31.7 to 36.2 |
| ppr/12 | Gibbs 75.0 to 73.8 | half_ppr/14 | Gibbs 88.1 to 84.9 |
| USO | Gibbs 88.6 to 85.8 | Charlotte | Gibbs 78.6 to 81.2 |

All 14 are in the figures (section 3, last column); the median is about 1.3.
It matches the expected-starts idea the values already use (ES model): a
player's value is what he is expected to contribute, not a bet that the
projections' current ordering is exact.

**What it costs.** Three to nine pipeline passes per setting at a 0.1% weight
cut (fewer with a coarser cut), in the engine (`vpAllocate` in
`value-model.js`), the Python reference and the spec reference, paired on one
branch with `value_check compare` at 0 and zero rank-guard inversions, per
the value-change rules. A native version (fractional starter and bench
counts inside the lines and group totals) would be one pass but touches more
math. Either is T1 work and a decision record.

## A second step found on the way: chart fill-in membership

The 19 non-flip cases over 1.0 are all one mechanism, at the RB rostered
cutoff in standard 12- and 14-team. When an RB just above Chris Brooks
(standard/14) drops 0.5 to 1 PPG, Brooks enters the VP-2.4 fill-in set (the
top rostered + 1 by mean projection). CBS's chart, which doesn't list him,
then gets an estimated value for him, and his DDF Value goes from 0 to 1.74
(6.97 in CBS Adjusted). Raheim Sanders (standard/12) is the same step the
other way: he holds 1.38 from a CBS estimate and drops to 0 when CJ
Donaldson passes him. The allocation doesn't change in either. It needs its
own ticket: B smooths the rostered count but not who sits in the fill-in
set.

## Limits

- Python reference only. The engine's `vpAllocate` uses the same rule (checked
  by reading it), so the browser flips the same way; the options are prototypes
  in the research script, not in the engine.
- The history replays today's code on each bake's fixture. The site published
  whatever code ran then, so these are the flips today's rule would have
  shown, not the ones readers saw.
- USO and Charlotte are measured at their own roster settings with no league
  loaded. With rosters loaded (PR #1105), the bench comes from real rosters,
  so bench flips go away at the DDF level, but the flex split still comes from
  this rule and still flips.
- One-superflex and 2-QB settings were not swept (the 12-setting grid is
  1-QB). The flex rule is the same there, plus a superflex cutoff with the
  same shape.
- C's real-league shares come from two leagues' W/R/T slots on one day
  (USO: RB 5, WR 6, TE 1; Charlotte: RB 5, WR 5, TE 2). A real version would
  use market data.

## Reproduce

```
python3 tools/research/jeg1286_flex_flips.py --repo . --tag main
python3 tools/research/jeg1286_flex_flips.py --repo <PR #1077 checkout> --git . --tag band --only margins,sweep,history --opts A,B75b
python3 tools/research/jeg1286_report.py docs/research/data/jeg1286_flex_flips_main.json docs/research/data/jeg1286_flex_flips_band.json > docs/research/data/jeg1286_flex_flips.md
```

The main run takes about 30 minutes on 4 cores and writes about 12 MB of JSON,
which is not committed; the figures page is generated from it. The script
first checks that
its own copy of the allocation equals `value_reference.allocate` on every
setting, and stops if not.
