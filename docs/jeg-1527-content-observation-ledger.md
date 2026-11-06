# JEG-1527 content observation ledger and scheduler audit

This record describes the local observation-store core and audits scheduler evidence in this checkout. Written by Codex, 2026-11-05. No production schedule or database was queried or changed.

## Implemented contract

`pipelines/lib/content_observations.py` owns a local SQLite schema and writer. Each observation is an immutable row with a complete serialized six-part scope: source, dataset, season, week_slate, scoring, variant. SQLite triggers reject update/delete. `BEGIN IMMEDIATE` serializes read/append so concurrent writers cannot derive clocks from the same obsolete predecessor. Each row retains its normalized native snapshot, hash, previous accepted hash, normalizer version, result, coverage, snapshot reference, consumers, and optional ingested/served hashes. Storage must be persisted by the eventual scheduler; an ephemeral Actions checkout is insufficient.

`Ledger.observe()` accepts complete parsed native rows and explicit expected coverage. Call it after existing identity, schema and source-specific validation, before scaling or pricing. Acquisition failures use result `failed` or `skipped`; incomplete coverage is recorded without advancing accepted hash or clocks. Invalid identities/schema/numbers raise before writing and must be recorded as failed by the collector. This core does not replace identity resolution, expected-identity-set validation, Razzball doubled-Games validation, or upstream parser guards.

ESPN input rows use canon/player_id, pos and native weeks/stats dictionaries. Submit independent datasets `skill`, `k`, `dst`; mixing their positions fails. FantasyCalc accepts API player.id/value rows or the current collector's fantasycalc_id/value rows. Razzball accepts position-table rows with rz_std_ppg, rz_half_ppr_ppg, rz_ppr_ppg, games_reported and the listed native raw-stat columns. It does not parse or select HTML tables. CBS accepts parsed player_name/gp rows with native raw_stats, including receptions. Scrape dates, build fields and publisher page stamps do not enter hashes. All adapters sort identities, preserve null/zero and additions/deletions, and encode finite decimal values without rounding. Hashes are full SHA-256.

An initial observation is an unknown-vintage baseline. Only a subsequent valid different hash in the same normalizer version establishes observed change time. Normalizer changes establish a new baseline, not vendor change. Unchanged pulls preserve content time, including previously trusted numeric time. Explicit timezone-aware numeric update timestamps may establish baseline vintage only when the caller has validated their semantics. Date-only trusted numeric timestamps are rejected; unverified publisher dates are retained only as supporting evidence. Page publication labels are not trusted numeric timestamps.

`verdict()` computes ages at evaluation time: strictly greater than 86,400 seconds is stale; unknown vintage, future numeric time, materially inconsistent clocks, incomplete/failed/skipped acquisition and overdue pulls are separate reasons. Failed attempts preserve prior accepted timestamps and therefore cannot erase content staleness. A caller can reevaluate without a bake.

`pipelines/observe_content.py` is an offline CLI writer. Supply `--ledger PATH --scope scope.json --rows rows.json --expected N --attempted-at UTC_ISO`. Scope JSON contains the six Scope fields; rows JSON is a parsed native list. Use `--result failed` without rows for failed attempts. The CLI neither fetches nor publishes.

`build_dataset_status()` reads the default local ledger (or an injected Ledger) and accepts `observation_scopes`, also available via `meta.content_observation_scopes`: a map from panel key to a list of complete Scope dictionaries. All configured scopes must be healthy. Missing scopes/history are non-green. Per-scope freshness observations expose both clocks, age, hash, coverage, evaluation time and reasons. CBS ROS is added. Primary model health inherits ESPN input health rather than bake date. Pending sources remain pending with explicit unhealthy freshness. No synthetic historic observation is created from legacy snapshot dates.

## Scheduler and registry audit (repo evidence, not live state)

