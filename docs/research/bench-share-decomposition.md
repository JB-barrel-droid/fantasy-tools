# Bench share decomposition: why the overall lands near the floor (JEG-549)

Owner ticket: JEG-604. Written 2026-10-12. Script: `tools/bench_research/bench_share_decomposition.py`.

## The puzzle

At 12-team full PPR (approved defaults, current data):
- Fill-in-only floor: 8.3%
- Recommended bench share: 8.8%
- Plain VORP ceiling: 13.4%
- Gap above the floor: +0.5 percentage points

The overall bench share sits only 0.5pp above the fill-in floor, even though individual bench players derive a large fraction of their value from the start-worthy term. For example, RB33 Jordan Mason at 9.58 ppg gets 39.4% of his surplus from the start-worthy probability and only 13.6% from fill-in. Where does the difference go?

## The answer: displacement

When sigma > 0, bench players near the starter line have a probability of performing above it (the start-worthy term). But this also means the marginal starter has a probability of performing below the line. Value flows from the marginal starter to the bench player, roughly dollar-for-dollar.

At ppr/12 with approved-defaults parameters:

| Position | Bench SW gain | Starter displacement | Net SW effect |
|---|---|---|---|
| QB | -0.1 | -7.6 | -7.7 |
| RB | +8.8 | -5.8 | +3.1 |
| WR | +9.3 | -1.2 | +8.1 |
| TE | +2.0 | -2.1 | -0.0 |
| **Total** | **+20.1** | **-16.6** | **+3.5** |

**Displacement absorbs 83% of the gross start-worthy gain.** The bench tier gains 20.1 value units from start-worthy probabilities, but starters lose 16.6 to displacement, leaving a net gain of only 3.5 units on a 2688-unit pie — about 0.1% of total value.

## Why the net is positive but small

Displacement is not perfectly symmetric because:
1. **Bench players close to the line gain more than distant starters lose.** A player just below the starter line has a high P(X > l), so they gain a lot of start-worthy value. The corresponding starter just above the line loses a similar amount. But the starter's total value is larger (they have surplus from being above waivers), so the percentage effect is smaller.
2. **The probability tail is asymmetric.** At sigma > 0, the probability mass above the line for bench players and below it for starters is approximately balanced near the line, but bench players further from the line add small positive contributions that have no matching starter loss.
3. **QB displacement exceeds its gain** because QB bench players are few and far from the line (the QB position has only 1 starter per team, so the line is high).

## For the post: 3-5 sentence explanation

The overall bench share (about 9%) is close to the fill-in-only floor (about 8%) because of displacement. When uncertainty gives a bench player a chance of performing like a starter, that same uncertainty means the marginal starter might perform like a bench player. The marginal starter loses nearly as much value from this downside as the bench player gains from the upside. Across all positions, displacement absorbs about 83% of the gross start-worthy value, leaving only a small net effect. This is why the model's bench share is insensitive to sigma (the spread parameter): doubling sigma moves the overall from 8.3% to only 8.9%.

## Bench player examples (ESPN, ppr/12)

Run: `python3 tools/bench_research/bench_share_decomposition.py --setting ppr/12`

| Player | Pos | Rank | PPG | Lineup share | Start-worthy | Fill-in | Fill-in-only share |
|---|---|---|---|---|---|---|---|
| Jordan Mason | RB | 33 | 9.58 | 53.1% | 39.4% | 13.6% | 40.2% |
| Jadarian Price | RB | 35 | 9.46 | 52.0% | 37.9% | 14.1% | 40.2% |
| Tyjae Spears | RB | 36 | 8.52 | 42.8% | 25.7% | 17.0% | 40.2% |
| Blake Corum | RB | 38 | 8.25 | 39.8% | 22.1% | 17.7% | 40.2% |
| Khalil Shakir | WR | 40 | 9.87 | 49.2% | 40.7% | 8.6% | 37.6% |
| Xavier Worthy | WR | 41 | 9.80 | 48.3% | 39.6% | 8.7% | 37.6% |
| Romeo Doubs | WR | 43 | 9.61 | 45.7% | 36.6% | 9.1% | 37.6% |

Note: the fill-in-only share is constant within a position because with sigma = 0 and the same band structure, every player in the same depth band gets the same fill probability. The variation in the full model comes entirely from the start-worthy term.

## What changes after JEG-562

JEG-562 moves tiers to the convention (starter line = midpoint of last starter and first non-starter). This shifts which players are marginal starters and changes the displacement balance. The displacement fraction (currently 83%) may change, but the mechanism — and the explanation for why the overall sits near the floor — will not.
