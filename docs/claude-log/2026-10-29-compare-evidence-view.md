## 2026-10-29 - Isolated Fieldnotes Compare evidence view (PR #1136; JEG-1271, corrections JEG-1294 and JEG-1319)

Contract: add a standalone `CompareEvidenceView` (`app/v2/compare-evidence-view.js` and `.css`) that renders the existing `dealRead`, `compareTrade` and `tradeVerdict` outputs from frozen, injected input and computes nothing. It is not loaded by the page. No value, default, ranking or copy-policy change.

### Verified (check named)
- `python3 -m unittest tests.test_compare_evidence_view_contract`: 4 tests OK locally. It recomputes the 9 synthetic fixtures with the current `trade.js` and checks every rendered word and number against the input; its mutants fail it (PR description).
- `python3 -m unittest tests.test_render_sweep_shards tests.test_validate_shards`: 22 tests OK after the JEG-1319 move.
- JEG-1319 finding 3: `tests.test_compare_evidence_view_render` is no longer in `test-core` or `test-core-shard-4` (the deploy gate); it is in `test-render-extra` and `test-render-sweep-3`. The contract test stays in `test-core` / shard 4. Checked by `grep -n compare_evidence Makefile`.
- `tests.test_render_sweep_coverage` lists no compare-evidence module as unwired. It fails on this head with 4 failures that are the same on `origin/main` (five other render modules unwired); not caused by this PR.

### Claimed, not confirmed
- The render test (`tests.test_compare_evidence_view_render`: 320/390/1280 overflow, keyboard, retained focus and slot, frozen input, broken-build mutants) has not passed in a real browser. Its first Linux run (head 2ed4546, preview shard 4) was red: every disclosure's content was 5 px wider than its box at all three widths, and the slot-rebuilt mutant raised a TypeError instead of reporting a problem. Commit 2637f6e changes the disclosure toggle to a two-column grid, names the overflowing child in the failure, and null-guards `SLOT_FOCUS`; whether that clears the overflow is unconfirmed until the Render sweep run on this head reads it (no Chromium in the cloud session).
- The overflow's cause is not named yet; the 2637f6e diagnostic is meant to name it.
