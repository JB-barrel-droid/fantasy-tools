## 2026-10-29 - JEG-1049 edge drift workflow (daily plus on demand)

Contract: add the workflow that runs the merged edge drift checker (`tools/edge_drift_check.mjs`, #1111 / JEG-1256) against production once a day and on demand. Jeremy picked "A" (daily plus on demand) at 22:08 UTC. Read-only: no secrets, no deploy, no Supabase writes.

- `.github/workflows/edge-drift-check.yml`: `schedule` 12:40 UTC daily plus `workflow_dispatch`; `permissions: contents: read`; checks out the triggering commit, runs the checker on Node 22, keeps its exit code (0 in sync, 1 drift, 2 could not compare) and writes the verdict and output to the run summary. A red run is a warning; nothing else waits on it.
- `tests/test_edge_drift_workflow.py`: pins the two triggers, the read-only permissions, no `secrets.`/deploy/Supabase CLI text, and runs the step's real script against closed local ports, which must exit 2 with a "Could not compare" summary.
- `Makefile`: the new test runs in `test-unit-modules` next to `tests.test_edge_drift_check`.
- `config/monitoring_coverage.json`: the workflow is listed under `unmonitored_workflows` (informational, gates nothing), as `full-suite.yml` is.

### Verified (check named)
- `python3 -m unittest tests.test_edge_drift_workflow tests.test_edge_drift_check tests.test_monitoring_coverage tests.test_workflow_script_paths`: OK.
- The exit-code test fails when the step's last line is changed to `exit 0` (0 != 2), then passes when restored.
- Without the manifest line, `tests.test_monitoring_coverage` fails with "edge-drift-check.yml: workflow is not in config/monitoring_coverage.json".

### Claimed, not confirmed
- `make validate` here stopped at `tests.test_week_history` because this cloud sandbox has no Playwright (`ModuleNotFoundError: playwright`), unrelated to this change; the preview CI run is the gate.
- Behaviour on the real production endpoints is unconfirmed: the first scheduled or manual run after merge is that proof. A red first run would mean production is behind main (a redeploy is Jeremy's call) or unreachable from GitHub runners.
- #1003 (`cma/JEG-1049`) is now superseded by #1111 plus this PR; closing it is Jeremy's call.
