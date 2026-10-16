# Bench share decomposition: why the overall lands near the floor (JEG-549)

Owner ticket: JEG-604. Written 2026-10-12. Script: `tools/bench_research/bench_share_decomposition.py`.

## The puzzle

At 12-team full PPR (convention-based tiers, config params, 2026-10-16):
- Fill-in-only floor: 9.3%
- Recommended bench share: 9.7%
- Plain VORP ceiling: 20.2%
- Gap above the floor: +0.4 percentage points

The overall bench share sits only 0.4pp above the fill-in floor, even though individual bench players derive a large fraction of their value from the start-worthy term. For example, RB31 Cam Skattebo at 11.37 ppg gets 37.5% of his lineup share from the start-worthy probability and only 11.4% from fill-in. Where does the difference go?

## The answer: displacement

When sigma > 0, bench players near the starter line have a probability of performing above it (the start-worthy term). But this also means the marginal starter has a probability of performing below the line. Value flows from the marginal starter to the bench player, roughly dollar-for-dollar.

At ppr/12 with config parameters on settled convention (pie = 2352 units):

| Position | Bench SW gain | Starter displacement | Net SW effect |
|---|---|---|---|
| QB | -1.0 | -5.8 | -6.8 |
| RB | +1.6 | -7.6 | -6.0 |
| WR | +25.1 | -6.6 | +18.5 |
| TE | -0.9 | -0.4 | -1.3 |
| **Total** | **+24.8** | **-20.3** | **+4.5** |

**Displacement absorbs 82% of the gross start-worthy gain.** The bench tier gains 24.8 value units from start-worthy probabilities, but starters lose 20.3 to displacement, leaving a net gain of only 4.5 units on a 2352-unit pie — about 0.2% of total value.

## Why the net is positive but small

Displacement is not perfectly symmetric because:
1. **Bench players close to the line gain more than distant starters lose.** A player just below the starter line has a high P(X > l), so they gain a lot of start-worthy value. The corresponding starter just above the line loses a similar amount. But the starter's total value is larger (they have surplus from being above waivers), so the percentage effect is smaller.
2. **The probability tail is asymmetric.** At sigma > 0, the probability mass above the line for bench players and below it for starters is approximately balanced near the line, but bench players further from the line add small positive contributions that have no matching starter loss.
3. **QB displacement exceeds its gain** because QB bench players are few and far from the line (the QB position has only 1 starter per team, so the line is high).

## For the post: 3-5 sentence explanation

The overall bench share (about 10%) is close to the fill-in-only floor (about 9%) because of displacement. When uncertainty gives a bench player a chance of performing like a starter, that same uncertainty means the marginal starter might perform like a bench player. The marginal starter loses nearly as much value from this downside as the bench player gains from the upside. Across all positions, displacement absorbs about 82% of the gross start-worthy value, leaving only a small net effect. This is why the model's bench share is insensitive to sigma (the spread parameter): doubling sigma moves the overall from 9.3% to only 10.7%.

## Bench player examples (ESPN, ppr/12)

Run: `python3 tools/bench_research/bench_share_decomposition.py --setting ppr/12`

| Player | Pos | Rank | PPG | Lineup share | Start-worthy | Fill-in | Fill-in-only share |
|---|---|---|---|---|---|---|---|
| J.K. Dobbins | RB | 30 | 11.51 | 50.0% | 38.9% | 11.1% | 29.8% |
| Cam Skattebo | RB | 31 | 11.37 | 48.9% | 37.5% | 11.4% | 29.8% |
| David Montgomery | RB | 32 | 11.31 | 48.4% | 36.9% | 11.6% | 29.8% |
| Omarion Hampton | RB | 34 | 10.28 | 39.5% | 25.6% | 13.8% | 29.8% |
| Deebo Samuel Sr. | WR | 32 | 11.40 | 49.7% | 39.2% | 10.4% | 37.6% |
| Jordan Addison | WR | 33 | 10.97 | 44.6% | 33.3% | 11.3% | 37.6% |
| Stefon Diggs | WR | 34 | 10.92 | 44.0% | 32.6% | 11.4% | 37.6% |
| Juwan Johnson | TE | 13 | 10.06 | 39.2% | 37.6% | 1.5% | 17.0% |

Note: the fill-in-only share is constant within a position because with sigma = 0 and the same band structure, every player in the same depth band gets the same fill probability. The variation in the full model comes entirely from the start-worthy term.

## Pre-convention numbers (for reference)

Previous run on pre-convention tiers (2026-10-12): fill-in floor 8.3%, recommended 8.8%, VORP ceiling 13.4% at ppr/12. Displacement absorbed 83% of the gross start-worthy gain. The mechanism is unchanged; the convention shifted tier boundaries, increasing both the floor and the ceiling.
