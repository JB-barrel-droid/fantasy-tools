# Expected-starts value: before and after, all 12 settings

Produced by `pipelines/expected_starts_model.py` on the Week 5 build. Before = today's live values (two-tier at the 15% bench share, ESPN anchored), scaled to the fixed pie. After A = expected-starts replaces the slices (ES-4 to ES-6). After B = slices kept, bench budget set from A. Bench-tier share = the pie held by players ranked past the starters on the mean projection. Price ratio = median value per point above waivers, starters over bench tier.

Parameters: QB m 11.8%, sigma 17.8%, floor 0.69; RB m 14.4%, sigma 28.5%, floor 0.84; WR m 11.8%, sigma 30.0%, floor 0.99; TE m 15.1%, sigma 35.0%, floor 0.65; bye share 7.8%.

## Bench-tier share and starter/bench price, per setting

| Setting | Variant | QB bench | RB bench | WR bench | TE bench | Overall | Fill-state share | QB price | RB price | WR price | TE price | Inversions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| standard/8 | before | 15.0% | 10.0% | 17.9% | 17.9% | 13.5% | n/a | 1.2x | 1.5x | 0.8x | 0.9x | n/a |
| standard/8 | after A | 12.3% | 6.4% | 11.7% | 14.4% | 9.3% | 5.9% | 1.4x | 2.8x | 1.6x | 1.1x | 0 |
| standard/8 | after A-option | 17.3% | 8.8% | 16.4% | 19.4% | 13.3% | 3.9% | 1.0x | 1.6x | 0.9x | 0.8x | 0 |
| standard/8 | after B | 12.2% | 5.8% | 11.1% | 13.9% | 8.9% | n/a | 1.4x | 2.5x | 1.3x | 1.2x | 0 |
| standard/10 | before | 13.8% | 12.7% | 16.5% | 17.0% | 14.3% | n/a | 1.1x | 1.0x | 1.0x | 1.1x | n/a |
| standard/10 | after A | 10.6% | 7.7% | 10.1% | 13.2% | 9.1% | 6.1% | 1.3x | 2.0x | 2.3x | 1.5x | 0 |
| standard/10 | after A-option | 15.0% | 9.7% | 14.4% | 17.4% | 12.5% | 3.9% | 1.0x | 1.4x | 1.2x | 0.9x | 0 |
| standard/10 | after B | 10.7% | 7.1% | 9.7% | 13.1% | 8.8% | n/a | 1.2x | 1.9x | 2.1x | 1.5x | 0 |
| standard/12 | before | 23.8% | 12.2% | 15.1% | 15.2% | 14.4% | n/a | 1.4x | 1.1x | 1.1x | 0.7x | n/a |
| standard/12 | after A | 22.7% | 6.8% | 7.7% | 9.9% | 8.5% | 5.2% | 2.1x | 2.2x | 2.7x | 1.2x | 0 |
| standard/12 | after A-option | 25.0% | 8.3% | 11.3% | 14.8% | 11.5% | 3.2% | 1.4x | 1.7x | 1.6x | 0.7x | 0 |
| standard/12 | after B | 22.4% | 5.8% | 7.5% | 9.2% | 8.0% | n/a | 2.0x | 2.4x | 2.9x | 1.3x | 0 |
| standard/14 | before | 21.6% | 13.2% | 16.0% | 15.0% | 15.1% | n/a | 1.1x | 0.9x | 0.9x | 0.7x | n/a |
| standard/14 | after A | 20.8% | 7.6% | 7.7% | 9.2% | 8.7% | 5.2% | 2.0x | 1.9x | 2.0x | 1.5x | 0 |
| standard/14 | after A-option | 22.6% | 8.8% | 10.5% | 14.7% | 11.1% | 3.2% | 1.2x | 1.6x | 1.3x | 0.7x | 0 |
| standard/14 | after B | 19.8% | 6.8% | 6.7% | 8.7% | 8.0% | n/a | 2.2x | 2.1x | 2.3x | 1.7x | 0 |
| half_ppr/8 | before | 15.1% | 9.8% | 18.1% | 17.7% | 13.6% | n/a | 1.2x | 1.6x | 0.8x | 1.0x | n/a |
| half_ppr/8 | after A | 12.3% | 5.9% | 11.9% | 14.4% | 9.2% | 5.8% | 1.4x | 3.6x | 1.4x | 1.2x | 0 |
| half_ppr/8 | after A-option | 17.3% | 8.5% | 16.6% | 19.6% | 13.4% | 3.8% | 1.0x | 1.8x | 0.9x | 0.9x | 0 |
| half_ppr/8 | after B | 12.3% | 5.4% | 11.2% | 14.1% | 8.9% | n/a | 1.4x | 3.4x | 1.5x | 1.2x | 0 |
| half_ppr/10 | before | 13.6% | 11.5% | 16.8% | 16.7% | 13.9% | n/a | 1.2x | 1.2x | 0.8x | 1.1x | n/a |
| half_ppr/10 | after A | 10.6% | 7.5% | 9.6% | 12.9% | 8.9% | 5.8% | 1.3x | 2.1x | 2.1x | 1.3x | 0 |
| half_ppr/10 | after A-option | 15.0% | 9.8% | 13.8% | 17.2% | 12.4% | 3.7% | 1.0x | 1.6x | 1.2x | 1.0x | 0 |
| half_ppr/10 | after B | 10.7% | 6.9% | 9.3% | 12.5% | 8.5% | n/a | 1.2x | 2.1x | 2.0x | 1.4x | 0 |
| half_ppr/12 | before | 23.9% | 11.7% | 16.4% | 17.0% | 14.7% | n/a | 1.4x | 1.2x | 1.0x | 0.8x | n/a |
| half_ppr/12 | after A | 22.7% | 6.9% | 8.1% | 12.1% | 8.8% | 5.1% | 2.1x | 2.2x | 2.4x | 1.1x | 0 |
| half_ppr/12 | after A-option | 25.0% | 8.7% | 11.7% | 17.8% | 12.0% | 3.0% | 1.4x | 1.6x | 1.5x | 0.6x | 0 |
| half_ppr/12 | after B | 22.4% | 6.8% | 8.2% | 11.8% | 8.9% | n/a | 2.0x | 2.1x | 2.3x | 1.2x | 0 |
| half_ppr/14 | before | 21.6% | 12.7% | 16.1% | 14.9% | 14.9% | n/a | 1.1x | 1.2x | 0.8x | 0.7x | n/a |
| half_ppr/14 | after A | 20.8% | 8.2% | 7.2% | 9.6% | 8.7% | 5.2% | 2.0x | 1.9x | 2.1x | 1.3x | 0 |
| half_ppr/14 | after A-option | 22.6% | 9.6% | 9.9% | 14.9% | 11.2% | 3.2% | 1.2x | 1.6x | 1.4x | 0.6x | 0 |
| half_ppr/14 | after B | 19.8% | 7.4% | 6.1% | 9.0% | 8.0% | n/a | 2.2x | 2.2x | 2.3x | 1.3x | 0 |
| ppr/8 | before | 15.0% | 11.7% | 16.5% | 17.6% | 14.3% | n/a | 1.2x | 1.5x | 0.9x | 0.9x | n/a |
| ppr/8 | after A | 12.4% | 8.2% | 10.0% | 14.8% | 9.7% | 5.7% | 1.4x | 2.8x | 1.6x | 1.1x | 0 |
| ppr/8 | after A-option | 17.4% | 11.0% | 14.4% | 19.8% | 13.7% | 3.8% | 1.0x | 1.6x | 1.0x | 0.9x | 0 |
| ppr/8 | after B | 12.3% | 7.6% | 9.4% | 14.0% | 9.2% | n/a | 1.4x | 2.7x | 1.7x | 1.2x | 0 |
| ppr/10 | before | 13.5% | 11.2% | 16.6% | 16.7% | 13.9% | n/a | 1.2x | 1.4x | 0.8x | 1.8x | n/a |
| ppr/10 | after A | 10.6% | 7.9% | 8.1% | 13.0% | 8.5% | 5.6% | 1.3x | 2.4x | 2.2x | 2.3x | 0 |
| ppr/10 | after A-option | 15.0% | 10.4% | 12.2% | 17.7% | 12.1% | 3.5% | 1.0x | 1.7x | 1.1x | 0.9x | 0 |
| ppr/10 | after B | 10.7% | 7.5% | 7.9% | 12.4% | 8.2% | n/a | 1.3x | 2.3x | 2.0x | 2.4x | 0 |
| ppr/12 | before | 24.0% | 12.7% | 15.8% | 16.9% | 15.2% | n/a | 1.5x | 1.0x | 1.0x | 0.8x | n/a |
| ppr/12 | after A | 22.7% | 9.1% | 6.4% | 12.6% | 9.1% | 5.3% | 2.1x | 1.6x | 2.8x | 1.3x | 0 |
| ppr/12 | after A-option | 25.0% | 11.4% | 9.7% | 18.3% | 12.3% | 3.1% | 1.4x | 1.2x | 1.6x | 0.7x | 0 |
| ppr/12 | after B | 22.4% | 8.8% | 6.4% | 13.2% | 9.0% | n/a | 2.0x | 1.7x | 2.7x | 1.3x | 0 |
| ppr/14 | before | 21.6% | 12.7% | 14.4% | 17.5% | 14.5% | n/a | 1.2x | 1.2x | 0.8x | 0.5x | n/a |
| ppr/14 | after A | 20.8% | 8.0% | 6.9% | 10.6% | 8.6% | 5.1% | 2.0x | 2.0x | 2.0x | 1.1x | 0 |
| ppr/14 | after A-option | 22.6% | 9.7% | 9.6% | 15.3% | 11.1% | 3.1% | 1.2x | 1.7x | 1.3x | 0.7x | 0 |
| ppr/14 | after B | 19.8% | 7.5% | 5.9% | 9.6% | 7.9% | n/a | 2.2x | 2.3x | 2.2x | 1.2x | 0 |

