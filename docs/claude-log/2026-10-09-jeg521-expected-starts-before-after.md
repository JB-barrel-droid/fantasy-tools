# Expected-starts value: before and after, all 12 settings

Produced by `pipelines/expected_starts_model.py` on the Week 5 build. Before = today's live values (two-tier at the 15% bench share, ESPN anchored), scaled to the fixed pie. After A = expected-starts replaces the slices (ES-4 to ES-6). After B = slices kept, bench budget set from A. Bench-tier share = the pie held by players ranked past the starters on the mean projection. Price ratio = median value per point above waivers, starters over bench tier.

Parameters: QB m 9.9%, sigma 18.2%, floor 0.69; RB m 10.0%, sigma 30.0%, floor 0.89; WR m 13.0%, sigma 30.8%, floor 1.01; TE m 15.9%, sigma 36.2%, floor 0.64; bye share 7.2%.

## Bench-tier share and starter/bench price, per setting

| Setting | Variant | QB bench | RB bench | WR bench | TE bench | Overall | Fill-state share | QB price | RB price | WR price | TE price | Inversions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| standard/8 | before | 19.0% | 10.0% | 18.0% | 17.7% | 13.8% | n/a | 1.0x | 1.6x | 0.7x | 1.0x | n/a |
| standard/8 | after A | 16.4% | 6.1% | 11.8% | 14.5% | 9.4% | 5.3% | 1.2x | 3.1x | 1.7x | 1.2x | 0 |
| standard/8 | after A-option | 20.5% | 8.6% | 16.5% | 19.4% | 13.4% | 3.5% | 0.8x | 1.7x | 0.9x | 0.8x | 0 |
| standard/8 | after B | 16.0% | 5.6% | 11.2% | 13.9% | 9.1% | n/a | 1.2x | 2.6x | 1.3x | 1.2x | 0 |
| standard/10 | before | 17.4% | 12.7% | 16.5% | 17.1% | 14.5% | n/a | 1.0x | 1.0x | 0.9x | 1.1x | n/a |
| standard/10 | after A | 14.1% | 7.4% | 10.3% | 13.3% | 9.2% | 5.5% | 1.2x | 2.1x | 2.3x | 1.4x | 0 |
| standard/10 | after A-option | 18.2% | 9.5% | 14.6% | 17.6% | 12.7% | 3.5% | 0.9x | 1.5x | 1.2x | 0.9x | 0 |
| standard/10 | after B | 14.1% | 6.8% | 9.9% | 13.2% | 8.9% | n/a | 1.2x | 2.0x | 2.1x | 1.5x | 0 |
| standard/12 | before | 19.8% | 12.2% | 15.1% | 15.3% | 14.0% | n/a | 1.4x | 1.1x | 1.1x | 0.8x | n/a |
| standard/12 | after A | 16.1% | 6.4% | 7.7% | 10.1% | 7.8% | 4.8% | 2.3x | 2.4x | 2.6x | 1.5x | 0 |
| standard/12 | after A-option | 19.8% | 8.1% | 11.4% | 14.8% | 10.9% | 2.9% | 1.5x | 1.8x | 1.5x | 0.7x | 0 |
| standard/12 | after B | 15.7% | 5.4% | 7.5% | 9.3% | 7.3% | n/a | 2.2x | 2.7x | 2.6x | 1.6x | 0 |
| standard/14 | before | 16.9% | 13.3% | 16.1% | 15.0% | 14.7% | n/a | 1.1x | 0.9x | 0.8x | 0.7x | n/a |
| standard/14 | after A | 14.2% | 7.1% | 8.0% | 9.2% | 8.1% | 4.7% | 2.1x | 2.1x | 1.8x | 1.6x | 0 |
| standard/14 | after A-option | 17.3% | 8.4% | 10.9% | 14.6% | 10.6% | 2.9% | 1.2x | 1.7x | 1.3x | 0.7x | 0 |
| standard/14 | after B | 12.6% | 6.4% | 6.8% | 8.6% | 7.2% | n/a | 2.3x | 2.3x | 2.3x | 1.7x | 0 |
| half_ppr/8 | before | 19.2% | 9.8% | 18.1% | 17.7% | 14.0% | n/a | 1.0x | 1.7x | 0.8x | 1.0x | n/a |
| half_ppr/8 | after A | 16.4% | 5.7% | 12.0% | 14.4% | 9.3% | 5.1% | 1.2x | 3.8x | 1.7x | 1.2x | 0 |
| half_ppr/8 | after A-option | 20.5% | 8.4% | 16.7% | 19.6% | 13.6% | 3.4% | 0.8x | 1.9x | 1.0x | 0.9x | 0 |
| half_ppr/8 | after B | 16.0% | 5.3% | 11.3% | 14.1% | 9.1% | n/a | 1.2x | 3.7x | 1.5x | 1.2x | 0 |
| half_ppr/10 | before | 17.2% | 10.8% | 17.8% | 17.2% | 14.2% | n/a | 1.0x | 1.2x | 0.8x | 1.1x | n/a |
| half_ppr/10 | after A | 14.1% | 6.6% | 10.9% | 13.4% | 9.1% | 5.3% | 1.2x | 2.4x | 1.9x | 1.3x | 0 |
| half_ppr/10 | after A-option | 18.2% | 8.8% | 15.1% | 17.5% | 12.7% | 3.3% | 0.9x | 1.7x | 1.1x | 1.1x | 0 |
| half_ppr/10 | after B | 14.0% | 6.2% | 10.4% | 13.1% | 8.9% | n/a | 1.2x | 2.2x | 1.9x | 1.4x | 0 |
| half_ppr/12 | before | 19.8% | 10.6% | 17.1% | 17.0% | 14.1% | n/a | 1.5x | 1.3x | 1.0x | 0.8x | n/a |
| half_ppr/12 | after A | 16.1% | 6.0% | 8.5% | 12.1% | 8.0% | 4.7% | 2.2x | 2.7x | 2.3x | 1.1x | 0 |
| half_ppr/12 | after A-option | 20.0% | 7.7% | 12.2% | 17.8% | 11.3% | 2.7% | 1.5x | 2.0x | 1.4x | 0.6x | 0 |
| half_ppr/12 | after B | 15.8% | 6.0% | 8.6% | 11.8% | 8.2% | n/a | 2.1x | 2.5x | 2.2x | 1.3x | 0 |
| half_ppr/14 | before | 16.8% | 12.6% | 16.0% | 14.9% | 14.5% | n/a | 1.1x | 1.2x | 0.8x | 0.7x | n/a |
| half_ppr/14 | after A | 14.2% | 7.8% | 7.2% | 9.6% | 8.1% | 4.8% | 2.1x | 2.0x | 2.1x | 1.3x | 0 |
| half_ppr/14 | after A-option | 17.3% | 9.4% | 9.9% | 14.9% | 10.7% | 2.9% | 1.2x | 1.6x | 1.3x | 0.6x | 0 |
| half_ppr/14 | after B | 12.6% | 7.0% | 6.1% | 9.0% | 7.2% | n/a | 2.3x | 2.4x | 2.1x | 1.4x | 0 |
| ppr/8 | before | 19.1% | 11.3% | 16.7% | 17.6% | 14.5% | n/a | 1.0x | 1.6x | 0.9x | 1.0x | n/a |
| ppr/8 | after A | 16.4% | 7.9% | 10.1% | 14.8% | 9.8% | 5.1% | 1.2x | 3.0x | 1.6x | 1.1x | 0 |
| ppr/8 | after A-option | 20.5% | 10.9% | 14.4% | 19.8% | 13.9% | 3.5% | 0.8x | 1.6x | 1.0x | 0.9x | 0 |
| ppr/8 | after B | 16.0% | 7.4% | 9.5% | 14.0% | 9.4% | n/a | 1.2x | 2.8x | 1.6x | 1.2x | 0 |
| ppr/10 | before | 17.2% | 11.3% | 16.6% | 15.5% | 14.0% | n/a | 1.0x | 1.5x | 0.8x | 1.9x | n/a |
| ppr/10 | after A | 14.1% | 7.5% | 8.3% | 11.9% | 8.5% | 5.2% | 1.2x | 2.6x | 2.3x | 2.2x | 0 |
| ppr/10 | after A-option | 18.1% | 10.2% | 12.3% | 17.0% | 12.2% | 3.2% | 0.9x | 1.7x | 1.3x | 0.9x | 0 |
| ppr/10 | after B | 14.0% | 7.1% | 8.1% | 11.4% | 8.3% | n/a | 1.2x | 2.4x | 2.1x | 2.4x | 0 |
| ppr/12 | before | 19.8% | 12.8% | 15.7% | 16.8% | 14.8% | n/a | 1.5x | 1.0x | 1.0x | 0.8x | n/a |
| ppr/12 | after A | 16.1% | 8.8% | 6.5% | 12.6% | 8.5% | 4.9% | 2.3x | 1.7x | 2.8x | 1.4x | 0 |
| ppr/12 | after A-option | 19.9% | 11.2% | 9.8% | 18.3% | 11.9% | 2.9% | 1.5x | 1.3x | 1.6x | 0.7x | 0 |
| ppr/12 | after B | 15.8% | 8.5% | 6.5% | 13.1% | 8.5% | n/a | 2.1x | 1.7x | 2.6x | 1.3x | 0 |
| ppr/14 | before | 16.8% | 12.9% | 14.2% | 17.1% | 14.1% | n/a | 1.2x | 1.2x | 0.8x | 0.6x | n/a |
| ppr/14 | after A | 14.2% | 7.8% | 6.9% | 10.7% | 8.0% | 4.7% | 2.1x | 2.1x | 2.0x | 1.1x | 0 |
| ppr/14 | after A-option | 17.3% | 9.6% | 9.6% | 15.3% | 10.7% | 2.8% | 1.2x | 1.7x | 1.3x | 0.7x | 0 |
| ppr/14 | after B | 12.6% | 7.2% | 5.9% | 9.6% | 7.2% | n/a | 2.3x | 2.5x | 2.1x | 1.2x | 0 |

