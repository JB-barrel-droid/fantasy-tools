## 2026-11-07 - JEG-1557 Mobile defects, connect.html rework, caveats note

Contract: fix the visual defects a 390/360 sweep of the swapped live site finds, rework connect.html (hierarchy, plain
steps, friendly error and success states) with parser and storage unchanged, run the PMM review on desktop and mobile,
and (added by Jeremy 2026-11-07) tell users our caveats: a short collapsed note on the team assessment and Trade &
Waiver Recommendations pages, and one line when a league first loads in the entry flow.

PMM jobs: no runnable definition exists in the repo. The definition is the JEG-1357 audit text (copy of every page:
headline, glossary, explainers, empty/error states, CTAs, honesty of labels; each finding where/what/why/size). Two fresh
agents ran it against the live entry flow, one at 1440x900 and one at 390x844 (touch, iPhone UA too).

What changed
- Mobile: entry header no longer pinned on phones and its three steps sit in one row; action bar reason is calm grey and
  compact; info icon stays a circle (44px tap area via ::after); footer links and header Menu 44px; 11px text raised to
  12px (eyebrows, range labels, position chips); explore Back no longer wraps. (`app/next/styles.css`, `actionbar.css`)
- connect.html: one numbering (page Step 1 / Step 2; how-to slides read "1 of 3"), "Where is your league?", fixed the
  self-contradicting league ID lead, ID box placeholder and empty/bad-ID messages, "Open your rosters page" button,
  jump link to the paste box, success card scrolled into view with "Found N teams and M players.", unreadable-paste
  wording, manual-entry copy, blocked hint "Paste your rosters to continue." Parser, `ddf:pasted` record and storage untouched.
- `app/next/caveats.js` (new, reusable): `data-ddf-caveats="assessment|recommendations|entry"`; detail collapsed; an empty
  `.ddf-caveats__slot` is left for the JEG-1558 opportunity-size read. Added to team.html, find.html and the connect
  recognition card; listed in `ROOT_FILES`.
- Old v2 caveats: no block titled caveats exists in the old pages (searched v2 and the pre-swap trade-value-chart index at
  0f348123d). The closest old wording was "read those gaps as leads to check, not verdicts" and "Partial rosters are fine";
  the note keeps that meaning.
- Touch pass (Jeremy 2026-11-07): `touch-action: manipulation` (important, because some controls use `all:unset`) on every
  interactive element in the shared stylesheet; no user-scalable or maximum-scale anywhere (test); inputs/selects/textareas
  16px on phones (iOS focus zoom); `#vchart` was `touch-action:none` (blocked page scroll over the chart) and is now
  `pan-y pinch-zoom` since the chart handles horizontal drag itself; `overscroll-behavior: contain` on menus, table
  wrappers, player list, step trail, carousel. The site has no modals, sheets or drawers (menus are dropdown panels), so
  there is no body scroll lock to add; hover reveals are already limited to `(hover:hover) and (pointer:fine)`.

Verified (check named)
- `python3 -m unittest tests.test_jeg1557_mobile_connect` (11 pass; 16 failures and 5 errors with the app/next changes stashed).
- Same file, TouchBehaviorTest: computed touch-action on all interactive elements, field font size >=16px and 0 overflow on all 13 pages at 390 and 360; stylesheet rule and no zoom-lock meta; chart touch-action.
- QA script (local dist): 13 pages at 1440, 390, 360: 0 console errors, 0 horizontal overflow, 0 broken internal links.
- `tests.test_entry_pages` summary assertion updated to the new wording.

Claimed, not confirmed
- See the PR for `make validate`, the rendered gate, and the live check after merge.

## 2026-11-07 - JEG-1557 follow-up: caveats note on partners.html
Contract: Jeremy asked for the caveats note on the Partners page too; the Workspace agent (JEG-1560) agreed to wait until #1349 and #1350 merged.
- `app/next/partners.html`: `data-ddf-caveats="recommendations"` after the lede, `caveats.js` before `</main>`.
- Verified: `tests.test_jeg1557_mobile_connect` (caveats test now covers team, find and partners at 1440 and 390), `tests.test_partners_rank_parity`.
- Claimed, not confirmed: CI and live check on this PR.
