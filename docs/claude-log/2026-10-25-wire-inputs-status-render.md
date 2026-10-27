## 2026-10-25 - Wire test_v2_inputs_status_render so main deploys again (part of JEG-1073)

Contract: the Deploy dashboard run for 48313ba failed in `make validate` at `tests.test_render_sweep_coverage`: `test_v2_inputs_status_render` (added by #915) was in no Makefile run list. #874 (the coverage guard) merged after #915, so the two collided on main. The DDF Value change (#919) could not go live until main was green again.

Change: one line, `tests.test_v2_inputs_status_render` added to `test-render-extra` (the non-blocking daily render sweep, where #874 put the other render modules). No assertion changed.

### Verified (check named)
- `python3 -m unittest tests.test_render_sweep_coverage`: 4 pass after the line is added; the four failures in the deploy log were exactly this module.

### Claimed, not confirmed
- That `test_v2_inputs_status_render` itself is green: it was not run here (the guard only needs it wired). #915's description says it passes.
- That nothing else is red in `make validate` on main: the deploy log showed only this failure in `test-core`, but later steps of `make validate` (after test-core) did not run in that log.
