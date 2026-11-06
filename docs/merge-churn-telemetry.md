# Merge churn telemetry

JEG-1525 implements the local collection and reporting slice of JEG-1513 section 6 follow-up 3. It measures observed PR events rather than deriving PR-ready times or rebases from commit timestamps. Owner: JEG-1525. Last verified: 2026-11-05 against fixture tests. No live baseline has been collected.

## Run locally

Python standard library only; no credentials or network required. From the repository root:

```sh
python3 pipelines/merge_churn.py --db output/merge-churn.sqlite collect --fixture tests/data/merge_churn/week.json
python3 pipelines/merge_churn.py --db output/merge-churn.sqlite report --repository example/tools --start 2026-11-02T00:00:00Z
python3 pipelines/merge_churn.py --db output/merge-churn.sqlite report --repository example/tools --start 2026-11-02T00:00:00Z --json
python3 -m unittest tests.test_merge_churn -v
```

The checked-in fixture is synthetic, recorded in the normalized input format for deterministic tests. It is not captured GitHub activity and its numbers are not a production baseline. Choose a durable database path and retain/back up that file. The CLI prints reports to stdout; redirect to retain weekly artifacts. Nothing schedules itself or modifies GitHub.

## Durable schema and source boundary

SQLite `user_version=1` contains `events(repository, source_id, pr, kind, occurred_at, payload)`, keyed by `(repository, source_id)` and indexed by repository/PR/time. Payload is canonical JSON. All timestamps require an explicit timezone and are stored in UTC. The immutable event history retains every head, base-distance sample, lifecycle timestamp, CI attempt observation and explicit refresh time. Report values are derived, not destructive aggregates. Other schema versions fail closed.

`collect(db, source)` accepts any object implementing `EventSource.events()`. `FixtureSource` reads `{ "schema_version": 1, "events": [...] }`. Each event requires repository (`owner/repo`), positive integer PR, stable nonempty source ID, kind, occurred_at and a payload object (empty when unnecessary). Kinds:

| Kind | Required payload | Meaning |
| --- | --- | --- |
| ready | none | Explicit queue eligibility decision, not merely draft-to-ready or CI success |
| enqueue | none | Queue entry |
| refresh | head_sha | Queue/owner explicitly refreshed an integration candidate or branch |
| merge | none | PR merged timestamp |
| head | head_sha | Initial head or head change, with original event time if available |
| base | head_sha, base_sha, behind | Nonnegative integer base commits absent from head at sample time |
| ci | head_sha, run_id, attempt, started_at | One workflow run attempt observation; optional completed_at |

CI event occurred_at is the observation timestamp; started_at/completed_at are execution timestamps. A running attempt's later completion is a **new observation with a new source ID**, retaining the same run_id/attempt. The latest observation as of the report end wins. Use attempt-specific execution start/completion, not PR creation or run creation/queue timestamps. Run IDs are repository-global. A run associated with multiple PRs contributes to each PR's totals but once to repository totals. Minutes measure workflow attempt wall time, not summed job execution, billed minutes or estimated financial cost.

Ingest is transactional and idempotent. Replays insert zero rows; changed content under an existing source ID fails and rolls back the entire batch. Delivery order does not determine report chronology. A malformed batch must be corrected by its producer before another collection; the collector performs no retries. Base samples must be supplied explicitly; unknown distances are omitted, never replaced with zero. No head transition is classified as a rebase or refresh without an explicit refresh event.

## Weekly metric definitions

A report covers seven UTC days `[start, start + 7 days)`. Its PR cohort has at least one event in that window. Earlier history is read to establish initial head and first ready/enqueue times; future events are excluded. Recollecting late-arriving history can revise a historical report.

- Refreshes/PR: explicit refresh events in window / cohort PR count. Head transitions are separately counted, including a transition from a known pre-window head.
- Stale rate: PRs with any `behind > 0` sample in window / PRs with any base sample in window. Multiple samples do not overweight busy PRs. Missing observations are excluded; the report includes the sampled denominator. This is an observed-any-stale rate, not time spent stale.
- Ready-to-merge latency: median minutes from first explicit ready event to merge, for PRs merged within the window with a usable ready event. Open PRs and missing/invalid readiness intervals are excluded, with sample count shown. Re-entry into readiness does not reset this metric; it includes holds after first readiness.
- CI attempts: distinct `(run_id, attempt)` with execution start in window. Completed attempts contribute wall minutes. Running attempts count in attempts but have no completed minutes. Attempts crossing the window boundary contribute their full completed duration only once a completion observation is available before report end. Subsequent reports do not reassign them to completion week; regenerate the original start-week report to incorporate later-known completion only if its observation falls before that report's end. Thus historical reports deliberately remain an as-of-window-end view and may have incomplete duration coverage.
- Superseded CI: a different head event occurs strictly after attempt start and strictly before completion (or report end for running attempts). Report attempt share and completed wall-minute share separately. This counts the entire duration of superseded attempts, not only time after invalidation. An already obsolete SHA at execution start is not included by this definition. Missing head history can undercount. A stale head, canceled conclusion or later run alone is not evidence of supersession.

Undefined ratios and latencies render `N/A` (JSON null). This is an observed baseline with coverage counts, not a target or a claim of complete history.

## Pointing it at live data: remaining integration

The shipped adapter reads fixtures. Live API transport, pagination, queue emission and scheduling are **not implemented or activated**. To collect a live baseline:

1. Implement an `EventSource` adapter for the named repository using approved read-only GitHub access to pull requests/timelines, Actions workflow runs and individual rerun attempts, and commit comparison/contents. Paginate every result and associate runs to PRs without counting unrelated main/branch runs. Handle API failures as failed collections; preserve checkpoint and saved responses rather than blindly retrying.
2. Persist head transitions from webhook/timeline evidence and head/base-distance samples from comparisons at observation time. Polling snapshots miss intermediate heads and cannot recreate historical base distances. Backfill only what is evidenced; label incomplete coverage. Preserve raw responses securely outside public output for audit; never store credentials in event payloads.
3. Wire the actual integration queue to emit stable-ID ready, enqueue and refresh events. Draft-to-ready events alone do not establish independent review plus green-CI queue eligibility. Keep readiness semantics consistent with the queue owner.
4. Configure repository, durable SQLite path/backups, collection cadence and retention. Add API-response fixture tests for pagination, reruns, failure/checkpoint behavior and PR association before activation; compare a saved live sample against GitHub and the queue event log. No live API compatibility has been verified here.
5. Have Jeremy provide/authorize the read access and approve the named collection schedule/activation under repository policy. No credential retrieval, scheduler change, merge, push or deployment is part of this implementation.

A weekly production baseline requires a full week of this coverage. The synthetic test report cannot substitute for it.
