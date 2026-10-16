# JEG-526 and JEG-529: stash signals outside the pie (2026-10-12)

Built `pipelines/stash_signals.py` (Python reference), `config/handcuff_jump.json`
(written by `tools/handcuff_jump.py --config`) and `tests/test_stash_signals.py`.
Nothing touches value_reference.py, the engine, DDF Value or Indexed.

- JEG-526: contingent = (1-b) m_lead (1-m_i) (promoted - w)+ P(promoted > l) for each
  team's depth-2 back. Promoted level = measured multiple of the setting's starter
  line (1.22x behind a top-12 lead back, 1.19x otherwise). Week 5 ppr/12 ESPN: Vaki
  0.54 points per week (own P(start) 0.00 -> stash signal 0.08), Hill, Ty Johnson alike.
- JEG-529: per position, best free-agent option and top-3 mean vs each bench
  player's hold value; drop_candidate flag, display only.
- Verified: tests/test_stash_signals.py (11 pass); the pie-unchanged test compares
  every row's DDF value before and after a build.
- Claimed, not verified: the 12-combo sweep (no engine file changed, so not run);
  `make validate` has 16 failures in tests/test_bench_share_readout_matches_reference.py
  (JS readout vs Python reference, QB differs by 0.0014) that do not involve any file
  in this diff; treated as pre-existing after JEG-562 landed.
- Open: drawer display ("If his starter misses: ...") is front-end (v2.js). Depth chart
  data is thin (32 teams have RB1/RB2 orders) and stale in places (guarded by the
  projection check). Lead back already out (IR) is not modelled.

## Merge note (2026-10-15)
- Dropped the incidental regeneration of `config/lineup_parameters.json` (sigma values) from this slice; main's version kept, so the pie and DDF Value are untouched (ddf-group-vorps total_vorp 3063.8466 unchanged).
- Verified: `tests.test_stash_signals` (11 ok). Not green: `make validate` stops at `tests.test_asset_load_retry` (2 failures, "not yet published for week 6"), which fails identically in ~/code/fantasy-tools, so pre-existing. `value_check compare --strict` reports disagree in this worktree for held sources; unrelated to this diff (no engine or DDF config changes). Claimed, not confirmed: the 12-combo engine_dump sweep was not run since the diff changes no engine inputs.