## Position shares of the pie (blended DDF Value)

| Setting | QB before | QB after A | RB before | RB after A | WR before | WR after A | TE before | TE after A |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| standard/8 | 7.8% | 6.4% | 53.4% | 50.8% | 32.0% | 36.6% | 6.8% | 6.1% |
| standard/10 | 7.0% | 6.7% | 54.3% | 51.7% | 32.4% | 35.7% | 6.3% | 5.9% |
| standard/12 | 9.1% | 7.1% | 52.5% | 50.1% | 32.1% | 36.6% | 6.2% | 6.3% |
| standard/14 | 10.4% | 7.4% | 51.8% | 49.1% | 31.9% | 37.3% | 5.9% | 6.1% |
| half_ppr/8 | 7.0% | 6.1% | 50.9% | 48.7% | 34.8% | 38.6% | 7.3% | 6.6% |
| half_ppr/10 | 6.0% | 6.3% | 51.1% | 49.3% | 36.0% | 38.2% | 6.8% | 6.2% |
| half_ppr/12 | 8.1% | 6.5% | 48.7% | 47.5% | 36.4% | 39.5% | 6.8% | 6.4% |
| half_ppr/14 | 9.1% | 7.0% | 46.3% | 45.9% | 37.4% | 40.6% | 7.1% | 6.5% |
| ppr/8 | 6.1% | 5.7% | 44.9% | 46.0% | 41.1% | 41.2% | 7.8% | 7.0% |
| ppr/10 | 5.4% | 6.0% | 47.1% | 46.6% | 39.7% | 41.0% | 7.9% | 6.4% |
| ppr/12 | 7.0% | 6.2% | 42.0% | 44.3% | 43.6% | 42.8% | 7.4% | 6.7% |
| ppr/14 | 8.1% | 6.6% | 41.9% | 43.3% | 41.0% | 42.9% | 9.0% | 7.2% |

## Sensitivity at 12-team full PPR (option A)

