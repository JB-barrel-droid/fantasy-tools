## 2026-10-25 - Deploy gate red on main: unwired render test (JEG-976 / JEG-1076)

Contract: `make validate` was failing on `main` (8d3958da) because `tests/test_v2_inputs_status_render.py`, added by #915 (JEG-1076), was named in no Makefile run list, and `tests.test_render_sweep_coverage` (added to `test-core` by #874, JEG-976) fails when any render module is unwired. Wire the module so the gate is green again.

### Verified (check named)
- On a clean worktree of `origin/main` 8d3958da, `python3 -m unittest tests.test_render_sweep_coverage` failed 4 of 4, with `test_v2_inputs_status_render: in no Makefile run list and not known red`.
- With one line added to `test-render-extra` in the Makefile, the same command passes (4 tests OK). That is the test that fails without the fix.

### Claimed, not confirmed
- `tests/test_v2_inputs_status_render.py` was not run in this session, so whether it is green is unknown. It is wired into `test-render-extra` (the daily non-blocking sweep), not into the blocking gate, the same way #874 wired the other 20 unverified render modules.
- `make validate` was not run locally on this branch; the `preview` check on the PR is the evidence.
- Follow-up for Jeremy: the coverage guard makes every new render test a deploy-gate failure until someone wires it, which is how this happened. Whether to keep that strictness or make it a warning is his call.
