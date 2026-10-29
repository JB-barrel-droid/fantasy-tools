## 2026-10-29 - JEG-1178 week selector, taken over from the Codex/fe-pc lane (PR #1012)

Contract: finish PR #1012 (site week selector) to the ticket's Next and Done-when, on the same branch
(`fe/jeg-1176-week-selector`) with a normal main merge. No value math, Supabase, deploy or merge.

### What changed
- Merged `origin/main` (5c07ad67) into the branch; no conflicts.
- `tests/test_week_stale_deadline.py` (new, no browser): `pastThursdayNoon` with both clocks pinned per
  case, around Thursday 12:00 CT in daylight time (week 8, 2026-10-29) and standard time (week 10,
  2026-11-12, after the 2026-11-01 change), the day-pin fallback, the instant winning over the day, and
  four mutations (UTC instead of Central, noon counted as past noon, Friday instead of Thursday, day pin
  read as end of day) that each must turn a case red. New `stale` command in
  `tests/source_freshness_harness.js`; a case with neither clock pinned exits non-zero.
- `tests/fixtures/week_state_vectors.json`: 40% (2 of 5, stays on N) and 60% (3 of 5, moves to N+1)
  cases, checked by `tests/test_week_state.py` against both `value-model.js` and `pipelines/week_state.py`.
- Wiring: `make test-unit-modules` runs the new test. `v2-render-test.yml` (the front-end merge check,
  Chromium installed) now runs `tests.test_week_stale_deadline` and `tests.test_week_selector_render`, so
  the 390 and 1366x768 selector checks run on every front-end PR, not only in the off-PR full suite.
  Its timeout went from 25 to 35 minutes (the run was about 13 minutes before).

### Verified (check named)
- `python3 -m unittest tests.test_week_stale_deadline`: 2 tests OK (16 boundary cases, 4 mutations caught).
- `python3 -m unittest tests.test_week_state`: 9 tests OK with the two new vectors.
- `tests.test_ci_speedup_workflows`, `tests.test_v2_render_runs_on_data_push`, `tests.test_no_real_clock`,
  `tests.test_source_freshness`, `tests.test_render_sweep_shards`, `tests.test_validate_shards`: OK.
- `make validate`: see the PR description for the result on this head.

### Claimed, not confirmed
- `tests/test_week_selector_render.py` (0/43/57/100% at 390 and 1366x768, contributed-week labels,
  stale badge, Compare fit, wk= round trip) was not run here: this cloud box has no Playwright Chromium.
  The previous owner reported it passing on their PC on bdf44906 (Linear comment, 2026-10-29 01:48 UTC);
  no CI job ran it before this change. The first v2-render run on this head is the check.