| Case | QB bench | RB bench | WR bench | TE bench | Overall | Fill-state share | QB price | RB price | WR price | TE price | RB top-12 share | WR top-12 share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| recommended (share form) | 16.1% | 8.8% | 6.5% | 12.6% | 8.5% | 4.9% | 2.3x | 1.7x | 2.8x | 1.4x | 56.7% | 48.4% |
| recommended, convex option form | 19.9% | 11.2% | 9.8% | 18.3% | 11.9% | 2.9% | 1.5x | 1.3x | 1.6x | 0.7x | 53.2% | 43.8% |
| convex option form, sigma x 0.5 | 18.3% | 9.9% | 7.9% | 16.3% | 10.2% | 3.2% | 1.8x | 1.6x | 2.2x | 0.9x | 54.2% | 45.3% |
| m x 0.5 | 16.0% | 8.4% | 6.1% | 12.4% | 8.1% | 3.6% | 2.3x | 1.8x | 3.0x | 1.4x | 57.2% | 49.0% |
| m x 0.75 | 16.1% | 8.6% | 6.3% | 12.5% | 8.3% | 4.3% | 2.3x | 1.8x | 2.9x | 1.4x | 56.9% | 48.7% |
| m x 1.25 | 16.2% | 9.0% | 6.7% | 12.6% | 8.7% | 5.6% | 2.2x | 1.7x | 2.7x | 1.4x | 56.4% | 48.1% |
| m x 1.5 | 16.2% | 9.2% | 6.9% | 12.7% | 8.9% | 6.2% | 2.2x | 1.6x | 2.6x | 1.3x | 56.1% | 47.8% |
| sigma x 0.0 | 16.0% | 8.2% | 5.9% | 11.7% | 8.0% | 4.5% | 2.1x | 1.8x | 2.9x | 2.3x | 56.1% | 47.5% |
| sigma x 0.25 | 16.0% | 8.4% | 5.9% | 12.3% | 8.1% | 4.4% | 2.3x | 1.9x | 3.1x | 1.5x | 56.1% | 47.6% |
| sigma x 0.5 | 15.8% | 8.5% | 6.0% | 12.2% | 8.1% | 4.6% | 2.3x | 1.9x | 3.0x | 1.5x | 56.4% | 48.0% |
| sigma x 0.75 | 15.9% | 8.6% | 6.2% | 12.4% | 8.3% | 4.8% | 2.3x | 1.8x | 2.9x | 1.4x | 56.6% | 48.3% |
| sigma x 1.25 | 16.3% | 9.1% | 6.7% | 12.7% | 8.8% | 4.9% | 2.2x | 1.6x | 2.6x | 1.3x | 56.6% | 48.3% |
| sigma x 1.5 | 16.4% | 9.3% | 6.9% | 12.9% | 8.9% | 4.8% | 2.2x | 1.6x | 2.5x | 1.3x | 56.4% | 48.1% |
| first-pass assumptions (m QB 11 RB 17 WR 14 TE 13, sigma 25%) | 16.4% | 9.5% | 6.2% | 12.3% | 8.7% | 4.9% | 2.3x | 1.6x | 3.1x | 1.6x | 55.4% | 47.6% |
| lower bound: fill-in only (sigma 0) | 16.0% | 8.2% | 5.9% | 11.7% | 8.0% | 4.5% | 2.1x | 1.8x | 2.9x | 2.3x | 56.1% | 47.5% |
| upper bound: plain value above waivers (bench starts every week) | 18.8% | 13.5% | 11.3% | 15.1% | 13.1% | n/a | 1.6x | 1.0x | 1.4x | 1.1x | 50.8% | 43.0% |
| before (today) | 19.8% | 12.8% | 15.7% | 16.8% | 14.8% | n/a | 1.5x | 1.0x | 1.0x | 0.8x | 52.0% | 39.2% |

## Expected lineup share of a player's surplus (ESPN, 12-team full PPR, option A)

| Position | Rank | Player | Points per game | sigma (ppg) | Lineup share of surplus | Start-worthy part |
| --- | --- | --- | --- | --- | --- | --- |
| QB | 1 | Josh Allen | 23.84 | 4.35 | 73.7% | 72.7% |
| QB | 7 | Tyler Shough | 20.45 | 3.73 | 57.1% | 54.9% |
| QB | 12 | Dak Prescott | 19.49 | 3.55 | 49.5% | 46.8% |
| QB | 13 | Jared Goff | 18.95 | 3.45 | 44.7% | 41.8% |
| QB | 18 | Jordan Love | 18.11 | 3.3 | 36.6% | 33.4% |
| RB | 1 | Jahmyr Gibbs | 25.71 | 7.72 | 82.1% | 81.6% |
| RB | 16 | Chuba Hubbard | 14.5 | 4.35 | 73.4% | 69.3% |
| RB | 31 | Josh Jacobs | 10.43 | 3.13 | 54.0% | 42.6% |
| RB | 32 | Jordan Mason | 10.35 | 3.11 | 53.3% | 41.8% |
| RB | 37 | Alvin Kamara | 8.5 | 2.55 | 34.9% | 19.5% |
| RB | 44 | Keaton Mitchell | 7.69 | 2.31 | 25.9% | 10.4% |
| WR | 1 | Ja'Marr Chase | 21.25 | 6.54 | 77.7% | 76.8% |
| WR | 21 | Carnell Tate | 13.77 | 4.24 | 67.7% | 63.5% |
| WR | 41 | Adonai Mitchell | 10.4 | 3.2 | 49.3% | 40.4% |
| WR | 42 | Jameson Williams | 10.4 | 3.2 | 49.3% | 40.4% |
| WR | 47 | Xavier Worthy | 9.84 | 3.03 | 44.2% | 34.4% |
| WR | 54 | Ryan Flournoy | 8.67 | 2.67 | 31.8% | 20.9% |
| TE | 1 | Trey McBride | 17.16 | 6.21 | 69.3% | 68.4% |
| TE | 7 | Tyler Warren | 11.8 | 4.27 | 54.6% | 52.0% |
| TE | 12 | Juwan Johnson | 10.33 | 3.74 | 45.5% | 42.0% |
| TE | 13 | T.J. Hockenson | 9.97 | 3.61 | 42.8% | 39.0% |
| TE | 18 | Pat Freiermuth | 8.41 | 3.04 | 28.3% | 23.7% |

## Top movers, blended DDF Value, before (scaled to the pie) and after A

### standard/8

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 13.91 | 39.75 | 53.63 | +13.88 |
| Ja'Marr Chase | WR | starter | 12.13 | 32.99 | 44.51 | +11.52 |
| Puka Nacua | WR | starter | 13.69 | 35.63 | 46.9 | +11.27 |
| Amon-Ra St. Brown | WR | starter | 11.8 | 30.69 | 41.56 | +10.87 |
| CeeDee Lamb | WR | starter | 12.43 | 32.03 | 42.47 | +10.45 |
| Chris Olave | WR | starter | 10.69 | 24.01 | 31.92 | +7.91 |
| Justin Jefferson | WR | starter | 10.72 | 23.06 | 29.89 | +6.84 |
| Nico Collins | WR | starter | 10.99 | 22.66 | 29.41 | +6.75 |
| Zay Flowers | WR | starter | 10.4 | 21.69 | 28.33 | +6.65 |
| Drake London | WR | starter | 10.18 | 20.17 | 26.34 | +6.17 |
| Rhamondre Stevenson | RB | bench | 9.34 | 14.04 | 8.92 | -5.12 |
| Jahmyr Gibbs | RB | starter | 20.2 | 73.91 | 78.93 | +5.02 |
| Quinshon Judkins | RB | starter | 10.83 | 19.88 | 15.27 | -4.61 |
| Travis Etienne | RB | bench | 8.46 | 9.92 | 5.43 | -4.49 |
| Bijan Robinson | RB | starter | 18.56 | 68.04 | 72.51 | +4.47 |
| Aaron Jones | RB | bench | 9.31 | 11.87 | 7.61 | -4.26 |
| Christian Watson | WR | starter | 10.18 | 16.85 | 20.91 | +4.06 |
| Kenneth Walker III | RB | starter | 17.88 | 63.34 | 67.05 | +3.71 |
| Omarion Hampton | RB | starter | 9.8 | 19.46 | 15.76 | -3.69 |
| TreVeyon Henderson | RB | bench | 8.17 | 8.45 | 4.76 | -3.69 |
| David Montgomery | RB | starter | 10.13 | 15.31 | 11.69 | -3.61 |
| Tetairoa McMillan | WR | starter | 10.3 | 17.44 | 20.99 | +3.55 |
| George Pickens | WR | starter | 9.24 | 14.7 | 18.24 | +3.54 |
| Kyle Monangai | RB | bench | 8.34 | 7.82 | 4.36 | -3.46 |
| Jonathan Taylor | RB | starter | 16.22 | 53.98 | 57.41 | +3.42 |
| Tony Pollard | RB | starter | 10.54 | 12.27 | 8.89 | -3.38 |
| Tee Higgins | WR | starter | 10.23 | 16.36 | 19.65 | +3.29 |
| Parker Washington | WR | starter | 9.31 | 14.4 | 17.63 | +3.23 |
| Jordan Mason | RB | bench | 8.7 | 6.48 | 3.33 | -3.15 |
| Derrick Henry | RB | starter | 16.59 | 51.28 | 54.27 | +2.99 |

