## 2026-10-09 - FantasyCalc promotes after the import-health fix (JEG-512 follow-up)

Contract: confirm the claimed item in 2026-10-09-fc-import-health.md, that
FantasyCalc promotes after PR #480 (merge 9793769).

### Verified (check named)
- Rebuild-chain run 38003291693 (dispatched, head 9793769): the import step
  stamped "594 fantasycalc rows (vintage Week 5, 0 review)"; the import
  health step printed "GATE: GREEN -- all import sources verified fresh";
  the chain printed "fantasycalc: promoted 3/3". It pushed 3c94d0cb to main,
  where output/comparison-chain-status.json is outcome green, held [].
- Live site after the Deploy dashboard run 38006023276 (head 3c94d0cb,
  success): modules/comparison-sources-data.json FantasyCalc section has
  fetched_at 2026-10-09T17:05:19 (the fcwk5_2026-10-09t1705 bake; before:
  13:07:08) and promoted_at 23:25:40Z; modules/comparison-chain-status.json
  is green with no holds; modules/source-import-health.json FantasyCalc is
  ok, row_count 594, db_latest_rows 594. Checked by fetching the three
  files with a cache-busting query.

### Claimed, not confirmed
- Nothing new.
