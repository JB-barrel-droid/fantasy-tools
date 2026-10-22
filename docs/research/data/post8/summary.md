# Post 8 outputs (2026-10-22, pipelines/value_reference.py value-reference-002/2 at git cc576e71)
Setting {'scoring': 'ppr', 'teams': 12, 'superflex': 0}; weeks [2, 3, 4, 5, 6, 7]; trades drawn per week {2: 12000, 3: 12000, 4: 12000, 5: 12000, 6: 12000, 7: 12000}; balance band 0.2; seed 883.
Live week 7: charts available on the page ['usatoday', 'fantasypros', 'cbs']; excluded {'fantasycalc': 'held: fidelity: publisher_vs_stored'}.
Port check: {'ran': True, 'compared': 400, 'mismatches': 0, 'fields': ['propose', 'proposeConf', 'agree', 'of', 'accept', 'acceptConf', 'yes', 'deal', 'finder'], 'live': {'ran': True, 'compared': 200, 'mismatches': 0, 'examples': [], 'fields': ['propose', 'proposeConf', 'agree', 'of', 'accept', 'acceptConf', 'yes', 'deal', 'finder']}}

## Label frequencies, all weeks pooled (DDF Value = blended, the live rule)

propose:
| label | trades | share |
|---|---|---|
| Unclear / Low | 34985 | 48.6% |
| No / High | 18391 | 25.5% |
| Yes / High | 15444 | 21.4% |
| Yes / Medium | 1651 | 2.3% |
| No / Medium | 1529 | 2.1% |

propose reason:
| label | trades | share |
|---|---|---|
| No: both lose | 19920 | 27.7% |
| Unclear: thin | 18202 | 25.3% |
| Yes: both win | 17095 | 23.7% |
| Unclear: projections disagree | 14374 | 20.0% |
| Unclear: even | 1950 | 2.7% |
| Unclear: no projections | 459 | 0.6% |

accept:
| label | trades | share |
|---|---|---|
| Likely / High | 27909 | 38.8% |
| Unlikely / High | 17452 | 24.2% |
| Toss-up / Low | 12875 | 17.9% |
| Likely / Low | 9283 | 12.9% |
| Unlikely / Low | 4481 | 6.2% |

deal:
| label | trades | share |
|---|---|---|
| lose|lose | 25156 | 34.9% |
| win|win | 17996 | 25.0% |
| even|lose | 7423 | 10.3% |
| win|lose | 5237 | 7.3% |
| even|win | 4259 | 5.9% |
| win|even | 3874 | 5.4% |
| even|even | 3780 | 5.2% |
| lose|even | 2403 | 3.3% |
| lose|win | 1872 | 2.6% |

charts agree:
| label | trades | share |
|---|---|---|
| 4 of 4 | 26197 | 36.4% |
| 3 of 4 | 19301 | 26.8% |
| 2 of 4 | 13063 | 18.1% |
| 1 of 4 | 9146 | 12.7% |
| 0 of 4 | 4293 | 6.0% |

Finder rule (DDF win and 3+ of 4 charts have the rival even or winning): 8298 of 72000 (11.5%).

