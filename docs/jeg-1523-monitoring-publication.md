# Monitoring publication staging (JEG-1523)

A partial implementation moves the health pair through versioned object bundles. Written by Codex, 2026-11-05. Status: staged core slice; **not ready for production cutover**.

## Inventory

| Artifact | Producer | Consumers / coupling | This slice |
| --- | --- | --- | --- |
| source-import-health.json, pipeline-checkpoints.json | health-artifacts.yml; rebuild-chain.yml also writes health | health_artifacts_watch.py; modules/status.html; modules/dashboard.html; monitor_alerts.py; chain/checkpoint diagnostics | Health workflow pair + watcher migrated behind switch; other readers/writer remain legacy |
| monitoring-summary.json | health-artifacts.yml / build_monitoring_summary.py | status.html, dashboard.html, audit_monitoring_coverage.py, monitor_alerts.py | Inventory only |
| ops-status.json | health-artifacts.yml / build_ops_status.py | status.html | Inventory only |
| fidelity-pulse.json | fidelity-pulse.yml / fidelity_pulse.py | status.html; fidelity_hold.py; fidelity_pulse.py --previous; rebuild chain holds and resync dispatch logic | Inventory only; previous-run state must migrate before writer |
| comparison-chain-status.json (including failed heartbeat), github-actions.json | rebuild-chain.yml; record_post_rebuild_validation.py; lib/record_workflow_run.py | status.html/dashboard.html; check_deadlines.py; chain_stuck_alert.py; source_lateness.py; build_pipeline_checkpoints.py; coverage_triage.py | Inventory only; split status from successful production fixture publication and preserve late post-validation writes |
| .github/source-vintage-state.json | source-vintage-check.yml | source-vintage dispatcher loop guard | Inventory only; read durable state before dispatch to prevent loops |

Production fixtures, player bakes, input lineage and value reports remain on main. SOURCE.md's historical counts are evidence, not a live November 5 baseline.

## Implemented contract

`MONITORING_PUBLICATION_URL` empty means legacy behavior. Nonempty makes the health-pair producer publish via HTTP PUT and makes the health watcher resolve the same channel. `MONITORING_PUBLICATION_TOKEN` is an optional write-only bearer credential provided by the operator; never logged. Existing watcher observation recording, source-time freshness thresholds and arrival outcomes remain in place. The producer still copies local dist files so timestamp arrival expectations and local alerts use this run's bytes.

Gateway keys under `<base>/v1/health/`:

- `objects/<sha256>.json`: canonical original JSON, including original source timestamps and red states.
- `versions/<revision>.json`: durable schema-version-1 manifest containing object hashes, keys and source timestamps.
- `latest.json`: stable served manifest, published only after all objects and version manifest succeed.

Readers validate schema, manifest revision, object key and SHA-256. Missing or corrupt data fails closed; there is no fallback to stale legacy data. Publication makes no git calls and has no automatic retries. The existing health workflow concurrency group serializes this producer. A gateway must atomically replace objects and retain immutable history; public GET must support no-cache. Cross-producer namespace ownership must be designed before adding chain writes. A failed pointer PUT can have an unknown outcome: reconcile the manifest revision before considering another operation.

## Remaining release work

This implementation is intentionally a complete core slice rather than a claim that JEG-1523 is complete. It does not provide a deployed storage gateway, browser resolver, other producer migrations, full inventory of indirect readers, retention policy enforcement or production telemetry. CI build artifacts alone are not the durable store.

Before activation, implement a durable HTTP object gateway and public served endpoint; migrate browser readers and all remaining producers/readers in the table; preserve dispatch loop guards and chain heartbeat arrival/deadline alerts; stage verification using real HTTP and failed/late publications. Add workflow-level tests and run the complete deploy gate successfully. Verify scoped publication-pause retention against the gateway in staging; the health switch calls the existing stage guard before any upload. Protect against stale/out-of-order publication if additional producers can share a namespace. Add channel rollback/read-consistency tests.

Human step: **Jeremy approves the named production publication deployment and cutover**, after review and green CI. Jeremy provisions the endpoint and enters credentials himself; no GitHub settings changes by agents. Once the migration is complete, one `MONITORING_PUBLICATION_URL` configuration change selects producer and consumer channel; reset it to empty to roll back only after regenerating fresh legacy copies. At present, setting it would strand browser readers on aging files, so do not enable it.

## Local reduction simulation

`python3 -m pytest -q -s tests/test_monitoring_publication.py` simulates 24 distinct health observations in an in-memory object gateway. All 24 version manifests remain addressable. Legacy pair publication is modeled as one main commit per observation: 24 versus zero channel artifact commits, a 100% reduction for that pair only. This is a deterministic modeled count, not measured GitHub push/deploy savings or a ticket-wide forecast.
