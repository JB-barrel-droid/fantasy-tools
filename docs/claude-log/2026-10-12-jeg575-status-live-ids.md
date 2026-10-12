## 2026-10-12 - JEG-575 status history resolves through Sleeper's live gsis_id

Change: `PlayerIndex.resolve_sleeper` takes `live_gsis` (tried before the identity base's gsis_id); `save_player_status_history.build_rows` passes the live record's `gsis_id`. New `tests/test_player_status_history_ids.py` (live record, no base entry; fails without the fix).

### Verified (check named)
- New tests pass; `make validate` result recorded in the PR.

### Claimed, not confirmed
- The real shift in the name/gsis/unresolved split (needs the next live run's `output/player-status-history.json`).
- espn_id: not added. resolve_sleeper has no ESPN path from a Sleeper record, and the ticket's "and espn_id" would need a players-side espn lookup; left out.
