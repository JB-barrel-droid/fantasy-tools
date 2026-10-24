## 2026-10-24 - JEG-1020 league settings apply live; Find a trade reprocesses on change

Jeremy, 2026-10-24: "Reprocess the text when league settings change. Don't require hitting accept or save when league settings are changed." No value math touched (curve-widget.js and value-model.js unchanged).

**What changed**
- `app/v2/v2.js` Your league: no Apply, no Cancel. Footer is Reset defaults, Undo changes (back to what the panel opened with), Done (closes only). Each control sets the draft and starts a 150 ms debounce; the recompute runs from the timer, not the input handler; Done and any close flush a pending change. The engine refusing a value keeps the last valid results and shows one inline line (`[data-league-issue]`). After a recompute that took 200 ms or more the next change shows "Updating..." first. Polite live region `#v2LeagueLive` says "Results updated for the new league settings." plus any notes; focus stays on the control (at a stepper limit it moves to the other stepper); no scroll. The panel resyncs from the engine only when a value moved (roster clamp, bench-share override), and says so.
- `leagueChange()` is exception-safe and fires `ddf:league-settings-changed` (also from share-link open and Position weights Apply). The old "Cancel/Apply" contract line GL-11 is rewritten (docs/feature-contract.md, qa-report).
- `app/v2/finder.js` (small, local): each side remembers the page text it was read from (`S.src`), hand-removed players (`S.removed`); one handler re-reads the text, drops players the engine no longer has, adds newly matched ones, re-renders chips/evaluation, re-runs results if they were showing, and puts back the reader's ticks inside groups (only ticks the reader changed from the default), open details, open/folded roster input, ticked "move" players, cleared sides.
- Tests updated because they encoded Apply (not loosened): test_v2_panels_render, test_v2_advanced_render, test_v2_season_weeks_render, test_v2_contract_render (gl11). New: tests/test_v2_league_live_render.py.

**Verified (named)**
- tests/test_v2_league_live_render.py: passes; guard test passes (7 broken builds caught: apply step back, no debounce, Find listener removed, invalid intermediate throws, no Updating state, no live announcement, focus stolen).
- Pass: test_v2_advanced_render, test_v2_season_weeks_render, test_v2_panels_render (includes 1366 fit), test_v2_contract_render, test_v2_a11y_render, finder render tests (render, paste, collapse, groups, impact, box, arrange, chips, eval, import, kdef_search), finder node tests (14).
- Pre-existing red on origin/main, same failure with and without this change (run in a clean worktree): test_v2_finder_fit_render guard "tier ordering off" not caught; test_v2_phone_tap_targets "writing/research: only 7 controls found".
- Tab audit, live change vs a page set up with the same settings first: Player values, Trade targets, Risers and fallers, Compare, Values auditing, How values work, Find a trade all identical text (no stale state). The Find equivalence found one real bug on the way (restored default ticks over the new best package); fixed by restoring only ticks the reader changed.
- Recompute (headless Chromium, Find results showing): default 61-66 ms; extreme (14 teams, superflex, deep bench, extra flex, injury history all) 255-262 ms.

**Claimed, not checked**
- Roster-paste parse output does not depend on settings (parse takes engine rows, no shape); the re-read is therefore mostly a no-op today and matters when rows or positions change. Real devices; screen readers (live region only checked as text).
- The roster-paste "unsure" taps (lesser matches) are not re-asked after a change.
- Sources (Customize) Done does not notify Find; Position weights still has Apply.

### Follow-up (same day): Jeremy's three answers on PR #886

Jeremy, 2026-10-24: (1) Position weights applies live too; (2) changing Customize sources re-runs Find like a settings change; (3) a lesser-match ("unsure") player not yet confirmed is asked again after a settings change.

- Position weights: no Apply/Cancel; footer Reset defaults, Undo changes (back to the shares it opened with), Done. A valid share starts the same 150 ms debounce; an invalid one (outside the range, empty) keeps the last valid value with the existing inline range message; the other boxes, bars and the bench readout follow what the engine rebalanced. The old Apply step in tests/test_v2_panels_render.py (`check_weights`) is replaced by waits for the engine plus `[data-done="weights"]` and an assertion that no Apply/Cancel exists (the step it encoded is the one Jeremy removed; no assertion was loosened: the engine-share, range-message, snap-back and reset assertions are unchanged).
- Customize (sources) Done, the bench-override reset link and the share-link open now fire the same event; Find re-runs and says "Updated for the new source selection." The live region reads "Results updated for the new source selection."
- Unsure questions: each side's pending "Yes, add / No, search" prompts are re-built after a change (same match, same buttons), listed in the live region as "N matches to check again" and in the inline note; an answered question (Yes or No) is remembered and not asked again; a prompt whose player is no longer in the engine rows is named as "can no longer be matched". Focus is not moved.
- Guards (tests/test_v2_league_live_render.py, each proven against a broken build): Position weights Apply step back; Customize change leaves Find stale; unsure prompt not asked again. Check of why each failed: weights patch -> "QB 30 did not apply on its own"; customize patch -> "Find was not re-run after a Customize change"; unsure patch -> live region lacks "check again".
- Conflict with fe/finder-assessment-table (PR #883, still open, not landed): one hunk in finder.js where the card is built; my `v2FindSettingsNote` paragraph and their `v2FindFit` headline + `v2FindAssess` section sit on adjacent lines. Resolution when #883 lands: keep all three elements, in the order headline, assessment, settings note, then `v2FindOut`. Their branch was not merged here.
