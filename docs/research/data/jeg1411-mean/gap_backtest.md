# Gap backtest figures (JEG-882 / JEG-1411)

Aggregation: mean; modeled saved 2026 inputs.

Generated 2026-11-01T20:01Z by `tools/research/gap_backtest.py` at 88f51c1f; reference value-reference-002/2; weeks [2, 3, 4, 5, 6, 7]; live build unavailable: offline modeled rerun, no live check.

Fixture consistency check (not a live check): week 7 snapshot vs the reference's fixture run: 3690 values, max abs diff 14.3009, within 0.05: False (hidden in fixture run: []; held sources read from the served version: []; with the raw snapshot instead the DDF Value max diff is 8.24).


## Our value = DDF Value (Full PPR, 12 teams)

### Lists by week

| Week | Sources saved | Compared | Priced by charts | Ours above 0 | Buy listed | Sell listed | Buy eligible | Sell eligible | Mean abs gap |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 5 | 361 | 245 | 192 | 0 | 25 | 47 | 118 | +1.71 |
| 3 | 6 | 513 | 250 | 192 | 0 | 30 | 48 | 127 | +1.26 |
| 4 | 7 | 707 | 254 | 194 | 0 | 22 | 46 | 123 | +0.84 |
| 5 | 7 | 731 | 264 | 197 | 0 | 29 | 49 | 131 | +0.85 |
| 6 | 7 | 736 | 264 | 202 | 0 | 29 | 45 | 135 | +0.89 |
| 7 | 7 | 738 | 271 | 198 | 0 | 24 | 46 | 124 | +0.93 |

### Horizon 1 week (n=1274 player-weeks, 295 players, weeks [2, 3, 4, 5, 6])

| Test | Spearman rho [95% cluster bootstrap] |
|---|---|
| gap vs change in Trade chart average price | -0.02 [-0.09, +0.05] (n=1274) |
| gap vs change in our value | -0.02 [-0.10, +0.06] (n=1274) |
| gap vs change in gap | -0.12 [-0.18, -0.06] (n=1274) |
| position-demeaned gap vs change in Trade chart average | -0.02 [-0.09, +0.05] (n=1274) |
| placebo (Trade chart average own move t-1 to t) vs change in Trade chart average | +0.20 [+0.13, +0.27] (n=1021) |
| gap vs change in Trade chart average, same rows as placebo | -0.01 [-0.09, +0.06] (n=1021) |
| rank regression, change in Trade chart average on gap and placebo | gap t=-0.2, placebo t=+6.6 (n=1021) |

Per week (rho, gap vs change in Trade chart average / vs change in ours):

| Week | n | Trade chart average | ours |
|---|---|---|---|
| 2 | 244 | -0.05 | -0.04 |
| 3 | 248 | -0.12 | -0.00 |
| 4 | 254 | +0.10 | +0.05 |
| 5 | 264 | -0.05 | -0.11 |
| 6 | 264 | +0.03 | -0.01 |

Per position:

| Position | n | Trade chart average | ours |
|---|---|---|---|
| QB | 170 | +0.13 | +0.13 |
| RB | 385 | +0.02 | +0.02 |
| WR | 531 | -0.06 | -0.06 |
| TE | 188 | -0.15 | -0.08 |

Quintiles of the gap (1 = charts pay least relative to us, 5 = most); outcome = change in Trade chart average price:

| Bucket | Gap range | n | Mean change | Median change | Share up |
|---|---|---|---|---|---|
| 1 | -16.8 to -0.5 | 255 | -0.20 | -0.26 | 45% |
| 2 | -0.5 to +0.4 | 255 | +0.01 | -0.01 | 33% |
| 3 | +0.4 to +1.3 | 254 | +0.14 | -0.01 | 47% |
| 4 | +1.3 to +2.7 | 255 | +0.12 | -0.17 | 45% |
| 5 | +2.7 to +5.2 | 255 | -0.14 | -0.13 | 43% |

