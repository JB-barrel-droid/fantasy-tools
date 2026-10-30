## 2026-10-29 - JEG-1351 path A: merge three duplicate Sleeper player rows

Contract: fix the four JEG-1202 Sleeper known gaps by merging the three
gsis-less duplicate public.players rows (4653, 4655, 4660) into the original
rows (2785, 437, 4363), with verified aliases for the four Sleeper spellings
and a sync guard so the refresh can't add such a row again. Jeremy asked for
both paths built (until 8 PM CT, 2026-10-29); this is path A. Nothing was
applied to production.

### Verified (check named)
- Each pair is one person: read-only SQL on iskiybsimubiujwuchsl
  (2026-10-29 23:30 UTC) shows the original's metadata.gsis_id equals the
  gsis that data/inputs/sleeper_projection_idmap.csv (status matched) gives
  the duplicate's Sleeper id. Pinned by
  `tests.test_jeg1351_sleeper_duplicates` (4 tests, fail without the
  migration file).
- References on the duplicates, all 34 foreign keys to public.players: 4653
  none, 4655 none, 4660 player_status_history 19 (read-only SQL).
- The four resolver cases move from known_gap to pass:
  `docs/research/JEG-1202/build_matrix.py` rebuild, `--check` no drift,
  `tests.test_jeg1202_platform_spellings` OK.
- Sync guard: `tests.test_nfl_universe` new
  `test_sleeper_id_the_idmap_ties_to_an_existing_row_is_not_inserted_again`
  errors on main and passes here; `test_committed_idmap_ties_the_three_jeg1351_sleeper_ids` passes.
- `tests.test_player_alias_table` OK (seed rows equal the JSON).

### Claimed, not confirmed
- `tests.test_player_aliases` collision guard fails on three aliases until
  the merge migration runs and the players.json bake refreshes, because the
  committed bake still holds rows 4653/4655/4660 under the Sleeper text. The
  order is: apply both migrations (Jeremy's yes), rebake, then merge.
- The migration's SQL has not been run anywhere (no branch database).
- Not touched: 4661 Ben VanSumeren (same pattern, duplicate carries values).
