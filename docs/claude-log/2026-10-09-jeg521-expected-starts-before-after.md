# Expected-starts value: before and after, all 12 settings

Produced by `pipelines/expected_starts_model.py` on the Week 5 build. Before = today's live values (two-tier at the 15% bench share, ESPN anchored), scaled to the fixed pie. After A = expected-starts replaces the slices (ES-4 to ES-6). After B = slices kept, bench budget set from A. Bench-tier share = the pie held by players ranked past the starters on the mean projection. Price ratio = median value per point above waivers, starters over bench tier.

Parameters: QB m 11.0%, sigma 18.2%, floor 0.69; RB m 15.3%, sigma 30.0%, floor 0.89; WR m 11.7%, sigma 30.8%, floor 1.01; TE m 14.4%, sigma 36.2%, floor 0.64; bye share 7.2%.

## Bench-tier share and starter/bench price, per setting

| Setting | Variant | QB bench | RB bench | WR bench | TE bench | Overall | Fill-state share | QB price | RB price | WR price | TE price | Inversions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| standard/8 | before | 19.0% | 10.0% | 18.0% | 17.7% | 13.8% | n/a | 1.0x | 1.6x | 0.7x | 1.0x | n/a |
| standard/8 | after A | 16.4% | 6.5% | 11.7% | 14.5% | 9.6% | 5.8% | 1.2x | 2.8x | 1.7x | 1.2x | 0 |
| standard/8 | after A-option | 20.5% | 9.0% | 16.4% | 19.4% | 13.7% | 3.8% | 0.8x | 1.6x | 0.9x | 0.8x | 0 |
| standard/8 | after B | 16.0% | 6.0% | 11.1% | 13.9% | 9.2% | n/a | 1.2x | 2.4x | 1.3x | 1.2x | 0 |
| standard/10 | before | 17.4% | 12.7% | 16.5% | 17.1% | 14.5% | n/a | 1.0x | 1.0x | 0.9x | 1.1x | n/a |
| standard/10 | after A | 14.1% | 7.8% | 10.2% | 13.3% | 9.5% | 6.1% | 1.2x | 2.0x | 2.3x | 1.4x | 0 |
| standard/10 | after A-option | 18.2% | 9.9% | 14.5% | 17.6% | 13.0% | 3.8% | 0.9x | 1.4x | 1.2x | 0.9x | 0 |
| standard/10 | after B | 14.1% | 7.2% | 9.8% | 13.2% | 9.1% | n/a | 1.2x | 1.9x | 2.1x | 1.5x | 0 |
| standard/12 | before | 19.8% | 12.2% | 15.1% | 15.3% | 14.0% | n/a | 1.4x | 1.1x | 1.1x | 0.8x | n/a |
| standard/12 | after A | 16.1% | 6.8% | 7.7% | 10.0% | 8.0% | 5.2% | 2.3x | 2.2x | 2.7x | 1.5x | 0 |
| standard/12 | after A-option | 19.8% | 8.5% | 11.3% | 14.8% | 11.1% | 3.2% | 1.5x | 1.8x | 1.5x | 0.7x | 0 |
| standard/12 | after B | 15.7% | 5.8% | 7.5% | 9.2% | 7.5% | n/a | 2.2x | 2.4x | 2.6x | 1.6x | 0 |
| standard/14 | before | 16.9% | 13.3% | 16.1% | 15.0% | 14.7% | n/a | 1.1x | 0.9x | 0.8x | 0.7x | n/a |
| standard/14 | after A | 14.2% | 7.6% | 7.9% | 9.1% | 8.3% | 5.1% | 2.1x | 1.9x | 1.9x | 1.6x | 0 |
| standard/14 | after A-option | 17.3% | 8.9% | 10.8% | 14.5% | 10.8% | 3.2% | 1.2x | 1.6x | 1.3x | 0.7x | 0 |
| standard/14 | after B | 12.6% | 6.9% | 6.7% | 8.6% | 7.4% | n/a | 2.3x | 2.1x | 2.3x | 1.7x | 0 |
| half_ppr/8 | before | 19.2% | 9.8% | 18.1% | 17.7% | 14.0% | n/a | 1.0x | 1.7x | 0.8x | 1.0x | n/a |
| half_ppr/8 | after A | 16.4% | 6.1% | 11.9% | 14.3% | 9.6% | 5.5% | 1.2x | 3.5x | 1.7x | 1.2x | 0 |
| half_ppr/8 | after A-option | 20.5% | 8.7% | 16.6% | 19.6% | 13.8% | 3.6% | 0.8x | 1.8x | 1.0x | 0.9x | 0 |
| half_ppr/8 | after B | 16.0% | 5.6% | 11.2% | 14.1% | 9.2% | n/a | 1.2x | 3.4x | 1.5x | 1.2x | 0 |
| half_ppr/10 | before | 17.2% | 10.8% | 17.8% | 17.2% | 14.2% | n/a | 1.0x | 1.2x | 0.8x | 1.1x | n/a |
| half_ppr/10 | after A | 14.1% | 7.0% | 10.8% | 13.4% | 9.4% | 5.8% | 1.2x | 2.1x | 1.9x | 1.3x | 0 |
| half_ppr/10 | after A-option | 18.2% | 9.2% | 15.0% | 17.5% | 12.9% | 3.6% | 0.9x | 1.6x | 1.1x | 1.1x | 0 |
| half_ppr/10 | after B | 14.1% | 6.6% | 10.3% | 13.0% | 9.0% | n/a | 1.2x | 2.0x | 2.0x | 1.4x | 0 |
| half_ppr/12 | before | 19.8% | 10.6% | 17.1% | 17.0% | 14.1% | n/a | 1.5x | 1.3x | 1.0x | 0.8x | n/a |
| half_ppr/12 | after A | 16.1% | 6.3% | 8.4% | 12.1% | 8.2% | 5.1% | 2.2x | 2.5x | 2.4x | 1.1x | 0 |
| half_ppr/12 | after A-option | 20.0% | 8.0% | 12.2% | 17.8% | 11.5% | 3.0% | 1.5x | 1.9x | 1.4x | 0.6x | 0 |
| half_ppr/12 | after B | 15.8% | 6.3% | 8.5% | 11.8% | 8.3% | n/a | 2.1x | 2.3x | 2.2x | 1.3x | 0 |
| half_ppr/14 | before | 16.8% | 12.6% | 16.0% | 14.9% | 14.5% | n/a | 1.1x | 1.2x | 0.8x | 0.7x | n/a |
| half_ppr/14 | after A | 14.2% | 8.2% | 7.1% | 9.5% | 8.3% | 5.2% | 2.1x | 1.9x | 2.1x | 1.3x | 0 |
| half_ppr/14 | after A-option | 17.3% | 9.8% | 9.8% | 14.8% | 10.9% | 3.1% | 1.2x | 1.6x | 1.3x | 0.6x | 0 |
| half_ppr/14 | after B | 12.6% | 7.5% | 6.0% | 8.9% | 7.4% | n/a | 2.3x | 2.2x | 2.2x | 1.4x | 0 |
| ppr/8 | before | 19.1% | 11.3% | 16.7% | 17.6% | 14.5% | n/a | 1.0x | 1.6x | 0.9x | 1.0x | n/a |
| ppr/8 | after A | 16.4% | 8.3% | 10.0% | 14.7% | 9.9% | 5.5% | 1.2x | 2.8x | 1.6x | 1.1x | 0 |
| ppr/8 | after A-option | 20.5% | 11.2% | 14.3% | 19.8% | 14.1% | 3.7% | 0.8x | 1.5x | 1.0x | 0.9x | 0 |
| ppr/8 | after B | 16.1% | 7.8% | 9.4% | 14.0% | 9.5% | n/a | 1.2x | 2.7x | 1.7x | 1.2x | 0 |
| ppr/10 | before | 17.2% | 11.3% | 16.6% | 15.5% | 14.0% | n/a | 1.0x | 1.5x | 0.8x | 1.9x | n/a |
| ppr/10 | after A | 14.1% | 8.0% | 8.2% | 11.8% | 8.7% | 5.6% | 1.2x | 2.5x | 2.4x | 2.2x | 0 |
| ppr/10 | after A-option | 18.2% | 10.6% | 12.3% | 17.0% | 12.4% | 3.5% | 0.9x | 1.7x | 1.3x | 0.9x | 0 |
| ppr/10 | after B | 14.1% | 7.5% | 8.0% | 11.3% | 8.5% | n/a | 1.2x | 2.3x | 2.2x | 2.4x | 0 |
| ppr/12 | before | 19.8% | 12.8% | 15.7% | 16.8% | 14.8% | n/a | 1.5x | 1.0x | 1.0x | 0.8x | n/a |
| ppr/12 | after A | 16.1% | 9.3% | 6.4% | 12.5% | 8.6% | 5.3% | 2.2x | 1.6x | 2.9x | 1.4x | 0 |
| ppr/12 | after A-option | 20.0% | 11.6% | 9.7% | 18.3% | 12.0% | 3.1% | 1.5x | 1.2x | 1.7x | 0.7x | 0 |
| ppr/12 | after B | 15.8% | 9.0% | 6.4% | 13.1% | 8.6% | n/a | 2.1x | 1.6x | 2.7x | 1.3x | 0 |
| ppr/14 | before | 16.8% | 12.9% | 14.2% | 17.1% | 14.1% | n/a | 1.2x | 1.2x | 0.8x | 0.6x | n/a |
| ppr/14 | after A | 14.2% | 8.2% | 6.8% | 10.6% | 8.2% | 5.0% | 2.1x | 2.0x | 2.0x | 1.1x | 0 |
| ppr/14 | after A-option | 17.3% | 9.9% | 9.5% | 15.3% | 10.8% | 3.0% | 1.2x | 1.6x | 1.3x | 0.7x | 0 |
| ppr/14 | after B | 12.6% | 7.7% | 5.8% | 9.6% | 7.4% | n/a | 2.3x | 2.3x | 2.1x | 1.2x | 0 |

