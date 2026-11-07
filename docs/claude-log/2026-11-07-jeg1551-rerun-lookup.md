## 2026-11-07 - JEG-1551 merge flow: find the receipt run by PR after a review

Contract: fix the Codex app's P1 on PR #1341 head 8c10671c. After a review,
`rerun-after-review` looked up the trusted receipt run by the PR's head SHA,
but a `pull_request_target` run records main's commit as its head SHA, so it
found nothing and a passing review never refreshed the check. This corrects
`2026-11-07-jeg1551-review-fixes.md`, which said a review re-runs the check.

### Verified (check named)
- `review_receipt.find_receipt_run` finds the newest trusted run for the
  reviewed PR through the run's linked pull requests, then the
  `review-receipt` check run on the PR head (only when that run belongs to
  the receipt workflow), then the PR's branch, and never queries by the PR
  head SHA: `tests.test_jeg1551_merge_flow.FindReceiptRunTest`.
- The `rerun-after-review` job checks out main, calls
  `python3 -m pipelines.review_receipt find-run`, uses no head SHA, and
  putting a head-SHA lookup back is caught:
  `tests.test_jeg1551_merge_flow.WorkflowWiringTest` (fails on the previous
  workflow file, passes on this one).
- Focused suite (154 tests) passes apart from the monitoring-coverage test,
  which names only chain-run-feedback.yml, main-write-pause-switch.yml and
  main-writer-checks.yml, as on main.

### Claimed, not confirmed
- GitHub links `pull_request_target` runs to their PR in the runs list or
  through the check run on the PR head; the first real review after #1341
  merges will show which path finds it. If none does, the job now fails
  visibly instead of passing silently.
