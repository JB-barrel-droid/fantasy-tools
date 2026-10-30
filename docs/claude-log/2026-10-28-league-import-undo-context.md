## 2026-10-28 - Restore value context on league import Undo

Contract: independent delta review of release #1062 at `4e2458ad` found that
Undo restored league rosters and settings but left the shared basis/override active.

### Verified (check named)

- `test_shared_league_cancel_and_undo_restore_previous_value_context`: PASS, 43.399s,
  no skips. The browser checks both previous custom CBS/player-override and default
  contexts, cancel, accepted import, Undo, unchanged local saved preferences, and
  persistence of restored context after navigation.
- The original finder/league link round trip rerun: PASS, 1 test, no skips.
- `node --check` on touched JS and `git diff --check`: PASS.

### Claimed, not confirmed

- One parent-owned independent delta review and new-head required CI remain.
- No engine, position-share, Supabase or production change.
