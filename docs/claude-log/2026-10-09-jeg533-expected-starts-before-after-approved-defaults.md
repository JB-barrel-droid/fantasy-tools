# Expected-starts value: before and after, all 12 settings

Produced by `pipelines/expected_starts_model.py` on the Week 5 build. Before = today's live values (two-tier at the 15% bench share, ESPN anchored), scaled to the fixed pie. After A = expected-starts replaces the slices (ES-4 to ES-6). After B = slices kept, bench budget set from A. Bench-tier share = the pie held by players ranked past the starters on the mean projection. Price ratio = median value per point above waivers, starters over bench tier.

Parameters: QB m 11.8%, sigma 14.9%, floor 0.69; RB m 14.4%, sigma 27.7%, floor 0.84; WR m 11.8%, sigma 21.6%, floor 0.99; TE m 15.1%, sigma 19.6%, floor 0.65; bye share 7.8%.

## Bench-tier share and starter/bench price, per setting

| Setting | Variant | QB bench | RB bench | WR bench | TE bench | Overall | Fill-state share | QB price | RB price | WR price | TE price | Inversions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| standard/8 | before | 15.0% | 10.0% | 17.9% | 17.9% | 13.5% | n/a | 1.2x | 1.5x | 0.8x | 0.9x | n/a |
| standard/8 | after A | 12.2% | 6.4% | 11.5% | 14.0% | 9.2% | 6.0% | 1.4x | 2.8x | 1.7x | 1.1x | 0 |
| standard/8 | after A-option | 17.1% | 8.7% | 15.4% | 18.3% | 12.6% | 4.1% | 1.1x | 1.6x | 1.0x | 0.9x | 0 |
| standard/8 | after B | 12.1% | 5.8% | 10.8% | 13.4% | 8.7% | n/a | 1.4x | 2.5x | 1.4x | 1.2x | 0 |
| standard/10 | before | 13.8% | 12.7% | 16.5% | 17.0% | 14.3% | n/a | 1.1x | 1.0x | 1.0x | 1.1x | n/a |
| standard/10 | after A | 10.5% | 7.7% | 9.9% | 12.9% | 9.0% | 6.1% | 1.3x | 2.0x | 2.4x | 1.5x | 0 |
| standard/10 | after A-option | 14.6% | 9.7% | 13.4% | 16.4% | 12.0% | 4.0% | 1.0x | 1.4x | 1.3x | 1.1x | 0 |
| standard/10 | after B | 10.5% | 7.1% | 9.4% | 12.7% | 8.6% | n/a | 1.3x | 1.9x | 2.2x | 1.6x | 0 |
| standard/12 | before | 23.8% | 12.2% | 15.1% | 15.2% | 14.4% | n/a | 1.4x | 1.1x | 1.1x | 0.7x | n/a |
| standard/12 | after A | 22.6% | 6.7% | 7.4% | 9.4% | 8.3% | 5.2% | 2.1x | 2.2x | 2.9x | 1.3x | 0 |
| standard/12 | after A-option | 24.7% | 8.3% | 10.3% | 13.1% | 10.9% | 3.4% | 1.4x | 1.7x | 1.8x | 0.8x | 0 |
| standard/12 | after B | 22.3% | 5.8% | 7.2% | 8.8% | 7.9% | n/a | 2.0x | 2.4x | 3.0x | 1.4x | 0 |
| standard/14 | before | 21.6% | 13.2% | 16.0% | 15.0% | 15.1% | n/a | 1.1x | 0.9x | 0.9x | 0.7x | n/a |
| standard/14 | after A | 20.7% | 7.6% | 7.5% | 8.9% | 8.6% | 5.1% | 2.0x | 1.9x | 2.0x | 1.6x | 0 |
| standard/14 | after A-option | 22.2% | 8.8% | 9.6% | 12.5% | 10.5% | 3.4% | 1.3x | 1.6x | 1.5x | 1.0x | 0 |
| standard/14 | after B | 19.7% | 6.8% | 6.5% | 8.3% | 7.9% | n/a | 2.3x | 2.1x | 2.4x | 1.8x | 0 |
| half_ppr/8 | before | 15.1% | 9.8% | 18.1% | 17.7% | 13.6% | n/a | 1.2x | 1.6x | 0.8x | 1.0x | n/a |
| half_ppr/8 | after A | 12.2% | 5.9% | 11.6% | 14.0% | 9.1% | 5.8% | 1.4x | 3.6x | 1.5x | 1.2x | 0 |
| half_ppr/8 | after A-option | 17.1% | 8.4% | 15.5% | 18.7% | 12.7% | 4.0% | 1.1x | 1.8x | 1.0x | 0.9x | 0 |
| half_ppr/8 | after B | 12.1% | 5.4% | 10.9% | 13.6% | 8.7% | n/a | 1.4x | 3.4x | 1.6x | 1.2x | 0 |
| half_ppr/10 | before | 13.6% | 11.5% | 16.8% | 16.7% | 13.9% | n/a | 1.2x | 1.2x | 0.8x | 1.1x | n/a |
| half_ppr/10 | after A | 10.5% | 7.5% | 9.4% | 12.5% | 8.8% | 5.8% | 1.3x | 2.1x | 2.2x | 1.4x | 0 |
| half_ppr/10 | after A-option | 14.6% | 9.7% | 12.8% | 16.1% | 11.8% | 3.8% | 1.0x | 1.6x | 1.3x | 1.2x | 0 |
| half_ppr/10 | after B | 10.5% | 6.9% | 9.0% | 12.0% | 8.3% | n/a | 1.3x | 2.1x | 2.1x | 1.4x | 0 |
| half_ppr/12 | before | 23.9% | 11.7% | 16.4% | 17.0% | 14.7% | n/a | 1.4x | 1.2x | 1.0x | 0.8x | n/a |
| half_ppr/12 | after A | 22.6% | 6.9% | 7.8% | 11.8% | 8.7% | 5.0% | 2.1x | 2.2x | 2.5x | 1.2x | 0 |
| half_ppr/12 | after A-option | 24.7% | 8.6% | 10.7% | 16.1% | 11.4% | 3.1% | 1.4x | 1.7x | 1.7x | 0.8x | 0 |
| half_ppr/12 | after B | 22.3% | 6.8% | 7.9% | 11.5% | 8.8% | n/a | 2.0x | 2.1x | 2.4x | 1.3x | 0 |
| half_ppr/14 | before | 21.6% | 12.7% | 16.1% | 14.9% | 14.9% | n/a | 1.1x | 1.2x | 0.8x | 0.7x | n/a |
| half_ppr/14 | after A | 20.7% | 8.1% | 7.0% | 9.1% | 8.6% | 5.2% | 2.1x | 1.9x | 2.2x | 1.3x | 0 |
| half_ppr/14 | after A-option | 22.2% | 9.6% | 9.0% | 12.9% | 10.6% | 3.3% | 1.3x | 1.6x | 1.7x | 0.9x | 0 |
| half_ppr/14 | after B | 19.7% | 7.4% | 5.9% | 8.6% | 7.8% | n/a | 2.3x | 2.2x | 2.4x | 1.4x | 0 |
| ppr/8 | before | 15.0% | 11.7% | 16.5% | 17.6% | 14.3% | n/a | 1.2x | 1.5x | 0.9x | 0.9x | n/a |
| ppr/8 | after A | 12.2% | 8.2% | 9.8% | 14.3% | 9.5% | 5.7% | 1.4x | 2.8x | 1.7x | 1.1x | 0 |
| ppr/8 | after A-option | 17.2% | 10.9% | 13.5% | 18.9% | 13.1% | 4.0% | 1.1x | 1.6x | 1.1x | 0.9x | 0 |
| ppr/8 | after B | 12.1% | 7.6% | 9.1% | 13.5% | 9.0% | n/a | 1.4x | 2.7x | 1.8x | 1.2x | 0 |
| ppr/10 | before | 13.5% | 11.2% | 16.6% | 16.7% | 13.9% | n/a | 1.2x | 1.4x | 0.8x | 1.8x | n/a |
| ppr/10 | after A | 10.5% | 7.8% | 7.9% | 12.6% | 8.4% | 5.6% | 1.3x | 2.4x | 2.3x | 2.5x | 0 |
| ppr/10 | after A-option | 14.6% | 10.3% | 11.3% | 16.5% | 11.5% | 3.7% | 1.0x | 1.7x | 1.3x | 1.2x | 0 |
| ppr/10 | after B | 10.5% | 7.4% | 7.7% | 12.0% | 8.1% | n/a | 1.3x | 2.3x | 2.1x | 2.5x | 0 |
| ppr/12 | before | 24.0% | 12.7% | 15.8% | 16.9% | 15.2% | n/a | 1.5x | 1.0x | 1.0x | 0.8x | n/a |
| ppr/12 | after A | 22.6% | 9.1% | 6.2% | 12.4% | 8.9% | 5.3% | 2.1x | 1.7x | 3.0x | 1.4x | 0 |
| ppr/12 | after A-option | 24.7% | 11.3% | 8.7% | 16.6% | 11.7% | 3.3% | 1.4x | 1.3x | 1.9x | 0.8x | 0 |
| ppr/12 | after B | 22.3% | 8.8% | 6.1% | 12.8% | 8.9% | n/a | 2.0x | 1.7x | 2.8x | 1.4x | 0 |
| ppr/14 | before | 21.6% | 12.7% | 14.4% | 17.5% | 14.5% | n/a | 1.2x | 1.2x | 0.8x | 0.5x | n/a |
| ppr/14 | after A | 20.7% | 7.9% | 6.7% | 10.2% | 8.4% | 5.1% | 2.1x | 2.1x | 2.2x | 1.1x | 0 |
| ppr/14 | after A-option | 22.2% | 9.6% | 8.7% | 13.7% | 10.5% | 3.2% | 1.3x | 1.7x | 1.6x | 0.8x | 0 |
| ppr/14 | after B | 19.7% | 7.5% | 5.7% | 9.2% | 7.7% | n/a | 2.3x | 2.3x | 2.3x | 1.3x | 0 |