## Position shares of the pie (blended DDF Value)

| Setting | QB before | QB after A | RB before | RB after A | WR before | WR after A | TE before | TE after A |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| standard/8 | 7.8% | 6.5% | 53.4% | 49.4% | 32.0% | 37.8% | 6.8% | 6.3% |
| standard/10 | 7.0% | 6.8% | 54.3% | 50.4% | 32.4% | 36.8% | 6.3% | 6.1% |
| standard/12 | 9.1% | 7.2% | 52.5% | 48.7% | 32.1% | 37.7% | 6.2% | 6.5% |
| standard/14 | 10.4% | 7.5% | 51.8% | 47.7% | 31.9% | 38.5% | 5.9% | 6.3% |
| half_ppr/8 | 7.0% | 6.1% | 50.9% | 47.3% | 34.8% | 39.8% | 7.3% | 6.8% |
| half_ppr/10 | 6.0% | 6.4% | 51.1% | 47.9% | 36.0% | 39.3% | 6.8% | 6.4% |
| half_ppr/12 | 8.1% | 6.6% | 48.7% | 46.1% | 36.4% | 40.7% | 6.8% | 6.6% |
| half_ppr/14 | 9.1% | 7.0% | 46.3% | 44.5% | 37.4% | 41.8% | 7.1% | 6.7% |
| ppr/8 | 6.1% | 5.8% | 44.9% | 44.6% | 41.1% | 42.4% | 7.8% | 7.2% |
| ppr/10 | 5.4% | 6.0% | 47.1% | 45.2% | 39.7% | 42.1% | 7.9% | 6.6% |
| ppr/12 | 7.0% | 6.2% | 42.0% | 42.9% | 43.6% | 44.0% | 7.4% | 6.9% |
| ppr/14 | 8.1% | 6.6% | 41.9% | 41.9% | 41.0% | 44.1% | 9.0% | 7.4% |

## Sensitivity at 12-team full PPR (option A)

