# 2026-10-28 · Live fill-in peers (JEG-1201) · WIP

Branch `be/jeg-1201-live-fillin-peers`, off origin/main 759a4f9. Stopped early
(usage limit); no code changed yet. This entry is the handoff.

Decision (Jeremy, 2026-10-28): "Use fantasycalc and projections sources, those
should be refreshing at least daily, so they are good". Earlier: "Where there is
cross source dependency, we can lean on live sources so the trade charts are not
reliant on each other."

## Verified (check named)

- Baseline on main, `python3 -m unittest`: test_spec_reference_value_pipeline,
  test_value_pipeline_engine, test_value_reference_worked_example,
  test_promotion_model_parity, test_coverage_fill_in, test_player_scenario_matrix,
  test_superflex, test_short_chart_waiver, test_value_check, test_rank_guard,
  test_row_missing_reasons, test_published_league_settings_engine,
  test_rookie_bye_bump all OK. test_expected_starts_model.Live errors in
  setUpClass (missing params file; pre-existing, unrelated).
- Playwright is not installed here, so `value_check compare` cannot run.
- Code read: peers built at `pipelines/value_reference.py` ~921/953
  (`chart_peers`, `peers`), `_estimate` ~346; JS `chartPeersFor` /
  `estimateFor` in `app/trade-value-chart/assets/value-model.js` ~975;
  spec reference `pipelines/spec_reference/value_pipeline.py` `estimate_player`
  ~221 and `peers_all` ~862/891.
- Projection natives (`Setting.natives`) are per-game points; ESPN lists
  ineligible players at 0.0; the superflex overlay applies to charts only.
  The ratio path (sum chart / sum peer over the last 10 shared, times the peer
  native) works on points: the ratio is chart value per point.

## Claimed, not confirmed

- `PIPELINE_VERSION` "value-pipeline/2" has not been bumped for earlier value
  changes (JEG-969, JEG-1073); a bump makes value_check "incomparable" (no
  check). Lean: no bump.

## TODO (what's left)

1. Peers for chart c = FantasyCalc (unless c is FantasyCalc) + included
   projections, listed natives. Same in value_reference, value-model.js and the
   spec reference. Proposed: a `live` flag on chart inputs (FantasyCalc) to keep
   the engine source-neutral, or a LIVE_CHARTS constant.
2. Regenerate the worked-example expected estimates from value_reference and
   confirm the engine and spec reference reproduce them (house practice, JEG-1073).
3. New test: a weekly chart's estimate does not move when another weekly
   chart's values change (fails on the old rule).
4. Decide on ESPN 0.0 natives as peers (they pull the median down); report it.
5. methodology.md VP-2.4 and decisions.md entry.
6. Impact on the committed fixture, old vs new (Full PPR 12 1QB; Half, Standard
   12; Full PPR SF 12), to /mnt/project-files/ddf/fillin-peers-impact-2026-10-28.md.
   List a player only when the move is over 5% AND over 2 trade-value points
   (the published-value scale; Jeremy: "If the 5% only amounts to 1-2 trade
   value points, it's immaterial"). Header gives the count over 5% but 2 points
   or less, not listed. At most ~60 rows by absolute %.
7. Report only: chart_sigma (takes chart peers, ~925), DDF weights, and
   `unified.peer_natives` / `translate_ranked` peers (tests/test_short_chart_waiver.py).