### standard/10

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 13.91 | 42.02 | 56.0 | +13.98 |
| Ja'Marr Chase | WR | starter | 12.13 | 35.19 | 47.48 | +12.29 |
| Amon-Ra St. Brown | WR | starter | 11.8 | 33.25 | 44.68 | +11.43 |
| Puka Nacua | WR | starter | 13.69 | 37.56 | 48.66 | +11.09 |
| CeeDee Lamb | WR | starter | 12.43 | 34.6 | 45.43 | +10.83 |
| Chris Olave | WR | starter | 10.69 | 27.03 | 35.59 | +8.56 |
| Jahmyr Gibbs | RB | starter | 20.2 | 76.18 | 84.57 | +8.39 |
| Bijan Robinson | RB | starter | 18.56 | 71.02 | 78.94 | +7.92 |
| Justin Jefferson | WR | starter | 10.72 | 25.83 | 33.35 | +7.52 |
| Zay Flowers | WR | starter | 10.4 | 24.62 | 31.9 | +7.29 |
| Nico Collins | WR | starter | 10.99 | 25.84 | 32.88 | +7.03 |
| Kenneth Walker III | RB | starter | 17.88 | 66.6 | 73.59 | +6.99 |
| Drake London | WR | starter | 10.18 | 23.35 | 30.02 | +6.67 |
| Jonathan Taylor | RB | starter | 16.22 | 58.2 | 64.43 | +6.23 |
| RJ Harvey | RB | bench | 6.73 | 9.71 | 4.33 | -5.38 |
| Derrick Henry | RB | starter | 16.59 | 55.4 | 60.74 | +5.34 |
| Josh Allen | QB | starter | 23.39 | 28.27 | 33.53 | +5.26 |
| James Cook | RB | starter | 13.43 | 49.29 | 54.52 | +5.23 |
| Brian Robinson | RB | bench | 6.7 | 8.34 | 3.12 | -5.22 |
| Alvin Kamara | RB | bench | 6.31 | 7.43 | 2.4 | -5.03 |
| Kyle Monangai | RB | bench | 8.34 | 14.88 | 9.89 | -4.99 |
| Christian McCaffrey | RB | starter | 14.73 | 52.02 | 56.99 | +4.96 |
| Zach Charbonnet | RB | starter | 8.64 | 12.24 | 7.41 | -4.83 |
| Tony Pollard | RB | starter | 10.54 | 19.34 | 14.75 | -4.59 |
| Rico Dowdle | RB | bench | 6.39 | 6.78 | 2.28 | -4.50 |
| Jordan Mason | RB | starter | 8.7 | 13.07 | 8.57 | -4.49 |
| Rhamondre Stevenson | RB | starter | 9.34 | 20.25 | 15.79 | -4.47 |
| J.K. Dobbins | RB | starter | 8.66 | 11.72 | 7.29 | -4.43 |
| Travis Etienne | RB | bench | 8.46 | 15.78 | 11.46 | -4.32 |
| TreVeyon Henderson | RB | bench | 8.17 | 14.54 | 10.26 | -4.28 |

### standard/12

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 13.91 | 43.13 | 60.29 | +17.16 |
| Ja'Marr Chase | WR | starter | 12.13 | 36.23 | 51.5 | +15.27 |
| Amon-Ra St. Brown | WR | starter | 11.8 | 34.56 | 48.71 | +14.16 |
| CeeDee Lamb | WR | starter | 12.43 | 36.21 | 50.17 | +13.96 |
| Puka Nacua | WR | starter | 13.69 | 38.79 | 52.26 | +13.48 |
| Jahmyr Gibbs | RB | starter | 20.2 | 77.71 | 89.45 | +11.74 |
| Chris Olave | WR | starter | 10.69 | 28.74 | 39.97 | +11.23 |
| Bijan Robinson | RB | starter | 18.56 | 72.74 | 83.94 | +11.20 |
| Justin Jefferson | WR | starter | 10.72 | 27.59 | 37.8 | +10.22 |
| Kenneth Walker III | RB | starter | 17.88 | 68.22 | 78.19 | +9.97 |
| Zay Flowers | WR | starter | 10.4 | 26.35 | 36.04 | +9.69 |
| Nico Collins | WR | starter | 10.99 | 27.75 | 37.11 | +9.36 |
| Drake London | WR | starter | 10.18 | 25.2 | 33.95 | +8.75 |
| Jonathan Taylor | RB | starter | 16.22 | 60.58 | 69.21 | +8.63 |
| James Cook | RB | starter | 13.43 | 52.02 | 59.77 | +7.75 |
| Derrick Henry | RB | starter | 16.59 | 57.8 | 65.19 | +7.39 |
| Christian McCaffrey | RB | starter | 14.73 | 54.35 | 61.67 | +7.32 |
| Brock Bowers | TE | starter | 9.59 | 24.2 | 31.5 | +7.30 |
| Trey McBride | TE | starter | 9.05 | 21.59 | 27.85 | +6.26 |
| George Pickens | WR | starter | 9.24 | 19.68 | 25.61 | +5.94 |
| Rico Dowdle | RB | bench | 6.39 | 11.25 | 5.36 | -5.89 |
| Christian Watson | WR | starter | 10.18 | 22.1 | 27.82 | +5.72 |
| Bryce Young | QB | bench | 17.71 | 10.2 | 4.51 | -5.69 |
| Tetairoa McMillan | WR | starter | 10.3 | 22.19 | 27.84 | +5.65 |
| Brian Robinson | RB | bench | 6.7 | 12.46 | 6.92 | -5.54 |
| Alvin Kamara | RB | bench | 6.31 | 10.86 | 5.38 | -5.48 |
| Keaton Mitchell | RB | bench | 6.0 | 8.91 | 3.45 | -5.46 |
| Ollie Gordon II | RB | starter | 8.69 | 18.79 | 13.43 | -5.35 |
| Parker Washington | WR | starter | 9.31 | 19.41 | 24.75 | +5.34 |
| Kyren Williams | RB | starter | 14.17 | 48.47 | 53.79 | +5.32 |

