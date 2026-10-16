# JEG-527 (part of): season week inputs in Edit league (2026-10-15)

Slice 1: Edit league gets "Season weeks" (week the values are for, last regular-season week, playoff weeks, optimize for); the content week is settable; share links carry non-default weeks. Engine math (window, byes, drift, playoff injury rate) is unchanged; v2 only collects inputs (app/v2/v2.js, curve-widget.js).

Verified: tests.test_v2_season_weeks_render (2 pass); make sync clean after re-merging origin/main.
Not clean, pre-existing on main (checked in a clean origin/main worktree): tests.test_asset_load_retry (2 fail, wall-clock week 6 vs build week 5); tests.test_bench_share_readout_matches_reference (16 fail on main, 17 here: my new contentWeek case fails the same engine-vs-reference gap); value_check compare reports ddf_value_charts_prior availability gaps. DDF Value not touched; 12-combo sweep not rerun (no engine math change).
Left: reference agreement for the content-week case waits on the main reference drift fix; JEG-534 first slice separately.
