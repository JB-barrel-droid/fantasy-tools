# Bench-share bounds reconciliation (JEG-548)

Owner ticket: JEG-604. Written 2026-10-12. Script: `tools/bench_research/bench_share_bounds.py`.

## The discrepancy

Two documents quote different bench-share bounds at 12-team full PPR:

| Source | Fill-in floor | Plain VORP ceiling |
|---|---|---|
| Approved-defaults log (JEG-533, 2026-10-09) | 8.6% | 13.3% |
| Methodology ES-7 sensitivity text | 8.1% | 13.1% |

## Why they differ

The two sets of numbers come from **two different parameter sets**, not a bug:

| Parameter | Approved defaults (recent/5-year) | Eleven-season (all) |
|---|---|---|
| QB m | 11.8% | 11.0% |
| RB m | 14.4% | 15.3% |
| WR m | 11.8% | 11.7% |
| TE m | 15.1% | 14.4% |
| bye share | 7.8% | 7.2% |
| QB sigma | 14.9% | 18.2% |
| RB sigma | 27.7% | 30.0% |
| WR sigma | 21.6% | 30.8% |
| TE sigma | 19.6% | 36.2% |

The fill-in floor depends on m and bye (not sigma, which is set to zero). A higher bye share (7.8% vs 7.2%) gives more fill-in opportunities, raising the floor from 8.1% to 8.6%. The plain VORP ceiling also shifts slightly because waiver lines move with the data.

The methodology ES-7 sensitivity paragraph (line 786) quotes the eleven-session run's bounds. The approved-defaults log sensitivity table quotes the approved-defaults run's bounds. Neither is wrong; they are from different runs. The approved-defaults numbers (8.6% / 13.3%) are the authoritative figures at the approved defaults.

## Which is correct at the approved defaults

The approved-defaults log: **8.6% / 13.3%**. The methodology ES-7 text should cite these, not the eleven-session run. However, both numbers are stale because:

1. The Razzball fix (JEG-555/593) changed the underlying data.
2. JEG-562 will move tier definitions to the roster convention.

On current data (post-Razzball fix, pre-convention), both parameter sets produce approximately the same bounds because the data changed more than the parameters:

| Setting | Fill-in floor (recent) | Fill-in floor (all) | Ceiling (recent) | Ceiling (all) |
|---|---|---|---|---|
| ppr/12 | 8.3% | 8.3% | 13.4% | 13.4% |

## Step-by-step calculation of each bound (12-team full PPR)

### Inputs