Same buckets; outcome = change in our value:

| Bucket | n | Mean change | Median change | Share up |
|---|---|---|---|---|
| 1 | 255 | -0.17 | -0.09 | 49% |
| 2 | 255 | -0.11 | +0.00 | 15% |
| 3 | 254 | +0.02 | +0.00 | 38% |
| 4 | 255 | +0.24 | -0.01 | 47% |
| 5 | 255 | +0.13 | -0.09 | 44% |

Base rates over all compared players: Trade chart average up 43% [39, 46] (n=1274), down 57% [54, 60] (n=1274); mean change in Trade chart average -0.02, in ours +0.02.

| List | n | Players | Mean gap | Consensus moves toward ours | Ours moves toward Trade chart average | Gap closes | Still listed | Sign flips |
|---|---|---|---|---|---|---|---|---|
| sell listed | 135 | 63 | +2.1 | 52% [43, 60] (n=135) | 52% [43, 60] (n=135) | 53% [46, 60] (n=135) | 56% [46, 65] (n=135) | 9% [5, 15] (n=135) |
| sell eligible | 634 | 184 | +2.3 | 54% [49, 58] (n=634) | 44% [40, 49] (n=634) | 57% [54, 61] (n=634) | 15% [11, 20] (n=634) | 2% [1, 3] (n=634) |
| buy listed | 0 | | | | | | | |
| buy eligible | 234 | 59 | -6.0 | 47% [39, 54] (n=234) | 50% [42, 58] (n=234) | 44% [38, 51] (n=234) | 0% [0, 0] (n=234) | 5% [2, 8] (n=234) |

Persistence: gap vs gap 1 week later +0.91 [+0.89, +0.93] (n=1274); gap shrinks 56% [53, 58] (n=1274); sign flips 3% [2, 4] (n=1274); share of gap movement that came from the Trade chart average side 48%.


### Horizon 2 weeks (n=1011 player-weeks, 289 players, weeks [2, 3, 4, 5])

| Test | Spearman rho [95% cluster bootstrap] |
|---|---|
| gap vs change in Trade chart average price | +0.01 [-0.08, +0.10] (n=1011) |
| gap vs change in our value | +0.05 [-0.06, +0.14] (n=1011) |
| gap vs change in gap | -0.21 [-0.29, -0.13] (n=1011) |
| position-demeaned gap vs change in Trade chart average | +0.01 [-0.07, +0.10] (n=1011) |
| placebo (Trade chart average own move t-1 to t) vs change in Trade chart average | +0.16 [+0.07, +0.23] (n=759) |
| gap vs change in Trade chart average, same rows as placebo | +0.03 [-0.07, +0.13] (n=759) |
| rank regression, change in Trade chart average on gap and placebo | gap t=+0.9, placebo t=+4.4 (n=759) |

Per week (rho, gap vs change in Trade chart average / vs change in ours):

| Week | n | Trade chart average | ours |
|---|---|---|---|
| 2 | 243 | -0.02 | +0.09 |
| 3 | 250 | -0.01 | +0.07 |
| 4 | 254 | +0.06 | +0.03 |
| 5 | 264 | +0.03 | -0.01 |

Per position:

| Position | n | Trade chart average | ours |
|---|---|---|---|
| QB | 135 | +0.23 | +0.19 |
| RB | 306 | +0.07 | +0.12 |
| WR | 420 | -0.02 | +0.02 |
| TE | 150 | -0.21 | -0.15 |

Quintiles of the gap (1 = charts pay least relative to us, 5 = most); outcome = change in Trade chart average price:

| Bucket | Gap range | n | Mean change | Median change | Share up |
|---|---|---|---|---|---|
| 1 | -16.8 to -0.5 | 202 | -0.66 | -0.74 | 42% |
| 2 | -0.5 to +0.3 | 202 | +0.06 | -0.01 | 33% |
| 3 | +0.3 to +1.3 | 203 | +0.37 | -0.02 | 49% |
| 4 | +1.3 to +2.7 | 201 | +0.18 | -0.14 | 45% |
| 5 | +2.7 to +5.2 | 203 | -0.17 | -0.32 | 44% |

