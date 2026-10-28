## 2026-10-28 - JEG-1184 finder guardrail settings

Contract: Add prominent protected-position and lineup-fill controls, with three supported numeric finder minimums under Advanced. Save them with the local workspace, include active settings in search links, and preserve the release branch's default finder results.

### Verified (check named)
- `tests.test_v2_finder_guardrails`: protected RB rejects a weakening trade, active DDF and lineup minimums filter, default settings leave the complete search result unchanged, invalid values reset, workspace export/import and local-storage visits round-trip, and link settings decode.
- `tests.test_v2_finder_guardrails_render` with `/usr/bin/chromium`: keyboard controls, invalid input, reload, reset, link visit, phone overflow and page errors passed.
- `tests.test_v2_finder` and `tests.test_v2_league_units` passed.
- `tests.test_validate_shards` passed after wiring the focused unit test into `test-core` and shard 3; the focused browser test is in the `v2-render` workflow.
- `tests/fixtures/finder_search_signature.js` produced identical 2-for-2 and 3-for-3 signatures for this branch and the PR #1062 head before edits. The repository's older `finder_search_golden.json` already differs from that head.

### Claimed, not confirmed
- Remote CI and production behavior are pending review. No production merge or deployment was performed.
