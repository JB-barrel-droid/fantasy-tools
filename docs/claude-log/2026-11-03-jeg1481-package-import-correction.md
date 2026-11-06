## 2026-11-03 - Package import correction / JEG-1481

Contract: advance PR #1294 to full CI on the coordinator's instruction after
reported re-review passed for `e8289b5729723c249ec57802bcd3589aa4c2d7ab`.
Existing runs were completed; seven PRs were ready, leaving one slot under
the ready-PR cap. Marking this PR ready started preview run 41658804160 and
render run 41658804328 at the same head, with no duplicate dispatch.

### Verified (check named)

- Preview run 41658804160 completed `preview-build` successfully: the job's
  `make validate-base` step covers reference/sync, guard harness, strict value
  comparison and integration checks. Shard 2 failed during `make test-core-shard-2`
  with exit 2. Its annotations did not identify the failing assertion. At the
  time of diagnosis the other core shards and render groups were still active.
- Local isolated import `python3 -I` with only the checkout root on `sys.path`
  failed to import `pipelines.build_versus_vegas`: `ModuleNotFoundError: lib`.
  The new test `test_imports_as_package_with_isolated_python_path` failed before
  the fix with that error. Existing `test_pipelines_import_standalone` runs in
  core shard 2, making this a possible cause of that failure, not a confirmed
  attribution without the detailed CI log.
- The adapter now uses `.lib.weekly_inputs_contract` when imported as a package
  and `lib.weekly_inputs_contract` when executed directly as a CLI. No path or
  environment mutation, skipped test or weakened assertion was added.
- `python3 -m unittest tests.test_pipelines_import_standalone tests.test_weekly_inputs_contract tests.test_build_weekly_inputs tests.test_versus_vegas`:
  110 tests pass, including the existing relocated-checkout import guard and
  its negative control, the new isolated-import regression, and both real CLIs.
  Receipt: `/tmp/jeg1481-import-correction-tests.log`.
- The correction is limited to the adapter, one regression test and this log.
  No source activation, runtime writer, live route, pricing, Supabase,
  credentials, production data, merge or deploy actions were taken.

### Claimed, not confirmed

- Exact corrected-head CI and review are pending. The coordinator's earlier
  re-review receipt applies to e8289b57 only. Results for this correction will
  be recorded on JEG-1481 and the PR.
- Detailed CI logs and uploaded screenshots remain inaccessible via previously
  denied download hosts; no retry or bypass was attempted. The exact root of
  the old-head shard failure is not claimed.
- Active old-head runs are allowed to finish before pushing, to avoid triggering
  their configured concurrency cancellation. Data-source activation,
  verified-play compute and shared live-route integration remain separate gates.
