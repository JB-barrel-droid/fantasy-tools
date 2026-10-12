## 2026-10-12 - JEG-558 market bench ratios

Contract: ship `config/market_bench.json` (one_qb and two_qb frozen ratios, cited) plus the FFC snapshots, derivation script and pinning test, to unblock JEG-559.

### Verified (check named)
- `curl` of fantasyfootballcalculator.com from this machine returned 200; `robots.txt` disallows only /api/, /ajax/, /adp/csv/ etc., not the HTML archive pages used.
- `python3 pipelines/derive_market_bench.py --fetch` saved 9 snapshots (one_qb 2016/2018/2020/2024 plus excluded 2022; two_qb 2018/2020/2022/2024). one_qb 2022 lists 157 players, below 162, so it fails closed as truncated (`tests.test_market_bench`).
- `--derive` reproduces the ticket values within 0.02. Exceptions: one_qb QB 0.87 (frozen 0.88) and K 0.02 (frozen 0.00). All two_qb values match exactly. Frozen values from Jeremy's 2026-10-10 15:25 comment are stored as authoritative.

- `tests.test_market_bench` and `tests.test_monitoring_coverage` on the py3.12 venv: 33 tests OK.
- Full `make validate` was NOT completed: 46 of ~286 core targets passed with no failure, then it stalled under load from 8 concurrent validates and was killed. An earlier py3.9 run failed `tests.test_razzball_one_save` (py3.9 cannot parse ".1+00:00"; unrelated, use the py3.12 venv). The change is additive, so CI is the full gate; fix forward.

### Claimed, not confirmed
- Why the original one_qb QB/K differ by 0.01-0.02: assumed the original measurement used slightly different draft sets (K/DEF set vs skill-only set); not investigated.