Same buckets; outcome = change in our value:

| Bucket | n | Mean change | Median change | Share up |
|---|---|---|---|---|
| 1 | 202 | -0.78 | -0.71 | 45% |
| 2 | 202 | -0.14 | +0.00 | 22% |
| 3 | 203 | +0.18 | +0.00 | 39% |
| 4 | 201 | +0.48 | -0.01 | 47% |
| 5 | 203 | +0.42 | -0.03 | 49% |

Base rates over all compared players: Trade chart average up 43% [39, 47] (n=1011), down 57% [53, 61] (n=1011); mean change in Trade chart average -0.04, in ours +0.03.

| List | n | Players | Mean gap | Consensus moves toward ours | Ours moves toward Trade chart average | Gap closes | Still listed | Sign flips |
|---|---|---|---|---|---|---|---|---|
| sell listed | 105 | 55 | +2.1 | 50% [40, 61] (n=105) | 52% [43, 62] (n=105) | 55% [46, 65] (n=105) | 48% [36, 57] (n=105) | 14% [7, 22] (n=105) |
| sell eligible | 498 | 172 | +2.3 | 53% [48, 58] (n=498) | 47% [41, 53] (n=498) | 62% [57, 66] (n=498) | 15% [10, 20] (n=498) | 4% [2, 6] (n=498) |
| buy listed | 0 | | | | | | | |
| buy eligible | 189 | 58 | -5.9 | 42% [33, 51] (n=189) | 55% [46, 64] (n=189) | 48% [40, 57] (n=189) | 0% [0, 0] (n=189) | 8% [4, 13] (n=189) |

Persistence: gap vs gap 2 week later +0.82 [+0.77, +0.86] (n=1011); gap shrinks 58% [54, 61] (n=1011); sign flips 5% [4, 7] (n=1011); share of gap movement that came from the Trade chart average side 48%.


### Realised points (n=1299 player-weeks, 283 players, signal weeks [2, 3, 4, 5, 6, 7])

Spearman gap vs (actual minus ESPN projected points per game over the next two games): -0.02 [-0.09, +0.05] (n=1299); projection vs actual +0.63; mean residual +0.54.

| Bucket | Gap range | n | Mean residual | Share beats projection |
|---|---|---|---|---|
| 1 | -17.5 to -1.3 | 260 | +0.28 | 52% |
| 2 | -1.3 to +0.4 | 260 | +1.36 | 58% |
| 3 | +0.4 to +1.3 | 259 | +0.20 | 50% |
| 4 | +1.3 to +2.6 | 260 | +0.34 | 48% |
| 5 | +2.6 to +5.2 | 260 | +0.50 | 52% |

sell listed: n=136, mean residual -0.47, beats projection 45% [36, 53] (n=136).

Per position: QB -0.08 (n=185), RB +0.07 (n=375), WR -0.05 (n=530), TE -0.08 (n=209)


## Our value = DDF Value (projections) (Full PPR, 12 teams)

### Lists by week

| Week | Sources saved | Compared | Priced by charts | Ours above 0 | Buy listed | Sell listed | Buy eligible | Sell eligible | Mean abs gap |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 5 | 350 | 235 | 174 | 24 | 29 | 56 | 107 | +1.78 |
| 3 | 6 | 513 | 250 | 196 | 27 | 32 | 64 | 100 | +1.28 |
| 4 | 7 | 706 | 253 | 207 | 25 | 28 | 62 | 99 | +0.89 |
| 5 | 7 | 729 | 262 | 213 | 25 | 31 | 63 | 105 | +1.01 |
| 6 | 7 | 734 | 262 | 221 | 21 | 31 | 64 | 110 | +0.93 |
| 7 | 7 | 736 | 269 | 211 | 28 | 24 | 71 | 95 | +0.88 |

