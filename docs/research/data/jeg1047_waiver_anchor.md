# JEG-1047 waiver-line sensitivity (2026-10-29)

Inputs: `data/fixtures/current` built 2026-10-28T23:27:25.844743+00:00, content week 8; prior-week lines from `data/history/week-7.json`. Engine: Python reference (`pipelines/value_reference.py`) at d4d995f. Candidate rules are hypothetical and applied to the three projection sources only.

Source state at this build: ESPN included, CBS ROS held: fidelity: publisher_vs_stored, Razzball held: fidelity: publisher_vs_stored.

## 1. One-player perturbation, waiver-line player, +/-1 PPG

Each case moves only the waiver-line player's projection by 1 PPG and measures every other player at that position in that source's Adjusted value. 'Moved' = changed by more than 0.05.

| Rule | Cases | Median others moved | 90th pct biggest move | Worst move | Worst move % | Worst DDF Projections move | Median rank changes | Worst DDF Value move |
|---|---|---|---|---|---|---|---|---|
| Current (one player) | 288 | 18.0 | 1.41 | 3.2 | 73.9% | 0.79 | 2.0 | 0.758 |
| Average band (7 players) | 288 | 18.0 | 0.54 | 0.82 | 37.5% | 0.3 | 2.0 | 0.591 |
| Median band (7 players) | 288 | 18.0 | 1.41 | 3.2 | 73.9% | 0.79 | 2.0 | 0.758 |
| Fitted curve (11 players) | 288 | 18.0 | 0.66 | 0.99 | 40.8% | 0.32 | 2.0 | 0.591 |
| Time smoothing (this week and last, one player each) | 288 | 13.0 | 0.69 | 1.4 | 39.7% | 0.33 | 1.0 | 0.591 |
| Average band + time smoothing | 288 | 10.0 | 0.29 | 0.73 | 32.2% | 0.28 | 0.0 | 0.59 |

### Pass rates against candidate tolerances (waiver-line player, +/-1 PPG)

A case passes when no other player at the position moves more than the tolerance in that source's Adjusted value. 'No special leverage' = no bigger than the same source and position's move when its top player changes by 1 PPG.

| Rule | <= 0.25 pts | <= 0.5 pts | <= 0.5 pts and <= 10% | <= 1.0 pts | No special leverage |
|---|---|---|---|---|---|
| Current (one player) | 33% | 59% | 50% | 81% | 54% |
| Average band (7 players) | 45% | 85% | 60% | 100% | 80% |
| Median band (7 players) | 33% | 59% | 50% | 81% | 54% |
| Fitted curve (11 players) | 37% | 78% | 57% | 100% | 71% |
| Time smoothing (this week and last, one player each) | 59% | 82% | 72% | 95% | 79% |
| Average band + time smoothing | 84% | 99% | 90% | 100% | 97% |

## 2. Current rule, by source and position (waiver-line player, +/-1 PPG)

| Source | Pos | Cases | Median others moved | Worst move | Worst move % | Worst DDF Projections move |
|---|---|---|---|---|---|---|
| ESPN | QB | 24 | 18.0 | 2.16 | 73.9% | 0.56 |
| ESPN | RB | 24 | 32.5 | 1.1 | 7.8% | 0.3 |
| ESPN | WR | 24 | 20.5 | 1.41 | 31.9% | 0.28 |
| ESPN | TE | 24 | 14.0 | 1.74 | 51.5% | 0.35 |
| CBS ROS | QB | 24 | 17.0 | 1.31 | 48.9% | 0.38 |
| CBS ROS | RB | 24 | 30.5 | 2.98 | 27.2% | 0.66 |
| CBS ROS | WR | 24 | 34.0 | 2.24 | 39.4% | 0.59 |
| CBS ROS | TE | 24 | 15.0 | 2.08 | 72.5% | 0.44 |
| Razzball | QB | 24 | 15.0 | 3.2 | 60.9% | 0.79 |
| Razzball | RB | 24 | 23.5 | 1.34 | 12.0% | 0.34 |
| Razzball | WR | 24 | 36.5 | 2.06 | 28.7% | 0.43 |
| Razzball | TE | 24 | 14.0 | 2.08 | 53.6% | 0.51 |

## 3. Control: the top player at the position, +/-1 PPG (current rule)