Propose line if DDF Value were projections only (PR #814):

| label | trades | share |
|---|---|---|
| No / High | 29301 | 40.7% |
| Yes / High | 24653 | 34.2% |
| Unclear / Low | 17432 | 24.2% |
| None / None | 614 | 0.9% |

## Propose answer by chart-agreement count (blended)

| charts agree | Yes | No | Unclear | trades |
|---|---|---|---|---|
| 0 | 17.9% | 6.1% | 75.9% | 4293 |
| 1 | 23.9% | 11.8% | 64.3% | 9146 |
| 2 | 26.5% | 16.7% | 56.7% | 13063 |
| 3 | 25.5% | 25.6% | 48.9% | 19301 |
| 4 | 21.9% | 43.7% | 34.3% | 26197 |

## Next-week flips by label (see high_by_agree.csv, stability.csv)

| variant | propose | confidence | charts agree | trades | propose answer changes | 95% CI | DDF sign flips | Yes<->No |
|---|---|---|---|---|---|---|---|---|
| blended | Yes | High | 0 | 636 | 36.0% | 32.5% to 39.3% | 24.2% | 11.0% |
| blended | Yes | High | 1 | 1703 | 36.2% | 34.1% to 38.4% | 21.5% | 9.8% |
| blended | Yes | High | 2 | 2566 | 33.5% | 31.7% to 35.2% | 15.9% | 7.4% |
| blended | Yes | High | 3 | 3620 | 26.6% | 25.2% to 27.9% | 11.4% | 5.0% |
| blended | Yes | High | 4 | 4186 | 18.7% | 17.6% to 19.9% | 6.7% | 2.9% |
| blended | Yes | High | any | 12711 | 27.2% | 26.4% to 27.9% | 12.7% | 5.7% |
| blended | Yes | Medium | 0 | 20 | 75.0% | 55.0% to 92.6% | 40.0% | 25.0% |
| blended | Yes | Medium | 1 | 97 | 49.5% | 40.2% to 58.8% | 23.7% | 8.2% |
| blended | Yes | Medium | 2 | 247 | 55.5% | 49.4% to 61.8% | 19.4% | 10.9% |
| blended | Yes | Medium | 3 | 425 | 45.9% | 41.2% to 50.7% | 14.6% | 5.9% |
| blended | Yes | Medium | 4 | 553 | 39.8% | 36.0% to 43.8% | 9.0% | 4.0% |
| blended | Yes | Medium | any | 1342 | 45.8% | 43.6% to 48.4% | 14.2% | 6.5% |
| blended | No | High | 0 | 226 | 28.3% | 22.6% to 34.1% | 19.9% | 10.2% |
| blended | No | High | 1 | 865 | 34.8% | 31.7% to 37.8% | 20.5% | 8.3% |
| blended | No | High | 2 | 1709 | 33.3% | 31.0% to 35.6% | 17.7% | 7.5% |
| blended | No | High | 3 | 3669 | 29.3% | 27.9% to 30.7% | 13.9% | 5.5% |
| blended | No | High | 4 | 8557 | 20.6% | 19.7% to 21.5% | 8.5% | 3.4% |
| blended | No | High | any | 15026 | 25.1% | 24.4% to 25.8% | 11.7% | 4.8% |
| blended | No | Medium | 0 | 2 | 50.0% | 0.0% to 100.0% | 0.0% | 0.0% |
| blended | No | Medium | 1 | 19 | 42.1% | 21.1% to 63.2% | 31.6% | 15.8% |
| blended | No | Medium | 2 | 85 | 36.5% | 25.9% to 46.5% | 11.8% | 3.5% |
| blended | No | Medium | 3 | 293 | 47.8% | 42.3% to 53.2% | 18.1% | 6.1% |
| blended | No | Medium | 4 | 856 | 39.1% | 35.9% to 42.2% | 12.5% | 5.7% |
| blended | No | Medium | any | 1255 | 41.0% | 38.2% to 43.6% | 14.0% | 5.8% |
| blended | Unclear | Low | 0 | 2716 | 48.5% | 46.4% to 50.4% | 57.4% | 0.0% |
| blended | Unclear | Low | 1 | 4847 | 50.3% | 48.9% to 51.7% | 41.8% | 0.0% |
| blended | Unclear | Low | 2 | 6101 | 48.7% | 47.5% to 50.1% | 37.1% | 0.0% |
| blended | Unclear | Low | 3 | 7799 | 47.9% | 46.9% to 49.0% | 36.1% | 0.0% |
| blended | Unclear | Low | 4 | 7650 | 51.1% | 50.0% to 52.2% | 31.6% | 0.0% |
| blended | Unclear | Low | any | 29113 | 49.4% | 48.9% to 49.9% | 38.1% | 0.0% |
| projections | Yes | High | 0 | 4004 | 39.1% | 37.7% to 40.5% | 29.2% | 21.3% |
| projections | Yes | High | 1 | 4220 | 35.1% | 33.9% to 36.7% | 25.6% | 18.2% |
| projections | Yes | High | 2 | 3749 | 34.8% | 33.2% to 36.3% | 23.6% | 15.6% |
| projections | Yes | High | 3 | 4243 | 27.3% | 25.9% to 28.7% | 18.1% | 12.2% |
| projections | Yes | High | 4 | 4292 | 21.7% | 20.6% to 22.8% | 12.2% | 7.0% |
| projections | Yes | High | any | 20508 | 31.4% | 30.8% to 32.0% | 21.6% | 14.8% |
| projections | No | High | 0 | 2252 | 38.9% | 37.0% to 41.0% | 28.7% | 20.8% |
| projections | No | High | 1 | 3554 | 34.8% | 33.3% to 36.4% | 24.1% | 16.6% |
| projections | No | High | 2 | 3861 | 30.9% | 29.4% to 32.4% | 21.2% | 14.5% |
| projections | No | High | 3 | 5351 | 28.0% | 26.8% to 29.1% | 18.6% | 12.5% |
| projections | No | High | 4 | 9222 | 20.4% | 19.6% to 21.1% | 12.1% | 7.2% |
| projections | No | High | any | 24240 | 27.6% | 27.0% to 28.1% | 18.3% | 12.2% |
| projections | Unclear | Low | 0 | 2913 | 66.1% | 64.5% to 67.8% | 56.2% | 0.0% |
| projections | Unclear | Low | 1 | 2883 | 62.5% | 60.7% to 64.3% | 45.4% | 0.0% |
| projections | Unclear | Low | 2 | 2713 | 65.4% | 63.7% to 67.3% | 41.6% | 0.0% |
| projections | Unclear | Low | 3 | 2756 | 65.0% | 63.1% to 66.9% | 40.4% | 0.0% |
| projections | Unclear | Low | 4 | 2820 | 65.9% | 64.3% to 67.6% | 31.9% | 0.0% |
| projections | Unclear | Low | any | 14085 | 65.0% | 64.2% to 65.7% | 43.2% | 0.0% |

## High-confidence labels by package size, tier and position (blended)

| propose | group | trades | answer changes next week | 95% CI | DDF sign flips | all charts agreed |
|---|---|---|---|---|---|---|
| Yes / High | 1-for-1 | 2766 | 28.1% | 26.4% to 29.7% | 14.5% | 41.5% |
| Yes / High | 2-for-1 | 2838 | 30.0% | 28.3% to 31.7% | 15.3% | 15.2% |
| Yes / High | 2-for-2 | 3824 | 25.3% | 23.8% to 26.7% | 11.5% | 45.4% |
| Yes / High | 3-for-2 | 3283 | 26.0% | 24.6% to 27.5% | 10.5% | 26.6% |
| Yes / High | all bench | 742 | 44.9% | 41.4% to 48.4% | 31.4% | 6.1% |
| Yes / High | all starters | 3397 | 23.7% | 22.3% to 25.2% | 10.0% | 46.4% |
| Yes / High | mixed | 8572 | 27.0% | 26.0% to 27.9% | 12.2% | 29.9% |
| Yes / High | QB only | 79 | 26.6% | 17.7% to 36.7% | 13.9% | 26.6% |
| Yes / High | RB only | 533 | 23.4% | 19.7% to 27.0% | 9.9% | 48.6% |
| Yes / High | TE only | 28 | 35.7% | 17.9% to 53.6% | 25.0% | 3.6% |
| Yes / High | WR only | 791 | 28.6% | 25.8% to 31.4% | 12.4% | 44.4% |
| Yes / High | mixed positions | 11280 | 27.2% | 26.4% to 28.1% | 12.8% | 31.5% |
| No / High | 1-for-1 | 2707 | 28.9% | 27.1% to 30.8% | 13.9% | 41.6% |
| No / High | 2-for-1 | 4050 | 25.6% | 24.3% to 26.9% | 13.1% | 66.1% |
| No / High | 2-for-2 | 3711 | 25.8% | 24.3% to 27.2% | 11.1% | 46.0% |
| No / High | 3-for-2 | 4558 | 21.8% | 20.6% to 23.0% | 9.6% | 66.8% |
| No / High | all bench | 863 | 39.4% | 36.0% to 42.6% | 25.1% | 23.1% |
| No / High | all starters | 4069 | 23.5% | 22.2% to 24.8% | 9.5% | 60.9% |
| No / High | mixed | 10094 | 24.5% | 23.7% to 25.4% | 11.4% | 58.2% |
| No / High | QB only | 75 | 37.3% | 26.7% to 46.7% | 16.0% | 32.0% |
| No / High | RB only | 618 | 22.7% | 19.2% to 25.8% | 9.2% | 64.7% |
| No / High | TE only | 32 | 40.6% | 21.9% to 56.2% | 12.5% | 18.8% |
| No / High | WR only | 892 | 27.7% | 24.7% to 30.7% | 13.6% | 66.8% |
| No / High | mixed positions | 13409 | 24.9% | 24.1% to 25.7% | 11.7% | 56.2% |

## Stability week to week

| variant | weeks | trades | propose | accept | deal | DDF sign | Yes<->No | usatoday | fantasycalc | fantasypros | cbs | projections |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| blended | 2->3 | 12000 | 42.2% | 33.6% | 46.6% | 25.9% | 3.2% | 21.6% | 20.4% | 13.4% | 21.2% | 29.8% |
| blended | 3->4 | 11447 | 44.4% | 31.8% | 49.4% | 28.6% | 4.3% | 14.8% | 24.0% | 18.5% | 20.3% | 29.1% |
| blended | 4->5 | 12000 | 39.6% | 27.0% | 44.4% | 26.0% | 3.0% | 15.8% | 13.0% | 8.9% | 18.1% | 26.3% |
| blended | 5->6 | 12000 | 32.7% | 30.5% | 44.2% | 21.6% | 1.4% | 15.3% | 18.7% | 16.0% | 18.9% | 20.2% |
| blended | 6->7 | 12000 | 32.5% | 33.0% | 45.2% | 22.8% | 1.7% | 16.3% | 23.6% | 16.5% | 21.1% | 17.8% |
| projections | 2->3 | 12000 | 44.0% | 33.6% | 54.5% | 30.1% | 15.3% | 21.6% | 20.4% | 13.4% | 21.2% | 29.8% |
| projections | 3->4 | 11447 | 43.8% | 31.8% | 55.0% | 29.4% | 13.8% | 14.8% | 24.0% | 18.5% | 20.3% | 29.1% |
| projections | 4->5 | 12000 | 40.5% | 27.0% | 48.6% | 27.1% | 10.2% | 15.8% | 13.0% | 8.9% | 18.1% | 26.3% |
| projections | 5->6 | 12000 | 31.7% | 30.5% | 46.7% | 20.7% | 6.4% | 15.3% | 18.7% | 16.0% | 18.9% | 20.2% |
| projections | 6->7 | 12000 | 29.2% | 33.0% | 45.6% | 18.7% | 4.7% | 16.3% | 23.6% | 16.5% | 21.1% | 17.8% |

## Thresholds (DDF Value and DDF Projections both win now; blended)

| DDF margin >= | charts agree >= | trades | share of all | still win next week | still win by 5%+ | lose next week |
|---|---|---|---|---|---|---|
| 5.0% | 0 | 16230 | 27.3% | 84.2% | 75.1% | 15.3% |
| 5.0% | 1 | 15228 | 25.6% | 85.2% | 76.0% | 14.3% |
| 5.0% | 2 | 12862 | 21.6% | 87.3% | 77.9% | 12.3% |
| 5.0% | 3 | 9582 | 16.1% | 89.3% | 80.5% | 10.2% |
| 7.5% | 0 | 13868 | 23.3% | 85.9% | 78.3% | 13.7% |
| 7.5% | 1 | 13109 | 22.1% | 86.8% | 79.2% | 12.7% |
| 7.5% | 2 | 11308 | 19.0% | 88.6% | 81.0% | 11.0% |
| 7.5% | 3 | 8719 | 14.7% | 90.4% | 83.1% | 9.2% |
| 10.0% | 0 | 11279 | 19.0% | 87.2% | 81.0% | 12.3% |
| 10.0% | 1 | 10740 | 18.1% | 88.0% | 81.7% | 11.5% |
| 10.0% | 2 | 9416 | 15.8% | 89.6% | 83.2% | 10.0% |
| 10.0% | 3 | 7448 | 12.5% | 91.2% | 85.1% | 8.4% |
| 15.0% | 0 | 5784 | 9.7% | 89.9% | 85.3% | 9.8% |
| 15.0% | 1 | 5562 | 9.4% | 90.5% | 85.9% | 9.2% |
| 15.0% | 2 | 4972 | 8.4% | 91.7% | 87.2% | 8.1% |
| 15.0% | 3 | 4128 | 6.9% | 93.0% | 88.6% | 6.7% |

## Will they accept: same answer next week

| answer | confidence | trades | same next week | 95% CI |
|---|---|---|---|---|
| Likely | High | 22977 | 82.5% | 82.0% to 83.0% |
| Likely | Low | 7732 | 71.3% | 70.5% to 72.4% |
| Toss-up | Low | 10537 | 30.2% | 29.3% to 31.0% |
| Unlikely | High | 14521 | 76.0% | 75.3% to 76.6% |
| Unlikely | Low | 3680 | 60.8% | 59.1% to 62.4% |

## Pairwise rank correlation (Spearman), latest saved week

| chart a | chart b | group | players | rho |
|---|---|---|---|---|
| usatoday | fantasycalc | all | 269 | 0.9025 |
| usatoday | fantasycalc | QB | 33 | 0.9378 |
| usatoday | fantasycalc | RB | 86 | 0.952 |
| usatoday | fantasycalc | WR | 111 | 0.9378 |
| usatoday | fantasycalc | TE | 39 | 0.899 |
| usatoday | fantasycalc | starter | 84 | 0.8995 |
| usatoday | fantasycalc | bench | 83 | 0.6078 |
| usatoday | fantasypros | all | 268 | 0.8669 |
| usatoday | fantasypros | QB | 32 | 0.7056 |
| usatoday | fantasypros | RB | 86 | 0.9401 |
| usatoday | fantasypros | WR | 112 | 0.8981 |
| usatoday | fantasypros | TE | 38 | 0.8595 |
| usatoday | fantasypros | starter | 84 | 0.8234 |
| usatoday | fantasypros | bench | 83 | 0.6197 |
| usatoday | cbs | all | 267 | 0.881 |
| usatoday | cbs | QB | 32 | 0.8955 |
| usatoday | cbs | RB | 86 | 0.9221 |
| usatoday | cbs | WR | 111 | 0.8849 |
| usatoday | cbs | TE | 38 | 0.8626 |
| usatoday | cbs | starter | 84 | 0.9437 |
| usatoday | cbs | bench | 83 | 0.6744 |
| fantasycalc | fantasypros | all | 212 | 0.8441 |
| fantasycalc | fantasypros | QB | 33 | 0.7296 |
| fantasycalc | fantasypros | RB | 65 | 0.9528 |
| fantasycalc | fantasypros | WR | 85 | 0.9179 |
| fantasycalc | fantasypros | TE | 29 | 0.8911 |
| fantasycalc | fantasypros | starter | 84 | 0.8556 |
| fantasycalc | fantasypros | bench | 83 | 0.5021 |
| fantasycalc | cbs | all | 207 | 0.9191 |
| fantasycalc | cbs | QB | 33 | 0.9245 |
| fantasycalc | cbs | RB | 65 | 0.933 |
| fantasycalc | cbs | WR | 80 | 0.933 |
| fantasycalc | cbs | TE | 29 | 0.898 |
| fantasycalc | cbs | starter | 84 | 0.9473 |
| fantasycalc | cbs | bench | 83 | 0.6763 |
| fantasypros | cbs | all | 194 | 0.8358 |
| fantasypros | cbs | QB | 32 | 0.6913 |
| fantasypros | cbs | RB | 61 | 0.9295 |
| fantasypros | cbs | WR | 80 | 0.8847 |
| fantasypros | cbs | TE | 21 | 0.9013 |
| fantasypros | cbs | starter | 84 | 0.8716 |
| fantasypros | cbs | bench | 83 | 0.4677 |

## Pairwise trade-direction agreement (share of trades both series point the same way)

| a | b | group | trades | same direction |
|---|---|---|---|---|
| usatoday | fantasycalc | 1-for-1 | 16867 | 68.4% |
| usatoday | fantasycalc | 2-for-1 | 17357 | 67.4% |
| usatoday | fantasycalc | 2-for-2 | 17400 | 70.6% |
| usatoday | fantasycalc | 3-for-2 | 17557 | 69.3% |
| usatoday | fantasycalc | all bench | 10215 | 63.7% |
| usatoday | fantasycalc | all starters | 15866 | 72.6% |
| usatoday | fantasycalc | mixed | 43100 | 68.8% |
| usatoday | fantasycalc | QB only | 557 | 68.2% |
| usatoday | fantasycalc | RB only | 2795 | 74.4% |
| usatoday | fantasycalc | TE only | 217 | 65.4% |
| usatoday | fantasycalc | WR only | 4479 | 71.9% |
| usatoday | fantasycalc | mixed positions | 61133 | 68.5% |
| usatoday | fantasycalc | all | 69181 | 68.9% |
| usatoday | fantasypros | 1-for-1 | 16675 | 63.1% |
| usatoday | fantasypros | 2-for-1 | 17404 | 72.0% |
| usatoday | fantasypros | 2-for-2 | 17429 | 65.3% |
| usatoday | fantasypros | 3-for-2 | 17574 | 70.8% |
| usatoday | fantasypros | all bench | 9993 | 63.4% |
| usatoday | fantasypros | all starters | 15911 | 69.9% |
| usatoday | fantasypros | mixed | 43178 | 68.1% |
| usatoday | fantasypros | QB only | 417 | 56.6% |
| usatoday | fantasypros | RB only | 2782 | 73.3% |
| usatoday | fantasypros | TE only | 216 | 74.1% |
| usatoday | fantasypros | WR only | 4526 | 69.7% |
| usatoday | fantasypros | mixed positions | 61141 | 67.5% |
| usatoday | fantasypros | all | 69082 | 67.9% |
| usatoday | cbs | 1-for-1 | 15468 | 78.2% |
| usatoday | cbs | 2-for-1 | 16929 | 77.7% |
| usatoday | cbs | 2-for-2 | 17000 | 76.6% |
| usatoday | cbs | 3-for-2 | 17323 | 77.6% |
| usatoday | cbs | all bench | 9593 | 74.2% |
| usatoday | cbs | all starters | 15117 | 80.4% |
| usatoday | cbs | mixed | 42010 | 77.2% |
| usatoday | cbs | QB only | 502 | 70.5% |
| usatoday | cbs | RB only | 2621 | 77.0% |
| usatoday | cbs | TE only | 195 | 65.1% |
| usatoday | cbs | WR only | 4261 | 75.4% |
| usatoday | cbs | mixed positions | 59141 | 77.8% |
| usatoday | cbs | all | 66720 | 77.5% |
| fantasycalc | fantasypros | 1-for-1 | 17285 | 59.7% |
| fantasycalc | fantasypros | 2-for-1 | 17795 | 60.4% |
| fantasycalc | fantasypros | 2-for-2 | 17854 | 61.0% |
| fantasycalc | fantasypros | 3-for-2 | 17889 | 62.5% |
| fantasycalc | fantasypros | all bench | 10354 | 57.0% |
| fantasycalc | fantasypros | all starters | 16338 | 65.3% |
| fantasycalc | fantasypros | mixed | 44131 | 60.2% |
| fantasycalc | fantasypros | QB only | 459 | 66.2% |
| fantasycalc | fantasypros | RB only | 2896 | 71.0% |
| fantasycalc | fantasypros | TE only | 220 | 58.2% |
| fantasycalc | fantasypros | WR only | 4667 | 68.0% |
| fantasycalc | fantasypros | mixed positions | 62581 | 59.9% |
| fantasycalc | fantasypros | all | 70823 | 60.9% |
| fantasycalc | cbs | 1-for-1 | 15991 | 71.1% |
| fantasycalc | cbs | 2-for-1 | 17310 | 74.7% |
| fantasycalc | cbs | 2-for-2 | 17407 | 76.2% |
| fantasycalc | cbs | 3-for-2 | 17637 | 77.9% |
| fantasycalc | cbs | all bench | 9906 | 63.0% |
| fantasycalc | cbs | all starters | 15517 | 79.9% |
| fantasycalc | cbs | mixed | 42922 | 76.1% |
| fantasycalc | cbs | QB only | 546 | 74.2% |
| fantasycalc | cbs | RB only | 2723 | 75.2% |
| fantasycalc | cbs | TE only | 199 | 63.3% |
| fantasycalc | cbs | WR only | 4387 | 79.8% |
| fantasycalc | cbs | mixed positions | 60490 | 74.8% |
| fantasycalc | cbs | all | 68345 | 75.1% |
| fantasypros | cbs | 1-for-1 | 15763 | 62.1% |
| fantasypros | cbs | 2-for-1 | 17349 | 66.9% |
| fantasypros | cbs | 2-for-2 | 17442 | 63.0% |
| fantasypros | cbs | 3-for-2 | 17653 | 65.8% |
| fantasypros | cbs | all bench | 9657 | 62.2% |
| fantasypros | cbs | all starters | 15555 | 67.6% |
| fantasypros | cbs | mixed | 42995 | 63.9% |
| fantasypros | cbs | QB only | 397 | 61.5% |
| fantasypros | cbs | RB only | 2711 | 70.1% |
| fantasypros | cbs | TE only | 200 | 51.0% |
| fantasypros | cbs | WR only | 4424 | 70.7% |
| fantasypros | cbs | mixed positions | 60475 | 63.9% |
| fantasypros | cbs | all | 68207 | 64.5% |
| ddf_value | usatoday | 1-for-1 | 16475 | 68.0% |
| ddf_value | usatoday | 2-for-1 | 17264 | 65.8% |
| ddf_value | usatoday | 2-for-2 | 17343 | 72.0% |
| ddf_value | usatoday | 3-for-2 | 17531 | 70.8% |
| ddf_value | usatoday | all bench | 9709 | 59.6% |
| ddf_value | usatoday | all starters | 15888 | 75.5% |
| ddf_value | usatoday | mixed | 43016 | 69.0% |
| ddf_value | usatoday | QB only | 544 | 69.7% |
| ddf_value | usatoday | RB only | 2750 | 75.1% |
| ddf_value | usatoday | TE only | 214 | 63.5% |
| ddf_value | usatoday | WR only | 4436 | 74.8% |
| ddf_value | usatoday | mixed positions | 60669 | 68.5% |
| ddf_value | usatoday | all | 68613 | 69.2% |
| ddf_value | fantasycalc | 1-for-1 | 17074 | 72.0% |
| ddf_value | fantasycalc | 2-for-1 | 17655 | 75.3% |
| ddf_value | fantasycalc | 2-for-2 | 17766 | 78.5% |
| ddf_value | fantasycalc | 3-for-2 | 17843 | 80.5% |
| ddf_value | fantasycalc | all bench | 10061 | 60.7% |
| ddf_value | fantasycalc | all starters | 16318 | 80.7% |
| ddf_value | fantasycalc | mixed | 43959 | 78.8% |
| ddf_value | fantasycalc | QB only | 596 | 76.0% |
| ddf_value | fantasycalc | RB only | 2857 | 77.9% |
| ddf_value | fantasycalc | TE only | 218 | 66.5% |
| ddf_value | fantasycalc | WR only | 4576 | 79.3% |
| ddf_value | fantasycalc | mixed positions | 62091 | 76.4% |
| ddf_value | fantasycalc | all | 70338 | 76.6% |
| ddf_value | fantasypros | 1-for-1 | 16893 | 63.8% |
| ddf_value | fantasypros | 2-for-1 | 17697 | 62.6% |
| ddf_value | fantasypros | 2-for-2 | 17799 | 66.6% |
| ddf_value | fantasypros | 3-for-2 | 17862 | 66.6% |
| ddf_value | fantasypros | all bench | 9854 | 55.5% |
| ddf_value | fantasypros | all starters | 16360 | 71.9% |
| ddf_value | fantasypros | mixed | 44037 | 64.5% |
| ddf_value | fantasypros | QB only | 448 | 77.0% |
| ddf_value | fantasypros | RB only | 2847 | 71.1% |
| ddf_value | fantasypros | TE only | 217 | 58.1% |
| ddf_value | fantasypros | WR only | 4619 | 67.8% |
| ddf_value | fantasypros | mixed positions | 62120 | 64.4% |
| ddf_value | fantasypros | all | 70251 | 65.0% |
| ddf_value | cbs | 1-for-1 | 15609 | 71.3% |
| ddf_value | cbs | 2-for-1 | 17208 | 72.9% |
| ddf_value | cbs | 2-for-2 | 17353 | 76.9% |
| ddf_value | cbs | 3-for-2 | 17607 | 77.7% |
| ddf_value | cbs | all bench | 9400 | 59.0% |
| ddf_value | cbs | all starters | 15544 | 81.0% |
| ddf_value | cbs | mixed | 42833 | 76.0% |
| ddf_value | cbs | QB only | 533 | 71.9% |
| ddf_value | cbs | RB only | 2681 | 78.0% |
| ddf_value | cbs | TE only | 198 | 74.8% |
| ddf_value | cbs | WR only | 4341 | 78.3% |
| ddf_value | cbs | mixed positions | 60024 | 74.4% |
| ddf_value | cbs | all | 67777 | 74.8% |

## Superseded snapshots (same week, a different pull of one chart)

| week | chart | other pull | trades | propose answer differs | chart direction differs |
|---|---|---|---|---|---|
| 4 | usatoday | 2026-09-29T00:00 | 12000 | 0.1% | 0.1% |
| 5 | fantasycalc | 2026-10-09T17:05 | 12000 | 4.8% | 14.7% |
| 5 | fantasycalc | 2026-10-10T00:05 | 12000 | 4.6% | 14.3% |
| 5 | fantasycalc | 2026-10-10T07:05 | 12000 | 5.1% | 14.5% |
| 5 | fantasycalc | 2026-10-10T14:05 | 12000 | 4.9% | 14.6% |
| 5 | fantasycalc | 2026-10-10T21:05 | 12000 | 5.6% | 15.1% |
| 5 | fantasycalc | 2026-10-11T04:05 | 12000 | 5.7% | 15.4% |
| 5 | fantasycalc | 2026-10-11T11:05 | 12000 | 5.7% | 15.5% |
| 5 | fantasycalc | 2026-10-11T18:05 | 12000 | 5.6% | 15.1% |
| 5 | fantasycalc | 2026-10-12T01:05 | 12000 | 4.3% | 15.1% |
| 5 | fantasycalc | 2026-10-12T08:05 | 12000 | 4.8% | 15.9% |
| 5 | fantasycalc | 2026-10-12T15:05 | 12000 | 5.2% | 16.1% |
| 5 | fantasycalc | 2026-10-12T22:05 | 12000 | 5.0% | 16.9% |
| 5 | fantasypros | 2026-10-07 21:23 | 12000 | 0.1% | 0.0% |
| 5 | usatoday | 2026-10-07 00:00 | 12000 | 0.5% | 1.0% |
| 6 | cbs | 2026-10-13T21:35 | 12000 | 0.8% | 1.6% |
| 6 | cbs | 2026-10-14T12:35 | 12000 | 0.1% | 0.2% |
| 6 | fantasycalc | 2026-10-16T17:05 | 12000 | 3.9% | 14.0% |
| 6 | fantasycalc | 2026-10-17T00:05 | 12000 | 3.5% | 13.3% |
| 6 | fantasycalc | 2026-10-17T07:05 | 12000 | 3.7% | 15.1% |
| 6 | fantasycalc | 2026-10-17T14:05 | 12000 | 4.0% | 14.9% |
| 6 | fantasycalc | 2026-10-17T21:05 | 12000 | 3.9% | 15.4% |
| 6 | fantasycalc | 2026-10-18T04:05 | 12000 | 4.3% | 15.3% |
| 6 | fantasycalc | 2026-10-18T11:05 | 12000 | 4.4% | 16.1% |
| 6 | fantasycalc | 2026-10-18T18:05 | 12000 | 4.3% | 16.1% |
| 6 | fantasycalc | 2026-10-19T01:05 | 12000 | 4.0% | 15.6% |
| 6 | fantasycalc | 2026-10-19T08:05 | 12000 | 4.2% | 16.2% |
| 6 | fantasycalc | 2026-10-19T15:05 | 12000 | 4.3% | 16.2% |
| 6 | fantasycalc | 2026-10-19T22:05 | 12000 | 4.6% | 17.8% |
| 7 | fantasycalc | 2026-10-22T08:05 | 12000 | 1.4% | 3.5% |
| 7 | fantasycalc | 2026-10-22T15:05 | 12000 | 1.9% | 4.3% |
