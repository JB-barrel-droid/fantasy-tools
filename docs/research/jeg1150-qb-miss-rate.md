# QB miss_rate alternatives (JEG-1150)

Research only, written 2026-10-29 for Jeremy's decision. Nothing in the live model, `config/` or the rates changed.

- **Script:** `tools/research/jeg1150_qb_miss_rate.py` (patches `roster_convention._BENCH_MISS_RATE["QB"]` in memory per run, then runs the Python reference `value_reference.compute`).
- **Figures:** [data/jeg1150_qb_miss_rate.json](data/jeg1150_qb_miss_rate.json).
- **Inputs:** `data/fixtures/current` (as of 2026-10-29), main at `5c07ad6`. Values are DDF Value on the Adjusted tab, default roster (1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 7 bench).
- **JS twin:** `app/trade-value-chart/assets/value-model.js` (JEG-1121 stable block) uses the same constants and formula; it was not run separately because nothing ships.

## Recommendation

Keep QB miss_rate at 0.12 (no change). Jeremy's league is not lighter on QBs than the model; it is slightly heavier. His 7 of 66 bench seats is 10.6%; the model's 8 of 84 is 9.5%. Scaled to 84 seats his league holds about 8.9 QBs, so 8 is the closest count the method can give. Lowering the rate moves away from his league, and 0.09 changes nothing at 12 teams.

## Why the count moves in steps

Bench seats go to the highest PPG × discount, where backup k at a position is discounted by c^(1 + floor(k / t1)), c = starters per team × (1/17 + miss_rate) and t1 = round(2 × c × teams). After t1 backups the discount squares (QB: 0.18 to 0.03), so QB seats land in blocks of t1. At 12 teams t1 is 3 at 0.06, 4 at 0.09 and 0.12, and 5 at 0.15, giving 6, 8, 8 and 10 QB seats. A count of 7 is not reachable by changing miss_rate alone; it would need a change to the tier rule, which is out of scope here.

## Bench seats by position, standard, 12 teams (84 seats)

| QB miss_rate | QB | RB | WR | TE | QB share |
|---|---|---|---|---|---|
| 0.06 | 6 | 42 | 27 | 9 | 7.1% |
| 0.09 | 8 | 42 | 27 | 7 | 9.5% |
| **0.12 (live)** | **8** | **42** | **27** | **7** | **9.5%** |
| 0.15 | 10 | 42 | 27 | 5 | 11.9% |
| Jeremy's league (66 seats) | 7 | 30 | 23 | 6 | 10.6% |

QB seats trade only with TE at this setting; RB and WR seats don't move.

## Other settings (QB bench seats)

| Setting | 0.06 | 0.09 | 0.12 (live) | 0.15 |
|---|---|---|---|---|
| standard 8 / 10 / 12 / 14 | 2 / 3 / 6 / 6 | 3 / 6 / 8 / 8 | 6 / 8 / 8 / 10 | 6 / 8 / 10 / 12 |
| half PPR 8 / 10 / 12 / 14 | 2 / 2 / 6 / 6 | 3 / 6 / 8 / 8 | 6 / 8 / 8 / 10 | 6 / 8 / 10 / 12 |
| PPR 8 / 10 / 12 / 14 | 2 / 2 / 3 / 3 | 3 / 6 / 8 / 8 | 6 / 8 / 8 / 10 | 6 / 8 / 10 / 12 |

0.09 is identical to live at 12 teams but cuts QB seats at 8, 10 and 14 teams. 0.06 leaves only 3 QB backups in a 12- or 14-team PPR league.

## Values, standard, 12 teams (DDF Value, absolute)

0.09 gives exactly the live values, so it is left out.

| Player | Tier (live) | 0.06 | 0.12 (live) | 0.15 |
|---|---|---|---|---|
| Josh Allen, QB1 | starter | 32.09 | 33.95 | 36.98 |
| Drake Maye, QB2 | starter | 20.80 | 22.20 | 24.32 |
| Patrick Mahomes, QB12 | last starter | 4.30 | 4.75 | 5.42 |
| Matthew Stafford, QB13 | first bench | 3.58 | 3.97 | 4.52 |
| Jahmyr Gibbs, RB1 | starter | 88.98 | 88.63 | 88.53 |
| Braelon Allen, RB34 | last starter | 10.28 | 10.23 | 10.22 |
| Aaron Jones, RB35 | first bench | 10.27 | 10.23 | 10.21 |
| Jaxon Smith-Njigba, WR1 | starter | 55.53 | 55.37 | 55.42 |
| Emeka Egbuka, WR26 | last starter | 7.83 | 7.81 | 7.82 |
| Rashee Rice, WR27 | first bench | 7.21 | 7.19 | 7.20 |
| Brock Bowers, TE1 | starter | 27.61 | 27.02 | 25.79 |
| Trey McBride, TE2 | starter | 24.47 | 23.92 | 22.57 |
| Harold Fannin Jr., TE12 | last starter | 3.64 | 3.42 | 2.45 |
| Dallas Goedert, TE13 | first bench | 3.33 | 3.12 | 2.17 |

Position totals (starter tier / bench tier):

| Position | 0.06 | 0.12 (live) | 0.15 |
|---|---|---|---|
| QB | 158.9 / 9.3 | 170.4 / 10.7 | 187.9 / 12.8 |
| RB | 1241.7 / 102.5 | 1236.7 / 102.0 | 1235.3 / 101.8 |
| WR | 625.2 / 62.9 | 623.4 / 62.7 | 624.0 / 62.8 |
| TE | 137.1 / 14.0 | 132.8 / 12.6 | 118.9 / 8.0 |

The biggest single move is Josh Allen: down 1.86 at 0.06, up 3.04 at 0.15. Value follows the seats: QB and TE swap value, RB and WR move by under 0.4 per player. The overall bench share barely moves (7.03% in every case).

## Options for Jeremy

- **A (recommended):** keep 0.12 and close JEG-1150 with no change. It is the closest fit to his league's QB share.
- **B:** 0.06. QB 6 / TE 9 at 12 teams; QB starter value falls 7% (Allen 33.95 to 32.09); PPR 12 and 14 teams drop to 3 QB backups.
- **C:** 0.15. QB 10 / TE 5; QB starter value rises 10% (Allen to 36.98) and TE values fall (Bowers 27.02 to 25.79, Fannin 3.42 to 2.45).

Any change ships as a value change: Python reference, spec reference and JS on one branch, `value_check compare` at 0, rank guard at 0, and a before/after table on live data.
