## 2026-11-03 - Current-main release preparation / JEG-1481

Contract: resume the existing isolated page lane on Jeremy's coordinator
instruction, normally integrate current main, run focused checks, and prepare
exact-head CI without overlapping the active PR #1174 release suites or main
rebuild. Same owner and branch `fe/JEG-1195-versus-vegas`, same PR #1294.
No source activation, shared live-route wiring, PR merge, deploy, Supabase,
deletion, credentials/access changes or retries of denied Linear writes.

### Verified (check named)

- Live ownership/head checks: remote and local prior head were
  `947b7233dc0897b3a5722c4a799863309813743c`; PR #1294 was open and ready,
  with no active lane runs or competing claim in the read-only ticket/PR
  history. Current main was `237e685c98e8a3de7f3f1508ccfe8a22c68145e6`.
  Current main's `AGENTS.md` was read. Linear writes were not retried.
- Live release capacity check: PR #1174 at
  `6f59a94a6ec1f9834999f489e3c76d17c4d189e5` had active preview run
  41737320284 and render run 41737320320; main rebuild run 41735589614 was
  also active on 237e685c. No extra broad verification was dispatched.
- PR #1294 was converted to draft before the integration push, so its
  expensive preview/render jobs remain deferred while release capacity is
  occupied. The conversion's cheap draft checks completed before push;
  no active lane run was cancelled.
- `git merge --no-ff origin/main` succeeded without conflicts, producing
  merge commit `206ef76adcd845aae44d33ab7dd4017d2fdd0acb` with parents
  947b7233 and 237e685c. It brings in only main's existing monitoring/chain
  artifacts. `git merge-base --is-ancestor 237e685c HEAD` passed. A scoped
  diff from 947b7233 confirms no change to the isolated app, adapter or tests.
- `python3 -m unittest tests.test_pipelines_import_standalone tests.test_weekly_inputs_contract tests.test_build_weekly_inputs tests.test_versus_vegas`:
  110 tests passed in 5.898 seconds on the integrated tree. Includes the
  relocated-checkout import guard and its deliberately broken-import negative
  control, clean-interpreter regression, wrong-source/ROS refusals, raw-rank
  protections, missing/partial/unresolved rows, identity and real producer CLI
  to preview CLI integration. Receipt: `/tmp/jeg1481-release-focused.log`.
- `node --check app/versus-vegas/view.js` and `git diff --check` passed.
  No broad local suite, sync/build or browser-download attempt was made.
- Prior head 947b7233 had full green preview/render CI and 17 focused CI
  tests. The coordinator reported its independent delta review passed by
  inspection with no actionable findings; that reviewer did not independently
  run tests or submit a formal GitHub approval. Those receipts stay scoped
  to the prior head, not this integration head.

### Claimed, not confirmed

- New-head focused/browser CI is prepared by the normal draft push and its
  exact head/run/result will be recorded in PR #1294 and the handoff. Local
  rendered checks remain subject to the previously missing Chromium binary;
  its denied download was not retried.
- Full release verification is deliberately pending the serial capacity gate:
  let PR #1174's preview/render runs and the active main rebuild finish;
  re-read current main and this PR's head/ownership. If main advanced, merge
  it normally and rerun focused checks. Once stable, mark this same PR ready
  once to trigger full exact-head preview/core/render CI; do not duplicate it
  with a manual broad dispatch.
- Require the appropriate independent review receipt for the final integrated
  head after its required CI is green. No earlier-head review or CI is
  represented as current-head approval. Merge/deployment remain outside this
  task. Runtime data activation, verified-play compute and shared live-route
  integration are distinct downstream gates, not silently completed here.

### Follow-up main refresh in this preparation session

- Main advanced during the initial draft push to
  `66f784177afcd3bf1a9e941a8cfd37b7cf66ba0e`, an automated chain-status
  commit with the message `chain failed; fixture not updated`. Read-only
  metadata confirms rebuild run 41735589614 completed with failure. This
  operational result is not repaired or waived by this isolated page lane.
- The initial integrated draft head
  `f6b99d68dc58bf60ad0247c5f2709edcef6c4a47` passed its dedicated focused
  workflow 41737863934. Its required broad aggregators report the expected
  draft deferral, with expensive jobs skipped, not a full verification pass.
- Normally merged that newest main as well, producing
  `225fbbdcb7e7247ce58a34301ceb4081f83011c7` (parents f6b99d68 and
  66f78417). This adds only the four already-committed chain-status/monitoring
  artifacts from main; no source or fixture update is invented.
- Repeated the same focused command after this meaningful base change:
  all 110 tests passed in 6.202 seconds. Node syntax and diff checks passed.
  Receipt: `/tmp/jeg1481-release-refresh-focused.log`.
- The final documentation commit records these results without changing the
  isolated view, adapter, tests or shared live-route files. Exact final head
  and focused CI receipt will be in PR #1294 and the handoff. Full suites stay
  deferred until PR #1174's active release verification finishes and the
  coordinator rechecks main stability; no duplicate broad dispatch or idle
  model wait is started.