### Horizon 1 week (n=1259 player-weeks, 292 players, weeks [2, 3, 4, 5, 6])

| Test | Spearman rho [95% cluster bootstrap] |
|---|---|
| gap vs change in Trade chart average price | -0.19 [-0.26, -0.13] (n=1259) |
| gap vs change in our value | +0.19 [+0.13, +0.25] (n=1259) |
| gap vs change in gap | -0.34 [-0.39, -0.29] (n=1259) |
| position-demeaned gap vs change in Trade chart average | -0.20 [-0.27, -0.14] (n=1259) |
| placebo (Trade chart average own move t-1 to t) vs change in Trade chart average | +0.20 [+0.14, +0.27] (n=1011) |
| gap vs change in Trade chart average, same rows as placebo | -0.22 [-0.28, -0.14] (n=1011) |
| rank regression, change in Trade chart average on gap and placebo | gap t=-6.9, placebo t=+6.5 (n=1011) |

Per week (rho, gap vs change in Trade chart average / vs change in ours):

| Week | n | Trade chart average | ours |
|---|---|---|---|
| 2 | 235 | -0.08 | +0.29 |
| 3 | 247 | -0.11 | +0.27 |
| 4 | 253 | -0.08 | +0.11 |
| 5 | 262 | -0.45 | +0.11 |
| 6 | 262 | -0.23 | +0.15 |

Per position:

| Position | n | Trade chart average | ours |
|---|---|---|---|
| QB | 169 | -0.01 | +0.24 |
| RB | 377 | -0.19 | +0.22 |
| WR | 525 | -0.22 | +0.17 |
| TE | 188 | -0.31 | +0.16 |

Quintiles of the gap (1 = charts pay least relative to us, 5 = most); outcome = change in Trade chart average price:

| Bucket | Gap range | n | Mean change | Median change | Share up |
|---|---|---|---|---|---|
| 1 | -24.8 to -1.9 | 252 | +0.43 | +0.23 | 58% |
| 2 | -1.9 to +0.1 | 247 | -0.03 | -0.01 | 38% |
| 3 | +0.1 to +0.7 | 256 | +0.15 | -0.01 | 39% |
| 4 | +0.7 to +2.6 | 252 | -0.01 | -0.10 | 43% |
| 5 | +2.6 to +15.9 | 252 | -0.63 | -0.55 | 36% |

Same buckets; outcome = change in our value:

| Bucket | n | Mean change | Median change | Share up |
|---|---|---|---|---|
| 1 | 252 | -1.43 | -1.18 | 36% |
| 2 | 247 | +0.09 | +0.00 | 35% |
| 3 | 256 | +0.13 | +0.00 | 31% |
| 4 | 252 | +0.37 | +0.00 | 49% |
| 5 | 252 | +0.89 | +0.08 | 55% |

Base rates over all compared players: Trade chart average up 43% [40, 46] (n=1259), down 57% [54, 60] (n=1259); mean change in Trade chart average -0.02, in ours +0.01.

| List | n | Players | Mean gap | Consensus moves toward ours | Ours moves toward Trade chart average | Gap closes | Still listed | Sign flips |
|---|---|---|---|---|---|---|---|---|
| sell listed | 151 | 66 | +3.6 | 57% [48, 65] (n=151) | 49% [42, 56] (n=151) | 50% [43, 56] (n=151) | 62% [51, 71] (n=151) | 21% [15, 29] (n=151) |
| sell eligible | 520 | 188 | +2.9 | 59% [54, 63] (n=520) | 50% [46, 54] (n=520) | 59% [56, 63] (n=520) | 21% [15, 27] (n=520) | 14% [11, 17] (n=520) |
| buy listed | 122 | 61 | -6.8 | 66% [56, 74] (n=122) | 61% [53, 70] (n=122) | 67% [60, 75] (n=122) | 51% [39, 60] (n=122) | 16% [9, 25] (n=122) |
| buy eligible | 308 | 123 | -4.8 | 57% [51, 63] (n=308) | 64% [58, 69] (n=308) | 57% [53, 63] (n=308) | 28% [21, 35] (n=308) | 25% [20, 30] (n=308) |

