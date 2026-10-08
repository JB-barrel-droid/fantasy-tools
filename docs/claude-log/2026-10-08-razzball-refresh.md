## 2026-10-08 - GAP-RAZZBALL-SUFFIX-POOL + GAP-RAZZBALL-STALE-BAKE: Razzball refreshes through the normal automated path (fix/razzball-refresh)

Contract: make Razzball refresh automatically (scrape -> Supabase -> chain
import -> legs -> section -> promote) so the section stops sitting on the
hand-built 2026-10-01 snapshot that lacked 27 players; make the browser's
Razzball (players.json rz_ppg) use the same Supabase snapshot instead of the
stale 2026-09-22 CSV (relayed finding from the week-history agent); add
verified nickname aliases; prove live-vs-section parity.

### Cause
- Section: `rebuild_comparison_chain.SOURCES` omitted razzball. The workflow's
  import loop wrote `data/raw/sources/razzball/<date>/snapshot.json` every run,
  but no stage built legs or a section from it, so the published section stayed
  on its last hand build (2026-10-01, pre-suffix-fix). Side effect: the hourly
  `source-vintage-check` saw Supabase 2026-10-06 != fixture 2026-10-01 forever
  and dispatched the chain every hour for nothing.
- Browser: `bake_players.py` read `data/inputs/razzball_projections.csv`
  (razzball_snapshot_date 2026-09-22) unconditionally; nothing refreshed that
  file after Muse's puller was retired. players.json meta.rz_snapshot
  2026-09-22 vs section vintage 2026-10-01, and the freshness label reads the
  section.
- Supabase side is healthy: newest `razzball_projections` vintage 2026-10-06
  (672 rows, written 2026-10-07 03:51 UTC); the 2026-10-07 13:09 UTC write-mode
  run re-saved the same page stamp. pg_cron `razzball-sync-live` (11:20 UTC
  daily) is active. 7 rows of that save went to review: Kenny Gainwell (alias
  added 2026-10-07 after the save), Joshua Palmer, Chigoziem Okonkwo, Mitch
  Trubisky (no alias), Audric Estime (two public.players rows), J. Sturdivant,
  Jalen Cropper.

### Fix
- `rebuild_comparison_chain.py`: razzball added to SOURCES with
  `run_razzball_source` (the cbsros pipeline, parameterised via
  `LEG_SECTION_SCRIPTS`; `_verify_cbsros_section` takes the source). Before the
  legs it requires players.json `rz_snapshot` == snapshot vintage
  (`razzball_bake_mismatch`); otherwise razzball is held. Any razzball failure
  goes through `isolate_hold` (section kept byte-for-byte, others publish).
- `import_supabase_references.py`: razzball snapshot rows carry the saver's
  `player_key`.
- `bake_players.py`: `--razzball-snapshot` (default: newest imported snapshot
  under data/raw/sources/razzball; the CSV only when none exists), priced by
  `player_key`. rebuild-chain.yml's bake step and bake-players.yml (which now
  imports razzball first) pass it explicitly.
- `build_ddf_two_tier_leg.ALIASES`: joshua palmer -> josh palmer, drew
  ogletree -> andrew ogletree, chigoziem okonkwo -> chig okonkwo, mitch
  trubisky -> mitchell trubisky (shared by the saver and the legs).
- Data: players.json re-baked (only rz_* fields change), 12 legs
  `ddf-20261006-razzball-*` committed, sources.razzball rebuilt at 2026-10-06.
- `tests/cbsros_live_section_harness.js` takes a source argument (default
  cbsros; existing callers unchanged).
- Tests changed, and why: `test_razzball_supabase` round-trip now pops the new
  `player_key` (and asserts it) before comparing the file row (the assertion
  pinned the exact field set, not a value); `test_nicknames_are_not_guessed`
  used "Joshua Palmer" as its never-resolves example, which is now a verified
  alias, so it uses an unaliased name and a new test pins the 5 aliases.
  `test_rebuild_chain_failclosed.WireFake`/`make_repo` gained razzball stage
  fakes and a baked players.json (harness only; no assertion changed).

### Verified (named checks)
- Supabase (read-only MCP): vintages 2026-10-01 (692) and 2026-10-06 (672);
  cron job 25 active; monitoring observations 2026-10-07 03:51 and 13:09 ok.
- Importer round trip: the real `import_supabase_references.build_razzball_snapshot`
  on the live table (anon REST read; player names injected from players.json +
  an MCP read because anon cannot read public.players) gives 672 rows whose
  three PPG columns equal the CI scrape artifact (run 37626322829) row for row;
  the artifact's 7 extra rows are exactly the 7 review rows.