## Position shares of the pie (blended DDF Value)

| Setting | QB before | QB after A | RB before | RB after A | WR before | WR after A | TE before | TE after A |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| standard/8 | 8.0% | 6.4% | 53.3% | 49.2% | 32.0% | 38.0% | 6.7% | 6.4% |
| standard/10 | 7.0% | 6.7% | 54.3% | 50.1% | 32.4% | 36.8% | 6.3% | 6.3% |
| standard/12 | 9.2% | 7.3% | 52.5% | 48.4% | 32.1% | 37.8% | 6.2% | 6.4% |
| standard/14 | 10.5% | 7.5% | 51.9% | 47.5% | 31.7% | 38.7% | 5.9% | 6.3% |
| half_ppr/8 | 7.2% | 6.1% | 50.8% | 47.0% | 34.7% | 40.0% | 7.2% | 7.0% |
| half_ppr/10 | 6.1% | 6.3% | 51.1% | 47.7% | 36.0% | 39.4% | 6.8% | 6.6% |
| half_ppr/12 | 8.2% | 6.9% | 48.8% | 45.7% | 36.2% | 40.7% | 6.8% | 6.7% |
| half_ppr/14 | 9.1% | 7.0% | 46.4% | 44.3% | 37.5% | 42.0% | 7.1% | 6.7% |
| ppr/8 | 6.2% | 5.7% | 45.1% | 44.4% | 40.9% | 42.6% | 7.8% | 7.4% |
| ppr/10 | 5.4% | 6.0% | 47.0% | 45.1% | 39.7% | 42.0% | 7.9% | 6.9% |
| ppr/12 | 7.2% | 6.5% | 42.1% | 42.6% | 43.3% | 43.8% | 7.4% | 7.1% |
| ppr/14 | 8.1% | 6.6% | 41.7% | 41.6% | 41.2% | 44.3% | 9.0% | 7.5% |

## Sensitivity at 12-team full PPR (option A)

