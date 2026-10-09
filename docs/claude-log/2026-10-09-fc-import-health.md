## 2026-10-09 - FantasyCalc import-health hold, 594 vs 591 (JEG-512)

Contract: find why import health held FantasyCalc (table 594 rows, manifest
591), fix it at the cause, and apply Jeremy's count-drift rule ("hold only on
big drops": small changes alert-only, a drop of more than about 10% at any
position holds) to import health.

### Verified (check named)
- The hold: rebuild-chain run 37990714617 log, "Run import health check":
  `FAILED fantasycalc [BLOCKING] ... TABLE_DRIFT: table has 594 rows at
  latest vintage Week 5, manifest expects 591`; the import step stamped
  "591 fantasycalc rows (vintage Week 5, 3 review)"; promote refused and
  FantasyCalc was held on its earlier Week 5 section.
- Not a re-save and not a duplicate: Supabase read-only query on
  source_trade_values (fantasycalc, as_published, qb_slots=1) grouped by
  bake: the latest bake fcwk5_2026-10-09t1705_v1 has 594 rows = 198
  player_keys x 3 scorings; both the importer and the health check already
  scope to the latest bake. The one new key against the 10:05 bake is 3081
  Tyreek Hill (players row exists, WR, MIA).
- Cause: his 3 rows have `value` NULL and `native_value` 350/354/357
  (same query). #451 (JEG-480) made `save_usatoday_references.apply_reindex`
  store a row with no ESPN anchor pair as value NULL; the FantasyCalc saver
  calls the same function. The importer prices NULL-value rows by
  native_value only for usatoday (`NATIVE_PRICED_SOURCES`), so the 3 rows went
  to review, and import health's fantasycalc config said review rows never
  sit in the table (`table_holds_review_rows: False`), so it expected 591.
- Fix: fantasycalc added to `NATIVE_PRICED_SOURCES`; fantasycalc
  `table_holds_review_rows` = True (its importer reads from the table, so
  its import-time review rows are table rows); same-vintage count change is
  a promotable `COUNT_DRIFT (non-blocking)` warning unless the total or any
  position drops more than 10%, which stays a blocking TABLE_DRIFT. The
  position-capable tables now select `position` (Razzball `pos`).
- Fail-first: before the fix, 7 new tests failed (`python3 -m pytest` on the
  unfixed code: tests/test_import_health.py JEG-512
  block and test_fantasycalc_row_without_chart_value_is_priced_by_native);
  after, tests.test_import_health, test_usatoday_fidelity_jeg480,
  test_verify_import_health, test_promote_section, test_razzball_one_save,
  test_build_lag_gate, test_verify_health_bake_selection,
  test_checkpoints_health_freshest: 149 tests OK on Python 3.12.
- Negative tests prove the guards: with the per-position loop disabled,
  test_big_drop_at_one_position_holds_even_when_the_total_is_small fails;
  with the total check disabled, test_big_total_drop_holds and four existing
  row-drift tests fail.
- Assertion changes: tests/test_usatoday_fidelity_jeg480
  test_other_sources_keep_the_strict_rule used fantasycalc as its example
  strict source; now cbs (fantasycalc is native-priced by this fix).
  tests/test_supabase_import test_bad_rows_go_to_review's two bad-value
  fantasycalc rows now also have no native_value, so they still go to review
  (with a native number they are priced by it, the JEG-480 rule).

### Claimed, not confirmed
- Post-merge chain run promotes FantasyCalc: see the follow-up entry below
  once the run is checked.
- Local `python3` is 3.9: tests/test_razzball_one_save test_latest_save_rows
  fails there (fromisoformat cannot parse a 1-digit fraction before 3.11),
  passes on 3.12, which CI uses. Pre-existing, not touched.