| Case | QB bench | RB bench | WR bench | TE bench | Overall | Fill-state share | QB price | RB price | WR price | TE price | RB top-12 share | WR top-12 share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| recommended (share form) | 16.1% | 9.3% | 6.4% | 12.5% | 8.6% | 5.3% | 2.2x | 1.6x | 2.9x | 1.4x | 56.1% | 48.5% |
| recommended, convex option form | 20.0% | 11.6% | 9.7% | 18.3% | 12.0% | 3.1% | 1.5x | 1.2x | 1.7x | 0.7x | 52.8% | 43.9% |
| convex option form, sigma x 0.5 | 18.4% | 10.3% | 7.8% | 16.3% | 10.3% | 3.4% | 1.8x | 1.6x | 2.3x | 0.9x | 53.8% | 45.4% |
| m x 0.5 | 16.0% | 8.7% | 6.0% | 12.4% | 8.2% | 3.8% | 2.3x | 1.8x | 3.0x | 1.4x | 56.9% | 49.0% |
| m x 0.75 | 16.1% | 9.0% | 6.2% | 12.5% | 8.4% | 4.6% | 2.3x | 1.7x | 2.9x | 1.4x | 56.5% | 48.8% |
| m x 1.25 | 16.2% | 9.5% | 6.6% | 12.6% | 8.8% | 6.0% | 2.2x | 1.5x | 2.7x | 1.4x | 55.7% | 48.2% |
| m x 1.5 | 16.2% | 9.8% | 6.8% | 12.6% | 9.0% | 6.7% | 2.2x | 1.5x | 2.6x | 1.4x | 55.4% | 48.0% |
| sigma x 0.0 | 16.0% | 8.8% | 5.8% | 11.6% | 8.1% | 4.8% | 2.1x | 1.8x | 3.0x | 2.4x | 55.5% | 47.6% |
| sigma x 0.25 | 16.0% | 8.9% | 5.7% | 12.3% | 8.2% | 4.8% | 2.3x | 1.7x | 3.2x | 1.6x | 55.5% | 47.7% |
| sigma x 0.5 | 15.8% | 8.9% | 5.9% | 12.2% | 8.3% | 5.0% | 2.3x | 1.8x | 3.1x | 1.5x | 55.8% | 48.1% |
| sigma x 0.75 | 15.9% | 9.1% | 6.1% | 12.3% | 8.4% | 5.2% | 2.3x | 1.7x | 3.0x | 1.5x | 56.0% | 48.4% |
| sigma x 1.25 | 16.3% | 9.5% | 6.6% | 12.7% | 8.9% | 5.3% | 2.2x | 1.5x | 2.7x | 1.3x | 56.0% | 48.4% |
| sigma x 1.5 | 16.5% | 9.6% | 6.8% | 12.8% | 9.1% | 5.2% | 2.2x | 1.5x | 2.6x | 1.3x | 55.9% | 48.3% |
| first-pass assumptions (m QB 11 RB 17 WR 14 TE 13, sigma 25%) | 16.4% | 9.5% | 6.2% | 12.3% | 8.7% | 4.9% | 2.3x | 1.6x | 3.1x | 1.6x | 55.4% | 47.6% |
| lower bound: fill-in only (sigma 0) | 16.0% | 8.8% | 5.8% | 11.6% | 8.1% | 4.8% | 2.1x | 1.8x | 3.0x | 2.4x | 55.5% | 47.6% |
| upper bound: plain value above waivers (bench starts every week) | 18.8% | 13.5% | 11.3% | 15.1% | 13.1% | n/a | 1.6x | 1.0x | 1.4x | 1.1x | 50.8% | 43.0% |
| before (today) | 19.8% | 12.8% | 15.7% | 16.8% | 14.8% | n/a | 1.5x | 1.0x | 1.0x | 0.8x | 52.0% | 39.2% |

## Expected lineup share of a player's surplus (ESPN, 12-team full PPR, option A)

| Position | Rank | Player | Points per game | sigma (ppg) | Lineup share of surplus | Start-worthy part |
| --- | --- | --- | --- | --- | --- | --- |
| QB | 1 | Josh Allen | 23.84 | 4.35 | 72.8% | 71.8% |
| QB | 7 | Tyler Shough | 20.45 | 3.73 | 56.6% | 54.2% |
| QB | 12 | Dak Prescott | 19.49 | 3.55 | 49.1% | 46.2% |
| QB | 13 | Jared Goff | 18.95 | 3.45 | 44.3% | 41.3% |
| QB | 18 | Jordan Love | 18.11 | 3.3 | 36.3% | 33.0% |
| RB | 1 | Jahmyr Gibbs | 25.71 | 7.72 | 77.4% | 76.8% |
| RB | 16 | Chuba Hubbard | 14.5 | 4.35 | 70.1% | 65.2% |
| RB | 31 | Josh Jacobs | 10.43 | 3.13 | 53.6% | 40.1% |
| RB | 32 | Jordan Mason | 10.35 | 3.11 | 53.0% | 39.3% |
| RB | 37 | Alvin Kamara | 8.5 | 2.55 | 36.9% | 18.4% |
| RB | 44 | Keaton Mitchell | 7.69 | 2.31 | 28.6% | 9.8% |
| WR | 1 | Ja'Marr Chase | 21.25 | 6.54 | 78.8% | 78.0% |
| WR | 21 | Carnell Tate | 13.77 | 4.24 | 68.5% | 64.5% |
| WR | 41 | Adonai Mitchell | 10.4 | 3.2 | 49.5% | 41.0% |
| WR | 42 | Jameson Williams | 10.4 | 3.2 | 49.5% | 41.0% |
| WR | 47 | Xavier Worthy | 9.84 | 3.03 | 44.3% | 35.0% |
| WR | 54 | Ryan Flournoy | 8.67 | 2.67 | 31.6% | 21.2% |
| TE | 1 | Trey McBride | 17.16 | 6.21 | 70.5% | 69.6% |
| TE | 7 | Tyler Warren | 11.8 | 4.27 | 55.4% | 52.9% |
| TE | 12 | Juwan Johnson | 10.33 | 3.74 | 46.1% | 42.8% |
| TE | 13 | T.J. Hockenson | 9.97 | 3.61 | 43.3% | 39.7% |
| TE | 18 | Pat Freiermuth | 8.41 | 3.04 | 28.5% | 24.1% |

## Top movers, blended DDF Value, before (scaled to the pie) and after A

### standard/8

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 13.91 | 39.75 | 55.46 | +15.71 |
| Ja'Marr Chase | WR | starter | 12.13 | 32.99 | 46.02 | +13.02 |
| Puka Nacua | WR | starter | 13.69 | 35.63 | 48.49 | +12.86 |
| Amon-Ra St. Brown | WR | starter | 11.8 | 30.69 | 42.96 | +12.27 |
| CeeDee Lamb | WR | starter | 12.43 | 32.03 | 43.9 | +11.88 |
| Chris Olave | WR | starter | 10.69 | 24.01 | 32.98 | +8.97 |
| Justin Jefferson | WR | starter | 10.72 | 23.06 | 30.88 | +7.82 |
| Nico Collins | WR | starter | 10.99 | 22.66 | 30.37 | +7.71 |
| Zay Flowers | WR | starter | 10.4 | 21.69 | 29.27 | +7.58 |
| Drake London | WR | starter | 10.18 | 20.17 | 27.21 | +7.03 |
| Rhamondre Stevenson | RB | bench | 9.34 | 14.04 | 9.16 | -4.88 |
| Quinshon Judkins | RB | starter | 10.83 | 19.88 | 15.15 | -4.73 |
| Christian Watson | WR | starter | 10.18 | 16.85 | 21.57 | +4.73 |
| Tetairoa McMillan | WR | starter | 10.3 | 17.44 | 21.66 | +4.21 |
| Travis Etienne | RB | bench | 8.46 | 9.92 | 5.75 | -4.17 |
| George Pickens | WR | starter | 9.24 | 14.7 | 18.81 | +4.11 |
| Aaron Jones | RB | bench | 9.31 | 11.87 | 7.87 | -4.00 |
| Omarion Hampton | RB | starter | 9.8 | 19.46 | 15.52 | -3.93 |
| Tee Higgins | WR | starter | 10.23 | 16.36 | 20.26 | +3.90 |
| Parker Washington | WR | starter | 9.31 | 14.4 | 18.17 | +3.77 |
| Davante Adams | WR | starter | 10.81 | 16.92 | 20.43 | +3.51 |
| David Montgomery | RB | starter | 10.13 | 15.31 | 11.8 | -3.51 |
| TreVeyon Henderson | RB | bench | 8.17 | 8.45 | 4.99 | -3.46 |
| Tony Pollard | RB | starter | 10.54 | 12.27 | 9.01 | -3.26 |
| Cam Skattebo | RB | starter | 11.62 | 22.94 | 19.69 | -3.25 |
| Kyle Monangai | RB | bench | 8.34 | 7.82 | 4.64 | -3.18 |
| DeVonta Smith | WR | starter | 8.77 | 12.87 | 16.01 | +3.14 |
| Jordan Mason | RB | bench | 8.7 | 6.48 | 3.46 | -3.02 |
| Jeremiyah Love | RB | starter | 11.44 | 27.49 | 24.48 | -3.01 |
| Garrett Wilson | WR | starter | 8.74 | 12.89 | 15.79 | +2.90 |