- Aliases: public.players has exactly one row for each target (Josh Palmer 822
  WR, Andrew Ogletree 920 TE, Chig Okonkwo 4247 TE, Mitchell Trubisky 4214 QB)
  and none for the source spellings; each target is a fixture slug. Saver dry
  run on the CI snapshot with the new aliases: the 4 resolve; review left =
  Estime (ambiguous), Sturdivant, Cropper (+ Ben VanSumeren, an artefact of my
  skill-position-only players list; production saved him).
- Bake reproduction: a read-only shim serving public.players (QB/RB/WR/TE/K/DST,
  1,558 rows, md5 of key|pos|active|name and of key:team equal to the DB),
  teams and 2026 games from MCP reads, plus `export_cbsros_snapshot.py`
  (2026-10-02). origin/main's bake_players.py on it reproduces the committed
  players.json exactly (613 rows identical; meta differs only in
  dataset_status.built_at). The branch bake with the 2026-10-06 snapshot changes
  only rz_ppg/rz_ros/rz_filled_*/rz_complete/rz_covered/rz_comp_count/
  delta_rz_*; rz_snapshot 2026-09-22 -> 2026-10-06, n_rz_complete 511 -> 499;
  audit passed. Key-based vs name-based identity on the 672 rows: 0 disagree.
- Section: 12 legs from the snapshot, 496 values per combo (was 469), 176
  review rows, none naming a fixture player. New in full_12 include Kenneth
  Walker III 63.5, Luther Burden III, Harold Fannin Jr., Brian Thomas Jr. 7.9;
  dropped 11 (Estime + 10 players Razzball no longer lists). Biggest full_12
  moves are vintage: Puka Nacua +18.6, Christian Watson -12.1.
- `node tests/cbsros_live_section_harness.js browser-pool razzball`: max
  |live - section| 31.42 on origin/main (live 511 players from the CSV vs
  section 469) -> 0.050 on the branch (full_14 TE). Section pool is fully
  priced live in all 48 cells; live has 1 extra RB and 2 extra WR with no
  fixture slug (GAP-RAZZBALL-REFRESH-FOLLOWUPS).
- `tests/test_razzball_refresh.py` (13 tests, added to test-core): 12 fail on
  origin/main 196906f (the 13th is the pure guard function's own negative
  test). Mutations: dropping the bake-vintage gate fails 1; dropping the
  isolation fails 2.
- Chain tests: test_rebuild_chain_failclosed, _per_source_hold, _workflow,
  _bake, test_build_lag_gate, test_vorp_translation_checkpoint,
  test_translate_via_vorp, test_razzball_supabase, test_suffix_identity: OK.
  `test_bake_today_unboundlocal` (4 errors, bye-table) and
  `test_lineage_freshness` (3) fail identically on origin/main.
- 12-combo sweep (system Chrome, `make sync` builds of 196906f and the branch):
  fixedPieIndexed, sourceScaleAgreement, sourcePeaks identical within 1e-6 in
  every combo. fixedPie razzball / razzball_vorp checks move (ppr_12 target
  2634.8 -> 2628.9, shared 176 -> 175; ok both sides). getRows: only
  `rz_ppg` and the razzball / razzball_vorp values change (150-252 rows per
  combo); 514 -> 508 rows (Achane, Jayden Reed, Jaxson Dart and others lose a
  Razzball-only row: Razzball no longer lists them).
- `make sync`; `CHROMIUM_PATH=<system Chrome> make validate`: exit 0 (run
  without data/raw/sources/razzball, as in the Pages deploy). app/ and dist/
  regenerations reverted before commit (origin/main's own `make sync` produces
  the same file set).
- `check_input_lineage.py` (not in validate): razzball goes from
  missing_lineage_block to sha/built_at mismatch (writer stamps the full_8 leg,
  checker picks the newest leg); cbsros has the same mismatch on origin/main.

### Claimed, not confirmed
- The next rebuild-chain run reproduces this section (same importer, legs and
  builder on the same table rows; not run in CI). If the 11:20 UTC sync first
  adds the 4 alias rows to the 2026-10-06 vintage, the chain section gains them
  before players.json does (until the 11:45 bake).
- The freshness label equals the browser's Razzball vintage because the guard
  forces section vintage == players.json rz_snapshot; product-data.js still
  reads the section, unchanged, and was not opened in a browser.
- Achane / Reed / Dart are absent from Razzball's own pages (inferred from the
  scrape having no truncation code; the live page was not checked).
