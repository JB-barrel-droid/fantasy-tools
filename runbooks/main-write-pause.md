# Pause automated main publication (JEG-1215)

This switch defers only Git publication. It does not disable workflows, imports,
validation, database writes already performed by existing jobs, Pages, or PR CI.
No live pause is enabled by this PR. Parent release owner activates/restores it.

Control: `.github/main-write-pause.json`, default `paused: false`. Writers fetch
current main before staging a publication commit and again before each push.
They use the control from fetched main, not the checkout's old copy. Branch-only
bake/backfill jobs are unchanged. Ten main writers have twelve guarded blocks;
`tests.test_main_write_guard` pins that inventory and rejects unguarded writers.

## Activate

1. Merge Pages sharding #1056 first. Merge/review this plumbing with green CI.
2. Confirm all active writers use this plumbing; let older-code runs finish.
   Changing the file cannot retrofit a guard into jobs already using old code.
   Do not cancel broader jobs without specific approval.
3. Through an approved PR, set `paused: true`, `started_at` to current UTC,
   `expires_at` to an explicit future UTC time no more than six hours later,
   and a nonempty `reason` naming the release owner/window. Do not edit schedules
   or Supabase. Example shape (replace timestamps; never reuse this example):
   `{"paused":true,"started_at":"<UTC ISO time>","expires_at":"<UTC ISO time>","reason":"release owner/window"}`.
4. Verify publication summaries say paused and artifact uploads succeeded.
   Activation's own main commit and already accepted pushes can trigger Pages;
   wait for in-flight writers to reach their guard before calling main stable.
   A change after a guard fetch makes an ordinary old-tip push reject, and the
   existing retry path checks the control again. No force push is introduced.

## Retention and failure behavior

Each paused publication uploads `deferred-<writer>-<run-attempt>` for 14 days.
It contains a binary Git patch and JSON metadata (base commit, control tip,
reason, timestamp and run ID). Stage patches include only explicitly staged
publication paths, excluding partial unstaged fixtures. The index is unstaged
without removing worktree bytes, preventing a later health publication from
accidentally including a deferred candidate. Push patches retain unpushed commits.

A deferred step exits successfully with `pushed=false`; downstream processing
continues and deploys conditional on an actual push stay conditional. Pages itself
is unchanged. The job summary and warning annotations identify deferral.

Malformed/unreadable control or a failed fetch defer publication and retain the
candidate, rather than pretending the pause is off. A retention failure is an
explicit step error and must be investigated; it is never reported as a successful
pause. Upload steps run with `always()`. Missing control means the default off
state, allowing pre-install main and deliberate rollback compatibility.

## Restore

Parent release owner merges a PR setting `paused: false` (keep the file).
Verify subsequent writer summaries say unpaused and ordinary pushes resume.
A valid pause automatically stops applying at `expires_at`, even if the restore
PR is delayed; fix malformed control explicitly. No background job or database
change is needed. This task is not operationally complete until the parent has
verified restoration after any actual activation.

Regenerate and validate fresh output after restoration. Retained patches are
recovery evidence, not permission to replay stale data: inspect metadata and
apply against the recorded base in an isolated branch only after review.

## Integration with JEG-1206 / #1054

This PR is independent of #1054 and currently changes the existing rebuild
publication block. The integrator must retain both guards when combining its
new worktree publisher: guard before the candidate commit and immediately before
each worktree push, retaining the root candidate for recovery. Re-run both retry
and pause suites after integration. The writer inventory test rejects a new
unguarded `git -C ... push`. Do not merge either PR with that conflict unresolved.

## Reverse the design

Use a reviewed revert PR for this guard and its workflow wiring after restoring
`paused: false`. Do not delete workflow branches, artifacts, or generated output.