### standard/10

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 13.91 | 42.02 | 57.9 | +15.88 |
| Ja'Marr Chase | WR | starter | 12.13 | 35.19 | 49.08 | +13.88 |
| Amon-Ra St. Brown | WR | starter | 11.8 | 33.25 | 46.18 | +12.93 |
| Puka Nacua | WR | starter | 13.69 | 37.56 | 50.29 | +12.73 |
| CeeDee Lamb | WR | starter | 12.43 | 34.6 | 46.96 | +12.36 |
| Chris Olave | WR | starter | 10.69 | 27.03 | 36.77 | +9.74 |
| Justin Jefferson | WR | starter | 10.72 | 25.83 | 34.45 | +8.62 |
| Zay Flowers | WR | starter | 10.4 | 24.62 | 32.95 | +8.33 |
| Nico Collins | WR | starter | 10.99 | 25.84 | 33.96 | +8.11 |
| Drake London | WR | starter | 10.18 | 23.35 | 31.0 | +7.65 |
| Josh Allen | QB | starter | 23.39 | 28.27 | 33.77 | +5.50 |
| Brock Bowers | TE | starter | 9.59 | 24.28 | 29.53 | +5.25 |
| RJ Harvey | RB | bench | 6.73 | 9.71 | 4.57 | -5.15 |
| Jahmyr Gibbs | RB | starter | 20.2 | 76.18 | 81.27 | +5.09 |
| Christian Watson | WR | starter | 10.18 | 20.01 | 25.02 | +5.01 |
| Brian Robinson | RB | bench | 6.7 | 8.34 | 3.41 | -4.93 |
| Bijan Robinson | RB | starter | 18.56 | 71.02 | 75.87 | +4.86 |
| George Pickens | WR | starter | 9.24 | 17.67 | 22.53 | +4.86 |
| Kyle Monangai | RB | bench | 8.34 | 14.88 | 10.03 | -4.85 |
| Alvin Kamara | RB | bench | 6.31 | 7.43 | 2.71 | -4.73 |
| Tetairoa McMillan | WR | starter | 10.3 | 20.16 | 24.88 | +4.72 |
| Zach Charbonnet | RB | starter | 8.64 | 12.24 | 7.57 | -4.67 |
| Tony Pollard | RB | starter | 10.54 | 19.34 | 14.71 | -4.63 |
| Rhamondre Stevenson | RB | starter | 9.34 | 20.25 | 15.68 | -4.57 |
| Parker Washington | WR | starter | 9.31 | 17.41 | 21.91 | +4.49 |
| Jordan Mason | RB | starter | 8.7 | 13.07 | 8.73 | -4.34 |
| J.K. Dobbins | RB | starter | 8.66 | 11.72 | 7.38 | -4.33 |
| Trey McBride | TE | starter | 9.05 | 21.49 | 25.79 | +4.30 |
| Rico Dowdle | RB | bench | 6.39 | 6.78 | 2.53 | -4.25 |
| TreVeyon Henderson | RB | bench | 8.17 | 14.54 | 10.29 | -4.24 |

### standard/12

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 13.91 | 43.13 | 62.34 | +19.21 |
| Ja'Marr Chase | WR | starter | 12.13 | 36.23 | 53.25 | +17.02 |
| Amon-Ra St. Brown | WR | starter | 11.8 | 34.56 | 50.36 | +15.80 |
| CeeDee Lamb | WR | starter | 12.43 | 36.21 | 51.87 | +15.66 |
| Puka Nacua | WR | starter | 13.69 | 38.79 | 54.04 | +15.25 |
| Chris Olave | WR | starter | 10.69 | 28.74 | 41.31 | +12.57 |
| Justin Jefferson | WR | starter | 10.72 | 27.59 | 39.07 | +11.48 |
| Zay Flowers | WR | starter | 10.4 | 26.35 | 37.24 | +10.89 |
| Nico Collins | WR | starter | 10.99 | 27.75 | 38.35 | +10.59 |
| Drake London | WR | starter | 10.18 | 25.2 | 35.07 | +9.87 |
| Brock Bowers | TE | starter | 9.59 | 24.2 | 32.62 | +8.42 |
| Jahmyr Gibbs | RB | starter | 20.2 | 77.71 | 86.11 | +8.40 |
| Bijan Robinson | RB | starter | 18.56 | 72.74 | 80.83 | +8.09 |
| Trey McBride | TE | starter | 9.05 | 21.59 | 28.84 | +7.25 |
| Kenneth Walker III | RB | starter | 17.88 | 68.22 | 75.31 | +7.08 |
| George Pickens | WR | starter | 9.24 | 19.68 | 26.45 | +6.77 |
| Christian Watson | WR | starter | 10.18 | 22.1 | 28.73 | +6.63 |
| Tetairoa McMillan | WR | starter | 10.3 | 22.19 | 28.75 | +6.56 |
| Parker Washington | WR | starter | 9.31 | 19.41 | 25.55 | +6.14 |
| Jonathan Taylor | RB | starter | 16.22 | 60.58 | 66.67 | +6.09 |
| DeVonta Smith | WR | starter | 8.77 | 17.67 | 23.66 | +5.99 |
| Tee Higgins | WR | starter | 10.23 | 21.46 | 27.37 | +5.91 |
| Garrett Wilson | WR | starter | 8.74 | 17.97 | 23.79 | +5.82 |
| Bryce Young | QB | bench | 17.71 | 10.2 | 4.57 | -5.63 |
| James Cook | RB | starter | 13.43 | 52.02 | 57.63 | +5.61 |
| Rico Dowdle | RB | bench | 6.39 | 11.25 | 5.65 | -5.60 |
| Ollie Gordon II | RB | starter | 8.69 | 18.79 | 13.24 | -5.55 |
| Brian Robinson | RB | bench | 6.7 | 12.46 | 7.05 | -5.41 |
| Alvin Kamara | RB | bench | 6.31 | 10.86 | 5.57 | -5.29 |
| Keaton Mitchell | RB | bench | 6.0 | 8.91 | 3.71 | -5.20 |

