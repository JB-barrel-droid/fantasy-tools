## 2026-10-28 - JEG-1201: hold-tolerance guard (WIP, stopped early)

Contract: a guard in PR CI that runs the live-page and whole-fixture checks
(superflex live page, rank guard, week history) with each source root held
the way `rebuild_comparison_chain.isolate_hold` holds it, so a test that
cannot cope with a held or lagging source fails in its own PR.

Stopped on the coordinator's word (usage nearly out). No code written yet:
this commit is the log only.

### Verified (check named)
- Nothing run beyond reading code and `python3 pipelines/sync_dashboard_artifacts.py`
  (rc 0, 2.6 s). That sync left generated churn in `dist/` and `app/` in the
  worktree; none of it is committed.
- No Chromium here (`PLAYWRIGHT_BROWSERS_PATH` empty, download host blocked),
  so every render check skips locally. Their results can only come from PR CI.

### Claimed, not confirmed (read from code)
- Roots: `value_check.SOURCE_DERIVED` = usatoday, fantasycalc, fantasypros,
  cbs, espn, cbsros, razzball. Chain hold mark: `validationHold`
  {reason "chain hold: review hold", week, root, stage} on each section and
  its `_adjusted`; no `hold_level`, so the page and reference treat it as red
  (hidden).
- Lag scenario to reuse: `tests/test_week_history.transition_overrides`
  (swaps 12-team natives to the saved prior week and sets the history index's
  served week; it clears holds, so the hold must be re-marked after it).
  Prior pattern for running checks on a held fixture:
  `tests/test_seeded_hold_build.py` (`STATIC_EXPORT_COMPARISON`, patching
  `test_superflex.FIXTURE`).
- Suspected latent bug, not yet tested: `tests/test_superflex.page_problems`
  skips only charts that are lagging (`own_week_reads`). A chart that is
  red-held but on the current week is hidden from `sourceMaps()` and would
  report "listed players not plotted". Needs a render run to confirm.

### TODO
- `tests/_hold_scenarios.py`: `held_fixture(fixture, root)` (isolate_hold
  mark, week labels back one week) and `held_overrides(root)` for the browser
  (transition_overrides + re-marked hold).
- `tests/test_hold_tolerance.py`: per root, Python checks (rank guard
  `check_fixture`, superflex `identity_problems`, value_reference compute and
  week view) plus render checks (`test_superflex.page_problems`,
  `test_rank_guard.order_problems`, `test_week_history.collect`).
- Fix any hold-intolerant check found, each with a test that fails without it.
- Makefile: add to `test-core` and one `test-core-shard-N`
  (`tests/test_validate_shards.py` requires both).
