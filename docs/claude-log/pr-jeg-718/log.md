## 2026-10-19 - JEG-718 / JEG-725: local render-red triage, cluster 1 (fixtures and test premises)

Contract: find the root cause of each locally red v2 render module on origin/main e5822d2c and fix it without loosening an assertion.

### Findings
- Fresh worktree: committed `dist/` has no `dist/v2` (GAP-APP-ASSETS-LAG). Modules that never call `_render_env.ensure_built()` (chart_fit, names, player_tags, risers ... ) serve a 404 until `make sync` ran. Environment, not code. Running two modules in parallel races the sync (rmtree FileNotFoundError, JSONDecodeError): run them one at a time.
- Held-state drift (fixture): the live fixture on 2026-10-19 holds espn, fantasycalc, razzball, cbsros and cbs. chart_fit, compare, ddf, ddf_versions (uses ddf_render's server), player_tags (uses names_render's server), risers and states did not pin holds, so their premise (ESPN on the legend, a DDF Value that drops with ESPN, a projection series, rows for the projection rise/fall) failed. Fix: `pin_holds_in_dist` (tests/_holds.py, the JEG-675 convention) in each module's own copy of dist.
- player_tags, states (real test bug): the test clicked the middle of the first row, which since JEG-457 is a chart value cell that opens its math tip and stops the click, so the drawer never opened. Product behavior is by design; the test now clicks `td.player`.
- chart_fit "padding dropped" not caught (JEG-725): the default rank window's extremes never sit within 4% of a tick step, so the mutant gives identical ticks. The guard was not discriminating. The test now sweeps 24 rank windows and fails if none is sensitive to the padding. Negative test: with `pad = 0` patched into v2.js the guard subtest passes (mutant caught); the unpatched build is clean.
- phone_fallback_font: macOS has no DejaVu Sans, so the forced "wide" face is not wide and the guard's `'#manifesto' not found in {}`. The test now probes the face and skips locally (an error under RENDER_TESTS_REQUIRED=1). CI (Ubuntu) has DejaVu.
- JEG-725 Q2: CI's "v2 render test" workflow runs only `tests.test_v2_contract_render` (PR only). It does not run chart_fit, player_tags, states, panels etc. so green there says nothing about them. `make validate` / pages.yml list more (see Makefile), pages.yml is the deploy gate. Browser version was not the cause of any failure above.

### Verified (check named)
- Each module run alone with `python -m pytest tests/test_v2_<m>_render.py` after `pipelines/sync_dashboard_artifacts.py`: chart_fit, compare, ddf, ddf_versions, player_tags, risers, states pass; phone_fallback_font skips locally.

### Claimed, not confirmed
- That the DejaVu probe returns true on Ubuntu CI (not run there).
- Not in this PR: panels, targets, waterfall (separate clusters).
