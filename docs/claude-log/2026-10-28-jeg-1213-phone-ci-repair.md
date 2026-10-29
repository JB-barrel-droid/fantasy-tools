## 2026-10-28 - JEG-1213 phone CI repair

Contract: repair PR #1058's 375px phone-context clipping by reusing #1043's verified fallback-font fix, merge latest main, run bounded checks and one independent delta review. No merge to main, deployment or deletion.

### Verified (check named)
- Git ancestry correction: prior head `6153bc89` contained #1043 `68b95fa5`, not the later `d886fc9f`. Earlier JEG-1213 handoff/log claims that d886fc9f was already included were incorrect. Fetched the full later SHA explicitly and merged it normally as `df20ab3e`.
- The reused UI fix reduces existing phone gaps and freshness padding, retaining 14px text and 44px control height. No competing CSS rule added. Its regression exercises default and DejaVu Sans at 375/390px, active overrides, Reset and Undo.
- Merged main `2ccdcc79` normally as `010f7a7d`, including main's approved #1044 engine change. No new engine edits or methodology choices. Conflicts were documentation only: retained all picks, main's #1142 continuation, and newer #1134 UI handoff.

### Repair verification
- Focused test: `RENDER_TESTS_REQUIRED=1 CHROMIUM_PATH=/usr/bin/chromium python3 -m unittest tests.test_v2_phone_context_row_render.PhoneContextRowTest.test_override_reset_and_undo_keep_the_closed_summary_readable` — exit 0, 1 test in 36.493 seconds; 12 measured states at 375/390px in default/DejaVu Sans were 45px high, clipped=False, overflow=0.
- Independent read-only delta review of `6153bc89..010f7a7d`: PASS, no actionable findings. CSS and fallback-font assertions retained; all picks and appropriate handoff sections preserved; engine files match main `2ccdcc79`. No duplicate broad suite or additional workers.
- Final checkpoint changes documentation only after tested/reviewed integration `010f7a7d`. Build-generated untracked outputs remain local and excluded from commits; no deletion performed.

### Claimed, not confirmed
- Remote exact-head CI remains necessary. #1043 and #969 remain release dependencies; parent owns serial merge and live verification. JEG-1213 stays open.