| Source | Current evidence | Coverage/registration limits |
|---|---|---|
| ESPN skill | `source_probe_schedules_20261008.sql` declares `source-probe-projections`, `25 3-23/4 * * *` UTC, dispatching source-probe.yml for espn,cbsros,razzball; source_probe.py maps ESPN changes to espn-supabase-sync.yml | The migration explicitly removes trigger-espn-sync-live. Commented old Actions timer is not active scheduling evidence. Probes detect changes; they are not observations in this ledger. |
| ESPN K / DST | Separate ledger scopes are supported and position-checked | dataset_status.py says K/DST chart entries retired under GAP-029; no separate active collector registration established here. Do not infer their coverage from skill ESPN. Reconcile current consumers before adding required panel scopes. |
| CBS ROS | Same four-hour projection probe declaration; cbsros-supabase-sync.yml remains dispatchable | Migration removes trigger-cbsros-sync-live and trigger-cbsros-sync-retry. Old commented Wednesday timer does not prove current registration. Acquisition date is excluded from content hashing. |
| Razzball | Same projection probe declaration; source_probe.py maps to razzball-supabase-sync.yml | Migration removes razzball-sync-live. Existing probes include page stamps/table hashes, which do not satisfy this numeric-only ledger. Source-specific native extraction/validation still required. |
| FantasyCalc | `source_probe_schedules_20261008.sql`: source-probe-fantasycalc at `5 * * * *` UTC; fantasycalc-weekly-save.yml documents trigger-fantasycalc-weekly-save Tue/Fri 13:07 UTC | Current pull_fantasycalc_12team.py pulls 3 scoring formats at 12 teams for 1 QB and independently 2 QB: six lists, not SOURCE.md's historical 24. 2-QB failure currently does not block 1-QB saves. Complete required-combo atomic promotion is not implemented here. |
| FantasyCalc drift | fantasycalc-drift.yml explicitly MANUAL ONLY; producers_schedule_tidy_20261008.sql retires trigger-fantasycalc-drift-live | Contrary to the older SOURCE.md inventory, the current workflow no longer triggers refresh. Drift is not a content clock. |
| Editorial charts | source_probe_schedules_20261008.sql declares `35 */3 * * 1-4` and `35 0,12 * * 0,5,6` UTC for cbs,usatoday,fantasypros | Numeric adapters and ledger recording for these sources remain unwired; panel reports unknown instead of green. |
| ECR, prediction markets | dataset_status.py documents ECR and prediction-market leg retirement | Do not reactivate retired sources. Weekly consumer lifecycle outside this core remains to be reconciled. |

Registry evidence currently lives in `pipelines/source_probe.py` POLICIES and workflow mapping plus SQL declarations; it is not a verified enabled-source manifest. This change activates no timer. Actual `cron.job` enabled flags and `cron.job_run_details` were not available/queried. An authorized operator must export them and reconcile deployed state before changing schedules; do not enable duplicate Actions timers.

## Remaining before full ticket acceptance

Connect validated collectors to the durable writer on every acquisition, including unchanged early-return paths and failures. Archive original raw payloads in durable storage and provide their references. Reconcile Razzball native raw-stat aliases with the acquiring parser and retain its doubled-Games guards. Provide expected identities/position coverage, not merely a row-count expectation. Reconcile six currently supported FantasyCalc lists versus any other enabled consumer combos; implement all-required-combo atomic promotion without changing numeric methodology. Wire bake metadata to the exact served scopes and verify ingested/served hashes. The supplied API stores those hashes but does not prove propagation.

Add remaining editorial adapters and any other explicitly enabled required chart sources. Wire durable ledger persistence/read access into workflows. Implement hourly/client status reevaluation so displayed flags age without rebakes, JEG-1515 readiness gating and alert routing. The helper can recompute verdicts now, but no hourly dispatcher or client updater is activated by this change. No live source freshness or scheduler execution is certified.

Human step: Jeremy must specifically approve any production database migration, schedule activation, merge/deploy, or production-data change. The acting coordinator must reconcile live scheduler exports and JEG-1515's exact interface before that approval; no approval is requested in this local-only implementation.

## Post-review acquisition wiring (2026-11-06)

The ESPN, FantasyCalc, Razzball ROS and CBS ROS pull entry points now write
observations before promoting their output. ESPN also records unchanged pulls
before its early return. Failed/partial entry-point runs append failed
observations; FantasyCalc's optional superflex failure invalidates those three
scopes while retaining its existing independent 1-QB save behavior. A ledger
write failure stops promotion and is not automatically retried.

`CONTENT_OBSERVATION_LEDGER` selects the shared SQLite file (default:
`data/content-observations.sqlite3`). Acquisition and bake must use the same
persistent file. Bake supplies the recorded 2026 ROS scope keys in
`meta.content_observation_scopes`; dataset status validates source, season,
ROS dataset and required ESPN position coverage before reading verdicts.
The current skill-only chart requires ESPN skill, and would additionally
require independent K/DST scopes if those positions were served. Missing or
invalid mappings and incomplete ledger coverage remain non-green.

The `native-v2-numeric` normalizer retains team/position text in snapshots and
coverage but excludes those descriptive fields from numeric hashes, and includes
the Razzball collector's native `pg_*` and share-column names. Changing
normalizer version establishes an unknown baseline, rather than treating the
hash-format migration as evidence of fresh numbers.

These are local acquisition integrations, not deployed storage provisioning.
Separate CI runners still need an explicitly shared durable ledger; no storage,
workflow, schedule or production configuration was activated by this fix.
Original raw-response archival and ingestion/served-hash propagation remain
unimplemented, as listed in the original implementation report.
