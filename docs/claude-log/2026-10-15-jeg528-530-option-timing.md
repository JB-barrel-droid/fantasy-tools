## 2026-10-15 - JEG-528, JEG-530: option value and timing horizon series

PR #604, squash-merged to main.

### What changed
- **JEG-530 (option value):** `esBandSurplus` / `_band_surplus` computes
  E[(X-w)+ x 1{band}] -- the convex option form. `optionValue` per row =
  premium (optionAdjusted - adjusted) averaged across sources. Separate series;
  DDF Value unchanged.
- **JEG-528 (timing horizon):** `timingFactor = windowWeeks / 17`. Bench
  (fill-in) value scales by this; starter value does not. `timingValue` per row
  = discount (adjusted - timingAdjusted) averaged across sources.
- Updated mutation anchor in `test_view_invariants.py` for the local-variable
  refactor in `_price`.

### Verified
- 16/16 reference worked example: PASS
- 12-combo headless sweep (fixedPieIndexed): PASS
- DDF Value pinned to 1e-6: PASS
- Negative mutation test (view_invariants): PASS
- Math review: esBandSurplus derivation checked against integral identity
  for truncated normal. Degenerate (sd=0) and infinite-hi cases correct.
  Python and JS implementations identical.

### Not verified (pre-existing on main)
- ReferenceMatchesEngine (held-source mismatch, another agent fixing)
- 2 ExpectedStartsVariantTest anchors (pre-existing on main)
