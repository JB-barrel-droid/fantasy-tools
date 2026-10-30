## 2026-10-29 - JEG-1313: platform-spelling audit in CI, active players saved

Contract: close two follow-ups from #1114 (JEG-1202): save which players are
active so the offline ambiguity results match the live registry, and run the
audit test in CI.

### Verified (check named)
- `data/inputs/players_active_snapshot.json` holds the 2,126 active keys of
  4,702 public.players rows (read-only SELECT, 2026-10-29T20:19:29Z). The SQL
  md5 of the key list (5bb0c234…) equals the local md5 of the file's list, and
  the SQL md5 of `player_key|full_name|position` (e67427e3…) equals the same
  digest of `players_identity_snapshot.json`, so the flags pair with exactly
  those rows.
- `python3 docs/research/JEG-1202/build_matrix.py --check`: no drift after the
  rebuild. Cases: 695, 683 pass, 12 known gaps (unchanged). No-position
  ambiguous cases 18 -> 10; the 8 that changed now expect their one active row.
- `python3 -m unittest tests.test_jeg1202_platform_spellings`: 10 tests OK. The
  3 new tests error on the pre-change build (no `ACTIVE`, no active flags).
- `python3 -m unittest tests.test_run_suite tests.test_validate_runner
  tests.test_player_aliases tests.test_sleeper_projection_idmap`: OK.

### Claimed, not confirmed
- The test runs in preview CI through `test-unit-modules`; confirmed only once
  the PR's preview run reports.
