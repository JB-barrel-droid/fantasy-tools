## 2026-10-26 - JEG-1118 v2-render on data pushes to main

Contract: run v2-render on pushes to main that change the baked data (Jeremy, 2026-10-26: "Run it on push to mains that affect the data"), so a bad bake is caught in minutes. Warn only; never hold a data refresh.

### Verified (check named)
- Path list: `git show --stat` of b227f453, 9c15530f and 53155f2e, and the commit step of `.github/workflows/rebuild-chain.yml` (`git add` list). The bake changes `data/fixtures/current/*`, `data/ddf-two-tier/*`, `data/inputs/*`, `config/lineup_parameters.json`, plus monitoring output under `dist/modules`, `output/` and `data/history` that the render test does not read. The filter keeps the four paths the page is built from.
- Bot pushes do not fire `push` workflows: rebuild-chain.yml pushes with `git push` under `GITHUB_TOKEN` (no PAT; its own JEG-274 comment says so, and it dispatches pages.yml for that reason). So the chain now also dispatches v2-render-test.yml (`workflow_dispatch`, allowed for GITHUB_TOKEN; the job already has `actions: write`). No new secret.
- `python3 -m unittest tests.test_v2_render_runs_on_data_push` passes (8 tests). The same file run against `origin/main` copies of the two workflows fails (`test_real_files_pass` and 4 mutation checks), so it fails without the change.
- Pinning tests still pass: preview_workflow_matches_pages, gha_schedules_pg_cron, workflow_dispatch_permissions, no_failopen_workflows, rebuild_chain_* (94 tests, OK).

### Claimed, not confirmed
- That GitHub fires the dispatched run on a real chain push: only observable after merge, on the next chain push.
- Red run surfaces in `dist/modules/github-actions.json` (all workflows, last 5 runs, failing_streak at 3) and so in Ops status; I did not change those workflows.
