## 2026-10-29 - JEG-1310 CBS ROS divergence: cause and options (research)

Contract: measure how far CBS rest of season sits from ESPN and Razzball ROS by
position and week, find why, and show what three handling options would do to
DDF Value (projections). Docs only; no math change.

### Verified (check named)
- Gap by position and week 4-8 from data/history/week-N.json
  (`docs/research/JEG-1310/cbs_options.py`).
- CBS printed points vs its own stat line, per player, week 8, and by
  position for five snapshots (SQL on public.cbs_ros_projections.raw_stats,
  read only).
- Option effects on DDF Value (projections) at 12 teams full PPR, half PPR
  and superflex PPR: `cbs_options.py` running `pipelines/value_reference.py`
  Setting on the committed week-8 fixture.
- Divergence check with CBS rescored: unchanged `check_source_divergence.run`
  on a temp fixture with CBS legs rebuilt by `build_cbsros_ddf_leg.build_leg`
  (half 45.3% -> 41.0%, full 48.9% -> 45.3%).

### Claimed, not confirmed
- CBS uses 6-point passing TDs and rounds yardage down per game: a fit to
  CBS's numbers, not read from CBS's rules page.
- Live page values match the Python reference at these settings (not
  checked live).
