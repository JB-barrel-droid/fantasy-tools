## 2026-10-25 - FE finder lane (parent JEG-1093)

Contract: Find a trade front-end fixes from Jeremy's Mac review: JEG-1103, JEG-1094, JEG-1095, JEG-1098, JEG-1099.

### JEG-1103 Risers and Fallers duplicate DDF
Cause: the Risers picker passed every series in `TradeValueMovers.SERIES` to `renderSeriesPicker`, including `ddf_value_charts`, which is the same series as `ddf_value` (`sameAs`, JEG-1073) and carries the same label "DDF Value". Other pickers already hide it via `ddfPickKey`. Fix: Risers picker filters to pickable keys.
#### Verified (check named)
- `tests.test_v2_risers_render` passes; `check_picker` now asserts unique option labels; new mutation "duplicate DDF option in Risers picker" (filter removed) is caught by the checks (negative test).
#### Claimed, not confirmed
- Live site not reproduced; cause found from code.
