## 2026-10-19 - JEG-684 NumberFire ROS table + saver (draft, not applied)

Contract: per-source Supabase table and saver for NumberFire ROS, approved by Jeremy 2026-10-19; modeled on PR 667 (KeepTradeCut). The puller was already on main. No value math, no publish, nothing wired into DDF Value. Migration 012 is NOT applied; the lead applies it after Jeremy confirms the columns.

### What changed
- sql/migrations/012_numberfire_ros_projections.sql (CREATE TABLE + unique grain index + RLS only), pipelines/save_numberfire_ros_references.py (dry run default, --write upserts and verifies the count), tests/test_save_numberfire_ros.py.
- Per-stat ROS projections stored raw for rescoring; source fantasy total kept as fantasy_points for audit only (scoring unstated). Zero stats are NULL.

### Verified (check named)
- `pytest tests/test_save_numberfire_ros.py`: all pass (hermetic, no network, no DB).
- Negative test: with the zero-to-null rule and the fingerprint check removed from the saver, 2-3 of the tests fail (test_zero_and_missing_stay_null_never_zero, test_bad_snapshot_fails_closed); restored afterward.
- Puller tests still pass alongside (test_pull_*).

### Claimed, not confirmed
- Table name and columns match what Jeremy wants (he has not confirmed). Migration not applied, so no live write, no live Supabase column check.
- Migration number 011/012/013 is ordered against PR 667's 010 (also unmerged); renumber if merge order changes.
