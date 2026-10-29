## 2026-10-29 - JEG-1276 bench-decay evidence benchmark and decision memo

Contract: replay the committed bench-decay research (post 1 / #846, JEG-943 /
#847, JEG-528 / #604) from a fixed manifest, offline, and write a memo that
separates measured, historical and hypothetical results and ends with the
question for Jeremy. No engine, spec, reference, Supabase or value change.

This entry sits here, not in `docs/claude-log/`, because JEG-1276 limits this
lane to four new paths. Move it on request.

### Verified (check named)
- Every manifest source matches its sha256 at baseline `430791c4`, and the
  four research JSON files and the JEG-943 plan are byte-identical to their
  merge commits (git blob compare against 35205b89 and b0a448b8).
- `python3 tools/research/bench-decay-evidence/bench_decay_evidence.py --check`
  passes: 81 rows, 10 gaps, outputs match a rerun.
- `python3 -m unittest tests.test_bench_decay_evidence`: 29 tests pass.
- Each guard is load-bearing: disabling the leak check, the future-date check,
  the horizon check, the hash check, or printing missing as 0 each makes at
  least one test fail (manual mutation run, file restored after).
- The #604 timing rule lines are present in `pipelines/value_reference.py` and
  `app/trade-value-chart/assets/value-model.js` at baseline.
- `objective_window("season", 17)` returns (18, 17), so the #604 factor stays
  at 1 at content week 17 (G10; read in `derive_lineup_parameters.py`).
- G2 to G5 read from `tools/research/bench_value_by_week.py` and
  `tools/research/breakout_rate.py` at baseline.

### Claimed, not confirmed
- No page reads timingValue or optionValue (rg over app/, mcp-server/,
  supabase/, tests/ at baseline; not checked on the live site).
- Engine numbers are from the 2026-10-23 capture; today's engine was not run.
- Which of post 1's two bench shares (10.0% vs 8.7%) holds today (G8).
