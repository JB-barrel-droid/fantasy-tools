## 2026-10-30 - JEG-1354 players.active production write

Contract: Jeremy picked A in the main chat at 19:09 UTC: "turn the write on
and run it with today's Sleeper list". Back up first, write, read back, report
on JEG-1354.

### Verified (check named)
- Dry run (`sync_players_active.plan`, Sleeper base pulled 2026-10-30 17:22
  UTC on main): 445 set true (33 by gsis id, 412 by position-checked name),
  57 set false (all tied by id), 0 skipped. Players rows matched live by md5
  per 100-key bucket over all 1,514 skill rows.
- Name-match check (read-only): 412 clean, 0 doubtful. 20 apparent gsis
  conflicts are a leading space in Sleeper's gsis id (equal once trimmed);
  2 Sleeper namesakes (Frank Gore Jr., Jacoby Jones) resolve to the current
  player; every match falls within about one draft class (row gsis id against
  Sleeper id).
- Before the write: skill-row md5 26e0e9b64be690ebdd341ede668bd1f6, same as
  the dry run. Previous values of the 502 rows saved to
  `ddf/backups/2026-10-30-jeg1354-players-active-before.csv` in the project
  files.
- Write: one guarded SQL update (skill positions only, true only where false,
  false only where true) returned 445 true and 57 false. A separate read-back
  shows 1,048 active skill rows (660 + 445 - 57), and the named spot checks on
  both sides read as expected.
- Check: skill players on a team in today's `player_status_history` that are
  still inactive: 3 (Jordan Moore, Amar Johnson, Ty Pezza). All three are
  outside the active universe, which the rule leaves alone.

### Claimed, not confirmed
- Future runs stay dry until the repository variable `PLAYERS_ACTIVE_SYNC` is
  set to `write`; this session can't set repository variables.
- PlayerIndex does not trim gsis ids; trimming would turn about 20 name
  matches into id matches. Not changed here.