### standard/14

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 13.91 | 42.7 | 65.38 | +22.68 |
| Ja'Marr Chase | WR | starter | 12.13 | 36.38 | 56.45 | +20.07 |
| CeeDee Lamb | WR | starter | 12.43 | 36.35 | 55.11 | +18.76 |
| Amon-Ra St. Brown | WR | starter | 11.8 | 34.88 | 53.5 | +18.63 |
| Puka Nacua | WR | starter | 13.69 | 38.41 | 56.22 | +17.81 |
| Chris Olave | WR | starter | 10.69 | 29.32 | 44.63 | +15.31 |
| Justin Jefferson | WR | starter | 10.72 | 28.21 | 42.27 | +14.06 |
| Zay Flowers | WR | starter | 10.4 | 27.0 | 40.32 | +13.32 |
| Nico Collins | WR | starter | 10.99 | 28.17 | 41.21 | +13.04 |
| Jahmyr Gibbs | RB | starter | 20.2 | 82.5 | 94.98 | +12.48 |
| Bijan Robinson | RB | starter | 18.56 | 77.25 | 89.58 | +12.33 |
| Drake London | WR | starter | 10.18 | 25.88 | 37.98 | +12.10 |
| Kenneth Walker III | RB | starter | 17.88 | 72.23 | 83.36 | +11.13 |
| Brock Bowers | TE | starter | 9.59 | 23.64 | 33.83 | +10.18 |
| Jonathan Taylor | RB | starter | 16.22 | 64.88 | 74.34 | +9.46 |
| James Cook | RB | starter | 13.43 | 56.09 | 65.33 | +9.24 |
| Trey McBride | TE | starter | 9.05 | 21.11 | 30.28 | +9.17 |
| Christian McCaffrey | RB | starter | 14.73 | 57.99 | 66.67 | +8.69 |
| George Pickens | WR | starter | 9.24 | 20.72 | 29.26 | +8.54 |
| Christian Watson | WR | starter | 10.18 | 22.76 | 31.01 | +8.25 |
| Tetairoa McMillan | WR | starter | 10.3 | 22.92 | 31.01 | +8.09 |
| Derrick Henry | RB | starter | 16.59 | 61.98 | 69.85 | +7.87 |
| Parker Washington | WR | starter | 9.31 | 20.38 | 28.09 | +7.71 |
| DeVonta Smith | WR | starter | 8.77 | 18.93 | 26.57 | +7.64 |
| Tee Higgins | WR | starter | 10.23 | 22.2 | 29.64 | +7.44 |
| Garrett Wilson | WR | starter | 8.74 | 19.28 | 26.69 | +7.41 |
| Davante Adams | WR | starter | 10.81 | 22.49 | 28.9 | +6.41 |
| Kyren Williams | RB | starter | 14.17 | 52.13 | 58.25 | +6.12 |
| Malik Nabers | WR | starter | 7.7 | 16.21 | 22.32 | +6.11 |
| Javonte Williams | RB | starter | 13.95 | 50.4 | 56.36 | +5.97 |

### half_ppr/8

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 17.24 | 41.78 | 55.0 | +13.22 |
| Ja'Marr Chase | WR | starter | 15.71 | 36.09 | 47.73 | +11.64 |
| Puka Nacua | WR | starter | 17.37 | 38.41 | 49.28 | +10.87 |
| Amon-Ra St. Brown | WR | starter | 15.32 | 34.06 | 44.73 | +10.67 |
| CeeDee Lamb | WR | starter | 15.97 | 35.08 | 45.18 | +10.10 |
| Chris Olave | WR | starter | 13.84 | 26.61 | 34.48 | +7.87 |
| Justin Jefferson | WR | starter | 13.66 | 25.13 | 31.8 | +6.67 |
| Zay Flowers | WR | starter | 12.94 | 22.75 | 29.14 | +6.40 |
| Nico Collins | WR | starter | 13.73 | 24.13 | 30.4 | +6.27 |
| Drake London | WR | starter | 12.83 | 21.75 | 27.73 | +5.98 |
| Jahmyr Gibbs | RB | starter | 22.48 | 71.54 | 77.47 | +5.93 |
| Bijan Robinson | RB | starter | 20.27 | 64.96 | 70.09 | +5.12 |
| Rhamondre Stevenson | RB | bench | 10.61 | 13.85 | 8.96 | -4.89 |
| Travis Etienne | RB | bench | 9.68 | 9.94 | 5.5 | -4.44 |
| Kenneth Walker III | RB | starter | 19.41 | 60.02 | 64.32 | +4.30 |
| Quinshon Judkins | RB | starter | 12.4 | 19.77 | 15.56 | -4.21 |
| Aaron Jones | RB | bench | 10.63 | 11.62 | 7.51 | -4.11 |
| Jonathan Taylor | RB | starter | 17.5 | 50.77 | 54.55 | +3.78 |
| David Montgomery | RB | starter | 11.0 | 14.11 | 10.38 | -3.73 |
| Omarion Hampton | RB | starter | 10.63 | 17.63 | 13.93 | -3.70 |
| TreVeyon Henderson | RB | bench | 8.84 | 7.33 | 3.91 | -3.42 |
| Kyle Monangai | RB | bench | 8.98 | 6.67 | 3.25 | -3.42 |
| Christian Watson | WR | starter | 12.44 | 17.29 | 20.62 | +3.34 |
| Tony Pollard | RB | starter | 11.65 | 11.35 | 8.04 | -3.31 |
| Tetairoa McMillan | WR | starter | 13.17 | 19.26 | 22.5 | +3.24 |
| Derrick Henry | RB | starter | 17.26 | 46.42 | 49.62 | +3.20 |
| George Pickens | WR | starter | 11.7 | 15.82 | 18.9 | +3.08 |
| Jordan Mason | RB | bench | 9.25 | 5.2 | 2.17 | -3.03 |
| Deebo Samuel Sr. | WR | bench | 9.03 | 5.75 | 2.74 | -3.01 |
| Rome Odunze | WR | bench | 8.51 | 4.79 | 1.79 | -3.00 |

