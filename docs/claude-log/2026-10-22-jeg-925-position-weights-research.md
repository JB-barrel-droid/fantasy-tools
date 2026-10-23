## 2026-10-22 - JEG-925 Research post: How position weights work

- Wrote research post 09 (`docs/research/posts/09-how-position-weights-work.md`) explaining the derivation of position weights from VP-2 through VP-5 (mixes, DDF weights, budgets), with a worked example using ESPN at PPR/12.
- All numbers recomputed from the Python reference (`pipelines/value_reference.py`, `Setting(Inputs.load(), scoring='ppr', teams=12, expected_starts=True).result()`) on the week 7 fixture. Eight-group sum verified = 1.0000.
- Sensitivity tables across 8/10/12/14 teams, PPR/Half/Standard, and superflex run from the same pipeline.
- Per-source mixes from all five included sources (FantasyCalc, CBS, ESPN, CBS ROS, Razzball).
- Drafted 120-word dashboard explainer; suggested placement in the v2 "How values work" tab.
- No code/doc disagreements found for the weight derivation itself. The methodology spec (VP-3, VP-4) matches both `value_reference.py:_mixes()` and `value_reference.py:ddf_weights()` and the engine's VP-4 block in `value-model.js`.
- Updated `docs/research/README.md` with post 7 entry.
- Verified: eight-group sum = 1.0, budgets = pie x weights, per-source group totals match code output. Not verified: approximate sensitivity percentages (2-3% per 1-point shift), 12-combo sweep not run (no engine code changed).
- Claimed, not checked: full `make validate` (no code changes, only docs).
- Jeremy decisions (2026-10-23): title is "How we split value across positions"; dashboard explainer goes as a collapsible section in the "How values work" tab, no separate card. UI implementation is a follow-up ticket under JEG-925.
