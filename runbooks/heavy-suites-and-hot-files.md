# Heavy suites on one machine, and the hot-file merge rule

From `AGENTS.md` ("Hot files and merge order"), restated as a runbook.

## Heavy suites: one machine at a time

The render tests, the contract test (`tests/test_v2_contract_render.py`) and the 12-combo sweep launch a headless browser and a local server. Several concurrent runs stall the machine (eight concurrent `make validate` runs did on 2026-10-12).

- Run heavy suites on one machine at a time, sequentially: the Mac or Linux CI, not a laptop with several sessions running.
- If `make validate` stalls, run the targeted suites for your diff plus `python3 -m unittest tests.test_<module>` for every test module you touched, and say so in the PR and the log.
- A render test needs a browser. It skips when none is installed unless `RENDER_TESTS_REQUIRED=1` (CI sets it).

## Hot files: one In Progress ticket at a time

`app/v2/v2.js`, `curve-widget.js`, `value-model.js`, `value_reference.py` (and its spec reference), `config/roster.json`, `config/lineup_parameters.json`, `pipelines/bake_players.py`.

1. Merge one engine PR at a time and re-run `make test-core` after each. Two PRs on `curve-widget.js` merged minutes apart broke deploys twice.
2. Merge `origin/main` into the branch (no force-push), then `make sync` and `make validate`. Value changes pair the JS, the Python reference and the spec reference on one branch, with `value_check compare` at 0 and zero rank-guard inversions ([sweep-and-rank-guard.md](sweep-and-rank-guard.md)).
3. Generated files (`dist/`, generated `app/` outputs, the fixture) are never hand-merged: after a merge, regenerate them with `make sync`.
4. Squash-merge as "JEG-xxx", then verify live when published output changed ([verify-live.md](verify-live.md)).
5. Lane order: back end engine, then the front end that depends on it, then copy.
