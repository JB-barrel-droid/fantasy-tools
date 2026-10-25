## 2026-10-23 - JEG-969 step 2: bench value decomposition

Ticket: JEG-969 lane A. Branch: research/JEG-969-bench-share.

### Verified (check named)

- Promotion/demotion rates measured from nflverse 2015-2025 weekly actuals
  (weekly_actuals_nflverse_2015_2025.csv.gz), all 11 seasons, PPR scoring,
  12-team.
- Week 7 promotion rate: QB 12.7%, RB 13.0%, WR 17.4%, TE 28.8%.
  Demotion rate: QB 25.8%, RB 17.8%, WR 22.0%, TE 28.8%.
- Rates decay roughly linearly with weeks remaining (weeks 1-4 ~22%
  promotion, weeks 13-17 ~6-7%).
- First backup promotion rate ~34-40% (all weeks pooled) across positions.
- Bench share decomposition at ppr/12: fill-in floor 8.1%, recommended 9.0%
  (ES model with sigma), displacement absorbs 82% of gross start-worthy gain.
- Reconciliation table of all bench share figures (6.4%, 9-12%, 10.0%,
  11.7%, 23.5%, 6.35%, 15%) with their definitions and sources.

### Claimed (not confirmed)

- The promotion rates from season-to-date PPG rankings may differ from what
  the engine would produce using projected PPG (the engine's tier basis).
  Historical actuals are a proxy for projections.
- TE promotion rates appear unusually stable across season phases; this may
  reflect the small sample (66 bench TEs per season at 12-team with 6 bench
  seats).

### Script

`tools/bench_research/promotion_demotion_rates.py` (new, committed).
