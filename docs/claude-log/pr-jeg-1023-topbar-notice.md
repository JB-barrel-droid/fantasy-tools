## 2026-10-24 - JEG-1023: top bar notice, built for season-long value (PR #889)

Jeremy (2026-10-24): add a notice in the top bar on all pages that the dashboard is designed for season-long value only,
not weekly decisions or playoff optimization; it should be closable and stay closed for the session. Follow-up
instruction: say the "Optimize for playoffs" setting has not been reviewed and likely is not working, and that
defenses and kickers are not yet accounted for. Keep the setting; add a "Not reviewed" caption later.

### What changed
- `app/v2/shell.html`, `v2.css`, `v2.js`: one line under the tab row ("Built for season-long value, not weekly
  start/sit decisions or playoff optimization."), a "More" button that opens the full list as an overlay, and an X
  ("Dismiss notice") that stores the dismissal in sessionStorage (in-memory fallback when storage is blocked).
- Ids and classes are `v2SeasonNote*` / `v2-topnote*`: `v2Notice` / `.v2-notice` already belong to the sources notice.
- Desktop: the nav row's min-height drops 64 to 46 px while the notice shows, and the notice row is 18 px, so the
  header is 64 px shown or dismissed.

### Verified (named checks)
- `tests/test_v2_topbar_notice_render.py` (new): notice text and full list on 10 routes at 1366x768 and 390x844; header
  64 px shown and dismissed at 1440x900, 1366x768, 1024x768; no sideways scroll at 390, 360, 320, 844x390, 768, 820;
  dismiss across routes, reload, a fresh context, and blocked storage. Seven broken-build proofs each fail it.
- `tests/test_v2_hamburger_nav_render.py`, `tests/test_v2_nav_render.py`: pass.
- `tests/test_v2_waterfall_render.py`: the verdict-fit test passes with the notice shown.
- Header heights shown / dismissed (px): 1366 and 1024: 64 / 64. 820 and 768: 170 / 152. 390, 360, 320: 148 / 104.
  844x390: 104 / 64.

### Claimed, not confirmed
- `test_v2_waterfall_render.test_guard_fails_on_broken_builds` fails on origin/main too ("no wide verdict column on
  short viewports" is not caught); not touched.
- At 768 and 820 the tab row already wraps, so the notice adds its 18 px row there. A phone adds 44 px (the 44 px
  buttons make that the floor for a separate row). A padding tweak to cut 8 px had no effect and was removed.
- The "Not reviewed" caption next to "Optimize for" is not added: `fe/league-settings-live` edits the adjacent lines.
