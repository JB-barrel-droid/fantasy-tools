## 2026-10-30 - JEG-1362 pin the players.active dry run

Contract: correction child of JEG-1354 from the independent review of #1187
(head c3808a7). Add a test that pins the dry run and the 75% guard in
`main()`, and reword the misleading "no name fallback" comment. No production
write, no value math.

### Verified (check named)
- `python3 -m unittest tests.test_sync_players_active`: 15 pass (12 old, 3 new
  in `MainDryRunTests`), with a fake `sbclient` module and a temp base file.
- Mutation `if args.write:` -> `if True:` fails
  `test_default_run_is_a_dry_run` (it passed all 12 old tests before).
- Removing the guard's `return 1` fails
  `test_refused_plan_writes_nothing_even_with_write_flag` for both `[]` and
  `["--write"]`.
- `origin/main` merged in normally (conflicts only in the `Makefile` test list
  and the risk register's "Last updated" line, both kept from each side);
  `tests.test_run_suite` and `tests.test_validate_shards` pass after the merge.

### Claimed, not confirmed
- The comment change is wording only; `resolve_sleeper`'s name fallback and
  the `how not in ID_HOWS` guard are unchanged and still pinned by
  `test_retired_player_reached_by_name_only_keeps_its_flag`.
- Exact live dry-run counts for JEG-1354 are still not posted.
