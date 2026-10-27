## 2026-10-26 - JEG-1121 stable bench allocation

Contract: Replace greedy-PPG + D'Hondt-fallback bench allocation with a clean VORP × usage-discount pass (`c^(1+floor(k/t1))`), no D'Hondt fallback. All bench seats filled in one cross-position greedy pass; replacement level = 0; seats left unfilled only if no positive-PPG candidates remain.

### Verified (check named)

- `python3 -m unittest tests.test_roster_convention` — 37 tests pass including 3 new ones (determinism, no D'Hondt RB tail, unfilled seats when all zero PPG)
- `python3 -m unittest tests.test_value_reference_worked_example` — 18 tests pass; hand-check values updated for new allocation (p1 RB Delta adj 49.445413, ddf_blended 50.760350)
- `python3 -m unittest tests.test_spec_reference_value_pipeline` — 24 tests pass; spec reference default changed to `flex_bench_seats=True`
- `python3 -m unittest tests.test_value_pipeline_engine` — 21 tests pass (node); fixture updated for VORP path, engine test updated to `flex_bench_seats=True`
- Bench counts verified against actual ESPN projection data (main checkout data):
  - STD/12: QB 5→8, RB 53→42, WR 19→27, TE 7→7 (RB share 63%→50%)
  - PPR/12: QB 5→8, RB 35→33, WR 37→33, TE 7→10 (RB share 42%→39%)
- `make test-core` pre-Playwright tests pass (120 + 201 tests); Playwright errors in test_rank_guard and test_superflex are pre-existing environment failures (browsers not installed), confirmed by running same test on HEAD before changes

### Claimed, not confirmed

- Value impact on individual players (risers/fallers) not computed: chart source data absent from worktree (DDF_FAMILY["blended"]="chart" per JEG-1073, but chart sources excluded in this environment). Directionally: WR and TE backup values increase with more bench seats; deep RB backup values decrease.
- `make validate` full gate not verified (Playwright/sync failure is pre-existing environment issue)
