## 2026-10-26 - JEG-1121 greedy bench allocation

Contract: Replace D'Hondt bench allocation with a league-wide greedy pool fill so backup QB decisions are driven by player pool, not preset ratios. Keep the units fix (flex_filled division bug) from the prior revision.

### Verified (check named)

- Units fix correct in 4 locations (JS ×2, Python ×4): `python3 -m pytest tests/test_roster_convention.py -v` — all 5 new greedy-behavior tests pass
- 25 engine tests pass: `python3 -m pytest tests/test_value_pipeline_engine.py -v`
- Rank guard 0 inversions: `python3 pipelines/check_rank_guard.py` — "pass -- 12 chart x combo checks, 0 failed, 0 inversions"
- Allocation consistent between JS engine and Python reference: `composite_disagreements: []` in value_check report
- Worked-example fixture regenerated for bench_per_team=5: `python3 tools/worked_example_expected_starts.py --check` passes

### Claimed, not confirmed

- `make validate` will pass once value_check --strict is resolved (currently fails with 199 mismatches)
- 12-combo headless sweep clean (rank guard passed but browser sweep not run)

### Blocker (blocked on Jeremy via JEG-1121 needs-review)

Raw PPG greedy bench over-allocates QB: at std/8, QB gets 24 of 56 bench seats (3 per team) vs 8 in D'Hondt. RB bench drops from 24 → 12. This causes value_check --strict to fail because the expanded fill set pulls in fringe QBs (McKee 1138, Geno 2608, Cousins 3541) that are in some source `native` dicts but not in per-combo `player_keys`, causing engine/Python divergence.

Three options posted to JEG-1121: A=normalize PPG by position mean (recommended), B=cap per position, C=data fix only.

Branch: be/bench-seats-units-fix. Not deployed.
