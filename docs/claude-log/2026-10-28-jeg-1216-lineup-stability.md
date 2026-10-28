## 2026-10-28 - JEG-1216 lineup comparison stability

Contract: build the shared presentation helper for the league opportunity panel and interactive Compare. Preserve the finder-selected starters, align unchanged players within each slot group, and expose bench rows through an accessible control. Work starts from release PR #1062 head `50f76b95` and must wait for JEG-1213 before production merge.

### Verified (check named)

- `git ls-remote origin refs/pull/1062/head` returned `50f76b95a05d6abd8b5119d7d68a9c5faf04abc7`; this branch was created from that exact commit.
- `python3 -m unittest tests.test_jeg1216_lineup tests.test_build_v2_page -v` passed after correcting a wrong test expectation about the selected FLEX player.
- `RENDER_TESTS_REQUIRED=1 CHROMIUM_PATH=/usr/bin/chromium python3 -m unittest tests.test_jeg1216_lineup_render tests.test_v2_league_oppanel_render.LeagueOppPanelRenderTest.test_panel -v` passed: two tests, including desktop and 390 px checks.

### Claimed, not confirmed

- Production behavior is not verified; JEG-1213 and its release candidate have not landed in this session.
- Interactive Compare is owned by its separate feature worker and is expected to consume `TradeValueLineupComparison` after this branch is available.
