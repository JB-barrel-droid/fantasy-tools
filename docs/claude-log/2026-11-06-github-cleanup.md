## 2026-11-06 - GitHub Actions and branch cleanup sweep (no ticket; repo hygiene)

Contract: at Jeremy's request ("Clean up my GitHub processes"), inventory
workflows, runs, branches and PRs, then carry out his choice "A. Hygiene sweep":
delete merged branches, disable orphaned workflows via a PSpice print, and
ticket the always-red workflows. No code, workflow or config file changed.

### Verified (check named)
- 154 non-main branches: 25 have a merged PR, 47 a closed-unmerged PR, 31 no PR
  and 51 an open PR (`git ls-remote --heads` joined to every PR head ref via
  `gh api repos/.../pulls?state=all`, paged explicitly).
- 20 of the 25 merged branches still sit at their merged PR's head SHA
  (`gh api pulls/<n> .head.sha` == `branches/<b> .commit.sha`). The other 5
  (banana/fix-main-bench-share, be/JEG-975, be/jeg-820, be/jeg-833,
  claude/divergence-evidence-audit) moved after merge and are kept.
- 11 registered workflows have no file on main. 5 are on open-PR branches
  (fast-gate #1260, pr-freshness #1262, release-batch #1303,
  versus-vegas-preview-tests #1294, jeg1209-preview #1096) and must stay
  enabled. 6 are orphaned (`gh api contents/.github/workflows/<f>?ref=<open
  ref>` for every open PR ref).
- Always red: `health-artifacts.yml` (every run since 2026-10-30; push to main
  fails 3x, then the served-artifact watch exits 2), `render-sweep.yml` (every
  run since 2026-10-29; 4 tests in 3 modules), `full-suite.yml` (7 of 8 nightly
  runs cancelled at the 120-minute timeout), `chain-run-feedback.yml` (its only
  run failed, printing `gh api` usage). Checked with job logs via `gh api
  actions/jobs/<id>/logs`.
- Run 37642358642 (Record site deploy, queued since 2026-10-07) cannot be
  cancelled: `cancel` and `force-cancel` both return HTTP 409 "not been queued
  yet". Only deleting the run record removes it, and that needs Jeremy's yes.
- Filed JEG-1546 (render sweep) and JEG-1547 (nightly suite timeout) in Backlog.
  Commented evidence on JEG-1522 (chain-run-feedback) and JEG-1523 (health
  artifacts), with marker `claude-gh-cleanup-2026-11-06`.

- Second pass (Jeremy chose "B"): removed `.github/workflows/jeg1140-settings-render.yml`.
  JEG-1140 was canceled on 2026-11-06, yet the workflow still ran on every PR
  touching `v2.js`, `v2.css`, `workspace.js` or the `Makefile`. Its three test
  modules stay covered by `make test-unit-modules` (Makefile lines 223-225).
  Also dropped its manifest line in `config/monitoring_coverage.json` and its
  name from the workflow list in
  `tests/test_org_cutover.py::test_build_and_status_workflows_export_shared_repository_variable`.
  That assertion read a file that no longer exists, so the assertion itself was
  wrong once the file was removed; no other assertion changed.
- `jeg1265-values-fieldnotes.yml` is kept: it is the only runner of
  `tests.test_jeg1265_values_fieldnotes`, so removing it would drop a test.
- `python3 -m unittest tests.test_org_cutover`: OK.
  `tests.test_monitoring_coverage::test_real_repo_is_fully_covered` is red with
  and without this change, with the identical problem list:
  `chain-run-feedback.yml`, `main-write-pause-switch.yml` and
  `main-writer-checks.yml` are missing from the manifest. That is pre-existing on
  main and not in `docs/baseline-reds/registry.json`; it is left for those
  workflows' owners.
- Moved #1260 and #1084 back to draft, bringing ready-for-review PRs from 10 to
  the cap of 8.

- 2026-11-07: the 20 merged branches were deleted by bridge Mac job
  `gh-cleanup-branch-deletes-2026-11-07` (Jeremy: "A", run through a bridge
  worker; PSpice's runtime blocks api.github.com). The job's script checked
  each branch's head SHA before deleting it and reported 20 DONE, 0 skipped,
  0 failed. Independently confirmed afterwards with `git ls-remote --heads
  origin` from the cloud session: all 20 are gone.
- 2026-11-07: closed #1260 as superseded (Jeremy: "3A"), with notes on the
  PR and on JEG-1451. Branch `codex/JEG-1451-fast-gate` is kept.
- The phantom run 37642358642 cannot be deleted either: `DELETE
  actions/runs/37642358642` returns 403 "Could not delete the workflow run"
  from GitHub. Only GitHub Support can clear it; it is harmless.

### Claimed, not confirmed
- The 7 orphaned workflows (the 6 listed plus `fast-gate.yml` after #1260
  closed) are still enabled. No agent route can reach the API to disable
  them, and they cannot start without a file on main or on an open PR branch.
- `make validate` could not finish locally: one `test-core` error,
  `ModuleNotFoundError: No module named 'playwright'` in
  `tests.test_week_history` (Python Playwright is not installed in this
  container). The PR's preview CI is the authoritative run.
- (2026-11-06; superseded by the 2026-11-07 Verified bullet above for the
  branches.) This cloud session can push only to its own branch, and the API
  write path returns 403 through the proxy, so the deletes and disables were
  first handed to Jeremy as a PSpice print.
- The health-artifacts push failures likely share a cause with JEG-1519 (bot
  rate limit) and should clear with the JEG-1523 cutover. Not reproduced.
