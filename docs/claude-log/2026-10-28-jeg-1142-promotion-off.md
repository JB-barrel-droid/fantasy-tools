## 2026-10-28 - JEG-1142 promotion/demotion model switched off

Contract: apply no role-change math to values (no bench promotion boost, no
starter demotion cut), per Jeremy's Linear comment of 2026-10-27 ("I don't want
a demotion penalty / promotion argument applied to anyone. We don't have a
basis for it yet."). Keep the starter/bench weighting. Redo of #999 on current
main (`be/jeg-1142-promotion-off-v2`, main merged in, no rebase).

### Verified (check named)
- `PROMOTION_MODEL_ENABLED = false` in value-model.js, value_reference.py and
  spec_reference/value_pipeline.py: `tests.test_value_pipeline_engine`
  (`TestPromotionModelSwitchedOff`) passes; with the engine switch flipped to
  true locally the module fails (9 failures, 1 error).
- `tests.test_spec_reference_value_pipeline`, `tests.test_value_pipeline_engine`,
  `tests.test_promotion_model_parity` (dormant model, both engines part for
  part) and `tests.test_rank_guard` pass locally.
- Before/after on the committed snapshot (Python reference, PPR/12, model on
  vs off), 1QB position totals: QB +3.4%, RB -1.7%, WR +0.7%, TE +2.3%;
  superflex: QB +2.5%, RB -2.7%, WR -0.2%, TE +1.5%. DDF Value top 24 keeps
  its order in 1QB. The top 3 RBs fall about 6.4% (Gibbs 79.49 -> 74.38),
  QB and TE starters rise about 4-5% (Allen 31.28 -> 32.81, Bowers 33.73 ->
  35.06), bench and depth players fall up to 23% (Allgeier 1.25 -> 0.97).
  Same numbers as #999's report.
- `app/values-explainer/reviewed.json` hashes updated; the explainer template
  never described the promotion model, so the narrative is unchanged.
- No edge function deploy: get-values fetches the published value-model.js at
  runtime (supabase/functions/get-values/index.ts, VALUE_MODEL_URL).

### Claimed, not confirmed
- `value_check compare` at 0 and `make validate`: need Playwright, left to
  preview CI on the PR.
- The "Bench players are options" copy (app/v2/shell.html) speaks of injury
  and role-change upside in general terms; it describes the bench share,
  which stays, so it is left as is.
- Health-check thresholds were tuned with the model on; not re-tuned here.

### Review follow-ups (T1 review, same PR)
- Re-froze `tests/fixtures/baseline_main_771c3422/` from this PR's engine (its
  README says a deliberate default-value change re-freezes it);
  `tests/test_basis_overrides_render.py` needs Playwright, so it is left to CI.
  Verified: the copied curve-widget.js equals the old copy byte for byte; only
  the switch lines in value-model.js differ.
- `test_python_reference_flag_on_equals_baseline` pinned to a day in the
  served week (`data_today()`) and asserts rows are priced; before, it priced 0
  rows and compared None to None. Verified: it fails with the Python switch
  on and passes with it off.
- Stale "on by default" comments updated in the engine, both references and
  `tests/value_pipeline_driver.js`.
