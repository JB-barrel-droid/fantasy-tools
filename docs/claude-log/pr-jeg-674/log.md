## 2026-10-19 - JEG-674 Dynasty Daddy table + saver (draft, not applied)

Contract: per-source Supabase table and saver for Dynasty Daddy, approved by Jeremy 2026-10-19; modeled on PR 667 (KeepTradeCut). The puller was already on main. No value math, no publish, nothing wired into DDF Value. Migration 013 is NOT applied; the lead applies it after Jeremy confirms the columns.

### What changed
- sql/migrations/013_dynasty_daddy_trade_values.sql (CREATE TABLE + unique grain index + RLS only), pipelines/save_dynasty_daddy_references.py (dry run default, --write upserts and verifies the count), tests/test_save_dynasty_daddy.py.
- Comparison and id bridge only; FantasyPros-derived ranks not stored; ids kept as JSONB.

### Verified (check named)
- `pytest tests/test_save_dynasty_daddy.py`: all pass (hermetic, no network, no DB).
- Negative test: with the zero-to-null rule and the fingerprint check removed from the saver, 2-3 of the tests fail (test_zero_and_missing_stay_null_never_zero, test_bad_snapshot_fails_closed); restored afterward.
- Puller tests still pass alongside (test_pull_*).

### Claimed, not confirmed
- Table name and columns match what Jeremy wants (he has not confirmed). Migration not applied, so no live write, no live Supabase column check.
- Migration number 011/012/013 is ordered against PR 667's 010 (also unmerged); renumber if merge order changes.
