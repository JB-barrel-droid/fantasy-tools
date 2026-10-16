# JEG-527 + JEG-534 remainder — 2026-10-16

## JEG-527: content-week reference agreement + 12-combo sweep

**Verified:**
- Extended `value_reference.settings()` with a content-week case (`ppr/12/sf0` at `content_week=9, objective=regular`).
- Extended `value_check.py` ENGINE_JS to reset lineup settings to defaults between combos and apply any `lineup` overrides (content_week, objective, etc.).
- `value_check compare --strict --rerun-engine`: **agree**, 1,196,179 values compared (up from 852,906), 0 mismatches across all 25 settings including the content-week case.
- `test_bench_share_readout_matches_reference`: 3 passed, 16 subtests passed (includes content-week case at line 40).
- 12-combo sweep (`test_published_league_settings_render`): 2 passed, fixedPieIndexed PASS.
- Guard harness: PASS.

**DDF Value unchanged** (no engine math change; the content-week setting exercises existing paths at different parameters).

## JEG-534: G6 re-point + lineup signal

**G6 re-point:** `score_lineup_values.render_report` now leads with projected-start calibration (MR-23: the share predicts whether the weekly projection puts a player inside the starter count, not whether he finishes there on Sunday). Realized-finish calibration kept as legacy secondary.

**Lineup signal (MR-23 option (a)):**
- Created `config/lineup_signal.json` (schema `lineup-signal/1`) with per-position pair swap rates, weeks-any rates, and starter weekly projection spread from `tools/weekly_matchup_swaps.py` (2018-2025, PPR, 12-team).
- `sync_dashboard_artifacts.py` copies it to `dist/assets/lineup-signal.json`.
- `curve-widget.js` loads it at init and exposes `getLineupSignal()` on TradeValueCurveControls. Display only; no value calculation change.

**Not built:** options (b) and (c) per MR-23 recommendation.