| Case | QB bench | RB bench | WR bench | TE bench | Overall | Fill-state share | QB price | RB price | WR price | TE price | RB top-12 share | WR top-12 share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| recommended (share form) | 22.6% | 9.1% | 6.2% | 12.4% | 8.9% | 5.3% | 2.1x | 1.7x | 3.0x | 1.4x | 56.2% | 48.3% |
| recommended, convex option form | 24.7% | 11.3% | 8.7% | 16.6% | 11.7% | 3.3% | 1.4x | 1.3x | 1.9x | 0.8x | 53.0% | 44.7% |
| convex option form, sigma x 0.5 | 23.5% | 10.1% | 7.4% | 14.9% | 10.3% | 3.5% | 1.8x | 1.6x | 2.5x | 1.1x | 53.8% | 45.5% |
| m x 0.5 | 22.6% | 8.5% | 5.7% | 12.2% | 8.5% | 3.9% | 2.1x | 1.8x | 3.2x | 1.5x | 56.9% | 48.9% |
| m x 0.75 | 22.6% | 8.8% | 5.9% | 12.3% | 8.7% | 4.6% | 2.1x | 1.7x | 3.1x | 1.5x | 56.5% | 48.6% |
| m x 1.25 | 22.6% | 9.4% | 6.4% | 12.5% | 9.1% | 6.0% | 2.1x | 1.6x | 2.9x | 1.4x | 55.8% | 48.1% |
| m x 1.5 | 22.7% | 9.6% | 6.6% | 12.5% | 9.3% | 6.6% | 2.1x | 1.5x | 2.8x | 1.4x | 55.5% | 47.8% |
| sigma x 0.0 | 22.4% | 8.6% | 5.9% | 11.7% | 8.6% | 4.9% | 1.8x | 1.7x | 3.0x | 2.3x | 55.5% | 47.5% |
| sigma x 0.25 | 22.6% | 8.8% | 5.9% | 12.4% | 8.7% | 4.8% | 1.9x | 1.7x | 3.2x | 1.6x | 55.5% | 47.6% |
| sigma x 0.5 | 22.5% | 8.8% | 5.9% | 12.4% | 8.7% | 4.9% | 2.0x | 1.8x | 3.1x | 1.5x | 55.8% | 47.8% |
| sigma x 0.75 | 22.5% | 8.9% | 6.0% | 12.3% | 8.8% | 5.1% | 2.1x | 1.7x | 3.0x | 1.5x | 56.0% | 48.1% |
| sigma x 1.25 | 22.7% | 9.3% | 6.3% | 12.4% | 9.1% | 5.4% | 2.1x | 1.6x | 2.9x | 1.4x | 56.1% | 48.4% |
| sigma x 1.5 | 22.8% | 9.5% | 6.5% | 12.5% | 9.2% | 5.4% | 2.1x | 1.5x | 2.8x | 1.4x | 56.0% | 48.4% |
| first-pass assumptions (m QB 11 RB 17 WR 14 TE 13, sigma 25%) | 23.0% | 9.5% | 6.2% | 12.4% | 9.1% | 4.9% | 2.1x | 1.6x | 3.1x | 1.5x | 55.3% | 47.5% |
| lower bound: fill-in only (sigma 0) | 22.4% | 8.6% | 5.9% | 11.7% | 8.6% | 4.9% | 1.8x | 1.7x | 3.0x | 2.3x | 55.5% | 47.5% |
| upper bound: plain value above waivers (bench starts every week) | 23.9% | 13.4% | 11.2% | 15.2% | 13.3% | n/a | 1.5x | 1.0x | 1.4x | 1.0x | 50.9% | 43.0% |
| before (today) | 24.0% | 12.7% | 15.8% | 16.9% | 15.2% | n/a | 1.5x | 1.0x | 1.0x | 0.8x | 52.0% | 39.1% |

## Expected lineup share of a player's surplus (ESPN, 12-team full PPR, option A)

| Position | Rank | Player | Points per game | sigma (ppg) | Lineup share of surplus | Start-worthy part |
| --- | --- | --- | --- | --- | --- | --- |
| QB | 1 | Josh Allen | 23.84 | 3.54 | 75.4% | 74.5% |
| QB | 7 | Tyler Shough | 20.45 | 3.04 | 58.8% | 56.1% |
| QB | 12 | Dak Prescott | 19.49 | 2.89 | 50.2% | 46.7% |
| QB | 13 | Jared Goff | 18.95 | 2.81 | 44.5% | 40.7% |
| QB | 18 | Jordan Love | 18.11 | 2.69 | 35.0% | 30.7% |
| RB | 1 | Jahmyr Gibbs | 25.71 | 7.12 | 78.1% | 77.7% |
| RB | 16 | Chuba Hubbard | 14.5 | 4.02 | 71.6% | 67.0% |
| RB | 31 | Josh Jacobs | 10.43 | 2.89 | 54.4% | 40.3% |
| RB | 32 | Jordan Mason | 10.35 | 2.87 | 53.8% | 39.4% |
| RB | 37 | Alvin Kamara | 8.5 | 2.36 | 36.6% | 17.0% |
| RB | 44 | Keaton Mitchell | 7.69 | 2.13 | 27.9% | 8.4% |
| WR | 1 | Ja'Marr Chase | 21.25 | 4.6 | 80.8% | 80.5% |
| WR | 21 | Carnell Tate | 13.77 | 2.98 | 74.2% | 70.8% |
| WR | 41 | Adonai Mitchell | 10.4 | 2.25 | 52.2% | 40.7% |
| WR | 42 | Jameson Williams | 10.4 | 2.25 | 52.2% | 40.6% |
| WR | 47 | Xavier Worthy | 9.84 | 2.13 | 45.3% | 32.2% |
| WR | 54 | Ryan Flournoy | 8.67 | 1.88 | 28.8% | 14.5% |
| TE | 1 | Trey McBride | 17.16 | 3.37 | 77.2% | 77.0% |
| TE | 7 | Tyler Warren | 11.8 | 2.32 | 64.4% | 61.5% |
| TE | 12 | Juwan Johnson | 10.33 | 2.03 | 50.0% | 44.6% |
| TE | 13 | T.J. Hockenson | 9.97 | 1.96 | 45.2% | 39.1% |
| TE | 18 | Pat Freiermuth | 8.41 | 1.65 | 21.2% | 13.4% |

## Top movers, blended DDF Value, before (scaled to the pie) and after A

### standard/8

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 13.91 | 39.55 | 55.27 | +15.71 |
| Ja'Marr Chase | WR | starter | 12.33 | 33.49 | 47.07 | +13.57 |
| Puka Nacua | WR | starter | 13.72 | 35.57 | 48.5 | +12.93 |
| Amon-Ra St. Brown | WR | starter | 11.8 | 30.6 | 43.29 | +12.69 |
| CeeDee Lamb | WR | starter | 12.43 | 31.9 | 44.1 | +12.20 |
| Chris Olave | WR | starter | 10.69 | 23.9 | 33.21 | +9.32 |
| Justin Jefferson | WR | starter | 10.68 | 22.84 | 31.08 | +8.24 |
| Nico Collins | WR | starter | 10.99 | 22.53 | 30.54 | +8.01 |
| Zay Flowers | WR | starter | 10.4 | 21.58 | 29.52 | +7.94 |
| Drake London | WR | starter | 10.18 | 20.11 | 27.34 | +7.24 |
| Omarion Hampton | RB | starter | 9.83 | 20.44 | 15.41 | -5.03 |
| Rhamondre Stevenson | RB | bench | 9.37 | 14.09 | 9.1 | -4.99 |
| Christian Watson | WR | starter | 10.15 | 16.7 | 21.63 | +4.93 |
| Tetairoa McMillan | WR | starter | 10.3 | 17.36 | 22.01 | +4.65 |
| Travis Etienne | RB | bench | 8.46 | 9.9 | 5.6 | -4.29 |
| George Pickens | WR | starter | 9.24 | 14.64 | 18.9 | +4.26 |
| Josh Allen | QB | starter | 23.39 | 36.58 | 32.46 | -4.13 |
| Tee Higgins | WR | starter | 10.16 | 16.05 | 20.14 | +4.09 |
| Aaron Jones | RB | bench | 9.31 | 11.72 | 7.65 | -4.06 |
| Parker Washington | WR | starter | 9.31 | 14.35 | 18.29 | +3.93 |
| Davante Adams | WR | starter | 10.81 | 16.86 | 20.76 | +3.90 |
| Quinshon Judkins | RB | starter | 10.83 | 18.76 | 15.09 | -3.66 |
| David Montgomery | RB | starter | 10.13 | 15.29 | 11.69 | -3.60 |
| TreVeyon Henderson | RB | bench | 8.17 | 8.42 | 4.84 | -3.58 |
| DeVonta Smith | WR | starter | 9.04 | 13.59 | 17.14 | +3.54 |
| Brock Bowers | TE | starter | 9.59 | 25.19 | 28.64 | +3.46 |
| Tony Pollard | RB | starter | 10.54 | 12.14 | 8.85 | -3.29 |
| Kyle Monangai | RB | bench | 8.34 | 7.81 | 4.56 | -3.26 |
| Cam Skattebo | RB | starter | 11.62 | 22.75 | 19.54 | -3.22 |
| Jordan Mason | RB | bench | 8.7 | 6.46 | 3.35 | -3.11 |

