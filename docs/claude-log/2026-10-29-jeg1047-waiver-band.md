## 2026-10-29 - JEG-1047 projection waiver line becomes a 7-player band

Contract: Jeremy picked option A on the JEG-1047 research ("A", 2026-10-29).
Each projection source's waiver line at a position is the mean of the 7
players around the first non-rostered seat (indexes N-3 to N+3, clipped).
Charts keep the one-player line; the short-list fallback is unchanged. Bar: a
1 PPG change to the waiver-line player moves no other player at the position
by more than 1.0 point in that source's Adjusted value.

### Changed
- `pipelines/lib/roster_convention.py` `waiver_band_line` and JS twin
  `roster-convention.js` `waiverBandLine` (one definition, JEG-556).
- `pipelines/value_reference.py` `_waiver_value` (projection family only).
- `pipelines/spec_reference/value_pipeline.py` VP-2.3 line.
- `app/trade-value-chart/assets/value-model.js` `vpWaiverBand`.
- Python reference `_price` now records `unfunded_moved` as
  `{from, to, amount}`, the engine's shape, so the worked example can pin it
  (the band makes QB bench unfunded in the 2-team example).
- `tests/fixtures/value_pipeline_worked_example.json` regenerated from the
  reference (ES variants via `tools/worked_example_expected_starts.py`);
  hand-check constants in the reference and spec worked-example tests updated
  (rule changed by Jeremy).
- `docs/methodology.md` VP-2.3 and ES-3, the explainer template wording,
  `docs/decisions.md`, risk row GAP-WAIVER-LINE-ONE-PLAYER.

### Verified (check named)
- `tests/test_waiver_band_line.py`: band math, JS twin parity on 200 random
  lists, all three implementations call the band, and the 1.0 point bar on
  every projection source and position at ppr/12 and standard/8. With the
  `value_reference.py` change stashed it fails (worst 3.2, Razzball QB,
  standard/8); `test_band_beats_one_player_rule` also runs both rules.
- Worked example: engine, reference and spec reproduce the regenerated
  fixture to 1e-6 (`test_value_pipeline_engine`,
  `test_value_reference_worked_example`, `test_spec_reference_value_pipeline`).
- `make validate` (value_check compare, rank guard): see the PR.
- Before/after on the live fixture, reference, all 12 settings: DDF
  Projections moves at most 0.57 (standard/14), DDF Value at most 0.79
  (standard/8); at ppr/12, 24 of 739 DDF Projections values and 23 DDF Value
  values change, all at most 0.26, top QBs.

### Claimed, not confirmed
- The values explainer was not regenerated (`make values-explainer` needs
  Playwright, not installed here); only its template wording changed.
- No Supabase deploy is needed: get-values fetches the published
  `value-model.js` at runtime (read in the function source, not exercised).
