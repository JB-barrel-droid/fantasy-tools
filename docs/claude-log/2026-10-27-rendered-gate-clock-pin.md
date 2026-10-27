# 2026-10-27: pin the rendered gate's page clock to the data's week (JEG-1152)

Session: mac-mini/claude-code/3c99fe67 (Ba-Nana run). Branch
`banana/fix-main-rendered-gate-clock`.

## Why

After d377e659 (engine promotion model matches the reference), pages.yml run
40465821362 passed `make validate` and failed in the rendered gate:
`gate_flexibility.mjs` `chooseLockOrder` timed out ("did not find some
options" on `#curveLockOrder`). The Node gate scripts load the page with the
real clock. From the Tuesday week-8 flip until week-8 charts publish, the page
drops every chart as not yet published, so the lock order the gate returns to
is not one of the offered options. This is the same unpinned clock that #979
fixed for the Python render tests.

## Change

- `tests/rendered_gate/{gate,gate_flexibility,bench_share_readout_harness}.mjs`:
  when `TRADE_VALUE_TODAY` is set, add an init script that sets
  `window.TRADE_VALUE_TODAY` (as `_render_env.pin_data_week_script` does).
- `pages.yml`, `preview.yml`: the rendered-gate step sets `TRADE_VALUE_TODAY`
  from `tests.test_week_history._fixture_today()`.

## Verified (check named)

- `node tests/rendered_gate/gate_flexibility.mjs dist` on the local build,
  real clock 2026-10-27: exit 2, the same TimeoutError as CI. With
  `TRADE_VALUE_TODAY=2026-10-26` (the `_fixture_today()` value): exit 0.
- `gate.mjs` and `bench_share_readout_harness.mjs` with the pin: exit 0.

## Claimed, not confirmed

- pages.yml green on main after merge: see the PR and the Linear comment.

## Process note

Before this, a `git push origin banana/fix-main-bench-share` from this worktree
went to `main` (the branch's upstream was `origin/main` with
`push.default=upstream`), landing d377e659 on main without PR checks or the
merge lock. It was a fast-forward, nothing was overwritten. Push with an
explicit `HEAD:refs/heads/<branch>` refspec.
