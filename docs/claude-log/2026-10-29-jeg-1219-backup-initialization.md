## 2026-10-29 - JEG-1219 fresh backup-button initialization

Contract: correct the fresh-page Bench backups button initialization reported in Linear comment `97fc817c-40ce-4245-97df-7d4e418c1cd7`, within the existing picker owner's branch. Preserve zero defaults, 0–20 bounds, guardrail/search/fit calculations, selectors and Claude JEG-1237's separately pending fold design. No main push, PR merge, deletion or Supabase operation.

### Verified (check named)

- Baseline picker head `35c189781425d77ee7e2935d5f7694eea221b14b`: the new `FinderSavedTeamRenderTest.test_fresh_backup_controls_click_keyboard_bounds_and_persistence` failed at both 1366px and 390px before any reset/import/settings workaround: `QB + must work before any settings update` (`is_disabled()` was true at 0). One test, two failing subtests, 27.739s. Initial localStorage and sessionStorage were both empty.
- Cause: the shared `el()` helper serializes attributes; `disabled=false` still creates the boolean disabled attribute. The backup construction site now sets the button's DOM `disabled` property after creation. The shared helper, click clamp, handlers, saved settings and URL precedence are unchanged.
- Same new regression after the fix: **1 passed, no skips, 31.789s**, covering both widths, all four positions, click/Enter/Space, initial minus disabled/plus enabled, zero/20 bounds, reload persistence, reset, real-roster shared-link replay and a separate plain-route saved preference reload. The reset action opens its existing Advanced disclosure; no force clicks or runtime setup repair is used before initial checks.
- Independent final source/test delta review **PASS** against `35c18978`: syntax and scoped whitespace passed; no calculation/default/selector/layout changes or blockers. Reviewer ran no duplicate browser suite.
- Combined final verification: `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 python3 -m unittest tests.test_v2_finder_saved_team tests.test_v2_finder_saved_team_render tests.test_v2_finder_guardrails tests.test_v2_finder_guardrails_render tests.test_v2_contract_render.ContractRenderTest.test_every_live_contract_line`: **14 passed, no skips, 146.457s**.
- JEG-1237/#1100 overlap: owner notified on both tickets before editing. Its `92ccf8a5a5b74f8d891f50ebddf4a67dca917135` finder/CSS patch passes `git apply --check` against the corrected picker source; it was not applied. Claude edits collapse/guardrails render tests, while this regression extends the already wired saved-team render module. No shared test-file edit, fold wrapper/summary/CSS hunk or Claude branch change.
- Current main `ff351526fa93bb6be04c8cc3e336abb207f758e2` adds no runtime/test/build changes under `app/v2`, `tests`, `Makefile` or `pipelines` since integrated main `dbe06a7e`; no generated-data-only merge or repeated full local validation was performed.

### Claimed, not confirmed

- Fresh exact-head CI is pending at this checkpoint. Earlier `35c18978` CI is historical evidence, not substituted for the new fix's CI; final follow-up belongs in PR/ticket metadata to avoid restarting CI for a documentation-only result.
- No production/live verification or release action is claimed. PR #1094 stays draft and its branch is retained under the parent's hold.