### standard/14

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 13.91 | 42.7 | 67.55 | +24.85 |
| Ja'Marr Chase | WR | starter | 12.13 | 36.38 | 58.32 | +21.94 |
| CeeDee Lamb | WR | starter | 12.43 | 36.35 | 56.93 | +20.58 |
| Amon-Ra St. Brown | WR | starter | 11.8 | 34.88 | 55.28 | +20.40 |
| Puka Nacua | WR | starter | 13.69 | 38.41 | 58.09 | +19.68 |
| Chris Olave | WR | starter | 10.69 | 29.32 | 46.1 | +16.77 |
| Justin Jefferson | WR | starter | 10.72 | 28.21 | 43.66 | +15.45 |
| Zay Flowers | WR | starter | 10.4 | 27.0 | 41.64 | +14.64 |
| Nico Collins | WR | starter | 10.99 | 28.17 | 42.57 | +14.39 |
| Drake London | WR | starter | 10.18 | 25.88 | 39.23 | +13.35 |
| Brock Bowers | TE | starter | 9.59 | 23.64 | 35.02 | +11.38 |
| Trey McBride | TE | starter | 9.05 | 21.11 | 31.34 | +10.24 |
| George Pickens | WR | starter | 9.24 | 20.72 | 30.21 | +9.49 |
| Christian Watson | WR | starter | 10.18 | 22.76 | 32.02 | +9.26 |
| Tetairoa McMillan | WR | starter | 10.3 | 22.92 | 32.03 | +9.11 |
| Bijan Robinson | RB | starter | 18.56 | 77.25 | 86.24 | +8.99 |
| Jahmyr Gibbs | RB | starter | 20.2 | 82.5 | 91.42 | +8.92 |
| Parker Washington | WR | starter | 9.31 | 20.38 | 29.0 | +8.63 |
| DeVonta Smith | WR | starter | 8.77 | 18.93 | 27.43 | +8.50 |
| Tee Higgins | WR | starter | 10.23 | 22.2 | 30.61 | +8.41 |
| Garrett Wilson | WR | starter | 8.74 | 19.28 | 27.56 | +8.28 |
| Kenneth Walker III | RB | starter | 17.88 | 72.23 | 80.26 | +8.03 |
| Davante Adams | WR | starter | 10.81 | 22.49 | 29.85 | +7.35 |
| James Cook | RB | starter | 13.43 | 56.09 | 62.95 | +6.86 |
| Malik Nabers | WR | starter | 7.7 | 16.21 | 23.03 | +6.82 |
| Jonathan Taylor | RB | starter | 16.22 | 64.88 | 71.58 | +6.70 |
| A.J. Brown | WR | starter | 8.65 | 17.44 | 23.87 | +6.44 |
| Christian McCaffrey | RB | starter | 14.73 | 57.99 | 64.23 | +6.25 |
| Jayden Daniels | QB | starter | 19.54 | 15.62 | 9.76 | -5.86 |
| Matthew Stafford | QB | starter | 19.2 | 13.13 | 7.54 | -5.59 |

### half_ppr/8

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 17.24 | 41.78 | 56.82 | +15.04 |
| Ja'Marr Chase | WR | starter | 15.71 | 36.09 | 49.3 | +13.21 |
| Puka Nacua | WR | starter | 17.37 | 38.41 | 50.9 | +12.49 |
| Amon-Ra St. Brown | WR | starter | 15.32 | 34.06 | 46.2 | +12.13 |
| CeeDee Lamb | WR | starter | 15.97 | 35.08 | 46.66 | +11.58 |
| Chris Olave | WR | starter | 13.84 | 26.61 | 35.59 | +8.98 |
| Justin Jefferson | WR | starter | 13.66 | 25.13 | 32.82 | +7.69 |
| Zay Flowers | WR | starter | 12.94 | 22.75 | 30.07 | +7.33 |
| Nico Collins | WR | starter | 13.73 | 24.13 | 31.37 | +7.24 |
| Drake London | WR | starter | 12.83 | 21.75 | 28.61 | +6.86 |
| Rhamondre Stevenson | RB | bench | 10.61 | 13.85 | 9.14 | -4.70 |
| Quinshon Judkins | RB | starter | 12.4 | 19.77 | 15.39 | -4.39 |
| Travis Etienne | RB | bench | 9.68 | 9.94 | 5.77 | -4.17 |
| Christian Watson | WR | starter | 12.44 | 17.29 | 21.25 | +3.97 |
| Tetairoa McMillan | WR | starter | 13.17 | 19.26 | 23.19 | +3.93 |
| Aaron Jones | RB | bench | 10.63 | 11.62 | 7.71 | -3.91 |
| Omarion Hampton | RB | starter | 10.63 | 17.63 | 13.73 | -3.90 |
| George Pickens | WR | starter | 11.7 | 15.82 | 19.48 | +3.65 |
| David Montgomery | RB | starter | 11.0 | 14.11 | 10.49 | -3.62 |
| Parker Washington | WR | starter | 11.51 | 15.1 | 18.52 | +3.43 |
| TreVeyon Henderson | RB | bench | 8.84 | 7.33 | 4.1 | -3.23 |
| Tony Pollard | RB | starter | 11.65 | 11.35 | 8.12 | -3.23 |
| Cam Skattebo | RB | starter | 12.75 | 21.84 | 18.65 | -3.19 |
| Kyle Monangai | RB | bench | 8.98 | 6.67 | 3.5 | -3.18 |
| Tee Higgins | WR | starter | 12.87 | 17.61 | 20.64 | +3.03 |
| Rome Odunze | WR | bench | 8.51 | 4.79 | 1.8 | -2.99 |
| Deebo Samuel Sr. | WR | bench | 9.03 | 5.75 | 2.77 | -2.98 |
| DeVonta Smith | WR | starter | 11.51 | 14.76 | 17.74 | +2.98 |
| Garrett Wilson | WR | starter | 11.61 | 15.24 | 18.21 | +2.97 |
| Jordan Mason | RB | bench | 9.25 | 5.2 | 2.28 | -2.92 |

