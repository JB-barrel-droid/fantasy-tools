## 2026-10-28 - JEG-1216 lineup comparison stability

Contract: build the shared presentation helper for the league opportunity panel and interactive Compare. Preserve the finder-selected starters, align unchanged players within each slot group, and expose bench rows through an accessible control. Work starts from release PR #1062 head `50f76b95` and must wait for JEG-1213 before production merge.

### Verified (check named)

- `git ls-remote origin refs/pull/1062/head` returned `50f76b95a05d6abd8b5119d7d68a9c5faf04abc7`; this branch was created from that exact commit.
- `python3 -m unittest tests.test_jeg1216_lineup tests.test_build_v2_page -v` passed after correcting a wrong test expectation about the selected FLEX player.
- `RENDER_TESTS_REQUIRED=1 CHROMIUM_PATH=/usr/bin/chromium python3 -m unittest tests.test_jeg1216_lineup_render tests.test_v2_league_oppanel_render.LeagueOppPanelRenderTest.test_panel -v` passed: two tests, including desktop and 390 px checks.
- The final `tests.test_jeg1216_lineup_render` run passed after adding a visible genuine-gain assertion and an unpriced bench-cell assertion. It checks keyboard expansion and no document overflow at 390 px.
- `RENDER_TESTS_REQUIRED=1 CHROMIUM_PATH=/usr/bin/chromium python3 -m unittest tests.test_jeg1216_lineup_render tests.test_jeg1213_acceptance_render -v` passed: 12 tests, including the original Find a trade acceptance flows. This run preceded only the final league table fit wording change; the final focused render rerun passed afterward.
- `python3 -m unittest tests.test_render_sweep_coverage tests.test_render_sweep_shards -v` passed 10 tests after registering the new test modules in the Makefile.
- Draft [PR #1066](https://github.com/JB-barrel-droid/fantasy-tools/pull/1066) was created with base `release/league-finder-20261028` and head `fe/jeg-1216-lineup-stability`; the feature is not in #1062.

### Claimed, not confirmed

- Production behavior is not verified; JEG-1213 and its release candidate have not landed in this session. Exact-final-head CI and an independent review remain required.
- A duplicate local `make validate` was stopped after its reference/sync/guard checks and the core suites through `tests.test_v2_phone_source_links_render` passed, because draft PR #1066 had started the full Preview build and v2 render workflows. The local command exited 130 by intentional interrupt, not a test failure.
- Interactive Compare is owned by its separate feature worker and is expected to consume `TradeValueLineupComparison` after this branch is available.
