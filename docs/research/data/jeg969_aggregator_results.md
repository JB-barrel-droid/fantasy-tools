# JEG-969 Lane B: Aggregator Test Results

Script: `tools/research/jeg969_aggregator_tests.py`, run 2026-10-23.
All tests use PPR scoring unless noted. Bootstrap CIs: 2000 resamples, seed 20261023.

## Test A: Per-source ROS accuracy (2026 wk 2-6)

| Source | N | MAE | RMSE | Bias | 95% CI | Rank corr |
|--------|---|-----|------|------|--------|-----------|
| espn | 1425 | 4.677 | 6.399 | -0.902 | [4.449, 4.902] | 0.637 |
| cbsros | 703 | 5.046 | 6.657 | -0.714 | [4.732, 5.374] | 0.625 |
| razzball | 1171 | 4.501 | 6.304 | -1.267 | [4.259, 4.757] | 0.675 |

## Test B: ESPN week-ahead (2026 wk 1-6)

ESPN weekly: n=1940, MAE=4.393, RMSE=6.032, bias=-0.199, rank_corr=0.701

## Test C: RotoWire multi-season (2018-2025)

Overall: n=31437, MAE=4.767, RMSE=6.51, bias=0.118, rank_corr=0.686

| Season | N | MAE | Bias |
|--------|---|-----|------|
| 2018 | 1632 | 5.52 | -0.245 |
| 2019 | 2327 | 5.481 | 0.166 |
| 2020 | 3098 | 5.119 | 0.049 |
| 2021 | 3854 | 5.207 | 0.71 |
| 2022 | 4712 | 4.666 | 0.29 |
| 2023 | 5100 | 4.448 | -0.216 |
| 2024 | 5262 | 4.446 | -0.231 |
| 2025 | 5452 | 4.422 | 0.326 |

## Test D: Aggregator comparison (2026 ROS)

| Aggregator | N | MAE | RMSE | Bias | 95% CI | vs Equal (diff, CI, sig) |
|------------|---|-----|------|------|--------|--------------------------|
| 1_equal_mean | 1122 | 4.609 | 6.277 | -1.105 | [4.355, 4.865] |  |
| 2_median | 1122 | 4.613 | 6.299 | -1.133 | [4.365, 4.868] | 0.0041, [-0.0214, 0.0303], False |
| 4_inverse_error | 1122 | 4.61 | 6.279 | -1.109 | [4.364, 4.864] | 0.0011, [-0.0007, 0.0028], False |
| 5_inverse_error_by_pos | 1122 | 4.611 | 6.28 | -1.106 | [4.358, 4.862] | 0.0022, [-0.0002, 0.0045], False |
| 6_bias_corrected | 1122 | 4.716 | 6.189 | 0.021 | [4.494, 4.956] | 0.1067, [0.0454, 0.1696], True |
| 7_shrinkage_0.9 | 1122 | 4.601 | 6.233 | -0.994 | [4.352, 4.851] | -0.0081, [-0.0366, 0.0213], False |

## Test E: RotoWire vs ESPN head-to-head (2026)

Paired n=1812: RotoWire MAE=4.495, ESPN MAE=4.499
MAE diff (RW-ESPN)=-0.004, CI=[-0.07, 0.058]
Average of both: MAE=4.462

## Test F: RotoWire stability across seasons

MAE range=[4.422, 5.52], CV=0.09, conclusion: stable

## Shrinkage (RotoWire, leave-one-season-out)

| Blend | N | MAE | RMSE |
|-------|---|-----|------|
| blend_0.8 | 31437 | 4.821 | 6.479 |
| blend_0.85 | 31437 | 4.792 | 6.47 |
| blend_0.9 | 31437 | 4.773 | 6.473 |
| blend_0.95 | 31437 | 4.765 | 6.486 |
| blend_1.0 | 31437 | 4.767 | 6.51 |
