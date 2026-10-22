# Gap backtest figures (JEG-882)

Generated 2026-10-22T22:01Z by `tools/research/gap_backtest.py` at cc576e71; reference value-reference-002/2; weeks [2, 3, 4, 5, 6, 7]; live build tv-20261022-1627-fee76c6 (read from the live site 2026-10-22; PR #814 unmerged).

Self-test: week 7 snapshot vs the reference's live run: 3670 values, max abs diff 0.0000, within 0.05: True (hidden in live run: ['fantasycalc']; held sources read from the served version: ['fantasycalc']; with the raw snapshot instead the DDF Value max diff is 0.32).


## Our value = DDF Value as blended live (charts and projections) (Full PPR, 12 teams)

### Lists by week

| Week | Sources saved | Compared | Priced by charts | Ours above 0 | Buy listed | Sell listed | Buy eligible | Sell eligible | Mean abs gap |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 5 | 361 | 203 | 193 | 2 | 32 | 52 | 113 | +1.50 |
| 3 | 6 | 513 | 204 | 201 | 9 | 33 | 58 | 106 | +0.99 |
| 4 | 7 | 707 | 203 | 212 | 11 | 25 | 66 | 101 | +0.74 |
| 5 | 7 | 731 | 208 | 217 | 15 | 28 | 71 | 98 | +0.75 |
| 6 | 7 | 736 | 207 | 219 | 10 | 24 | 64 | 106 | +0.77 |
| 7 | 7 | 734 | 209 | 214 | 4 | 22 | 61 | 103 | +0.77 |

### Horizon 1 week (n=1023 player-weeks, 239 players, weeks [2, 3, 4, 5, 6])

| Test | Spearman rho [95% cluster bootstrap] |
|---|---|
| gap vs change in consensus price | -0.15 [-0.22, -0.09] (n=1023) |
| gap vs change in our value | +0.01 [-0.06, +0.08] (n=1023) |
| gap vs change in gap | -0.23 [-0.28, -0.18] (n=1023) |
| position-demeaned gap vs change in consensus | -0.14 [-0.21, -0.08] (n=1023) |
| placebo (consensus own move t-1 to t) vs change in consensus | +0.18 [+0.11, +0.24] (n=818) |
| gap vs change in consensus, same rows as placebo | -0.17 [-0.24, -0.10] (n=818) |
| rank regression, change in consensus on gap and placebo | gap t=-4.9, placebo t=+5.0 (n=818) |

Per week (rho, gap vs change in consensus / vs change in ours):

| Week | n | consensus | ours |
|---|---|---|---|
| 2 | 203 | -0.07 | +0.08 |
| 3 | 202 | -0.16 | +0.07 |
| 4 | 203 | -0.04 | +0.08 |
| 5 | 208 | -0.27 | -0.13 |
| 6 | 207 | -0.20 | -0.07 |

Per position:

| Position | n | consensus | ours |
|---|---|---|---|
| QB | 160 | +0.02 | +0.21 |
| RB | 313 | -0.15 | +0.06 |
| WR | 412 | -0.14 | -0.02 |
| TE | 138 | -0.36 | -0.13 |

Quintiles of the gap (1 = charts pay least relative to us, 5 = most); outcome = change in consensus price:

| Bucket | Gap range | n | Mean change | Median change | Share up |
|---|---|---|---|---|---|
| 1 | -15.3 to -2.7 | 205 | +0.18 | -0.00 | 50% |
| 2 | -2.7 to +0.2 | 204 | +0.18 | +0.01 | 51% |
| 3 | +0.2 to +1.0 | 205 | +0.18 | -0.02 | 47% |
| 4 | +1.0 to +2.7 | 204 | -0.12 | -0.19 | 41% |
| 5 | +2.7 to +9.4 | 205 | -0.66 | -0.62 | 34% |

Same buckets; outcome = change in our value:

| Bucket | n | Mean change | Median change | Share up |
|---|---|---|---|---|
| 1 | 205 | -0.16 | -0.08 | 49% |
| 2 | 204 | -0.07 | -0.01 | 45% |
| 3 | 205 | +0.14 | +0.00 | 50% |
| 4 | 204 | +0.12 | -0.01 | 47% |
| 5 | 205 | +0.05 | -0.06 | 47% |

Base rates over all compared players: consensus up 45% [41, 48] (n=1023), down 55% [52, 59] (n=1023); mean change in consensus -0.05, in ours +0.02.

| List | n | Players | Mean gap | Consensus moves toward ours | Ours moves toward consensus | Gap closes | Still listed | Sign flips |
|---|---|---|---|---|---|---|---|---|
| sell listed | 142 | 69 | +2.5 | 65% [57, 73] (n=142) | 46% [37, 54] (n=142) | 54% [47, 61] (n=142) | 56% [46, 64] (n=142) | 15% [9, 22] (n=142) |
| sell eligible | 524 | 174 | +2.3 | 59% [55, 63] (n=524) | 50% [45, 54] (n=524) | 57% [54, 61] (n=524) | 19% [14, 25] (n=524) | 10% [8, 13] (n=524) |
| buy listed | 47 | 32 | -5.4 | 66% [52, 80] (n=47) | 53% [39, 67] (n=47) | 70% [56, 84] (n=47) | 32% [17, 45] (n=47) | 6% [0, 15] (n=47) |
| buy eligible | 311 | 101 | -4.3 | 52% [46, 57] (n=311) | 53% [46, 59] (n=311) | 57% [52, 62] (n=311) | 13% [8, 17] (n=311) | 12% [9, 17] (n=311) |

Persistence: gap vs gap 1 week later +0.84 [+0.80, +0.87] (n=1023); gap shrinks 54% [51, 56] (n=1023); sign flips 13% [10, 15] (n=1023); share of gap movement that came from the consensus side 49%.


### Horizon 2 weeks (n=816 player-weeks, 232 players, weeks [2, 3, 4, 5])

| Test | Spearman rho [95% cluster bootstrap] |
|---|---|
| gap vs change in consensus price | -0.10 [-0.20, -0.01] (n=816) |
| gap vs change in our value | +0.05 [-0.05, +0.14] (n=816) |
| gap vs change in gap | -0.29 [-0.36, -0.21] (n=816) |
| position-demeaned gap vs change in consensus | -0.08 [-0.18, +0.01] (n=816) |
| placebo (consensus own move t-1 to t) vs change in consensus | +0.15 [+0.06, +0.23] (n=613) |
| gap vs change in consensus, same rows as placebo | -0.11 [-0.21, -0.00] (n=613) |
| rank regression, change in consensus on gap and placebo | gap t=-2.5, placebo t=+3.6 (n=613) |

Per week (rho, gap vs change in consensus / vs change in ours):

| Week | n | consensus | ours |
|---|---|---|---|
| 2 | 201 | -0.08 | +0.09 |
| 3 | 204 | -0.08 | +0.11 |
| 4 | 203 | -0.05 | +0.07 |
| 5 | 208 | -0.20 | -0.07 |

Per position:

| Position | n | consensus | ours |
|---|---|---|---|
| QB | 127 | +0.13 | +0.25 |
| RB | 249 | -0.08 | +0.13 |
| WR | 328 | -0.09 | +0.00 |
| TE | 112 | -0.43 | -0.09 |

Quintiles of the gap (1 = charts pay least relative to us, 5 = most); outcome = change in consensus price:

| Bucket | Gap range | n | Mean change | Median change | Share up |
|---|---|---|---|---|---|
| 1 | -15.3 to -2.6 | 163 | -0.29 | -0.20 | 46% |
| 2 | -2.6 to +0.2 | 163 | +0.14 | +0.04 | 51% |
| 3 | +0.2 to +1.0 | 164 | +0.52 | -0.03 | 48% |
| 4 | +1.0 to +2.7 | 162 | +0.04 | -0.25 | 45% |
| 5 | +2.7 to +9.4 | 164 | -1.05 | -0.93 | 37% |

Same buckets; outcome = change in our value:

| Bucket | n | Mean change | Median change | Share up |
|---|---|---|---|---|
| 1 | 163 | -0.88 | -0.52 | 47% |
| 2 | 163 | -0.04 | +0.00 | 51% |
| 3 | 164 | +0.43 | +0.01 | 53% |
| 4 | 162 | +0.43 | +0.00 | 52% |
| 5 | 164 | +0.19 | +0.02 | 51% |

Base rates over all compared players: consensus up 45% [41, 50] (n=816), down 55% [50, 59] (n=816); mean change in consensus -0.13, in ours +0.02.

| List | n | Players | Mean gap | Consensus moves toward ours | Ours moves toward consensus | Gap closes | Still listed | Sign flips |
|---|---|---|---|---|---|---|---|---|
| sell listed | 118 | 63 | +2.6 | 59% [49, 69] (n=118) | 52% [42, 61] (n=118) | 49% [41, 57] (n=118) | 45% [33, 56] (n=118) | 21% [14, 31] (n=118) |
| sell eligible | 418 | 161 | +2.2 | 57% [51, 62] (n=418) | 53% [47, 58] (n=418) | 57% [52, 61] (n=418) | 16% [11, 21] (n=418) | 14% [10, 18] (n=418) |
| buy listed | 37 | 28 | -5.3 | 65% [49, 79] (n=37) | 43% [28, 59] (n=37) | 65% [49, 82] (n=37) | 16% [3, 30] (n=37) | 8% [0, 19] (n=37) |
| buy eligible | 246 | 93 | -4.3 | 49% [42, 57] (n=246) | 51% [43, 59] (n=246) | 54% [48, 60] (n=246) | 12% [8, 17] (n=246) | 17% [12, 23] (n=246) |

Persistence: gap vs gap 2 week later +0.73 [+0.67, +0.79] (n=816); gap shrinks 52% [48, 55] (n=816); sign flips 17% [14, 21] (n=816); share of gap movement that came from the consensus side 48%.


### Realised points (n=883 player-weeks, 227 players, signal weeks [2, 3, 4, 5, 6])

Spearman gap vs (actual minus ESPN projected points per game over the next two games): -0.01 [-0.09, +0.07] (n=883); projection vs actual +0.59; mean residual +0.33.

| Bucket | Gap range | n | Mean residual | Share beats projection |
|---|---|---|---|---|
| 1 | -15.3 to -2.8 | 177 | +0.45 | 49% |
| 2 | -2.8 to +0.1 | 176 | -0.10 | 51% |
| 3 | +0.1 to +1.0 | 177 | +0.98 | 53% |
| 4 | +1.0 to +2.7 | 176 | +0.17 | 46% |
| 5 | +2.7 to +9.4 | 177 | +0.15 | 49% |

sell listed: n=118, mean residual -0.36, beats projection 41% [30, 50] (n=118).

buy listed: n=42, mean residual +1.38, beats projection 55% [39, 71] (n=42).

Per position: QB +0.15 (n=146), RB +0.01 (n=260), WR -0.08 (n=348), TE -0.16 (n=129)


## Our value = DDF Value from projections only (PR #814 default) (Full PPR, 12 teams)

### Lists by week

| Week | Sources saved | Compared | Priced by charts | Ours above 0 | Buy listed | Sell listed | Buy eligible | Sell eligible | Mean abs gap |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 5 | 350 | 200 | 168 | 24 | 36 | 61 | 101 | +1.75 |
| 3 | 6 | 513 | 204 | 187 | 30 | 31 | 72 | 90 | +1.22 |
| 4 | 7 | 706 | 203 | 199 | 24 | 26 | 68 | 90 | +0.88 |
| 5 | 7 | 729 | 207 | 200 | 23 | 27 | 75 | 88 | +0.96 |
| 6 | 7 | 734 | 206 | 205 | 20 | 23 | 75 | 87 | +0.90 |
| 7 | 7 | 732 | 208 | 200 | 29 | 23 | 68 | 87 | +0.82 |

### Horizon 1 week (n=1017 player-weeks, 238 players, weeks [2, 3, 4, 5, 6])

| Test | Spearman rho [95% cluster bootstrap] |
|---|---|
| gap vs change in consensus price | -0.22 [-0.28, -0.16] (n=1017) |
| gap vs change in our value | +0.21 [+0.14, +0.27] (n=1017) |
| gap vs change in gap | -0.36 [-0.41, -0.31] (n=1017) |
| position-demeaned gap vs change in consensus | -0.22 [-0.28, -0.15] (n=1017) |
| placebo (consensus own move t-1 to t) vs change in consensus | +0.18 [+0.10, +0.25] (n=813) |
| gap vs change in consensus, same rows as placebo | -0.26 [-0.33, -0.19] (n=813) |
| rank regression, change in consensus on gap and placebo | gap t=-7.6, placebo t=+5.0 (n=813) |

Per week (rho, gap vs change in consensus / vs change in ours):

| Week | n | consensus | ours |
|---|---|---|---|
| 2 | 200 | -0.08 | +0.31 |
| 3 | 201 | -0.15 | +0.31 |
| 4 | 203 | -0.12 | +0.12 |
| 5 | 207 | -0.43 | +0.10 |
| 6 | 206 | -0.32 | +0.16 |

Per position:

| Position | n | consensus | ours |
|---|---|---|---|
| QB | 160 | -0.15 | +0.30 |
| RB | 312 | -0.21 | +0.25 |
| WR | 407 | -0.21 | +0.19 |
| TE | 138 | -0.36 | +0.15 |

Quintiles of the gap (1 = charts pay least relative to us, 5 = most); outcome = change in consensus price:

| Bucket | Gap range | n | Mean change | Median change | Share up |
|---|---|---|---|---|---|
| 1 | -24.9 to -3.2 | 204 | +0.59 | +0.38 | 58% |
| 2 | -3.2 to -0.1 | 203 | +0.06 | -0.03 | 48% |
| 3 | -0.1 to +0.8 | 203 | +0.20 | -0.02 | 45% |
| 4 | +0.8 to +2.9 | 203 | -0.25 | -0.26 | 35% |
| 5 | +2.9 to +19.1 | 204 | -0.81 | -0.76 | 36% |

Same buckets; outcome = change in our value:

| Bucket | n | Mean change | Median change | Share up |
|---|---|---|---|---|
| 1 | 204 | -1.44 | -0.97 | 34% |
| 2 | 203 | -0.03 | -0.25 | 43% |
| 3 | 203 | +0.07 | +0.00 | 40% |
| 4 | 203 | +0.60 | +0.00 | 47% |
| 5 | 204 | +0.82 | +0.06 | 52% |

Base rates over all compared players: consensus up 45% [41, 48] (n=1017), down 55% [52, 59] (n=1017); mean change in consensus -0.04, in ours +0.00.

| List | n | Players | Mean gap | Consensus moves toward ours | Ours moves toward consensus | Gap closes | Still listed | Sign flips |
|---|---|---|---|---|---|---|---|---|
| sell listed | 143 | 61 | +3.8 | 61% [52, 70] (n=143) | 53% [45, 61] (n=143) | 50% [44, 56] (n=143) | 59% [48, 68] (n=143) | 22% [16, 32] (n=143) |
| sell eligible | 455 | 169 | +3.1 | 61% [56, 66] (n=455) | 48% [43, 52] (n=455) | 55% [52, 59] (n=455) | 20% [14, 26] (n=455) | 17% [13, 21] (n=455) |
| buy listed | 121 | 62 | -6.9 | 60% [51, 68] (n=121) | 67% [58, 76] (n=121) | 63% [56, 70] (n=121) | 55% [44, 64] (n=121) | 16% [10, 24] (n=121) |
| buy eligible | 350 | 133 | -4.5 | 56% [50, 61] (n=350) | 64% [59, 69] (n=350) | 60% [54, 65] (n=350) | 27% [20, 33] (n=350) | 23% [18, 28] (n=350) |

Persistence: gap vs gap 1 week later +0.68 [+0.62, +0.73] (n=1017); gap shrinks 52% [50, 55] (n=1017); sign flips 21% [18, 23] (n=1017); share of gap movement that came from the consensus side 41%.


### Horizon 2 weeks (n=811 player-weeks, 231 players, weeks [2, 3, 4, 5])

| Test | Spearman rho [95% cluster bootstrap] |
|---|---|
| gap vs change in consensus price | -0.19 [-0.27, -0.11] (n=811) |
| gap vs change in our value | +0.20 [+0.11, +0.30] (n=811) |
| gap vs change in gap | -0.43 [-0.49, -0.36] (n=811) |
| position-demeaned gap vs change in consensus | -0.18 [-0.27, -0.10] (n=811) |
| placebo (consensus own move t-1 to t) vs change in consensus | +0.15 [+0.06, +0.23] (n=610) |
| gap vs change in consensus, same rows as placebo | -0.22 [-0.32, -0.12] (n=610) |
| rank regression, change in consensus on gap and placebo | gap t=-5.7, placebo t=+3.8 (n=610) |

Per week (rho, gap vs change in consensus / vs change in ours):

| Week | n | consensus | ours |
|---|---|---|---|
| 2 | 197 | -0.09 | +0.25 |
| 3 | 204 | -0.16 | +0.23 |
| 4 | 203 | -0.17 | +0.16 |
| 5 | 207 | -0.34 | +0.17 |

Per position:

| Position | n | consensus | ours |
|---|---|---|---|
| QB | 127 | -0.05 | +0.30 |
| RB | 248 | -0.18 | +0.22 |
| WR | 324 | -0.18 | +0.22 |
| TE | 112 | -0.39 | +0.13 |

Quintiles of the gap (1 = charts pay least relative to us, 5 = most); outcome = change in consensus price:

| Bucket | Gap range | n | Mean change | Median change | Share up |
|---|---|---|---|---|---|
| 1 | -24.9 to -3.2 | 162 | +0.59 | +0.68 | 55% |
| 2 | -3.2 to -0.1 | 162 | -0.03 | -0.02 | 49% |
| 3 | -0.1 to +0.8 | 162 | +0.36 | -0.02 | 47% |
| 4 | +0.8 to +3.0 | 162 | -0.07 | -0.40 | 40% |
| 5 | +3.0 to +19.1 | 163 | -1.40 | -1.21 | 36% |

Same buckets; outcome = change in our value:

| Bucket | n | Mean change | Median change | Share up |
|---|---|---|---|---|
| 1 | 162 | -2.15 | -1.59 | 36% |
| 2 | 162 | -0.15 | -0.20 | 48% |
| 3 | 162 | +0.26 | +0.00 | 42% |
| 4 | 162 | +0.97 | +0.04 | 54% |
| 5 | 163 | +1.22 | +0.18 | 56% |

Base rates over all compared players: consensus up 45% [41, 50] (n=811), down 55% [50, 58] (n=811); mean change in consensus -0.11, in ours +0.03.

| List | n | Players | Mean gap | Consensus moves toward ours | Ours moves toward consensus | Gap closes | Still listed | Sign flips |
|---|---|---|---|---|---|---|---|---|
| sell listed | 120 | 58 | +3.8 | 59% [49, 68] (n=120) | 54% [45, 64] (n=120) | 50% [43, 58] (n=120) | 47% [35, 57] (n=120) | 30% [20, 41] (n=120) |
| sell eligible | 368 | 156 | +3.1 | 60% [55, 66] (n=368) | 52% [46, 58] (n=368) | 57% [52, 62] (n=368) | 17% [11, 23] (n=368) | 21% [16, 26] (n=368) |
| buy listed | 99 | 52 | -6.6 | 63% [53, 73] (n=99) | 60% [50, 71] (n=99) | 62% [52, 71] (n=99) | 42% [29, 55] (n=99) | 28% [18, 39] (n=99) |
| buy eligible | 274 | 127 | -4.5 | 54% [47, 61] (n=274) | 59% [53, 66] (n=274) | 59% [53, 66] (n=274) | 22% [14, 29] (n=274) | 27% [21, 34] (n=274) |

Persistence: gap vs gap 2 week later +0.56 [+0.47, +0.63] (n=811); gap shrinks 53% [50, 56] (n=811); sign flips 25% [21, 29] (n=811); share of gap movement that came from the consensus side 44%.


### Realised points (n=883 player-weeks, 227 players, signal weeks [2, 3, 4, 5, 6])

Spearman gap vs (actual minus ESPN projected points per game over the next two games): -0.04 [-0.12, +0.04] (n=883); projection vs actual +0.59; mean residual +0.33.

| Bucket | Gap range | n | Mean residual | Share beats projection |
|---|---|---|---|---|
| 1 | -24.9 to -3.3 | 177 | +0.99 | 57% |
| 2 | -3.3 to -0.2 | 176 | -0.62 | 42% |
| 3 | -0.2 to +0.8 | 177 | +0.99 | 54% |
| 4 | +0.8 to +3.0 | 176 | +0.31 | 46% |
| 5 | +3.0 to +19.1 | 177 | -0.01 | 49% |

sell listed: n=122, mean residual +0.16, beats projection 48% [37, 59] (n=122).

buy listed: n=109, mean residual +0.93, beats projection 56% [46, 66] (n=109).

Per position: QB +0.04 (n=146), RB +0.02 (n=260), WR -0.10 (n=348), TE -0.17 (n=129)


## All 12 settings, our value = DDF Value (blend): Spearman gap vs next-week change in consensus

| Scoring | Teams | n | rho | 95% CI | rho (ours changes) | sell listed hit | buy listed hit |
|---|---|---|---|---|---|---|---|
| standard | 8 | 987 | -0.11 | [-0.18, -0.02] | +0.09 | 57% [46, 67] (n=83) | 68% [57, 81] (n=37) |
| standard | 10 | 1002 | -0.10 | [-0.18, -0.02] | +0.08 | 56% [48, 65] (n=126) | 64% [51, 78] (n=44) |
| standard | 12 | 1029 | -0.11 | [-0.20, -0.04] | -0.00 | 55% [46, 62] (n=155) | 63% [51, 76] (n=43) |
| standard | 14 | 1088 | -0.13 | [-0.22, -0.06] | -0.03 | 60% [53, 68] (n=165) | 54% [39, 68] (n=39) |
| half_ppr | 8 | 987 | -0.13 | [-0.20, -0.04] | +0.10 | 54% [44, 63] (n=84) | 69% [54, 85] (n=36) |
| half_ppr | 10 | 998 | -0.12 | [-0.19, -0.04] | +0.08 | 58% [50, 68] (n=117) | 64% [50, 78] (n=39) |
| half_ppr | 12 | 1028 | -0.13 | [-0.20, -0.06] | +0.02 | 63% [56, 71] (n=138) | 67% [57, 78] (n=46) |
| half_ppr | 14 | 1083 | -0.17 | [-0.25, -0.11] | -0.01 | 70% [59, 79] (n=133) | 64% [51, 78] (n=45) |
| ppr | 8 | 986 | -0.16 | [-0.22, -0.10] | +0.09 | 56% [47, 66] (n=96) | 63% [51, 80] (n=35) |
| ppr | 10 | 995 | -0.14 | [-0.22, -0.07] | +0.07 | 62% [53, 71] (n=108) | 57% [45, 70] (n=46) |
| ppr | 12 | 1023 | -0.15 | [-0.21, -0.09] | +0.01 | 65% [57, 74] (n=142) | 66% [53, 80] (n=47) |
| ppr | 14 | 1083 | -0.16 | [-0.21, -0.10] | +0.00 | 67% [57, 76] (n=134) | 70% [55, 85] (n=40) |
