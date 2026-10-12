# 2026-10-10 - JEG-586 merge fe/contract (contract v1.2) onto main

### Verified (checks named)
- fe/508fix was already on main (PR #508, JEG-541).
- Rebased fe/contract (44ee796e) on origin/main; conflicts only in `tests/test_v2_contract_render.py`
  and `docs/v2-design-notes.md`. Kept both sides: main's GL-20 partial check and its broken-build
  guard case, plus the branch's GL-22..24 pending lines, TT-06 and MF-01.
- `.venv/bin/python -m unittest tests.test_v2_contract_render`: 6 tests OK in 173s, including
  PV-03/05/16/17 (the zoom checks that failed under load before).
- `make validate`: see PR for the result.

### Not checked
- Did not re-run the 12-combo trade-chart sweep: no change to the trade-value chart or curves.
