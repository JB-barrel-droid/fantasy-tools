## 2026-10-12 - JEG-606: unpriced players' DDF Value and team fix

### What changed

1. **DDF Value null -> 0 for universe_only players** (`app/trade-value-chart/assets/curve-widget.js`):
   `setCompositeFields` now computes the DDF composite from `row.values` when
   no pipeline row exists and the player is `universe_only`. VP-6.2 already sets
   individual chart values to 0 for these players; the composite now averages
   those zeros instead of returning null.

2. **Stale team on universe_only players** (`pipelines/bake_players.py`):
   When a player enters the bake via `espn_zero` (comparison fixture absent
   entry) with `team=""`, `_resolve_team_abbr` falls back to the registry's
   team_id, which can be stale (traded/released). The `universe_only` check at
   line 843 did not catch these players because `espn_row.get("universe_only")`
   is False for espn_zero rows. Fix: after setting `universe_only = True`,
   override `row["team"]` with `uni["team"]` (the current Sleeper roster team).

### Root cause

JEG-508 made the pipeline ESPN-neutral, but `setCompositeFields` still relied
exclusively on `pipeline.rows` for the DDF composite. Universe_only players
have no pipeline row (no source lists them in its natives), so the composite
was null instead of 0.

The stale team bug predates JEG-508: any player in the comparison fixture's
keyed identities that is also a universe_only player got the registry's (stale)
team because the universe_only team override at line 843 only checked
`espn_row.get("universe_only")`, not the final determination at line 918.

### Verified

- 12-combo engine dump sweep: all 13 combos `fixedPieIndexed=True`,
  `sourceScaleAgreement=True`.
- `test_search_players_universe`: tightened assertion from
  `assertIn(ddf_value, (0, None))` to `assertEqual(0, ddf_value)`. Passes
  with fix, fails without (negative-tested: reverting the engine change
  produces `AssertionError: 0 != None`).
- `test_jeg606_unpriced_team_and_value`: fixture-level guard checks every
  universe_only player's team matches `unpriced_reason`. Negative-tested
  with injected stale-team data. Fixture test itself requires a fresh bake
  (next CI run).
- `make validate` exits 0.

### Decision

Option (a) from the ticket: the engine returns 0 for universe_only rows. v2
already displays "0.0" for universe_only rows without reading the value, so
this makes the engine consistent with the display.
