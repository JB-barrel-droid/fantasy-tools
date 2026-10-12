## 2026-10-12 - JEG-504 market average beside Our value

Contract: Trade targets shows the mean of the compared charts' rescaled values beside Our value, with our value minus it (symbol + sign), and a single "= market average" note when they match to one decimal (TT-09).

### Verified (check named)
- `tests.test_v2_targets`: the average, count, left-out count, difference and equal flag equal an independent Python recomputation for constructed rows (equal case, a null chart, a finite 0 chart); three mutations (zero dropped, sign flipped, equal never flagged) are caught.
- `tests.test_v2_targets_render` (`check_market`): every rendered table row and phone card, for all four Our-value series at 1440 and 390 px, equals a recomputation from `getRows()`; three render mutations are caught.

### Claimed, not confirmed
- Visual fit of the extra column at 1024 px relies on the no-horizontal-scroll layout check passing, not on a screenshot review.
- Rare edge: averages that differ at one decimal but with a difference under 0.05 show "▲ 0.0".