### half_ppr/10

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 17.24 | 44.23 | 59.56 | +15.33 |
| Ja'Marr Chase | WR | starter | 15.71 | 38.52 | 52.29 | +13.77 |
| Amon-Ra St. Brown | WR | starter | 15.32 | 36.8 | 49.5 | +12.69 |
| Puka Nacua | WR | starter | 17.37 | 40.39 | 52.86 | +12.47 |
| CeeDee Lamb | WR | starter | 15.97 | 37.82 | 49.84 | +12.03 |
| Chris Olave | WR | starter | 13.84 | 29.93 | 39.45 | +9.51 |
| Justin Jefferson | WR | starter | 13.66 | 28.17 | 36.65 | +8.48 |
| Zay Flowers | WR | starter | 12.94 | 26.08 | 34.08 | +8.00 |
| Nico Collins | WR | starter | 13.73 | 27.47 | 35.17 | +7.69 |
| Drake London | WR | starter | 12.83 | 25.23 | 32.59 | +7.36 |
| Josh Allen | QB | starter | 23.39 | 24.4 | 31.75 | +7.35 |
| Brock Bowers | TE | starter | 12.59 | 25.94 | 30.51 | +4.58 |
| Tetairoa McMillan | WR | starter | 13.17 | 22.21 | 26.79 | +4.58 |
| Christian Watson | WR | starter | 12.44 | 20.68 | 25.1 | +4.42 |
| George Pickens | WR | starter | 11.7 | 19.23 | 23.63 | +4.41 |
| Josh Downs | WR | bench | 8.62 | 8.73 | 4.46 | -4.27 |
| RJ Harvey | RB | bench | 8.73 | 10.79 | 6.57 | -4.22 |
| Parker Washington | WR | starter | 11.51 | 18.47 | 22.64 | +4.17 |
| Romeo Doubs | WR | bench | 7.81 | 5.95 | 2.03 | -3.92 |
| Garrett Wilson | WR | starter | 11.61 | 18.62 | 22.49 | +3.87 |
| DeVonta Smith | WR | starter | 11.51 | 18.0 | 21.85 | +3.85 |
| Trey McBride | TE | starter | 12.69 | 24.61 | 28.42 | +3.81 |
| Alvin Kamara | RB | bench | 7.52 | 6.92 | 3.15 | -3.77 |
| Stefon Diggs | WR | bench | 8.76 | 8.42 | 4.71 | -3.71 |
| Tee Higgins | WR | starter | 12.87 | 20.75 | 24.41 | +3.65 |
| Jordan Addison | WR | bench | 8.03 | 6.06 | 2.48 | -3.58 |
| Brian Robinson | RB | bench | 7.03 | 5.81 | 2.27 | -3.54 |
| Kyle Monangai | RB | bench | 8.98 | 12.03 | 8.59 | -3.44 |
| Jakobi Meyers | WR | bench | 8.63 | 6.86 | 3.47 | -3.39 |
| Rico Dowdle | RB | bench | 7.25 | 5.59 | 2.22 | -3.37 |

### half_ppr/12

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 17.24 | 45.14 | 64.89 | +19.74 |
| Ja'Marr Chase | WR | starter | 15.71 | 39.65 | 57.07 | +17.42 |
| Amon-Ra St. Brown | WR | starter | 15.32 | 38.05 | 54.32 | +16.26 |
| CeeDee Lamb | WR | starter | 15.97 | 39.37 | 55.49 | +16.12 |
| Puka Nacua | WR | starter | 17.37 | 41.48 | 57.31 | +15.83 |
| Chris Olave | WR | starter | 13.84 | 31.8 | 44.6 | +12.80 |
| Justin Jefferson | WR | starter | 13.66 | 30.19 | 41.81 | +11.63 |
| Zay Flowers | WR | starter | 12.94 | 28.13 | 38.93 | +10.80 |
| Nico Collins | WR | starter | 13.73 | 29.55 | 40.16 | +10.61 |
| Drake London | WR | starter | 12.83 | 27.34 | 37.27 | +9.93 |
| Brock Bowers | TE | starter | 12.59 | 25.73 | 32.94 | +7.20 |
| Tetairoa McMillan | WR | starter | 13.17 | 24.55 | 31.14 | +6.59 |
| Trey McBride | TE | starter | 12.69 | 24.65 | 31.11 | +6.46 |
| George Pickens | WR | starter | 11.7 | 21.54 | 27.93 | +6.38 |
| Christian Watson | WR | starter | 12.44 | 23.02 | 29.34 | +6.32 |
| Bijan Robinson | RB | starter | 20.27 | 71.01 | 77.23 | +6.22 |
| Jahmyr Gibbs | RB | starter | 22.48 | 77.04 | 83.19 | +6.15 |
| Parker Washington | WR | starter | 11.51 | 20.85 | 26.76 | +5.91 |
| Garrett Wilson | WR | starter | 11.61 | 21.2 | 27.05 | +5.85 |
| DeVonta Smith | WR | starter | 11.51 | 20.45 | 26.22 | +5.77 |
| Kenneth Walker III | RB | starter | 19.41 | 65.86 | 71.55 | +5.68 |
| Tee Higgins | WR | starter | 12.87 | 23.09 | 28.72 | +5.63 |
| Bryce Young | QB | bench | 17.71 | 9.37 | 4.22 | -5.15 |
| James Cook | RB | starter | 14.34 | 48.51 | 53.36 | +4.84 |
| Davante Adams | WR | starter | 13.32 | 22.98 | 27.71 | +4.73 |
| Jonathan Taylor | RB | starter | 17.5 | 58.13 | 62.81 | +4.68 |
| Malik Nabers | WR | starter | 9.89 | 16.92 | 21.33 | +4.41 |
| Christian McCaffrey | RB | starter | 16.75 | 53.54 | 57.89 | +4.35 |
| Rico Dowdle | RB | bench | 7.25 | 9.39 | 5.13 | -4.26 |
| Brian Robinson | RB | bench | 7.03 | 9.33 | 5.15 | -4.18 |