Persistence: gap vs gap 1 week later +0.66 [+0.61, +0.72] (n=1259); gap shrinks 57% [54, 59] (n=1259); sign flips 17% [15, 20] (n=1259); share of gap movement that came from the Trade chart average side 40%.


### Horizon 2 weeks (n=997 player-weeks, 286 players, weeks [2, 3, 4, 5])

| Test | Spearman rho [95% cluster bootstrap] |
|---|---|
| gap vs change in Trade chart average price | -0.17 [-0.25, -0.09] (n=997) |
| gap vs change in our value | +0.19 [+0.09, +0.27] (n=997) |
| gap vs change in gap | -0.40 [-0.47, -0.33] (n=997) |
| position-demeaned gap vs change in Trade chart average | -0.17 [-0.25, -0.09] (n=997) |
| placebo (Trade chart average own move t-1 to t) vs change in Trade chart average | +0.16 [+0.08, +0.25] (n=752) |
| gap vs change in Trade chart average, same rows as placebo | -0.20 [-0.29, -0.11] (n=752) |
| rank regression, change in Trade chart average on gap and placebo | gap t=-5.6, placebo t=+4.5 (n=752) |

Per week (rho, gap vs change in Trade chart average / vs change in ours):

| Week | n | Trade chart average | ours |
|---|---|---|---|
| 2 | 232 | -0.08 | +0.26 |
| 3 | 250 | -0.11 | +0.19 |
| 4 | 253 | -0.17 | +0.16 |
| 5 | 262 | -0.32 | +0.14 |

Per position:

| Position | n | Trade chart average | ours |
|---|---|---|---|
| QB | 134 | -0.02 | +0.25 |
| RB | 298 | -0.18 | +0.19 |
| WR | 415 | -0.18 | +0.19 |
| TE | 150 | -0.29 | +0.11 |

Quintiles of the gap (1 = charts pay least relative to us, 5 = most); outcome = change in Trade chart average price:

| Bucket | Gap range | n | Mean change | Median change | Share up |
|---|---|---|---|---|---|
| 1 | -24.8 to -1.9 | 200 | +0.41 | +0.37 | 54% |
| 2 | -1.9 to +0.1 | 190 | +0.16 | -0.01 | 45% |
| 3 | +0.1 to +0.7 | 208 | +0.28 | -0.02 | 37% |
| 4 | +0.7 to +2.7 | 199 | +0.09 | -0.16 | 44% |
| 5 | +2.7 to +15.9 | 200 | -1.10 | -1.05 | 37% |

Same buckets; outcome = change in our value:

| Bucket | n | Mean change | Median change | Share up |
|---|---|---|---|---|
| 1 | 200 | -1.77 | -1.88 | 39% |
| 2 | 190 | +0.01 | +0.00 | 39% |
| 3 | 208 | +0.25 | +0.00 | 37% |
| 4 | 199 | +0.59 | +0.00 | 50% |
| 5 | 200 | +1.25 | +0.48 | 60% |

Base rates over all compared players: Trade chart average up 43% [39, 47] (n=997), down 57% [53, 61] (n=997); mean change in Trade chart average -0.03, in ours +0.07.

| List | n | Players | Mean gap | Consensus moves toward ours | Ours moves toward Trade chart average | Gap closes | Still listed | Sign flips |
|---|---|---|---|---|---|---|---|---|
| sell listed | 120 | 60 | +3.8 | 59% [49, 69] (n=120) | 52% [42, 63] (n=120) | 52% [44, 60] (n=120) | 53% [41, 65] (n=120) | 29% [20, 40] (n=120) |
| sell eligible | 410 | 177 | +3.0 | 59% [53, 64] (n=410) | 54% [48, 60] (n=410) | 61% [56, 66] (n=410) | 19% [13, 25] (n=410) | 17% [13, 21] (n=410) |
| buy listed | 99 | 54 | -6.5 | 66% [55, 76] (n=99) | 56% [45, 68] (n=99) | 65% [55, 74] (n=99) | 43% [31, 55] (n=99) | 26% [17, 36] (n=99) |
| buy eligible | 243 | 115 | -4.7 | 58% [49, 65] (n=243) | 61% [54, 67] (n=243) | 56% [49, 63] (n=243) | 25% [18, 33] (n=243) | 34% [27, 41] (n=243) |