## Position shares of the pie (blended DDF Value)

| Setting | QB before | QB after A | RB before | RB after A | WR before | WR after A | TE before | TE after A |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| standard/8 | 8.0% | 6.4% | 53.3% | 49.8% | 32.0% | 37.5% | 6.7% | 6.2% |
| standard/10 | 7.0% | 6.7% | 54.3% | 50.8% | 32.4% | 36.4% | 6.3% | 6.1% |
| standard/12 | 9.2% | 7.3% | 52.5% | 49.0% | 32.1% | 37.5% | 6.2% | 6.2% |
| standard/14 | 10.5% | 7.5% | 51.9% | 48.0% | 31.7% | 38.4% | 5.9% | 6.1% |
| half_ppr/8 | 7.2% | 6.1% | 50.8% | 47.7% | 34.7% | 39.6% | 7.2% | 6.7% |
| half_ppr/10 | 6.1% | 6.3% | 51.1% | 48.3% | 36.0% | 39.0% | 6.8% | 6.4% |
| half_ppr/12 | 8.2% | 6.9% | 48.8% | 46.3% | 36.2% | 40.3% | 6.8% | 6.5% |
| half_ppr/14 | 9.1% | 7.0% | 46.4% | 44.8% | 37.5% | 41.7% | 7.1% | 6.5% |
| ppr/8 | 6.2% | 5.7% | 45.1% | 45.0% | 40.9% | 42.1% | 7.8% | 7.1% |
| ppr/10 | 5.4% | 6.0% | 47.0% | 45.7% | 39.7% | 41.6% | 7.9% | 6.6% |
| ppr/12 | 7.2% | 6.4% | 42.1% | 43.2% | 43.3% | 43.5% | 7.4% | 6.8% |
| ppr/14 | 8.1% | 6.6% | 41.7% | 42.1% | 41.2% | 44.0% | 9.0% | 7.3% |

## Sensitivity at 12-team full PPR (option A)