### standard/10

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 13.91 | 42.03 | 57.34 | +15.31 |
| Ja'Marr Chase | WR | starter | 12.33 | 35.71 | 49.51 | +13.80 |
| Amon-Ra St. Brown | WR | starter | 11.8 | 33.29 | 46.21 | +12.92 |
| Puka Nacua | WR | starter | 13.72 | 37.68 | 49.92 | +12.24 |
| CeeDee Lamb | WR | starter | 12.43 | 34.64 | 46.84 | +12.20 |
| Chris Olave | WR | starter | 10.69 | 26.99 | 36.88 | +9.89 |
| Justin Jefferson | WR | starter | 10.68 | 25.69 | 34.48 | +8.78 |
| Zay Flowers | WR | starter | 10.4 | 24.56 | 33.09 | +8.53 |
| Nico Collins | WR | starter | 10.99 | 25.79 | 34.0 | +8.21 |
| Drake London | WR | starter | 10.18 | 23.32 | 31.16 | +7.84 |
| Brock Bowers | TE | starter | 9.59 | 24.2 | 30.74 | +6.54 |
| Trey McBride | TE | starter | 9.05 | 21.42 | 27.0 | +5.58 |
| RJ Harvey | RB | bench | 6.73 | 9.74 | 4.45 | -5.29 |
| Christian Watson | WR | starter | 10.15 | 19.92 | 25.14 | +5.22 |
| George Pickens | WR | starter | 9.24 | 17.63 | 22.75 | +5.12 |
| Brian Robinson | RB | bench | 6.7 | 8.29 | 3.28 | -5.02 |
| Kyle Monangai | RB | bench | 8.34 | 14.89 | 9.91 | -4.97 |
| Tetairoa McMillan | WR | starter | 10.3 | 20.12 | 25.08 | +4.96 |
| Alvin Kamara | RB | bench | 6.31 | 7.42 | 2.6 | -4.81 |
| Parker Washington | WR | starter | 9.31 | 17.38 | 22.14 | +4.76 |
| Zach Charbonnet | RB | starter | 8.64 | 12.18 | 7.45 | -4.73 |
| Jahmyr Gibbs | RB | starter | 20.2 | 75.95 | 80.67 | +4.71 |
| Tony Pollard | RB | starter | 10.54 | 19.25 | 14.54 | -4.71 |
| Rhamondre Stevenson | RB | starter | 9.37 | 20.35 | 15.66 | -4.69 |
| Josh Allen | QB | starter | 23.39 | 28.99 | 33.6 | +4.61 |
| Bijan Robinson | RB | starter | 18.52 | 70.68 | 75.24 | +4.56 |
| Travis Etienne | RB | bench | 8.46 | 15.81 | 11.42 | -4.40 |
| J.K. Dobbins | RB | starter | 8.64 | 11.65 | 7.27 | -4.39 |
| Jordan Mason | RB | starter | 8.7 | 13.0 | 8.62 | -4.39 |
| DeVonta Smith | WR | starter | 9.04 | 16.28 | 20.63 | +4.35 |

### standard/12

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 13.91 | 42.97 | 61.8 | +18.83 |
| Ja'Marr Chase | WR | starter | 12.33 | 36.64 | 53.69 | +17.05 |
| Amon-Ra St. Brown | WR | starter | 11.8 | 34.49 | 50.42 | +15.92 |
| CeeDee Lamb | WR | starter | 12.43 | 36.12 | 51.76 | +15.64 |
| Puka Nacua | WR | starter | 13.72 | 38.74 | 53.66 | +14.92 |
| Chris Olave | WR | starter | 10.69 | 28.65 | 41.49 | +12.84 |
| Justin Jefferson | WR | starter | 10.68 | 27.39 | 39.13 | +11.74 |
| Zay Flowers | WR | starter | 10.4 | 26.26 | 37.45 | +11.19 |
| Nico Collins | WR | starter | 10.99 | 27.65 | 38.43 | +10.78 |
| Drake London | WR | starter | 10.18 | 25.16 | 35.35 | +10.20 |
| Brock Bowers | TE | starter | 9.59 | 24.15 | 32.54 | +8.40 |
| Jahmyr Gibbs | RB | starter | 20.2 | 77.59 | 85.41 | +7.82 |
| Bijan Robinson | RB | starter | 18.52 | 72.5 | 80.1 | +7.59 |
| Trey McBride | TE | starter | 9.05 | 21.54 | 28.88 | +7.34 |
| George Pickens | WR | starter | 9.24 | 19.62 | 26.82 | +7.20 |
| Christian Watson | WR | starter | 10.15 | 21.98 | 28.95 | +6.97 |
| Tetairoa McMillan | WR | starter | 10.3 | 22.11 | 28.98 | +6.88 |
| Kenneth Walker III | RB | starter | 17.88 | 68.02 | 74.63 | +6.61 |
| Parker Washington | WR | starter | 9.31 | 19.38 | 25.94 | +6.57 |
| DeVonta Smith | WR | starter | 9.04 | 18.27 | 24.73 | +6.46 |
| Garrett Wilson | WR | starter | 8.74 | 17.92 | 24.18 | +6.25 |
| Tee Higgins | WR | starter | 10.16 | 21.19 | 27.39 | +6.19 |
| Jonathan Taylor | RB | starter | 16.22 | 60.46 | 66.19 | +5.73 |
| Rico Dowdle | RB | bench | 6.39 | 11.12 | 5.47 | -5.64 |
| Bryce Young | QB | bench | 17.71 | 10.34 | 4.8 | -5.54 |
| Ollie Gordon II | RB | starter | 8.69 | 18.72 | 13.19 | -5.53 |
| Brian Robinson | RB | bench | 6.7 | 12.35 | 6.92 | -5.44 |
| James Cook | RB | starter | 13.4 | 51.82 | 57.2 | +5.38 |
| Alvin Kamara | RB | bench | 6.31 | 10.79 | 5.45 | -5.34 |
| Davante Adams | WR | starter | 10.81 | 22.03 | 27.35 | +5.32 |

