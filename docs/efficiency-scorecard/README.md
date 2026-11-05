# Efficiency scorecard (JEG-1464)

The collector is `scripts/efficiency_scorecard.py`. It calls no models, changes
no service settings, and uses GitHub REST GETs through the installed `gh` login.
It never reads credential files, environment files, cookies, or keys. Bridge
journals and saved result counters are read-only. Only allowlisted numeric
counters and lifecycle metadata leave those files; prompt/report/comment text
is never copied. GitHub authentication remains inside `gh`.

Runtime outputs belong in `/Users/botcomp/code/scratch/jeg1464/out/`. This
directory holds the daily Markdown/JSON, one row/date in `daily.csv`, the
baseline window and PR membership in `baseline.json`, and small capacity,
bridge-load and open-PR CSV samples. Repeating a date replaces its row (so a
partial day can become complete). A nonblocking output lock prevents overlap.
The initial readout is preserved here as [first-readout.md](first-readout.md).

## Run step and schedule (not installed)

Coordinator: run the following command at **06:00 America/Chicago daily,
Nov 1–14, 2026**. It reports the previous complete CT day. The Nov 14 run
includes Nov 13 and writes `final-summary.md`; later automatic runs are no-ops.
No fixed UTC offset: daylight saving time ends Nov 1.

```sh
cd /Users/botcomp/code/scratch/jeg1464/wt && PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin /usr/bin/python3 scripts/efficiency_scorecard.py run --out /Users/botcomp/code/scratch/jeg1464/out --charter docs/efficiency-scorecard/charter.json --asks /Users/botcomp/code/scratch/jeg1464/out/asks.jsonl
```

The equivalent cron entry below is provided for an operator, **not installed**.
It assumes this Mac's scheduler timezone is America/Chicago. The coordinator
run step above is canonical; cron on another timezone must be translated.

```cron
0 6 * * * cd /Users/botcomp/code/scratch/jeg1464/wt && PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin /usr/bin/python3 scripts/efficiency_scorecard.py run --out /Users/botcomp/code/scratch/jeg1464/out --charter docs/efficiency-scorecard/charter.json --asks /Users/botcomp/code/scratch/jeg1464/out/asks.jsonl
```

For small capacity and journal samples every five minutes, the separate command
is below. Each invocation exits; there is no resident polling loop. Automatic
sampling stops after Nov 13. The run command also takes one capacity sample.

```sh
cd /Users/botcomp/code/scratch/jeg1464/wt && PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin /usr/bin/python3 scripts/efficiency_scorecard.py sample --out /Users/botcomp/code/scratch/jeg1464/out
```

Add `--sample-prs` to sample open conflicts and behind-main counts using REST.
It uses three requests per open PR plus list pagination; budget that against
the shared GitHub quota before scheduling. Without it, historical conflict and
behind-main observations remain unknown. These are observations, not backfill.

All modes enforce **3,670,016 KiB (3.5 GiB)** available from
`df -k /Users/botcomp/code`, Jeremy's explicit override for this job. The check
runs before creating output, before every REST call, before saved-result reads,
and before writes. Under the floor, exit 3 prints the available KiB and mount;
there is no cleanup, retry, or credential change. Other collection errors exit
2 without retry. Output already written remains available; a failed collection
does not write successful daily PR counts. There is no automatic fallback.

The first full run stopped on HTTP 403 (core rate limit exhausted, 0/5000).
The explicit degraded command used for the first readout was:

```sh
python3 scripts/efficiency_scorecard.py run --summary-only --start 2026-10-30 --end 2026-10-31 --out /Users/botcomp/code/scratch/jeg1464/out --charter docs/efficiency-scorecard/charter.json
```

`--summary-only` uses REST issue search's independent quota. It validates
`incomplete_results`, paginates daily windows, refuses >1000 results/day, and
uses `pull_request.merged_at`, not `closed_at`. It reports unavailable stage
details explicitly. It is an operator choice, never an automatic retry.

## Counting contract

- A day is `[00:00 CT, next 00:00 CT)`. A current day is labeled partial.
  Each merged PR is counted once per repo, regardless of ticket references,
  author, original draft status or base branch. Unmerged/closed PRs are excluded.
- Open-to-merge means GitHub `created_at` → `merged_at`, elapsed wall hours.
  Median averages the central pair. P90 uses nearest rank:
  `sorted[ceil(0.9*n)-1]`. Missing observations are null, never zero.
- Merge bins are `[06:00,07:00)` and `[16:00,17:00)` CT, with everything else
  outside. The charter names approval times but no window duration. These
  one-hour descriptive bins are explicitly **not evidence of an approval**.
- `baseline.json` records the exact recount bounds, repo set, PR membership,
  start/end fields and percentile method. The recount found 442 PRs in
  `JB-barrel-droid/fantasy-tools`, `[2026-10-17T05:00:00Z,
  2026-10-31T19:43:25.305067Z)`, median 1.9168 h and p90 19.6667 h. The quoted
  Muse baseline stays **442 / 1.9 h / 19.4 h**. Matching the count is not proof
  that Muse used the same bounds or percentile method. Original query and
  `/Users/botcomp/code/scratch/rootcause/` were unavailable; confirmation of
  the original method remains open.