| Case | QB bench | RB bench | WR bench | TE bench | Overall | Fill-state share | QB price | RB price | WR price | TE price | RB top-12 share | WR top-12 share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| recommended (share form) | 22.7% | 9.1% | 6.4% | 12.6% | 9.1% | 5.3% | 2.1x | 1.6x | 2.8x | 1.3x | 56.1% | 48.4% |
| recommended, convex option form | 25.0% | 11.4% | 9.7% | 18.3% | 12.3% | 3.1% | 1.4x | 1.2x | 1.6x | 0.7x | 52.9% | 43.8% |
| convex option form, sigma x 0.5 | 23.8% | 10.2% | 7.9% | 16.3% | 10.7% | 3.4% | 1.7x | 1.6x | 2.2x | 0.9x | 53.8% | 45.3% |
| m x 0.5 | 22.6% | 8.6% | 6.0% | 12.5% | 8.7% | 3.9% | 2.1x | 1.8x | 3.0x | 1.4x | 56.9% | 49.0% |
| m x 0.75 | 22.7% | 8.9% | 6.2% | 12.6% | 8.9% | 4.6% | 2.1x | 1.7x | 2.9x | 1.3x | 56.5% | 48.7% |
| m x 1.25 | 22.7% | 9.4% | 6.6% | 12.7% | 9.2% | 6.0% | 2.1x | 1.6x | 2.7x | 1.3x | 55.8% | 48.2% |
| m x 1.5 | 22.7% | 9.6% | 6.8% | 12.8% | 9.4% | 6.7% | 2.1x | 1.5x | 2.6x | 1.3x | 55.5% | 47.9% |
| sigma x 0.0 | 22.4% | 8.6% | 5.9% | 11.7% | 8.6% | 4.9% | 1.8x | 1.7x | 3.0x | 2.3x | 55.5% | 47.5% |
| sigma x 0.25 | 22.6% | 8.8% | 5.9% | 12.4% | 8.7% | 4.8% | 2.0x | 1.8x | 3.1x | 1.5x | 55.5% | 47.6% |
| sigma x 0.5 | 22.5% | 8.8% | 6.0% | 12.3% | 8.7% | 5.0% | 2.1x | 1.8x | 3.1x | 1.5x | 55.8% | 48.0% |
| sigma x 0.75 | 22.6% | 9.0% | 6.2% | 12.5% | 8.9% | 5.2% | 2.1x | 1.7x | 3.0x | 1.4x | 56.1% | 48.4% |
| sigma x 1.25 | 22.8% | 9.3% | 6.6% | 12.8% | 9.3% | 5.3% | 2.1x | 1.6x | 2.7x | 1.3x | 56.1% | 48.4% |
| sigma x 1.5 | 22.9% | 9.5% | 6.8% | 13.0% | 9.4% | 5.3% | 2.0x | 1.5x | 2.6x | 1.2x | 56.0% | 48.2% |
| first-pass assumptions (m QB 11 RB 17 WR 14 TE 13, sigma 25%) | 23.0% | 9.5% | 6.2% | 12.4% | 9.1% | 4.9% | 2.1x | 1.6x | 3.1x | 1.5x | 55.3% | 47.5% |
| lower bound: fill-in only (sigma 0) | 22.4% | 8.6% | 5.9% | 11.7% | 8.6% | 4.9% | 1.8x | 1.7x | 3.0x | 2.3x | 55.5% | 47.5% |
| upper bound: plain value above waivers (bench starts every week) | 23.9% | 13.4% | 11.2% | 15.2% | 13.3% | n/a | 1.5x | 1.0x | 1.4x | 1.0x | 50.9% | 43.0% |
| before (today) | 24.0% | 12.7% | 15.8% | 16.9% | 15.2% | n/a | 1.5x | 1.0x | 1.0x | 0.8x | 52.0% | 39.1% |

## Expected lineup share of a player's surplus (ESPN, 12-team full PPR, option A)

| Position | Rank | Player | Points per game | sigma (ppg) | Lineup share of surplus | Start-worthy part |
| --- | --- | --- | --- | --- | --- | --- |
| QB | 1 | Josh Allen | 23.84 | 4.24 | 72.3% | 71.2% |
| QB | 7 | Tyler Shough | 20.45 | 3.64 | 56.2% | 53.7% |
| QB | 12 | Dak Prescott | 19.49 | 3.47 | 48.7% | 45.7% |
| QB | 13 | Jared Goff | 18.95 | 3.37 | 44.0% | 40.7% |
| QB | 18 | Jordan Love | 18.11 | 3.22 | 35.9% | 32.3% |
| RB | 1 | Jahmyr Gibbs | 25.71 | 7.34 | 77.9% | 77.5% |
| RB | 16 | Chuba Hubbard | 14.5 | 4.14 | 71.1% | 66.4% |
| RB | 31 | Josh Jacobs | 10.43 | 2.98 | 54.1% | 40.3% |
| RB | 32 | Jordan Mason | 10.35 | 2.95 | 53.5% | 39.4% |
| RB | 37 | Alvin Kamara | 8.5 | 2.43 | 36.6% | 17.5% |
| RB | 44 | Keaton Mitchell | 7.69 | 2.2 | 28.1% | 8.9% |
| WR | 1 | Ja'Marr Chase | 21.25 | 6.38 | 78.5% | 77.6% |
| WR | 21 | Carnell Tate | 13.77 | 4.14 | 68.5% | 64.4% |
| WR | 41 | Adonai Mitchell | 10.4 | 3.13 | 49.6% | 40.7% |
| WR | 42 | Jameson Williams | 10.4 | 3.12 | 49.6% | 40.6% |
| WR | 47 | Xavier Worthy | 9.84 | 2.96 | 44.3% | 34.5% |
| WR | 54 | Ryan Flournoy | 8.67 | 2.61 | 31.5% | 20.6% |
| TE | 1 | Trey McBride | 17.16 | 6.0 | 70.1% | 69.2% |
| TE | 7 | Tyler Warren | 11.8 | 4.13 | 55.2% | 52.5% |
| TE | 12 | Juwan Johnson | 10.33 | 3.61 | 45.8% | 42.2% |
| TE | 13 | T.J. Hockenson | 9.97 | 3.49 | 43.0% | 39.1% |
| TE | 18 | Pat Freiermuth | 8.41 | 2.94 | 28.0% | 23.3% |

## Top movers, blended DDF Value, before (scaled to the pie) and after A

### standard/8

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 13.91 | 39.55 | 54.85 | +15.29 |
| Ja'Marr Chase | WR | starter | 12.33 | 33.49 | 46.38 | +12.88 |
| Puka Nacua | WR | starter | 13.72 | 35.57 | 48.08 | +12.51 |
| Amon-Ra St. Brown | WR | starter | 11.8 | 30.6 | 42.61 | +12.01 |
| CeeDee Lamb | WR | starter | 12.43 | 31.9 | 43.48 | +11.58 |
| Chris Olave | WR | starter | 10.69 | 23.9 | 32.64 | +8.75 |
| Justin Jefferson | WR | starter | 10.68 | 22.84 | 30.41 | +7.58 |
| Nico Collins | WR | starter | 10.99 | 22.53 | 30.02 | +7.48 |
| Zay Flowers | WR | starter | 10.4 | 21.58 | 28.95 | +7.37 |
| Drake London | WR | starter | 10.18 | 20.11 | 26.95 | +6.84 |
| Rhamondre Stevenson | RB | bench | 9.37 | 14.09 | 9.24 | -4.85 |
| Omarion Hampton | RB | starter | 9.83 | 20.44 | 15.61 | -4.82 |
| Christian Watson | WR | starter | 10.15 | 16.7 | 21.26 | +4.56 |
| Josh Allen | QB | starter | 23.39 | 36.58 | 32.33 | -4.25 |
| Travis Etienne | RB | bench | 8.46 | 9.9 | 5.71 | -4.19 |
| Tetairoa McMillan | WR | starter | 10.3 | 17.36 | 21.42 | +4.06 |
| George Pickens | WR | starter | 9.24 | 14.64 | 18.62 | +3.98 |
| Aaron Jones | RB | bench | 9.31 | 11.72 | 7.77 | -3.95 |
| Tee Higgins | WR | starter | 10.16 | 16.05 | 19.75 | +3.70 |
| Parker Washington | WR | starter | 9.31 | 14.35 | 18.0 | +3.65 |
| TreVeyon Henderson | RB | bench | 8.17 | 8.42 | 4.93 | -3.49 |
| Quinshon Judkins | RB | starter | 10.83 | 18.76 | 15.28 | -3.48 |
| David Montgomery | RB | starter | 10.13 | 15.29 | 11.85 | -3.44 |
| Davante Adams | WR | starter | 10.81 | 16.86 | 20.24 | +3.38 |
| DeVonta Smith | WR | starter | 9.04 | 13.59 | 16.83 | +3.24 |
| Tony Pollard | RB | starter | 10.54 | 12.14 | 8.96 | -3.18 |
| Kyle Monangai | RB | bench | 8.34 | 7.81 | 4.63 | -3.18 |
| Joe Burrow | QB | starter | 20.48 | 13.01 | 9.96 | -3.05 |
| Jordan Mason | RB | bench | 8.7 | 6.46 | 3.41 | -3.04 |
| Cam Skattebo | RB | starter | 11.62 | 22.75 | 19.77 | -2.98 |