### half_ppr/14

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 17.24 | 47.01 | 70.47 | +23.47 |
| Ja'Marr Chase | WR | starter | 15.71 | 41.62 | 62.2 | +20.59 |
| CeeDee Lamb | WR | starter | 15.97 | 41.23 | 60.69 | +19.46 |
| Amon-Ra St. Brown | WR | starter | 15.32 | 40.07 | 59.41 | +19.34 |
| Puka Nacua | WR | starter | 17.37 | 42.79 | 61.53 | +18.73 |
| Chris Olave | WR | starter | 13.84 | 33.79 | 49.65 | +15.86 |
| Justin Jefferson | WR | starter | 13.66 | 32.08 | 46.64 | +14.56 |
| Zay Flowers | WR | starter | 12.94 | 30.13 | 43.7 | +13.57 |
| Nico Collins | WR | starter | 13.73 | 31.32 | 44.78 | +13.46 |
| Drake London | WR | starter | 12.83 | 29.31 | 41.84 | +12.54 |
| George Pickens | WR | starter | 11.7 | 23.36 | 32.02 | +8.66 |
| Tetairoa McMillan | WR | starter | 13.17 | 25.99 | 34.58 | +8.59 |
| Christian Watson | WR | starter | 12.44 | 24.63 | 33.0 | +8.37 |
| Bijan Robinson | RB | starter | 20.27 | 73.77 | 82.11 | +8.34 |
| Jahmyr Gibbs | RB | starter | 22.48 | 79.91 | 87.91 | +8.00 |
| Parker Washington | WR | starter | 11.51 | 22.69 | 30.66 | +7.97 |
| Garrett Wilson | WR | starter | 11.61 | 23.09 | 30.92 | +7.83 |
| DeVonta Smith | WR | starter | 11.51 | 22.24 | 30.05 | +7.82 |
| Tee Higgins | WR | starter | 12.87 | 24.49 | 32.24 | +7.75 |
| Kenneth Walker III | RB | starter | 19.41 | 68.53 | 76.03 | +7.51 |
| Brock Bowers | TE | starter | 12.59 | 28.54 | 35.71 | +7.17 |
| James Cook | RB | starter | 14.34 | 51.36 | 58.22 | +6.86 |
| Davante Adams | WR | starter | 13.32 | 24.11 | 30.8 | +6.69 |
| Jonathan Taylor | RB | starter | 17.5 | 60.7 | 67.24 | +6.54 |
| Trey McBride | TE | starter | 12.69 | 27.47 | 33.9 | +6.43 |
| Malik Nabers | WR | starter | 9.89 | 19.15 | 25.27 | +6.12 |
| Christian McCaffrey | RB | starter | 16.75 | 56.12 | 62.11 | +5.99 |
| A.J. Brown | WR | starter | 10.99 | 19.84 | 25.71 | +5.87 |
| Derrick Henry | RB | starter | 17.26 | 56.37 | 61.81 | +5.43 |
| Keon Coleman | WR | bench | 6.92 | 9.44 | 4.25 | -5.19 |

### ppr/8

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 20.57 | 46.56 | 58.02 | +11.46 |
| Puka Nacua | WR | starter | 21.02 | 42.11 | 52.43 | +10.32 |
| Ja'Marr Chase | WR | starter | 19.3 | 41.36 | 51.24 | +9.88 |
| Amon-Ra St. Brown | WR | starter | 18.84 | 39.55 | 48.82 | +9.27 |
| CeeDee Lamb | WR | starter | 19.51 | 39.82 | 48.77 | +8.95 |
| Chris Olave | WR | starter | 17.02 | 31.62 | 38.14 | +6.52 |
| Justin Jefferson | WR | starter | 16.61 | 29.05 | 34.36 | +5.31 |
| Nico Collins | WR | starter | 16.44 | 27.55 | 32.55 | +4.99 |
| Zay Flowers | WR | starter | 15.47 | 26.46 | 31.14 | +4.68 |
| Jahmyr Gibbs | RB | starter | 24.74 | 66.98 | 71.63 | +4.65 |
| Drake London | WR | starter | 15.49 | 25.78 | 30.32 | +4.54 |
| Rome Odunze | WR | bench | 10.16 | 6.19 | 2.04 | -4.15 |
| Deebo Samuel Sr. | WR | bench | 10.74 | 6.87 | 2.75 | -4.12 |
| Bijan Robinson | RB | starter | 22.01 | 59.84 | 63.89 | +4.05 |
| Jameson Williams | WR | bench | 10.53 | 7.81 | 3.84 | -3.97 |
| DK Metcalf | WR | bench | 11.98 | 9.07 | 5.1 | -3.97 |
| Jalen Coker | WR | starter | 13.0 | 12.05 | 8.28 | -3.78 |
| Stefon Diggs | WR | bench | 10.84 | 5.81 | 2.14 | -3.67 |
| Ladd McConkey | WR | bench | 11.27 | 9.96 | 6.35 | -3.61 |
| Josh Downs | WR | bench | 10.79 | 5.77 | 2.2 | -3.57 |
| Emeka Egbuka | WR | bench | 11.23 | 8.53 | 4.97 | -3.56 |
| Jonathan Taylor | RB | starter | 18.74 | 45.44 | 48.73 | +3.29 |
| Kenneth Walker III | RB | starter | 20.94 | 55.16 | 58.35 | +3.19 |
| Rhamondre Stevenson | RB | bench | 11.88 | 11.86 | 8.76 | -3.09 |
| Denzel Boston | WR | bench | 11.27 | 6.6 | 3.52 | -3.08 |
| Tetairoa McMillan | WR | starter | 16.07 | 22.02 | 24.97 | +2.96 |
| Travis Etienne | RB | bench | 10.9 | 8.58 | 5.76 | -2.82 |
| Terry McLaurin | WR | starter | 12.69 | 10.64 | 7.89 | -2.74 |
| Derrick Henry | RB | starter | 17.88 | 40.2 | 42.8 | +2.60 |
| Quinshon Judkins | RB | starter | 13.94 | 18.0 | 15.42 | -2.58 |

### ppr/10

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 20.57 | 45.47 | 61.48 | +16.01 |
| Ja'Marr Chase | WR | starter | 19.3 | 40.62 | 54.92 | +14.30 |
| Puka Nacua | WR | starter | 21.02 | 41.65 | 55.23 | +13.58 |
| Amon-Ra St. Brown | WR | starter | 18.84 | 39.09 | 52.42 | +13.34 |
| CeeDee Lamb | WR | starter | 19.51 | 39.69 | 52.37 | +12.68 |
| Chris Olave | WR | starter | 17.02 | 32.2 | 41.99 | +9.79 |
| Justin Jefferson | WR | starter | 16.61 | 29.87 | 38.58 | +8.71 |
| Josh Allen | QB | starter | 23.39 | 21.73 | 30.2 | +8.47 |
| Zay Flowers | WR | starter | 15.47 | 27.43 | 35.3 | +7.87 |
| Nico Collins | WR | starter | 16.44 | 28.67 | 36.49 | +7.83 |
| Drake London | WR | starter | 15.49 | 26.89 | 34.28 | +7.39 |
| Stefon Diggs | WR | bench | 10.84 | 11.4 | 5.7 | -5.70 |
| Tetairoa McMillan | WR | starter | 16.07 | 23.74 | 28.84 | +5.09 |
| Romeo Doubs | WR | bench | 9.33 | 7.01 | 2.32 | -4.69 |
| Christian Watson | WR | starter | 14.71 | 21.37 | 25.74 | +4.37 |
| Jakobi Meyers | WR | bench | 10.5 | 8.52 | 4.2 | -4.32 |
| George Pickens | WR | starter | 14.2 | 20.63 | 24.93 | +4.30 |
| Josh Downs | WR | bench | 10.79 | 10.12 | 5.86 | -4.26 |
| Jordan Addison | WR | bench | 9.61 | 7.05 | 2.84 | -4.21 |
| Garrett Wilson | WR | starter | 14.5 | 20.89 | 24.98 | +4.09 |
| Denzel Boston | WR | starter | 11.27 | 11.26 | 7.18 | -4.08 |
| Parker Washington | WR | starter | 13.71 | 19.68 | 23.71 | +4.03 |
| Tee Higgins | WR | starter | 15.52 | 21.76 | 25.76 | +4.00 |
| Wan'Dale Robinson | WR | bench | 9.42 | 5.83 | 1.91 | -3.92 |
| DeVonta Smith | WR | starter | 14.21 | 19.78 | 23.65 | +3.86 |
| Rome Odunze | WR | bench | 10.16 | 9.53 | 5.72 | -3.81 |
| Lamar Jackson | QB | starter | 20.64 | 12.43 | 16.07 | +3.64 |
| Brian Thomas Jr. | WR | bench | 9.04 | 5.54 | 1.98 | -3.56 |
| Jordyn Tyson | WR | waiver | 7.43 | 5.01 | 1.48 | -3.53 |
| Davante Adams | WR | starter | 15.83 | 21.05 | 24.51 | +3.46 |