- Stage receipts record started (Linear state type `started`), PR creation,
  ready-for-review/review-request timeline events, first approving review,
  exact-head approval, all observed CI contexts green on the PR head, and
  merge. A non-draft PR with no conversion event is reviewable at creation;
  its first explicit request is a separate timestamp. The merged PR head is
  used, never the squash commit. Reviews and status contexts are paginated.
- Merge-ready is labeled a **proxy**: max(reviewable, first exact-head pass,
  all observed contexts green). Required branch-rule eligibility is not
  available from this proxy, and dismissed approvals may limit it. The first
  review pass can refer to an older head; it cannot establish current-head
  readiness. The slowest stage compares disjoint observed waits; missing
  stages can change the ranking. Open-to-merge is shown separately.
- Daily stage distributions use PRs merged that day. JSON also holds open PR
  receipts at collection time and per-ticket distributions over linked PRs;
  ticket references do not multiply PR counts. Unknown Linear history means
  started-to-open is unknown. `review_pass` exports must name the exact head.
- `pr-samples.csv` records mergeability and `behind_by` at sample time.
  Unknown mergeability is counted separately. Behind-main time integrates
  only consecutive observations ≤10 minutes apart, clipped to the CT day.
  It is a sampled lower bound, not a recovered historical duration. No
  historical conflict state is inferred from current state.

## Coverage and optional inputs

The bridge journals currently record terminal events, not job starts/queues.
Counts are **observed distinct completed run IDs** by event date/provider,
including interrupted/failed/needs-input events, not all jobs started. Event
IDs deduplicate journal mirrors. Failures count journal events, not a model's
structured `blocked` verdict. Running/queued are unknown from these journals.
The first bridge activity receipt measured Claude 0 running, Codex bridge 5
running; the endpoint did not supply queued counts. Other provider journals can
be added with `--journal provider=/path/job-journal.json`.

Claude saved counters cover latest retained native result files, not every
resume; 20 results on Oct 30 had 194 turns and $14.4551 **list-equivalent**
dollars. This is not spend and does not reproduce JEG-1429's full ledger.
Tokens are counted only where numeric counters exist, with a recorded count
beside each total. No Codex/Muse/OpenCode/Pi token or dollar usage is invented.
The live JEG-1429 ledger path was unavailable. Jobs are not equated to verified
ticket completions. Comparisons do not pool job types or risk tiers.

RAM used is `(active + wired + physical compressor pages) × page size` from
`vm_stat`, excluding inactive cache. Total RAM and CPU count are from `sysctl`.
CPU readings are 1/5/15-minute load averages, not utilization percentages.
Pressure is the raw `kern.memorystatus_vm_pressure_level` (1 normal, 2 warning,
4 critical). Historical capacity on Oct 30 is unavailable.

The following optional exports contain **only these fields**, no prose or
credentials. The script does not call Linear GraphQL or Duet's private stores:

```json
{
  "JEG-123": {
    "stateHistory": [{"state": {"type": "started"}, "startedAt": "2026-10-30T10:00:00Z"}],
    "review_pass": [{"at": "2026-10-30T12:00:00Z", "head_sha": "exact-pr-head"}]
  }
}
```

Pass that file with `--linear`. For Duet asks, coordinators must append one
line per ask to shared `out/asks.jsonl`, e.g.
`{"id":"unique-ask-id","at":"2026-10-31T19:00:00Z"}`. Count one ID per day;
no question/message text. An absent/empty unconfirmed log is unknown, not zero.

`--activity` accepts a fresh exported `get_bridge_activity` receipt such as
`{"at":"...","claude":{"running":0},"codex_bridge":{"running":5}}`.
Missing queued/failed counters stay unknown. Receipts older than five minutes
cannot supply current load. No code in this tool starts a bridge job.

`charter.json` enumerates the JEG-1444 execution items and intended metrics.
Shipping and deployment dates start unknown: a merged PR is not proof a bridge
patch is live. The coordinator supplies verified `shipped`, ISO `go_live`, and
evidence-backed `observed_change` (better/worse/no change, or unknown). Dates
after a report's day cannot be shown as live then. No causal effect is claimed.
Pending original baseline provenance, stage backfill, go-live evidence and an
independent Claude review prevent claiming the entire ticket done.

## Checks

```sh
python3 -m unittest tests.test_efficiency_scorecard
git diff --check
```

Fixtures exercise exact-head gates, missing data, pagination/search integrity,
CT/DST boundaries, disk-stop-before-write, deduplication, sampled durations,
stale activity and idempotent daily rows. F1 is not applicable: this is an
offline reporting script, with no product/runtime or F1 harness changes.