### standard/10

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 13.91 | 42.03 | 57.22 | +15.19 |
| Ja'Marr Chase | WR | starter | 12.33 | 35.71 | 49.11 | +13.40 |
| Amon-Ra St. Brown | WR | starter | 11.8 | 33.29 | 45.73 | +12.44 |
| Puka Nacua | WR | starter | 13.72 | 37.68 | 49.83 | +12.15 |
| CeeDee Lamb | WR | starter | 12.43 | 34.64 | 46.49 | +11.85 |
| Chris Olave | WR | starter | 10.69 | 26.99 | 36.32 | +9.33 |
| Justin Jefferson | WR | starter | 10.68 | 25.69 | 33.92 | +8.23 |
| Zay Flowers | WR | starter | 10.4 | 24.56 | 32.53 | +7.97 |
| Nico Collins | WR | starter | 10.99 | 25.79 | 33.52 | +7.73 |
| Drake London | WR | starter | 10.18 | 23.32 | 30.64 | +7.32 |
| Jahmyr Gibbs | RB | starter | 20.2 | 75.95 | 81.72 | +5.77 |
| Bijan Robinson | RB | starter | 18.52 | 70.68 | 76.2 | +5.53 |
| Brock Bowers | TE | starter | 9.59 | 24.2 | 29.66 | +5.46 |
| RJ Harvey | RB | bench | 6.73 | 9.74 | 4.53 | -5.20 |
| Brian Robinson | RB | bench | 6.7 | 8.29 | 3.35 | -4.94 |
| Kyle Monangai | RB | bench | 8.34 | 14.89 | 10.05 | -4.84 |
| Kenneth Walker III | RB | starter | 17.88 | 66.29 | 71.06 | +4.77 |
| Christian Watson | WR | starter | 10.15 | 19.92 | 24.68 | +4.77 |
| Alvin Kamara | RB | bench | 6.31 | 7.42 | 2.66 | -4.76 |
| George Pickens | WR | starter | 9.24 | 17.63 | 22.28 | +4.65 |
| Zach Charbonnet | RB | starter | 8.64 | 12.18 | 7.55 | -4.63 |
| Tony Pollard | RB | starter | 10.54 | 19.25 | 14.71 | -4.54 |
| Trey McBride | TE | starter | 9.05 | 21.42 | 25.94 | +4.52 |
| Rhamondre Stevenson | RB | starter | 9.37 | 20.35 | 15.85 | -4.50 |
| Tetairoa McMillan | WR | starter | 10.3 | 20.12 | 24.6 | +4.48 |
| Josh Allen | QB | starter | 23.39 | 28.99 | 33.44 | +4.45 |
| Jonathan Taylor | RB | starter | 16.22 | 58.05 | 62.4 | +4.35 |
| J.K. Dobbins | RB | starter | 8.64 | 11.65 | 7.36 | -4.29 |
| Parker Washington | WR | starter | 9.31 | 17.38 | 21.66 | +4.28 |
| Jordan Mason | RB | starter | 8.7 | 13.0 | 8.73 | -4.27 |

### standard/12

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 13.91 | 42.97 | 61.78 | +18.80 |
| Ja'Marr Chase | WR | starter | 12.33 | 36.64 | 53.41 | +16.77 |
| Amon-Ra St. Brown | WR | starter | 11.8 | 34.49 | 50.04 | +15.55 |
| CeeDee Lamb | WR | starter | 12.43 | 36.12 | 51.51 | +15.39 |
| Puka Nacua | WR | starter | 13.72 | 38.74 | 53.68 | +14.94 |
| Chris Olave | WR | starter | 10.69 | 28.65 | 40.97 | +12.33 |
| Justin Jefferson | WR | starter | 10.68 | 27.39 | 38.65 | +11.26 |
| Zay Flowers | WR | starter | 10.4 | 26.26 | 36.93 | +10.67 |
| Nico Collins | WR | starter | 10.99 | 27.65 | 38.0 | +10.35 |
| Drake London | WR | starter | 10.18 | 25.16 | 34.83 | +9.68 |
| Jahmyr Gibbs | RB | starter | 20.2 | 77.59 | 86.49 | +8.90 |
| Bijan Robinson | RB | starter | 18.52 | 72.5 | 81.1 | +8.60 |
| Kenneth Walker III | RB | starter | 17.88 | 68.02 | 75.56 | +7.54 |
| Brock Bowers | TE | starter | 9.59 | 24.15 | 31.55 | +7.40 |
| George Pickens | WR | starter | 9.24 | 19.62 | 26.28 | +6.66 |
| Jonathan Taylor | RB | starter | 16.22 | 60.46 | 67.0 | +6.54 |
| Christian Watson | WR | starter | 10.15 | 21.98 | 28.48 | +6.49 |
| Tetairoa McMillan | WR | starter | 10.3 | 22.11 | 28.55 | +6.44 |
| Trey McBride | TE | starter | 9.05 | 21.54 | 27.86 | +6.32 |
| James Cook | RB | starter | 13.4 | 51.82 | 57.88 | +6.05 |
| Parker Washington | WR | starter | 9.31 | 19.38 | 25.41 | +6.03 |
| DeVonta Smith | WR | starter | 9.04 | 18.27 | 24.29 | +6.02 |
| Tee Higgins | WR | starter | 10.16 | 21.19 | 26.97 | +5.78 |
| Garrett Wilson | WR | starter | 8.74 | 17.92 | 23.66 | +5.74 |
| Rico Dowdle | RB | bench | 6.39 | 11.12 | 5.57 | -5.55 |
| Bryce Young | QB | bench | 17.71 | 10.34 | 4.8 | -5.55 |
| Christian McCaffrey | RB | starter | 14.73 | 54.13 | 59.63 | +5.50 |
| Ollie Gordon II | RB | starter | 8.69 | 18.72 | 13.33 | -5.39 |
| Brian Robinson | RB | bench | 6.7 | 12.35 | 7.02 | -5.33 |
| Derrick Henry | RB | starter | 17.09 | 58.77 | 64.06 | +5.29 |