### half_ppr/10

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 17.24 | 44.23 | 57.66 | +13.43 |
| Ja'Marr Chase | WR | starter | 15.71 | 38.52 | 50.62 | +12.11 |
| Amon-Ra St. Brown | WR | starter | 15.32 | 36.8 | 47.92 | +11.12 |
| Puka Nacua | WR | starter | 17.37 | 40.39 | 51.18 | +10.79 |
| CeeDee Lamb | WR | starter | 15.97 | 37.82 | 48.26 | +10.44 |
| Chris Olave | WR | starter | 13.84 | 29.93 | 38.21 | +8.28 |
| Justin Jefferson | WR | starter | 13.66 | 28.17 | 35.51 | +7.34 |
| Josh Allen | QB | starter | 23.39 | 24.4 | 31.56 | +7.15 |
| Zay Flowers | WR | starter | 12.94 | 26.08 | 33.02 | +6.94 |
| Nico Collins | WR | starter | 13.73 | 27.47 | 34.07 | +6.60 |
| Drake London | WR | starter | 12.83 | 25.23 | 31.58 | +6.35 |
| Jahmyr Gibbs | RB | starter | 22.48 | 76.31 | 82.2 | +5.89 |
| Bijan Robinson | RB | starter | 20.27 | 70.09 | 75.74 | +5.65 |
| Kenneth Walker III | RB | starter | 19.41 | 65.11 | 70.12 | +5.02 |
| RJ Harvey | RB | bench | 8.73 | 10.79 | 6.37 | -4.43 |
| Jonathan Taylor | RB | starter | 17.5 | 56.52 | 60.87 | +4.35 |
| Josh Downs | WR | bench | 8.62 | 8.73 | 4.38 | -4.35 |
| Alvin Kamara | RB | bench | 7.52 | 6.92 | 2.87 | -4.05 |
| Romeo Doubs | WR | bench | 7.81 | 5.95 | 2.0 | -3.95 |
| Stefon Diggs | WR | bench | 8.76 | 8.42 | 4.63 | -3.79 |
| Brian Robinson | RB | bench | 7.03 | 5.81 | 2.05 | -3.77 |
| Tetairoa McMillan | WR | starter | 13.17 | 22.21 | 25.97 | +3.77 |
| George Pickens | WR | starter | 11.7 | 19.23 | 22.93 | +3.70 |
| Christian McCaffrey | RB | starter | 16.75 | 52.31 | 55.98 | +3.68 |
| Christian Watson | WR | starter | 12.44 | 20.68 | 24.35 | +3.67 |
| Jordan Addison | WR | bench | 8.03 | 6.06 | 2.44 | -3.62 |
| Derrick Henry | RB | starter | 17.26 | 52.14 | 55.74 | +3.60 |
| Rico Dowdle | RB | bench | 7.25 | 5.59 | 2.0 | -3.59 |
| Kyle Monangai | RB | bench | 8.98 | 12.03 | 8.47 | -3.57 |
| Brock Bowers | TE | starter | 12.59 | 25.94 | 29.48 | +3.54 |

### half_ppr/12

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 17.24 | 45.14 | 62.84 | +17.70 |
| Ja'Marr Chase | WR | starter | 15.71 | 39.65 | 55.28 | +15.63 |
| Amon-Ra St. Brown | WR | starter | 15.32 | 38.05 | 52.61 | +14.56 |
| CeeDee Lamb | WR | starter | 15.97 | 39.37 | 53.75 | +14.37 |
| Puka Nacua | WR | starter | 17.37 | 41.48 | 55.5 | +14.02 |
| Chris Olave | WR | starter | 13.84 | 31.8 | 43.21 | +11.41 |
| Justin Jefferson | WR | starter | 13.66 | 30.19 | 40.52 | +10.33 |
| Jahmyr Gibbs | RB | starter | 22.48 | 77.04 | 86.7 | +9.67 |
| Zay Flowers | WR | starter | 12.94 | 28.13 | 37.73 | +9.60 |
| Bijan Robinson | RB | starter | 20.27 | 71.01 | 80.47 | +9.47 |
| Nico Collins | WR | starter | 13.73 | 29.55 | 38.92 | +9.37 |
| Drake London | WR | starter | 12.83 | 27.34 | 36.12 | +8.79 |
| Kenneth Walker III | RB | starter | 19.41 | 65.86 | 74.53 | +8.67 |
| Jonathan Taylor | RB | starter | 17.5 | 58.13 | 65.39 | +7.27 |
| James Cook | RB | starter | 14.34 | 48.51 | 55.49 | +6.98 |
| Christian McCaffrey | RB | starter | 16.75 | 53.54 | 60.24 | +6.70 |
| Derrick Henry | RB | starter | 17.26 | 53.68 | 59.97 | +6.29 |
| Brock Bowers | TE | starter | 12.59 | 25.73 | 31.84 | +6.11 |
| Tetairoa McMillan | WR | starter | 13.17 | 24.55 | 30.19 | +5.64 |
| George Pickens | WR | starter | 11.7 | 21.54 | 27.09 | +5.54 |
| Trey McBride | TE | starter | 12.69 | 24.65 | 30.07 | +5.43 |
| Christian Watson | WR | starter | 12.44 | 23.02 | 28.45 | +5.43 |
| Bryce Young | QB | bench | 17.71 | 9.37 | 4.18 | -5.19 |
| Parker Washington | WR | starter | 11.51 | 20.85 | 25.96 | +5.11 |
| Garrett Wilson | WR | starter | 11.61 | 21.2 | 26.24 | +5.04 |
| DeVonta Smith | WR | starter | 11.51 | 20.45 | 25.43 | +4.99 |
| Tee Higgins | WR | starter | 12.87 | 23.09 | 27.85 | +4.76 |
| Kyren Williams | RB | starter | 15.81 | 47.23 | 51.96 | +4.73 |
| Javonte Williams | RB | starter | 15.36 | 45.0 | 49.65 | +4.65 |
| Rico Dowdle | RB | bench | 7.25 | 9.39 | 4.9 | -4.50 |

