## 2026-11-07 - JEG-1551 merge flow: fixes from the independent review

Contract: fix the nine findings of the independent Codex review of PR #1341
(first head of the merge flow), so the review-receipt check cannot be edited
or faked by a PR and the data pin never mixes two data states. This corrects
parts of `2026-11-07-jeg1551-merge-flow.md`, which said a `ddf-review` comment
from any agent counted and that the receipt workflow ran on `pull_request`.

### Verified (check named)
- `review-receipt.yml` runs on `pull_request_target`, `merge_group` and
  `workflow_run` (after the new `review-receipt-trigger.yml`), never checks
  out the PR's code, and has exactly one job named `review-receipt`; editing
  the trigger back to `pull_request` or checking out the PR head is caught:
  `tests.test_jeg1551_merge_flow.WorkflowWiringTest`.
- Only the Codex GitHub app or a `DDF_REVIEW_LOGINS` login other than the PR
  author counts as a reviewer; an app review with a P0/P1 badge (in the body
  or an inline comment) fails, its thumbs-up counts only after the head's
  first check suite, and a listed login's verdict must be the first line:
  `tests.test_jeg1551_merge_flow.ReviewReceiptTest`.
- A comparison of 300 or more files cannot carry an old review over to a new
  head, and renames count by both names for the old-head comparison, the
  value-math hold, the docs-only rule and the data pin: same test file
  (`ReviewReceiptTest`, `ChangeScopeTest`, `DataPinSnapshotTest`).
- One run resolves one pin in `pr-state` (`data_pin` output) and every build,
  shard and render job applies it through `DATA_PIN`; a pin missing any data
  root changes nothing; a failed restore is undone, including files the pin
  added, while files that were already there are kept:
  `tests.test_jeg1551_merge_flow.DataPinSnapshotTest` (real temporary git
  repo) and `WorkflowWiringTest.test_pr_state_resolves_one_pin_for_the_run`.
- The docs-only classifier is checked against every old build input, alone
  and next to a docs file, and removing any one input from it is caught:
  `tests.test_ci_speedup_workflows`.
- `review-receipt-trigger.yml` is listed in `config/monitoring_coverage.json`:
  `tests.test_monitoring_coverage` names only chain-run-feedback.yml,
  main-write-pause-switch.yml and main-writer-checks.yml, as on main.

### Claimed, not confirmed
- A review on GitHub re-runs the trusted check through the trigger workflow;
  the first real review will show it.
- A PR could add a second job reporting a check named `review-receipt`; the
  independent review sees it in the diff. A code-owner rule on `.github/`
  would close it fully, and that is a GitHub setting for Jeremy.
- Pages publishing on merge needs no per-merge yes: Jeremy answered "A" on
  2026-11-07 (03:46 UTC) to option A, "No yes needed": merged PRs publish the
  site as data refreshes do, and his yes stays for Supabase and function
  deploys, migrations and value math (finding 7). The first real merge will
  show the deploy runs.