### standard/14

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 13.91 | 42.31 | 67.27 | +24.97 |
| Ja'Marr Chase | WR | starter | 12.33 | 36.45 | 58.67 | +22.21 |
| CeeDee Lamb | WR | starter | 12.43 | 36.07 | 56.82 | +20.75 |
| Amon-Ra St. Brown | WR | starter | 11.8 | 34.58 | 55.19 | +20.61 |
| Puka Nacua | WR | starter | 13.72 | 38.22 | 58.02 | +19.79 |
| Chris Olave | WR | starter | 10.69 | 28.97 | 45.93 | +16.95 |
| Justin Jefferson | WR | starter | 10.68 | 27.83 | 43.43 | +15.60 |
| Zay Flowers | WR | starter | 10.4 | 26.68 | 41.49 | +14.81 |
| Nico Collins | WR | starter | 10.99 | 27.88 | 42.39 | +14.50 |
| Drake London | WR | starter | 10.18 | 25.6 | 39.13 | +13.53 |
| Brock Bowers | TE | starter | 9.59 | 23.71 | 33.67 | +9.96 |
| George Pickens | WR | starter | 9.24 | 20.57 | 30.18 | +9.61 |
| Christian Watson | WR | starter | 10.15 | 22.56 | 31.92 | +9.36 |
| Tetairoa McMillan | WR | starter | 10.3 | 22.77 | 31.99 | +9.22 |
| Bijan Robinson | RB | starter | 18.52 | 77.46 | 86.59 | +9.13 |
| Jahmyr Gibbs | RB | starter | 20.2 | 82.85 | 91.89 | +9.04 |
| Trey McBride | TE | starter | 9.05 | 21.17 | 30.13 | +8.96 |
| Parker Washington | WR | starter | 9.31 | 20.19 | 28.97 | +8.78 |
| DeVonta Smith | WR | starter | 9.04 | 19.44 | 28.14 | +8.70 |
| Garrett Wilson | WR | starter | 8.74 | 19.12 | 27.55 | +8.42 |
| Tee Higgins | WR | starter | 10.16 | 21.98 | 30.4 | +8.42 |
| Kenneth Walker III | RB | starter | 17.88 | 72.44 | 80.58 | +8.14 |
| Davante Adams | WR | starter | 10.81 | 22.42 | 29.85 | +7.42 |
| Malik Nabers | WR | starter | 7.7 | 16.04 | 23.04 | +7.01 |
| James Cook | RB | starter | 13.4 | 56.26 | 63.25 | +7.00 |
| Jonathan Taylor | RB | starter | 16.22 | 65.13 | 71.96 | +6.83 |
| Jayden Daniels | QB | starter | 20.07 | 17.71 | 10.98 | -6.72 |
| A.J. Brown | WR | starter | 8.65 | 17.36 | 23.89 | +6.53 |
| Christian McCaffrey | RB | starter | 14.73 | 58.1 | 64.46 | +6.35 |
| Matthew Stafford | QB | starter | 19.2 | 13.25 | 7.64 | -5.61 |

### half_ppr/8

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 17.24 | 41.55 | 56.26 | +14.72 |
| Ja'Marr Chase | WR | starter | 15.98 | 36.69 | 49.69 | +13.00 |
| Puka Nacua | WR | starter | 17.37 | 38.2 | 50.44 | +12.24 |
| Amon-Ra St. Brown | WR | starter | 15.32 | 33.95 | 45.85 | +11.90 |
| CeeDee Lamb | WR | starter | 15.97 | 34.93 | 46.27 | +11.34 |
| Chris Olave | WR | starter | 13.84 | 26.5 | 35.23 | +8.74 |
| Justin Jefferson | WR | starter | 13.66 | 25.0 | 32.49 | +7.49 |
| Zay Flowers | WR | starter | 12.94 | 22.66 | 29.76 | +7.10 |
| Nico Collins | WR | starter | 13.73 | 24.0 | 31.02 | +7.02 |
| Drake London | WR | starter | 12.83 | 21.7 | 28.34 | +6.64 |
| Omarion Hampton | RB | starter | 10.66 | 18.58 | 13.78 | -4.79 |
| Rhamondre Stevenson | RB | bench | 10.64 | 13.89 | 9.21 | -4.68 |
| Travis Etienne | RB | bench | 9.68 | 9.93 | 5.73 | -4.21 |
| Aaron Jones | RB | bench | 10.63 | 11.48 | 7.62 | -3.86 |
| Tetairoa McMillan | WR | starter | 13.17 | 19.15 | 22.99 | +3.84 |
| Christian Watson | WR | starter | 12.41 | 17.16 | 20.99 | +3.83 |
| David Montgomery | RB | starter | 11.0 | 14.11 | 10.52 | -3.59 |
| George Pickens | WR | starter | 11.7 | 15.77 | 19.3 | +3.53 |
| Jahmyr Gibbs | RB | starter | 22.48 | 71.19 | 74.73 | +3.53 |
| Parker Washington | WR | starter | 11.51 | 15.07 | 18.36 | +3.29 |
| TreVeyon Henderson | RB | bench | 8.84 | 7.32 | 4.05 | -3.27 |
| Tony Pollard | RB | starter | 11.65 | 11.24 | 8.07 | -3.17 |
| Quinshon Judkins | RB | starter | 12.4 | 18.69 | 15.53 | -3.17 |
| Kyle Monangai | RB | bench | 8.94 | 6.62 | 3.47 | -3.15 |
| Bijan Robinson | RB | starter | 20.27 | 64.61 | 67.62 | +3.01 |
| DeVonta Smith | WR | starter | 11.81 | 15.49 | 18.48 | +2.99 |
| Jordan Mason | RB | bench | 9.25 | 5.2 | 2.21 | -2.98 |
| Tee Higgins | WR | starter | 12.81 | 17.31 | 20.25 | +2.95 |
| Cam Skattebo | RB | starter | 12.78 | 21.74 | 18.81 | -2.94 |
| Deebo Samuel Sr. | WR | bench | 9.03 | 5.69 | 2.76 | -2.92 |