Persistence: gap vs gap 2 week later +0.54 [+0.46, +0.61] (n=997); gap shrinks 56% [52, 59] (n=997); sign flips 22% [18, 25] (n=997); share of gap movement that came from the Trade chart average side 43%.


### Realised points (n=1299 player-weeks, 283 players, signal weeks [2, 3, 4, 5, 6, 7])

Spearman gap vs (actual minus ESPN projected points per game over the next two games): -0.05 [-0.12, +0.01] (n=1299); projection vs actual +0.63; mean residual +0.54.

| Bucket | Gap range | n | Mean residual | Share beats projection |
|---|---|---|---|---|
| 1 | -24.8 to -2.1 | 260 | +0.94 | 57% |
| 2 | -2.1 to +0.1 | 259 | +0.56 | 54% |
| 3 | +0.1 to +0.8 | 260 | +0.79 | 52% |
| 4 | +0.8 to +2.6 | 260 | +0.46 | 49% |
| 5 | +2.6 to +15.9 | 260 | -0.07 | 48% |

sell listed: n=150, mean residual -0.21, beats projection 44% [33, 54] (n=150).

buy listed: n=135, mean residual +1.04, beats projection 54% [46, 63] (n=135).

Per position: QB -0.08 (n=185), RB +0.03 (n=375), WR -0.09 (n=530), TE -0.11 (n=209)


## All 12 settings, our value = DDF Value: Spearman gap vs next-week change in Trade chart average

| Scoring | Teams | n | rho | 95% CI | rho (ours changes) | sell listed hit | buy listed hit |
|---|---|---|---|---|---|---|---|
| standard | 8 | 1263 | -0.04 | [-0.12, +0.03] | +0.08 | 51% [39, 62] (n=82) | n/a |
| standard | 10 | 1282 | -0.04 | [-0.12, +0.04] | +0.05 | 50% [40, 60] (n=132) | n/a |
| standard | 12 | 1300 | -0.04 | [-0.12, +0.04] | +0.01 | 51% [44, 60] (n=167) | n/a |
| standard | 14 | 1322 | -0.05 | [-0.12, +0.02] | -0.05 | 51% [45, 58] (n=178) | n/a |
| half_ppr | 8 | 1257 | -0.05 | [-0.11, +0.02] | +0.09 | 56% [46, 65] (n=89) | n/a |
| half_ppr | 10 | 1261 | -0.03 | [-0.11, +0.04] | +0.07 | 51% [42, 58] (n=134) | n/a |
| half_ppr | 12 | 1283 | -0.02 | [-0.09, +0.03] | +0.01 | 48% [39, 56] (n=159) | n/a |
| half_ppr | 14 | 1308 | -0.03 | [-0.11, +0.04] | -0.01 | 51% [43, 59] (n=135) | n/a |
| ppr | 8 | 1253 | -0.05 | [-0.11, +0.01] | +0.08 | 57% [44, 70] (n=88) | n/a |
| ppr | 10 | 1258 | -0.03 | [-0.10, +0.04] | +0.10 | 50% [43, 59] (n=129) | n/a |
| ppr | 12 | 1274 | -0.02 | [-0.09, +0.05] | -0.02 | 52% [43, 60] (n=135) | n/a |
| ppr | 14 | 1293 | -0.01 | [-0.08, +0.05] | +0.02 | 53% [46, 62] (n=115) | n/a |
