## 2026-10-08 - GAP-CBSROS-BAKE-IDENTITY: CBS ROS refresh blocked by a live-vs-section mismatch (fix/cbsros-parity)

Contract: find why post-rebuild `make validate` failed on the 2026-10-08 CBS
ROS data (rebuild-chain run 37752789485, bake_players=true), fix the wrong
side with server/browser parity, and add a test that fails on the broken
state. Do not loosen the 0.25 tolerance.

### Cause
- Identity, not calibration math. On the 2026-10-08 snapshot the leg prices
  two players that players.json leaves out:
  - Chig Okonkwo (4247, TE), saved as `chigoziem okonkwo`.
  - Mitchell Trubisky (4214, QB), saved as `mitch trubisky`.
- The 2026-10-08 save is the first vintage to hold either of them (Supabase
  read: both rows exist only at 2026-10-08). The saver resolved them through
  the verified ALIASES added on fix/razzball-refresh, and the legs resolve the
  same spellings through the same ALIASES.
- `export_cbsros_snapshot.py`, which the CI bake reads, dropped the saved
  player_key. `bake_players._intake_cbsros` then re-resolved the saved
  player_norm by name through the canonical registry. The registry's aliases
  come from `player_identity_map.json` and do not include either spelling. The
  CI log shows `cbsros intake: 365 priced players (367 rows ...), 2 unresolved`.
- Okonkwo projects 6.969 PPR ppg, which puts him inside the 14-team TE bench.
  Without him, the browser's TE waiver line drops one player: the leg has
  rw 6.462 (Parkinson), the browser 6.108 (Engram).
  - The leg's TE share steps down to 0.148 (economics break at 0.15). The
    browser calibrates at 0.15.
  - Every live full_14 TE value moves, by up to 3.72.
- Trubisky (0.73 ppg, waiver) has no effect on any value.
- The leg is right: each alias names the only public.players row of that name
  at that position. The bake is wrong.

### Fix
- `export_cbsros_snapshot.py` and `import_supabase_references.build_cbsros_snapshot`
  carry the saver's player_key on every row.
- `bake_players._intake_cbsros` prices by the row's player_key. A row without
  one (a file-built snapshot) still resolves by name and fails closed. This is
  the same pattern as the Razzball intake.
- New `tests/test_cbsros_bake_identity.py`, added to `make test-core`.

### Verified (check named)
- Reproduction setup: the read-only stand-in sbclient (scratchpad
  `fake_sb`; public.players from MCP dumps, everything else via anon GETs,
  writes raise) and the real exporter, importer, bake, 12 leg builds and
  section build on the 2026-10-08 rows. No Supabase writes.
- `node tests/cbsros_live_section_harness.js section-pool`:
  - Before the fix: max 3.723 at full_14 TE, the same number as the CI run.
  - After the fix: max 0.050 (standard_10 RB) across all 48 combo x position
    cells.
  - browser-pool gives the same result, and live pool == section pool in
    every cell.
  - The 0.05 is the section's 0.1/0.01 rounding. The tolerance is unchanged.
- `python3 -m unittest tests.test_cbsros_8t_qb` on the 2026-10-08 data: OK.
- Pool diff before the fix: leg-only keys were exactly {4247, 4214}. There
  were no browser-only keys and no ppg mismatches above 0.0006.
- Importer change: legs + section rebuilt from the new importer snapshot
  (player_key added) are identical to the old one's.
- 2026-10-02 data: the fixed bake on the 2026-10-02 export reproduces
  origin/main's players.json cbsros_* fields exactly (0 differences). This
  bug needs the 10-08 rows, so it does not touch committed data.
- New test, negative-tested:
  - Removing `player_key` from the exporter rows fails 3 subtests.
  - Reverting `_intake_cbsros` to name-only resolution fails the same 3
    (real 10-08 rows, plus the chigoziem okonkwo and mitch trubisky alias
    cases).
  - Green on the branch.
- 12-combo sweep (system Chrome, `make sync` builds of origin/main 59950d4
  and the branch on committed data):
  - Checked fixedPieIndexed, sourceScaleAgreement, sourcePeaks, fixedPie and
    all 508 getRows() rows with every source value.
  - Result: identical in all 12 combos. Nothing moves.
- `CHROMIUM_PATH=... make validate`: exit 0, including the new module. Build
  churn was reverted with `git checkout -- app dist`.

### Claimed, not confirmed
- The next rebuild-chain run with bake_players=true passes post-rebuild
  validate. Expected from the local reproduction, which matched the CI number
  (3.723) exactly, but the chain was not run.
- In the local stand-in, Razzball imported 681 rows against CI's 682 (a gap in
  the stand-in's players list). This does not affect CBS ROS.
- Two alias maps remain: `player_identity_map.json` alias_to_canonical (the
  canonical registry) and `build_ddf_two_tier_leg.ALIASES` (savers and legs).
  The ESPN CSV and prediction-market bake inputs are still resolved by name,
  so they can diverge the same way if an alias lands in one map only. Logged
  in the risk row; nothing diverges today (ESPN and pm intake: 0 unresolved).