### half_ppr/10

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 17.24 | 44.2 | 58.96 | +14.76 |
| Ja'Marr Chase | WR | starter | 15.98 | 39.1 | 52.46 | +13.36 |
| Amon-Ra St. Brown | WR | starter | 15.32 | 36.84 | 49.11 | +12.27 |
| Puka Nacua | WR | starter | 17.37 | 40.36 | 52.38 | +12.02 |
| CeeDee Lamb | WR | starter | 15.97 | 37.84 | 49.43 | +11.60 |
| Chris Olave | WR | starter | 13.84 | 29.9 | 39.04 | +9.14 |
| Justin Jefferson | WR | starter | 13.66 | 28.12 | 36.28 | +8.17 |
| Zay Flowers | WR | starter | 12.94 | 26.03 | 33.72 | +7.69 |
| Nico Collins | WR | starter | 13.73 | 27.42 | 34.78 | +7.36 |
| Drake London | WR | starter | 12.83 | 25.23 | 32.28 | +7.06 |
| Josh Allen | QB | starter | 23.39 | 24.99 | 31.44 | +6.45 |
| Brock Bowers | TE | starter | 12.59 | 25.88 | 30.49 | +4.60 |
| Rome Odunze | WR | bench | 8.47 | 9.51 | 4.99 | -4.52 |
| Tetairoa McMillan | WR | starter | 13.17 | 22.16 | 26.56 | +4.40 |
| Josh Downs | WR | bench | 8.62 | 8.75 | 4.39 | -4.36 |
| RJ Harvey | RB | bench | 8.7 | 10.77 | 6.5 | -4.27 |
| George Pickens | WR | starter | 11.7 | 19.2 | 23.43 | +4.23 |
| Christian Watson | WR | starter | 12.41 | 20.6 | 24.83 | +4.23 |
| Parker Washington | WR | starter | 11.51 | 18.45 | 22.45 | +4.00 |
| Romeo Doubs | WR | bench | 7.81 | 5.92 | 1.99 | -3.93 |
| Stefon Diggs | WR | bench | 8.73 | 8.49 | 4.58 | -3.91 |
| Trey McBride | TE | starter | 12.72 | 24.63 | 28.5 | +3.87 |
| DeVonta Smith | WR | starter | 11.81 | 18.61 | 22.42 | +3.81 |
| Alvin Kamara | RB | bench | 7.52 | 6.9 | 3.1 | -3.80 |
| Garrett Wilson | WR | starter | 11.61 | 18.6 | 22.31 | +3.71 |
| Jordan Addison | WR | bench | 8.03 | 6.04 | 2.46 | -3.57 |
| Brian Robinson | RB | bench | 7.03 | 5.77 | 2.22 | -3.55 |
| Tee Higgins | WR | starter | 12.81 | 20.55 | 24.02 | +3.48 |
| Kyle Monangai | RB | bench | 8.94 | 12.0 | 8.56 | -3.44 |
| Jakobi Meyers | WR | bench | 8.63 | 6.82 | 3.41 | -3.41 |

### half_ppr/12

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 17.24 | 45.09 | 64.05 | +18.96 |
| Ja'Marr Chase | WR | starter | 15.98 | 40.16 | 57.05 | +16.89 |
| Amon-Ra St. Brown | WR | starter | 15.32 | 38.04 | 53.76 | +15.72 |
| CeeDee Lamb | WR | starter | 15.97 | 39.36 | 54.88 | +15.52 |
| Puka Nacua | WR | starter | 17.37 | 41.48 | 56.58 | +15.10 |
| Chris Olave | WR | starter | 13.84 | 31.69 | 44.08 | +12.39 |
| Justin Jefferson | WR | starter | 13.66 | 30.08 | 41.31 | +11.23 |
| Zay Flowers | WR | starter | 12.94 | 28.0 | 38.49 | +10.48 |
| Nico Collins | WR | starter | 13.73 | 29.43 | 39.66 | +10.23 |
| Drake London | WR | starter | 12.83 | 27.24 | 36.89 | +9.65 |
| Bijan Robinson | RB | starter | 20.27 | 70.53 | 77.43 | +6.91 |
| Jahmyr Gibbs | RB | starter | 22.48 | 76.51 | 83.42 | +6.91 |
| Brock Bowers | TE | starter | 12.59 | 25.65 | 32.25 | +6.60 |
| Kenneth Walker III | RB | starter | 19.41 | 65.31 | 71.67 | +6.36 |
| Tetairoa McMillan | WR | starter | 13.17 | 24.47 | 30.78 | +6.31 |
| George Pickens | WR | starter | 11.7 | 21.44 | 27.66 | +6.21 |
| Christian Watson | WR | starter | 12.41 | 22.88 | 29.0 | +6.12 |
| Trey McBride | TE | starter | 12.72 | 24.63 | 30.53 | +5.90 |
| Parker Washington | WR | starter | 11.51 | 20.75 | 26.52 | +5.77 |
| DeVonta Smith | WR | starter | 11.81 | 20.97 | 26.69 | +5.71 |
| Garrett Wilson | WR | starter | 11.61 | 21.1 | 26.8 | +5.70 |
| Tee Higgins | WR | starter | 12.81 | 22.87 | 28.21 | +5.34 |
| James Cook | RB | starter | 14.3 | 48.39 | 53.58 | +5.19 |
| Jonathan Taylor | RB | starter | 17.47 | 57.83 | 62.99 | +5.16 |
| Bryce Young | QB | bench | 17.71 | 9.49 | 4.52 | -4.97 |
| Christian McCaffrey | RB | starter | 16.75 | 53.14 | 57.97 | +4.83 |
| Davante Adams | WR | starter | 13.32 | 22.93 | 27.41 | +4.49 |
| Rico Dowdle | RB | bench | 7.25 | 9.47 | 5.04 | -4.43 |
| Malik Nabers | WR | starter | 9.89 | 16.83 | 21.21 | +4.37 |
| Brian Robinson | RB | bench | 7.03 | 9.43 | 5.1 | -4.33 |