- Roster: 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 6 bench (D'Hondt bench allocation: QB 1, RB 2, WR 3, TE 1).
- Sources: three projections (ESPN, CBS ROS, Razzball) and four charts (FantasyCalc, USA Today, FantasyPros, CBS).
- Tiers: order players by mean projected points per game; starter tier = top S players, bench tier = next B players, waiver tier = rest. S and B are set by the roster allocation across 12 teams.

### Lower bound: fill-in only (sigma = 0)

When sigma = 0, no player has a probability of performing above the starter line. Bench players earn value only when filling in for a missing starter.

1. **Availability.** For each position, `avail = (1 - bye) x (1 - m)`.
   - At approved defaults: QB avail = (1 - 0.078) x (1 - 0.118) = 0.814; RB = 0.790; WR = 0.814; TE = 0.783.
2. **Fill-in probability.** The probability that at least k starters are unavailable, where k is the bench player's depth. At depth 1 (first backup): `fill_1 = P(Binom(n, q) >= 1) = 1 - (1 - q)^n`, where n = starters per team and q = bye + (1 - bye) x m.
   - RB at 12 teams: n = 3 (2 dedicated + typically 1 flex), q = 0.078 + 0.922 x 0.144 = 0.211.  fill_1 = 1 - (0.789)^3 = 50.9%.
3. **Fill-in value.** For a bench player at projected value x: `value = avail x (x - w) x fill_k`, where w is the waiver line (value of the first player past the roster).
4. **Aggregate.** The bench tier's total value divided by the pie gives the bench-share floor.

With sigma = 0 every bench player's value is a simple product of surplus, availability, and fill-in probability. No uncertainty, no start-worthy term.

### Upper bound: plain value above waivers

Every point above the waiver line counts. No missed games (m = 0), no byes (bye = 0), no lineup probability: `value = x - w`.

1. For each source, compute VORP: `value_i = max(0, x_i - w_p)`.
2. Scale to the pie: `adjusted_i = value_i x pie / sum(all values)`.
3. Blend across sources (DDF mean).
4. The bench tier's share of the total is the ceiling.

This is what bench share would be if bench players started every week and never missed games.

## Both bounds, all 12 settings (pre-convention, approved-defaults parameters)

Run: `python3 tools/bench_research/bench_share_bounds.py --from-log --params recent`

| Setting | Fill-in floor | Recommended | Plain VORP ceiling | Gap (rec - floor) |
|---|---|---|---|---|
| standard/8 | 10.0% | 10.0% | 14.8% | +0.1pp |
| standard/10 | 8.9% | 9.2% | 13.7% | +0.3pp |
| standard/12 | 7.8% | 8.1% | 12.7% | +0.4pp |
| standard/14 | 7.4% | 7.9% | 13.2% | +0.6pp |
| half_ppr/8 | 9.6% | 9.9% | 14.6% | +0.4pp |
| half_ppr/10 | 8.7% | 9.2% | 13.7% | +0.4pp |
| half_ppr/12 | 7.9% | 8.2% | 12.8% | +0.3pp |
| half_ppr/14 | 7.5% | 8.2% | 13.4% | +0.8pp |
| ppr/8 | 9.2% | 9.6% | 14.1% | +0.3pp |
| ppr/10 | 9.1% | 9.5% | 14.0% | +0.4pp |
| ppr/12 | 8.3% | 8.8% | 13.4% | +0.5pp |
| ppr/14 | 8.0% | 8.7% | 13.8% | +0.7pp |

## Final bounds on settled convention (2026-10-16)

After JEG-562 (expected starts on convention), JEG-563 (default roster 2 WR / 7
bench / K / DEF), and JEG-630 (JS engine parity), re-run on current config
parameters. The convention changes tier definitions (waiver line = first player
past market-bench rosters; starter line = midpoint of last starter and first
non-starter), which shifts the bench tier boundaries. Default roster is 1 QB /
2 RB / 2 WR / 1 TE / 1 FLEX / K / DEF, 7 bench.

Run: `python3 tools/bench_research/bench_share_bounds.py` (config params)

| Setting | Fill-in floor | Recommended | Plain VORP ceiling | Gap (rec - floor) |
|---|---|---|---|---|
| standard/8 | 11.7% | 11.5% | 21.6% | -0.1pp |
| standard/10 | 10.1% | 9.9% | 21.2% | -0.3pp |
| standard/12 | 8.6% | 8.8% | 20.8% | +0.2pp |
| standard/14 | 8.5% | 9.0% | 20.0% | +0.5pp |
| half_ppr/8 | 12.2% | 12.2% | 21.7% | +0.0pp |
| half_ppr/10 | 10.2% | 10.4% | 20.2% | +0.1pp |
| half_ppr/12 | 9.0% | 9.3% | 19.5% | +0.4pp |
| half_ppr/14 | 8.2% | 8.6% | 19.0% | +0.4pp |
| ppr/8 | 9.6% | 9.8% | 19.0% | +0.2pp |
| ppr/10 | 9.8% | 10.1% | 20.4% | +0.3pp |
| ppr/12 | 9.3% | 9.7% | 20.2% | +0.4pp |
| ppr/14 | 8.5% | 8.7% | 19.9% | +0.3pp |

Key changes from the convention: the VORP ceiling rose (more bench players in
the tier with 7 bench and the convention's D'Hondt allocation), while
the fill-in floor and recommended share rose modestly (about +1pp at ppr/12).
The recommended bench share at ppr/12 is now **9.7%** (was 8.8% pre-convention).

Per-position bounds at ppr/12:

| Position | Fill-in floor | Recommended | Plain VORP | Start-worthy share of gap |
|---|---|---|---|---|
| QB | 6.9% | 6.4% | 9.0% | -24% |
| RB | 7.5% | 7.4% | 14.5% | -2% |
| WR | 11.7% | 12.8% | 27.2% | 7% |
| TE | 2.8% | 2.6% | 2.9% | -149% |
| Overall | 9.3% | 9.7% | 20.2% | 4% |

Commit: on main at the build tag after JEG-562/563/630 merged.