### standard/14

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 13.91 | 42.31 | 67.18 | +24.87 |
| Ja'Marr Chase | WR | starter | 12.33 | 36.45 | 58.79 | +22.34 |
| CeeDee Lamb | WR | starter | 12.43 | 36.07 | 56.91 | +20.84 |
| Amon-Ra St. Brown | WR | starter | 11.8 | 34.58 | 55.39 | +20.81 |
| Puka Nacua | WR | starter | 13.72 | 38.22 | 57.87 | +19.65 |
| Chris Olave | WR | starter | 10.69 | 28.97 | 46.27 | +17.29 |
| Justin Jefferson | WR | starter | 10.68 | 27.83 | 43.74 | +15.92 |
| Zay Flowers | WR | starter | 10.4 | 26.68 | 41.85 | +15.17 |
| Nico Collins | WR | starter | 10.99 | 27.88 | 42.64 | +14.75 |
| Drake London | WR | starter | 10.18 | 25.6 | 39.49 | +13.90 |
| Brock Bowers | TE | starter | 9.59 | 23.71 | 34.54 | +10.83 |
| George Pickens | WR | starter | 9.24 | 20.57 | 30.64 | +10.06 |
| Trey McBride | TE | starter | 9.05 | 21.17 | 31.05 | +9.88 |
| Christian Watson | WR | starter | 10.15 | 22.56 | 32.24 | +9.68 |
| Tetairoa McMillan | WR | starter | 10.3 | 22.77 | 32.27 | +9.50 |
| Parker Washington | WR | starter | 9.31 | 20.19 | 29.4 | +9.21 |
| DeVonta Smith | WR | starter | 9.04 | 19.44 | 28.56 | +9.12 |
| Garrett Wilson | WR | starter | 8.74 | 19.12 | 28.04 | +8.91 |
| Tee Higgins | WR | starter | 10.16 | 21.98 | 30.68 | +8.71 |
| Bijan Robinson | RB | starter | 18.52 | 77.46 | 85.6 | +8.14 |
| Jahmyr Gibbs | RB | starter | 20.2 | 82.85 | 90.83 | +7.97 |
| Davante Adams | WR | starter | 10.81 | 22.42 | 30.02 | +7.60 |
| Malik Nabers | WR | starter | 7.7 | 16.04 | 23.5 | +7.46 |
| Kenneth Walker III | RB | starter | 17.88 | 72.44 | 79.66 | +7.22 |
| A.J. Brown | WR | starter | 8.65 | 17.36 | 24.34 | +6.98 |
| Jayden Daniels | QB | starter | 20.07 | 17.71 | 11.14 | -6.57 |
| James Cook | RB | starter | 13.4 | 56.26 | 62.56 | +6.30 |
| Jonathan Taylor | RB | starter | 16.22 | 65.13 | 71.14 | +6.01 |
| Matthew Golden | WR | starter | 8.64 | 16.26 | 22.08 | +5.81 |
| Christian McCaffrey | RB | starter | 14.73 | 58.1 | 63.74 | +5.64 |

### half_ppr/8

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 17.24 | 41.55 | 56.68 | +15.13 |
| Ja'Marr Chase | WR | starter | 15.98 | 36.69 | 50.29 | +13.60 |
| Puka Nacua | WR | starter | 17.37 | 38.2 | 50.79 | +12.59 |
| Amon-Ra St. Brown | WR | starter | 15.32 | 33.95 | 46.48 | +12.54 |
| CeeDee Lamb | WR | starter | 15.97 | 34.93 | 46.83 | +11.90 |
| Chris Olave | WR | starter | 13.84 | 26.5 | 35.79 | +9.30 |
| Justin Jefferson | WR | starter | 13.66 | 25.0 | 33.15 | +8.15 |
| Zay Flowers | WR | starter | 12.94 | 22.66 | 30.28 | +7.62 |
| Nico Collins | WR | starter | 13.73 | 24.0 | 31.56 | +7.56 |
| Drake London | WR | starter | 12.83 | 21.7 | 28.74 | +7.04 |
| Omarion Hampton | RB | starter | 10.66 | 18.58 | 13.58 | -4.99 |
| Rhamondre Stevenson | RB | bench | 10.64 | 13.89 | 9.07 | -4.83 |
| Tetairoa McMillan | WR | starter | 13.17 | 19.15 | 23.57 | +4.42 |
| Travis Etienne | RB | bench | 9.68 | 9.93 | 5.62 | -4.31 |
| Christian Watson | WR | starter | 12.41 | 17.16 | 21.34 | +4.18 |
| Aaron Jones | RB | bench | 10.63 | 11.48 | 7.49 | -3.98 |
| Brock Bowers | TE | starter | 12.59 | 26.38 | 30.24 | +3.85 |
| George Pickens | WR | starter | 11.7 | 15.77 | 19.58 | +3.80 |
| David Montgomery | RB | starter | 11.0 | 14.11 | 10.36 | -3.75 |
| Parker Washington | WR | starter | 11.51 | 15.07 | 18.6 | +3.53 |
| DeVonta Smith | WR | starter | 11.81 | 15.49 | 18.87 | +3.38 |
| Trey McBride | TE | starter | 12.72 | 24.86 | 28.23 | +3.37 |
| Quinshon Judkins | RB | starter | 12.4 | 18.69 | 15.32 | -3.37 |
| TreVeyon Henderson | RB | bench | 8.84 | 7.32 | 3.96 | -3.35 |
| Tee Higgins | WR | starter | 12.81 | 17.31 | 20.65 | +3.34 |
| Tony Pollard | RB | starter | 11.65 | 11.24 | 7.96 | -3.28 |
| Kyle Monangai | RB | bench | 8.94 | 6.62 | 3.4 | -3.22 |
| Garrett Wilson | WR | starter | 11.61 | 15.19 | 18.39 | +3.19 |
| Cam Skattebo | RB | starter | 12.78 | 21.74 | 18.56 | -3.19 |
| Jordan Mason | RB | bench | 9.25 | 5.2 | 2.16 | -3.04 |

