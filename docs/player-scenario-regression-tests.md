# Player Scenario Regression Tests

These tests are meant to answer football questions with current players, without
pinning the suite to stale weekly rankings. The player names are selected from
the shipped fixture each run by archetype: position, current dashboard role,
source value, and distance from the starter/bench or bench/waiver boundary.

The executable coverage lives in `tests/test_player_scenario_matrix.py`.

## Scenario Concepts

- **Core starters by position**: picks the current top QB, RB, WR, and TE on the
  ESPN anchor. This answers whether obvious starters are still priced and role
  classified as starters across the end-to-end fixture.
- **Starter/bench margins**: picks the lowest current starter and highest current
  bench player at each position. This answers whether the dashboard's role line
  remains ordered where lineup decisions are most sensitive.
- **Bench/waiver margins**: picks the lowest current bench player and highest
  current waiver player where the fixture has both. This answers whether the
  bottom-of-roster line behaves like a real waiver boundary.
- **Square bench and square waiver players**: picks middle-of-role players, not
  just cut-line edge cases. This answers whether the model still covers ordinary
  bench and waiver decisions.
- **Two-for-one consolidation trade**: picks two current bench players and a
  current starter closest to their combined value. This answers whether
  multi-player trade totals are computed from canonical player values rather
  than from hardcoded names.
- **Cross-position package trade**: picks a current QB starter plus WR bench
  player against a current RB starter. This answers whether package math keeps
  each player's position-specific source value instead of flattening positions.
- **Waiver throw-in**: picks a bench/waiver boundary pair and adds the waiver
  player to the bench side. This answers whether a waiver player is explicit low
  value, not a silent missing-value fill.
- **Multi-source coverage**: checks the selected scenario players are priced by
  the ESPN anchor plus at least two other source maps. This answers whether a
  scenario is broad enough to test the published comparison product.

## Freshness Rule

Future weeks should change which players are selected. A scenario should fail
only when the fixture can no longer produce that archetype, the role boundary is
misordered, or source coverage becomes too thin for the scenario to be useful.