### half_ppr/14

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 17.24 | 47.01 | 68.34 | +21.33 |
| Ja'Marr Chase | WR | starter | 15.71 | 41.62 | 60.32 | +18.71 |
| CeeDee Lamb | WR | starter | 15.97 | 41.23 | 58.86 | +17.63 |
| Amon-Ra St. Brown | WR | starter | 15.32 | 40.07 | 57.61 | +17.54 |
| Puka Nacua | WR | starter | 17.37 | 42.79 | 59.66 | +16.86 |
| Chris Olave | WR | starter | 13.84 | 33.79 | 48.16 | +14.37 |
| Justin Jefferson | WR | starter | 13.66 | 32.08 | 45.25 | +13.16 |
| Zay Flowers | WR | starter | 12.94 | 30.13 | 42.4 | +12.26 |
| Nico Collins | WR | starter | 13.73 | 31.32 | 43.44 | +12.12 |
| Bijan Robinson | RB | starter | 20.27 | 73.77 | 85.46 | +11.69 |
| Jahmyr Gibbs | RB | starter | 22.48 | 79.91 | 91.52 | +11.61 |
| Drake London | WR | starter | 12.83 | 29.31 | 40.59 | +11.28 |
| Kenneth Walker III | RB | starter | 19.41 | 68.53 | 79.12 | +10.60 |
| Jonathan Taylor | RB | starter | 17.5 | 60.7 | 69.96 | +9.27 |
| James Cook | RB | starter | 14.34 | 51.36 | 60.52 | +9.16 |
| Christian McCaffrey | RB | starter | 16.75 | 56.12 | 64.6 | +8.47 |
| Derrick Henry | RB | starter | 17.26 | 56.37 | 64.3 | +7.92 |
| George Pickens | WR | starter | 11.7 | 23.36 | 31.07 | +7.71 |
| Tetairoa McMillan | WR | starter | 13.17 | 25.99 | 33.55 | +7.56 |
| Christian Watson | WR | starter | 12.44 | 24.63 | 32.02 | +7.38 |
| Parker Washington | WR | starter | 11.51 | 22.69 | 29.76 | +7.06 |
| DeVonta Smith | WR | starter | 11.51 | 22.24 | 29.17 | +6.93 |
| Garrett Wilson | WR | starter | 11.61 | 23.09 | 30.0 | +6.91 |
| Tee Higgins | WR | starter | 12.87 | 24.49 | 31.28 | +6.79 |
| Kyren Williams | RB | starter | 15.81 | 49.53 | 55.82 | +6.29 |
| Chase Brown | RB | starter | 14.86 | 46.12 | 52.35 | +6.23 |
| Javonte Williams | RB | starter | 15.36 | 47.34 | 53.53 | +6.19 |
| Brock Bowers | TE | starter | 12.59 | 28.54 | 34.56 | +6.02 |
| Davante Adams | WR | starter | 13.32 | 24.11 | 29.88 | +5.77 |
| Ashton Jeanty | RB | starter | 14.48 | 45.1 | 50.85 | +5.75 |

### ppr/8

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 20.57 | 46.56 | 56.25 | +9.70 |
| Puka Nacua | WR | starter | 21.02 | 42.11 | 50.84 | +8.73 |
| Ja'Marr Chase | WR | starter | 19.3 | 41.36 | 49.69 | +8.33 |
| Jahmyr Gibbs | RB | starter | 24.74 | 66.98 | 74.78 | +7.80 |
| Amon-Ra St. Brown | WR | starter | 18.84 | 39.55 | 47.35 | +7.80 |
| CeeDee Lamb | WR | starter | 19.51 | 39.82 | 47.3 | +7.48 |
| Bijan Robinson | RB | starter | 22.01 | 59.84 | 66.67 | +6.83 |
| Kenneth Walker III | RB | starter | 20.94 | 55.16 | 60.87 | +5.71 |
| Chris Olave | WR | starter | 17.02 | 31.62 | 37.0 | +5.38 |
| Jonathan Taylor | RB | starter | 18.74 | 45.44 | 50.79 | +5.35 |
| Christian McCaffrey | RB | starter | 18.77 | 44.07 | 48.46 | +4.38 |
| Derrick Henry | RB | starter | 17.88 | 40.2 | 44.57 | +4.36 |
| Justin Jefferson | WR | starter | 16.61 | 29.05 | 33.34 | +4.29 |
| Rome Odunze | WR | bench | 10.16 | 6.19 | 2.03 | -4.16 |
| Deebo Samuel Sr. | WR | bench | 10.74 | 6.87 | 2.73 | -4.14 |
| Kyren Williams | RB | starter | 17.42 | 35.69 | 39.73 | +4.05 |
| DK Metcalf | WR | bench | 11.98 | 9.07 | 5.02 | -4.05 |
| Nico Collins | WR | starter | 16.44 | 27.55 | 31.59 | +4.04 |
| Jameson Williams | WR | bench | 10.53 | 7.81 | 3.8 | -4.01 |
| Jalen Coker | WR | starter | 13.0 | 12.05 | 8.11 | -3.94 |
| Zay Flowers | WR | starter | 15.47 | 26.46 | 30.22 | +3.76 |
| Ladd McConkey | WR | bench | 11.27 | 9.96 | 6.23 | -3.72 |
| Stefon Diggs | WR | bench | 10.84 | 5.81 | 2.12 | -3.69 |
| Drake London | WR | starter | 15.49 | 25.78 | 29.43 | +3.65 |
| Emeka Egbuka | WR | bench | 11.23 | 8.53 | 4.9 | -3.63 |
| Josh Downs | WR | bench | 10.79 | 5.77 | 2.18 | -3.60 |
| Chase Brown | RB | starter | 17.08 | 34.44 | 37.96 | +3.52 |
| Javonte Williams | RB | starter | 16.78 | 33.74 | 37.03 | +3.29 |
| Rhamondre Stevenson | RB | bench | 11.88 | 11.86 | 8.6 | -3.26 |
| Denzel Boston | WR | bench | 11.27 | 6.6 | 3.46 | -3.14 |

### ppr/10

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 20.57 | 45.47 | 59.61 | +14.14 |
| Ja'Marr Chase | WR | starter | 19.3 | 40.62 | 53.26 | +12.64 |
| Puka Nacua | WR | starter | 21.02 | 41.65 | 53.56 | +11.90 |
| Amon-Ra St. Brown | WR | starter | 18.84 | 39.09 | 50.84 | +11.75 |
| CeeDee Lamb | WR | starter | 19.51 | 39.69 | 50.78 | +11.10 |
| Chris Olave | WR | starter | 17.02 | 32.2 | 40.74 | +8.54 |
| Josh Allen | QB | starter | 23.39 | 21.73 | 30.05 | +8.32 |
| Justin Jefferson | WR | starter | 16.61 | 29.87 | 37.43 | +7.56 |
| Zay Flowers | WR | starter | 15.47 | 27.43 | 34.26 | +6.83 |
| Nico Collins | WR | starter | 16.44 | 28.67 | 35.41 | +6.75 |
| Drake London | WR | starter | 15.49 | 26.89 | 33.27 | +6.38 |
| Jahmyr Gibbs | RB | starter | 24.74 | 74.28 | 80.4 | +6.11 |
| Stefon Diggs | WR | bench | 10.84 | 11.4 | 5.6 | -5.80 |
| Bijan Robinson | RB | starter | 22.01 | 67.32 | 72.99 | +5.67 |
| Kenneth Walker III | RB | starter | 20.94 | 62.04 | 67.03 | +4.99 |
| Romeo Doubs | WR | bench | 9.33 | 7.01 | 2.29 | -4.72 |
| Jakobi Meyers | WR | bench | 10.5 | 8.52 | 4.12 | -4.40 |
| Jonathan Taylor | RB | starter | 18.74 | 53.3 | 57.68 | +4.39 |
| Josh Downs | WR | bench | 10.79 | 10.12 | 5.75 | -4.37 |
| Tetairoa McMillan | WR | starter | 16.07 | 23.74 | 28.0 | +4.26 |
| Jordan Addison | WR | bench | 9.61 | 7.05 | 2.8 | -4.25 |
| Denzel Boston | WR | starter | 11.27 | 11.26 | 7.03 | -4.23 |
| Wan'Dale Robinson | WR | bench | 9.42 | 5.83 | 1.89 | -3.94 |
| Rome Odunze | WR | bench | 10.16 | 9.53 | 5.62 | -3.91 |
| Christian McCaffrey | RB | starter | 18.77 | 51.09 | 54.88 | +3.79 |
| Christian Watson | WR | starter | 14.71 | 21.37 | 25.0 | +3.63 |
| George Pickens | WR | starter | 14.2 | 20.63 | 24.22 | +3.59 |
| Brian Thomas Jr. | WR | bench | 9.04 | 5.54 | 1.95 | -3.59 |
| Derrick Henry | RB | starter | 17.88 | 47.74 | 51.31 | +3.57 |
| Lamar Jackson | QB | starter | 20.64 | 12.43 | 15.98 | +3.55 |

