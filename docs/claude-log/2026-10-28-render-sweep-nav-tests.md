## 2026-10-28 - Render sweep: three stale render tests after the JEG-1106 menu and JEG-1098 top 10

Contract: get three red render tests on main back to a meaningful pass. No product code changed; all three are test
issues after decided changes in 9cffc5cb (JEG-1106 menu at every width, Jeremy 2026-10-25; JEG-1098 top 10).

What changed
- tests/test_v2_a11y_batch1_render.py: FOCUS_RING put its probe next to the first `.v2-tab`, which is now inside the
  closed menu (display: none). The probe could not take focus, `:focus-visible` did not match and the check returned
  99, so it passed without measuring and the "nav ring reverted" mutation was not caught. The probe now goes in
  `.v2-nav-inner` (always shown); an unfocused or non-`:focus-visible` probe is an error.
- tests/test_v2_league_basis_render.py: go() opens the menu (#v2NavToggle) before clicking the entry, as
  test_v2_overrides_basis_render already does.
- tests/test_v2_league_top10_render.py: a missing Show 10 more / Show all / Show top 10 only button is recorded as
  an error instead of a 30 s Playwright timeout. With PAGE = 20, Show all is not rendered after one Show more, which
  crashed the "opens on 20" guard.

### Verified (check named)
- The three files parse; `python3 -m unittest` on them reaches the browser launch (Chromium is not installable here).
- Mutation anchors in the a11y and top-10 guards still match app/v2/v2.css and app/v2/league.js (grep).
- With the reverted rule the ring is #087F5B on #142B25 = 2.99:1 (< 3) in light mode, computed with the test's
  luminance formula; with the rule, #fff on #142B25 = 14.98:1.

### Claimed, not confirmed
- None of the three render tests was run in a browser (Chromium blocked in this environment); the fixes are reasoned
  from code. CI's render sweep is the check.
- The light-mode margin for the nav ring guard is thin (2.99 vs 3.0); a small change to --v2-focus or --v2-nav could
  make the guard stop catching the mutation again.
