## 2026-10-08 - GAP-CBSROS-LIVE-POOL: suffix names dropped by the CBS ROS and Razzball legs (fix/suffix-names)

Contract: find where suffixed names (Jr., III, II, Sr.) fail identity, fix the
root cause in normalization without creating collisions, rebuild what can be
rebuilt, and prove live-vs-section parity for CBS ROS.

### Cause
- `build_cbsros_ddf_leg.py` and `build_razzball_ddf_leg.py` joined each
  snapshot row to the fixture's `player_keys` by exact slug (plus ALIASES).
  Both sources' `player_norm` strip suffixes ('kenneth walker'). The fixture
  slugs are inconsistent: 27 keep the suffix ('kenneth walker iii'), others
  drop it ('travis etienne'). Every suffixed player whose slug kept the
  suffix went to review as `unresolved_identity`.
- `bake_players.py`, which feeds the browser's live repricing, resolves
  through `canonical_players.norm_player_name` (suffix-stripping) against
  public.players, so the browser priced those players and the leg did not.
  Different pools move every waiver and starter line.
- Second defect on the same path: the CBS ROS and Razzball section builders
  key values by the leg's `player_norm`, which was the source spelling, not
  the fixture slug. An alias-resolved row would have been published under a
  name nothing joins on.

### Per-source check (read-only Supabase, 2026-10-08)
For the 27 suffixed fixture keys, the latest saved rows per source table vs
the fixture section (full_12):
- cbs 5/5, fantasycalc 11/11, fantasypros 9/9, usatoday 13/13, espn 26/26:
  every saved key is in the section (these paths carry player_key, or the ESPN
  CSV keeps the suffix). No gap.
- cbsros 16 saved, 0 in section. razzball 25 saved, 0 in section. The gap.
- Save-side resolvers (`save_*_references.resolve_name`) strip suffixes and
  resolved all of these. `save_razzball_references` has no nickname
  expansion: Kenny Gainwell, Joshua Palmer, Drew Ogletree never reached
  `razzball_projections` (separate, logged in GAP-RAZZBALL-SUFFIX-POOL).
- The browser has no name normalization of its own (joins by player_key and
  slug), so parity lives in the Python resolvers.

### Fix
- `build_ddf_two_tier_leg.FixtureIdentity`, shared by the ESPN, CBS ROS and
  Razzball legs: verified ALIASES, then exact slug, then the slug's
  `norm_player_name` form (the repo's single normalization rule, also used by
  the bake), narrowed by position from players.json. More than one key left
  -> `ambiguous_identity`, excluded. A source spelling that carries the suffix
  and hits a slug exactly still resolves (it names its player). Two source rows
  on one key -> both `duplicate_identity`, excluded.
- CBS ROS and Razzball legs emit the fixture slug as `player_norm` and keep the
  source spelling as `source_norm`.
- `tests/test_static_export.py`: the pinned cbsros full_12 Josh Allen value
  20.8 -> 20.3. The pin was wrong: it was computed on the pool missing 16
  players. 20.3 is what the live path already showed (harness: 20.29).

### Verified (named checks)
- Collisions: 0 normalized-form collisions among the fixture's 610
  `player_keys` slugs (any position; `FixtureIdentity.ambiguous_forms()` is
  empty). public.players (4,646 rows) under the same rule: 0 collisions within
  a position among the 1,461 QB/RB/WR/TE rows. Cross-position collisions exist
  (Michael Carter RB / Michael Carter II DB, DJ Turner WR / DJ Turner II DB,
  Justin Jefferson WR / LB, Lamar Jackson QB / DB, ...); the position filter
  separates them and an unknown position fails closed (test below).
- Regression check on real inputs: re-resolving every row of the CBS ROS
  2026-09-30 and 2026-10-02 snapshots, the ESPN CSV and the Razzball CSV:
  no previously resolved row changes key; CBS ROS gains exactly the 16, whose
  keys equal the player_key public.cbs_ros_projections stores; ESPN and the
  Razzball CSV gain none.
- CBS ROS rebuild: the 2026-10-02 snapshot was reconstructed read-only from
  `cbs_ros_projections` (md5 of key|pos|norm and four weighted sums match the
  table). origin/main's leg + section builders on it reproduce the committed
  section exactly (values and natives). The branch's builders: 333 -> 349
  players per combo; 113-202 values move per combo; largest standard_12 Jaxon
  Smith-Njigba 40.2 -> 50.9; new: Kenneth Walker III 35-42 across combos,
  Harold Fannin Jr. 10-16, Luther Burden III 4-12.
- `node tests/cbsros_live_section_harness.js browser-pool`: max |live -
  section| 10.72 on origin/main -> 0.21 on the branch; live pool == section
  pool in all 48 combo x position cells. The 0.21 (standard_8 QB) is
  players.json's 2-decimal `cbsros_ppg`: fed the leg's 3-decimal natives the
  max is 0.05.
- `tests/test_suffix_identity.py` (added to test-core): 8 tests pass on the
  branch; on origin/main 9b97f88 all 8 fail (73 failing subtests). Mutation:
  emitting the source spelling as `player_norm` again fails 7 subtests.
- 12-combo sweep (system Chrome, `make sync` builds of origin/main 9b97f88
  and the branch): fixedPieIndexed, sourceScaleAgreement, sourcePeaks,
  fixedPie, scaleAgreement, all source maps and all 514 getRows() rows
  identical within 1e-6 in every combo (only float noise below 1e-12). The
  curve engine reprices CBS ROS live from players.json, so it was already on
  the full pool; the change shows in readers of the fixture section (main
  comparison table's CBS ROS column). dist/consolidated-values.json carries no
  cbsros rows and is unchanged.
- `CHROMIUM_PATH=... make validate`: exit 0. Regenerated dist/app churn and the
  locally built 2026-10-02 legs were removed before commit.
- Also run: test_ddf_two_tier_leg, test_cbsros_8t_qb, test_cbsros_section,
  test_verify_cbsros_legs, test_games_remaining, test_espn_pool_cap,
  test_save_espn_cbs_references, test_input_lineage, test_lineage_writers and
  others: OK. `test_razzball_production_followups.test_razzball_date_uses_vintage`
  fails identically on origin/main (node harness crash), not this change.

### Not done
- Razzball section not rebuilt: the raw 2026-10-01 snapshot is not in the repo,
  the table lacks 3 of the 27 rows, and the chain does not rebuild Razzball
  (GAP-024). Logged as GAP-RAZZBALL-SUFFIX-POOL.

### Claimed, not confirmed
- The next rebuild-chain run (Supabase import, 12 legs, section) produces the
  same CBS ROS section as this local rebuild. Expected because origin/main's
  code reproduced the committed section from the same reconstructed rows, but
  the chain was not run.
- The main comparison table's CBS ROS column was not opened in a browser; that
  it reads `sources.cbsros.combos[combo].values` is from reading
  comparison-dashboard.js. v2 (app/v2/targets.js) was not checked.
