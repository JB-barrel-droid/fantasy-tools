## 2026-10-30 - JEG-1373 Waivers mutation offline classes on every PR (#1232)

Contract: run the three offline classes of `tests/test_waivers_mutation_specificity.py` (JEG-1279, #1144) on every PR as
their own check that goes red on a failure but does not block merges, with test-core unchanged (Jeremy's option A,
2026-10-29 9:32 PM CT).

### Verified (check named)
- The new check runs on PRs and passes on a clean head: `waivers-mutation-offline` run 41129316814 on 24ae279, 21 tests OK,
  Playwright 1.49.1 package installed, no browser.
- A PR that breaks a Waivers mutation check shows the failure on that PR: temp commit 1ec0b96 broke the `no headline text`
  anchor in `app/v2/waivers.js`; run 41129437046 on #1232 failed with `StaleAnchor ... occurs 0 times`. Revert abe0a50
  (tree identical to 24ae279) is green again.
- The step fails rather than exits 0: GitHub runs it under `bash -e {0}` (job log), and the independent review showed the
  same script without `set -o pipefail` exits 0 on a broken anchor, with it exits 1.
- Stays out of the required path and test-core: `tests.test_waivers_mutation_offline_workflow` (18 tests, each rule
  negative-tested) checks preview.yml, pages.yml and every `test-core*` Makefile target; `git diff origin/main` touches no
  test-core recipe.
- Existing guards pass on 1661fda: `tests.test_monitoring_coverage` (failed on abe0a50 because the workflow was not in
  `config/monitoring_coverage.json`; review finding, fixed), `test_workflow_script_paths`, `test_workflow_no_event_interpolation`,
  `test_workflow_dispatch_permissions`, `test_ci_speedup_workflows`, `test_preview_workflow_matches_pages`,
  `test_no_failopen_workflows`, `test_validate_shards`.
- Independent Claude review: changes needed on abe0a50 (the monitoring entry), delta review of 1661fda approved.

### Claimed, not confirmed
- The check is non-required in branch protection: inferred from preview.yml's comments (`preview` is the required check);
  repository settings were not read or changed.
- Checkout uses the PR head SHA, as preview.yml does, so an anchor broken only by the merge with main shows after merge,
  not on the PR.
- `tests.test_render_sweep_coverage` fails locally on main as well as on this branch (reviewer's run); not this PR's.
