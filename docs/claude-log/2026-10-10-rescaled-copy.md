## 2026-10-10 - JEG-510 rescaled copy

Contract: replace "as published", "published chart" and "indexed" (as a label) with "rescaled" in app/v2 copy; group name "Trade charts (rescaled)". Copy only; internal keys and method ids (`indexed`, `is-indexed`) unchanged. (`docs/claude-log.md` is the frozen archive; this file is the entry.)

### Verified (check named)
- New `tests.test_v2_rescaled_copy` (added to `make test-core`) scans app/v2 string literals and shell.html text for the old labels: clean now; `test_guard_fails_on_old_labels` restores 8 old labels one at a time and the scan flags each.
- Render suites pass after the change: test_v2_compare_render, test_v2_how_render, test_v2_risers_render, test_v2_targets_render, test_v2_states_render, test_v2_contract_render, test_espn_zero_badge_render.
- Tests edited ONLY because the pinned string is what changed (not to go green): test_v2_how_render (mutation anchor `Source-relative index` heading), test_v2_contract_render (`Published chart` column), test_v2_states_render, test_v2_risers_render (group name), test_v2_panels_render (group label), test_v2_targets_render (caption, `Wk N · rescaled`, ⓘ text, subtitle).
- Pre-existing failures reproduced on unmodified main (296acd62), so not caused by this change: test_v2_ux_render (390px "How values work" hit area 43x44), test_v2_panels_render (1440px horizontal scroll 25px, same figure before and after), test_espn_listed_rows and test_bench_share_low_pie (playwright wait_for_function timeouts in the pre-fix-widget mutation tests). The last two sit in `make test-core`, so `make validate` is red on main in this environment before reaching the later suites; the remaining test-core and test-integration commands were run individually and passed.

### Claimed, not confirmed
- Legacy dashboard (app/trade-value-chart: comparison-dashboard.js, curve-widget.js, index.html) and pipelines/lib/dataset_status.py still say "as published"; outside the app/v2 scope and the back-end lane, not changed. The ESPN-zero badge title (product-data.js, shown in v2) was changed.
- Scale anchor (ESPN vs DDF) is no longer described in the ⓘ text (JEG-499); not re-checked in the values explainer.
