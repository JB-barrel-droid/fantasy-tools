## 2026-10-23 - JEG-793 egress trims (gzip, vintage check, narrower importer reads)

Contract: three trims Jeremy approved on 2026-10-23 (multiple choice) that must not change data, values or published output. No schedule or cadence change; no front end change.

### What changed
- `pipelines/gh_sbclient.py` (the only Supabase client in CI; every workflow copies it in as `sbclient.py`): sends `Accept-Encoding: gzip`, decodes transparently. `[supabase-bytes]` keeps `bytes=` as the decoded size (comparable with the audit) and adds `wire=` (on-wire, what the bill sees); the step-summary table gets a `wire` column.
- `pipelines/check_source_vintage.py`: ESPN, CBS ROS and Razzball are read for the newest snapshot date only (one `limit=1` lookup, then the dated slice) instead of the whole table; all sources select only the columns the derivation reads (was `select=*`).
- `pipelines/import_supabase_references.py`: same newest-date lookup (`latest_date_param`) for ESPN, CBS ROS and Razzball. `_select_latest_snapshot_date` still runs on the result, so the selection logic is unchanged.

### Verified (check named)
- Data identical with and without each trim: `tests/test_egress_trims_jeg793.py` (11 tests; in-memory PostgREST stand-in with multi-date, multi-week, multi-bake, NULL-date and superflex rows). Vintage check compared against a copy of the legacy whole-table logic for all six sources; importer snapshot and manifest compared byte-for-byte (JSON) scoped vs unscoped for espn, cbsros, razzball; gzip vs plain reply returns equal data.
- Each guard fails on a broken state (mutations run with `/tmp/jeg793/mut.py`, all caught): no gzip decode, no Accept-Encoding header, wire not recorded/printed, `week` dropped from the CBS ROS select, `source_content_date` dropped from the Razzball select, `bake_id` dropped from the source_trade_values select, ascending instead of descending date order in both the checker and the importer; an off-by-one (second newest) date fails in-suite.
- Existing tests still pass, run one file at a time: test_check_source_vintage, test_gh_sbclient_bytes, test_supabase_import, test_razzball_supabase, test_razzball_refresh, test_rebuild_chain_source_resiliency, test_superflex_publisher_values, test_bake_on_change, test_checkpoint_c2_collection, test_usatoday_fidelity_jeg480, test_verify_health_bake_selection.
- Row bytes, live project iskiybsimubiujwuchsl, read-only SQL (`length(to_jsonb(row)::text)`): razzball 12,295 rows / 11.74 MB whole vs 675 rows / 0.64 MB newest date; cbs_ros 5,857 rows / 4.77 MB vs 366 rows / 0.30 MB; espn 975 rows / 0.55 MB vs 588 rows / 0.35 MB.

### Claimed, not confirmed
- Supabase actually returns gzip for PostgREST responses and bills on-wire bytes: not tested against the live API (no key used in this session). The first Actions run after merge prints `bytes=` vs `wire=`; compare with the dashboard once.
- Gzip ratio (5-10x) is an estimate from the audit; no live measurement.
- Vintage-check saving per run (about 15 of 19 MB) and rebuild-chain saving (razzball 10.7 MB and cbs_ros about 4.5 MB per run, from the row sizes above) are derived from the audit counters and these row sizes, not from an Actions run.
- No full-chain before/after dry run: the chain writes `dist/` and the publish path is `make sync` only. The importer equivalence is proven on builder output with fixtures, not on a live rebuild.

### Deliberately not done (and why)
- `verify_import_health.py` still reads whole tables (narrow columns). It publishes `ignored_older_rows = len(rows) - len(latest_rows)`, which needs the whole-table count; scoping it would change a published health field. Option if wanted: a count-only request.
- `build_week_history.py --supabase` already selects explicit columns; unchanged.
- Importer `select=*` is kept for the dated slice: the builders pass `raw_stats`, per-game, team, health and other row fields through; a column list needs a per-field audit against the real table and was judged not worth the risk next to the date scoping (which removes about 94% of those rows). Follow-up candidate.
- The audit's "source_trade_values fetched 4 times" are disjoint slices (fantasycalc, usatoday, fantasypros importers, plus the health re-query), not repeats; the importer already scopes to the latest week. The real repeats were whole-table reads of razzball, cbs_ros and espn, now date-scoped. No cross-process cache was added: separate processes would need an on-disk cache invalidated by the writes in the same chain.
