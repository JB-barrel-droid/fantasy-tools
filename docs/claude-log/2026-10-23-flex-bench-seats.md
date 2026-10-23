# 2026-10-23: MR-28 flex_bench_seats implementation

## What
Implemented `flex_bench_seats` flag (off by default) across all three engines
(Python reference, JS browser engine, spec reference). When on, bench-seat
weights count superflex+flex starters, matching the ES model's
`allocate_league()`. This changes QB from ~15 bench seats to ~4 in canonical
12-team 1QB.

## Verified
- 22 engine parity tests pass (including 3 new flex bench seat tests)
- 23 spec reference tests pass
- 12-combo sweep: fixedPieIndexed passes all 13 settings
- Spec/JS parity confirmed via test
- Flag OFF does not change any value (test_flex_bench_seats_off_matches_default)

## Not verified
- `make validate` not re-run for this commit (only engine/spec tests run)
- Headless browser sweep not re-run (flag is off by default, no shown value changes)
- Full `value_check compare` not re-run

## Commit
`720f9652` on `research/JEG-969-bench-share`, PR #867

## Files changed
- `pipelines/value_reference.py`: bench_seats, allocate, chart_sigma, run_pipeline, Setting, compute
- `app/trade-value-chart/assets/value-model.js`: vpAllocate, esChartSigma
- `pipelines/spec_reference/value_pipeline.py`: dhondt_bench, allocate, es_chart_sigma, run_week, run
- `tests/test_value_pipeline_engine.py`: TestFlexBenchSeats class (3 tests)
- `tests/test_spec_reference_value_pipeline.py`: mock accepts **kwargs
- `tests/value_pipeline_driver.js`: --flex-bench-seats / --no-flex-bench-seats
- `tools/bench_research/flex_bench_sweep.py`: 12-combo sweep script
