## 2026-10-28 - Interactive trades release candidate

Contract: Assemble a small user-facing candidate from interactive Compare (JEG-1214), stable before/after lineup presentation (JEG-1216), and Find a trade guardrail settings (JEG-1184). This is a draft integration branch only; full CI and final independent integration review precede any merge or deployment.

### Exact manifest

| Input | Included head | Role |
| --- | --- | --- |
| `origin/main` after merged #1062 | `3b5c94841d9b524c478d1eb05eb61ecb9665b807` | Base and first user-facing release |
| #1066, JEG-1216 | `ed0154c66422005d05d62c79a45c3b91d1ff39f6` | Stable shared lineup rows and expandable bench |
| #1067, JEG-1214 | `7b60ecad1a01d411c8dbce345fd4ce4cec1affd3` | Interactive Compare; contains the #1066 head already |
| #1068, JEG-1184 | `be501b0b296aaf29c662c12c2fcdbf99a39b18a3` | Finder guardrail settings, persistence and links |
| Corrective UI | `18335897` | Compare module controls, selected trade details immediately under the chosen row or in its phone card, and eight-team warning text |
| JEG-1184 follow-up | `8ceb47b1`, `8348541b` | Exact 1-for-1 package size and positional minimum bench backups, including saved/link state and tests |

`release/interactive-trades-20261028` merges #1067 once, then #1068 once, with no conflicts. #1066 is an ancestor of #1067 and was not picked separately. The two guardrail follow-up commits were cherry-picked after the corrective UI commit. Original feature PRs remain open; this release does not auto-close them before live verification. The candidate does not include source health, publishing controls, source taxonomy or design proposals, or fill-value math. Existing value calculations and labels remain as each feature branch supplied them.

### Verified (check named)

- `git merge-base --is-ancestor ed0154c6 origin/fe/jeg-1214-interactive-compare` returned 0; the shared helper is already in Compare.
- `CHROMIUM_PATH=/usr/bin/chromium python -m unittest tests.test_interactive_trades_release_render -q` passed. One browser visit checks both loaded rosters, live trade edits, unchanged lineup rows, bench expansion, 2-for-1 spots, Swap then Cancel, external hash and assist trade replacement, saved and linked guardrail settings, and default finder result parity with inactive guardrails.
- `CHROMIUM_PATH=/usr/bin/chromium python -m unittest tests.test_interactive_trades_release_render tests.test_v2_compare_rosters_render tests.test_jeg1216_lineup tests.test_jeg1216_lineup_render tests.test_v2_finder_guardrails tests.test_v2_finder_guardrails_render -q` passed (6 tests).
- `.github/workflows/v2-render-test.yml` runs the combined release browser test as part of the PR render check.
- `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 python -m unittest tests.test_v2_league_oppanel_render.LeagueOppPanelRenderTest.test_panel tests.test_v2_league_oppanel_render.LeagueOppPanelRenderTest.test_phone_panel_stays_inside_selected_card tests.test_v2_league_oppanel_render.LeagueOppPanelRenderTest.test_eight_team_mismatch_has_no_null_and_quick_fix_works tests.test_v2_compare_rosters_render tests.test_v2_finder_guardrails_render` passed (5 tests) on the integrated source. It exercises a complete 20-team synthetic league for the selected trade details and an eight-team mismatch quick fix.
- `python -m unittest tests.test_v2_finder_guardrails` passed (1 test); it checks exact 1-for-1, positional bench minimum exclusion, save/load, reset, and link round trips.
- `tests.test_v2_finder_groups` fails because a kept trade does not name a zero-value throw-in. `checks()` returned the same failure against `18335897:app/v2/finder.js`, before the follow-up commits. This is an existing grouping failure, not a guardrail regression.
- First-release Mac live QA passed Week 8 values and freshness, search, Compare source rows and swap verdict, league export/import/Undo, summary columns and filters, and mobile layout. Sparse synthetic rosters produced no opportunities; opportunity ranking and custom-basis link payload were not independently verified live.

### Claimed, not confirmed

- Draft release PR #1069 is open. Full remote CI and final independent integration review are pending. The broad local `make validate` run was stopped during the slower browser sweep once the PR was open, so it is not claimed as a pass. No production merge, deployment, Supabase action, or branch deletion occurred.