### half_ppr/10

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 17.24 | 44.2 | 59.11 | +14.91 |
| Ja'Marr Chase | WR | starter | 15.98 | 39.1 | 52.77 | +13.66 |
| Amon-Ra St. Brown | WR | starter | 15.32 | 36.84 | 49.51 | +12.68 |
| Puka Nacua | WR | starter | 17.37 | 40.36 | 52.42 | +12.06 |
| CeeDee Lamb | WR | starter | 15.97 | 37.84 | 49.72 | +11.88 |
| Chris Olave | WR | starter | 13.84 | 29.9 | 39.56 | +9.66 |
| Justin Jefferson | WR | starter | 13.66 | 28.12 | 36.81 | +8.69 |
| Zay Flowers | WR | starter | 12.94 | 26.03 | 34.28 | +8.25 |
| Nico Collins | WR | starter | 13.73 | 27.42 | 35.28 | +7.86 |
| Drake London | WR | starter | 12.83 | 25.23 | 32.81 | +7.59 |
| Josh Allen | QB | starter | 23.39 | 24.99 | 31.54 | +6.55 |
| Brock Bowers | TE | starter | 12.59 | 25.88 | 31.7 | +5.81 |
| Trey McBride | TE | starter | 12.72 | 24.63 | 29.62 | +4.99 |
| Tetairoa McMillan | WR | starter | 13.17 | 22.16 | 27.02 | +4.87 |
| George Pickens | WR | starter | 11.7 | 19.2 | 23.92 | +4.72 |
| Christian Watson | WR | starter | 12.41 | 20.6 | 25.32 | +4.72 |
| Rome Odunze | WR | bench | 8.47 | 9.51 | 4.9 | -4.61 |
| Parker Washington | WR | starter | 11.51 | 18.45 | 22.93 | +4.48 |
| Josh Downs | WR | bench | 8.62 | 8.75 | 4.33 | -4.42 |
| RJ Harvey | RB | bench | 8.7 | 10.77 | 6.39 | -4.38 |
| DeVonta Smith | WR | starter | 11.81 | 18.61 | 22.88 | +4.27 |
| Garrett Wilson | WR | starter | 11.61 | 18.6 | 22.81 | +4.21 |
| Romeo Doubs | WR | bench | 7.81 | 5.92 | 1.92 | -4.00 |
| Stefon Diggs | WR | bench | 8.73 | 8.49 | 4.51 | -3.98 |
| Tee Higgins | WR | starter | 12.81 | 20.55 | 24.43 | +3.88 |
| Alvin Kamara | RB | bench | 7.52 | 6.9 | 3.04 | -3.87 |
| Jordan Addison | WR | bench | 8.03 | 6.04 | 2.42 | -3.62 |
| Brian Robinson | RB | bench | 7.03 | 5.77 | 2.17 | -3.61 |
| Kyle Monangai | RB | bench | 8.94 | 12.0 | 8.43 | -3.57 |
| Jakobi Meyers | WR | bench | 8.63 | 6.82 | 3.29 | -3.52 |

### half_ppr/12

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 17.24 | 45.09 | 64.05 | +18.96 |
| Ja'Marr Chase | WR | starter | 15.98 | 40.16 | 57.19 | +17.03 |
| Amon-Ra St. Brown | WR | starter | 15.32 | 38.04 | 54.01 | +15.96 |
| CeeDee Lamb | WR | starter | 15.97 | 39.36 | 55.02 | +15.65 |
| Puka Nacua | WR | starter | 17.37 | 41.48 | 56.48 | +15.00 |
| Chris Olave | WR | starter | 13.84 | 31.69 | 44.49 | +12.80 |
| Justin Jefferson | WR | starter | 13.66 | 30.08 | 41.72 | +11.64 |
| Zay Flowers | WR | starter | 12.94 | 28.0 | 38.97 | +10.97 |
| Nico Collins | WR | starter | 13.73 | 29.43 | 40.05 | +10.62 |
| Drake London | WR | starter | 12.83 | 27.24 | 37.36 | +10.12 |
| Brock Bowers | TE | starter | 12.59 | 25.65 | 33.28 | +7.64 |
| Trey McBride | TE | starter | 12.72 | 24.63 | 31.47 | +6.85 |
| George Pickens | WR | starter | 11.7 | 21.44 | 28.17 | +6.72 |
| Tetairoa McMillan | WR | starter | 13.17 | 24.47 | 31.16 | +6.69 |
| Christian Watson | WR | starter | 12.41 | 22.88 | 29.46 | +6.58 |
| Parker Washington | WR | starter | 11.51 | 20.75 | 27.03 | +6.28 |
| Garrett Wilson | WR | starter | 11.61 | 21.1 | 27.32 | +6.22 |
| DeVonta Smith | WR | starter | 11.81 | 20.97 | 27.16 | +6.19 |
| Bijan Robinson | RB | starter | 20.27 | 70.53 | 76.4 | +5.87 |
| Jahmyr Gibbs | RB | starter | 22.48 | 76.51 | 82.29 | +5.78 |
| Tee Higgins | WR | starter | 12.81 | 22.87 | 28.58 | +5.72 |
| Kenneth Walker III | RB | starter | 19.41 | 65.31 | 70.72 | +5.41 |
| Bryce Young | QB | bench | 17.71 | 9.49 | 4.51 | -4.98 |
| Davante Adams | WR | starter | 13.32 | 22.93 | 27.74 | +4.82 |
| Malik Nabers | WR | starter | 9.89 | 16.83 | 21.59 | +4.76 |
| James Cook | RB | starter | 14.3 | 48.39 | 52.92 | +4.53 |
| Rico Dowdle | RB | bench | 7.25 | 9.47 | 4.95 | -4.52 |
| Brian Robinson | RB | bench | 7.03 | 9.43 | 5.01 | -4.41 |
| Jonathan Taylor | RB | starter | 17.47 | 57.83 | 62.17 | +4.34 |
| Keaton Mitchell | RB | bench | 6.85 | 8.01 | 3.67 | -4.34 |