### ppr/12

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 20.57 | 51.37 | 65.02 | +13.66 |
| Ja'Marr Chase | WR | starter | 19.3 | 46.24 | 58.22 | +11.98 |
| Jahmyr Gibbs | RB | starter | 24.74 | 71.88 | 83.85 | +11.97 |
| Bijan Robinson | RB | starter | 22.01 | 65.39 | 76.76 | +11.37 |
| Amon-Ra St. Brown | WR | starter | 18.84 | 44.48 | 55.74 | +11.26 |
| CeeDee Lamb | WR | starter | 19.51 | 45.56 | 56.52 | +10.96 |
| Puka Nacua | WR | starter | 21.02 | 47.17 | 58.04 | +10.87 |
| Kenneth Walker III | RB | starter | 20.94 | 59.98 | 70.53 | +10.55 |
| Chris Olave | WR | starter | 17.02 | 37.34 | 46.15 | +8.81 |
| Jonathan Taylor | RB | starter | 18.74 | 52.65 | 61.42 | +8.78 |
| Christian McCaffrey | RB | starter | 18.77 | 49.82 | 58.29 | +8.46 |
| Romeo Doubs | WR | bench | 9.33 | 13.4 | 5.35 | -8.04 |
| Derrick Henry | RB | starter | 17.88 | 47.18 | 54.94 | +7.76 |
| James Cook | RB | starter | 15.27 | 43.35 | 51.11 | +7.76 |
| Justin Jefferson | WR | starter | 16.61 | 35.09 | 42.85 | +7.76 |
| Kalif Raymond | WR | bench | 7.37 | 8.21 | 0.91 | -7.30 |
| Zay Flowers | WR | starter | 15.47 | 32.3 | 39.48 | +7.18 |
| Nico Collins | WR | starter | 16.44 | 33.63 | 40.68 | +7.05 |
| Drake London | WR | starter | 15.49 | 31.64 | 38.35 | +6.71 |
| Kyren Williams | RB | starter | 17.42 | 43.28 | 49.73 | +6.45 |
| Chase Brown | RB | starter | 17.08 | 41.53 | 47.93 | +6.39 |
| Javonte Williams | RB | starter | 16.78 | 40.74 | 47.05 | +6.31 |
| Ashton Jeanty | RB | starter | 16.4 | 39.9 | 45.88 | +5.98 |
| Brian Thomas Jr. | WR | bench | 9.04 | 10.4 | 4.69 | -5.71 |
| Malik Washington | WR | starter | 10.27 | 11.27 | 5.76 | -5.51 |
| Chris Godwin | WR | bench | 8.88 | 9.76 | 4.61 | -5.14 |
| Jordan Addison | WR | bench | 9.61 | 10.44 | 5.58 | -4.86 |
| Tre Tucker | WR | bench | 9.02 | 7.67 | 2.82 | -4.85 |
| Dontayvion Wicks | WR | bench | 8.36 | 7.22 | 2.45 | -4.78 |
| Courtland Sutton | WR | bench | 9.53 | 9.41 | 4.78 | -4.63 |

### ppr/14

| Player | Pos | Tier | Points per game | Before | After A | Change |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 20.57 | 51.95 | 69.89 | +17.94 |
| Ja'Marr Chase | WR | starter | 19.3 | 46.82 | 62.53 | +15.71 |
| CeeDee Lamb | WR | starter | 19.51 | 46.17 | 61.05 | +14.88 |
| Amon-Ra St. Brown | WR | starter | 18.84 | 45.22 | 60.09 | +14.86 |
| Puka Nacua | WR | starter | 21.02 | 47.34 | 61.78 | +14.45 |
| Jahmyr Gibbs | RB | starter | 24.74 | 74.79 | 88.32 | +13.53 |
| Bijan Robinson | RB | starter | 22.01 | 68.28 | 81.62 | +13.34 |
| Chris Olave | WR | starter | 17.02 | 38.28 | 50.48 | +12.20 |
| Kenneth Walker III | RB | starter | 20.94 | 63.03 | 75.21 | +12.18 |
| Justin Jefferson | WR | starter | 16.61 | 35.91 | 47.01 | +11.10 |
| Jonathan Taylor | RB | starter | 18.74 | 55.17 | 65.84 | +10.67 |
| Zay Flowers | WR | starter | 15.47 | 33.43 | 43.61 | +10.19 |
| Nico Collins | WR | starter | 16.44 | 34.56 | 44.71 | +10.14 |
| James Cook | RB | starter | 15.27 | 46.18 | 56.19 | +10.01 |
| Christian McCaffrey | RB | starter | 18.77 | 52.76 | 62.64 | +9.87 |
| Drake London | WR | starter | 15.49 | 32.82 | 42.34 | +9.53 |
| Derrick Henry | RB | starter | 17.88 | 49.85 | 59.22 | +9.37 |
| Chase Brown | RB | starter | 17.08 | 44.15 | 51.94 | +7.79 |
| Kyren Williams | RB | starter | 17.42 | 45.71 | 53.49 | +7.78 |
| Javonte Williams | RB | starter | 16.78 | 43.39 | 51.02 | +7.63 |
| Ashton Jeanty | RB | starter | 16.4 | 42.57 | 49.85 | +7.29 |
| Tetairoa McMillan | WR | starter | 16.07 | 29.02 | 35.67 | +6.64 |
| George Pickens | WR | starter | 14.2 | 25.88 | 32.24 | +6.36 |
| Christian Watson | WR | starter | 14.71 | 26.7 | 32.8 | +6.10 |
| Garrett Wilson | WR | starter | 14.5 | 26.51 | 32.5 | +5.98 |
| Parker Washington | WR | starter | 13.71 | 25.09 | 31.03 | +5.94 |
| DeVonta Smith | WR | starter | 14.21 | 25.05 | 30.86 | +5.81 |
| Chuba Hubbard | RB | starter | 12.57 | 33.17 | 38.97 | +5.80 |
| Tee Higgins | WR | starter | 15.52 | 26.76 | 32.52 | +5.76 |
| D'Andre Swift | RB | starter | 12.64 | 30.41 | 35.73 | +5.33 |