| Source | Pos | Median others moved | Worst move |
|---|---|---|---|
| ESPN | QB | 12.0 | 0.9 |
| ESPN | RB | 25.0 | 0.39 |
| ESPN | WR | 25.5 | 0.77 |
| ESPN | TE | 11.0 | 1.02 |
| CBS ROS | QB | 12.0 | 0.81 |
| CBS ROS | RB | 24.0 | 0.37 |
| CBS ROS | WR | 25.0 | 0.65 |
| CBS ROS | TE | 11.0 | 0.97 |
| Razzball | QB | 14.0 | 1.13 |
| Razzball | RB | 27.5 | 0.41 |
| Razzball | WR | 25.0 | 0.95 |
| Razzball | TE | 11.5 | 1.27 |

## 4. Worst single cases under the current rule

| Setting | Source | Pos | Player (native PPG) | Change | Line before -> after | Others moved | Worst move | Worst % |
|---|---|---|---|---|---|---|---|---|
| standard/8 | Razzball | QB | Bo Nix (14.7) | +0.5 | 14.7 -> 15.1 | 14 | 3.733 | 60.3% |
| half_ppr/8 | Razzball | QB | Bo Nix (14.7) | +0.5 | 14.7 -> 15.1 | 14 | 3.568 | 60.3% |
| ppr/8 | Razzball | QB | Bo Nix (14.7) | +0.5 | 14.7 -> 15.1 | 14 | 3.551 | 60.3% |
| standard/8 | Razzball | QB | Bo Nix (14.7) | +1.0 | 14.7 -> 15.1 | 14 | 3.199 | 60.9% |
| half_ppr/8 | Razzball | QB | Bo Nix (14.7) | +1.0 | 14.7 -> 15.1 | 14 | 3.058 | 60.9% |
| ppr/8 | Razzball | QB | Bo Nix (14.7) | +1.0 | 14.7 -> 15.1 | 13 | 3.046 | 60.9% |
| ppr/14 | CBS ROS | RB | Kaelon Black (4.11) | -1.0 | 4.11 -> 3.282 | 62 | 2.98 | 27.2% |
| half_ppr/12 | CBS ROS | RB | Kyle Juszczyk (3.54) | -1.0 | 3.54 -> 2.936 | 57 | 2.375 | 18.8% |
| ppr/8 | CBS ROS | WR | Malik Washington (9.218) | +0.5 | 9.218 -> 9.59 | 45 | 2.272 | 29.1% |
| ppr/8 | CBS ROS | WR | Malik Washington (9.218) | +1.0 | 9.218 -> 9.59 | 45 | 2.242 | 29.5% |
| standard/14 | ESPN | QB | Geno Smith (16.964) | -1.0 | 16.964 -> 16.42 | 23 | 2.163 | 73.9% |
| half_ppr/8 | CBS ROS | WR | Alec Pierce (9.344) | -1.0 | 9.344 -> 9.027 | 27 | 2.114 | 39.4% |

## 5. One-time repricing if a rule replaced the current one (today's data)

| Rule | Cells | Median players moved per cell | Worst move | Median line change (PPG) | Median rank changes |
|---|---|---|---|---|---|
| Average band (7 players) | 144 | 15.0 | 1.8 | -0.012 | 20.5 |
| Median band (7 players) | 144 | 0.0 | 0.0 | 0.0 | 0.0 |
| Fitted curve (11 players) | 144 | 14.0 | 1.23 | 0.003 | 12.0 |
| Time smoothing (this week and last, one player each) | 144 | 21.0 | 2.17 | 0.0 | 58.5 |
| Average band + time smoothing | 144 | 22.0 | 2.78 | -0.006 | 59.0 |

## 6. Week-to-week line movement on saved weeks

Mean absolute week-over-week change in the line (PPG), at the current settings' rostered counts.

| Rule | All cells | QB | RB | WR | TE |
|---|---|---|---|---|---|
| Current (one player) | 0.437 | 0.64 | 0.386 | 0.256 | 0.464 |
| Average band (7 players) | 0.401 | 0.597 | 0.347 | 0.234 | 0.425 |
| Median band (7 players) | 0.437 | 0.64 | 0.386 | 0.256 | 0.464 |
| Fitted curve (11 players) | 0.415 | 0.608 | 0.365 | 0.243 | 0.443 |
| Time smoothing (this week and last, one player each) | 0.28 | 0.415 | 0.273 | 0.162 | 0.27 |
| Average band + time smoothing | 0.264 | 0.409 | 0.249 | 0.149 | 0.247 |
