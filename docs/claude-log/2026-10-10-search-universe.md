## 2026-10-10 - Search covers every active NFL player, front end (JEG-502)

Contract GL-20 and Jeremy's decision (2026-10-09): unvalued players appear only in search results, never in tables or charts, as "0.0" with the reason.

### What shipped (`app/v2`)
- Player values, Trade targets and Risers & fallers: a "○ Not valued" list under the filters when a search matches players no source prices. Each row shows name, position, "DDF Value 0.0" and the engine's `unpriced_reason`. At most 8 rows, then a count. Position filter applies.
- Compare a trade: the search dropdown lists them after priced players, with 0.0 and the reason, disabled (not addable: a trade is a table and a chart).
- Player values empty state says the search matched only players with no value, listed above.
- Uses `C.searchPlayers` (engine), memoized by query and position, cleared on `trade-value-rows-change`.
- Team is not shown for these players: 29 of 306 have a stale `team` (BE-5 in docs/v2-design-notes.md). The reason names the current status and team.
- "0.0" is a display rule for `universe_only` rows, not read from the engine: since JEG-508 the engine returns DDF Value null for them (it returned 0 before).
- Contract test: GL-20 is `PENDING("JEG-502", partial=gl20)` until the Doc drops its "to build". The check picks a real practice-squad player from the engine and searches every tab. Broken build: Player values without the list is caught.

### Verified (check named)
- `tests.test_v2_contract_render` OK on main ed77a14e + this change (GL-20 partial passes; GL-20 fails on main's v2.js: the player is not found on any tab).
- `make validate` exit 0.
- Earlier the same day, before the rebase: every `tests/test_v2_*_render.py` suite one at a time, `test_launch_front_door`, `test_ddf_composite_value` OK, except `test_v2_ux_render` and `test_v2_panels_render`, which fail identically on clean main on this Mac.

### Claimed, not confirmed
- The full v2 render sweep was not rerun after rebasing onto the 71 commits that include JEG-508 work.
