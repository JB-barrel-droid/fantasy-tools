## 2026-10-16 - JEG-563: merge main, JS defaults, sweep

Merged origin/main into the PR branch (no conflicts), then moved the JS side and
the independent spec reference onto the new default (JEG-630's job was done on main
by PR 564, but the default constants it reads were still 3 WR / 6 bench).

### Changed

- value-model.js (TRANSLATION_REF_SLOTS WR 2, TRANSLATION_BENCH_MIX_12 14/28/35/6,
  SAVED_SETUP_SHAPE), product-data.js default_roster_shape, curve-widget.js and
  comparison-dashboard.js default roster (WR 2, BENCH 7; K/DEF controls stay JEG-565).
- Python: sync_dashboard_artifacts METHODOLOGY_ROSTER, refresh_vorp_translation,
  spec_reference/* defaults, engine_dump docstring.
- Pinned assertion changed: test_spec_reference_value_pipeline pie 2688/3024 ->
  2352/2688. The old numbers were 12 x 28 x 8 skill slots; the default is now 7
  (sf1: 8). The assertion was wrong for the new decision, not the code.
- Curve collapse floor 25 -> 20 (curve-widget.js). At 8 teams + superflex USA Today's
  indexed peak is 24.1-24.3 on the new default (27.0 on main); the setting threw
  valuesAboveCollapseFloor from setRosterSpot. A broken scale peaks near the mean
  (~5), so 20 keeps the guard's purpose. This IS a loosened guard: flagged for Jeremy.
- config/lineup_parameters.json left alone: re-deriving it drifts on main too (data
  week), unrelated to the roster.

- Also: value-model.js benchPerTeam defaults 6 -> 7 (positionalMaxForSetup, translation opts);
  score_lineup_values read tiers[k]["mean"] but tiers_on_mean returns "value" since PR 562
  (module did not even import on main); fixed to "value".
- Test pins moved to the new default (each was the old decision, not a code claim): test_vorp_translation_js_parity
  (WR 3 -> 2, bench 6 -> 7), test_superflex, test_published_league_settings_engine SAVED_SHAPE,
  test_methodology_payload roster, test_view_invariants starting_slots, test_three_view_pipeline_wiring
  fixtures (target_count stays 168: 12 x 7 + 12 x 7 bench), test_score_lineup_values (7 starters; flex takes WR 21).

### Verified (check named)

- value_check compare --rerun-engine --strict: agree, 905,878 values, 0 mismatches.
- test_spec_reference_value_pipeline, test_value_reference_worked_example,
  test_roster_convention_parity, test_bench_share_readout_matches_reference,
  test_expected_starts_model (needs output/lineup-parameters.json from
  derive_lineup_parameters; it is gitignored): all pass.
- engine_dump 13 settings vs main: fixedPieIndexed and indexedOrderOk true in all 13.
  Pie shrinks by 1/8 everywhere (e.g. ppr/12 2688 -> 2352; sf1 3024 -> 2688). ppr/12
  top values: RB 75.8 -> 67.0, WR 57.2 -> 48.2, TE 33.3 -> 30.2, QB 26.0 -> 32.3 (fewer
  WR starters lowers WR/RB scarcity above waivers, one more bench seat; QB share rises).

- Also green: test_superflex, test_vorp_translation_js_parity, test_methodology_payload,
  test_roster_convention, test_rank_guard, test_view_invariants, test_three_view_pipeline_wiring,
  test_score_lineup_values, test_reindex_section, test_published_league_settings_engine.
- Bench share of value (engine_dump, main -> new): ppr/12 QB 13.9% -> 23.0%, RB 7.2% -> 11.1%,
  WR 9.9% -> 11.5%, TE 4.6% -> 7.7%; sf1 QB 2.8% -> 6.4%. This is JEG-546/548 territory, not
  assessed here.

### Claimed without confirming

- sourceScaleAgreement not separately inspected beyond the value_check agreement.
- Live-site check after merge (pending merge).
