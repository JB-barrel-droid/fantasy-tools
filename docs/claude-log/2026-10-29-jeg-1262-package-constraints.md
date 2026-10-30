## 2026-10-29 - JEG-1262 package uniqueness and roster application (part of JEG-1183)

Contract: add a pure helper, `app/v2/trade-package-constraints.js`, that checks a set of already chosen trades
(my team against each counterparty once, each player at most once, every player on its original roster, clear keys)
and applies a valid set to the rosters, with an explicit error and no partial application otherwise. No search,
selection, ranking, valuation, lineup or fit logic. No existing file changed.

### Verified (check named)
- The fixture package (4 teams, 3 trades: 1-for-1, 2-for-1, 1-for-2) validates and gives the hand-written final
  rosters; applyPackage equals applyTrade one after another; all 6 orderings give the same rosters; an unequal
  3-for-1 plus 0-for-2 package conserves every player in both orderings
  (`python3 -m unittest tests.test_jeg1183_package_constraints`, test_checks_pass).
- 24 negative cases each fail with their own code and return no league, and inputs are unchanged after every call;
  deep-frozen inputs run under strict mode without a throw; output shares no object with input (same test).
- x: keys (DEF, K, an unmatched WR) move as plain entries; engine-row values never reach a roster (same test).
- The checks fail on six mutated builds: counterparty check removed, used-player check removed, membership not
  checked, partial application on error, entries moved by reference, engine row moved instead of the roster entry
  (test_checks_fail_on_broken_builds; each mutant's failures were printed and read).

### Claimed, not confirmed
- The new test is not wired into any Makefile target, so CI does not run it yet. Wiring it (one line in
  `test-unit-modules`) is proposed on JEG-1262 for the Makefile owner.
- `tests.test_render_sweep_coverage` is red on main before this change (unrelated render modules unwired); not
  touched here.
