## 2026-10-30 - Platform spellings as name-table rows (JEG-1387, part of JEG-1202)

Contract: store each player's grounded ESPN, Sleeper and Yahoo spelling as
`public.player_name_aliases` rows keyed by player_key, with provenance, in a
NOT APPLIED migration plus an offline JSON mirror. No resolver, alias, value or
Supabase change.

### Verified (check named)
- `python3 pipelines/build_platform_spellings.py --check`: 1,034 rows
  (Sleeper 929, ESPN 81, Yahoo 24), 0 held, no drift.
- `python3 -m unittest tests.test_platform_spellings`: 13 OK. Fails on main
  before this change (module and files absent).
- Read-only Supabase SELECTs, 2026-10-30 ~17:25 UTC: the table has no sleeper
  or yahoo rows; 9 of the 81 ESPN rows already exist at the same grain with the
  same player_key (left untouched by `do nothing`); 0 name another player.
  public.players has 4,702 rows, the snapshot count; every row's key is in the
  snapshot.
- No row points at 4653, 4655 or 4660 (the rows JEG-1351 deletes).

### Claimed, not confirmed
- The migration has not been run on any database, not even a branch. Its
  guards are checked by reading the SQL, not by executing it.
- Production ESPN rows `aaron jones` -> 164 and `kyle pitts` -> 1970 (ESPN
  projections backfill) look like the missing ground for the audit's
  `Aaron Jones Sr.` / `Kyle Pitts Sr.`; not used here, since the ground has to
  be committed evidence.
