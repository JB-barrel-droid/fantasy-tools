## 2026-10-23 - JEG-972 Find a trade: collapsible input, core-player groups, roster impact

Contract: build the approved spec (fantasy-tools-selfhost-notes/jeg-972-find-a-trade/spec.md, JEG-885, JEG-890) as three
commits on PR #875. No value, ranking or Compare change; roster impact is display only (Jeremy 2026-10-23).
No `make sync`, no 12-combo sweep (no value moves).

### Verified (check named)

- Search unchanged: node comparison of origin/main finder.js vs this branch on a 9v9 3-for-3 fixture, 221 trades, identical
  order, edge and score (zero-value throw-in folding is the only intended difference).
- Unit (node): tests/test_v2_finder.py, test_v2_finder_groups.py (parity of evaluateCombo with findTrades on every trade,
  throw-in collapse, simpler-variant-absent, receive-core grouping, 50% rule, equal-core ties, order determinism),
  test_v2_finder_impact.py (pickStarters ties, 2-for-1 empty slot, superflex QB, unvalued; rosterImpact; chart average).
- Render, each file alone under the shared lock: test_v2_finder_collapse_render, _groups_render, _impact_render (1366x768,
  390, 320), plus finder, arrange, import, paste and waterfall (Compare 1366x768 verdict fit) all green.
- Every new guard proven against a broken build in its own test (14 mutations caught across the five new files).
- Older finder tests: the pinned mutation anchors were re-pointed to the refactored code (judgeSums, link in groupCard,
  judgeLineup); the assertions and the defects they model are unchanged. Arrange/render tests click "Edit rosters" first
  because Find now folds the input.

### Claimed, not confirmed

- Screenshots before/after in fantasy-tools-selfhost-notes/jeg-972-find-a-trade/build/ use typed rosters (top players
  alternating), not the 14-man review rosters (not stored in the repo); the Yahoo matchup fixture gave 0 trades.
- Product behaviours taken from the spec text and awaiting Jeremy: gate-failing selections stay selectable with a warning;
  package cap disables extra ticks; 10 groups then "Show N more groups"; 1-for-1 groups have no checkboxes; position need
  is read from the DDF Value lineup. At 3-for-3 the 50% rule yields several near-duplicate multi-player targets.
