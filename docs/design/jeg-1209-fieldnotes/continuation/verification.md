# Fieldnotes revision 3: verification (JEG-1209)

Baseline: #1089 head `2c8931231ccd2bbeb4946ac031aee5ac655182f4`, `prototype.html` sha256 `f66e00c6f0098c46fcac6552943dfdcfc8f7b1302325c37a99c4ad1764adcf07`, unchanged.

## Verified (check named)
- `python3 preview/jeg-1209-fieldnotes/build.py --check`: the baseline hash, every vendor blob in `MANIFEST.json` and the built `index.html` match.
- (Earlier revision; the column move it mentions is gone since JEG-1250.) jsdom smoke run of the built page (scripted, no browser layout): no script errors; League status reads "4 teams · 51 players · Your team: Your sample team"; Opponents to include starts at 3 of 3; excluding one opponent gives "Showing 8 of 20 results from 2 of 3 opponents (30 stored in this example)" and Trade ideas "From 20 trade opportunities. Left out: 19 trades that aren't a gain for you."; Clear gives "No opponents are included, so no trades can be shown. 30 stored results are hidden by this filter." with Include all; a column move saves the order under `fieldnotesOpps` and keeps focus on the pressed button; opening details focuses `.detailtitle` and Escape returns focus to the row's button; a package-size change shows "Results are from the previous preferences" and sets `data-stale`; Values loading, No league and Projections missing each render their own text, and Trade ideas hide while loading or with no league.
- With all opponents included, 1 of the 30 stored opportunities is a Trade idea; the other 29 lower our starters (main's `ourFitOf` on the fixture's own fit fields).
- `python3 -m unittest tests.test_ci_speedup_workflows tests.test_gha_schedules_pg_cron tests.test_deploy_gate_unconditional`: 35 tests pass with the new workflow.

- How leaguemates trade (2026-10-29): jsdom run of `index.html#finder` finds 3 managers in the Managers card, no text input, text area or editable region in it, all 18 selects at Not sure / Not set, no box ticked, each summary "Not described yet.", no script errors; ticking Likes rookies saves `"note":"Likes rookies"`. `revision2.html` differs from the #1089 prototype only in its Find a trade route (checked with diff), so its paste box, team name and searches are back.
- CI (`checks.py`) runs the same Managers checks at every width.

## JEG-1250 corrections (2026-10-29)
- `checks.py` run locally (Playwright 1.49.1, Chromium, macOS): 140 of 140 pass, 18 screenshots. `build.py --check` passes.
- The same `checks.py` against the previous head `840cd4e1`: 121 of 140, 19 fail, one or more per finding: the live league key is replaced by the sample league and the live manager-profiles key is rewritten; filters lost on reload and through No league; no stable announcement region or Reset preview; a legacy note becomes "Likes rookies; Win-now" (earlier text deleted); the column order picker is still there.
- New checks (desktop 1280 unless named): live keys seeded first, then left out an opponent, ticked a manager box, reloaded, No league, reload in No league, back to Loaded, Reset preview: both live keys byte-for-byte unchanged and no other non-preview key added or removed; the filter and the ticked box survive each step; Also show and Reset preview write their final text into the same `#previewLive` node with focus on the pressed control. At 390: a note saved before the checkboxes ("Prefers WR depth; answers on weekends") shows as kept text, ticking Win-now and Likes rookies saves "Likes rookies; Win-now; Prefers WR depth; answers on weekends", unticking both returns the exact earlier text, and with a 275-character note a box is refused, announced and leaves the note unchanged.
- Column order picker removed after Jeremy's fixed-order decision (JEG-1232); checks assert the table and phone cards draw the fixed order and no picker exists.

## Claimed, not confirmed
- Layout, overflow at 1280/768/390/320, 44px targets, dark theme and the screenshots come from `checks.py` in the `JEG-1209 Fieldnotes preview` workflow. This sandbox cannot download a Chromium build, so those checks had not run here when this was written; the PR's workflow run and its artifact are the record.
- No screen reader was used. Announcements are checked only as `role="status"` / `aria-live` text.
- The vendored components are exactly their PR heads at the pinned commits; if those PRs change before merging, `build.py --vendor` must be rerun with new pins.
