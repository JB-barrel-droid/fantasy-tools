# JEG-534 (part of): first measurement of matchup swaps (2026-10-15)

Added tools/weekly_matchup_swaps.py (stdlib) over the stored Sleeper weekly projections (JEG-540), tests/test_weekly_matchup_swaps.py, and the result plus a recommendation (option a, lineup signal only) under MR-23 in docs/math-review-agenda.md.

Verified: tests.test_weekly_matchup_swaps passes; the tool ran on 2018-2025 data (pair swap rate QB 20%, RB 28%, WR 24%, TE 15%; starter weekly projection spread 7-19%).
Claimed, not confirmed: the starter counts (QB 12, RB 30, WR 30, TE 14) are a 12-team approximation, not read from the lineup parameters; season rank is ex post. No engine or value change, so no sweep.
Left: G6 calibration re-point to projected starts; options (b) and (c) not built.
