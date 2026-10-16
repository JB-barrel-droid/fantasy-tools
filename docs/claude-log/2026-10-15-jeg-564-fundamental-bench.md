# JEG-564: Fundamental bench module

Date: 2026-10-15
Ticket: JEG-564 (part of JEG-556)

## What changed

Added the fundamental bench module -- a config-driven module (Python + JS twin)
that exposes the pooled net-of-waiver ladder from the JEG-556 bench-value
research. Four new files:

- `config/fundamental_bench.json` -- pooled ladder data and research findings
- `pipelines/lib/fundamental_bench.py` -- Python API (ladder, bench_value,
  optimal_bench, bench_summary, findings)
- `app/trade-value-chart/assets/fundamental-bench.js` -- JS twin (IIFE)
- `dist/assets/fundamental-bench.js` -- dist copy of JS twin
- `tests/test_fundamental_bench.py` -- 22 tests (integrity, parity, guard,
  negative guard)

## Verified

- All 22 tests pass including JS/Python parity (subtests: 16).
- Guard test: no tier/line/value path imports the fundamental bench module.
- Negative guard test: simulated violations are caught.
- This is a pure addition; no existing files changed. DDF Value cannot be
  affected (module is never imported by any value path).
- Targeted test suite run (machine under load from ~20 agents; make validate
  timed out). No value-changing code touched.

## Not verified

- Full `make validate` (timed out under machine load).
