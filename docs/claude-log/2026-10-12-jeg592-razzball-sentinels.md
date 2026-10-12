## 2026-10-12 - JEG-592 sentinel players in the fidelity pulse (part of JEG-555)

Contract: stop a self-consistent bad projection row (Razzball Lamar 7.1, Mahomes 10.5) from reaching the chart unnoticed.

### Verified (check named)
- `tests.test_fidelity_sentinels` (8 tests) plus `tests.test_fidelity_pulse` and `tests.test_fidelity_razzball`: 74 pass on py3.12.
- Negative test `test_negative_without_the_sentinel_call_the_bad_rows_pass`: with `sentinel_failures` stubbed out, Razzball Lamar at 7.1 and Mahomes at 10.5 stay non-red.
- `make validate` exit 0.
- Sweep of the committed `players.json` (half PPR per game, below 60% of the other sources' mean, reference at least 3 ppg): 66 rows, posted on JEG-592.

### Claimed, not confirmed
- Bands were set from the committed fixture values; no live chart was read in this session.
- Trade charts are not swept (own scales, not per game).