### half_ppr/14

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 17.24 | 46.89 | 69.85 | +22.96 |
| Ja'Marr Chase | WR | starter | 15.98 | 42.02 | 62.4 | +20.38 |
| CeeDee Lamb | WR | starter | 15.97 | 41.2 | 60.37 | +19.17 |
| Amon-Ra St. Brown | WR | starter | 15.32 | 40.05 | 59.22 | +19.17 |
| Puka Nacua | WR | starter | 17.37 | 42.74 | 60.92 | +18.18 |
| Chris Olave | WR | starter | 13.84 | 33.72 | 49.58 | +15.86 |
| Justin Jefferson | WR | starter | 13.66 | 32.01 | 46.59 | +14.58 |
| Zay Flowers | WR | starter | 12.94 | 30.07 | 43.77 | +13.71 |
| Nico Collins | WR | starter | 13.73 | 31.25 | 44.68 | +13.43 |
| Drake London | WR | starter | 12.83 | 29.28 | 41.97 | +12.69 |
| George Pickens | WR | starter | 11.7 | 23.37 | 32.32 | +8.95 |
| Tetairoa McMillan | WR | starter | 13.17 | 25.98 | 34.61 | +8.64 |
| Christian Watson | WR | starter | 12.41 | 24.61 | 33.15 | +8.54 |
| Parker Washington | WR | starter | 11.51 | 22.7 | 30.99 | +8.29 |
| DeVonta Smith | WR | starter | 11.81 | 22.77 | 30.93 | +8.17 |
| Garrett Wilson | WR | starter | 11.61 | 23.09 | 31.22 | +8.13 |
| Bijan Robinson | RB | starter | 20.27 | 73.59 | 81.53 | +7.93 |
| Tee Higgins | WR | starter | 12.81 | 24.37 | 32.17 | +7.80 |
| Jahmyr Gibbs | RB | starter | 22.48 | 79.75 | 87.3 | +7.55 |
| Brock Bowers | TE | starter | 12.59 | 28.28 | 35.72 | +7.45 |
| Kenneth Walker III | RB | starter | 19.41 | 68.26 | 75.44 | +7.18 |
| Trey McBride | TE | starter | 12.72 | 27.22 | 33.95 | +6.72 |
| Davante Adams | WR | starter | 13.32 | 24.15 | 30.83 | +6.68 |
| James Cook | RB | starter | 14.3 | 51.33 | 57.89 | +6.57 |
| Malik Nabers | WR | starter | 9.89 | 19.18 | 25.74 | +6.56 |
| A.J. Brown | WR | starter | 10.99 | 19.87 | 26.09 | +6.21 |
| Jonathan Taylor | RB | starter | 17.47 | 60.6 | 66.79 | +6.19 |
| Christian McCaffrey | RB | starter | 16.75 | 55.91 | 61.62 | +5.71 |
| Keon Coleman | WR | bench | 6.96 | 9.38 | 4.26 | -5.12 |
| Michael Wilson | WR | starter | 10.95 | 19.05 | 24.11 | +5.06 |

### ppr/8

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 20.57 | 46.57 | 57.75 | +11.19 |
| Ja'Marr Chase | WR | starter | 19.6 | 41.96 | 51.97 | +10.01 |
| Puka Nacua | WR | starter | 21.02 | 42.27 | 52.07 | +9.80 |
| Amon-Ra St. Brown | WR | starter | 18.84 | 39.59 | 48.93 | +9.35 |
| CeeDee Lamb | WR | starter | 19.51 | 39.87 | 48.72 | +8.85 |
| Chris Olave | WR | starter | 17.02 | 31.43 | 38.26 | +6.83 |
| Justin Jefferson | WR | starter | 16.61 | 28.91 | 34.56 | +5.65 |
| Nico Collins | WR | starter | 16.44 | 27.34 | 32.68 | +5.34 |
| Zay Flowers | WR | starter | 15.44 | 26.16 | 31.19 | +5.02 |
| Drake London | WR | starter | 15.49 | 25.57 | 30.45 | +4.88 |
| Jahmyr Gibbs | RB | starter | 24.74 | 66.56 | 70.95 | +4.40 |
| Rome Odunze | WR | bench | 10.16 | 6.06 | 1.97 | -4.09 |
| Deebo Samuel Sr. | WR | bench | 10.74 | 6.7 | 2.67 | -4.03 |
| Jameson Williams | WR | bench | 10.56 | 7.67 | 3.73 | -3.93 |
| Bijan Robinson | RB | starter | 22.01 | 59.48 | 63.33 | +3.86 |
| DK Metcalf | WR | bench | 11.98 | 8.88 | 5.1 | -3.78 |
| Stefon Diggs | WR | bench | 10.84 | 5.69 | 2.03 | -3.66 |
| Ladd McConkey | WR | bench | 11.3 | 9.83 | 6.26 | -3.57 |
| Josh Downs | WR | bench | 10.79 | 5.62 | 2.07 | -3.55 |
| Omarion Hampton | RB | bench | 11.5 | 15.54 | 12.03 | -3.51 |
| Emeka Egbuka | WR | bench | 11.23 | 8.44 | 4.95 | -3.49 |
| Jalen Coker | WR | starter | 13.0 | 11.86 | 8.43 | -3.43 |
| Rhamondre Stevenson | RB | bench | 11.88 | 11.99 | 8.63 | -3.36 |
| Tetairoa McMillan | WR | starter | 16.07 | 21.95 | 25.24 | +3.29 |
| Travis Etienne | RB | bench | 10.9 | 8.72 | 5.63 | -3.09 |
| Kenneth Walker III | RB | starter | 20.94 | 54.74 | 57.83 | +3.09 |
| Jonathan Taylor | RB | starter | 18.74 | 45.33 | 48.39 | +3.07 |
| Denzel Boston | WR | bench | 11.27 | 6.4 | 3.45 | -2.95 |
| Trey McBride | TE | starter | 16.37 | 28.14 | 30.87 | +2.73 |
| Christian Watson | WR | starter | 14.68 | 19.3 | 21.98 | +2.68 |

### ppr/10

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 20.57 | 45.56 | 60.87 | +15.31 |
| Ja'Marr Chase | WR | starter | 19.6 | 41.21 | 55.16 | +13.94 |
| Amon-Ra St. Brown | WR | starter | 18.84 | 39.22 | 52.21 | +12.99 |
| Puka Nacua | WR | starter | 21.02 | 41.75 | 54.59 | +12.85 |
| CeeDee Lamb | WR | starter | 19.51 | 39.82 | 52.03 | +12.21 |
| Chris Olave | WR | starter | 17.02 | 32.22 | 41.89 | +9.66 |
| Justin Jefferson | WR | starter | 16.61 | 29.88 | 38.54 | +8.67 |
| Zay Flowers | WR | starter | 15.44 | 27.37 | 35.24 | +7.88 |
| Josh Allen | QB | starter | 23.39 | 22.22 | 30.05 | +7.82 |
| Nico Collins | WR | starter | 16.44 | 28.65 | 36.45 | +7.79 |
| Drake London | WR | starter | 15.49 | 26.92 | 34.33 | +7.41 |
| Stefon Diggs | WR | bench | 10.84 | 11.54 | 5.59 | -5.95 |
| Rome Odunze | WR | bench | 10.16 | 11.16 | 5.51 | -5.65 |
| Tetairoa McMillan | WR | starter | 16.07 | 23.74 | 28.93 | +5.19 |
| Romeo Doubs | WR | bench | 9.33 | 6.94 | 2.2 | -4.74 |
| Christian Watson | WR | starter | 14.68 | 21.33 | 25.86 | +4.53 |
| George Pickens | WR | starter | 14.2 | 20.63 | 25.11 | +4.49 |
| Josh Downs | WR | bench | 10.79 | 10.13 | 5.74 | -4.39 |
| Jakobi Meyers | WR | bench | 10.5 | 8.42 | 4.06 | -4.36 |
| Garrett Wilson | WR | starter | 14.5 | 20.89 | 25.19 | +4.30 |
| DeVonta Smith | WR | starter | 14.61 | 20.44 | 24.73 | +4.29 |
| Jordan Addison | WR | bench | 9.61 | 7.01 | 2.8 | -4.21 |
| Parker Washington | WR | starter | 13.71 | 19.68 | 23.86 | +4.19 |
| Tee Higgins | WR | starter | 15.45 | 21.63 | 25.73 | +4.10 |
| Wan'Dale Robinson | WR | bench | 9.42 | 5.74 | 1.76 | -3.98 |
| Jordyn Tyson | WR | waiver | 7.43 | 5.15 | 1.43 | -3.72 |
| Davante Adams | WR | starter | 15.83 | 21.05 | 24.66 | +3.60 |
| Brian Thomas Jr. | WR | bench | 9.04 | 5.42 | 1.92 | -3.50 |
| Lamar Jackson | QB | waiver | 17.17 | 10.83 | 14.32 | +3.49 |
| Chris Godwin | WR | bench | 8.88 | 5.17 | 1.69 | -3.48 |

