## 2026-10-30 - JEG-1391: comparison chain drops slugs for merged-away players

Contract: unblock main's comparison chain. Since the JEG-1351 duplicate merge
deleted players 4653, 4655 and 4660, every chain run failed `make validate`
("comparison artifact references unknown player_key values: [4653, 4655,
4660]", run 41109005453). `sync_universe_keys` only ever added slugs to the
fixture's `player_keys`, so the three deleted keys stayed.

Fix: `sync_universe_keys.prune` drops each slug whose player_key is not in
players.json, with its `display` and `teams` entries, inside `sync_files`
(which the chain calls after the bake). A drop over 2% of the slugs, or with
an empty players.json, drops nothing, so the orphan check still fails loudly
on a bad bake. No value math changes.

### Verified (check named)
- `tests.test_universe_chart_only`: 11 OK. The three new tests error on main
  (no `prune`, no `removed` argument) and pass here.
- On the committed fixture and committed players.json minus 4653/4655/4660,
  `prune` drops exactly `jody fortson`, `mitch tinsley`, `nyheim millerhines`,
  and `build_reference_data.validate_comparison` then passes.
- `tests.test_rebuild_chain_*` (8 modules), `test_comparison_*`,
  `test_sync_*`: OK except `test_rebuild_chain_bake.test_catches_validate_removed_from_the_chain`,
  which fails the same way on main without this change (pre-existing).

### Claimed, not confirmed
- The next chain run on main after merge prunes the three slugs and publishes;
  check that run's "slugs dropped" line and its validate step.
