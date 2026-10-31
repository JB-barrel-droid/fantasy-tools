## 2026-10-29 - JEG-1150 option A: keep QB miss_rate at 0.12 (pin only)

Contract: Jeremy, 2026-10-29, main chat: "If we need a decision but there are only two real Paths, do the
work for both, and then we'll decide after". This is path A (keep 0.12, the recommendation). No value
changes: it adds a test that pins the QB miss_rate in both twins so the choice can't drift.

### Verified (check named)
- `tests/test_bench_miss_rate.py`: 3 tests OK. JS `VORP_MISS` equals Python `_BENCH_MISS_RATE`; QB is
  0.12; at 12 teams QB backups come in a block of 4 (t1) ahead of TE.
- Changing only the JS QB rate to 0.15 fails `test_python_and_js_rates_match` (checked by hand, reverted).
- Python reference, data/fixtures/current: bench seats unchanged (std/12 QB 8 / RB 42 / WR 27 / TE 7;
  USO shape half PPR 12, WR3, bench 5: QB 4 / RB 27 / WR 24 / TE 5).

### Claimed, not confirmed
- CI shards and `make validate` on this head (not run here; cloud has no Playwright Chromium).
