## 2026-10-12 - JEG-608 stale tests after JEG-508

Contract: retire or rewrite the tests JEG-508 (#491, #532) left stale; delete only where the behavior was deliberately retired; check the VORP copy and review_candidate failures. Triage found the six files named in the task already pass except `test_review_candidate`; the ticket's own list was the real set of failures.

### Decisions per test
- `test_public_copy_no_vorp`: real defect, code fixed. `seriesField` in curve-widget.js held two `"vorp"` literals, against the JEG-225 rule that the literal appears only in `VIEW_MODE_ORDER`. Now reads `VIEW_MODE_ORDER[1]`. Test unchanged.
- `test_review_candidate` (usatoday explicit zero anchor): the test's demo candidate omitted `value_provenance: "published"`, so reindex took the legacy per-position branch and dropped chart-only players (Mixon, Hill). Real candidates carry it (build_comparison_source_section.py). Test fixed, not the data.
- `test_lock_revert_notice_render`: rewritten. The default lock is DDF Value (VP-7.4, JEG-508), not "ESPN adjusted". Also fixed the doubled caption "locked to DDF Value value" in `lockLabel` and pinned its absence.
- `test_source_combo_contract`: rewritten. `extract_function` lived in `test_two_tier_frontend.py`, deleted by #491; inlined. Mock now maps `*_adjusted` to the raw section like product-data.js `rawSourceKey` (the `*_adjusted` sections are gone from the data, #532).
- `test_jeg38_raw_vorp_sources`: group label rewritten to "Projections (VORP vs waivers)" (copy rule). `WidgetSourcePurityTest` (4 tests) deleted: `vorpPricedRows` was deleted by #491; raw VORP is now computed by the value pipeline.
- `test_chart_kdst_positions_and_view_wiring`: wiring pins rewritten to `seriesField` / `seriesValuesFrom` / the new `setViewMode` activation line. Two tests deleted: `test_agreement_check_reads_indexed_units` (the anchor-band agreement check is retired, GAP-026 2026-10-08 and test_source_scale_agreement_retired) and `test_vorp_view_resolves_via_player_keys` (the `vorp_views` lookup no longer exists; VP-11 reads pipeline fields).
- `test_below_leg_zero_render`: rewritten. The rule (a projected player is never "—") still holds, but JEG-508 prices every projected player as a native, so the `buildLegFloors` display patch and its "below-leg player in the data" precondition are gone. New expectation comes from #players-data projections only. Two mutations (drop low projections; CBS ROS prices no QB) are caught.
- Already green on current main, no change: `test_vorp_translation_unified`, `test_math_inspector`, `test_review_batch70_views`, `test_view_invariants`, `test_published_league_settings_render`, `test_espn_zero_badge_render`.

### Verified (check named)
- Each touched file run with pytest: all pass (see the PR for the make validate result).
- `test_below_leg_zero_render.test_guard_fails_on_broken_builds`: both mutations fail the render check; the unmodified widget passes.

### Claimed, not confirmed
- `test_jeg68_starter_markup` / `test_jeg69_direction_check` from the ticket list: no test by those names exists on main; `starterMarkupSane` only appears in `test_published_league_settings_engine`, which was not in the failing set.
- Main-branch trigger on preview.yml (ticket "also consider"): not done here.