### half_ppr/14

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 17.24 | 46.89 | 69.99 | +23.10 |
| Ja'Marr Chase | WR | starter | 15.98 | 42.02 | 62.4 | +20.38 |
| CeeDee Lamb | WR | starter | 15.97 | 41.2 | 60.4 | +19.19 |
| Amon-Ra St. Brown | WR | starter | 15.32 | 40.05 | 59.16 | +19.11 |
| Puka Nacua | WR | starter | 17.37 | 42.74 | 61.14 | +18.40 |
| Chris Olave | WR | starter | 13.84 | 33.72 | 49.36 | +15.64 |
| Justin Jefferson | WR | starter | 13.66 | 32.01 | 46.37 | +14.36 |
| Zay Flowers | WR | starter | 12.94 | 30.07 | 43.46 | +13.39 |
| Nico Collins | WR | starter | 13.73 | 31.25 | 44.48 | +13.23 |
| Drake London | WR | starter | 12.83 | 29.28 | 41.66 | +12.38 |
| Bijan Robinson | RB | starter | 20.27 | 73.59 | 82.53 | +8.94 |
| Jahmyr Gibbs | RB | starter | 22.48 | 79.75 | 88.39 | +8.64 |
| George Pickens | WR | starter | 11.7 | 23.37 | 31.92 | +8.55 |
| Tetairoa McMillan | WR | starter | 13.17 | 25.98 | 34.41 | +8.43 |
| Christian Watson | WR | starter | 12.41 | 24.61 | 32.84 | +8.24 |
| Kenneth Walker III | RB | starter | 19.41 | 68.26 | 76.37 | +8.10 |
| Parker Washington | WR | starter | 11.51 | 22.7 | 30.58 | +7.88 |
| DeVonta Smith | WR | starter | 11.81 | 22.77 | 30.58 | +7.81 |
| Garrett Wilson | WR | starter | 11.61 | 23.09 | 30.82 | +7.73 |
| Tee Higgins | WR | starter | 12.81 | 24.37 | 31.94 | +7.56 |
| James Cook | RB | starter | 14.3 | 51.33 | 58.56 | +7.24 |
| Jonathan Taylor | RB | starter | 17.47 | 60.6 | 67.6 | +7.00 |
| Davante Adams | WR | starter | 13.32 | 24.15 | 30.68 | +6.53 |
| Brock Bowers | TE | starter | 12.59 | 28.28 | 34.74 | +6.46 |
| Christian McCaffrey | RB | starter | 16.75 | 55.91 | 62.36 | +6.45 |
| Malik Nabers | WR | starter | 9.89 | 19.18 | 25.27 | +6.10 |
| Trey McBride | TE | starter | 12.72 | 27.22 | 33.05 | +5.82 |
| A.J. Brown | WR | starter | 10.99 | 19.87 | 25.67 | +5.80 |
| Derrick Henry | RB | starter | 17.76 | 57.22 | 62.9 | +5.67 |
| Keon Coleman | WR | bench | 6.96 | 9.38 | 4.33 | -5.05 |

### ppr/8

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 20.57 | 46.57 | 57.46 | +10.90 |
| Puka Nacua | WR | starter | 21.02 | 42.27 | 51.9 | +9.63 |
| Ja'Marr Chase | WR | starter | 19.6 | 41.96 | 51.56 | +9.60 |
| Amon-Ra St. Brown | WR | starter | 18.84 | 39.59 | 48.45 | +8.86 |
| CeeDee Lamb | WR | starter | 19.51 | 39.87 | 48.33 | +8.46 |
| Chris Olave | WR | starter | 17.02 | 31.43 | 37.76 | +6.33 |
| Jahmyr Gibbs | RB | starter | 24.74 | 66.56 | 72.09 | +5.53 |
| Justin Jefferson | WR | starter | 16.61 | 28.91 | 33.98 | +5.08 |
| Bijan Robinson | RB | starter | 22.01 | 59.48 | 64.32 | +4.84 |
| Nico Collins | WR | starter | 16.44 | 27.34 | 32.17 | +4.82 |
| Zay Flowers | WR | starter | 15.44 | 26.16 | 30.73 | +4.57 |
| Drake London | WR | starter | 15.49 | 25.57 | 30.03 | +4.46 |
| Rome Odunze | WR | bench | 10.16 | 6.06 | 2.04 | -4.01 |
| Kenneth Walker III | RB | starter | 20.94 | 54.74 | 58.72 | +3.98 |
| Deebo Samuel Sr. | WR | bench | 10.74 | 6.7 | 2.74 | -3.96 |
| Jameson Williams | WR | bench | 10.56 | 7.67 | 3.85 | -3.82 |
| DK Metcalf | WR | bench | 11.98 | 8.88 | 5.08 | -3.80 |
| Jonathan Taylor | RB | starter | 18.74 | 45.33 | 49.12 | +3.79 |
| Jalen Coker | WR | starter | 13.0 | 11.86 | 8.23 | -3.63 |
| Stefon Diggs | WR | bench | 10.84 | 5.69 | 2.15 | -3.54 |
| Ladd McConkey | WR | bench | 11.3 | 9.83 | 6.34 | -3.49 |
| Emeka Egbuka | WR | bench | 11.23 | 8.44 | 5.0 | -3.44 |
| Josh Downs | WR | bench | 10.79 | 5.62 | 2.21 | -3.42 |
| Omarion Hampton | RB | bench | 11.5 | 15.54 | 12.22 | -3.31 |
| Rhamondre Stevenson | RB | bench | 11.88 | 11.99 | 8.78 | -3.21 |
| Derrick Henry | RB | starter | 18.38 | 41.09 | 44.25 | +3.15 |
| Christian McCaffrey | RB | starter | 18.77 | 43.77 | 46.8 | +3.02 |
| Travis Etienne | RB | bench | 10.9 | 8.72 | 5.74 | -2.98 |
| Kyren Williams | RB | starter | 17.42 | 35.56 | 38.46 | +2.90 |
| Denzel Boston | WR | bench | 11.27 | 6.4 | 3.5 | -2.90 |

### ppr/10

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 20.57 | 45.56 | 60.77 | +15.21 |
| Ja'Marr Chase | WR | starter | 19.6 | 41.21 | 54.97 | +13.76 |
| Puka Nacua | WR | starter | 21.02 | 41.75 | 54.64 | +12.90 |
| Amon-Ra St. Brown | WR | starter | 18.84 | 39.22 | 51.92 | +12.70 |
| CeeDee Lamb | WR | starter | 19.51 | 39.82 | 51.85 | +12.03 |
| Chris Olave | WR | starter | 17.02 | 32.22 | 41.46 | +9.23 |
| Justin Jefferson | WR | starter | 16.61 | 29.88 | 38.09 | +8.22 |
| Josh Allen | QB | starter | 23.39 | 22.22 | 29.99 | +7.77 |
| Zay Flowers | WR | starter | 15.44 | 27.37 | 34.74 | +7.37 |
| Nico Collins | WR | starter | 16.44 | 28.65 | 35.99 | +7.34 |
| Drake London | WR | starter | 15.49 | 26.92 | 33.85 | +6.93 |
| Stefon Diggs | WR | bench | 10.84 | 11.54 | 5.58 | -5.95 |
| Rome Odunze | WR | bench | 10.16 | 11.16 | 5.57 | -5.60 |
| Tetairoa McMillan | WR | starter | 16.07 | 23.74 | 28.51 | +4.77 |
| Romeo Doubs | WR | bench | 9.33 | 6.94 | 2.27 | -4.67 |
| Josh Downs | WR | bench | 10.79 | 10.13 | 5.74 | -4.39 |
| Jakobi Meyers | WR | bench | 10.5 | 8.42 | 4.11 | -4.31 |
| Jordan Addison | WR | bench | 9.61 | 7.01 | 2.8 | -4.20 |
| Christian Watson | WR | starter | 14.68 | 21.33 | 25.38 | +4.04 |
| George Pickens | WR | starter | 14.2 | 20.63 | 24.62 | +3.99 |
| Wan'Dale Robinson | WR | bench | 9.42 | 5.74 | 1.85 | -3.89 |
| DeVonta Smith | WR | starter | 14.61 | 20.44 | 24.25 | +3.81 |
| Garrett Wilson | WR | starter | 14.5 | 20.89 | 24.7 | +3.81 |
| Parker Washington | WR | starter | 13.71 | 19.68 | 23.4 | +3.73 |
| Jordyn Tyson | WR | waiver | 7.43 | 5.15 | 1.45 | -3.70 |
| Tee Higgins | WR | starter | 15.45 | 21.63 | 25.31 | +3.68 |
| Jahmyr Gibbs | RB | starter | 24.74 | 74.11 | 77.76 | +3.65 |
| Bijan Robinson | RB | starter | 22.01 | 67.13 | 70.63 | +3.50 |
| Brian Thomas Jr. | WR | bench | 9.04 | 5.42 | 1.92 | -3.50 |
| Lamar Jackson | QB | waiver | 17.17 | 10.83 | 14.3 | +3.47 |

