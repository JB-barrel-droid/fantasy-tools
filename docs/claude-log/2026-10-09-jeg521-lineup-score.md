# Value sets against realized lineup points, 2026 (12 teams, ppr)

Produced by `pipelines/score_lineup_values.py`. A report, not a deploy gate. Weeks with actuals: [1, 2, 3, 4]. Game-day availability is read from the actuals (a stat line = played): known at kickoff to a manager, known after the fact here.

## Valued on Week 2 inputs, scored on weeks [2, 3, 4]

| Value set | QB rho | RB rho | WR rho | TE rho | All rho | Usable points | Rostered points |
| --- | --- | --- | --- | --- | --- | --- | --- |
| expected_starts_A | 0.008 | 0.799 | 0.774 | 0.352 | 0.632 | 3946 | 5482 |
| vp_slices_OC2A | 0.174 | 0.788 | 0.756 | 0.537 | 0.636 | 3951 | 5506 |
| plain_value_above_waivers | 0.112 | 0.803 | 0.716 | 0.468 | 0.621 | 3929 | 5480 |
| mean_projection | 0.483 | 0.783 | 0.735 | 0.598 | 0.584 | 3958 | 5553 |

Missed games among the players each set ranks as starters (realized vs assumed m):

| Value set | QB | RB | WR | TE |
| --- | --- | --- | --- | --- |
| expected_starts_A | 16.7% vs 9.9% | 6.5% vs 10.0% | 12.5% vs 13.0% | 8.3% vs 15.9% |
| vp_slices_OC2A | 16.7% vs 9.9% | 6.2% vs 10.0% | 12.5% vs 13.0% | 8.3% vs 15.9% |
| plain_value_above_waivers | 16.7% vs 9.9% | 6.5% vs 10.0% | 12.5% vs 13.0% | 8.3% vs 15.9% |
| mean_projection | 16.7% vs 9.9% | 6.2% vs 10.0% | 13.3% vs 13.0% | 8.3% vs 15.9% |

Start-worthy calibration (expected-starts P(level above the starter line) at valuation vs realized share of later team games with a finish inside the starter count):

| Predicted bin | Players | Team games | Realized |
| --- | --- | --- | --- |
| 0.0 to 0.2 | 26 | 78 | 26.9% |
| 0.2 to 0.4 | 21 | 63 | 33.3% |
| 0.4 to 0.6 | 41 | 123 | 30.1% |
| 0.6 to 0.8 | 45 | 135 | 52.6% |
| 0.8 to 1.0 | 33 | 99 | 70.7% |

## Valued on Week 3 inputs, scored on weeks [3, 4]

| Value set | QB rho | RB rho | WR rho | TE rho | All rho | Usable points | Rostered points |
| --- | --- | --- | --- | --- | --- | --- | --- |
| expected_starts_A | 0.468 | 0.720 | 0.692 | 0.640 | 0.631 | 2693 | 3662 |
| vp_slices_OC2A | 0.391 | 0.728 | 0.745 | 0.501 | 0.630 | 2615 | 3640 |
| plain_value_above_waivers | 0.520 | 0.787 | 0.703 | 0.438 | 0.612 | 2690 | 3637 |
| mean_projection | 0.430 | 0.780 | 0.789 | 0.706 | 0.606 | 2726 | 3760 |

Missed games among the players each set ranks as starters (realized vs assumed m):

| Value set | QB | RB | WR | TE |
| --- | --- | --- | --- | --- |
| expected_starts_A | 8.3% vs 9.9% | 10.0% vs 10.0% | 10.7% vs 13.0% | 0.0% vs 15.9% |
| vp_slices_OC2A | 8.3% vs 9.9% | 6.9% vs 10.0% | 10.7% vs 13.0% | 0.0% vs 15.9% |
| plain_value_above_waivers | 8.3% vs 9.9% | 10.0% vs 10.0% | 10.7% vs 13.0% | 0.0% vs 15.9% |
| mean_projection | 0.0% vs 9.9% | 6.7% vs 10.0% | 10.7% vs 13.0% | 0.0% vs 15.9% |

Start-worthy calibration (expected-starts P(level above the starter line) at valuation vs realized share of later team games with a finish inside the starter count):

| Predicted bin | Players | Team games | Realized |
| --- | --- | --- | --- |
| 0.0 to 0.2 | 36 | 72 | 26.4% |
| 0.2 to 0.4 | 23 | 46 | 26.1% |
| 0.4 to 0.6 | 51 | 102 | 36.3% |
| 0.6 to 0.8 | 41 | 82 | 56.1% |
| 0.8 to 1.0 | 33 | 66 | 66.7% |

## Valued on Week 4 inputs, scored on weeks [4]

| Value set | QB rho | RB rho | WR rho | TE rho | All rho | Usable points | Rostered points |
| --- | --- | --- | --- | --- | --- | --- | --- |
| expected_starts_A | 0.416 | 0.758 | 0.512 | 0.567 | 0.566 | 1364 | 1892 |
| vp_slices_OC2A | 0.573 | 0.767 | 0.556 | 0.632 | 0.606 | 1344 | 1873 |
| plain_value_above_waivers | -0.007 | 0.688 | 0.586 | 0.571 | 0.532 | 1338 | 1858 |
| mean_projection | 0.661 | 0.669 | 0.489 | 0.453 | 0.448 | 1412 | 1908 |

Missed games among the players each set ranks as starters (realized vs assumed m):

| Value set | QB | RB | WR | TE |
| --- | --- | --- | --- | --- |
| expected_starts_A | 16.7% vs 9.9% | 10.3% vs 10.0% | 14.3% vs 13.0% | 0.0% vs 15.9% |
| vp_slices_OC2A | 16.7% vs 9.9% | 10.0% vs 10.0% | 14.3% vs 13.0% | 0.0% vs 15.9% |
| plain_value_above_waivers | 16.7% vs 9.9% | 10.0% vs 10.0% | 14.3% vs 13.0% | 0.0% vs 15.9% |
| mean_projection | 16.7% vs 9.9% | 10.0% vs 10.0% | 14.3% vs 13.0% | 0.0% vs 15.9% |

Start-worthy calibration (expected-starts P(level above the starter line) at valuation vs realized share of later team games with a finish inside the starter count):

| Predicted bin | Players | Team games | Realized |
| --- | --- | --- | --- |
| 0.0 to 0.2 | 38 | 38 | 18.4% |
| 0.2 to 0.4 | 36 | 36 | 27.8% |
| 0.4 to 0.6 | 45 | 45 | 42.2% |
| 0.6 to 0.8 | 38 | 38 | 57.9% |
| 0.8 to 1.0 | 40 | 40 | 60.0% |
