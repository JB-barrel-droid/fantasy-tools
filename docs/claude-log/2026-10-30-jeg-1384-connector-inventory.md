# JEG-1384: connector inventory test red on main after the league link change

Session: cloud thread "Overnight board burn-down" (Jeremy asked for the board to clear overnight).

## What changed
- `tests/test_connector_inventory.py`: `find_trades_league` now routes to `#find-league`, and the
  `#find-league` "unresolved (JEG-1030 F2)" exception is gone. #1101 (JEG-1030) and #1175 (JEG-1329) merged six
  minutes apart; #1175 moved the tool's link to the league-wide finder, so the inventory was stale, not the code.

## Verified (check named)
- `python3 -m unittest tests.test_connector_inventory` on main c35173ca: FAILED (failures=1, expected failures=1),
  `find_trades_league links to #find-league, inventory says #find-trade`.
- Same command on this branch: OK (expected failures=1). The expected failure is the two routes still unresolved
  (`#player-values` F2, `#waivers` F3).

## Claimed, not confirmed
- Preview CI's full suite on this head (pending at the time of writing).