### ppr/12

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 20.57 | 50.85 | 66.16 | +15.31 |
| Ja'Marr Chase | WR | starter | 19.6 | 46.32 | 59.85 | +13.53 |
| Amon-Ra St. Brown | WR | starter | 18.84 | 44.12 | 56.83 | +12.70 |
| CeeDee Lamb | WR | starter | 19.51 | 45.19 | 57.6 | +12.41 |
| Puka Nacua | WR | starter | 21.02 | 46.82 | 59.09 | +12.26 |
| Chris Olave | WR | starter | 17.02 | 36.94 | 46.92 | +9.98 |
| Justin Jefferson | WR | starter | 16.61 | 34.73 | 43.57 | +8.83 |
| Jahmyr Gibbs | RB | starter | 24.74 | 72.2 | 80.8 | +8.60 |
| Bijan Robinson | RB | starter | 22.01 | 65.63 | 73.98 | +8.36 |
| Zay Flowers | WR | starter | 15.44 | 31.87 | 40.05 | +8.18 |
| Nico Collins | WR | starter | 16.44 | 33.27 | 41.31 | +8.04 |
| Kenneth Walker III | RB | starter | 20.94 | 60.13 | 67.96 | +7.83 |
| Romeo Doubs | WR | bench | 9.33 | 13.2 | 5.38 | -7.83 |
| Drake London | WR | starter | 15.49 | 31.32 | 39.01 | +7.69 |
| Kalif Raymond | WR | bench | 7.37 | 8.1 | 0.91 | -7.20 |
| Jonathan Taylor | RB | starter | 18.74 | 52.86 | 59.32 | +6.46 |
| Christian McCaffrey | RB | starter | 18.77 | 49.91 | 56.19 | +6.28 |
| James Cook | RB | starter | 15.24 | 43.47 | 49.42 | +5.95 |
| Derrick Henry | RB | starter | 18.38 | 48.12 | 53.88 | +5.76 |
| Brian Thomas Jr. | WR | bench | 9.04 | 10.17 | 4.69 | -5.48 |
| Malik Washington | WR | starter | 10.27 | 11.11 | 5.79 | -5.32 |
| Tetairoa McMillan | WR | starter | 16.07 | 28.15 | 33.11 | +4.95 |
| Chris Godwin | WR | bench | 8.88 | 9.48 | 4.6 | -4.88 |
| Tre Tucker | WR | bench | 9.02 | 7.65 | 2.83 | -4.82 |
| Jordan Addison | WR | bench | 9.61 | 10.35 | 5.63 | -4.73 |
| Chase Brown | RB | starter | 17.11 | 41.67 | 46.38 | +4.71 |
| Kyren Williams | RB | starter | 17.42 | 43.35 | 48.03 | +4.68 |
| Javonte Williams | RB | starter | 16.78 | 40.78 | 45.42 | +4.64 |
| Dontayvion Wicks | WR | bench | 8.36 | 7.09 | 2.45 | -4.64 |
| George Pickens | WR | starter | 14.2 | 24.57 | 29.2 | +4.63 |

### ppr/14

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 20.57 | 51.84 | 71.53 | +19.69 |
| Ja'Marr Chase | WR | starter | 19.6 | 47.2 | 64.56 | +17.36 |
| CeeDee Lamb | WR | starter | 19.51 | 46.17 | 62.59 | +16.43 |
| Amon-Ra St. Brown | WR | starter | 18.84 | 45.24 | 61.64 | +16.39 |
| Puka Nacua | WR | starter | 21.02 | 47.28 | 63.27 | +15.98 |
| Chris Olave | WR | starter | 17.02 | 38.25 | 51.7 | +13.45 |
| Justin Jefferson | WR | starter | 16.61 | 35.87 | 48.12 | +12.25 |
| Zay Flowers | WR | starter | 15.44 | 33.36 | 44.61 | +11.25 |
| Nico Collins | WR | starter | 16.44 | 34.52 | 45.74 | +11.23 |
| Drake London | WR | starter | 15.49 | 32.85 | 43.43 | +10.58 |
| Bijan Robinson | RB | starter | 22.01 | 68.36 | 78.79 | +10.43 |
| Jahmyr Gibbs | RB | starter | 24.74 | 74.97 | 85.27 | +10.30 |
| Kenneth Walker III | RB | starter | 20.94 | 63.06 | 72.6 | +9.53 |
| Jonathan Taylor | RB | starter | 18.74 | 55.21 | 63.62 | +8.40 |
| James Cook | RB | starter | 15.24 | 46.12 | 54.29 | +8.17 |
| Christian McCaffrey | RB | starter | 18.77 | 52.73 | 60.46 | +7.73 |
| Tetairoa McMillan | WR | starter | 16.07 | 29.03 | 36.53 | +7.50 |
| Derrick Henry | RB | starter | 18.38 | 50.68 | 57.95 | +7.27 |
| George Pickens | WR | starter | 14.2 | 25.93 | 33.07 | +7.14 |
| Christian Watson | WR | starter | 14.68 | 26.73 | 33.63 | +6.90 |
| Garrett Wilson | WR | starter | 14.5 | 26.56 | 33.33 | +6.77 |
| Parker Washington | WR | starter | 13.71 | 25.15 | 31.85 | +6.70 |
| DeVonta Smith | WR | starter | 14.61 | 25.65 | 32.33 | +6.68 |
| Tee Higgins | WR | starter | 15.45 | 26.67 | 33.18 | +6.51 |
| Chase Brown | RB | starter | 17.11 | 44.18 | 50.28 | +6.09 |
| Kyren Williams | RB | starter | 17.42 | 45.67 | 51.66 | +5.99 |
| Javonte Williams | RB | starter | 16.78 | 43.3 | 49.26 | +5.96 |
| Davante Adams | WR | starter | 15.83 | 25.93 | 31.59 | +5.66 |
| Ashton Jeanty | RB | starter | 16.4 | 42.48 | 48.12 | +5.64 |
| Malik Nabers | WR | starter | 12.11 | 22.13 | 27.22 | +5.09 |