### ppr/12

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 20.57 | 51.37 | 66.99 | +15.62 |
| Ja'Marr Chase | WR | starter | 19.3 | 46.24 | 59.98 | +13.73 |
| Amon-Ra St. Brown | WR | starter | 18.84 | 44.48 | 57.42 | +12.94 |
| CeeDee Lamb | WR | starter | 19.51 | 45.56 | 58.22 | +12.66 |
| Puka Nacua | WR | starter | 21.02 | 47.17 | 59.79 | +12.62 |
| Chris Olave | WR | starter | 17.02 | 37.34 | 47.52 | +10.18 |
| Justin Jefferson | WR | starter | 16.61 | 35.09 | 44.12 | +9.03 |
| Jahmyr Gibbs | RB | starter | 24.74 | 71.88 | 80.28 | +8.40 |
| Zay Flowers | WR | starter | 15.47 | 32.3 | 40.64 | +8.34 |
| Nico Collins | WR | starter | 16.44 | 33.63 | 41.88 | +8.25 |
| Bijan Robinson | RB | starter | 22.01 | 65.39 | 73.52 | +8.13 |
| Romeo Doubs | WR | bench | 9.33 | 13.4 | 5.44 | -7.95 |
| Drake London | WR | starter | 15.49 | 31.64 | 39.48 | +7.84 |
| Kenneth Walker III | RB | starter | 20.94 | 59.98 | 67.57 | +7.60 |
| Kalif Raymond | WR | bench | 7.37 | 8.21 | 0.91 | -7.30 |
| Jonathan Taylor | RB | starter | 18.74 | 52.65 | 58.89 | +6.24 |
| Christian McCaffrey | RB | starter | 18.77 | 49.82 | 55.9 | +6.07 |
| James Cook | RB | starter | 15.27 | 43.35 | 49.07 | +5.73 |
| Brian Thomas Jr. | WR | bench | 9.04 | 10.4 | 4.76 | -5.64 |
| Derrick Henry | RB | starter | 17.88 | 47.18 | 52.7 | +5.52 |
| Malik Washington | WR | starter | 10.27 | 11.27 | 5.87 | -5.40 |
| Tetairoa McMillan | WR | starter | 16.07 | 28.33 | 33.5 | +5.17 |
| Chris Godwin | WR | bench | 8.88 | 9.76 | 4.69 | -5.07 |
| Brock Bowers | TE | starter | 15.58 | 28.64 | 33.46 | +4.82 |
| Tre Tucker | WR | bench | 9.02 | 7.67 | 2.86 | -4.81 |
| George Pickens | WR | starter | 14.2 | 24.75 | 29.53 | +4.78 |
| Jordan Addison | WR | bench | 9.61 | 10.44 | 5.67 | -4.77 |
| Dontayvion Wicks | WR | bench | 8.36 | 7.22 | 2.47 | -4.76 |
| Christian Watson | WR | starter | 14.71 | 25.62 | 30.37 | +4.75 |
| Xavier Worthy | WR | bench | 8.63 | 7.31 | 2.74 | -4.57 |

### ppr/14

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 20.57 | 51.95 | 71.98 | +20.03 |
| Ja'Marr Chase | WR | starter | 19.3 | 46.82 | 64.39 | +17.57 |
| CeeDee Lamb | WR | starter | 19.51 | 46.17 | 62.87 | +16.70 |
| Amon-Ra St. Brown | WR | starter | 18.84 | 45.22 | 61.87 | +16.65 |
| Puka Nacua | WR | starter | 21.02 | 47.34 | 63.63 | +16.29 |
| Chris Olave | WR | starter | 17.02 | 38.28 | 51.98 | +13.69 |
| Justin Jefferson | WR | starter | 16.61 | 35.91 | 48.39 | +12.48 |
| Zay Flowers | WR | starter | 15.47 | 33.43 | 44.89 | +11.47 |
| Nico Collins | WR | starter | 16.44 | 34.56 | 46.03 | +11.46 |
| Drake London | WR | starter | 15.49 | 32.82 | 43.59 | +10.77 |
| Bijan Robinson | RB | starter | 22.01 | 68.28 | 78.29 | +10.02 |
| Jahmyr Gibbs | RB | starter | 24.74 | 74.79 | 84.69 | +9.90 |
| Kenneth Walker III | RB | starter | 20.94 | 63.03 | 72.16 | +9.13 |
| Jonathan Taylor | RB | starter | 18.74 | 55.17 | 63.18 | +8.02 |
| James Cook | RB | starter | 15.27 | 46.18 | 53.98 | +7.80 |
| Tetairoa McMillan | WR | starter | 16.07 | 29.02 | 36.72 | +7.69 |
| Christian McCaffrey | RB | starter | 18.77 | 52.76 | 60.13 | +7.36 |
| George Pickens | WR | starter | 14.2 | 25.88 | 33.18 | +7.30 |
| Christian Watson | WR | starter | 14.71 | 26.7 | 33.76 | +7.06 |
| Derrick Henry | RB | starter | 17.88 | 49.85 | 56.85 | +7.00 |
| Garrett Wilson | WR | starter | 14.5 | 26.51 | 33.44 | +6.93 |
| Parker Washington | WR | starter | 13.71 | 25.09 | 31.93 | +6.84 |
| Tee Higgins | WR | starter | 15.52 | 26.76 | 33.47 | +6.71 |
| DeVonta Smith | WR | starter | 14.21 | 25.05 | 31.76 | +6.70 |
| Davante Adams | WR | starter | 15.83 | 25.88 | 31.7 | +5.82 |
| Chase Brown | RB | starter | 17.08 | 44.15 | 49.88 | +5.73 |
| Kyren Williams | RB | starter | 17.42 | 45.71 | 51.35 | +5.64 |
| Javonte Williams | RB | starter | 16.78 | 43.39 | 49.0 | +5.62 |
| Ashton Jeanty | RB | starter | 16.4 | 42.57 | 47.87 | +5.30 |
| Malik Nabers | WR | starter | 12.07 | 21.97 | 27.15 | +5.18 |