### ppr/12

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 20.57 | 50.85 | 66.09 | +15.23 |
| Ja'Marr Chase | WR | starter | 19.6 | 46.32 | 59.86 | +13.54 |
| Amon-Ra St. Brown | WR | starter | 18.84 | 44.12 | 56.93 | +12.81 |
| CeeDee Lamb | WR | starter | 19.51 | 45.19 | 57.61 | +12.42 |
| Puka Nacua | WR | starter | 21.02 | 46.82 | 58.89 | +12.06 |
| Chris Olave | WR | starter | 17.02 | 36.94 | 47.22 | +10.27 |
| Justin Jefferson | WR | starter | 16.61 | 34.73 | 43.88 | +9.15 |
| Zay Flowers | WR | starter | 15.44 | 31.87 | 40.49 | +8.62 |
| Nico Collins | WR | starter | 16.44 | 33.27 | 41.64 | +8.37 |
| Drake London | WR | starter | 15.49 | 31.32 | 39.43 | +8.11 |
| Romeo Doubs | WR | bench | 9.33 | 13.2 | 5.31 | -7.89 |
| Jahmyr Gibbs | RB | starter | 24.74 | 72.2 | 79.67 | +7.47 |
| Bijan Robinson | RB | starter | 22.01 | 65.63 | 72.97 | +7.34 |
| Kalif Raymond | WR | bench | 7.37 | 8.1 | 0.83 | -7.28 |
| Kenneth Walker III | RB | starter | 20.94 | 60.13 | 67.05 | +6.91 |
| Jonathan Taylor | RB | starter | 18.74 | 52.86 | 58.54 | +5.67 |
| Christian McCaffrey | RB | starter | 18.77 | 49.91 | 55.45 | +5.54 |
| Brian Thomas Jr. | WR | bench | 9.04 | 10.17 | 4.68 | -5.49 |
| Brock Bowers | TE | starter | 15.58 | 28.52 | 33.89 | +5.38 |
| James Cook | RB | starter | 15.24 | 43.47 | 48.8 | +5.32 |
| Malik Washington | WR | starter | 10.27 | 11.11 | 5.85 | -5.26 |
| Tetairoa McMillan | WR | starter | 16.07 | 28.15 | 33.4 | +5.25 |
| George Pickens | WR | starter | 14.2 | 24.57 | 29.66 | +5.10 |
| Derrick Henry | RB | starter | 18.38 | 48.12 | 53.17 | +5.05 |
| Christian Watson | WR | starter | 14.68 | 25.39 | 30.43 | +5.04 |
| Tre Tucker | WR | bench | 9.02 | 7.65 | 2.71 | -4.95 |
| Parker Washington | WR | starter | 13.71 | 23.63 | 28.52 | +4.89 |
| Chris Godwin | WR | bench | 8.88 | 9.48 | 4.61 | -4.87 |
| Trey McBride | TE | starter | 16.37 | 28.44 | 33.3 | +4.87 |
| Garrett Wilson | WR | starter | 14.5 | 25.25 | 30.08 | +4.84 |

### ppr/14

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 20.57 | 51.84 | 71.33 | +19.49 |
| Ja'Marr Chase | WR | starter | 19.6 | 47.2 | 64.45 | +17.25 |
| Amon-Ra St. Brown | WR | starter | 18.84 | 45.24 | 61.59 | +16.35 |
| CeeDee Lamb | WR | starter | 19.51 | 46.17 | 62.47 | +16.30 |
| Puka Nacua | WR | starter | 21.02 | 47.28 | 62.97 | +15.69 |
| Chris Olave | WR | starter | 17.02 | 38.25 | 51.82 | +13.57 |
| Justin Jefferson | WR | starter | 16.61 | 35.87 | 48.27 | +12.41 |
| Zay Flowers | WR | starter | 15.44 | 33.36 | 44.9 | +11.53 |
| Nico Collins | WR | starter | 16.44 | 34.52 | 45.9 | +11.39 |
| Drake London | WR | starter | 15.49 | 32.85 | 43.7 | +10.85 |
| Bijan Robinson | RB | starter | 22.01 | 68.36 | 77.78 | +9.42 |
| Jahmyr Gibbs | RB | starter | 24.74 | 74.97 | 84.16 | +9.19 |
| Kenneth Walker III | RB | starter | 20.94 | 63.06 | 71.68 | +8.62 |
| Tetairoa McMillan | WR | starter | 16.07 | 29.03 | 36.68 | +7.65 |
| Jonathan Taylor | RB | starter | 18.74 | 55.21 | 62.82 | +7.61 |
| James Cook | RB | starter | 15.24 | 46.12 | 53.65 | +7.53 |
| George Pickens | WR | starter | 14.2 | 25.93 | 33.43 | +7.50 |
| Christian Watson | WR | starter | 14.68 | 26.73 | 33.94 | +7.21 |
| Parker Washington | WR | starter | 13.71 | 25.15 | 32.26 | +7.11 |
| Garrett Wilson | WR | starter | 14.5 | 26.56 | 33.65 | +7.10 |
| Christian McCaffrey | RB | starter | 18.77 | 52.73 | 59.71 | +6.98 |
| DeVonta Smith | WR | starter | 14.61 | 25.65 | 32.62 | +6.97 |
| Tee Higgins | WR | starter | 15.45 | 26.67 | 33.38 | +6.71 |
| Derrick Henry | RB | starter | 18.38 | 50.68 | 57.23 | +6.55 |
| Davante Adams | WR | starter | 15.83 | 25.93 | 31.74 | +5.81 |
| Brock Bowers | TE | starter | 15.58 | 32.29 | 37.88 | +5.59 |
| Malik Nabers | WR | starter | 12.11 | 22.13 | 27.68 | +5.56 |
| Chase Brown | RB | starter | 17.11 | 44.18 | 49.66 | +5.48 |
| Javonte Williams | RB | starter | 16.78 | 43.3 | 48.67 | +5.36 |
| Kyren Williams | RB | starter | 17.42 | 45.67 | 51.03 | +5.36 |
